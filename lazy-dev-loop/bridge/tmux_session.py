from collections.abc import Callable
import json
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time
import uuid

import config
import workspace_manager as wm

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
TMUX_SESSION_NAME = "lazy-dev-loop"


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


def check_tmux() -> bool:
    cmd = _wsl_cmd("command -v tmux")
    try:
        result = subprocess.run(cmd, capture_output=True, encoding='utf-8', timeout=10)
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False


def _wsl_cmd(inner: str) -> list[str]:
    flag = "-ic" if config.USE_INTERACTIVE_SHELL else "-lc"
    cmd = ["wsl.exe"]
    if config.WSL_DISTRO:
        cmd.extend(["-d", config.WSL_DISTRO])
    cmd.extend(["bash", flag, inner])
    return cmd


def _ensure_tmux() -> bool:
    if check_tmux():
        return True
    cmd = _wsl_cmd(
        "sudo apt-get update -qq && sudo apt-get install -y -qq tmux"
    )
    try:
        subprocess.run(cmd, capture_output=True, encoding='utf-8', timeout=120)
        return check_tmux()
    except Exception:
        return False


def _escape_single_quotes(text: str) -> str:
    return text.replace("'", "'\\''")


def _capture_pane() -> str:
    stdout, _, _ = _tmux(f"capture-pane -t {TMUX_SESSION_NAME} -p")
    return stdout or ""


def _tmux(tmux_args: str) -> tuple[str, str, int]:
    full = f"tmux {tmux_args}"
    cmd = _wsl_cmd(full)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding='utf-8',
            timeout=15,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except FileNotFoundError:
        return "", "wsl.exe not found", -1


def _opencode_cli(*args: str) -> tuple[str, str, int]:
    inner = " ".join(shlex.quote(a) for a in args)
    cmd = _wsl_cmd(f"cd /tmp && {config.OPENCODE_COMMAND} {inner} 2>/dev/null")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding='utf-8',
            timeout=30,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except FileNotFoundError:
        return "", "wsl.exe not found", -1


def _list_session_ids() -> set[str]:
    stdout, _, _ = _opencode_cli("session", "list")
    if not stdout:
        return set()
    return set(re.findall(r'ses_[a-zA-Z0-9]+', stdout))


