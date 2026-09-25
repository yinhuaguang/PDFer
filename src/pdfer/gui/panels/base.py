"""功能面板的公共基类。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.errors import PageRangeError, PdfError
from ..widgets import Hint
from ..taskrunner import TaskRunner

TaskFunction = Callable[..., Any]


class Panel(QWidget):
    """所有功能面板的基类。

    统一提供：任务提交（带忙碌保护）、进度联动、错误提示、结果提示。
    子类只需要关心「收集参数 → 调核心层 → 展示结果」。
    """

    title = "未命名功能"
    description = ""

    def __init__(self, runner: TaskRunner, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.runner = runner
        self._build()

    # ------------------------------------------------------------------ 子类实现

    def _build(self) -> None:
        """构建界面。子类必须实现。"""

    def on_task_finished(self, result: Any) -> None:
        """任务成功后的回调。默认什么都不做。"""

    def on_task_failed(self, message: str) -> None:
        """任务失败后的回调。默认弹出一个错误框。"""
        self.show_error("操作失败", message)

    # ------------------------------------------------------------------ 公共能力

    def _wrap(self, function: TaskFunction, description: str) -> Callable[[Any], Any]:
        """把「核心层调用」包装成接收 TaskContext 的形式。"""

        def callable_(context: Any) -> Any:
            return function(context)

        return callable_

    def start_task(
        self,
        function: Callable[[Any], Any],
        description: str,
        *,
        blocked_hint: str = "已有任务正在执行，请等待完成或先取消。",
    ) -> bool:
        """提交后台任务。返回 ``False`` 表示已有任务在跑。"""
        if self.runner.busy:
            self.show_warning("请稍候", blocked_hint)
            return False
        return self.runner.run(function, description, owner=self)

    def show_info(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)

    def show_warning(self, title: str, text: str) -> None:
        QMessageBox.warning(self, title, text)

    def show_error(self, title: str, text: str) -> None:
        QMessageBox.critical(self, title, text)

    def guard(self, function: Callable[[], None]) -> None:
        """执行一段可能抛业务异常的界面逻辑，统一转成提示框。"""
        try:
            function()
        except (PdfError, PageRangeError) as exc:
            self.show_error("无法继续", str(exc))
        except Exception as exc:  # noqa: BLE001
            self.show_error("出错了", f"发生了未预期的错误：{exc}")

    # ------------------------------------------------------------------ 布局助手

    def make_header(self, title: str, description: str) -> QWidget:
        """生成面板顶部的标题区。"""
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        layout.addWidget(title_label)

        if description:
            layout.addWidget(Hint(description))
        return box

    def make_row(self, *widgets: QWidget, spacing: int = 8) -> QWidget:
        """把若干控件横排成一行。"""
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for widget in widgets:
            layout.addWidget(widget)
        return box

    def make_primary_button(self, text: str, slot: Callable[[], None]) -> QPushButton:
        """生成主操作按钮（强调色）。"""
        button = QPushButton(text)
        button.setObjectName("primary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    @staticmethod
    def result_summary(paths: list[Path], prefix: str = "已生成") -> str:
        """把输出文件列表整理成一句提示。"""
        if not paths:
            return "没有任何文件生成。"
        if len(paths) == 1:
            return f"{prefix}：{paths[0].name}\n\n位置：{paths[0].parent}"
        head = "\n".join(f"· {p.name}" for p in paths[:5])
        more = f"\n· …… 以及其他 {len(paths) - 5} 个文件" if len(paths) > 5 else ""
        return f"{prefix} {len(paths)} 个文件，位于：\n{paths[0].parent}\n\n{head}{more}"
