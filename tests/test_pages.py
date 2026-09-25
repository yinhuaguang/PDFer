"""页面编辑（旋转 / 删除 / 重排 / 复制）的测试。

重点覆盖 :func:`save_pages` 的旋转叠加逻辑——同一页被多次引用时，
旋转角必须以「相对原始页面」为基准，否则会越转越歪。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from pdfer.core import PageRef, PdfOperationError, full_document, move, page_sizes, save_pages
from pdfer.core.errors import TaskCancelledError
from pdfer.core.progress import TaskContext


def rotations_of(path: Path) -> list[int]:
    reader = PdfReader(str(path))
    return [int(page.get("/Rotate", 0) or 0) for page in reader.pages]


class TestPageRef:
    def test_rotate_wraps(self) -> None:
        assert PageRef(0, 270).rotated_by(90).rotation == 0
        assert PageRef(0, 0).rotated_by(-90).rotation == 270

    def test_rotate_keeps_index(self) -> None:
        assert PageRef(7, 90).rotated_by(90).index == 7


class TestFullDocument:
    def test_length_and_order(self) -> None:
        pages = full_document(3)
        assert [p.index for p in pages] == [0, 1, 2]
        assert all(p.rotation == 0 for p in pages)


class TestMove:
    def test_forward(self) -> None:
        pages = full_document(3)
        assert [p.index for p in move(pages, 0, 1)] == [1, 0, 2]

    def test_backward(self) -> None:
        pages = full_document(3)
        assert [p.index for p in move(pages, 2, -1)] == [0, 2, 1]

    def test_out_of_range_is_noop(self) -> None:
        pages = full_document(3)
        assert [p.index for p in move(pages, 0, -1)] == [0, 1, 2]
        assert [p.index for p in move(pages, 2, 1)] == [0, 1, 2]

    def test_does_not_mutate_input(self) -> None:
        pages = full_document(3)
        move(pages, 0, 2)
        assert [p.index for p in pages] == [0, 1, 2]


class TestSavePages:
    def test_identity_keeps_all_pages(self, sample_pdf: Path, tmp_path: Path) -> None:
        out = save_pages(sample_pdf, tmp_path / "out.pdf", full_document(5))
        assert len(PdfReader(str(out)).pages) == 5

    def test_reorder(self, sample_pdf: Path, tmp_path: Path) -> None:
        refs = [PageRef(4, 0), PageRef(0, 0), PageRef(2, 0)]
        out = save_pages(sample_pdf, tmp_path / "out.pdf", refs)
        reader = PdfReader(str(out))
        assert len(reader.pages) == 3
        assert "Page 5" in (reader.pages[0].extract_text() or "")
        assert "Page 1" in (reader.pages[1].extract_text() or "")

    def test_delete(self, sample_pdf: Path, tmp_path: Path) -> None:
        refs = [PageRef(i, 0) for i in (0, 2, 4)]
        out = save_pages(sample_pdf, tmp_path / "out.pdf", refs)
        assert len(PdfReader(str(out)).pages) == 3

    def test_duplicate_page(self, sample_pdf: Path, tmp_path: Path) -> None:
        refs = [PageRef(0, 0), PageRef(0, 0), PageRef(1, 0)]
        out = save_pages(sample_pdf, tmp_path / "out.pdf", refs)
        assert len(PdfReader(str(out)).pages) == 3

    def test_rotate(self, sample_pdf: Path, tmp_path: Path) -> None:
        refs = [PageRef(0, 90), PageRef(1, 180), PageRef(2, 270), PageRef(3, 0)]
        out = save_pages(sample_pdf, tmp_path / "out.pdf", refs)
        assert rotations_of(out) == [90, 180, 270, 0]

    def test_rotation_does_not_accumulate(self, half_rotated_pdf: Path, tmp_path: Path) -> None:
        """同一页引用三次、分别转 0/90/180，结果必须是 90/180/270 而不是越加越大。"""
        refs = [PageRef(0, 0), PageRef(0, 90), PageRef(0, 180)]
        out = save_pages(half_rotated_pdf, tmp_path / "out.pdf", refs)
        # 源页自身带 /Rotate 90，因此基准是 90
        assert rotations_of(out) == [90, 180, 270]

    def test_rotate_beyond_full_circle(self, sample_pdf: Path, tmp_path: Path) -> None:
        refs = [PageRef(0, 270), PageRef(1, 360)]
        out = save_pages(sample_pdf, tmp_path / "out.pdf", refs)
        assert rotations_of(out) == [270, 0]

    def test_source_file_untouched(self, sample_pdf: Path, tmp_path: Path) -> None:
        before = sample_pdf.read_bytes()
        save_pages(sample_pdf, tmp_path / "out.pdf", [PageRef(0, 90)])
        assert sample_pdf.read_bytes() == before

    def test_output_is_separate_file(self, sample_pdf: Path, tmp_path: Path) -> None:
        out = save_pages(sample_pdf, tmp_path / "elsewhere" / "out.pdf", full_document(2))
        assert out.exists() and out != sample_pdf

    def test_empty_pages_rejected(self, sample_pdf: Path, tmp_path: Path) -> None:
        with pytest.raises(PdfOperationError, match="没有任何页面"):
            save_pages(sample_pdf, tmp_path / "out.pdf", [])

    def test_index_out_of_range(self, sample_pdf: Path, tmp_path: Path) -> None:
        with pytest.raises(PdfOperationError, match="越界"):
            save_pages(sample_pdf, tmp_path / "out.pdf", [PageRef(99, 0)])

    def test_metadata_preserved(self, tmp_path: Path) -> None:
        from .conftest import make_pdf

        source = make_pdf(tmp_path / "titled.pdf", 2, title="季度报告")
        out = save_pages(source, tmp_path / "out.pdf", full_document(2))
        assert PdfReader(str(out)).metadata.title == "季度报告"

    def test_metadata_can_be_dropped(self, tmp_path: Path) -> None:
        from .conftest import make_pdf

        source = make_pdf(tmp_path / "titled.pdf", 2, title="季度报告")
        out = save_pages(source, tmp_path / "out.pdf", full_document(2), keep_metadata=False)
        assert PdfReader(str(out)).metadata is None or PdfReader(str(out)).metadata.title in ("", None)

    def test_encrypted(self, encrypted_pdf: Path, tmp_path: Path) -> None:
        out = save_pages(encrypted_pdf, tmp_path / "out.pdf", full_document(3), password="secret")
        assert len(PdfReader(str(out)).pages) == 3

    def test_cancellation(self, sample_pdf: Path, tmp_path: Path) -> None:
        context = TaskContext(is_cancelled=lambda: True)
        with pytest.raises(TaskCancelledError):
            save_pages(sample_pdf, tmp_path / "out.pdf", full_document(5), ctx=context)


class TestPageSizes:
    def test_returns_one_entry_per_page(self, sample_pdf: Path) -> None:
        sizes = page_sizes(sample_pdf)
        assert len(sizes) == 5
        assert all(width > 0 and height > 0 for width, height in sizes)
