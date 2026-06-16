import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tmux_session import TmuxSession


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


if __name__ == "__main__":
    unittest.main()
