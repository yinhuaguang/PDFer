"""图形界面的冒烟测试。

用 Qt 的 offscreen 平台跑，无需真实显示器，因此可以在 CI 里执行。
只验证「界面能构建、面板能切换、文件能载入」，不重复测试核心逻辑。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过界面测试")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pdfer.gui.main_window import PANEL_SPECS, MainWindow  # noqa: E402
from pdfer.gui.panels import (  # noqa: E402
    ConvertPanel,
    ExtractPanel,
    InfoPanel,
    MergePanel,
    SplitPanel,
)
from pdfer.gui.theme import apply_theme  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    apply_theme(instance)
    return instance  # type: ignore[return-value]


@pytest.fixture
def window(app: QApplication) -> MainWindow:
    win = MainWindow()
    yield win
    # 释放 pdfium 持有的文件句柄，否则 Windows 上临时目录清理会失败
    win.pages_panel._reset_state()
    win.runner.wait_for_done(1000)
    win.close()


class TestMainWindow:
    def test_all_panels_built(self, window: MainWindow) -> None:
        assert window.stack.count() == len(PANEL_SPECS)
        assert window.sidebar.count() == len(PANEL_SPECS)
        for panel_class, _ in PANEL_SPECS:
            assert isinstance(window._panel(panel_class), panel_class)

    def test_first_panel_is_merge(self, window: MainWindow) -> None:
        assert isinstance(window.stack.currentWidget(), MergePanel)

    def test_switching_panels(self, window: MainWindow) -> None:
        window.show_panel(SplitPanel)
        assert isinstance(window.stack.currentWidget(), SplitPanel)
        window.show_panel(InfoPanel)
        assert isinstance(window.stack.currentWidget(), InfoPanel)

    def test_panel_titles_match_sidebar(self, window: MainWindow) -> None:
        for row, (panel_class, _) in enumerate(PANEL_SPECS):
            assert window.sidebar.item(row).text() == window._panel(panel_class).title

    def test_progress_is_hidden_initially(self, window: MainWindow) -> None:
        assert not window.progress.isVisible()
        assert not window.cancel_button.isVisible()

    def test_status_text(self, window: MainWindow) -> None:
        assert window.status_label.text() == "就绪"


class TestMergePanel:
    def test_starts_empty(self, window: MainWindow) -> None:
        assert window.merge_panel.files() == []

    def test_add_and_summarize(self, window: MainWindow, sample_pdf: Path, tmp_path: Path) -> None:
        from tests.conftest import make_pdf

        second = make_pdf(tmp_path / "second.pdf", 3)
        panel = window.merge_panel
        panel.add_files([str(sample_pdf), str(second)])

        assert len(panel.files()) == 2
        assert "2 个文件" in panel.summary.text()
        assert "8 页" in panel.summary.text()

    def test_ignores_non_pdf(self, window: MainWindow, tmp_path: Path) -> None:
        text_file = tmp_path / "note.txt"
        text_file.write_text("hello", encoding="utf-8")
        panel = window.merge_panel
        panel.add_files([str(text_file)])
        assert panel.files() == []

    def test_suggests_output_next_to_first_file(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.merge_panel
        panel.add_files([str(sample_pdf)])
        assert Path(panel.output.path).name == "合并结果.pdf"
        assert Path(panel.output.path).parent == sample_pdf.parent

    def test_move_reorders(self, window: MainWindow, sample_pdf: Path, tmp_path: Path) -> None:
        from tests.conftest import make_pdf

        second = make_pdf(tmp_path / "b.pdf", 1)
        panel = window.merge_panel
        panel.add_files([str(sample_pdf), str(second)])
        panel.list.setCurrentRow(0)
        panel._move(1)
        assert Path(panel.files()[0]).name == "b.pdf"

    def test_clear(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.merge_panel
        panel.add_files([str(sample_pdf)])
        panel._on_clear()
        assert panel.files() == []
        assert panel.output.path == ""

    def test_start_requires_two_files(self, window: MainWindow) -> None:
        """文件不足时应当被拦下，且不会启动后台任务。"""
        panel = window.merge_panel
        panel.show_warning = lambda *a, **k: None  # type: ignore[method-assign]
        panel._on_start()
        assert not window.runner.busy


class TestSplitPanel:
    def test_default_mode(self, window: MainWindow) -> None:
        assert window.split_panel.current_mode() == "every_n"

    def test_mode_switch_changes_page(self, window: MainWindow) -> None:
        panel = window.split_panel
        panel._on_mode_changed(2)
        assert panel.current_mode() == "ranges"
        assert panel.params.currentIndex() == 2

    def test_loads_document_info(self, window: MainWindow, outlined_pdf: Path) -> None:
        panel = window.split_panel
        panel.source.set_path(str(outlined_pdf))
        assert "5 页" in panel.file_info.text()
        assert "书签" in panel.bookmark_hint.text()

    def test_default_output_dir(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.split_panel
        panel.source.set_path(str(sample_pdf))
        assert Path(panel.output.path).name == "sample_拆分"

    def test_preview_lists_planned_files(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.split_panel
        panel.source.set_path(str(sample_pdf))
        panel.every_n.setValue(2)
        panel._on_preview()
        assert panel.plan_list.count() == 3
        assert "sample_p1-2.pdf" in panel.plan_list.item(0).text()

    def test_preview_reports_bad_range(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.split_panel
        panel.source.set_path(str(sample_pdf))
        panel._on_mode_changed(2)
        panel.ranges_edit.setText("99-100")
        captured: list[str] = []
        panel.show_error = lambda title, text: captured.append(text)  # type: ignore[method-assign]
        panel._on_preview()
        assert captured and "超出范围" in captured[0]


class TestPagesPanel:
    def test_loads_thumbnails_progressively(self, window: MainWindow, app: QApplication, sample_pdf: Path) -> None:
        panel = window.pages_panel
        panel.source.set_path(str(sample_pdf))
        assert panel.grid.count() == 5

        # 让增量渲染的定时器跑几轮
        for _ in range(30):
            app.processEvents()
        assert panel._thumb_cache, "缩略图定时器没有产出任何缓存"
        assert "5" in panel.render_status.text()

    def test_default_output_name(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.pages_panel
        panel.source.set_path(str(sample_pdf))
        assert Path(panel.output.path).name == "sample_编辑.pdf"

    def test_rotate_updates_item(self, window: MainWindow, sample_pdf: Path) -> None:
        from pdfer.core import PageRef
        from pdfer.gui.panels.pages_panel import ROLE_REF

        panel = window.pages_panel
        panel.source.set_path(str(sample_pdf))
        panel.grid.setCurrentRow(0)
        panel._rotate(90)

        ref = panel.grid.item(0).data(ROLE_REF)
        assert isinstance(ref, PageRef)
        assert ref.rotation == 90
        assert "↻90" in panel.grid.item(0).text()

    def test_delete_removes_item(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.pages_panel
        panel.source.set_path(str(sample_pdf))
        panel.grid.setCurrentRow(0)
        panel._delete()
        assert panel.grid.count() == 4

    def test_refuses_to_delete_everything(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.pages_panel
        panel.source.set_path(str(sample_pdf))
        warnings: list[str] = []
        panel.show_warning = lambda title, text: warnings.append(text)  # type: ignore[method-assign]
        panel.grid.selectAll()
        panel._delete()
        assert panel.grid.count() == 5
        assert warnings

    def test_duplicate_adds_copy(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.pages_panel
        panel.source.set_path(str(sample_pdf))
        panel.grid.setCurrentRow(0)
        panel._duplicate()
        assert panel.grid.count() == 6

    def test_collect_respects_view_order(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.pages_panel
        panel.source.set_path(str(sample_pdf))
        panel.grid.setCurrentRow(0)
        panel._move(2)
        assert [ref.index for ref in panel._collect(False)] == [1, 2, 0, 3, 4]

    def test_operations_without_selection_warn(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window.pages_panel
        panel.source.set_path(str(sample_pdf))
        warnings: list[str] = []
        panel.show_warning = lambda title, text: warnings.append(text)  # type: ignore[method-assign]
        panel.grid.clearSelection()
        panel._rotate(90)
        assert warnings


class TestExtractPanel:
    def test_default_choice_is_images(self, window: MainWindow) -> None:
        assert window._panel(ExtractPanel).current_choice() == 0

    def test_switching_choice_swaps_output_row(self, window: MainWindow) -> None:
        panel = window._panel(ExtractPanel)
        panel._on_choice_changed(1)
        assert panel.output.currentIndex() == 1
        assert "文字" in panel.start_button.text()

    def test_output_paths(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window._panel(ExtractPanel)
        panel.source.set_path(str(sample_pdf))
        assert Path(panel.image_output.path).name == "sample_图片"
        panel._on_choice_changed(1)
        assert Path(panel.text_output.path).name == "sample_文字.txt"


class TestConvertPanel:
    def test_estimate_after_load(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window._panel(ConvertPanel)
        panel.source.set_path(str(sample_pdf))
        assert "像素" in panel.estimate.text()

    def test_dpi_affects_estimate(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window._panel(ConvertPanel)
        panel.source.set_path(str(sample_pdf))
        panel.dpi.setValue(72)
        low = panel.estimate.text()
        panel.dpi.setValue(300)
        assert panel.estimate.text() != low

    def test_preset_updates_dpi(self, window: MainWindow) -> None:
        panel = window._panel(ConvertPanel)
        panel._on_preset(4)  # 300 dpi
        assert panel.dpi.value() == 300


class TestInfoPanel:
    def test_renders_details(self, window: MainWindow, sample_pdf: Path) -> None:
        panel = window._panel(InfoPanel)
        panel.source.set_path(str(sample_pdf))
        html = panel.browser.toHtml()
        assert "5 页" in html
        assert "未加密" in html

    def test_reports_encrypted(self, window: MainWindow, encrypted_pdf: Path) -> None:
        panel = window._panel(InfoPanel)
        panel.password.setText("secret")
        panel.source.set_path(str(encrypted_pdf))
        assert "已加密" in panel.browser.toHtml()


class TestTheme:
    def test_icon_is_generated(self) -> None:
        from pdfer.gui.widgets import pil_to_qpixmap
        from pdfer.icon import render_icon

        pixmap = pil_to_qpixmap(render_icon(64))
        assert not pixmap.isNull()
        assert pixmap.width() == 64

    def test_stylesheet_applied(self, app: QApplication) -> None:
        assert "QPushButton" in app.styleSheet()
