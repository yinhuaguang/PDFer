"""读写工具与文档信息的测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdfer.core import (
    PdfEncryptedError,
    PdfOperationError,
    default_output_dir,
    human_size,
    is_pdf,
    open_reader,
    read_info,
    unique_path,
)


class TestHumanSize:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0, "0 B"), (512, "512 B"), (1024, "1.0 KB"), (1536, "1.5 KB"), (1048576, "1.0 MB")],
    )
    def test_format(self, value: int, expected: str) -> None:
        assert human_size(value) == expected


class TestIsPdf:
    def test_case_insensitive(self) -> None:
        assert is_pdf("a.PDF")
        assert is_pdf(Path("b.pdf"))
        assert not is_pdf("c.txt")


class TestOpenReader:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(PdfOperationError, match="不存在"):
            open_reader(tmp_path / "nope.pdf")

    def test_broken_file(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.pdf"
        broken.write_bytes(b"this is definitely not a pdf")
        with pytest.raises(PdfOperationError):
            open_reader(broken)

    def test_encrypted_without_password(self, encrypted_pdf: Path) -> None:
        with pytest.raises(PdfEncryptedError, match="需要打开密码"):
            open_reader(encrypted_pdf)

    def test_encrypted_with_wrong_password(self, encrypted_pdf: Path) -> None:
        with pytest.raises(PdfEncryptedError, match="密码错误"):
            open_reader(encrypted_pdf, "wrong")

    def test_encrypted_with_password(self, encrypted_pdf: Path) -> None:
        reader = open_reader(encrypted_pdf, "secret")
        assert len(reader.pages) == 3


class TestPaths:
    def test_default_output_dir(self) -> None:
        assert default_output_dir("C:/docs/a.pdf", "_拆分").name == "a_拆分"

    def test_unique_path_no_conflict(self, tmp_path: Path) -> None:
        target = tmp_path / "out.pdf"
        assert unique_path(target) == target

    def test_unique_path_increments(self, tmp_path: Path) -> None:
        target = tmp_path / "out.pdf"
        target.write_bytes(b"x")
        assert unique_path(target).name == "out (1).pdf"
        (tmp_path / "out (1).pdf").write_bytes(b"x")
        assert unique_path(target).name == "out (2).pdf"


class TestReadInfo:
    def test_basic_fields(self, sample_pdf: Path) -> None:
        info = read_info(sample_pdf)
        assert info.page_count == 5
        assert info.name == "sample.pdf"
        assert info.file_size > 0
        assert info.encrypted is False
        assert info.first_page is not None
        assert info.is_uniform_size

    def test_detects_a4(self, sample_pdf: Path) -> None:
        assert read_info(sample_pdf).first_page.label == "A4"  # type: ignore[union-attr]

    def test_detects_letter(self, letter_pdf: Path) -> None:
        assert read_info(letter_pdf).first_page.label == "Letter"  # type: ignore[union-attr]

    def test_counts_outline(self, outlined_pdf: Path) -> None:
        info = read_info(outlined_pdf)
        assert info.has_outline
        assert info.outline_count == 5

    def test_metadata_title(self, tmp_path: Path) -> None:
        from .conftest import make_pdf

        path = make_pdf(tmp_path / "titled.pdf", 1, title="季度报告")
        assert read_info(path).title == "季度报告"

    def test_encrypted_flag(self, encrypted_pdf: Path) -> None:
        info = read_info(encrypted_pdf, "secret")
        assert info.encrypted is True
