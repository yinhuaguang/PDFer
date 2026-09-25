"""页面级编辑：旋转、删除、重排、提取。

统一用 :class:`PageRef` 描述「输出文件的第 k 页来自源文件的第 i 页、
并且额外旋转了 r 度」。这样四种操作就变成同一个数据结构的增删改，
界面只需维护一个 ``list[PageRef]``，保存时一次性落盘。

页面索引一律 **0 起点**。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from pypdf import PdfWriter
from pypdf.generic import NameObject, NumberObject

from .errors import PdfOperationError
from .merge import _write
from .pdfio import open_reader
from .progress import NULL_CONTEXT, TaskContext


@dataclass
class PageRef:
    """对源文档某一页的引用。"""

    index: int
    """源文档中的页序号（0 起点）。"""

    rotation: int
    """在源页面基础上额外旋转的角度，取值 0 / 90 / 180 / 270（顺时针）。"""

    def rotated_by(self, delta: int) -> "PageRef":
        """返回旋转 ``delta`` 度后的新引用（顺时针为正）。"""
        return PageRef(index=self.index, rotation=(self.rotation + delta) % 360)


def full_document(total_pages: int) -> list[PageRef]:
    """生成"原文顺序、不旋转"的完整页面列表。"""
    return [PageRef(index=index, rotation=0) for index in range(total_pages)]


def move(pages: list[PageRef], index: int, offset: int) -> list[PageRef]:
    """把第 ``index`` 项向前/向后移动 ``offset`` 位，返回新列表。

    越界时原样返回，方便界面直接调用而无需自行判断边界。
    """
    target = index + offset
    if not 0 <= index < len(pages) or not 0 <= target < len(pages):
        return pages
    result = list(pages)
    result.insert(target, result.pop(index))
    return result


def save_pages(
    source: str | Path,
    output: str | Path,
    pages: Sequence[PageRef],
    *,
    password: str | None = None,
    keep_metadata: bool = True,
    ctx: TaskContext | None = None,
) -> Path:
    """按 ``pages`` 指定的顺序与旋转角写出新 PDF。

    源文件**永不被修改**，结果一律写入 ``output``。

    Raises:
        PdfOperationError: 页列表为空、索引越界或写入失败。
    """
    context = ctx or NULL_CONTEXT
    source_path = Path(source)

    if not pages:
        raise PdfOperationError("结果中没有任何页面，请至少保留一页。")

    reader = open_reader(source_path, password)
    total_pages = len(reader.pages)

    invalid = [ref.index for ref in pages if not 0 <= ref.index < total_pages]
    if invalid:
        raise PdfOperationError(
            f"页序号越界：源文档共 {total_pages} 页，但引用了第 {invalid[0] + 1} 页。"
        )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter()
    # 缓存每页的原始旋转角度。同一页可能被多次引用（复制页面），
    # 缓存后即可把 rotation 当作「相对原始页面的绝对增量」，
    # 避免重复叠加导致旋转角越来越大。
    base_rotations: dict[int, int] = {}
    total = len(pages)

    try:
        for position, ref in enumerate(pages, start=1):
            context.check_cancel()
            context.report(position - 1, total, f"正在写入第 {position}/{total} 页")

            if ref.index not in base_rotations:
                raw = reader.pages[ref.index].get("/Rotate", 0)
                try:
                    base_rotations[ref.index] = int(raw) % 360
                except (TypeError, ValueError):
                    base_rotations[ref.index] = 0

            page = reader.pages[ref.index]
            target_rotation = (base_rotations[ref.index] + ref.rotation) % 360
            if target_rotation:
                page[NameObject("/Rotate")] = NumberObject(target_rotation)
            elif "/Rotate" in page:
                del page["/Rotate"]

            writer.add_page(page)

        if keep_metadata and reader.metadata:
            try:
                writer.add_metadata(
                    {key: value for key, value in reader.metadata.items() if value}
                )
            except Exception:  # noqa: BLE001
                pass

        context.report(total, total, "正在写入文件…")
        _write(writer, output_path)
    finally:
        writer.close()

    return output_path


def page_sizes(source: str | Path, password: str | None = None) -> list[tuple[float, float]]:
    """返回每页的 (宽, 高)，单位 pt。界面用于显示与排序。"""
    reader = open_reader(source, password)
    sizes: list[tuple[float, float]] = []
    for page in reader.pages:
        try:
            sizes.append((float(page.mediabox.width), float(page.mediabox.height)))
        except Exception:  # noqa: BLE001
            sizes.append((0.0, 0.0))
    return sizes
