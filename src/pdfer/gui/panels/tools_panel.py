"""实用工具面板：图片转 PDF、优化压缩、设置/移除密码。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import (
    OptimizeResult,
    default_output_path,
    human_size,
    images_to_pdf,
    optimize_pdf,
    protect_pdf,
    unprotect_pdf,
    unique_path,
)
from ..widgets import DropFileList, Hint, IMAGE_FILTER, PathRow, make_password_edit, reveal_in_file_manager
from .base import Panel

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


class ToolsPanel(Panel):
    title = "实用工具"
    description = "图片转 PDF、无损优化压缩，以及 PDF 打开密码的设置与移除。"

    def _build(self) -> None:
        self._last_action = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(self.make_header(self.title, self.description))

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_images_tab(), "图片 → PDF")
        self.tabs.addTab(self._build_optimize_tab(), "优化压缩")
        self.tabs.addTab(self._build_protect_tab(), "设置密码")
        self.tabs.addTab(self._build_unprotect_tab(), "移除密码")
        layout.addWidget(self.tabs, 1)

    # ------------------------------------------------------------------ 图片转 PDF

    def _build_images_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(Hint("支持 PNG / JPEG / WebP / BMP / TIFF；列表顺序就是 PDF 页顺序，可拖动调整。"))

        self.image_list = DropFileList()
        self.image_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.image_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.image_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.image_list.files_dropped.connect(self._add_images)
        layout.addWidget(self.image_list, 1)

        toolbar = QHBoxLayout()
        add_button = QPushButton("添加图片…")
        add_button.clicked.connect(self._browse_images)
        toolbar.addWidget(add_button)
        remove_button = QPushButton("移除所选")
        remove_button.clicked.connect(self._remove_images)
        toolbar.addWidget(remove_button)
        clear_button = QPushButton("清空")
        clear_button.clicked.connect(self.image_list.clear)
        toolbar.addWidget(clear_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        options = QHBoxLayout()
        options.addWidget(QLabel("页面 DPI"))
        self.image_dpi = QSpinBox()
        self.image_dpi.setRange(36, 1200)
        self.image_dpi.setValue(150)
        self.image_dpi.setSuffix(" dpi")
        options.addWidget(self.image_dpi)

        options.addWidget(QLabel("图片质量"))
        self.image_quality = QSpinBox()
        self.image_quality.setRange(1, 100)
        self.image_quality.setValue(92)
        self.image_quality.setSuffix(" %")
        options.addWidget(self.image_quality)
        options.addStretch(1)
        layout.addLayout(options)

        self.images_output = PathRow("保存为", mode="save_file", placeholder="合成后的 PDF 保存位置")
        layout.addWidget(self.images_output)

        row = QHBoxLayout()
        row.addStretch(1)
        button = self.make_primary_button("生成 PDF", self._start_images)
        row.addWidget(button)
        layout.addLayout(row)
        return page

    def _browse_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", IMAGE_FILTER)
        if paths:
            self._add_images(paths)

    def _add_images(self, paths: list[str]) -> None:
        existing = {
            self.image_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.image_list.count())
        }
        added = 0
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() not in _IMAGE_SUFFIXES or not path.is_file():
                continue
            resolved = str(path.resolve())
            if resolved in existing:
                continue
            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, resolved)
            self.image_list.addItem(item)
            existing.add(resolved)
            added += 1

        if added and not self.images_output.path:
            first = Path(self.image_list.item(0).data(Qt.ItemDataRole.UserRole))
            self.images_output.set_path(first.with_name(f"{first.stem}_合成.pdf"))

    def _remove_images(self) -> None:
        for item in list(self.image_list.selectedItems()):
            self.image_list.takeItem(self.image_list.row(item))

    def _image_paths(self) -> list[str]:
        return [
            str(self.image_list.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self.image_list.count())
        ]

    def _start_images(self) -> None:
        paths = self._image_paths()
        if not paths:
            self.show_warning("请先添加图片", "至少需要一张图片才能生成 PDF。")
            return
        default = Path(paths[0]).with_name(f"{Path(paths[0]).stem}_合成.pdf")
        output = Path(self.images_output.path) if self.images_output.path else default
        output = unique_path(output)
        self.images_output.set_path(output)
        dpi = self.image_dpi.value()
        quality = self.image_quality.value()
        self._last_action = "images"

        def job(context):
            return images_to_pdf(paths, output, dpi=dpi, jpeg_quality=quality, ctx=context)

        self.start_task(job, "正在把图片合成为 PDF…")

    # ------------------------------------------------------------------ 优化压缩

    def _build_optimize_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(
            Hint(
                "无损重写 PDF 结构、压缩可压缩的数据流并生成对象流。"
                "不会主动降低图片分辨率；已经高度压缩的文件可能变化很小。"
            )
        )
        self.optimize_source = PathRow("源文件")
        self.optimize_source.changed.connect(self._optimize_source_changed)
        layout.addWidget(self.optimize_source)

        row = QHBoxLayout()
        row.addWidget(QLabel("打开密码"))
        self.optimize_password = make_password_edit()
        self.optimize_password.setPlaceholderText("源文件未加密则留空")
        row.addWidget(self.optimize_password, 1)
        layout.addLayout(row)

        self.optimize_output = PathRow("保存为", mode="save_file", placeholder="优化后的 PDF 保存位置")
        layout.addWidget(self.optimize_output)
        layout.addStretch(1)

        action = QHBoxLayout()
        action.addStretch(1)
        action.addWidget(self.make_primary_button("开始优化", self._start_optimize))
        layout.addLayout(action)
        return page

    def _optimize_source_changed(self, path: str) -> None:
        if path:
            self.optimize_output.set_path(default_output_path(path, "_优化"))

    def _start_optimize(self) -> None:
        source = self.optimize_source.path
        if not source:
            self.show_warning("请先选择文件", "还没有选择要优化的 PDF。")
            return
        output = Path(self.optimize_output.path) if self.optimize_output.path else default_output_path(source, "_优化")
        output = unique_path(output)
        self.optimize_output.set_path(output)
        password = self.optimize_password.text() or None
        self._last_action = "optimize"

        def job(context):
            return optimize_pdf(source, output, password=password, ctx=context)

        self.start_task(job, "正在优化 PDF…")

    # ------------------------------------------------------------------ 设置密码

    def _build_protect_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(Hint("使用 AES-256 为 PDF 设置打开密码；源文件不会被覆盖。"))
        self.protect_source = PathRow("源文件")
        self.protect_source.changed.connect(self._protect_source_changed)
        layout.addWidget(self.protect_source)

        self.protect_source_password = make_password_edit("源文件已有密码时填写，否则留空")
        layout.addWidget(self._password_row("原密码", self.protect_source_password))

        self.protect_new_password = make_password_edit("新的打开密码")
        layout.addWidget(self._password_row("新密码", self.protect_new_password))

        self.protect_confirm = make_password_edit("再次输入新的打开密码")
        layout.addWidget(self._password_row("确认密码", self.protect_confirm))

        self.protect_output = PathRow("保存为", mode="save_file", placeholder="加密后的 PDF 保存位置")
        layout.addWidget(self.protect_output)
        layout.addStretch(1)

        action = QHBoxLayout()
        action.addStretch(1)
        action.addWidget(self.make_primary_button("设置密码", self._start_protect))
        layout.addLayout(action)
        return page

    def _protect_source_changed(self, path: str) -> None:
        if path:
            self.protect_output.set_path(default_output_path(path, "_加密"))

    def _start_protect(self) -> None:
        source = self.protect_source.path
        if not source:
            self.show_warning("请先选择文件", "还没有选择要加密的 PDF。")
            return
        password = self.protect_new_password.text()
        if not password:
            self.show_warning("密码不能为空", "请输入新的打开密码。")
            return
        if password != self.protect_confirm.text():
            self.show_warning("两次密码不一致", "请重新确认新密码。")
            return

        output = Path(self.protect_output.path) if self.protect_output.path else default_output_path(source, "_加密")
        output = unique_path(output)
        self.protect_output.set_path(output)
        source_password = self.protect_source_password.text() or None
        self._last_action = "protect"

        def job(context):
            return protect_pdf(
                source,
                output,
                user_password=password,
                source_password=source_password,
                ctx=context,
            )

        self.start_task(job, "正在设置 PDF 密码…")

    # ------------------------------------------------------------------ 移除密码

    def _build_unprotect_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(Hint("需要知道当前 PDF 的正确打开密码；本功能不会尝试破解未知密码。"))
        self.unprotect_source = PathRow("源文件")
        self.unprotect_source.changed.connect(self._unprotect_source_changed)
        layout.addWidget(self.unprotect_source)

        self.unprotect_password = make_password_edit("当前打开密码")
        layout.addWidget(self._password_row("当前密码", self.unprotect_password))

        self.unprotect_output = PathRow("保存为", mode="save_file", placeholder="移除密码后的 PDF 保存位置")
        layout.addWidget(self.unprotect_output)
        layout.addStretch(1)

        action = QHBoxLayout()
        action.addStretch(1)
        action.addWidget(self.make_primary_button("移除密码", self._start_unprotect))
        layout.addLayout(action)
        return page

    def _unprotect_source_changed(self, path: str) -> None:
        if path:
            self.unprotect_output.set_path(default_output_path(path, "_解密"))

    def _start_unprotect(self) -> None:
        source = self.unprotect_source.path
        if not source:
            self.show_warning("请先选择文件", "还没有选择要处理的 PDF。")
            return
        password = self.unprotect_password.text()
        if not password:
            self.show_warning("请输入密码", "需要当前打开密码才能生成无密码副本。")
            return

        output = Path(self.unprotect_output.path) if self.unprotect_output.path else default_output_path(source, "_解密")
        output = unique_path(output)
        self.unprotect_output.set_path(output)
        self._last_action = "unprotect"

        def job(context):
            return unprotect_pdf(source, output, password=password, ctx=context)

        self.start_task(job, "正在移除 PDF 密码…")

    @staticmethod
    def _password_row(label: str, edit: QLineEdit) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(label))
        row.addWidget(edit, 1)
        return box

    # ------------------------------------------------------------------ 结果

    def on_task_finished(self, result) -> None:
        if isinstance(result, OptimizeResult):
            before = human_size(result.before_bytes)
            after = human_size(result.after_bytes)
            delta = result.before_bytes - result.after_bytes
            if delta > 0:
                detail = f"优化完成：{before} → {after}，减少 {human_size(delta)}"
            elif delta < 0:
                detail = f"优化完成：{before} → {after}。该文件原本已高度压缩，优化后略有增大。"
            else:
                detail = f"优化完成：{before} → {after}"
            detail += f"\n\n位置：{result.output.parent}"
            self.show_info("优化完成", detail)
            reveal_in_file_manager(result.output)
            return

        path = Path(result)
        labels = {
            "images": "图片已合成为 PDF",
            "protect": "密码已设置",
            "unprotect": "密码已移除",
        }
        title = labels.get(self._last_action, "操作完成")
        size = human_size(path.stat().st_size) if path.exists() else "未知"
        self.show_info(title, f"已生成：{path.name}\n大小：{size}\n位置：{path.parent}")
        reveal_in_file_manager(path)
