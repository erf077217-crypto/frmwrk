import unittest
import re

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


class TestAnsiStripping(unittest.TestCase):

    def test_strips_sgr_reset(self):
        self.assertEqual(strip_ansi('hello\x1b[0m world'), 'hello world')

    def test_strips_color_codes(self):
        raw = '\x1b[31mERROR\x1b[0m: failed'
        clean = 'ERROR: failed'
        self.assertEqual(strip_ansi(raw), clean)

    def test_strips_mixed_sequences(self):
        raw = '\x1b[32m> build \u00b7 big-pickle \x1b[0m Hello!'
        clean = '> build \u00b7 big-pickle  Hello!'
        self.assertEqual(strip_ansi(raw), clean)

    def test_strips_csi_sequences(self):
        cases = [
            ('\x1b[K', ''),
            ('\x1b[2K', ''),
            ('\x1b[1;31m', ''),
            ('\x1b[?25l', ''),
            ('\x1b[?25h', ''),
        ]
        for raw, expected in cases:
            with self.subTest(raw=repr(raw)):
                self.assertEqual(strip_ansi(raw), expected)

    def test_preserves_plain_text(self):
        self.assertEqual(strip_ansi('hello world'), 'hello world')

    def test_preserves_newlines(self):
        self.assertEqual(strip_ansi('line1\nline2'), 'line1\nline2')

    def test_empty_string(self):
        self.assertEqual(strip_ansi(''), '')

    def test_real_world_output(self):
        raw = (
            '\x1b[0m > build \u00b7 big-pickle \x1b[0m '
            '\x1b[32mHello! How can I help you today?\x1b[0m'
        )
        clean = ' > build \u00b7 big-pickle  Hello! How can I help you today?'
        self.assertEqual(strip_ansi(raw), clean)


if __name__ == '__main__':
    unittest.main()
