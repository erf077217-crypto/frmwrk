import json
import os
import re
import select
import shlex
import subprocess
import threading
import time
import uuid

import config
import workspace_manager as wm
from platforms.factory import get_platform

platform = get_platform()

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
TMUX_SESSION_NAME = "lazy-dev-loop"
_current_session_id: str | None = None
_session_started_at: float | None = None

# ── Runtime debug flag (toggled via API, defaults to config) ──────────────
_debug_enabled = config.DEBUG_OUTPUT
_debug_lock = threading.Lock()


def set_debug(enabled: bool) -> None:
    global _debug_enabled
    with _debug_lock:
        _debug_enabled = enabled


def is_debug_enabled() -> bool:
    with _debug_lock:
        return _debug_enabled


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


def check_tmux() -> bool:
    return platform.check_command("tmux")


def _ensure_tmux() -> bool:
    if check_tmux():
        return True
    try:
        platform.run(
            "sudo apt-get update -qq && sudo apt-get install -y -qq tmux",
            timeout=120,
        )
        return check_tmux()
    except Exception:
        return False


def _capture_pane(scrollback: int = 0) -> str:
    if scrollback > 0:
        stdout, _, _ = _tmux(
            f"capture-pane -t {TMUX_SESSION_NAME} -p -S -{scrollback}"
        )
    else:
        stdout, _, _ = _tmux(f"capture-pane -t {TMUX_SESSION_NAME} -p")
    return strip_ansi(stdout or "")


def _wait_for_opencode_ready(timeout: int = 120) -> bool:
    """Poll until opencode shows its prompt character in the pane."""
    deadline = time.monotonic() + timeout
    t0 = time.monotonic()
    while time.monotonic() < deadline:
        content = _capture_pane_with_scrollback(200)
        if "▣" in content:
            elapsed = time.monotonic() - t0
            _dbg(f"_wait_for_opencode_ready: ready after {elapsed:.1f}s")
            return True
        time.sleep(0.5)
    elapsed = time.monotonic() - t0
    _dbg(f"_wait_for_opencode_ready: TIMEOUT after {elapsed:.1f}s (content={content[-100:]!r})")
    return False


def _tmux(tmux_args: str) -> tuple[str, str, int]:
    t0 = time.monotonic()
    try:
        result = platform.run(f"tmux {tmux_args}", timeout=15)
        elapsed = time.monotonic() - t0
        if elapsed > 0.5 or "has-session" in tmux_args or "send-keys" in tmux_args:
            _dbg(f"_tmux({tmux_args[:80]}) took {elapsed:.3f}s rc={result.returncode}")
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        _dbg(f"_tmux({tmux_args[:80]}) TIMEOUT after {elapsed:.3f}s")
        return "", "timeout", -1
    except FileNotFoundError:
        return "", platform.env_not_found_message, -1


