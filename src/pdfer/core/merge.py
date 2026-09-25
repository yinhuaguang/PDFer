"""合并多个 PDF。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from pypdf import PdfWriter

from .errors import PdfOperationError
from .pdfio import ensure_dir, open_reader
from .progress import NULL_CONTEXT, TaskContext


def merge(
    sources: Sequence[str | Path],
    output: str | Path,
    *,
    bookmark_per_file: bool = True,
    password: str | None = None,
    ctx: TaskContext | None = None,
) -> Path:
    """按给定顺序合并 PDF，写入 ``output``，返回输出路径。

    Args:
        sources: 源文件路径，顺序即最终页序。
        output: 输出文件路径；父目录不存在会自动创建。
        bookmark_per_file: 是否为每个源文件生成一个顶层书签，
            书签标题取文件名（不含扩展名）。合并几十个文件时非常有用。
        password: 若源文件已加密，用它尝试解密（所有文件共用同一密码）。
        ctx: 进度与取消上下文。

    Raises:
        PdfOperationError: 文件不足两个、密码错误或写入失败。
    """
    context = ctx or NULL_CONTEXT
    paths = [Path(p) for p in sources]

    if len(paths) < 2:
        raise PdfOperationError("合并至少需要 2 个 PDF 文件。")

    duplicates = {p for p in paths if paths.count(p) > 1}
    if duplicates:
        names = "、".join(sorted(p.name for p in duplicates))
        raise PdfOperationError(f"列表中存在重复文件，请先移除：{names}")

    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise PdfOperationError(f"文件不存在：{'、'.join(p.name for p in missing)}")

    output_path = Path(output)
    ensure_dir(output_path.parent)

    writer = PdfWriter()
    total = len(paths)
    try:
        for index, path in enumerate(paths, start=1):
            context.check_cancel()
            context.report(index - 1, total, f"正在合并：{path.name}")
            reader = open_reader(path, password)
            writer.append(
                reader,
                outline_item=path.stem if bookmark_per_file else None,
            )

        context.report(total, total, "正在写入文件…")
        _write(writer, output_path)
    finally:
        writer.close()

    return output_path


def _write(writer: PdfWriter, output: Path) -> None:
    """统一的写盘封装，把底层异常翻译成中文提示。"""
    try:
        with open(output, "wb") as handle:
            writer.write(handle)
    except PermissionError as exc:
        raise PdfOperationError(
            f"无法写入 {output.name}：文件被其他程序占用（可能正在 PDF 阅读器中打开）。"
        ) from exc
    except OSError as exc:
        raise PdfOperationError(f"写入 {output.name} 失败：{exc}") from exc


def validate_sources(sources: Iterable[str | Path]) -> list[str]:
    """合并前的预检查，返回警告信息列表（不抛异常）。"""
    warnings: list[str] = []
    paths = [Path(p) for p in sources]
    if len(paths) < 2:
        warnings.append("合并至少需要 2 个 PDF 文件。")
    for path in paths:
        if not path.is_file():
            warnings.append(f"文件不存在：{path.name}")
    names: dict[str, int] = {}
    for path in paths:
        names[path.name] = names.get(path.name, 0) + 1
    for name, count in names.items():
        if count > 1:
            warnings.append(f"「{name}」出现了 {count} 次，可能导致内容重复。")
    return warnings
