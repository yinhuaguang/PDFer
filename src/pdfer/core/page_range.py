"""页码范围表达式解析。

支持用户常见的书写习惯::

    1-3        第 1 到 3 页
    5          只第 5 页
    7-         第 7 页到最后一页（需提供总页数）
    -5         第 1 页到第 5 页（需提供总页数）
    1,3,5-8    混合写法
    1-3;5-8    分号 = 分组，用于「按范围拆分」生成多个文件

分隔符兼容中英文：``,`` ``，`` ``、`` ``;`` ``；`` 与空格均可用。
页码一律以 **1 为起点**（面向用户），返回值统一为 **0 起点的索引**，
避免上下层反复换算出错。
"""

from __future__ import annotations

import re

from .errors import PageRangeError

_SPLIT_RE = re.compile(r"[,，、;；\s]+")
_GROUP_RE = re.compile(r"[,，、;；]+")
_TOKEN_RE = re.compile(r"^(\d*)\s*[-~—－]\s*(\d*)$")


def _normalize(text: str) -> str:
    return (text or "").strip().replace("－", "-")


def _parse_token(token: str, total: int | None) -> list[int]:
    """把单个 token（如 ``3`` / ``1-5`` / ``7-``）展开成 0 起点索引列表。"""
    token = token.strip()
    if not token:
        return []

    if token.isdigit():
        start = end = int(token)
    else:
        match = _TOKEN_RE.match(token)
        if not match:
            raise PageRangeError(f"无法识别的页码写法：「{token}」")
        left, right = match.group(1), match.group(2)
        if left and right:
            start, end = int(left), int(right)
        elif left:
            if total is None:
                raise PageRangeError(f"「{token}」是开放式范围，需要先知道总页数")
            start, end = int(left), total
        elif right:
            start, end = 1, int(right)
        else:
            raise PageRangeError(f"无法识别的页码写法：「{token}」")

    if start < 1 or end < 1:
        raise PageRangeError(f"页码必须从 1 开始：「{token}」")
    if start > end:
        raise PageRangeError(f"起始页不能大于结束页：「{token}」")
    if total is not None and start > total:
        raise PageRangeError(f"页码超出范围：文档共 {total} 页，但指定了第 {start} 页")

    actual_end = end if total is None else min(end, total)
    return list(range(start - 1, actual_end))


def parse_pages(text: str, total: int | None = None, *, dedupe: bool = True) -> list[int]:
    """解析页码范围，返回 **0 起点** 的页索引列表。

    Args:
        text: 用户输入，如 ``"1-3,7,10-"``。
        total: 文档总页数。为 ``None`` 时不允许使用开放式范围（``7-``、``-5``）。
        dedupe: 是否去重（保持首次出现的顺序）。

    Raises:
        PageRangeError: 表达式非法。
    """
    normalized = _normalize(text)
    if not normalized:
        raise PageRangeError("页码不能为空")

    pages: list[int] = []
    for token in _SPLIT_RE.split(normalized):
        pages.extend(_parse_token(token, total))

    if not pages:
        raise PageRangeError("未解析出任何有效页码")
    if dedupe:
        seen: set[int] = set()
        pages = [p for p in pages if not (p in seen or seen.add(p))]
    return pages


def parse_groups(text: str, total: int | None = None) -> list[list[int]]:
    """解析分组页码范围，用于「按范围拆分」——每组输出一个文件。

    ``"1-3;5-8"`` → ``[[0,1,2], [4,5,6,7]]``

    若用户未使用分组分隔符，则每个逗号分隔的片段各自成为一组，
    即 ``"1-3,5-8"`` 与 ``"1-3;5-8"`` 等价。
    """
    normalized = _normalize(text)
    if not normalized:
        raise PageRangeError("页码范围不能为空")

    groups: list[list[int]] = []
    for chunk in _GROUP_RE.split(normalized):
        chunk = chunk.strip()
        if not chunk:
            continue
        groups.append(parse_pages(chunk, total))

    if not groups:
        raise PageRangeError("未解析出任何有效页码范围")
    return groups


def compress_pages(pages: list[int]) -> str:
    """把 0 起点索引列表压缩回 ``"1-3,7"`` 形式，用于生成文件名。"""
    if not pages:
        return ""
    ordered = sorted(pages)
    parts: list[str] = []
    start = prev = ordered[0]
    for current in ordered[1:]:
        if current == prev + 1:
            prev = current
            continue
        parts.append(f"{start + 1}-{prev + 1}" if start != prev else f"{start + 1}")
        start = prev = current
    parts.append(f"{start + 1}-{prev + 1}" if start != prev else f"{start + 1}")
    return ",".join(parts)