def _opencode_cli(*args: str) -> tuple[str, str, int]:
    inner = " ".join(shlex.quote(a) for a in args)
    try:
        result = platform.run(
            f"cd /tmp && {_opencode_cmd()} {inner} 2>/dev/null",
            timeout=30,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except FileNotFoundError:
        return "", platform.env_not_found_message, -1


def _escape_single_quotes(text: str) -> str:
    return text.replace("'", "'\\''")


def _capture_pane_with_scrollback(scrollback: int = 50000) -> str:
    stdout, _, _ = _tmux(
        f"capture-pane -t {TMUX_SESSION_NAME} -p -S -{scrollback}"
    )
    return strip_ansi(stdout or "")


def _extract_response(pane_content: str, sent_prompt: str) -> str:
    """Extract latest opencode response text from tmux pane capture.

    Strips ANSI, formatting, timing info, and echoed prompts,
    returning only the model's response text for the most recent prompt.
    """

    def _collect(lines_iter, start_idx):
        """Collect response lines starting at start_idx, stopping at ▣."""
        collected = []
        for line in lines_iter[start_idx:]:
            s = line.strip()
            if not s:
                continue
            if "▣" in s:
                break
            if any(s.startswith(c) for c in ("┃", "╹", "▀", "▄", "▌", "─", "│", "╻", "⠋", "⣽", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")):
                continue
            if s.startswith("+"):
                continue
            if s.startswith("→"):
                continue
            if s.startswith("~"):
                continue
            if s.startswith("⬝"):
                continue
            if "ctrl+p" in s or "Build" in s or "◉" in s:
                continue
            collected.append(s)
        return collected

    lines = pane_content.split("\n")

    # Primary method: find prompt echo even if wrapped across multiple ┃ lines
    # Join consecutive ┃-prefixed lines to handle prompt wrapping
    prompt_words = sent_prompt.split()
    if prompt_words:
        first_word = prompt_words[0]
    else:
        first_word = ""

    match_start = -1
    for i, line in enumerate(lines):
        s = line.strip()
        # Check if this line starts a prompt echo block
        if s.startswith("┃") and first_word and first_word in s:
            # Collect consecutive ┃ lines and check if they form the full prompt
            joined = []
            j = i
            while j < len(lines) and lines[j].strip().startswith("┃"):
                joined.append(lines[j].strip().lstrip("┃").strip())
                j += 1
            if joined and sent_prompt in " ".join(joined):
                match_start = i
                break
        # Fallback direct match (for single-line prompts)
        if sent_prompt in s:
            match_start = i
            break

    if match_start >= 0:
        # Skip past the ┃-prefixed block (prompt echo may span multiple lines)
        echo_end = match_start
        while echo_end < len(lines) and lines[echo_end].strip().startswith("┃"):
            echo_end += 1
        result = _collect(lines, echo_end)
        if result:
            return (" ".join(result)).strip()

    # Fallback: prompt echo scrolled out — use ▣ markers
    # Collect content BEFORE the last ▣ (which follows the response)
    marker_idxs = [i for i, line in enumerate(lines) if "▣" in line]
    if len(marker_idxs) >= 2:
        # Content between second-to-last ▣ and last ▣ (or end)
        start = marker_idxs[-2] + 1
        result = _collect(lines, start)
        if result and _looks_like_prompt_echo(result[0]):
            result = result[1:]
        if result:
            return (" ".join(result)).strip()
    elif marker_idxs:
        # Collect content BEFORE the last ▣ (not after)
        # The response is between the prompt echo and the final ▣
        start = 0
        end = marker_idxs[-1]
        result = _collect(lines[:end], start)
        if result:
            return (" ".join(result)).strip()

    return ""


def _looks_like_prompt_echo(line: str) -> bool:
    """Heuristic: a line that is a plain alphanumeric statement (not code/formatted)."""
    # A prompt echo is typically an unformatted text line
    # that doesn't start with formatting chars and is short enough to be user input
    if any(c in line for c in ("```", "{|", "|}", "---", "===")):
        return False
    if len(line) > 500:
        return False
    return True


def _opencode_cmd() -> str:
    cmd = config.OPENCODE_COMMAND
    if '/' not in cmd:
        resolver = getattr(platform, '_resolve_command', None)
        if resolver:
            resolved = resolver(cmd)
            if resolved:
                _dbg(f"Resolved {cmd} -> {resolved}")
                return resolved
    return cmd


def _create_session(timeout: int = 120, cwd: str | None = None) -> str | None:
    opencode = _opencode_cmd()
    inner = (
        f"{opencode} run --format json "
        f"{shlex.quote('.')}"
    )
    proc = None
    session_id = None
    deadline = time.monotonic() + timeout
    try:
        proc = platform.popen(
            inner,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
        )
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _dbg(f"_create_session: timed out after {timeout}s")
                break
            ready, _, _ = select.select([proc.stdout], [], [], remaining)
            if not ready:
                _dbg(f"_create_session: timed out after {timeout}s")
                break
            raw_line = proc.stdout.readline()
            if not raw_line:
                break
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                _dbg(f"_create_session: non-JSON line: {line[:200]}")
                continue
            if event.get("type") == "step_start":
                session_id = event.get("sessionID")
                break

        if session_id is None:
            _dbg("_create_session: no step_start found in output")

        return session_id
    except Exception as exc:
        _dbg(f"_create_session: exception: {exc}")
        return None
    finally:
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except OSError:
                pass


def _normalize_messages(raw_messages: list) -> list[dict]:
    normalized = []
    for msg in raw_messages:
        role = msg.get("info", {}).get("role", msg.get("role", "user"))
        parts = msg.get("parts", [])
        content_parts = []
        for part in parts:
            if part.get("type") == "text":
                t = part.get("text", "")
                if t:
                    content_parts.append(t)
        content = "\n".join(content_parts) if content_parts else (msg.get("content") or msg.get("text") or "")
        normalized.append({"role": role, "content": content})
    return normalized


def _dbg(msg: str):
    if is_debug_enabled():
        print(f"[DEBUG tmux_session] {msg}", flush=True)


# ── Process discovery / cleanup (platform-independent via platform.run) ────


def _find_opencode_processes() -> list[dict]:
    """Find all opencode processes using pgrep (or ps fallback).

    Works on Linux natively and inside WSL because platform.run()
    wraps commands in the appropriate shell.
    """
    results: list[dict] = []
    result = platform.run(
        "pgrep -af opencode 2>/dev/null || ps aux | grep -v grep | grep opencode",
        timeout=10,
    )
    stdout = result.stdout
    rc = result.returncode
    if rc == 0 and stdout:
        for line in stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if parts and parts[0].isdigit():
                pid = int(parts[0])
                cmd = parts[1] if len(parts) > 1 else ""
                if "grep" not in cmd and "pgrep" not in cmd:
                    results.append({"pid": pid, "cmd": cmd})
    _dbg(f"_find_opencode_processes: found {len(results)} process(es)")
    for p in results:
        _dbg(f"_find_opencode_processes:   pid={p['pid']} cmd={p['cmd'][:120]!r}")
    return results


def _kill_process(pid: int, name: str = "") -> bool:
    """Kill a process by PID.  SIGTERM first, then SIGKILL if still alive."""
    label = f"pid={pid}"
    if name:
        label += f" ({name[:80]})"
    _dbg(f"KILL: {label}")

    # SIGTERM
    platform.run(f"kill {pid} 2>/dev/null", timeout=5)
    time.sleep(0.3)

    # Verify — kill -0 checks existence without sending signal
    check = platform.run(f"kill -0 {pid} 2>/dev/null", timeout=5)
    if check.returncode != 0:
        _dbg(f"KILL: {label} terminated by SIGTERM")
        return True

    # SIGKILL
    _dbg(f"KILL: {label} still alive, sending SIGKILL")
    platform.run(f"kill -9 {pid} 2>/dev/null", timeout=5)
    time.sleep(0.3)

    check2 = platform.run(f"kill -0 {pid} 2>/dev/null", timeout=5)
    if check2.returncode != 0:
        _dbg(f"KILL: {label} terminated by SIGKILL")
        return True

    _dbg(f"KILL: {label} COULD NOT BE KILLED")
    return False


# ── Session health check ────────────────────────────────────────────────────


def check_session_health() -> dict:
    """Structured health check of the managed session.

    Returns:
        dict with boolean status per component and diagnostic details.
    """
    _dbg("SESSION HEALTH: checking")
    health: dict = {
        "tmux_session": False,
        "tmux_pane": False,
        "opencode_running": False,
        "opencode_processes": [],
        "workspace_set": False,
        "bridge_state_ok": False,
        "details": {},
    }

    # tmux session
    _, _, rc = _tmux(f"has-session -t {TMUX_SESSION_NAME}")
    health["tmux_session"] = rc == 0
    health["details"]["tmux_has_session_rc"] = rc
    _dbg(f"SESSION HEALTH: tmux session -> {health['tmux_session']} (rc={rc})")

    if health["tmux_session"]:
        # tmux pane(s)
        pane_out, _, pane_rc = _tmux(f"list-panes -t {TMUX_SESSION_NAME}")
        health["tmux_pane"] = pane_rc == 0
        health["details"]["tmux_list_panes_rc"] = pane_rc
        health["details"]["tmux_panes"] = pane_out.strip() if pane_out else ""
        _dbg(f"SESSION HEALTH: tmux panes -> {health['tmux_pane']}")
    else:
        health["details"]["tmux_list_panes_rc"] = -1

    # opencode processes
    oc_procs = _find_opencode_processes()
    health["opencode_running"] = len(oc_procs) > 0
    health["opencode_processes"] = oc_procs
    health["details"]["opencode_process_count"] = len(oc_procs)
    _dbg(f"SESSION HEALTH: opencode processes -> {len(oc_procs)}")

    # workspace
    ws = wm.get_workspace()
    wsl_path = ws.get("wsl_path")
    health["workspace_set"] = bool(wsl_path)
    health["details"]["workspace_path"] = wsl_path
    _dbg(f"SESSION HEALTH: workspace -> {bool(wsl_path)}")

    # bridge state
    health["bridge_state_ok"] = (
        health["tmux_session"]
        and _current_session_id is not None
        and len(oc_procs) > 0
    )
    health["details"]["bridge_session_id"] = _current_session_id

    _dbg(f"SESSION HEALTH: complete -> tmux={health['tmux_session']} "
         f"opencode={health['opencode_running']} "
         f"workspace={health['workspace_set']} "
         f"bridge_ok={health['bridge_state_ok']}")
    return health


# ── Stale-state recovery (idempotent, safe to run repeatedly) ────────────────


def _recover_env():
    """Recovery pass: clean up stale tmux sessions, orphaned opencode
    processes, and bridge state before creating a new session.

    Idempotent — safe to call multiple times.
    """
    _dbg("SESSION RECOVERY: starting")
    cleaned: dict = {"tmux": False, "opencode": False}

    # 1. Stale tmux session
    has_tmux = _tmux(f"has-session -t {TMUX_SESSION_NAME}")[2] == 0
    _dbg(f"SESSION RECOVERY: tmux exists={has_tmux}")
    if has_tmux:
        _dbg("SESSION RECOVERY: killing stale tmux session")
        _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
        time.sleep(0.5)
        still = _tmux(f"has-session -t {TMUX_SESSION_NAME}")[2] == 0
        if still:
            _dbg("SESSION RECOVERY: retrying tmux kill")
            _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
            time.sleep(0.5)
        cleaned["tmux"] = True
    else:
        _dbg("SESSION RECOVERY: no stale tmux session")

    # 2. Orphaned opencode processes (not inside our tmux)
    oc_procs = _find_opencode_processes()
    if oc_procs:
        _dbg(f"SESSION RECOVERY: killing {len(oc_procs)} orphaned opencode process(es)")
        for proc in oc_procs:
            _kill_process(proc["pid"], proc.get("cmd", ""))
        cleaned["opencode"] = True
    else:
        _dbg("SESSION RECOVERY: no orphaned opencode processes")

    # 3. Reset bridge state unconditionally
    global _current_session_id, _session_started_at
    old_sid = _current_session_id
    _current_session_id = None
    _session_started_at = None
    if old_sid is not None:
        _dbg(f"SESSION RECOVERY: cleared stale bridge session_id={old_sid}")

    # 4. Clear any in-flight prompt state
    _reset_prompt_state()

    _dbg(f"SESSION RECOVERY: complete (tmux={cleaned['tmux']} opencode={cleaned['opencode']})")


def _reset_prompt_state():
    """Safely clear any in-flight prompt state."""
    global _prompt_state
    with _prompt_lock:
        if _prompt_state.get("running"):
            _dbg(f"SESSION RECOVERY: clearing in-flight prompt {_prompt_state.get('prompt_id')}")
        _prompt_state = {}


# ── Verified shutdown (stops and verifies cleanup) ─────────────────────────


def _verified_shutdown() -> dict:
    """Shut down the managed session with verification.

    1. Kill tmux session (with retry)
    2. Verify tmux is dead
    3. Kill orphaned opencode processes
    4. Clear bridge state
    """
    global _current_session_id, _session_started_at
    sid = _current_session_id
    _dbg("SESSION SHUTDOWN: starting")

    # Step A — kill tmux session
    _dbg("SESSION SHUTDOWN: killing tmux session")
    _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
    time.sleep(0.5)

    # Step B — verify tmux is gone, retry up to 3×
    for attempt in range(3):
        alive = _tmux(f"has-session -t {TMUX_SESSION_NAME}")[2] == 0
        _dbg(f"SESSION SHUTDOWN: tmux alive check #{attempt + 1}: alive={alive}")
        if not alive:
            break
        _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
        time.sleep(0.5)

    # Step C — kill orphaned opencode processes
    oc_procs = _find_opencode_processes()
    if oc_procs:
        _dbg(f"SESSION SHUTDOWN: killing {len(oc_procs)} orphaned opencode process(es)")
        for proc in oc_procs:
            _kill_process(proc["pid"], proc.get("cmd", ""))
    else:
        _dbg("SESSION SHUTDOWN: no orphaned opencode processes")

    # Step D — clear bridge state and in-flight prompts
    _current_session_id = None
    _session_started_at = None
    _reset_prompt_state()
    _dbg("SESSION SHUTDOWN: complete")

    return {"success": True, "session_id": sid}


def _session_export(session_id: str) -> dict | None:
    stdout, stderr, rc = _opencode_cli("export", session_id)
    if rc != 0 or not stdout:
        _dbg(f"_session_export({session_id}): rc={rc} stdout_empty={not stdout} stderr={stderr!r}")
        return None

    raw_size = len(stdout)
    _dbg(f"_session_export({session_id}): raw_size={raw_size}")

    # Trim "Exporting session..." header line if present
    lines = stdout.split("\n")
    if lines and lines[0].startswith("Exporting session"):
        stdout = "\n".join(lines[1:])

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        pos = e.pos
        context_before = stdout[max(0, pos - 200):pos]
        context_after = stdout[pos:pos + 200]
        tail = stdout[-1000:]
        _dbg(f"_session_export({session_id}): JSON decode error: {e}")
        _dbg(f"_session_export({session_id}): error_position={pos} raw_size={raw_size}")
        _dbg(f"_session_export({session_id}): context_before={context_before[-200:]!r}")
        _dbg(f"_session_export({session_id}): context_after={context_after[:200]!r}")
        _dbg(f"_session_export({session_id}): tail={tail!r}")
        return None

    info = data.get("info", {})
    raw_messages = data.get("messages", [])
    norm = _normalize_messages(raw_messages)
    msg_count = len(norm)
    _dbg(f"_session_export({session_id}): {msg_count} messages, roles={[m['role'] for m in norm]}")
    return {
        "session_id": info.get("id"),
        "title": info.get("title"),
        "slug": info.get("slug"),
        "workspace": info.get("directory"),
        "agent": info.get("agent"),
        "model": info.get("model"),
        "tokens": info.get("tokens"),
        "cost": info.get("cost"),
        "time": info.get("time"),
        "messages": norm,
        "source": "opencode",
    }


class TmuxSession:

    @property
    def active(self) -> bool:
        return _tmux(f"has-session -t {TMUX_SESSION_NAME}")[2] == 0

    # ── lifecycle --------------------------------------------------------

    def start(self, session_id: str | None = None) -> dict:
        global _current_session_id, _session_started_at

        # Recovery pass — clean stale state so startup never fails
        # due to incomplete previous cleanup.
        _recover_env()

        if not _ensure_tmux():
            return {
                "success": False,
                "error": (
                    "tmux is required but not found. "
                    "Install it manually (apt install tmux) or "
                    "ensure 'command -v tmux' succeeds in the execution environment."
                ),
            }

        ws = wm.get_workspace()
        wsl_path = ws.get("wsl_path")
        if not wsl_path:
            return {
                "success": False,
                "error": "No workspace set. Set a workspace first.",
            }

        _tmux("set -g history-limit 50000 2>/dev/null")

        if not session_id:
            if not platform.check_command(config.OPENCODE_COMMAND):
                return {
                    "success": False,
                    "error": (
                        f"OpenCode ({config.OPENCODE_COMMAND}) not found. "
                        f"Install it or ensure 'command -v {config.OPENCODE_COMMAND}' "
                        f"succeeds in the execution environment."
                    ),
                }
            session_id = _create_session(cwd=wsl_path)
            if not session_id:
                return {
                    "success": False,
                    "error": (
                        "Failed to create OpenCode session. "
                        "Check bridge server logs for details."
                    ),
                }

        opencode_cmd = (
            f"{_opencode_cmd()} --session {shlex.quote(session_id)} {shlex.quote(wsl_path)}"
        )
        create_out = _tmux(
            f"new-session -d -s {TMUX_SESSION_NAME} {shlex.quote(opencode_cmd)}"
        )

        if create_out[2] != 0:
            return {
                "success": False,
                "error": (
                    f"Failed to create tmux session: "
                    f"{create_out[1][:200] or 'unknown error'}"
                ),
            }

        if not _wait_for_opencode_ready():
            if not self.active:
                return {
                    "success": False,
                    "error": "Session died before opencode became ready",
                }
            _dbg("start: proceeding even though opencode prompt not detected")

        _current_session_id = session_id
        _session_started_at = time.monotonic()

        return {
            "success": True,
            "session_id": session_id,
            "session_name": TMUX_SESSION_NAME,
        }

    def stop(self) -> dict:
        return _verified_shutdown()

    @staticmethod
    def _extract_new(before: str, after: str) -> str:
        if after.startswith(before):
            return after[len(before):]
        idx = after.find(before)
        if idx >= 0:
            return after[idx + len(before):]
        return after

    # ── status / info ----------------------------------------------------

    def status(self) -> dict:
        active = self.active
        uptime = None
        if active and _session_started_at:
            uptime = time.monotonic() - _session_started_at
        return {
            "active": active,
            "session_id": _current_session_id,
            "uptime": uptime,
        }

    def pane_preview(self, max_lines: int = 5) -> str:
        if not self.active:
            return ""
        content = _capture_pane()
        if not content.strip():
            return ""
        lines = content.rstrip("\n").split("\n")
        last = "\n".join(lines[-max_lines:])
        return strip_ansi(last)

    # ── terminal ---------------------------------------------------------

    def open_terminal(self) -> dict:
        _dbg(f"TmuxSession.open_terminal: active={self.active} TMUX_SESSION_NAME={TMUX_SESSION_NAME!r}")
        if not self.active:
            _dbg("TmuxSession.open_terminal: no active session")
            return {
                "success": False,
                "error": "No active session to attach to.",
            }

        result = platform.open_terminal(TMUX_SESSION_NAME)
        _dbg(f"TmuxSession.open_terminal: result={result}")
        return result


# ── module-level singleton ------------------------------------------------

_active = TmuxSession()


def get_active() -> TmuxSession:
    return _active


async def start_session(session_id: str | None = None) -> dict:
    # Idempotent: start() runs its own recovery pass, so calling
    # stop() here is redundant but harmless.  Keep it for backward
    # compatibility — the recovery pass inside start() handles
    # everything that stop() used to do.
    return _active.start(session_id)


async def stop_session() -> dict:
    # Idempotent: stop() does verification and recovery.
    # Calling it with nothing to stop is safe.
    return _active.stop()


def get_session_status() -> dict:
    return _active.status()


def open_terminal() -> dict:
    return _active.open_terminal()


# ── background prompt processing (via tmux send-keys + capture-pane) --------

_prompt_state: dict = {}
_prompt_lock = threading.Lock()


def start_prompt_background(prompt: str, mode: str = "summary") -> str:
    global _prompt_state
    prompt_id = uuid.uuid4().hex[:8]
    _dbg(f"PROMPT[{prompt_id}] created mode={mode} prompt={prompt[:60]!r}")

    has_sess_t0 = time.monotonic()
    has_sess_ok = _tmux(f"has-session -t {TMUX_SESSION_NAME}")[2] == 0
    _dbg(f"PROMPT[{prompt_id}] has-session: {has_sess_ok} ({time.monotonic()-has_sess_t0:.3f}s)")
    if not has_sess_ok:
        with _prompt_lock:
            _prompt_state = {
                "prompt_id": prompt_id,
                "running": False,
                "done": True,
                "result": None,
                "error": "No active tmux session. Start a session first.",
                "mode": mode,
            }
        return prompt_id

    def _is_session_alive() -> bool:
        return _tmux(f"has-session -t {TMUX_SESSION_NAME}")[2] == 0

    def _run():
        global _prompt_state
        completion_reason = None
        try:
            _dbg(f"PROMPT[{prompt_id}] queued")

            # 1. Send prompt into the running opencode TUI
            send_t0 = time.monotonic()
            escaped = _escape_single_quotes(prompt)
            _, stderr, rc = _tmux(
                f"send-keys -t {TMUX_SESSION_NAME} '{escaped}' Enter"
            )
            send_elapsed = time.monotonic() - send_t0
            _dbg(f"PROMPT[{prompt_id}] send-keys rc={rc} took={send_elapsed*1000:.0f}ms")
            if rc != 0:
                completion_reason = "send-keys-failed"
                _dbg(f"PROMPT[{prompt_id}] send-keys-failed stderr={stderr!r}")
                with _prompt_lock:
                    _prompt_state["error"] = stderr or "tmux send-keys failed"
                    _prompt_state["running"] = False
                    _prompt_state["done"] = True
                return

            # 2. Poll capture-pane until stability or session death.
            #    NO WALL-CLOCK TIMEOUT.
            last_extracted = ""
            stable_since: float | None = None
            changed = False
            saw_prompt_char = False
            session_alive = True
            poll_count = 0
            poll_t0 = time.monotonic()
            last_progress_report = 0.0

            while True:
                time.sleep(0.25)
                poll_count += 1

                # Check session health every 20 polls (~5s)
                if poll_count % 20 == 0:
                    if not _is_session_alive():
                        completion_reason = "session-died"
                        session_alive = False
                        _dbg(f"PROMPT[{prompt_id}] session-died (poll={poll_count} elapsed={time.monotonic()-poll_t0:.1f}s)")
                        break

                cap_t0 = time.monotonic()
                current = _capture_pane_with_scrollback()
                cap_elapsed = time.monotonic() - cap_t0
                capture_size = len(current)
                last_line = (current.strip().split("\n") or [""])[-1][:120]
                extracted = _extract_response(current, prompt)
                extracted_len = len(extracted)
                new_lines = extracted_len - len(last_extracted)

                _dbg(f"PROMPT[{prompt_id}] capture size={capture_size} last={last_line!r} extracted={extracted_len} new={new_lines} stable={stable_since is not None} changed={changed} saw_prompt={'▣' in current} cap_took={cap_elapsed*1000:.0f}ms")

                # Track whether ▣ prompt character has reappeared (signals completion)
                if "▣" in current:
                    saw_prompt_char = True

                is_meaningful = extracted_len >= 20

                if extracted == last_extracted:
                    if not changed:
                        pass
                    elif stable_since is None:
                        stable_since = time.time()
                        _dbg(f"PROMPT[{prompt_id}] stable start (poll={poll_count}, elapsed={time.monotonic()-poll_t0:.1f}s, extracted={extracted[:80]!r})")
                    elif time.time() - stable_since >= 1.5:
                        if is_meaningful or saw_prompt_char:
                            completion_reason = "stable-complete" if is_meaningful else "prompt-char-seen"
                            _dbg(f"PROMPT[{prompt_id}] completion_reason={completion_reason} (poll={poll_count}, elapsed={time.monotonic()-poll_t0:.1f}s)")
                            break
                else:
                    last_extracted = extracted
                    stable_since = None
                    if extracted_len >= 20:
                        changed = True
                    if extracted:
                        with _prompt_lock:
                            _prompt_state["progress"] = extracted
                    elapsed = time.monotonic() - poll_t0
                    if elapsed - last_progress_report >= 30.0:
                        last_progress_report = elapsed
                        _dbg(f"PROMPT[{prompt_id}] progress (poll={poll_count}, elapsed={elapsed:.1f}s, extracted_len={extracted_len})")

            # 3. Final result — use opencode export for ground truth
            elapsed = time.monotonic() - poll_t0
            result = last_extracted
            export_success = False
            sid = _current_session_id

            # Only attempt export if session is alive — dead sessions won't export
            if sid and session_alive:
                _dbg(f"PROMPT[{prompt_id}] export start session={sid}")
                exported = _session_export(sid)
                max_retries = 10
                for retry in range(max_retries):
                    if exported is not None:
                        export_success = True
                        break
                    _dbg(f"PROMPT[{prompt_id}] export retry {retry + 1}/{max_retries} session={sid}")
                    time.sleep(2.0)
                    exported = _session_export(sid)

                if export_success:
                    msgs = exported.get("messages", [])
                    for m in reversed(msgs):
                        if m.get("role") == "assistant" and m.get("content", "").strip():
                            reply = m["content"].strip()
                            if len(reply) >= len(result):
                                result = reply
                                _dbg(f"PROMPT[{prompt_id}] export reply (len={len(result)}) replaces pane (len={len(last_extracted)})")
                            else:
                                _dbg(f"PROMPT[{prompt_id}] keeping pane (len={len(result)}) > export reply (len={len(reply)})")
                            break

            if completion_reason is None:
                completion_reason = "unknown"

            _dbg(f"PROMPT[{prompt_id}] done elapsed={elapsed:.1f}s polls={poll_count} result_len={len(result)} reason={completion_reason} export_ok={export_success}")

            with _prompt_lock:
                _prompt_state["running"] = False
                _prompt_state["done"] = True
                _prompt_state["completion_reason"] = completion_reason
                _prompt_state["export_success"] = export_success
                _prompt_state["result"] = result or None
                _prompt_state.pop("progress", None)

        except Exception as e:
            completion_reason = "exception"
            _dbg(f"PROMPT[{prompt_id}] exception: {e}")
            with _prompt_lock:
                _prompt_state["completion_reason"] = completion_reason
                _prompt_state["error"] = str(e)
                _prompt_state["running"] = False
                _prompt_state["done"] = True

    with _prompt_lock:
        _dbg(f"PROMPT[{prompt_id}] started")
        _prompt_state = {
            "prompt_id": prompt_id,
            "running": True,
            "done": False,
            "progress": "",
            "result": None,
            "error": None,
            "mode": mode,
        }

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return prompt_id


def get_prompt_status(prompt_id: str) -> dict:
    with _prompt_lock:
        if _prompt_state.get("prompt_id") != prompt_id:
            _dbg(f"PROMPT[{prompt_id}] NOT FOUND, current={_prompt_state.get('prompt_id')}")
            return {"error": "prompt_id not found"}
        state = dict(_prompt_state)
        done = state.get('done')
        running = state.get('running')
        result_len = len(state.get('result', '') or '')
        _dbg(f"PROMPT[{prompt_id}] status done={done} running={running} result_len={result_len}")
        return state
