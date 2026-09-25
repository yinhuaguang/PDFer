"""后台任务执行器：把核心层的耗时函数放到线程池里跑，界面不卡死。

这是界面层与核心层之间唯一的耦合点：
核心层只认 :class:`~pdfer.core.progress.TaskContext`（纯 Python 回调），
本模块负责把 Qt 的线程池与信号接到这两个回调上。
"""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core.errors import PdfError, TaskCancelledError
from ..core.progress import Progress, TaskContext

TaskFunction = Callable[[TaskContext], Any]


class _Signals(QObject):
    """任务的信号载体。

    单独抽一个 QObject 是因为 QRunnable 本身不是 QObject，无法定义信号。
    """

    started = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class _Task(QRunnable):
    def __init__(self, function: TaskFunction, description: str) -> None:
        super().__init__()
        self.function = function
        self.description = description
        self.signals = _Signals()
        self.cancel_event = threading.Event()
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102 - QRunnable 接口
        self.signals.started.emit(self.description)

        def on_progress(progress: Progress) -> None:
            self.signals.progress.emit(progress.current, progress.total, progress.message)

        context = TaskContext(
            on_progress=on_progress,
            is_cancelled=self.cancel_event.is_set,
        )

        try:
            result = self.function(context)
        except TaskCancelledError:
            self.signals.cancelled.emit()
        except PdfError as exc:
            # 业务异常的消息本身就是给用户看的，直接透传
            self.signals.failed.emit(str(exc))
        except MemoryError:
            self.signals.failed.emit("内存不足。请尝试分批处理，或减小输出分辨率。")
        except Exception as exc:  # noqa: BLE001 - 兜底：绝不让界面线程收到未捕获异常
            detail = traceback.format_exc(limit=3)
            self.signals.failed.emit(f"发生了未预期的错误：{exc}\n\n{detail}")
        else:
            self.signals.finished.emit(result)


class TaskRunner(QObject):
    """串行执行后台任务，并对外暴露统一的进度信号。

    同时只允许一个任务：PDF 操作往往涉及大量磁盘 IO 和内存，
    并发跑多个只会互相拖慢，还会让进度条失去意义。
    """

    started = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._current: _Task | None = None
        self._owner: object | None = None

    @property
    def busy(self) -> bool:
        return self._current is not None

    @property
    def owner(self) -> object | None:
        """发起当前任务的面板，供界面把结果派发回正确的面板。"""
        return self._owner

    def run(
        self,
        function: TaskFunction,
        description: str = "正在处理…",
        owner: object | None = None,
    ) -> bool:
        """提交任务。若已有任务在跑则返回 ``False``。"""
        if self.busy:
            return False

        task = _Task(function, description)
        task.signals.started.connect(self.started)
        task.signals.progress.connect(self.progress)
        task.signals.finished.connect(self._on_finished)
        task.signals.failed.connect(self._on_failed)
        task.signals.cancelled.connect(self._on_cancelled)

        self._current = task
        self._owner = owner
        self._pool.start(task)
        return True

    def cancel(self) -> None:
        """请求取消当前任务。核心层会在下一个检查点退出。"""
        if self._current is not None:
            self._current.cancel_event.set()

    def wait_for_done(self, timeout_ms: int = 10000) -> bool:
        """等待当前任务结束，用于程序退出时避免线程被强杀。"""
        return self._pool.waitForDone(timeout_ms)

    def _clear(self) -> None:
        self._current = None

    def _on_finished(self, result: object) -> None:
        self._clear()
        self.finished.emit(result)

    def _on_failed(self, message: str) -> None:
        self._clear()
        self.failed.emit(message)

    def _on_cancelled(self) -> None:
        self._clear()
        self.cancelled.emit()
