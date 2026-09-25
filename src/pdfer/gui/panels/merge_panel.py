"""合并 PDF 面板。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core import human_size, merge, open_reader, validate_sources
from ..widgets import DropFileList, Hint, PathRow, reveal_in_file_manager
from .base import Panel


class MergePanel(Panel):
    title = "合并 PDF"
    description = "把多个 PDF 按你排定的顺序拼成一个文件。列表内可直接拖动调整顺序。"

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(self.make_header(self.title, self.description))

        self.list = DropFileList()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.files_dropped.connect(self.add_files)
        self.list.setMinimumHeight(200)
        layout.addWidget(self.list, 1)

        layout.addWidget(self._build_toolbar())

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        self.output = PathRow("输出到", mode="save_file", placeholder="合并后的 PDF 保存位置")
        bottom_layout.addWidget(self.output)

        self.bookmarks = QCheckBox("为每个源文件生成一个书签（推荐，合并后便于跳转）")
        self.bookmarks.setChecked(True)
        bottom_layout.addWidget(self.bookmarks)

        self.summary = Hint("尚未添加文件")
        bottom_layout.addWidget(self.summary)

        action_row = QHBoxLayout()
        action_row.addWidget(self.summary, 1)
        self.start_button = self.make_primary_button("开始合并", self._on_start)
        action_row.addWidget(self.start_button)
        bottom_layout.addLayout(action_row)

        layout.addWidget(bottom)

    def _build_toolbar(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for text, slot in (
            ("添加文件", self._on_add_files),
            ("添加文件夹", self._on_add_folder),
            ("移除所选", self._on_remove),
            ("清空", self._on_clear),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            layout.addWidget(button)

        layout.addStretch(1)

        self.up_button = QPushButton("上移")
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button = QPushButton("下移")
        self.down_button.clicked.connect(lambda: self._move(1))
        layout.addWidget(self.up_button)
        layout.addWidget(self.down_button)
        return row

    # ------------------------------------------------------------------ 列表操作

    def files(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def add_files(self, paths: list[str]) -> None:
        existing = set(self.files())
        added = 0
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() != ".pdf" or str(path) in existing:
                continue
            self.list.addItem(str(path))
            existing.add(str(path))
            added += 1
        if added:
            self.list.setCurrentRow(self.list.count() - 1)
        self._refresh_suggested_output()
        self._refresh_summary()

    def _on_add_files(self) -> None:
        from ..widgets import browse_pdf_files

        paths = browse_pdf_files(self, "选择要合并的 PDF（可多选）")
        if paths:
            self.add_files(paths)

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择包含 PDF 的文件夹")
        if not folder:
            return
        found = sorted(Path(folder).glob("*.pdf"), key=lambda p: p.name.lower())
        if not found:
            self.show_info("没有找到 PDF", f"文件夹 {folder} 中没有 PDF 文件。")
            return
        self.add_files([str(p) for p in found])

    def _on_remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._refresh_suggested_output()
        self._refresh_summary()

    def _on_clear(self) -> None:
        self.list.clear()
        self.output.clear()
        self._refresh_summary()

    def _move(self, offset: int) -> None:
        row = self.list.currentRow()
        target = row + offset
        if row < 0 or not 0 <= target < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    # ------------------------------------------------------------------ 状态刷新

    def _refresh_suggested_output(self) -> None:
        files = self.files()
        if not files:
            self.output.clear()
            return
        first = Path(files[0])
        suggestion = first.parent / "合并结果.pdf"
        if self.output.path != str(suggestion):
            self.output.set_path(suggestion)

    def _refresh_summary(self) -> None:
        files = self.files()
        if not files:
            self.summary.setText("尚未添加文件。可以直接把 PDF 拖到上方列表。")
            return

        total_bytes = 0
        total_pages = 0
        unreadable: list[str] = []
        for path in files:
            try:
                total_bytes += Path(path).stat().st_size
                total_pages += len(open_reader(path).pages)
            except Exception:  # noqa: BLE001 - 汇总信息容错，不打断用户
                unreadable.append(Path(path).name)

        text = f"共 {len(files)} 个文件 · {total_pages} 页 · 合计 {human_size(total_bytes)}"
        notices = validate_sources(files)
        if unreadable:
            notices.append(f"无法读取：{'、'.join(unreadable[:3])}")
        if notices:
            text += "\n⚠ " + "；".join(notices)
        self.summary.setText(text)

    # ------------------------------------------------------------------ 执行

    def _on_start(self) -> None:
        files = self.files()
        if len(files) < 2:
            self.show_warning("还差一点", "合并至少需要 2 个 PDF 文件。")
            return

        output = self.output.path or str(Path(files[0]).parent / "合并结果.pdf")
        self.output.set_path(output)
        use_bookmarks = self.bookmarks.isChecked()

        def job(context):
            return merge(files, output, bookmark_per_file=use_bookmarks, ctx=context)

        self.start_task(job, f"正在合并 {len(files)} 个文件…")

    def on_task_finished(self, result) -> None:
        path = Path(result)
        size = human_size(path.stat().st_size) if path.exists() else "未知"
        self.show_info(
            "合并完成",
            f"已生成：{path.name}\n大小：{size}\n位置：{path.parent}",
        )
        reveal_in_file_manager(path)
