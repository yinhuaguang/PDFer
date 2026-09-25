"""额外实用功能测试。"""

from __future__ import annotations

from pathlib import Path

import pikepdf
from PIL import Image
from pypdf import PdfReader

from pdfer.core import images_to_pdf, optimize_pdf, protect_pdf, unprotect_pdf


def test_images_to_pdf_keeps_order_and_page_count(tmp_path: Path) -> None:
    images: list[Path] = []
    for index, color in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255)), 1):
        path = tmp_path / f"{index}.png"
        Image.new("RGB", (120, 80), color).save(path)
        images.append(path)

    output = tmp_path / "images.pdf"
    result = images_to_pdf(images, output, dpi=150)

    assert result == output
    assert output.is_file()
    assert len(PdfReader(str(output)).pages) == 3


def test_optimize_pdf_creates_readable_copy(sample_pdf: Path, tmp_path: Path) -> None:
    output = tmp_path / "optimized.pdf"
    result = optimize_pdf(sample_pdf, output)

    assert result.output == output
    assert result.before_bytes > 0
    assert result.after_bytes > 0
    assert len(PdfReader(str(output)).pages) == 5


def test_protect_and_unprotect_pdf(sample_pdf: Path, tmp_path: Path) -> None:
    protected = tmp_path / "protected.pdf"
    plain = tmp_path / "plain-again.pdf"

    protect_pdf(sample_pdf, protected, user_password="secret")

    with pikepdf.Pdf.open(str(protected), password="secret") as pdf:
        assert pdf.is_encrypted
        assert len(pdf.pages) == 5

    unprotect_pdf(protected, plain, password="secret")

    with pikepdf.Pdf.open(str(plain)) as pdf:
        assert not pdf.is_encrypted
        assert len(pdf.pages) == 5
