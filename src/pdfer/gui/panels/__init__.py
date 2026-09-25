"""PDFer 的功能面板。"""

from __future__ import annotations

from .base import Panel
from .convert_panel import ConvertPanel
from .extract_panel import ExtractPanel
from .info_panel import InfoPanel
from .merge_panel import MergePanel
from .pages_panel import PagesPanel
from .split_panel import SplitPanel
from .tools_panel import ToolsPanel

__all__ = [
    "ConvertPanel",
    "ExtractPanel",
    "InfoPanel",
    "MergePanel",
    "PagesPanel",
    "Panel",
    "SplitPanel",
    "ToolsPanel",
]
