"""页面管理面板：缩略图里旋转、删除、重排，再另存为新文件。

设计要点：
* **列表即数据源**。顺序与旋转角都记在 ``QListWidgetItem`` 上，
  用户在缩略图间拖动排序后无需任何同步逻辑，读取时按视图顺序取即可。
* **缩略图增量生成**。用 ``QTimer`` 每 tick 渲染一页，界面不会假死，
  用户能立刻看到进度而不是盯着空白等半天。
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core import (
    PageRef,
    PdfRenderer,
    default_output_path,
    human_size,
    read_info,
    save_pages,
    unique_path,
)
from ...core.errors import PdfError
from ..widgets import Hint, PathRow, make_password_edit, pil_to_qpixmap, reveal_in_file_manager
from .base import Panel

ROLE_REF = Qt.ItemDataRole.UserRole
ROLE_ORIGINAL = Qt.ItemDataRole.UserRole + 1  # 未旋转的原始缩略图
ROLE_PAGE = Qt.ItemDataRole.UserRole + 2  # 源文档中的页序号

THUMB_MAX = 132
PLACEHOLDER = (238, 240, 244)


class PagesPanel(Panel):
    title = "页面管理"
    description = (
        "在缩略图里直接旋转、删除、拖动排序，或挑出需要的页面另存为新文件。"
        "源文件永远不会被修改。"
    )

    def _build(self) -> None:
        self._renderer: PdfRenderer | None = None
        self._thumb_cache: dict[int, QPixmap] = {}
        self._items_by_page: dict[int, list[QListWidgetItem]] = {}
        self._pending: deque[int] = deque()

        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._render_tick)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(self.make_header(self.title, self.description))

        self.source = PathRow("源文件")
        self.source.changed.connect(self._on_source_changed)
        layout.addWidget(self.source)

        self.file_info = Hint("尚未选择文件")
        layout.addWidget(self.file_info)

        self.grid = self._build_grid()
        layout.addWidget(self.grid, 1)

        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_save_group())

        action_row = QHBoxLayout()
        self.render_status = Hint("")
        action_row.addWidget(self.render_status, 1)
        self.save_button = self.make_primary_button("另存为新文件", self._on_save)
        action_row.addWidget(self.save_button)
        layout.addLayout(action_row)

    def _build_grid(self) -> QListWidget:
        grid = QListWidget()
        grid.setObjectName("pageGrid")
        grid.setViewMode(QListView.ViewMode.IconMode)
        grid.setIconSize(QSize(THUMB_MAX, THUMB_MAX))
        grid.setGridSize(QSize(THUMB_MAX + 30, THUMB_MAX + 56))
        grid.setResizeMode(QListView.ResizeMode.Adjust)
        grid.setMovement(QListView.Movement.Static)
        grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        grid.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        grid.setDefaultDropAction(Qt.DropAction.MoveAction)
        grid.setWordWrap(True)
        grid.setMinimumHeight(280)
        grid.setToolTip("拖动缩略图可以调整顺序；被拖起的页面会插入到放置位置")
        return grid

    def _build_toolbar(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for text, slot, tip in (
            ("↺ 左转", lambda: self._rotate(-90), "把选中的页面逆时针旋转 90°"),
            ("↻ 右转", lambda: self._rotate(90), "把选中的页面顺时针旋转 90°"),
            ("复制", self._duplicate, "复制选中的页面，副本插入在其后"),
            ("删除", self._delete, "从结果中移除选中的页面（源文件不受影响）"),
            ("上移", lambda: self._move(-1), "把选中的页面向前移动一位"),
            ("下移", lambda: self._move(1), "把选中的页面向后移动一位"),
        ):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            layout.addWidget(button)

        layout.addStretch(1)

        self.select_all_button = QPushButton("全选")
        self.select_all_button.clicked.connect(self.grid.selectAll)
        layout.addWidget(self.select_all_button)

        self.reset_button = QPushButton("恢复原状")
        self.reset_button.setToolTip("放弃所有改动，回到文档的原始顺序")
        self.reset_button.clicked.connect(self._reset_edits)
        layout.addWidget(self.reset_button)
        return row

    def _build_save_group(self) -> QWidget:
        box = QGroupBox("保存")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        self.output = PathRow("另存为", mode="save_file", placeholder="输出文件位置")
        layout.addWidget(self.output)

        row = QHBoxLayout()
        row.addWidget(QLabel("密码"))
        self.password = make_password_edit()
        self.password.setFixedWidth(240)
        self.password.setToolTip("源文件若已加密，请填写打开密码")
        row.addWidget(self.password)
        row.addStretch(1)

        self.export_button = QPushButton("仅导出所选页")
        self.export_button.setToolTip("只把选中的页面导出成一个新的 PDF")
        self.export_button.clicked.connect(lambda: self._on_save(only_selected=True))
        row.addWidget(self.export_button)
        layout.addLayout(row)
        return box

    # ------------------------------------------------------------------ 载入与缩略图

    def _reset_state(self) -> None:
        self._timer.stop()
        self._pending.clear()
        self._thumb_cache.clear()
        self._items_by_page.clear()
        self.grid.clear()
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
        self.render_status.clear()

    def _on_source_changed(self, path: str) -> None:
        self._reset_state()
        if not path:
            self.file_info.setText("尚未选择文件")
            self.output.clear()
            return

        try:
            info = read_info(path, self.password.text() or None)
            self._renderer = PdfRenderer(path, self.password.text() or None)
        except PdfError as exc:
            self.file_info.setText(f"⚠ {exc}")
            return

        self.file_info.setText(
            f"共 {info.page_count} 页 · {info.file_size_text}"
            + (f" · 首页 {info.first_page.describe()}" if info.first_page else "")
        )
        self.output.set_path(default_output_path(path, "_编辑"))
        self._create_items(info.page_count)
        self._pending.extend(range(info.page_count))
        self.render_status.setText(f"正在生成缩略图 0/{info.page_count}")
        self._timer.start()

    def _placeholder(self) -> QPixmap:
        pixmap = QPixmap(THUMB_MAX, int(THUMB_MAX * 1.35))
        pixmap.fill(Qt.GlobalColor.transparent)
        from PySide6.QtGui import QColor, QPainter  # noqa: PLC0415

        painter = QPainter(pixmap)
        painter.fillRect(pixmap.rect(), QColor(*PLACEHOLDER))
        painter.end()
        return pixmap

    def _create_items(self, total_pages: int) -> None:
        self.grid.clear()
        self._items_by_page.clear()
        placeholder = self._placeholder()
        for index in range(total_pages):
            item = QListWidgetItem()
            item.setData(ROLE_REF, PageRef(index=index, rotation=0))
            item.setData(ROLE_ORIGINAL, placeholder)
            item.setData(ROLE_PAGE, index)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setIcon(QIcon(placeholder))
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )
            self.grid.addItem(item)
            self._items_by_page.setdefault(index, []).append(item)

    def _render_tick(self) -> None:
        if self._renderer is None or not self._pending:
            self._timer.stop()
            total = self.grid.count()
            self.render_status.setText(
                f"缩略图已全部生成 · 共 {total} 页" if total else "缩略图已全部生成"
            )
            return

        page_index = self._pending.popleft()
        try:
            pixmap = self._thumb_cache.get(page_index)
            if pixmap is None:
                image = self._renderer.thumbnail(page_index, max_side=THUMB_MAX)
                pixmap = pil_to_qpixmap(image)
                self._thumb_cache[page_index] = pixmap
            for item in self._items_by_page.get(page_index, []):
                item.setData(ROLE_ORIGINAL, pixmap)
                self._apply_icon(item)
        except PdfError:
            pass  # 单页渲染失败不影响其他页

        total = self.grid.count()
        done = total - len(self._pending)
        self.render_status.setText(f"正在生成缩略图 {done}/{total}")

    def _apply_icon(self, item: QListWidgetItem) -> None:
        base: QPixmap | None = item.data(ROLE_ORIGINAL)
        ref: PageRef | None = item.data(ROLE_REF)
        if base is None or ref is None or base.isNull():
            return

        if ref.rotation:
            pixmap = base.transformed(
                QTransform().rotate(ref.rotation), Qt.TransformationMode.SmoothTransformation
            )
        else:
            pixmap = base

        item.setIcon(QIcon(pixmap))
        suffix = f"　↻{ref.rotation}°" if ref.rotation else ""
        item.setText(f"第 {ref.index + 1} 页{suffix}")
        item.setToolTip(f"源文档第 {ref.index + 1} 页" + (f"，已旋转 {ref.rotation}°" if ref.rotation else ""))

    def _apply_icon_all(self) -> None:
        for row in range(self.grid.count()):
            self._apply_icon(self.grid.item(row))

    # ------------------------------------------------------------------ 编辑操作

    def selected_items(self) -> list[QListWidgetItem]:
        return self.grid.selectedItems()

    def _require_selection(self) -> list[QListWidgetItem] | None:
        items = self.selected_items()
        if not items:
            self.show_warning("没有选中任何页面", "请先在缩略图中点选要操作的页面（按住 Ctrl 可多选）。")
            return None
        return items

    def _rotate(self, delta: int) -> None:
        items = self._require_selection()
        if items is None:
            return
        for item in items:
            ref: PageRef = item.data(ROLE_REF)
            item.setData(ROLE_REF, PageRef(index=ref.index, rotation=(ref.rotation + delta) % 360))
            self._apply_icon(item)

    def _delete(self) -> None:
        items = self._require_selection()
        if items is None:
            return
        if self.grid.count() - len(items) < 1:
            self.show_warning("不能全部删除", "结果至少需要保留一页。")
            return
        for item in items:
            self.grid.takeItem(self.grid.row(item))

    def _duplicate(self) -> None:
        items = self._require_selection()
        if items is None:
            return
        insert_at = self.grid.row(items[-1]) + 1
        for item in items:
            ref: PageRef = item.data(ROLE_REF)
            clone = QListWidgetItem()
            clone.setData(ROLE_REF, PageRef(index=ref.index, rotation=ref.rotation))
            clone.setData(ROLE_ORIGINAL, item.data(ROLE_ORIGINAL))
            clone.setData(ROLE_PAGE, item.data(ROLE_PAGE))
            clone.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            clone.setFlags(item.flags())
            self.grid.insertItem(insert_at, clone)
            self._apply_icon(clone)
            insert_at += 1
        self.grid.clearSelection()
        self.grid.setCurrentRow(insert_at - 1)

    def _move(self, offset: int) -> None:
        row = self.grid.currentRow()
        target = row + offset
        if row < 0 or not 0 <= target < self.grid.count():
            return
        item = self.grid.takeItem(row)
        self.grid.insertItem(target, item)
        self.grid.setCurrentRow(target)

    def _reset_edits(self) -> None:
        path = self.source.path
        if not path:
            return
        self._reset_state()
        try:
            info = read_info(path, self.password.text() or None)
            self._renderer = PdfRenderer(path, self.password.text() or None)
        except PdfError as exc:
            self.file_info.setText(f"⚠ {exc}")
            return
        self._create_items(info.page_count)
        self._pending.extend(range(info.page_count))
        self.render_status.setText(f"正在生成缩略图 0/{info.page_count}")
        self._timer.start()

    # ------------------------------------------------------------------ 保存

    def _collect(self, only_selected: bool) -> list[PageRef]:
        if only_selected:
            items: list[QListWidgetItem] = self.selected_items()
            # selectedItems() 的顺序不保证与视图一致，按行号重排
            items = sorted(items, key=self.grid.row)
        else:
            items = [self.grid.item(row) for row in range(self.grid.count())]
        return [item.data(ROLE_REF) for item in items]

    def _on_save(self, only_selected: bool = False) -> None:
        path = self.source.path
        if not path:
            self.show_warning("请先选择文件", "还没有选择要编辑的 PDF。")
            return

        refs = self._collect(only_selected)
        if not refs:
            self.show_warning("没有可保存的页面", "结果为空，请检查是否删除过度。")
            return

        suffix = "_选中页" if only_selected else "_编辑"
        default = default_output_path(path, suffix)
        output = Path(self.output.path) if self.output.path else default
        if only_selected or output.suffix.lower() != ".pdf":
            output = Path(str(default))

        try:
            if output.resolve() == Path(path).resolve():
                raise PdfError("输出路径与源文件相同，会覆盖原文件。请换一个文件名。")
        except OSError:
            pass

        output = unique_path(output)
        self.output.set_path(output)

        password = self.password.text() or None
        description = "正在保存所选页面…" if only_selected else "正在保存编辑结果…"

        def job(context):
            return save_pages(path, output, refs, password=password, ctx=context)

        self.start_task(job, description)

    def on_task_finished(self, result) -> None:
        path = Path(result)
        size = human_size(path.stat().st_size) if path.exists() else "未知"
        self.show_info(
            "保存完成",
            f"已生成：{path.name}\n页数：{len(self._collect(False))}\n大小：{size}\n位置：{path.parent}",
        )
        reveal_in_file_manager(path)
