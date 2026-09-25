"""拆分 PDF 面板。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import (
    build_groups,
    default_output_dir,
    open_reader,
    parse_groups,
    read_info,
    split,
)
from ...core.errors import PdfError
from ..widgets import Hint, PathRow, make_password_edit, reveal_in_file_manager
from .base import Panel

MODE_DESCRIPTIONS = {
    "every_n": "每 N 页生成一个 PDF，适合把长文档切成等长的若干份。",
    "each": "每一页导出为一个独立 PDF，适合批量分发单页文件。",
    "ranges": "按你写的页码范围分组，每组一个文件。分号分组，逗号是组内分隔。",
    "bookmarks": "按文档的顶层书签切分，扫描书、规范、合同最常用。",
}

MODE_ORDER = ("every_n", "each", "ranges", "bookmarks")


class SplitPanel(Panel):
    title = "拆分 PDF"
    description = "把一个大文件切成多个小文件。四种切法任选，切分前可先预览结果。"

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(self.make_header(self.title, self.description))

        self.source = PathRow("源文件")
        self.source.changed.connect(self._on_source_changed)
        layout.addWidget(self.source)

        self.file_info = Hint("尚未选择文件")
        layout.addWidget(self.file_info)

        layout.addWidget(self._build_mode_group(), 1)
        layout.addWidget(self._build_output_group())

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.preview_button = QPushButton("预览结果")
        self.preview_button.clicked.connect(self._on_preview)
        action_row.addWidget(self.preview_button)
        self.start_button = self.make_primary_button("开始拆分", self._on_start)
        action_row.addWidget(self.start_button)
        layout.addLayout(action_row)

    # ------------------------------------------------------------------ 界面构建

    def _build_mode_group(self) -> QWidget:
        box = QGroupBox("拆分方式")
        outer = QHBoxLayout(box)
        outer.setSpacing(18)

        choices = QWidget()
        choices_layout = QVBoxLayout(choices)
        choices_layout.setContentsMargins(0, 0, 0, 0)
        choices_layout.setSpacing(6)
        self.mode_group = QButtonGroup(self)
        labels = {"every_n": "每 N 页一个文件", "each": "每页一个文件", "ranges": "按页码范围分组", "bookmarks": "按书签层级"}
        for index, mode in enumerate(MODE_ORDER):
            radio = QRadioButton(labels[mode])
            radio.setProperty("mode", mode)
            self.mode_group.addButton(radio, index)
            choices_layout.addWidget(radio)
            if index == 0:
                radio.setChecked(True)
        choices_layout.addStretch(1)
        outer.addWidget(choices)

        self.params = QStackedWidget()
        self.params.addWidget(self._build_every_n_params())
        self.params.addWidget(self._build_each_params())
        self.params.addWidget(self._build_ranges_params())
        self.params.addWidget(self._build_bookmarks_params())
        outer.addWidget(self.params, 1)

        self.mode_group.idClicked.connect(self._on_mode_changed)
        return box

    def _build_every_n_params(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        row = QHBoxLayout()
        row.addWidget(QLabel("每"))
        self.every_n = QSpinBox()
        self.every_n.setRange(1, 9999)
        self.every_n.setValue(1)
        self.every_n.setSuffix(" 页")
        self.every_n.setFixedWidth(110)
        row.addWidget(self.every_n)
        row.addWidget(QLabel("切分为一个文件"))
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(Hint("例如 100 页的文档填 20，会得到 5 个文件。"))
        layout.addStretch(1)
        return page

    def _build_each_params(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(Hint("文档的每一页都会被导出为单独的 PDF 文件。"))
        layout.addStretch(1)
        return page

    def _build_ranges_params(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        row = QHBoxLayout()
        row.addWidget(QLabel("范围"))
        self.ranges_edit = QLineEdit()
        self.ranges_edit.setPlaceholderText("例如：1-3;5-8;10-")
        row.addWidget(self.ranges_edit, 1)
        layout.addLayout(row)
        layout.addWidget(
            Hint("分号 ; 分隔不同的输出文件；逗号 , 表示同一文件内的多个范围。"
                 "「10-」表示从第 10 页到结尾。")
        )
        layout.addStretch(1)
        return page

    def _build_bookmarks_params(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.bookmark_hint = Hint("按文档的顶层书签切分，每个书签对应一个文件。")
        layout.addWidget(self.bookmark_hint)
        layout.addStretch(1)
        return page

    def _build_output_group(self) -> QWidget:
        box = QGroupBox("输出设置")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        self.output = PathRow("输出目录", mode="directory", placeholder="拆分结果的存放位置")
        layout.addWidget(self.output)

        password_row = QHBoxLayout()
        password_row.addWidget(QLabel("密码"))
        self.password = make_password_edit()
        self.password.setFixedWidth(240)
        password_row.addWidget(self.password)
        password_row.addStretch(1)
        layout.addLayout(password_row)

        self.plan_list = QListWidget()
        self.plan_list.setMaximumHeight(110)
        self.plan_list.setVisible(False)
        layout.addWidget(self.plan_list)
        return box

    # ------------------------------------------------------------------ 交互

    def current_mode(self) -> str:
        index = self.mode_group.checkedId()
        return MODE_ORDER[index] if 0 <= index < len(MODE_ORDER) else "every_n"

    def _on_mode_changed(self, index: int) -> None:
        # 直接调用时按钮组状态未必已更新，这里补一次，
        # 保证「选中的单选按钮」和「当前模式」始终一致。
        button = self.mode_group.button(index)
        if button is not None:
            button.setChecked(True)
        self.params.setCurrentIndex(index)
        self.plan_list.setVisible(False)

    def _on_source_changed(self, path: str) -> None:
        self.file_info.setText("正在读取文件信息…")
        if not path:
            self.file_info.setText("尚未选择文件")
            self.output.clear()
            return
        try:
            info = read_info(path, self.password.text() or None)
        except PdfError as exc:
            self.file_info.setText(f"⚠ {exc}")
            return

        detail = f"共 {info.page_count} 页 · {info.file_size_text}"
        if info.first_page:
            detail += f" · 首页 {info.first_page.describe()}"
        if not info.is_uniform_size:
            detail += f" · 页面尺寸不统一（{len(info.size_summary)} 种）"
        self.file_info.setText(detail)

        self.bookmark_hint.setText(
            f"该文档有 {info.outline_count} 个书签，可以按书签拆分。"
            if info.has_outline
            else "该文档没有顶层书签，无法按书签拆分。"
        )
        self.output.set_path(default_output_dir(path, "_拆分"))

    def _compute_plan(self) -> list[tuple[str, list[int]]]:
        """计算切分方案（不写盘），供预览与执行共用。"""
        path = self.source.path
        if not path:
            raise PdfError("请先选择要拆分的 PDF 文件。")

        reader = open_reader(path, self.password.text() or None)
        total_pages = len(reader.pages)
        mode = self.current_mode()

        groups = None
        if mode == "ranges":
            groups = parse_groups(self.ranges_edit.text(), total_pages)

        return build_groups(
            reader,
            total_pages,
            mode=mode,
            pages_per_file=self.every_n.value(),
            groups=groups,
        )

    def _on_preview(self) -> None:
        def action() -> None:
            plan = self._compute_plan()
            prefix = Path(self.source.path).stem
            self.plan_list.clear()
            for suffix, indexes in plan:
                pages = f"{len(indexes)} 页"
                span = f"（第 {indexes[0] + 1}–{indexes[-1] + 1} 页）" if len(indexes) > 1 else f"（第 {indexes[0] + 1} 页）"
                self.plan_list.addItem(f"{prefix}_{suffix}.pdf　·　{pages}{span}")
            self.plan_list.setVisible(True)
            if len(plan) > 60:
                self.plan_list.addItem(f"…… 以及其他 {len(plan) - 60} 个文件")

        self.guard(action)

    def _on_start(self) -> None:
        path = self.source.path
        if not path:
            self.show_warning("请先选择文件", "还没有选择要拆分的 PDF。")
            return

        output_dir = self.output.path or str(default_output_dir(path, "_拆分"))
        self.output.set_path(output_dir)
        mode = self.current_mode()
        password = self.password.text() or None
        every_n = self.every_n.value()
        ranges_text = self.ranges_edit.text()

        def job(context):
            # 解析放在任务内部，这样范围写错时错误会走统一的失败通道
            groups = None
            if mode == "ranges":
                reader = open_reader(path, password)
                groups = parse_groups(ranges_text, len(reader.pages))
            return split(
                path,
                output_dir,
                mode=mode,
                pages_per_file=every_n,
                groups=groups,
                password=password,
                ctx=context,
            )

        self.start_task(job, "正在拆分 PDF…")

    def on_task_finished(self, result) -> None:
        files: list[Path] = list(result)
        self.show_info("拆分完成", Panel.result_summary(files, "已生成"))
        reveal_in_file_manager(files[0] if files else self.output.path)
