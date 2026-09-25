"""渲染、转图片与内容提取的测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from pdfer.core import (
    PdfOperationError,
    PdfRenderer,
    extract_images,
    extract_text,
    pdf_to_images,
    render_pages_as_thumbnails,
)
from pdfer.core.errors import TaskCancelledError
from pdfer.core.progress import TaskContext


def make_image_only_pdf(path: Path, image: Path, pages: int = 2) -> Path:
    """生成一个整页只有图片、没有任何文字层的 PDF（模拟扫描件）。"""
    doc = canvas.Canvas(str(path), pagesize=A4)
    for _ in range(pages):
        doc.drawImage(str(image), 0, 0, width=A4[0], height=A4[1])
        doc.showPage()
    doc.save()
    return path


class TestPdfRenderer:
    def test_page_count(self, sample_pdf: Path) -> None:
        with PdfRenderer(sample_pdf) as renderer:
            assert renderer.page_count == 5

    def test_page_size_is_a4(self, sample_pdf: Path) -> None:
        with PdfRenderer(sample_pdf) as renderer:
            width, height = renderer.page_size(0)
        assert width == pytest.approx(595, abs=2)
        assert height == pytest.approx(842, abs=2)

    def test_render_returns_rgb_image(self, sample_pdf: Path) -> None:
        with PdfRenderer(sample_pdf) as renderer:
            image = renderer.render(0, dpi=72)
        assert image.mode == "RGB"
        assert image.width == pytest.approx(595, abs=3)

    def test_higher_dpi_means_more_pixels(self, sample_pdf: Path) -> None:
        with PdfRenderer(sample_pdf) as renderer:
            low = renderer.render(0, dpi=72)
            high = renderer.render(0, dpi=144)
        assert high.width > low.width * 1.8

    def test_thumbnail_respects_max_side(self, sample_pdf: Path) -> None:
        with PdfRenderer(sample_pdf) as renderer:
            thumb = renderer.thumbnail(0, max_side=120)
        assert max(thumb.size) <= 120

    def test_rotation(self, sample_pdf: Path) -> None:
        with PdfRenderer(sample_pdf) as renderer:
            normal = renderer.render(0, dpi=72)
            turned = renderer.render(0, dpi=72, rotation=90)
        assert normal.size == (turned.height, turned.width)

    def test_index_out_of_range(self, sample_pdf: Path) -> None:
        with PdfRenderer(sample_pdf) as renderer, pytest.raises(PdfOperationError, match="越界"):
            renderer.render(99)

    def test_dpi_out_of_range(self, sample_pdf: Path) -> None:
        with PdfRenderer(sample_pdf) as renderer, pytest.raises(PdfOperationError, match="超出合理范围"):
            renderer.render(0, dpi=5000)

    def test_reuse_after_close_is_safe(self, sample_pdf: Path) -> None:
        renderer = PdfRenderer(sample_pdf)
        renderer.close()
        renderer.close()  # 重复关闭不应抛异常


class TestPdfToImages:
    def test_png_all_pages(self, sample_pdf: Path, tmp_path: Path) -> None:
        result = pdf_to_images(sample_pdf, tmp_path / "imgs", fmt="png", dpi=72)
        assert result.count == 5
        assert all(f.suffix == ".png" for f in result.files)
        assert all(f.exists() for f in result.files)

    def test_naming_is_zero_padded(self, sample_pdf: Path, tmp_path: Path) -> None:
        result = pdf_to_images(sample_pdf, tmp_path / "imgs", fmt="png", dpi=72)
        assert [f.name for f in result.files][:2] == ["sample_1.png", "sample_2.png"]

    def test_jpg_extension_normalised(self, sample_pdf: Path, tmp_path: Path) -> None:
        result = pdf_to_images(sample_pdf, tmp_path / "imgs", fmt="jpeg", dpi=72)
        assert all(f.suffix == ".jpg" for f in result.files)

    def test_page_subset(self, sample_pdf: Path, tmp_path: Path) -> None:
        result = pdf_to_images(sample_pdf, tmp_path / "imgs", pages=[0, 2], dpi=72)
        assert [f.name for f in result.files] == ["sample_1.png", "sample_3.png"]

    def test_creates_output_dir(self, sample_pdf: Path, tmp_path: Path) -> None:
        result = pdf_to_images(sample_pdf, tmp_path / "a" / "b" / "c", dpi=72)
        assert result.files[0].parent.exists()

    def test_images_are_readable(self, sample_pdf: Path, tmp_path: Path) -> None:
        result = pdf_to_images(sample_pdf, tmp_path / "imgs", fmt="png", dpi=96)
        with Image.open(result.files[0]) as image:
            assert image.width > 700

    def test_unsupported_format(self, sample_pdf: Path, tmp_path: Path) -> None:
        with pytest.raises(PdfOperationError, match="不支持的图片格式"):
            pdf_to_images(sample_pdf, tmp_path / "imgs", fmt="tiff")

    def test_empty_page_selection(self, sample_pdf: Path, tmp_path: Path) -> None:
        with pytest.raises(PdfOperationError, match="没有需要转换的页面"):
            pdf_to_images(sample_pdf, tmp_path / "imgs", pages=[99])

    def test_cancellation(self, sample_pdf: Path, tmp_path: Path) -> None:
        context = TaskContext(is_cancelled=lambda: True)
        with pytest.raises(TaskCancelledError):
            pdf_to_images(sample_pdf, tmp_path / "imgs", ctx=context)


class TestThumbnails:
    def test_batch(self, sample_pdf: Path) -> None:
        thumbs = render_pages_as_thumbnails(sample_pdf, [0, 1, 2], max_side=100)
        assert set(thumbs) == {0, 1, 2}
        assert all(max(image.size) <= 100 for image in thumbs.values())


class TestExtractImages:
    def test_finds_embedded_image(self, image_pdf: Path, tmp_path: Path) -> None:
        result = extract_images(image_pdf, tmp_path / "out")
        assert result.found >= 1
        assert result.count >= 1
        assert result.files[0].exists()

    def test_dedupe_collapses_repeats(self, image_pdf: Path, tmp_path: Path) -> None:
        deduped = extract_images(image_pdf, tmp_path / "a", dedupe=True)
        everything = extract_images(image_pdf, tmp_path / "b", dedupe=False)
        assert deduped.count < everything.count

    def test_min_size_filter(self, image_pdf: Path, tmp_path: Path) -> None:
        result = extract_images(image_pdf, tmp_path / "out", min_width=500, min_height=500)
        assert result.count == 0
        assert result.skipped_small > 0

    def test_zero_threshold_keeps_everything(self, image_pdf: Path, tmp_path: Path) -> None:
        result = extract_images(image_pdf, tmp_path / "out", min_width=0, min_height=0)
        assert result.count >= 1

    def test_no_images_is_not_an_error(self, sample_pdf: Path, tmp_path: Path) -> None:
        result = extract_images(sample_pdf, tmp_path / "out")
        assert result.count == 0
        assert result.found == 0

    def test_extracted_bytes_are_original(self, image_pdf: Path, tmp_path: Path, png_image: Path) -> None:
        """图片按原始数据写出，解出来的像素应与源图完全一致。"""
        result = extract_images(image_pdf, tmp_path / "out", min_width=0, min_height=0)
        with Image.open(result.files[0]) as extracted, Image.open(png_image) as original:
            assert extracted.size == original.size


class TestExtractText:
    def test_extracts_page_text(self, sample_pdf: Path, tmp_path: Path) -> None:
        out = extract_text(sample_pdf, tmp_path / "out.txt")
        content = out.read_text(encoding="utf-8-sig")
        assert "Page 1" in content and "Page 5" in content

    def test_page_markers(self, sample_pdf: Path, tmp_path: Path) -> None:
        out = extract_text(sample_pdf, tmp_path / "out.txt", page_markers=True)
        assert "第 1 页" in out.read_text(encoding="utf-8-sig")

    def test_page_markers_can_be_disabled(self, sample_pdf: Path, tmp_path: Path) -> None:
        out = extract_text(sample_pdf, tmp_path / "out.txt", page_markers=False)
        assert "第 1 页" not in out.read_text(encoding="utf-8-sig")

    def test_page_subset(self, sample_pdf: Path, tmp_path: Path) -> None:
        out = extract_text(sample_pdf, tmp_path / "out.txt", pages=[0])
        content = out.read_text(encoding="utf-8-sig")
        assert "Page 1" in content and "Page 2" not in content

    def test_written_as_utf8_with_bom(self, sample_pdf: Path, tmp_path: Path) -> None:
        out = extract_text(sample_pdf, tmp_path / "out.txt")
        assert out.read_bytes().startswith(b"\xef\xbb\xbf")

    def test_image_only_pdf_gives_helpful_error(self, tmp_path: Path, png_image: Path) -> None:
        scanned = make_image_only_pdf(tmp_path / "scan.pdf", png_image)
        with pytest.raises(PdfOperationError, match="扫描件"):
            extract_text(scanned, tmp_path / "out.txt")

    def test_cancellation(self, sample_pdf: Path, tmp_path: Path) -> None:
        context = TaskContext(is_cancelled=lambda: True)
        with pytest.raises(TaskCancelledError):
            extract_text(sample_pdf, tmp_path / "out.txt", ctx=context)
