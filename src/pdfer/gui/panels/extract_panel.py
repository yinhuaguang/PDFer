"""提取内容面板：导出内嵌图片或文字。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import (
    ExtractImagesResult,
    default_output_dir,
    default_output_path,
    extract_images,
    extract_text,
    human_size,
    parse_pages,
    read_info,
)
from ...core.errors import PdfError
from ..widgets import Hint, PathRow, make_password_edit, reveal_in_file_manager
from .base import Panel

TEXT_FILTER = "文本文件 (*.txt);;所有文件 (*.*)"


class ExtractPanel(Panel):
    title = "提取内容"
    description = (
        "把 PDF 里的内嵌图片或文字单独导出。图片按原始数据写出，"
        "画质不会有任何损失。"
    )

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

        layout.addWidget(self._build_choice_group(), 1)
        layout.addWidget(self._build_output_group())

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.start_button = self.make_primary_button("开始提取", self._on_start)
        action_row.addWidget(self.start_button)
        layout.addLayout(action_row)

    def _build_choice_group(self) -> QWidget:
        box = QGroupBox("提取内容")
        outer = QVBoxLayout(box)
        outer.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(20)
        self.choice_group = QButtonGroup(self)
        for index, text in enumerate(("内嵌图片", "文字内容")):
            radio = QRadioButton(text)
            self.choice_group.addButton(radio, index)
            row.addWidget(radio)
            if index == 0:
                radio.setChecked(True)
        row.addStretch(1)
        outer.addLayout(row)

        self.params = QStackedWidget()
        self.params.addWidget(self._build_image_params())
        self.params.addWidget(self._build_text_params())

        self.choice_group.idClicked.connect(self.params.setCurrentIndex)
        self.choice_group.idClicked.connect(self._on_choice_changed)
        outer.addWidget(self.params, 1)
        return box

    def _build_image_params(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("忽略小于"))
        self.min_width = QSpinBox()
        self.min_width.setRange(0, 20000)
        self.min_width.setValue(32)
        self.min_width.setSuffix(" px 宽")
        self.min_width.setFixedWidth(120)
        row.addWidget(self.min_width)

        self.min_height = QSpinBox()
        self.min_height.setRange(0, 20000)
        self.min_height.setValue(32)
        self.min_height.setSuffix(" px 高")
        self.min_height.setFixedWidth(120)
        row.addWidget(self.min_height)
        row.addWidget(QLabel("的图片"))
        row.addStretch(1)
        layout.addLayout(row)

        self.dedupe = QCheckBox("相同图片只导出一次（合同里的 logo 会在每页重复出现）")
        self.dedupe.setChecked(True)
        layout.addWidget(self.dedupe)

        layout.addWidget(
            Hint("提示：扫掉的证件、票据扫描件通常整页就是一张图，"
                 "把阈值调到 0 可以强制全部导出。")
        )
        layout.addStretch(1)
        return page

    def _build_text_params(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("页码范围"))
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("留空表示全部，例如 1-5,8")
        row.addWidget(self.pages_edit, 1)
        layout.addLayout(row)

        self.page_markers = QCheckBox("在每页文字前插入「第 N 页」分隔标记")
        self.page_markers.setChecked(True)
        layout.addWidget(self.page_markers)

        layout.addWidget(
            Hint("注意：本功能读取的是 PDF 里已有的文字层。如果文件是扫描件"
                 "（整页都是图片），提取结果会是空的——那种文件需要 OCR，"
                 "当前版本尚未支持。")
        )
        layout.addStretch(1)
        return page

    def _build_output_group(self) -> QWidget:
        box = QGroupBox("输出设置")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        self.output = QStackedWidget()
        self.image_output = PathRow("输出目录", mode="directory", placeholder="图片的存放位置")
        self.text_output = PathRow("保存为", mode="save_file", placeholder="文本文件的保存位置")
        self.output.addWidget(self.image_output)
        self.output.addWidget(self.text_output)
        layout.addWidget(self.output)

        row = QHBoxLayout()
        row.addWidget(QLabel("密码"))
        self.password = make_password_edit()
        self.password.setFixedWidth(240)
        row.addWidget(self.password)
        row.addStretch(1)
        layout.addLayout(row)
        return box

    # ------------------------------------------------------------------ 交互

    def current_choice(self) -> int:
        return max(0, self.choice_group.checkedId())

    def _on_choice_changed(self, index: int) -> None:
        # 直接调用时按钮组状态未必已更新，这里补一次，
        # 否则 current_choice() 会取到旧的选中项，输出路径也就填错。
        button = self.choice_group.button(index)
        if button is not None:
            button.setChecked(True)
        self.output.setCurrentIndex(index)
        self.start_button.setText("开始提取图片" if index == 0 else "开始提取文字")
        self._refresh_output()

    def _on_source_changed(self, path: str) -> None:
        if not path:
            self.file_info.setText("尚未选择文件")
            return
        try:
            info = read_info(path, self.password.text() or None)
        except PdfError as exc:
            self.file_info.setText(f"⚠ {exc}")
            return
        self.file_info.setText(f"共 {info.page_count} 页 · {info.file_size_text}")
        self._refresh_output()

    def _refresh_output(self) -> None:
        path = self.source.path
        if not path:
            return
        if self.current_choice() == 0:
            self.image_output.set_path(default_output_dir(path, "_图片"))
        else:
            self.text_output.set_path(default_output_path(path, "_文字", ".txt"))

    def _on_start(self) -> None:
        path = self.source.path
        if not path:
            self.show_warning("请先选择文件", "还没有选择要提取内容的 PDF。")
            return

        password = self.password.text() or None
        if self.current_choice() == 0:
            output_dir = self.image_output.path or str(default_output_dir(path, "_图片"))
            self.image_output.set_path(output_dir)
            min_width = self.min_width.value()
            min_height = self.min_height.value()
            dedupe = self.dedupe.isChecked()

            def job(context):
                return extract_images(
                    path,
                    output_dir,
                    min_width=min_width,
                    min_height=min_height,
                    dedupe=dedupe,
                    password=password,
                    ctx=context,
                )

            self.start_task(job, "正在提取图片…")
            return

        total_pages = None
        try:
            info = read_info(path, password)
            total_pages = info.page_count
        except PdfError as exc:
            self.show_error("无法继续", str(exc))
            return

        try:
            pages = parse_pages(self.pages_edit.text(), total_pages) if self.pages_edit.text().strip() else None
        except PdfError as exc:
            self.show_error("页码有误", str(exc))
            return

        output = self.text_output.path or str(default_output_path(path, "_文字", ".txt"))
        self.text_output.set_path(output)
        markers = self.page_markers.isChecked()

        def job_text(context):
            return extract_text(
                path,
                output,
                pages=pages,
                password=password,
                page_markers=markers,
                ctx=context,
            )

        self.start_task(job_text, "正在提取文字…")

    def on_task_finished(self, result) -> None:
        if isinstance(result, ExtractImagesResult):
            if not result.files:
                self.show_warning(
                    "没有提取到图片",
                    f"扫描了 {result.found} 个图像对象，但没有符合条件的结果。"
                    "可以尝试把最小尺寸设为 0 后重试。",
                )
                return
            detail = f"共导出 {result.count} 张图片"
            if result.skipped_small:
                detail += f"，因尺寸过小跳过 {result.skipped_small} 张"
            if result.skipped_broken:
                detail += f"，损坏跳过 {result.skipped_broken} 张"
            detail += f"\n\n位置：{result.files[0].parent}"
            self.show_info("提取完成", detail)
            reveal_in_file_manager(result.files[0])
            return

        output = Path(result)
        size = human_size(output.stat().st_size) if output.exists() else "未知"
        self.show_info("提取完成", f"已生成：{output.name}\n大小：{size}\n位置：{output.parent}")
        reveal_in_file_manager(output)
