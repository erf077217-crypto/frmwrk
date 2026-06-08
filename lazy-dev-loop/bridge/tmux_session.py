import re
import shlex
import subprocess
import time
import uuid

import config
import session_store as ss
import workspace_manager as wm

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
TMUX_SESSION_NAME = "lazy-dev-loop"


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


def check_tmux() -> bool:
    """Verify tmux is available inside WSL."""
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
    """Escape text for use inside bash single quotes.

    In single quotes the only character that cannot appear is a single
    quote itself.  The trick is: end the quote, add an escaped quote,
    then restart the quote.
    """
    return text.replace("'", "'\\''")


def _capture_pane() -> str:
    """Read current tmux pane content."""
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


class TmuxSession:
    """Manages a single OpenCode TUI process inside a named tmux session.

    The tmux session becomes the single source of truth.  Both the
    bridge (extension prompts) and the OS terminal attach to the *same*
    tmux session, guaranteeing shared state.
    """

    def __init__(self):
        self.session_id: str | None = None
        self.started_at: float | None = None
        self.prompt_count: int = 0
        self._last_capture: str = ""
        self.finished: bool = False

    # ── public helpers ---------------------------------------------------

    @property
    def active(self) -> bool:
        return _tmux(f"has-session -t {TMUX_SESSION_NAME}")[2] == 0

    @property
    def uptime(self) -> float | None:
        if self.started_at and self.active and not self.finished:
            return time.time() - self.started_at
        return None

    # ── lifecycle --------------------------------------------------------

    def start(self) -> dict:
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

        opencode_cmd = f"cd {shlex.quote(wsl_path)} && {config.OPENCODE_COMMAND}"
        create_out = _tmux(
            f'new-session -d -s {TMUX_SESSION_NAME} {shlex.quote(opencode_cmd)}'
        )

        time.sleep(3)

        if not self.active:
            return {
                "success": False,
                "error": f"tmux session failed to start: {create_out[1][:200]}",
            }

        self.session_id = uuid.uuid4().hex[:12]
        self.started_at = time.time()
        self.prompt_count = 0
        self.finished = False
        self._last_capture = _capture_pane()

        ss.create_session(self.session_id, ws, 0)

        return {
            "success": True,
            "session_id": self.session_id,
            "session_name": TMUX_SESSION_NAME,
        }

    def stop(self) -> dict:
        _tmux(f"kill-session -t {TMUX_SESSION_NAME} 2>/dev/null")
        self.finished = True
        if self.session_id:
            ss.finalize_session(self.session_id)
        return {
            "success": True,
            "session_id": self.session_id,
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

        # Persist
        cleaned_prompt = strip_ansi(prompt).strip()
        clean_output = strip_ansi(output).strip()

        if self.session_id:
            ss.append_message(self.session_id, "user", cleaned_prompt)
            ss.append_message(self.session_id, "assistant", clean_output)

        self.prompt_count += 1
        self._last_capture = _capture_pane()

        return {
            "success": True,
            "output": clean_output,
            "raw": output,
        }

    def _wait_for_stable_output(self, before: str, timeout: int | None = None) -> str:
        """Block until the tmux pane content stabilises (no change for 1.5 s).

        Returns the *new* content (everything added after *before*).
        """
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
            return after[len(before) :]
        idx = after.find(before)
        if idx >= 0:
            return after[idx + len(before) :]
        return after

    # ── status / info ----------------------------------------------------

    def status(self) -> dict:
        active = self.active
        wsl_workspace = wm.get_workspace()
        return {
            "active": active and not self.finished,
            "session_id": self.session_id,
            "session_name": TMUX_SESSION_NAME,
            "uptime": self.uptime,
            "started_at": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.started_at))
                if self.started_at
                else None
            ),
            "prompt_count": self.prompt_count,
            "workspace": wsl_workspace,
        }

    def pane_preview(self, max_lines: int = 5) -> str:
        """Return the last *max_lines* lines of the pane (ANSI-stripped)."""
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
                creationflags = subprocess.CREATE_NEW_CONSOLE  # 16
            subprocess.Popen(cmd, creationflags=creationflags)
            return {"success": True, "message": "Terminal launched"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ── module-level singleton ------------------------------------------------

_active = TmuxSession()


def get_active() -> TmuxSession:
    return _active


async def start_session() -> dict:
    if _active.active and not _active.finished:
        return {
            "success": False,
            "error": "Session already active. Stop it first.",
        }
    return _active.start()


async def stop_session() -> dict:
    return _active.stop()


async def send_prompt(prompt: str) -> dict:
    return _active.send_prompt(prompt)


def get_session_status() -> dict:
    return _active.status()


def open_terminal() -> dict:
    return _active.open_terminal()


def list_saved_sessions() -> list[dict]:
    return ss.list_sessions()


def get_saved_session(session_id: str) -> dict | None:
    return ss.get_session(session_id)


def archive_saved_session(session_id: str) -> dict:
    ok = ss.archive_session(session_id)
    if not ok:
        return {"success": False, "error": "Session not found"}
    return {"success": True, "session_id": session_id}


async def load_session(session_id: str) -> dict:
    saved = ss.get_session(session_id)
    if not saved:
        return {"success": False, "error": "Session not found"}

    if _active.active and not _active.finished:
        await _active.stop()

    ws_path = saved.get("workspace", {}).get("workspace")
    if ws_path:
        wm.set_workspace(ws_path)

    return _active.start()
