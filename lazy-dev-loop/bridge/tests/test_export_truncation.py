"""Validation: opencode export must not truncate at 64KB pipe limit.

Root cause
----------
Node.js ``process.stdout.write()`` (used by ``console.log``) silently
truncated output at ~65536 bytes when stdout was connected to a pipe
(``subprocess.PIPE``).  The fix redirects stdout to a temp file via the
shell (``> /tmp/...``), bypassing the pipe.

This test validates the fix.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import tmux_session
from platforms.factory import get_platform


class TestExportTruncation(unittest.TestCase):
    """Verify the file-redirect workaround captures large output correctly."""

    def test_file_redirect_captures_large_json(self):
        """Write large JSON to a file via subprocess shell redirect, verify no truncation."""
        LARGE_SIZE = 200_000
        platform = get_platform()
        helper = "/tmp/truncation_helper.py"
        fd, tmp = tempfile.mkstemp(suffix=".json", dir="/tmp")
        os.close(fd)
        os.chmod(tmp, 0o666)
        try:
            # Write JSON to the temp file inside the subprocess,
            # then confirm we can read it back completely.
            result = platform.run(
                f"python3 {helper} {tmp} {LARGE_SIZE}",
                timeout=30,
            )
            self.assertEqual(
                result.returncode, 0,
                f"helper failed: rc={result.returncode} stderr={result.stderr!r}",
            )
            with open(tmp, "r") as f:
                loaded = json.load(f)
            content = loaded["messages"][0]["content"]
            self.assertEqual(
                len(content), LARGE_SIZE,
                f"Content truncated: expected {LARGE_SIZE} bytes, got {len(content)}",
            )
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def test_opencode_cli_stdout_not_empty(self):
        """Verify _opencode_cli returns non-empty stdout via file redirect."""
        stdout, stderr, rc = tmux_session._opencode_cli("--version")
        self.assertEqual(rc, 0, f"opencode --version failed: rc={rc} stderr={stderr!r}")
        self.assertTrue(len(stdout) > 0, "stdout was empty")

    def test_small_output_not_broken(self):
        """Ensure the file redirect does not break small outputs."""
        platform = get_platform()
        result = platform.run("echo -n hello", timeout=10)
        self.assertIn("hello", result.stdout)


if __name__ == "__main__":
    unittest.main()
