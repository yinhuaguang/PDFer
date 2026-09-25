"""PDFer 核心层。

纯逻辑，不依赖任何 GUI 框架 —— 因此可以脱离界面单独测试，
也可以被命令行工具或脚本直接复用。

    >>> from pdfer.core import merge, split, read_info
"""

from __future__ import annotations

from .convert import ConvertResult, PdfRenderer, pdf_to_images, render_pages_as_thumbnails
from .errors import (
    PageRangeError,
    PdfEncryptedError,
    PdfError,
    PdfOperationError,
    PdfPasswordError,
    TaskCancelledError,
)
from .extract import ExtractImagesResult, extract_images, extract_text
from .extras import OptimizeResult, images_to_pdf, optimize_pdf, protect_pdf, unprotect_pdf
from .info import DocInfo, PageSize, read_info
from .merge import merge, validate_sources
from .page_range import compress_pages, parse_groups, parse_pages
from .pages import PageRef, full_document, move, page_sizes, save_pages
from .pdfio import (
    default_output_dir,
    default_output_path,
    ensure_dir,
    human_size,
    is_pdf,
    open_reader,
    unique_path,
)
from .progress import NULL_CONTEXT, Progress, TaskContext
from .split import MODE_LABELS, MODES, build_groups, split

__all__ = [
    "ConvertResult",
    "DocInfo",
    "ExtractImagesResult",
    "MODE_LABELS",
    "OptimizeResult",
    "MODES",
    "NULL_CONTEXT",
    "PageRangeError",
    "PageRef",
    "PageSize",
    "PdfEncryptedError",
    "PdfError",
    "PdfOperationError",
    "PdfPasswordError",
    "PdfRenderer",
    "Progress",
    "TaskCancelledError",
    "TaskContext",
    "build_groups",
    "compress_pages",
    "default_output_dir",
    "default_output_path",
    "ensure_dir",
    "extract_images",
    "extract_text",
    "full_document",
    "human_size",
    "images_to_pdf",
    "is_pdf",
    "merge",
    "move",
    "open_reader",
    "optimize_pdf",
    "page_sizes",
    "parse_groups",
    "parse_pages",
    "pdf_to_images",
    "protect_pdf",
    "read_info",
    "render_pages_as_thumbnails",
    "save_pages",
    "split",
    "unique_path",
    "unprotect_pdf",
    "validate_sources",
]
