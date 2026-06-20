import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time

import config
import workspace_manager as wm
from platforms.factory import get_platform

platform = get_platform()

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
_current_session_id: str | None = None
_session_started_at: float | None = None

_debug_enabled = config.DEBUG_OUTPUT
_debug_lock = threading.Lock()


def _tmux_session_name() -> str:
    return config.TMUX_SESSION_NAME


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
    return shutil.which("tmux") is not None


def _capture_pane(scrollback: int = 0) -> str:
    sname = _tmux_session_name()
    if scrollback > 0:
        stdout, _, _ = _tmux(
            f"capture-pane -t {sname} -p -S -{scrollback}"
        )
    else:
        stdout, _, _ = _tmux(f"capture-pane -t {sname} -p")
    return strip_ansi(stdout or "")


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
    fd, tmp_path = tempfile.mkstemp(suffix=".json", dir="/tmp")
    os.close(fd)
    os.chmod(tmp_path, 0o666)
    try:
        result = platform.run(
            f"cd /tmp && {_opencode_cmd()} {inner} >{shlex.quote(tmp_path)} 2>/dev/null",
            timeout=30,
        )
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                stdout = f.read()
        except (OSError, UnicodeDecodeError):
            stdout = ""
        return stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except FileNotFoundError:
        return "", platform.env_not_found_message, -1
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _escape_single_quotes(text: str) -> str:
    return text.replace("'", "'\\''")


def _capture_pane_full_history() -> str:
    sname = _tmux_session_name()
    stdout, _, _ = _tmux(
        f"capture-pane -t {sname} -p -S -"
    )
    return strip_ansi(stdout or "")


def _opencode_cmd() -> str:
    cmd = config.OPENCODE_COMMAND
    if '/' not in cmd:
        resolved = shutil.which(cmd)
        if resolved:
            return resolved
    return cmd


def _create_session(timeout: int = 120, cwd: str | None = None) -> str | None:
    opencode = _opencode_cmd()
    inner = (
        f"{opencode} run --format json "
        f"{shlex.quote('.')}"
    )
    try:
        result = platform.run(inner, timeout=timeout, cwd=cwd)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        _dbg(f"_create_session: rc={result.returncode} stdout_len={len(stdout)} "
             f"stderr_len={len(stderr)} cwd={cwd}")
        if stdout:
            _dbg(f"_create_session: stdout preview: {stdout[:500]!r}")
        if stderr:
            _dbg(f"_create_session: stderr: {stderr[:500]!r}")
        for line in stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                _dbg(f"_create_session: non-JSON line: {line[:200]!r}")
                continue
            sid = event.get("sessionID")
            etype = event.get("type")
            if etype == "step_start" and sid:
                return sid
            if etype == "error" and sid:
                err_msg = str(event.get("error", {}).get("data", {}).get("message", ""))
                _dbg(f"_create_session: session {sid} created but API error: {err_msg}")
                return sid
        _dbg("_create_session: no sessionID found in output")
        return None
    except subprocess.TimeoutExpired:
        _dbg(f"_create_session: timed out after {timeout}s")
        return None
    except Exception as exc:
        _dbg(f"_create_session: exception: {exc}")
        return None


def _dbg(msg: str):
    if is_debug_enabled():
        print(f"[DEBUG tmux_session] {msg}", flush=True)


class TmuxSession:

    @property
    def active(self) -> bool:
        return _tmux(f"has-session -t {_tmux_session_name()}")[2] == 0

    def start(self, session_id: str | None = None) -> dict:
        global _current_session_id, _session_started_at

        sname = _tmux_session_name()

        if not shutil.which("tmux"):
            return {
                "success": False,
                "error": (
                    "tmux is required but not found. "
                    "Install it manually and try again."
                ),
            }

        ws = wm.get_workspace()
        workspace_path = ws.get("workspace")
        if not workspace_path:
            return {
                "success": False,
                "error": "No workspace set. Set a workspace first.",
            }

        _tmux("set -g history-limit 50000 2>/dev/null")

        if not session_id:
            if not shutil.which(config.OPENCODE_COMMAND):
                return {
                    "success": False,
                    "error": (
                        f"OpenCode ({config.OPENCODE_COMMAND}) not found. "
                        "It should be installed in the container."
                    ),
                }
            session_id = _create_session(cwd=workspace_path)
            if not session_id:
                return {
                    "success": False,
                    "error": (
                        "Failed to create OpenCode session. "
                        "Check bridge server logs for details."
                    ),
                }

        opencode_cmd = (
            f"{_opencode_cmd()} --session {shlex.quote(session_id)} {shlex.quote(workspace_path)}"
        )
        # Create session with a shell first, then send the command.
        # This way the shell keeps the session alive after opencode exits.
        create_out = _tmux(f"new-session -d -s {sname}")
        if create_out[2] != 0:
            return {
                "success": False,
                "error": (
                    f"Failed to create tmux session: "
                    f"{create_out[1][:200] or 'unknown error'}"
                ),
            }
        escaped = _escape_single_quotes(opencode_cmd)
        _tmux(f"send-keys -t {sname} '{escaped}' Enter")

        _current_session_id = session_id
        _session_started_at = time.monotonic()

        return {
            "success": True,
            "session_id": session_id,
            "session_name": sname,
        }

    def stop(self) -> dict:
        global _current_session_id, _session_started_at
        sid = _current_session_id
        sname = _tmux_session_name()

        _tmux(f"kill-session -t {sname} 2>/dev/null")

        _current_session_id = None
        _session_started_at = None
        return {"success": True, "session_id": sid}

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

    def open_terminal(self) -> dict:
        _dbg(f"TmuxSession.open_terminal: active={self.active}")
        if not self.active:
            _dbg("TmuxSession.open_terminal: no active session")
            return {
                "success": False,
                "error": "No active session to attach to.",
            }

        result = platform.open_terminal(_tmux_session_name())
        _dbg(f"TmuxSession.open_terminal: result={result}")
        return result


