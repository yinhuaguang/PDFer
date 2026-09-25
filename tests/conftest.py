"""测试用的样例 PDF 生成器。

刻意用 reportlab 现场生成，而不是往仓库里塞二进制样例文件：
* 每个测试都能拿到干净的输入，互不干扰
* diff 里永远不会出现「样例 PDF 变了」这种无法评审的改动
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen import canvas

PAGE_TEXT = "Page {number}"


def make_pdf(
    path: Path,
    pages: int = 5,
    *,
    size: tuple[float, float] = A4,
    rotate: int = 0,
    title: str | None = None,
    with_image: Path | None = None,
    with_outline: bool = False,
) -> Path:
    """生成一个内容可预期的样例 PDF。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = canvas.Canvas(str(path), pagesize=size)
    if title:
        doc.setTitle(title)
    if rotate:
        doc.setPageRotation(rotate)

    for number in range(1, pages + 1):
        doc.setFont("Helvetica", 24)
        doc.drawString(72, size[1] - 96, PAGE_TEXT.format(number=number))
        if with_outline:
            doc.bookmarkPage(f"chapter-{number}")
            doc.addOutlineEntry(f"Chapter {number}", f"chapter-{number}", level=0)
        if with_image is not None:
            doc.drawImage(str(with_image), 72, 72, width=120, height=120, mask=None)
        doc.showPage()

    doc.save()
    return path


@pytest.fixture
def png_image(tmp_path: Path) -> Path:
    """一张按位置着色的 PNG，方便断言提取结果对不对。"""
    target = tmp_path / "logo.png"
    image = Image.new("RGB", (60, 40), (200, 30, 60))
    image.save(target)
    return target


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """5 页、无书签、无图片的基础样例。"""
    return make_pdf(tmp_path / "sample.pdf", 5)


@pytest.fixture
def outlined_pdf(tmp_path: Path) -> Path:
    """5 页、每页一个顶层书签。"""
    return make_pdf(tmp_path / "outlined.pdf", 5, with_outline=True)


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    """用户密码为 ``secret`` 的加密 PDF。"""
    from pypdf import PdfReader, PdfWriter

    plain = make_pdf(tmp_path / "_plain.pdf", 3)
    reader = PdfReader(str(plain))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password="secret", owner_password="owner")
    target = tmp_path / "encrypted.pdf"
    with open(target, "wb") as handle:
        writer.write(handle)
    return target


@pytest.fixture
def half_rotated_pdf(tmp_path: Path) -> Path:
    """第一页自带 /Rotate 90 的 PDF，用于验证旋转叠加是否正确。"""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, NumberObject

    plain = make_pdf(tmp_path / "_plain_rot.pdf", 3)
    reader = PdfReader(str(plain))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.pages[0][NameObject("/Rotate")] = NumberObject(90)
    target = tmp_path / "rotated.pdf"
    with open(target, "wb") as handle:
        writer.write(handle)
    return target


@pytest.fixture
def image_pdf(tmp_path: Path, png_image: Path) -> Path:
    """每页都嵌入同一张图片的 PDF。"""
    return make_pdf(tmp_path / "with_image.pdf", 3, with_image=png_image)


@pytest.fixture
def letter_pdf(tmp_path: Path) -> Path:
    return make_pdf(tmp_path / "letter.pdf", 2, size=letter)
