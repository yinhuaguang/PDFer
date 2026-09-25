"""PDF 转图片面板。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import ConvertResult, default_output_dir, parse_pages, pdf_to_images, read_info
from ...core.errors import PdfError
from ..widgets import Hint, PathRow, make_password_edit, reveal_in_file_manager
from .base import Panel

FORMATS = (("PNG（无损，体积较大）", "png"), ("JPEG（有损，体积小）", "jpg"), ("WebP（兼顾两者）", "webp"))

DPI_PRESETS = (
    (72, "72 dpi — 屏幕原始尺寸，适合快速预览"),
    (96, "96 dpi — 网页显示"),
    (150, "150 dpi — 日常查看、发给别人"),
    (200, "200 dpi — 需要看清小字"),
    (300, "300 dpi — 打印级，文件会很大"),
    (600, "600 dpi — 印刷级，请确认磁盘空间"),
)


class ConvertPanel(Panel):
    title = "转为图片"
    description = "把每一页导出成 PNG / JPEG / WebP 图片，用于预览、插图或归档。"

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

        layout.addWidget(self._build_format_group(), 1)
        layout.addWidget(self._build_output_group())

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.start_button = self.make_primary_button("开始转换", self._on_start)
        action_row.addWidget(self.start_button)
        layout.addLayout(action_row)

    def _build_format_group(self) -> QWidget:
        box = QGroupBox("输出设置")
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(QLabel("图片格式"))
        self.format_box = QComboBox()
        for label, value in FORMATS:
            self.format_box.addItem(label, value)
        self.format_box.setFixedWidth(240)
        self.format_box.currentIndexChanged.connect(self._refresh_estimate)
        row.addWidget(self.format_box)
        row.addStretch(1)
        layout.addLayout(row)

        row_dpi = QHBoxLayout()
        row_dpi.addWidget(QLabel("分辨率"))
        self.dpi = QSpinBox()
        self.dpi.setRange(10, 1200)
        self.dpi.setValue(150)
        self.dpi.setSuffix(" dpi")
        self.dpi.setFixedWidth(120)
        self.dpi.valueChanged.connect(self._refresh_estimate)
        row_dpi.addWidget(self.dpi)

        self.dpi_presets = QComboBox()
        for value, label in DPI_PRESETS:
            self.dpi_presets.addItem(label, value)
        self.dpi_presets.setFixedWidth(300)
        self.dpi_presets.currentIndexChanged.connect(self._on_preset)
        row_dpi.addWidget(self.dpi_presets)
        row_dpi.addStretch(1)
        layout.addLayout(row_dpi)

        row_quality = QHBoxLayout()
        row_quality.addWidget(QLabel("压缩质量"))
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(90)
        self.quality.setSuffix(" %")
        self.quality.setFixedWidth(120)
        self.quality.setToolTip("仅 JPEG / WebP 生效，数值越高越清晰、体积越大")
        row_quality.addWidget(self.quality)
        row_quality.addStretch(1)
        layout.addLayout(row_quality)

        row_pages = QHBoxLayout()
        row_pages.addWidget(QLabel("页码范围"))
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("留空表示全部页面，例如 1-3,7")
        row_pages.addWidget(self.pages_edit, 1)
        layout.addLayout(row_pages)

        self.estimate = Hint("")
        layout.addWidget(self.estimate)
        layout.addStretch(1)
        return box

    def _build_output_group(self) -> QWidget:
        box = QGroupBox("输出目录")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        self.output = PathRow("输出到", mode="directory", placeholder="图片的存放位置")
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

    def _on_preset(self, index: int) -> None:
        value = self.dpi_presets.itemData(index)
        if value:
            self.dpi.setValue(int(value))

    def _refresh_estimate(self) -> None:
        """按首页尺寸估算输出像素与磁盘占用，避免用户跑完才发现巨大。"""
        path = self.source.path
        if not path:
            self.estimate.clear()
            return
        try:
            info = read_info(path, self.password.text() or None)
        except PdfError:
            self.estimate.clear()
            return

        page_size = info.first_page
        if page_size is None:
            self.estimate.clear()
            return

        dpi = self.dpi.value()
        width_px = round(page_size.width / 72 * dpi)
        height_px = round(page_size.height / 72 * dpi)
        megapixels = width_px * height_px / 1_000_000
        # 经验值：150dpi 的 A4 页面约 3 万像素点/MB，PNG 更大
        per_page_mb = megapixels * (2.2 if self.format_box.currentData() == "png" else 0.55)
        total_mb = per_page_mb * info.page_count

        self.estimate.setText(
            f"按首页尺寸估算：每页 {width_px} × {height_px} 像素（{megapixels:.1f} 百万像素）；"
            f"{info.page_count} 页合计约 {total_mb:.0f} MB。实际大小随页面内容浮动。"
        )

    def _on_source_changed(self, path: str) -> None:
        if not path:
            self.file_info.setText("尚未选择文件")
            self.estimate.clear()
            return
        try:
            info = read_info(path, self.password.text() or None)
        except PdfError as exc:
            self.file_info.setText(f"⚠ {exc}")
            return
        self.file_info.setText(f"共 {info.page_count} 页 · {info.file_size_text}")
        self.output.set_path(default_output_dir(path, "_图片"))
        self._refresh_estimate()

    def _on_start(self) -> None:
        path = self.source.path
        if not path:
            self.show_warning("请先选择文件", "还没有选择要转换的 PDF。")
            return

        password = self.password.text() or None
        try:
            total_pages = read_info(path, password).page_count
            pages = (
                parse_pages(self.pages_edit.text(), total_pages)
                if self.pages_edit.text().strip()
                else None
            )
        except PdfError as exc:
            self.show_error("无法继续", str(exc))
            return

        output_dir = self.output.path or str(default_output_dir(path, "_图片"))
        self.output.set_path(output_dir)
        fmt = str(self.format_box.currentData())
        dpi = self.dpi.value()
        quality = self.quality.value()

        def job(context):
            return pdf_to_images(
                path,
                output_dir,
                fmt=fmt,
                dpi=dpi,
                pages=pages,
                jpeg_quality=quality,
                password=password,
                ctx=context,
            )

        self.start_task(job, f"正在转换（{dpi} dpi）…")

    def on_task_finished(self, result) -> None:
        converted: ConvertResult = result
        self.show_info(
            "转换完成",
            f"已导出 {converted.count} 张图片（{self.format_box.currentText().split('（')[0]}）\n\n"
            f"位置：{converted.files[0].parent if converted.files else self.output.path}",
        )
        if converted.files:
            reveal_in_file_manager(converted.files[0])
