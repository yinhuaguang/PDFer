"""拆分 PDF。

四种模式：

``every_n``   每 N 页切一个文件
``each``      每页单独一个文件（等价于 ``every_n`` 且 N=1，独立列出是为了界面清晰）
``ranges``    按用户给定的范围分组，每组一个文件，如 ``1-3;5-8``
``bookmarks`` 按顶层书签切分（扫描书籍、规范文档最常用）
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from pypdf import PdfWriter

from .errors import PdfOperationError
from .merge import _write
from .page_range import compress_pages
from .pdfio import ensure_dir, open_reader
from .progress import NULL_CONTEXT, TaskContext

MODES = ("every_n", "each", "ranges", "bookmarks")

MODE_LABELS = {
    "every_n": "每 N 页一个文件",
    "each": "每页一个文件",
    "ranges": "按页码范围分组",
    "bookmarks": "按书签层级",
}


def _bookmark_groups(reader, total_pages: int) -> list[tuple[str, list[int]]]:
    """把顶层书签转换成 ``(标题, 页索引列表)`` 分组。

    只取顶层书签作为切分点：位于第 k 个书签和第 k+1 个书签之间的所有页面
    归入第 k 组。第一个书签之前若有内容，归入「正文之前」一组。
    """
    try:
        outline = reader.outline
    except Exception as exc:  # noqa: BLE001
        raise PdfOperationError(f"无法读取该书签结构：{exc}") from exc

    top_level = [item for item in outline if not isinstance(item, list)]
    if not top_level:
        raise PdfOperationError("该文档没有顶层书签，无法按书签拆分。")

    entries: list[tuple[str, int]] = []
    for item in top_level:
        title = str(getattr(item, "title", "") or "未命名书签")
        try:
            page_index = reader.get_destination_page_number(item)
        except Exception:  # noqa: BLE001 - 目标无效的书签直接跳过
            continue
        entries.append((title, page_index))

    if not entries:
        raise PdfOperationError("该书签均无法定位到具体页面，无法按书签拆分。")

    entries.sort(key=lambda pair: pair[1])

    groups: list[tuple[str, list[int]]] = []
    if entries[0][1] > 0:
        groups.append(("正文之前", list(range(0, entries[0][1]))))

    for position, (title, start) in enumerate(entries):
        end = entries[position + 1][1] if position + 1 < len(entries) else total_pages
        if end <= start:
            continue
        groups.append((title, list(range(start, end))))

    if not groups:
        raise PdfOperationError("书签未能划分出有效的页范围。")
    return groups


def build_groups(
    reader,
    total_pages: int,
    *,
    mode: str,
    pages_per_file: int = 1,
    groups: Sequence[Sequence[int]] | None = None,
) -> list[tuple[str, list[int]]]:
    """根据模式计算切分方案，返回 ``(文件名后缀, 页索引列表)`` 列表。

    单独抽出来是为了让界面能**预览**切分结果，而不必真的写文件。
    """
    if mode == "every_n":
        if pages_per_file < 1:
            raise PdfOperationError("每个文件的页数至少为 1。")
        plan = []
        for start in range(0, total_pages, pages_per_file):
            indices = list(range(start, min(start + pages_per_file, total_pages)))
            if len(indices) > 1:
                label = f"p{indices[0] + 1}-{indices[-1] + 1}"
            else:
                label = f"p{indices[0] + 1}"
            plan.append((label, indices))
        return plan

    if mode == "each":
        return [(f"p{index + 1}", [index]) for index in range(total_pages)]

    if mode == "ranges":
        if not groups:
            raise PdfOperationError("请先填写页码范围。")
        plan = []
        for chunk in groups:
            indices = [index for index in chunk if 0 <= index < total_pages]
            if not indices:
                continue
            plan.append((f"p{compress_pages(indices)}", indices))
        if not plan:
            raise PdfOperationError("页码范围未落在文档的有效页内。")
        return plan

    if mode == "bookmarks":
        return _bookmark_groups(reader, total_pages)

    raise PdfOperationError(f"未知的拆分模式：{mode}")


def _safe_stem(title: str, max_length: int = 80) -> str:
    """把书签标题清洗成安全的文件名，并限制长度。"""
    cleaned = "".join("_" if char in '<>:"/\\|?*\x00-\x1f' else char for char in str(title))
    cleaned = " ".join(cleaned.split()).strip(" .")
    if not cleaned:
        cleaned = "未命名"
    return cleaned[:max_length]


def split(
    source: str | Path,
    output_dir: str | Path,
    *,
    mode: str = "every_n",
    pages_per_file: int = 1,
    groups: Sequence[Sequence[int]] | None = None,
    password: str | None = None,
    prefix: str | None = None,
    ctx: TaskContext | None = None,
) -> list[Path]:
    """拆分单个 PDF，返回生成的文件路径列表。

    Args:
        source: 源文件。
        output_dir: 输出目录，不存在会自动创建。
        mode: 见模块文档。
        pages_per_file: ``every_n`` 模式下的每份页数。
        groups: ``ranges`` 模式的页索引分组（0 起点，已由界面解析完成）。
        password: 源文件密码。
        prefix: 输出文件名前缀，默认取源文件名。
        ctx: 进度与取消上下文。
    """
    context = ctx or NULL_CONTEXT
    source_path = Path(source)
    out_dir = ensure_dir(output_dir)

    if mode not in MODES:
        raise PdfOperationError(f"未知的拆分模式：{mode}")

    reader = open_reader(source_path, password)
    total_pages = len(reader.pages)
    plan = build_groups(
        reader,
        total_pages,
        mode=mode,
        pages_per_file=pages_per_file,
        groups=groups,
    )

    # 前缀可能是调用方传入的任意字符串（例如书签标题），必须清洗掉
    # 文件系统不接受的字符，否则会写出一个非法路径而不是给出清晰报错。
    name_prefix = _safe_stem(prefix) if prefix else source_path.stem
    written: list[Path] = []
    total = len(plan)

    for index, (suffix, indices) in enumerate(plan, start=1):
        context.check_cancel()
        context.report(index - 1, total, f"正在生成第 {index}/{total} 个文件")

        writer = PdfWriter()
        try:
            for page_index in indices:
                writer.add_page(reader.pages[page_index])
            if reader.metadata:
                try:
                    writer.add_metadata(
                        {key: value for key, value in reader.metadata.items() if value}
                    )
                except Exception:  # noqa: BLE001 - 元数据格式异常不影响主体功能
                    pass
            target = out_dir / f"{name_prefix}_{_safe_stem(suffix)}.pdf"
            _write(writer, target)
            written.append(target)
        finally:
            writer.close()

    context.report(total, total, "拆分完成")
    if not written:
        raise PdfOperationError("没有生成任何文件，请检查拆分设置。")
    return written
