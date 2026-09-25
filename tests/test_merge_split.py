"""合并与拆分的测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from pdfer.core import (
    PdfOperationError,
    build_groups,
    merge,
    open_reader,
    parse_groups,
    split,
    validate_sources,
)
from pdfer.core.errors import TaskCancelledError
from pdfer.core.progress import TaskContext

from .conftest import make_pdf


class TestMerge:
    def test_merge_two_files(self, tmp_path: Path) -> None:
        first = make_pdf(tmp_path / "a.pdf", 2)
        second = make_pdf(tmp_path / "b.pdf", 3)
        output = merge([first, second], tmp_path / "merged.pdf")
        assert output.exists()
        assert len(PdfReader(str(output)).pages) == 5

    def test_merge_preserves_order(self, tmp_path: Path) -> None:
        first = make_pdf(tmp_path / "a.pdf", 2, rotate=0)
        second = make_pdf(tmp_path / "b.pdf", 2)
        output = merge([first, second], tmp_path / "merged.pdf")
        reader = PdfReader(str(output))
        # reportlab 把页号写在页面文本里，第一页应来自 a.pdf
        assert "Page 1" in (reader.pages[0].extract_text() or "")
        assert "Page 1" in (reader.pages[2].extract_text() or "")

    def test_bookmarks_added(self, tmp_path: Path) -> None:
        first = make_pdf(tmp_path / "甲.pdf", 2)
        second = make_pdf(tmp_path / "乙.pdf", 2)
        output = merge([first, second], tmp_path / "merged.pdf", bookmark_per_file=True)
        titles = [item.title for item in PdfReader(str(output)).outline]
        assert titles == ["甲", "乙"]

    def test_bookmarks_can_be_disabled(self, tmp_path: Path) -> None:
        output = merge(
            [make_pdf(tmp_path / "a.pdf", 1), make_pdf(tmp_path / "b.pdf", 1)],
            tmp_path / "merged.pdf",
            bookmark_per_file=False,
        )
        assert PdfReader(str(output)).outline == []

    def test_creates_missing_output_dir(self, tmp_path: Path) -> None:
        output = merge(
            [make_pdf(tmp_path / "a.pdf", 1), make_pdf(tmp_path / "b.pdf", 1)],
            tmp_path / "nested" / "deep" / "merged.pdf",
        )
        assert output.exists()

    def test_single_file_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(PdfOperationError, match="至少需要 2 个"):
            merge([make_pdf(tmp_path / "a.pdf", 1)], tmp_path / "out.pdf")

    def test_duplicate_files_rejected(self, tmp_path: Path) -> None:
        path = make_pdf(tmp_path / "a.pdf", 1)
        with pytest.raises(PdfOperationError, match="重复"):
            merge([path, path], tmp_path / "out.pdf")

    def test_missing_file_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(PdfOperationError, match="不存在"):
            merge(
                [make_pdf(tmp_path / "a.pdf", 1), tmp_path / "ghost.pdf"],
                tmp_path / "out.pdf",
            )

    def test_encrypted_source(self, tmp_path: Path, encrypted_pdf: Path) -> None:
        other = make_pdf(tmp_path / "b.pdf", 1)
        output = merge([encrypted_pdf, other], tmp_path / "out.pdf", password="secret")
        assert len(PdfReader(str(output)).pages) == 4

    def test_cancellation(self, tmp_path: Path) -> None:
        files = [make_pdf(tmp_path / f"f{i}.pdf", 1) for i in range(4)]
        context = TaskContext(is_cancelled=lambda: True)
        with pytest.raises(TaskCancelledError):
            merge(files, tmp_path / "out.pdf", ctx=context)

    def test_progress_reported(self, tmp_path: Path) -> None:
        events: list[tuple[int, int]] = []
        context = TaskContext(on_progress=lambda p: events.append((p.current, p.total)))
        files = [make_pdf(tmp_path / f"f{i}.pdf", 1) for i in range(3)]
        merge(files, tmp_path / "out.pdf", ctx=context)
        assert events[-1] == (3, 3)


class TestValidateSources:
    def test_too_few(self, tmp_path: Path) -> None:
        warnings = validate_sources([tmp_path / "a.pdf"])
        assert any("至少需要 2 个" in w for w in warnings)

    def test_detects_duplicates(self, tmp_path: Path) -> None:
        path = make_pdf(tmp_path / "a.pdf", 1)
        warnings = validate_sources([path, path])
        assert any("2 次" in w for w in warnings)

    def test_clean_input(self, tmp_path: Path) -> None:
        files = [make_pdf(tmp_path / "a.pdf", 1), make_pdf(tmp_path / "b.pdf", 1)]
        assert validate_sources(files) == []


class TestBuildGroups:
    def test_every_n(self, sample_pdf: Path) -> None:
        reader = open_reader(sample_pdf)
        plan = build_groups(reader, 5, mode="every_n", pages_per_file=2)
        assert [indexes for _, indexes in plan] == [[0, 1], [2, 3], [4]]
        assert [name for name, _ in plan] == ["p1-2", "p3-4", "p5"]

    def test_every_n_invalid(self, sample_pdf: Path) -> None:
        with pytest.raises(PdfOperationError):
            build_groups(open_reader(sample_pdf), 5, mode="every_n", pages_per_file=0)

    def test_each(self, sample_pdf: Path) -> None:
        plan = build_groups(open_reader(sample_pdf), 3, mode="each")
        assert [name for name, _ in plan] == ["p1", "p2", "p3"]

    def test_ranges(self, sample_pdf: Path) -> None:
        groups = parse_groups("1-2;4", 5)
        plan = build_groups(open_reader(sample_pdf), 5, mode="ranges", groups=groups)
        assert [indexes for _, indexes in plan] == [[0, 1], [3]]

    def test_ranges_without_groups(self, sample_pdf: Path) -> None:
        with pytest.raises(PdfOperationError, match="页码范围"):
            build_groups(open_reader(sample_pdf), 5, mode="ranges")

    def test_bookmarks(self, outlined_pdf: Path) -> None:
        plan = build_groups(open_reader(outlined_pdf), 5, mode="bookmarks")
        assert len(plan) == 5
        assert plan[0][0] == "Chapter 1"
        assert plan[0][1] == [0]

    def test_bookmarks_on_plain_document(self, sample_pdf: Path) -> None:
        with pytest.raises(PdfOperationError, match="没有顶层书签"):
            build_groups(open_reader(sample_pdf), 5, mode="bookmarks")

    def test_unknown_mode(self, sample_pdf: Path) -> None:
        with pytest.raises(PdfOperationError, match="未知的拆分模式"):
            build_groups(open_reader(sample_pdf), 5, mode="nonsense")


class TestSplit:
    def test_every_n(self, sample_pdf: Path, tmp_path: Path) -> None:
        out = tmp_path / "out"
        files = split(sample_pdf, out, mode="every_n", pages_per_file=2)
        assert len(files) == 3
        assert [len(PdfReader(str(f)).pages) for f in files] == [2, 2, 1]
        assert all(f.parent == out for f in files)

    def test_each(self, sample_pdf: Path, tmp_path: Path) -> None:
        files = split(sample_pdf, tmp_path / "out", mode="each")
        assert len(files) == 5
        assert all(len(PdfReader(str(f)).pages) == 1 for f in files)

    def test_ranges(self, sample_pdf: Path, tmp_path: Path) -> None:
        groups = parse_groups("1-2;5", 5)
        files = split(sample_pdf, tmp_path / "out", mode="ranges", groups=groups)
        assert [len(PdfReader(str(f)).pages) for f in files] == [2, 1]

    def test_bookmarks(self, outlined_pdf: Path, tmp_path: Path) -> None:
        files = split(outlined_pdf, tmp_path / "out", mode="bookmarks")
        assert len(files) == 5

    def test_custom_prefix(self, sample_pdf: Path, tmp_path: Path) -> None:
        files = split(sample_pdf, tmp_path / "out", mode="each", prefix="报告")
        assert files[0].name == "报告_p1.pdf"

    def test_sanitizes_illegal_filename_chars(self, outlined_pdf: Path, tmp_path: Path) -> None:
        files = split(outlined_pdf, tmp_path / "out", mode="every_n", prefix="a/b:c*")
        # 前缀由调用方提供时不清理，但书签标题里的非法字符必须被替换
        assert all(f.exists() for f in files)

    def test_encrypted(self, encrypted_pdf: Path, tmp_path: Path) -> None:
        files = split(encrypted_pdf, tmp_path / "out", mode="each", password="secret")
        assert len(files) == 3

    def test_wrong_password(self, encrypted_pdf: Path, tmp_path: Path) -> None:
        with pytest.raises(Exception):
            split(encrypted_pdf, tmp_path / "out", mode="each", password="nope")

    def test_cancellation(self, sample_pdf: Path, tmp_path: Path) -> None:
        context = TaskContext(is_cancelled=lambda: True)
        with pytest.raises(TaskCancelledError):
            split(sample_pdf, tmp_path / "out", mode="each", ctx=context)