_active = TmuxSession()


def get_active() -> TmuxSession:
    return _active


async def start_session(session_id: str | None = None) -> dict:
    return _active.start(session_id)


async def stop_session() -> dict:
    return _active.stop()


def get_session_status() -> dict:
    return _active.status()


def open_terminal() -> dict:
    return _active.open_terminal()


def start_prompt_background(prompt: str, mode: str = "summary") -> dict:
    sname = _tmux_session_name()
    has_sess_ok = _tmux(f"has-session -t {sname}")[2] == 0
    if not has_sess_ok:
        return {"success": False, "error": "No active tmux session. Start a session first."}

    escaped = _escape_single_quotes(prompt)
    _, stderr, rc = _tmux(
        f"send-keys -t {sname} '{escaped}' Enter"
    )
    if rc != 0:
        return {"success": False, "error": stderr or "tmux send-keys failed"}

    _dbg(f"send-prompt: prompt={prompt[:60]!r} sent via tmux")
    return {"success": True}


def _extract_part_text(part: dict) -> str:
    ptype = part.get("type", "")
    if ptype == "text":
        return part.get("text", "") or ""
    if ptype == "reasoning":
        return part.get("text", "") or ""
    if ptype == "tool":
        state = part.get("state", {})
        outp = state.get("output")
        if outp is None:
            return ""
        if isinstance(outp, str):
            return outp
        if isinstance(outp, dict):
            content = outp.get("content")
            if isinstance(content, str):
                return content
        if isinstance(outp, list):
            chunks: list[str] = []
            for item in outp:
                if isinstance(item, dict):
                    for key in ("output", "content", "text", "message"):
                        val = item.get(key)
                        if isinstance(val, str) and val.strip():
                            chunks.append(val)
                            break
                elif isinstance(item, str):
                    chunks.append(item)
            return "\n".join(chunks).strip()
        return ""
    return ""


def _extract_turn_content(collected_messages: list) -> str:
    chunks: list[str] = []
    for msg in collected_messages:
        parts = msg.get("parts", [])
        for part in parts:
            text = _extract_part_text(part)
            if text:
                chunks.append(text)
    return "\n\n".join(chunks).strip()


def get_latest_response(session_id: str) -> dict:
    stdout, stderr, rc = _opencode_cli("export", session_id)
    if rc != 0 or not stdout:
        _dbg(f"get_latest_response({session_id}): export failed rc={rc} empty={not stdout}")
        return {
            "success": False, "response": None, "message_count": 0, "collected_count": 0,
            "error": "Failed to export session. Session may not exist or OpenCode may not be ready.",
        }

    lines = stdout.split("\n")
    if lines and lines[0].startswith("Exporting session"):
        stdout = "\n".join(lines[1:])

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        _dbg(f"get_latest_response({session_id}): JSON decode error: {e}")
        return {
            "success": False, "response": None, "message_count": 0, "collected_count": 0,
            "error": "Export JSON parse failed.",
        }

    raw_messages: list = data.get("messages", [])
    total_count = len(raw_messages)
    _dbg(f"get_latest_response({session_id}): total exported messages={total_count}")

    if total_count == 0:
        return {
            "success": False, "response": None, "message_count": 0, "collected_count": 0,
            "error": "Session has no messages yet.",
        }

    last_user_idx = -1
    for i, m in enumerate(raw_messages):
        role = m.get("info", {}).get("role", m.get("role"))
        if role == "user":
            last_user_idx = i

    _dbg(f"get_latest_response({session_id}): latest user message index={last_user_idx}")

    if last_user_idx == -1:
        return {
            "success": False, "response": None, "message_count": total_count, "collected_count": 0,
            "error": "No user messages found in session.",
        }

    collected: list = []
    for i in range(last_user_idx + 1, total_count):
        m = raw_messages[i]
        role = m.get("info", {}).get("role", m.get("role"))
        if role == "user":
            _dbg(f"get_latest_response({session_id}): next user message at index {i}, stopping")
            break
        collected.append(m)

    collected_count = len(collected)
    assistant_count = sum(
        1 for m in collected
        if m.get("info", {}).get("role", m.get("role")) == "assistant"
    )
    _dbg(f"get_latest_response({session_id}): collected {collected_count} messages "
         f"({assistant_count} assistant) after user prompt at idx {last_user_idx}")

    if not collected:
        return {
            "success": False, "response": None,
            "message_count": total_count, "collected_count": 0,
            "error": "No assistant response yet. OpenCode may still be processing.",
        }

    full_response = _extract_turn_content(collected)
    response_len = len(full_response)
    _dbg(f"get_latest_response({session_id}): assembled response length={response_len}")

    return {
        "success": True,
        "response": full_response,
        "message_count": total_count,
        "collected_count": collected_count,
        "error": None,
    }
