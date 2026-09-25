"""可复用的界面小部件。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QWidget,
)

TEXT_FILTER = "文本文件 (*.txt);;所有文件 (*.*)"
PDF_FILTER = "PDF 文件 (*.pdf)"
IMAGE_FILTER = "图片 (*.png *.jpg *.jpeg *.webp);;所有文件 (*.*)"


def browse_pdf_files(parent: QWidget, title: str = "选择 PDF 文件") -> list[str]:
    """多选 PDF，返回路径列表。"""
    paths, _ = QFileDialog.getOpenFileNames(parent, title, "", PDF_FILTER)
    return paths


def browse_pdf_file(parent: QWidget, title: str = "选择 PDF 文件") -> str:
    """单选 PDF，取消时返回空串。"""
    path, _ = QFileDialog.getOpenFileName(parent, title, "", PDF_FILTER)
    return path


def browse_save_file(
    parent: QWidget, title: str, default_path: str, filters: str = PDF_FILTER
) -> str:
    """选择保存路径，取消时返回空串。"""
    path, _ = QFileDialog.getSaveFileName(parent, title, default_path, filters)
    return path


def browse_directory(parent: QWidget, title: str = "选择输出目录") -> str:
    """选择目录，取消时返回空串。"""
    return QFileDialog.getExistingDirectory(parent, title, "")


def make_password_edit(placeholder: str = "打开密码（文件未加密则留空）") -> QLineEdit:
    """生成一个密码输入框。"""
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    edit.setPlaceholderText(placeholder)
    edit.setClearButtonEnabled(True)
    return edit


def pil_to_qpixmap(image) -> QPixmap:
    """PIL 图像 → QPixmap。

    注意 ``QImage`` 并不持有传入的缓冲区，必须 ``copy()`` 一次，
    否则底层 bytes 被回收后会画出花屏。
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    raw = image.tobytes("raw", "RGBA")
    qimage = QImage(raw, image.width, image.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


class PathRow(QWidget):
    """一行「标签 + 只读路径框 + 浏览按钮」。

    统一了全项目的路径输入外观，也让面板代码少一半样板。
    """

    changed = Signal(str)

    def __init__(
        self,
        label: str,
        *,
        mode: str = "open_file",
        placeholder: str = "尚未选择",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._placeholder = placeholder

        self.label = QLabel(label)
        self.label.setMinimumWidth(72)

        self.edit = QLineEdit()
        self.edit.setReadOnly(True)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.edit.setCursorPosition(0)

        self.button = QPushButton("浏览…")
        self.button.setFixedWidth(84)
        self.button.clicked.connect(self._on_browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.label)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    @property
    def path(self) -> str:
        return self.edit.text()

    def set_path(self, path: str | os.PathLike[str]) -> None:
        text = str(path) if path else ""
        self.edit.setText(text)
        self.edit.setToolTip(text)
        self.edit.setCursorPosition(0)
        self.changed.emit(text)

    def clear(self) -> None:
        self.set_path("")

    def _on_browse(self) -> None:
        selected = ""
        if self._mode == "open_file":
            selected = browse_pdf_file(self)
        elif self._mode == "directory":
            selected = browse_directory(self)
        elif self._mode == "save_file":
            current = self.path or self._placeholder
            filters = TEXT_FILTER if current.lower().endswith(".txt") else PDF_FILTER
            selected = browse_save_file(self, "另存为", current, filters)
        if selected:
            self.set_path(selected)


class Hint(QLabel):
    """次要说明文字。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("hint")
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)


class DropFileList(QListWidget):
    """可接收外部文件拖入的列表；内部拖动仍用于排序。"""

    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setToolTip("可直接把文件拖到这里")

    @staticmethod
    def _local_files(event) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名约定
        if self._local_files(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._local_files(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        files = self._local_files(event)
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


def reveal_in_file_manager(path: str | os.PathLike[str]) -> None:
    """在系统文件管理器中定位文件（尽力而为，失败静默）。"""
    target = Path(path)
    try:
        if sys.platform == "win32":
            if target.is_dir():
                os.startfile(str(target))  # noqa: S606 - 本地可信路径
            else:
                subprocess.Popen(["explorer", "/select,", str(target)])  # noqa: S603,S607
        elif sys.platform == "darwin":
            args = ["open", "-R", str(target)] if target.is_file() else ["open", str(target)]
            subprocess.Popen(args)  # noqa: S603
        else:
            folder = target if target.is_dir() else target.parent
            subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603,S607
    except Exception:  # noqa: BLE001 - 打不开资源管理器不值得打断用户
        pass
