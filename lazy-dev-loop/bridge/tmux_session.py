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
    if config.DEBUG_OUTPUT:
        print(f"[DEBUG tmux_session] {msg}", flush=True)


def _session_export(session_id: str) -> dict | None:
    stdout, _, rc = _opencode_cli("export", session_id)
    if rc != 0 or not stdout:
        _dbg(f"_session_export({session_id}): rc={rc} stdout_empty={not stdout}")
        return None
    lines = stdout.split("\n")
    if lines and lines[0].startswith("Exporting session"):
        stdout = "\n".join(lines[1:])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        _dbg(f"_session_export({session_id}): JSON decode error: {e}")
        return None
    info = data.get("info", {})
    raw_messages = data.get("messages", [])
    norm = _normalize_messages(raw_messages)
    _dbg(f"_session_export({session_id}): {len(norm)} messages, roles={[m['role'] for m in norm]}")
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
        _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
        time.sleep(0.5)

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
        global _current_session_id, _session_started_at
        _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
        time.sleep(0.5)
        if self.active:
            _tmux(f"kill-session -t {TMUX_SESSION_NAME}")
            time.sleep(0.5)
        sid = _current_session_id
        _current_session_id = None
        _session_started_at = None
        return {
            "success": True,
            "session_id": sid,
        }

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
    if _active.active:
        _active.stop()
    return _active.start(session_id)


async def stop_session() -> dict:
    _active.stop()
    return {"success": True}


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
    _dbg(f"start_prompt_background: prompt_id={prompt_id} mode={mode} prompt={prompt[:60]!r}")

    has_sess_t0 = time.monotonic()
    has_sess_ok = _tmux(f"has-session -t {TMUX_SESSION_NAME}")[2] == 0
    _dbg(f"start_prompt_background: has-session check took {time.monotonic()-has_sess_t0:.3f}s, result={has_sess_ok}")
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

    def _run():
        global _prompt_state
        try:
            _dbg(f"tmux prompt: send-keys -t {TMUX_SESSION_NAME} '{prompt}'")

            # 1. Send prompt into the running opencode TUI
            escaped = _escape_single_quotes(prompt)
            _, stderr, rc = _tmux(
                f"send-keys -t {TMUX_SESSION_NAME} '{escaped}' Enter"
            )
            if rc != 0:
                with _prompt_lock:
                    _prompt_state["error"] = stderr or "tmux send-keys failed"
                    _prompt_state["running"] = False
                    _prompt_state["done"] = True
                return

            # 2. Poll capture-pane until the extracted response stabilizes.
            #    Compare extracted response text (immune to terminal client noise)
            #    instead of raw pane content.  Require at least one non-empty
            #    extracted response before declaring stability.
            deadline = time.time() + 300
            last_extracted = ""
            stable_since: float | None = None
            changed = False
            saw_prompt_char = False
            poll_count = 0
            poll_t0 = time.monotonic()

            while time.time() < deadline:
                time.sleep(0.25)
                poll_count += 1
                current = _capture_pane_with_scrollback()
                extracted = _extract_response(current, prompt)

                # Track whether ▣ prompt character has reappeared (signals completion)
                if "▣" in current:
                    saw_prompt_char = True

                # Only consider non-trivial extracted text as meaningful content
                is_meaningful = len(extracted) >= 20

                if extracted == last_extracted:
                    # Stability detected: content unchanged between polls
                    if not changed:
                        # Still waiting for first meaningful content
                        pass
                    elif stable_since is None:
                        stable_since = time.time()
                        _dbg(f"_run: stable start (poll={poll_count}, elapsed={time.monotonic()-poll_t0:.1f}s, extracted={extracted[:60]!r})")
                    elif time.time() - stable_since >= 1.5:
                        # Only complete if we have meaningful content OR ▣ reappeared
                        if is_meaningful or saw_prompt_char:
                            _dbg(f"_run: stability achieved (poll={poll_count}, elapsed={time.monotonic()-poll_t0:.1f}s)")
                            break
                else:
                    last_extracted = extracted
                    stable_since = None
                    # Only mark as changed if content is meaningful
                    if len(extracted) >= 20:
                        changed = True
                    # Update streaming progress even for partial content
                    if extracted:
                        with _prompt_lock:
                            _prompt_state["progress"] = extracted
                    if poll_count % 4 == 0:
                        _dbg(f"_run: content changed (poll={poll_count}, elapsed={time.monotonic()-poll_t0:.1f}s, extracted={extracted[:50]!r})")

            # 3. Final result — use opencode export for ground truth
            elapsed = time.monotonic() - poll_t0
            result = last_extracted

            # After completion, export the session for the definitive full response.
            # Pane extraction during generation only sees the visible 25-line window
            # (opencode is a full-screen TUI; tmux scrollback is empty), so the
            # extracted result may be only the last visible fragment.  The export
            # gives the complete assistant reply from opencode's internal data.
            sid = _current_session_id
            if sid:
                _dbg(f"_run: fetching export for session {sid}")
                exported = _session_export(sid)
                if exported:
                    msgs = exported.get("messages", [])
                    for m in reversed(msgs):
                        if m.get("role") == "assistant" and m.get("content", "").strip():
                            reply = m["content"].strip()
                            if len(reply) >= len(result):
                                result = reply
                                _dbg(f"_run: export reply (len={len(result)}) replaces pane extraction (len={len(last_extracted)})")
                            else:
                                _dbg(f"_run: keeping pane extraction (len={len(result)}) > export reply (len={len(reply)})")
                            break

            _dbg(f"_run: done (elapsed={elapsed:.1f}s, polls={poll_count}, result_len={len(result)}, result={result[:80]!r})")

            with _prompt_lock:
                _prompt_state["running"] = False
                _prompt_state["done"] = True
                _prompt_state["result"] = result or None
                _prompt_state.pop("progress", None)

        except Exception as e:
            _dbg(f"_run exception: {e}")
            with _prompt_lock:
                _prompt_state["error"] = str(e)
                _prompt_state["running"] = False
                _prompt_state["done"] = True

    with _prompt_lock:
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
            _dbg(f"get_prompt_status({prompt_id}): NOT FOUND, current={_prompt_state.get('prompt_id')}")
            return {"error": "prompt_id not found"}
        state = dict(_prompt_state)
        _dbg(f"get_prompt_status({prompt_id}): done={state.get('done')} running={state.get('running')} result_len={len(state.get('result','') or '')} error={state.get('error')}")
        return state