def _session_list() -> list[dict]:
    stdout, _, rc = _opencode_cli("session", "list")
    if rc != 0 or not stdout:
        return []
    sessions = []
    for line in stdout.strip().split("\n")[2:]:
        if not line.strip():
            continue
        parts = line.strip().split(None, 1)
        sid = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        title = rest
        updated = ""
        if "  " in rest:
            idx = rest.rfind("  ")
            title = rest[:idx]
            updated = rest[idx:].strip()
            sessions.append({
                "session_id": sid,
                "title": title.strip(),
            "updated": updated,
            "source": "opencode",
        })
    return sessions


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

    def __init__(self):
        self.oc_session_id: str | None = None
        self.started_at: float | None = None
        self.prompt_count: int = 0
        self._last_capture: str = ""
        self.finished: bool = False

    @property
    def active(self) -> bool:
        return _tmux(f"has-session -t {TMUX_SESSION_NAME}")[2] == 0

    @property
    def uptime(self) -> float | None:
        if self.started_at and self.active and not self.finished:
            return time.time() - self.started_at
        return None

    # ── lifecycle --------------------------------------------------------

    def start(self, session_id: str | None = None) -> dict:
        if not _ensure_tmux():
            return {
                "success": False,
                "error": (
                    "tmux is required but not found in WSL. "
                    "Install it manually (apt install tmux) or "
                    "ensure 'command -v tmux' succeeds inside WSL."
                ),
            }

        ws = wm.get_workspace()
        wsl_path = ws.get("wsl_path")
        if not wsl_path:
            return {
                "success": False,
                "error": "No workspace set. Set a workspace first.",
            }

        _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
        time.sleep(0.5)

        flag = ""
        if session_id:
            flag = f"--session {shlex.quote(session_id)}"

        opencode_cmd = (
            f"cd {shlex.quote(wsl_path)} && "
            f"{config.OPENCODE_COMMAND} {flag}".strip()
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

        time.sleep(3)

        if not self.active:
            return {
                "success": False,
                "error": f"Session died after creation: {create_out[1][:200]}",
            }

        if session_id:
            self.oc_session_id = session_id
        else:
            pane = _capture_pane()
            match = re.search(r'ses_[a-zA-Z0-9]+', pane)
            self.oc_session_id = match.group(0) if match else None

        self.started_at = time.time()
        self.prompt_count = 0
        self.finished = False
        self._last_capture = _capture_pane()

        return {
            "success": True,
            "session_id": self.oc_session_id,
            "session_name": TMUX_SESSION_NAME,
        }

    def stop(self) -> dict:
        _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
        time.sleep(0.5)
        if self.active:
            _tmux(f"kill-session -t {TMUX_SESSION_NAME}")
            time.sleep(0.5)
        self.finished = True
        return {
            "success": True,
            "session_id": self.oc_session_id,
        }

    # ── prompt -----------------------------------------------------------

    def send_prompt(self, prompt: str, mode: str = "summary") -> dict:
        if not self.active:
            return {
                "success": False,
                "error": "Session is not active. Start a session first.",
                "output": "",
            }

        before = _capture_pane()
        escaped = _escape_single_quotes(prompt)
        _tmux(f"send-keys -t {TMUX_SESSION_NAME} '{escaped}' Enter")

        raw_output = self._wait_for_stable_output(before)

        self.prompt_count += 1
        self._last_capture = _capture_pane()

        if mode == "summary":
            clean = _extract_assistant_response()
            if clean:
                return {"success": True, "output": clean, "source": "export"}
            final_pane = _capture_pane()
            filtered = _heuristic_filter(strip_ansi(final_pane))
            if filtered:
                return {"success": True, "output": filtered, "source": "filtered"}

        return {"success": True, "output": raw_output.strip(), "source": "raw"}

    def _wait_for_stable_output(
        self,
        before: str,
        on_progress: Callable[[str], None] | None = None,
        timeout: int | None = None,
    ) -> str:
        max_idle = timeout or config.RUN_TIMEOUT
        deadline = time.time() + max_idle
        clean_before = strip_ansi(before)
        clean_last = clean_before
        stable_since: float | None = None

        while time.time() < deadline:
            time.sleep(0.25)
            current = _capture_pane()
            clean_current = strip_ansi(current)

            if on_progress and clean_current != clean_before:
                new = self._extract_new(clean_before, clean_current)
                if new:
                    on_progress(_heuristic_filter(new.strip()))

            if clean_current == clean_last:
                if stable_since is not None and time.time() - stable_since >= 3.0:
                    break
            else:
                clean_last = clean_current
                stable_since = time.time()
                deadline = max(deadline, time.time() + max_idle)

        return self._extract_new(clean_before, clean_last)

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
        wsl_workspace = wm.get_workspace()
        return {
            "active": active and not self.finished,
            "session_id": self.oc_session_id,
            "session_name": TMUX_SESSION_NAME,
            "uptime": self.uptime,
            "started_at": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.started_at))
                if self.started_at
                else None
            ),
            "prompt_count": self.prompt_count,
            "workspace": wsl_workspace,
            "source": "opencode",
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
        if not self.active:
            return {
                "success": False,
                "error": "No active session to attach to.",
            }

        flag = "-ic" if config.USE_INTERACTIVE_SHELL else "-lc"
        inner = f"tmux attach -t {TMUX_SESSION_NAME}"
        cmd = ["wsl.exe"]
        if config.WSL_DISTRO:
            cmd.extend(("-d", config.WSL_DISTRO))
        cmd.extend(("bash", flag, inner))

        try:
            creationflags = 0
            if hasattr(subprocess, "CREATE_NEW_CONSOLE"):
                creationflags = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(cmd, creationflags=creationflags)
            return {"success": True, "message": "Terminal launched"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ── module-level singleton ------------------------------------------------

_active = TmuxSession()


def get_active() -> TmuxSession:
    return _active


async def start_session(session_id: str | None = None) -> dict:
    if _active.active:
        if not _active.finished:
            return {
                "success": False,
                "error": "Session already active. Stop it first.",
            }
        _active.stop()
    return _active.start(session_id)


async def stop_session() -> dict:
    return _active.stop()


async def send_prompt(prompt: str, mode: str = "summary") -> dict:
    return _active.send_prompt(prompt, mode=mode)


def get_session_status() -> dict:
    return _active.status()


def open_terminal() -> dict:
    return _active.open_terminal()


def list_sessions() -> list[dict]:
    return _session_list()


def get_session(session_id: str) -> dict | None:
    return _session_export(session_id)


async def load_session(session_id: str) -> dict:
    if _active.active and not _active.finished:
        _active.stop()
    return _active.start(session_id=session_id)


def delete_session(session_id: str) -> dict:
    stdout, stderr, rc = _opencode_cli("session", "delete", session_id)
    if rc != 0:
        return {"success": False, "error": stderr or "Delete failed"}
    return {"success": True, "deleted": session_id}


# ── output filtering -------------------------------------------------------

_TUI_CHARS = set(
    "┌┐└┘├┤┬┴┼╒╕╘╛╞╡╪╓╖╙╜╟╢╫"
    "─═│║╔╗╚╝╠╣╦╩╬▀▄█▌▐░▒▓■●◦◌◆◇▶▷▸►▻"
)

_BORDER_ONLY_RE = re.compile(
    r'^[─═┌┐└┘├┤┬┴┼╒╕╘╛╞╡╪╓╖╙╜╟╢╫╔╗╚╝╠╣╦╩╬▀▄█▌▐░▒▓■●\s]+$',
)


def _heuristic_filter(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    dropped_lines = 0
    for line in lines:
        raw = line.strip()
        if not raw:
            continue

        if raw.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        if _BORDER_ONLY_RE.match(raw):
            dropped_lines += 1
            continue

        content = raw.strip("".join(_TUI_CHARS) + " \t>")

        if not content:
            dropped_lines += 1
            continue

        if re.match(r'^opencode\s+v?\d+', content, re.I):
            dropped_lines += 1
            continue
        if re.match(r'^opencode\s+\d+\.\d+', content, re.I):
            dropped_lines += 1
            continue

        if re.match(r'^[d\-lpsbc]\S{9}\s+\d+', content):
            dropped_lines += 1
            continue
        if re.match(r'^total\s+\d+', content, re.I):
            dropped_lines += 1
            continue

        first_word = content.split(None, 1)[0].lower().rstrip(":;")

        if first_word in ("read", "write", "shell", "search", "browse",
                          "edit", "delete", "create", "list", "move", "copy"):
            if len(content) < 60:
                dropped_lines += 1
                continue
        if first_word in ("file", "directory", "path"):
            if len(content) < 60:
                dropped_lines += 1
                continue
        if re.match(r'^v?\d+\.\d+', first_word):
            dropped_lines += 1
            continue
        if re.match(r'^\$?[\d.,]+', first_word) and re.match(r'^[\d.,]+$', first_word):
            dropped_lines += 1
            continue

        if content.startswith("Press ") or content.startswith("Type "):
            dropped_lines += 1
            continue

        out.append(content)

    result = "\n".join(out).strip()
    _dbg(f"_heuristic_filter: in_lines={len(lines)} dropped={dropped_lines} out_lines={len(out)} out_chars={len(result)}")
    return result


def _extract_assistant_response(session_id: str | None = None, max_attempts: int = 30) -> str | None:
    sid = session_id or _active.oc_session_id
    if not sid:
        _dbg("_extract_assistant_response: no session_id")
        return None

    _dbg(f"_extract_assistant_response: session={sid} max_attempts={max_attempts}")
    for i in range(max_attempts):
        time.sleep(0.5)
        data = _session_export(sid)
        if not data:
            _dbg(f"_extract_assistant_response: attempt {i} — no export data yet")
            continue
        messages = data.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "").strip()
                if content:
                    _dbg(f"_extract_assistant_response: found at attempt {i} ({len(content)} chars)")
                    return content
    _dbg(f"_extract_assistant_response: exhausted {max_attempts} attempts, no assistant content found")
    return None


# ── background prompt processing (via opencode run --format json) -----------

_prompt_state: dict = {}
_prompt_lock = threading.Lock()


def start_prompt_background(prompt: str, mode: str = "summary") -> str:
    """Run prompt via `opencode run --format json` subprocess.

    Reads structured JSON events from stdout — no tmux, no scraping,
    no heuristic filters.  The assistant text arrives in a single "text"
    event once the model finishes generating.
    """
    global _prompt_state
    prompt_id = uuid.uuid4().hex[:8]

    # Build command:  opencode run --format json [--continue] <prompt>
    # NOTE: Must use _wsl_cmd() so this works on Windows (where opencode lives in WSL)
    inner = f"{config.OPENCODE_COMMAND} run --format json"
    if _active.oc_session_id:
        inner += " --continue"
    inner += f" {shlex.quote(prompt)}"
    cmd = _wsl_cmd(inner)

    def _run():
        global _prompt_state, _active
        proc = None
        _raw_log = None
        try:
            _dbg(f"starting: {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding='utf-8',
            )

            text_parts: list[str] = []
            _raw_log_path = os.path.join(tempfile.gettempdir(), "opencode_raw_lines.log")
            _raw_log = open(_raw_log_path, "w", encoding='utf-8')
            _raw_log.write(f"START cmd={' '.join(cmd)}\n")

            for raw_line in proc.stdout:
                _raw_log.write(raw_line)
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")
                part_type = event.get("part", {}).get("type", "")
                part_keys = list(event.get("part", {}).keys()) if event.get("part") else []

                # Log every event type and its string content (for TUI leak diagnosis)
                all_texts = {}
                def _gather_strings(obj, path=""):
                    if isinstance(obj, str) and len(obj) > 5:
                        all_texts[path] = obj[:120]
                    elif isinstance(obj, dict):
                        for k, v in obj.items():
                            _gather_strings(v, f"{path}.{k}")
                    elif isinstance(obj, list):
                        for i, v in enumerate(obj):
                            _gather_strings(v, f"{path}[{i}]")
                _gather_strings(event)
                if event_type not in ("step_start", "step_finish") or any("▣" in v or "Build" in v or "OpenCode Zen" in v or "┃" in v for v in all_texts.values()):
                    for k, v in all_texts.items():
                        if len(v) >= 10 and not k.startswith(".part.tokens") and not k.startswith(".part.id"):
                            _dbg(f"  {event_type!r} {k}={v!r}")

                if event_type == "step_start":
                    sid = event.get("sessionID")
                    if sid:
                        _active.oc_session_id = sid

                elif event_type == "text":
                    part_text = event.get("part", {}).get("text", "")
                    _dbg(f"  text event: part.type={part_type!r} text_len={len(part_text)} part_type==text={part_type == 'text'}")
                    if part_type == "text" and part_text:
                        text_parts.append(part_text)
                        with _prompt_lock:
                            _prompt_state["progress"] = "".join(text_parts)
                            _prompt_state["text_chunks"] = list(text_parts)
                    elif part_text:
                        _dbg(f"  *** REJECTED text event (part.type={part_type!r} != 'text') text={part_text[:120]!r}")

                elif event_type == "error":
                    err = event.get("error", {})
                    msg = err.get("data", {}).get("message", str(err))
                    _dbg(f"  error: {msg}")
                    with _prompt_lock:
                        _prompt_state["error"] = msg

                else:
                    _dbg(f"  UNHANDLED event type={event_type!r} keys={list(event.keys())} part_keys={part_keys}")

            _raw_log.close()
            _active.prompt_count += 1
            final_text = "".join(text_parts)

            _dbg(f"_run: result {len(final_text)} chars")

            with _prompt_lock:
                _prompt_state["running"] = False
                _prompt_state["done"] = True
                _prompt_state["result"] = final_text.strip()
                _prompt_state["text_chunks"] = None
                _prompt_state.pop("progress", None)

        except Exception as e:
            _dbg(f"_run exception: {e}")
            if _raw_log:
                try:
                    _raw_log.write(f"EXCEPTION: {e}\n")
                    _raw_log.close()
                except Exception:
                    pass
            with _prompt_lock:
                _prompt_state["error"] = str(e)
                _prompt_state["running"] = False
                _prompt_state["done"] = True
        finally:
            if proc and proc.returncode is None:
                try:
                    proc.kill()
                except OSError:
                    pass

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
            return {"error": "prompt_id not found"}
        return dict(_prompt_state)
