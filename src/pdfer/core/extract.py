"""内容提取：内嵌图片与纯文本。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Sequence

from PIL import Image, UnidentifiedImageError

from .errors import PdfOperationError
from .pdfio import ensure_dir, open_reader
from .progress import NULL_CONTEXT, TaskContext

# PIL 无法解码的图片格式（扫描件常用的 JBIG2 / JPEG2000）也应当被导出，
# 这里只列出扩展名，数据本身按原始字节写出。
_IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".jpe",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".webp",
    ".jp2",
    ".jpx",
    ".jbig2",
    ".jb2",
}


@dataclass
class ExtractImagesResult:
    """图片提取结果。"""

    files: list[Path] = field(default_factory=list)
    skipped_small: int = 0
    skipped_broken: int = 0
    found: int = 0

    @property
    def count(self) -> int:
        return len(self.files)


def _sniff_extension(data: bytes) -> str:
    """按文件头判断图片扩展名。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data.startswith(b"BM"):
        return ".bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return ".tif"
    if data.startswith(b"\x00\x00\x01\x00"):
        return ".ico"
    if data[:2] in (b"\xff\x4f", b"\xff\xd8"):
        return ".jp2"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"\x97JB2"):
        return ".jb2"
    return ".png"


def _resolve_extension(name: str, data: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in _IMAGE_EXTS:
        return ".jpg" if suffix == ".jpeg" else suffix
    return _sniff_extension(data)


def extract_images(
    source: str | Path,
    output_dir: str | Path,
    *,
    min_width: int = 0,
    min_height: int = 0,
    dedupe: bool = True,
    password: str | None = None,
    ctx: TaskContext | None = None,
) -> ExtractImagesResult:
    """导出 PDF 中内嵌的图片。

    原图数据会被**原样写出**（不重新编码），因此画质不会有任何损失。

    Args:
        min_width / min_height: 小于该尺寸的图片将被跳过，用于滤掉页码
            装饰线之类的碎片。设为 0 表示不限制。
        dedupe: 相同内容的图片只保存一次——合同里的公司 logo 会在每页
            重复出现，去重能显著减少文件数量。
    """
    context = ctx or NULL_CONTEXT
    source_path = Path(source)
    out_dir = ensure_dir(output_dir)

    reader = open_reader(source_path, password)
    result = ExtractImagesResult()
    seen: dict[str, Path] = {}
    sequence = 0
    total_pages = len(reader.pages)

    for page_index in range(total_pages):
        context.check_cancel()
        context.report(page_index, total_pages, f"正在扫描第 {page_index + 1}/{total_pages} 页")

        try:
            images = list(reader.pages[page_index].images)
        except Exception:  # noqa: BLE001 - 个别页的图片结构损坏不影响整体
            continue

        for image_file in images:
            try:
                data = image_file.data
            except Exception:  # noqa: BLE001
                result.skipped_broken += 1
                continue
            if not data:
                result.skipped_broken += 1
                continue

            result.found += 1
            digest = hashlib.sha1(data).hexdigest()

            if dedupe and digest in seen:
                continue

            original_name = str(getattr(image_file, "name", "") or "")
            if (min_width or min_height) and not _passes_size_filter(
                data, min_width, min_height
            ):
                result.skipped_small += 1
                continue

            sequence += 1
            extension = _resolve_extension(original_name, data)
            target = out_dir / f"p{page_index + 1:04d}_{sequence:03d}{extension}"
            try:
                target.write_bytes(data)
            except OSError as exc:
                raise PdfOperationError(f"写入 {target.name} 失败：{exc}") from exc

            if dedupe:
                seen[digest] = target
            result.files.append(target)

    context.report(total_pages, total_pages, "提取完成")
    return result


def _passes_size_filter(data: bytes, min_width: int, min_height: int) -> bool:
    """判断图片是否满足最小尺寸要求。无法解码的按"通过"处理。"""
    try:
        with Image.open(BytesIO(data)) as image:
            return image.width >= min_width and image.height >= min_height
    except (UnidentifiedImageError, OSError, ValueError):
        return True


def extract_text(
    source: str | Path,
    output: str | Path,
    *,
    pages: Sequence[int] | None = None,
    password: str | None = None,
    page_markers: bool = True,
    ctx: TaskContext | None = None,
) -> Path:
    """导出页面文字，写入 UTF-8 文本文件。

    说明：本功能只取 PDF 中**已有的文本层**。扫描件（纯图片 PDF）
    提取结果会是空的，需要 OCR 才能识别，这不在当前版本范围内。

    Args:
        pages: 要提取的页索引（0 起点），``None`` 表示全部。
        page_markers: 是否插入 ``===== 第 N 页 =====`` 分隔标记。
    """
    context = ctx or NULL_CONTEXT
    source_path = Path(source)
    reader = open_reader(source_path, password)
    total_pages = len(reader.pages)

    if pages is None:
        target_pages = list(range(total_pages))
    else:
        target_pages = [index for index in pages if 0 <= index < total_pages]
        if not target_pages:
            raise PdfOperationError("没有需要提取的页面。")

    texts: list[str] = []
    total = len(target_pages)

    for position, page_index in enumerate(target_pages, start=1):
        context.check_cancel()
        context.report(position, total, f"正在提取第 {page_index + 1} 页文字")
        try:
            texts.append(reader.pages[page_index].extract_text() or "")
        except Exception:  # noqa: BLE001
            texts.append("")

    # 先判断有没有真正提取到文字，再拼装分隔标记 —— 否则标记本身
    # 会让「一个字符都没提取到」被误判成成功，扫描件就得不到正确提示。
    if not any(text.strip() for text in texts):
        raise PdfOperationError(
            "未能提取到任何文字。该文件可能是扫描件（纯图片），需要 OCR 才能识别文字。"
        )

    chunks: list[str] = []
    for position, (page_index, text) in enumerate(zip(target_pages, texts)):
        if page_markers:
            chunks.append(f"===== 第 {page_index + 1} 页 =====\n{text.strip()}")
        else:
            chunks.append(text.strip())

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 带 BOM 的 UTF-8：Windows 记事本、Excel 打开中文不会乱码
    try:
        output_path.write_text("\n\n".join(chunks), encoding="utf-8-sig")
    except OSError as exc:
        raise PdfOperationError(f"写入 {output_path.name} 失败：{exc}") from exc

    return output_path
