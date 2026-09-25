"""读取 PDF 的元信息，用于「文档信息」面板。

注意：本模块只读取，不修改任何文件。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .pdfio import human_size, open_reader

# 常见纸张尺寸（单位 pt，纵向）。容差 4pt 以吸收生成器的舍入误差。
_KNOWN_SIZES = {
    "A3": (842, 1191),
    "A4": (595, 842),
    "A5": (420, 595),
    "A6": (298, 420),
    "B5": (499, 709),
    "Letter": (612, 792),
    "Legal": (612, 1008),
    "Tabloid": (792, 1224),
}
_SIZE_TOLERANCE = 4.0


@dataclass(frozen=True)
class PageSize:
    """单页尺寸（pt，已按实际显示方向归一）。"""

    width: float
    height: float

    @property
    def label(self) -> str:
        """识别的纸张名，如 ``A4 横向``；无法识别则为空串。"""
        short, long = sorted((self.width, self.height))
        for name, (w, h) in _KNOWN_SIZES.items():
            if abs(short - w) <= _SIZE_TOLERANCE and abs(long - h) <= _SIZE_TOLERANCE:
                return f"{name} 横向" if self.width > self.height else name
        return ""

    @property
    def mm(self) -> tuple[float, float]:
        return round(self.width * 25.4 / 72, 1), round(self.height * 25.4 / 72, 1)

    def describe(self) -> str:
        width_mm, height_mm = self.mm
        label = self.label
        base = f"{width_mm:g} × {height_mm:g} mm"
        return f"{base}（{label}）" if label else base


@dataclass
class DocInfo:
    """一个 PDF 的全部只读信息。"""

    path: Path
    page_count: int
    file_size: int
    file_size_text: str
    encrypted: bool
    pdf_version: str = ""
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    creator: str = ""
    producer: str = ""
    creation_date: str = ""
    modification_date: str = ""
    first_page: PageSize | None = None
    size_summary: list[tuple[str, int]] = field(default_factory=list)
    has_outline: bool = False
    outline_count: int = 0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_uniform_size(self) -> bool:
        return len(self.size_summary) <= 1


def _describe_size(page) -> PageSize:
    box = page.mediabox
    return PageSize(width=float(box.width), height=float(box.height))


def _count_outline(reader) -> int:
    """统计大纲（书签）条目总数，失败时返回 0。"""
    try:
        outline = reader.outline

        def walk(items) -> int:
            total = 0
            for item in items:
                if isinstance(item, list):
                    total += walk(item)
                else:
                    total += 1
            return total

        return walk(outline)
    except Exception:  # noqa: BLE001 - 大纲结构千奇百怪，读不到就当没有
        return 0


def read_info(path: str | Path, password: str | None = None) -> DocInfo:
    """读取 PDF 的元信息。

    Raises:
        PdfOperationError / PdfEncryptedError: 同 :func:`open_reader`。
    """
    pdf_path = Path(path)
    reader = open_reader(pdf_path, password)

    sizes: Counter[str] = Counter()
    first_page: PageSize | None = None
    for page in reader.pages:
        try:
            size = _describe_size(page)
        except Exception:  # noqa: BLE001
            continue
        if first_page is None:
            first_page = size
        sizes[size.describe()] += 1

    raw_meta = {}
    try:
        raw_meta = dict(reader.metadata or {})
    except Exception:  # noqa: BLE001
        raw_meta = {}

    def meta(key: str) -> str:
        value = raw_meta.get(key, "")
        return str(value) if value else ""

    outline_count = _count_outline(reader)
    size = pdf_path.stat().st_size

    return DocInfo(
        path=pdf_path,
        page_count=len(reader.pages),
        file_size=size,
        file_size_text=human_size(size),
        encrypted=bool(reader.is_encrypted),
        pdf_version=str(getattr(reader, "pdf_header", "") or "").lstrip("%"),
        title=meta("/Title"),
        author=meta("/Author"),
        subject=meta("/Subject"),
        keywords=meta("/Keywords"),
        creator=meta("/Creator"),
        producer=meta("/Producer"),
        creation_date=meta("/CreationDate"),
        modification_date=meta("/ModDate"),
        first_page=first_page,
        size_summary=[(label, count) for label, count in sizes.most_common()],
        has_outline=outline_count > 0,
        outline_count=outline_count,
    )
