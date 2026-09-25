"""进度回报与取消机制。

核心层刻意不依赖 Qt：这里定义纯 Python 的 :class:`TaskContext`，
由界面层（或命令行）注入回调，从而让核心逻辑可以脱离 GUI 单独测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .errors import TaskCancelledError


@dataclass(frozen=True)
class Progress:
    """一次进度快照。"""

    current: int
    total: int
    message: str = ""

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return max(0, min(100, round(self.current * 100 / self.total)))


ProgressCallback = Callable[[Progress], None]
CancelCheck = Callable[[], bool]


class TaskContext:
    """贯穿整个任务的上下文：回报进度、响应取消。

    核心层的每个耗时函数都接受一个 ``ctx`` 参数；不传则视为
    「无进度、不可取消」，便于脚本化调用与单元测试。

    Example:
        >>> ctx = TaskContext(on_progress=print)
        >>> ctx.report(1, 10, "正在处理")
        Progress(current=1, total=10, message='正在处理')
        >>> ctx.check_cancel()
    """

    __slots__ = ("_on_progress", "_is_cancelled", "_last_percent")

    def __init__(
        self,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCheck | None = None,
    ) -> None:
        self._on_progress = on_progress
        self._is_cancelled = is_cancelled
        self._last_percent = -1

    def report(self, current: int, total: int, message: str = "") -> None:
        """回报进度。百分比未变化时自动去抖，避免刷爆界面事件循环。"""
        if self._on_progress is None:
            return
        progress = Progress(current=current, total=total, message=message)
        if progress.percent == self._last_percent and current != total:
            return
        self._last_percent = progress.percent
        self._on_progress(progress)

    def report_stage(self, message: str, index: int, total: int) -> None:
        """回报"第 index 个阶段 / 共 total 个阶段"式的进度。"""
        self.report(index, total, message)

    def check_cancel(self) -> None:
        """若已被取消，抛出 :class:`TaskCancelledError`。"""
        if self._is_cancelled is not None and self._is_cancelled():
            raise TaskCancelledError("操作已取消")

    @property
    def cancelled(self) -> bool:
        return self._is_cancelled is not None and self._is_cancelled()


NULL_CONTEXT = TaskContext()
"""无进度、不可取消的上下文，供脚本与测试使用。"""
