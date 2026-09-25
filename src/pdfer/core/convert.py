"""页面渲染：把 PDF 页面画成位图。

底层用 pypdfium2（Chrome 的 PDFium 引擎），渲染质量与浏览器一致，
速度也远快于纯 Python 方案。所有渲染都通过 :class:`PdfRenderer`，
一次性打开文档后反复取页，避免逐页重复打开文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pypdfium2 as pdfium
from PIL import Image

from .errors import PdfOperationError
from .pdfio import ensure_dir, open_reader
from .progress import NULL_CONTEXT, TaskContext

# pdfium 内部以 72 dpi 为基准，scale = dpi / 72
_PDF_BASE_DPI = 72

IMAGE_FORMATS = {
    "png": ("PNG", ".png"),
    "jpg": ("JPEG", ".jpg"),
    "jpeg": ("JPEG", ".jpg"),
    "webp": ("WEBP", ".webp"),
}


def _to_rgb(image: Image.Image) -> Image.Image:
    """把任意模式转成 RGB，透明区域以白色填充。"""
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return image.convert("RGB")


class PdfRenderer:
    """可复用的渲染器，建议用 ``with`` 语句管理生命周期。

    Example:
        >>> with PdfRenderer("book.pdf") as renderer:
        ...     image = renderer.render(0, dpi=150)
    """

    def __init__(self, source: str | Path, password: str | None = None) -> None:
        self.source = Path(source)
        # 先用 pypdf 校验一次：pdfium 对加密文档的报错信息极不友好，
        # 而 pypdf 能明确区分「未提供密码」和「密码错误」。
        open_reader(self.source, password)
        try:
            self._doc = pdfium.PdfDocument(str(self.source), password=password or None)
        except Exception as exc:  # noqa: BLE001
            raise PdfOperationError(f"无法打开《{self.source.name}》用于渲染：{exc}") from exc
        self._closed = False

    def __enter__(self) -> "PdfRenderer":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            try:
                self._doc.close()
            except Exception:  # noqa: BLE001 - 关闭失败无需打扰用户
                pass
            self._closed = True

    @property
    def page_count(self) -> int:
        return len(self._doc)

    def page_size(self, page_index: int) -> tuple[float, float]:
        """返回页面尺寸（pt）。"""
        self._check_index(page_index)
        try:
            width, height = self._doc[page_index].get_size()
            return float(width), float(height)
        except Exception as exc:  # noqa: BLE001
            raise PdfOperationError(f"无法读取第 {page_index + 1} 页尺寸：{exc}") from exc

    def render(self, page_index: int, *, dpi: int = 150, rotation: int = 0) -> Image.Image:
        """把指定页渲染成 PIL 图像（RGB）。

        Args:
            page_index: 0 起点的页序号。
            dpi: 输出分辨率，网页预览用 96，打印通常 300。
            rotation: 额外旋转角度，必须是 90 的整数倍。
        """
        self._check_index(page_index)
        if dpi < 10 or dpi > 1200:
            raise PdfOperationError(f"分辨率 {dpi} dpi 超出合理范围（10–1200）。")
        try:
            page = self._doc[page_index]
            bitmap = page.render(scale=dpi / _PDF_BASE_DPI, rotation=rotation)
            return _to_rgb(bitmap.to_pil())
        except Exception as exc:  # noqa: BLE001
            raise PdfOperationError(f"渲染第 {page_index + 1} 页失败：{exc}") from exc

    def thumbnail(self, page_index: int, *, max_side: int = 160) -> Image.Image:
        """生成缩略图，长边不超过 ``max_side`` 像素。

        以较低 dpi 渲染后再缩放，比直接高清渲染再缩小快得多。
        """
        self._check_index(page_index)
        width, height = self.page_size(page_index)
        if width <= 0 or height <= 0:
            dpi = 72
        else:
            dpi = max(12, int(min(max_side / width, max_side / height) * _PDF_BASE_DPI))
        image = self.render(page_index, dpi=dpi)
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        return image

    def _check_index(self, page_index: int) -> None:
        if not 0 <= page_index < len(self._doc):
            raise PdfOperationError(
                f"页序号越界：文档共 {len(self._doc)} 页，请求的是第 {page_index + 1} 页。"
            )


@dataclass
class ConvertResult:
    """转换结果统计。"""

    files: list[Path]
    skipped: int = 0
    total_pages: int = 0

    @property
    def count(self) -> int:
        return len(self.files)


def pdf_to_images(
    source: str | Path,
    output_dir: str | Path,
    *,
    fmt: str = "png",
    dpi: int = 150,
    pages: Sequence[int] | None = None,
    jpeg_quality: int = 90,
    password: str | None = None,
    prefix: str | None = None,
    ctx: TaskContext | None = None,
) -> ConvertResult:
    """把 PDF 的若干页导出为图片，一页一个文件。

    Args:
        fmt: ``png`` / ``jpg`` / ``webp``。
        dpi: 输出分辨率。72 为屏幕原始大小，150 适合查看，300 适合打印。
        pages: 要导出的页索引（0 起点）。``None`` 表示全部页面。
        jpeg_quality: 仅 JPEG/WebP 生效，1–100。
        prefix: 输出文件名前缀，默认为源文件名。

    Returns:
        :class:`ConvertResult`，含生成的文件列表。
    """
    context = ctx or NULL_CONTEXT
    source_path = Path(source)
    out_dir = ensure_dir(output_dir)

    key = fmt.lower().lstrip(".")
    if key not in IMAGE_FORMATS:
        raise PdfOperationError(f"不支持的图片格式：{fmt}（可选：png / jpg / webp）")
    pil_format, extension = IMAGE_FORMATS[key]

    save_options: dict[str, object] = {}
    if pil_format == "JPEG":
        save_options = {"quality": max(1, min(100, jpeg_quality)), "optimize": True}
    elif pil_format == "WEBP":
        save_options = {"quality": max(1, min(100, jpeg_quality))}

    name_prefix = prefix or source_path.stem
    written: list[Path] = []
    skipped = 0

    with PdfRenderer(source_path, password) as renderer:
        target_pages = list(pages) if pages is not None else list(range(renderer.page_count))
        target_pages = [index for index in target_pages if 0 <= index < renderer.page_count]
        if not target_pages:
            raise PdfOperationError("没有需要转换的页面。")

        total = len(target_pages)
        # 按总页数的位数补零：5 页的文档得到 1..5，120 页的文档得到 001..120，
        # 这样在资源管理器里按名称排序永远与页序一致。
        width = max(1, len(str(renderer.page_count)))
        for position, page_index in enumerate(target_pages, start=1):
            context.check_cancel()
            context.report(position - 1, total, f"正在渲染第 {page_index + 1} 页")
            image = renderer.render(page_index, dpi=dpi)
            if pil_format == "JPEG":
                image = _to_rgb(image)
            target = out_dir / f"{name_prefix}_{page_index + 1:0{width}d}{extension}"
            try:
                image.save(target, format=pil_format, **save_options)
            except OSError as exc:
                raise PdfOperationError(f"写入 {target.name} 失败：{exc}") from exc
            finally:
                image.close()
            written.append(target)

    return ConvertResult(files=written, skipped=skipped, total_pages=total)


def render_pages_as_thumbnails(
    source: str | Path,
    page_indexes: Iterable[int],
    *,
    max_side: int = 160,
    password: str | None = None,
    ctx: TaskContext | None = None,
) -> dict[int, Image.Image]:
    """批量生成缩略图，返回 ``{页索引: 图像}``。"""
    context = ctx or NULL_CONTEXT
    indexes = list(page_indexes)
    result: dict[int, Image.Image] = {}
    with PdfRenderer(source, password) as renderer:
        total = len(indexes)
        for position, page_index in enumerate(indexes, start=1):
            context.check_cancel()
            context.report(position, total, f"正在生成缩略图 {position}/{total}")
            try:
                result[page_index] = renderer.thumbnail(page_index, max_side=max_side)
            except PdfOperationError:
                continue
    return result
