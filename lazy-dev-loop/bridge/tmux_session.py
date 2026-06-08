import json
import re
import shlex
import subprocess
import time

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

        time.sleep(3)

        if not self.active:
            return {
                "success": False,
                "error": f"tmux session failed to start: {create_out[1][:200]}",
            }

        self.oc_session_id = session_id or None
        self.started_at = time.time()
        self.prompt_count = 0
        self.finished = False
        self._last_capture = _capture_pane()

        return {
            "success": True,
            "session_id": session_id or None,
            "session_name": TMUX_SESSION_NAME,
        }

    def stop(self) -> dict:
        _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
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

        cleaned_prompt = strip_ansi(prompt).strip()
        clean_output = strip_ansi(output).strip()

        self.prompt_count += 1
        self._last_capture = _capture_pane()

        return {
            "success": True,
            "output": clean_output,
            "raw": output,
        }

    def _wait_for_stable_output(self, before: str, timeout: int | None = None) -> str:
        deadline = time.time() + (timeout or config.RUN_TIMEOUT)
        last_output = before
        stable_since: float | None = None

        while time.time() < deadline:
            time.sleep(0.25)
            current = _capture_pane()
            if current == last_output:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= 1.5:
                    break
            else:
                last_output = current
                stable_since = None

        return self._extract_new(before, last_output)

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
    if _active.active and not _active.finished:
        return {
            "success": False,
            "error": "Session already active. Stop it first.",
        }
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
