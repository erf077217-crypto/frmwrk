"""
Full tmux flow integration test.

Tests the core tmux+opencode flow directly inside WSL:
  1. Start opencode inside a named tmux session
  2. Send a prompt via tmux send-keys
  3. Capture the response via tmux capture-pane
  4. Extract new content after sending
  5. Cleanup

Run: python3 bridge/tests/test_tmux_integration.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tmux_session import (
    TmuxSession,
    _escape_single_quotes,
    strip_ansi,
)

TMUX_SESSION = "lazy-dev-loop"
WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.getcwd())))


def tmux(cmd: str) -> tuple[str, str, int]:
    full = f"tmux {cmd}"
    r = subprocess.run(
        full,
        capture_output=True,
        text=True,
        timeout=10,
        shell=True,
    )
    return r.stdout, r.stderr, r.returncode


def cleanup():
    tmux(f"kill-session -t {TMUX_SESSION} 2>/dev/null")


def test_lifecycle():
    print("=== Tmux + OpenCode Integration Test ===\n")

    # 0. Pre-flight
    r = subprocess.run(["which", "tmux"], capture_output=True, text=True)
    assert r.returncode == 0, "tmux not found"
    print(f"[OK] tmux: {subprocess.run(['tmux', '-V'], capture_output=True, text=True).stdout.strip()}")

    r = subprocess.run(["which", "opencode"], capture_output=True, text=True)
    assert r.returncode == 0, "opencode not found"
    print(f"[OK] opencode: {subprocess.run(['opencode', '--version'], capture_output=True, text=True).stdout.strip()}")

    cleanup()
    time.sleep(0.5)

    # 1. Start opencode in a detached tmux session
    opencode_cmd = f"cd {WORKSPACE} && opencode"
    print(f"[EXEC] tmux new-session -d -s {TMUX_SESSION} {opencode_cmd!r}")
    _, stderr, rc = tmux(f"new-session -d -s {TMUX_SESSION} {opencode_cmd!r}")
    print(f"       rc={rc}, stderr={stderr[:200] if stderr else '(none)'}")
    assert rc == 0, f"tmux new-session failed: rc={rc}, stderr={stderr}"

    # 2. Verify session is running
    _, _, rc = tmux(f"has-session -t {TMUX_SESSION}")
    assert rc == 0, "tmux session should exist"
    print("[OK] tmux session is running")

    # 3. Wait for opencode to initialise (loads context, shows prompt)
    print("[...] waiting 10s for opencode initialisation...")
    time.sleep(10)

    # 4. Capture the pane before sending
    before, *_ = tmux(f"capture-pane -t {TMUX_SESSION} -p")
    print(f"[BEFORE] pane content ({len(before)} chars)")
    last_lines = "\n".join(before.rstrip("\n").split("\n")[-3:])
    print(f"         last 3 lines: {last_lines!r}")

    # 5. Send a prompt
    prompt = "Say hello in one short sentence."
    escaped = _escape_single_quotes(prompt)
    send_cmd = f"send-keys -t {TMUX_SESSION} '{escaped}' Enter"
    print(f"[SEND] {send_cmd}")
    _, stderr, rc = tmux(send_cmd)
    print(f"       rc={rc}, stderr={stderr[:200] if stderr else '(none)'}")
    assert rc == 0, f"send-keys failed"

    # 6. Wait for stable output
    print("[...] waiting for stable output...")
    deadline = time.time() + 180
    last_output = before
    stable_since = None
    poll_count = 0

    while time.time() < deadline:
        time.sleep(0.25)
        poll_count += 1
        current, *_ = tmux(f"capture-pane -t {TMUX_SESSION} -p")
        if current == last_output:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= 1.5:
                break
        else:
            last_output = current
            stable_since = None

    print(f"[OK] stable after {poll_count} polls ({poll_count * 0.25:.1f}s)")

    # 7. Extract new content
    new_content = TmuxSession._extract_new(before, last_output)
    cleaned = strip_ansi(new_content).strip()

    print(f"\n[RESULT] response ({len(cleaned)} chars):")
    for line in cleaned.split("\n"):
        print(f"  | {line}")

    # Verify response is meaningful
    assert len(cleaned) > 0, "response should not be empty"
    assert len(cleaned) > 10, f"response suspiciously short: {cleaned!r}"
    print(f"\n[OK] response looks valid")

    # 8. Pane preview
    content, *_ = tmux(f"capture-pane -t {TMUX_SESSION} -p")
    lines = content.rstrip("\n").split("\n")
    print(f"\n[PREVIEW] last 5 pane lines ({len(lines)} total):")
    for line in lines[-5:]:
        print(f"  | {strip_ansi(line)}")

    # 9. Stop the session
    tmux(f"send-keys -t {TMUX_SESSION} 'C-c' Enter")
    time.sleep(1)
    cleanup()
    _, _, rc = tmux(f"has-session -t {TMUX_SESSION} 2>/dev/null")
    assert rc != 0, "session should be gone after kill"
    print("\n[OK] session cleaned up")

    print("\n=== ALL TESTS PASSED ===")
    return True


if __name__ == "__main__":
    try:
        success = test_lifecycle()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    finally:
        cleanup()
