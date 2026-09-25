"""页码范围解析的测试。

这是最容易出错、也最容易被用户踩到的一环（"1-3;5-8" 与 "1-3,5-8" 的区别），
所以覆盖得细一些。
"""

from __future__ import annotations

import pytest

from pdfer.core import PageRangeError, compress_pages, parse_groups, parse_pages


class TestParsePages:
    def test_single_page(self) -> None:
        assert parse_pages("3", 10) == [2]

    def test_closed_range(self) -> None:
        assert parse_pages("2-4", 10) == [1, 2, 3]

    def test_mixed(self) -> None:
        assert parse_pages("1-3,7,9-10", 10) == [0, 1, 2, 6, 8, 9]

    def test_open_end_uses_total(self) -> None:
        assert parse_pages("8-", 10) == [7, 8, 9]

    def test_open_start_uses_total(self) -> None:
        assert parse_pages("-3", 10) == [0, 1, 2]

    @pytest.mark.parametrize("separator", [",", "，", "、", ";", "；", " "])
    def test_chinese_separators(self, separator: str) -> None:
        assert parse_pages(f"1{separator}3", 10) == [0, 2]

    def test_wave_dash(self) -> None:
        assert parse_pages("1~3", 10) == [0, 1, 2]

    def test_dedupe_keeps_first_order(self) -> None:
        assert parse_pages("3,1,3,2", 10) == [2, 0, 1]

    def test_dedupe_off(self) -> None:
        assert parse_pages("1,1,2", 10, dedupe=False) == [0, 0, 1]

    def test_clamps_to_total(self) -> None:
        assert parse_pages("4-99", 5) == [3, 4]

    def test_empty_raises(self) -> None:
        with pytest.raises(PageRangeError):
            parse_pages("", 5)

    def test_zero_raises(self) -> None:
        with pytest.raises(PageRangeError):
            parse_pages("0", 5)

    def test_reversed_raises(self) -> None:
        with pytest.raises(PageRangeError):
            parse_pages("5-2", 10)

    def test_out_of_range_raises(self) -> None:
        with pytest.raises(PageRangeError):
            parse_pages("9", 5)

    def test_open_range_without_total_raises(self) -> None:
        with pytest.raises(PageRangeError):
            parse_pages("3-", None)

    def test_garbage_raises(self) -> None:
        with pytest.raises(PageRangeError):
            parse_pages("abc", 10)


class TestParseGroups:
    def test_semicolon_splits_groups(self) -> None:
        assert parse_groups("1-2;4", 10) == [[0, 1], [3]]

    def test_comma_also_splits_groups(self) -> None:
        assert parse_groups("1-2,4", 10) == [[0, 1], [3]]

    def test_single_group(self) -> None:
        assert parse_groups("1-3", 10) == [[0, 1, 2]]

    def test_empty_raises(self) -> None:
        with pytest.raises(PageRangeError):
            parse_groups("   ", 10)


class TestCompressPages:
    def test_consecutive(self) -> None:
        assert compress_pages([0, 1, 2]) == "1-3"

    def test_single(self) -> None:
        assert compress_pages([4]) == "5"

    def test_mixed_sorts_input(self) -> None:
        assert compress_pages([6, 0, 1, 2]) == "1-3,7"

    def test_empty(self) -> None:
        assert compress_pages([]) == ""
