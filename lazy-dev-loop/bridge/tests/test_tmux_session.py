import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tmux_session import TmuxSession, _diff_captures


class TestTmuxSessionHelpers(unittest.TestCase):

    def test_extract_new_prefix(self):
        result = TmuxSession._extract_new("before\n", "before\nnew content\n")
        self.assertEqual(result, "new content\n")

    def test_extract_new_fallback(self):
        result = TmuxSession._extract_new("old\n", "new only")
        self.assertEqual(result, "new only")

    def test_extract_new_no_change(self):
        result = TmuxSession._extract_new("same\n", "same\n")
        self.assertEqual(result, "")


class TestDiffCaptures(unittest.TestCase):

    def test_first_capture_returns_full(self):
        self.assertEqual(_diff_captures("", "hello world"), "hello world")

    def test_append_only(self):
        self.assertEqual(_diff_captures("hello ", "hello world"), "world")

    def test_no_change(self):
        self.assertEqual(_diff_captures("same", "same"), "")

    def test_both_empty(self):
        self.assertEqual(_diff_captures("", ""), "")

    def test_second_empty(self):
        self.assertEqual(_diff_captures("content", ""), "")

    def test_partial_overlap(self):
        prev = "aaaaabbbbb"
        curr = "bbbbbccccc"
        result = _diff_captures(prev, curr)
        self.assertEqual(result, "ccccc")

    def test_complete_replacement(self):
        prev = "old content"
        curr = "completely new"
        result = _diff_captures(prev, curr)
        self.assertEqual(result, "completely new")

    def test_multiline_append(self):
        prev = "line1\nline2\n"
        curr = "line1\nline2\nline3\nline4\n"
        self.assertEqual(_diff_captures(prev, curr), "line3\nline4\n")

    def test_scrollback_overflow(self):
        prev = "A" * 100 + "B" * 50
        curr = "B" * 50 + "C" * 30
        result = _diff_captures(prev, curr)
        self.assertEqual(result, "C" * 30)

    def test_search_limit_does_not_crash(self):
        prev = "X" * 20000
        curr = prev + "Y"
        result = _diff_captures(prev, curr)
        self.assertEqual(result, "Y")


if __name__ == "__main__":
    unittest.main()
