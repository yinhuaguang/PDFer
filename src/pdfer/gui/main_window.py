"""PDFer 主窗口：左侧功能导航 + 右侧面板，底部统一状态栏。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStyle,
    QWidget,
)

from ..icon import render_icon
from ..version import __app_desc__, __app_name__, __homepage__, __license__, __version__
from .panels import (
    ConvertPanel,
    ExtractPanel,
    InfoPanel,
    MergePanel,
    PagesPanel,
    Panel,
    SplitPanel,
    ToolsPanel,
)
from .taskrunner import TaskRunner
from .widgets import pil_to_qpixmap

SIDEBAR_WIDTH = 172
SIDEBAR_ITEM_HEIGHT = 42

#: (面板类, 侧边栏图标)
PANEL_SPECS: tuple[tuple[type[Panel], QStyle.StandardPixmap], ...] = (
    (MergePanel, QStyle.StandardPixmap.SP_FileDialogDetailedView),
    (SplitPanel, QStyle.StandardPixmap.SP_FileDialogListView),
    (PagesPanel, QStyle.StandardPixmap.SP_FileDialogContentsView),
    (ExtractPanel, QStyle.StandardPixmap.SP_FileDialogInfoView),
    (ConvertPanel, QStyle.StandardPixmap.SP_FileIcon),
    (InfoPanel, QStyle.StandardPixmap.SP_MessageBoxInformation),
    (ToolsPanel, QStyle.StandardPixmap.SP_ComputerIcon),
)

ABOUT_HTML = f"""
<h3>{__app_name__} {__version__}</h3>
<p>{__app_desc__}</p>
<p style="color:#6b7280;">
开源许可：{__license__}<br>
项目主页：<a href="{__homepage__}">{__homepage__}</a>
</p>
<p style="color:#6b7280;font-size:12px;">
本程序使用 Qt / PySide6（LGPL-3.0），版权归 The Qt Company 所有。<br>
完整的第三方依赖与许可证清单见随程序附带的 THIRD_PARTY_LICENSES.md。
</p>
"""

LICENSE_HTML = """
<h3>第三方依赖许可证</h3>
<table cellpadding="4">
<tr><td>pypdf</td><td>BSD-3-Clause</td></tr>
<tr><td>pikepdf / qpdf</td><td>MPL-2.0</td></tr>
<tr><td>pypdfium2 / PDFium</td><td>Apache-2.0 / BSD-3-Clause</td></tr>
<tr><td>Pillow</td><td>MIT-CMU</td></tr>
<tr><td>PySide6 / Qt</td><td>LGPL-3.0</td></tr>
</table>
<p style="color:#6b7280;font-size:12px;">
PySide6 / Qt 采用 LGPL-3.0。PDFer 仓库公开完整源码、依赖与构建脚本，
并同时保留单文件与目录版构建方式。完整说明见 THIRD_PARTY_LICENSES.md。
</p>
"""


class MainWindow(QMainWindow):
    """应用主窗口。

    同时承担三个职责：承载功能面板、把后台任务的状态映射到状态栏、
    以及把任务结果派发回发起该任务的面板。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__app_name__} {__version__} — {__app_desc__}")
        self.resize(1080, 760)
        self.setMinimumSize(QSize(880, 620))
        self.setAcceptDrops(True)
        self.setWindowIcon(QIcon(pil_to_qpixmap(render_icon(256))))

        self.runner = TaskRunner(self)
        self._panel_indexes: dict[type[Panel], int] = {}

        self._build_ui()
        self._build_menu()
        self._connect_runner()

    # ------------------------------------------------------------------ 界面构建

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(SIDEBAR_WIDTH)

        self.stack = QStackedWidget()

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        for index, (panel_class, pixmap) in enumerate(PANEL_SPECS):
            panel = panel_class(self.runner)
            self.stack.addWidget(panel)
            self._panel_indexes[panel_class] = index

            item = QListWidgetItem(self.style().standardIcon(pixmap), panel.title)
            item.setSizeHint(QSize(0, SIDEBAR_ITEM_HEIGHT))
            self.sidebar.addItem(item)

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(self._panel_indexes[MergePanel])

        self.merge_panel: MergePanel = self._panel(MergePanel)
        self.pages_panel: PagesPanel = self._panel(PagesPanel)
        self.split_panel: SplitPanel = self._panel(SplitPanel)

        self._build_status_bar()

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        self.status_label = QLabel("就绪")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(240)
        self.progress.setVisible(False)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.runner.cancel)

        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.progress)
        bar.addPermanentWidget(self.cancel_button)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        open_action = QAction("打开 PDF…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        add_action = QAction("添加到合并列表…", self)
        add_action.triggered.connect(self._on_add_to_merge)
        file_menu.addAction(add_action)

        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        about_action = QAction("关于 PDFer", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
        licenses_action = QAction("第三方许可证", self)
        licenses_action.triggered.connect(self._on_licenses)
        help_menu.addAction(licenses_action)

    def _panel(self, panel_class: type[Panel]) -> Panel:
        return self.stack.widget(self._panel_indexes[panel_class])  # type: ignore[return-value]

    def show_panel(self, panel_class: type[Panel]) -> None:
        self.sidebar.setCurrentRow(self._panel_indexes[panel_class])

    # ------------------------------------------------------------------ 任务状态

    def _connect_runner(self) -> None:
        self.runner.started.connect(self._on_task_started)
        self.runner.progress.connect(self._on_task_progress)
        self.runner.finished.connect(self._on_task_finished)
        self.runner.failed.connect(self._on_task_failed)
        self.runner.cancelled.connect(self._on_task_cancelled)

    def _on_task_started(self, description: str) -> None:
        self.status_label.setText(description)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)

    def _on_task_progress(self, current: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
        if message:
            self.status_label.setText(message)

    def _reset_progress(self, message: str) -> None:
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.status_label.setText(message)

    def _active_panel(self) -> Panel | None:
        owner = self.runner.owner
        return owner if isinstance(owner, Panel) else None

    def _on_task_finished(self, result: object) -> None:
        panel = self._active_panel()
        self._reset_progress("就绪")
        if panel is not None:
            panel.on_task_finished(result)

    def _on_task_failed(self, message: str) -> None:
        panel = self._active_panel()
        self._reset_progress("操作失败")
        if panel is not None:
            panel.on_task_failed(message)
        else:
            QMessageBox.critical(self, "操作失败", message)

    def _on_task_cancelled(self) -> None:
        self._reset_progress("已取消")
        panel = self._active_panel()
        if panel is not None:
            panel.show_info("已取消", "操作已被取消，未完整的输出文件建议手动删除。")

    # ------------------------------------------------------------------ 文件入口

    def _on_open(self) -> None:
        from .widgets import browse_pdf_files

        paths = browse_pdf_files(self, "打开 PDF（可多选）")
        if paths:
            self.open_files(paths)

    def _on_add_to_merge(self) -> None:
        from .widgets import browse_pdf_files

        paths = browse_pdf_files(self, "选择要合并的 PDF（可多选）")
        if paths:
            self.merge_panel.add_files(paths)
            self.show_panel(MergePanel)

    def open_files(self, paths: list[str]) -> None:
        """按文件数量自动选择最合适的面板。"""
        pdfs = [p for p in paths if Path(p).suffix.lower() == ".pdf"]
        if not pdfs:
            return
        if len(pdfs) == 1:
            self.pages_panel.source.set_path(pdfs[0])
            self.show_panel(PagesPanel)
        else:
            self.merge_panel.add_files(pdfs)
            self.show_panel(MergePanel)

    # ------------------------------------------------------------------ 拖放

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.open_files(paths)
            event.acceptProposedAction()

    # ------------------------------------------------------------------ 帮助

    def _on_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(f"关于 {__app_name__}")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(ABOUT_HTML)
        box.exec()

    def _on_licenses(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("第三方许可证")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(LICENSE_HTML)
        box.exec()

    # ------------------------------------------------------------------ 退出

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.runner.busy:
            reply = QMessageBox.question(
                self,
                "任务正在进行",
                "还有任务没有执行完，现在退出会中断它。确定退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.runner.cancel()
            if not self.runner.wait_for_done(5000):
                self.status_label.setText("正在等待后台任务结束…")
        event.accept()
