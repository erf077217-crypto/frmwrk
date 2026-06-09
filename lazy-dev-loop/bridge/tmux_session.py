from collections.abc import Callable
import json
import re
import shlex
import subprocess
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


def _session_export(session_id: str) -> dict | None:
    stdout, _, rc = _opencode_cli("export", session_id)
    if rc != 0 or not stdout:
        return None
    lines = stdout.split("\n")
    if lines and lines[0].startswith("Exporting session"):
        stdout = "\n".join(lines[1:])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    info = data.get("info", {})
    messages = data.get("messages", [])
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
        "messages": messages,
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

    def send_prompt(self, prompt: str) -> dict:
        if not self.active:
            return {
                "success": False,
                "error": "Session is not active. Start a session first.",
                "output": "",
            }

        before = _capture_pane()
        escaped = _escape_single_quotes(prompt)
        _tmux(f"send-keys -t {TMUX_SESSION_NAME} '{escaped}' Enter")

        output = self._wait_for_stable_output(before)

        self.prompt_count += 1
        self._last_capture = _capture_pane()

        return {
            "success": True,
            "output": output.strip(),
        }

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


async def send_prompt(prompt: str) -> dict:
    return _active.send_prompt(prompt)


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

_TOOL_LINE_RE = re.compile(
    r'^\s*(?:'
    r'[─═\s]{3,}'
    r'|```[\w]*'
    r'|```'
    r'|(?:>?\s*)(?:Read|Write|Shell|Search|Browse|Edit|Delete|Create|List|Move|Copy)\s+(?:file|directory|path|repo|code)\b'
    r'|(?:>?\s*)(?:File|Directory|Path)\s'
    r'|Token(?:s)?:?\s*(?:used|usage)?\s*\d'
    r'|Tokens?:?\s*\d'
    r'|Cost:?\s*\$?[\d.]'
    r'|Time:?\s*[\d.]+s'
    r'|API\s+request'
    r'|Rate\s+limit'
    r'|Retrying'
    r'|Error:\s*\d'
    r')',
    re.IGNORECASE,
)


def _heuristic_filter(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if _TOOL_LINE_RE.match(stripped):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _extract_assistant_summary(raw_output: str) -> str | None:
    session_id = _active.oc_session_id
    if not session_id:
        return None

    for _ in range(3):
        time.sleep(0.5)
        data = _session_export(session_id)
        if data:
            messages = data.get("messages", [])
            for msg in reversed(messages):
                role = msg.get("role", "")
                if role == "assistant":
                    content = msg.get("content") or msg.get("text") or ""
                    if content.strip():
                        return content.strip()
    return None


# ── background prompt processing -------------------------------------------

_prompt_state: dict = {}
_prompt_lock = threading.Lock()


def start_prompt_background(prompt: str) -> str:
    global _prompt_state
    prompt_id = uuid.uuid4().hex[:8]

    before = _capture_pane()
    escaped = _escape_single_quotes(prompt)
    _tmux(f"send-keys -t {TMUX_SESSION_NAME} '{escaped}' Enter")

    def _update_progress(content: str):
        with _prompt_lock:
            _prompt_state["progress"] = content

    def _run():
        global _prompt_state
        try:
            output = _active._wait_for_stable_output(
                before, on_progress=_update_progress
            )

            summary = _extract_assistant_summary(output) or output
            with _prompt_lock:
                _prompt_state["running"] = False
                _prompt_state["done"] = True
                _prompt_state["result"] = summary
        except Exception as e:
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
        }

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return prompt_id


def get_prompt_status(prompt_id: str) -> dict:
    with _prompt_lock:
        if _prompt_state.get("prompt_id") != prompt_id:
            return {"error": "prompt_id not found"}
        return dict(_prompt_state)
