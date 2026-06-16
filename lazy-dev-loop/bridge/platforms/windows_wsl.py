import re
import shlex
import subprocess

import config

_WIN_PATH_RE = re.compile(r'^([a-zA-Z]):\\(.*)')
_WSL_PATH_RE = re.compile(r'^/mnt/([a-z])/(.*)')


class WindowsWSLPlatform:

    @property
    def name(self) -> str:
        return "windows_wsl"

    def _wsl_cmd(self, command: str) -> list[str]:
        flag = "-ic" if config.USE_INTERACTIVE_SHELL else "-lc"
        cmd = ["wsl.exe"]
        if config.WSL_DISTRO:
            cmd.extend(["-d", config.WSL_DISTRO])
        cmd.extend(["bash", flag, command])
        return cmd

    def run(self, command: str, *, timeout: int | None = None, **kwargs) -> subprocess.CompletedProcess:
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("stdin", subprocess.DEVNULL)
        kwargs.setdefault("start_new_session", True)
        cmd = self._wsl_cmd(command)
        return subprocess.run(cmd, timeout=timeout, **kwargs)

    def popen(self, command: str, **kwargs) -> subprocess.Popen:
        kwargs.setdefault("text", True)
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("stdin", subprocess.DEVNULL)
        kwargs.setdefault("start_new_session", True)
        cmd = self._wsl_cmd(command)
        return subprocess.Popen(cmd, **kwargs)

    def check_command(self, command: str) -> bool:
        try:
            result = self.run(f"command -v {shlex.quote(command)}", timeout=10)
            return result.returncode == 0 and result.stdout.strip() != ""
        except Exception:
            return False

    def is_available(self) -> bool:
        try:
            subprocess.run(["wsl.exe", "--status"], capture_output=True, timeout=10)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def open_terminal(self, session_name: str) -> dict:
        flag = "-ic" if config.USE_INTERACTIVE_SHELL else "-lc"

        wsl_cmd = ["wsl.exe"]
        if config.WSL_DISTRO:
            wsl_cmd.extend(["-d", config.WSL_DISTRO])
        wsl_cmd.extend(["bash", flag, f"tmux attach -t {session_name}"])

        # Try Windows Terminal (wt.exe) first
        try:
            wt_cmd = ["wt.exe"] + wsl_cmd
            subprocess.Popen(wt_cmd)
            return {"success": True, "message": "Terminal launched via Windows Terminal"}
        except FileNotFoundError:
            pass
        except Exception as e:
            return {"success": False, "error": str(e)}

        # Fallback: wsl.exe with new console
        try:
            creationflags = 0
            if hasattr(subprocess, "CREATE_NEW_CONSOLE"):
                creationflags = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(wsl_cmd, creationflags=creationflags)
            return {"success": True, "message": "Terminal launched"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def to_exec_path(self, host_path: str) -> str:
        host_path = host_path.strip().strip('"').strip("'")
        match = _WIN_PATH_RE.match(host_path)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2).replace('\\', '/')
            return f"/mnt/{drive}/{rest}"
        match = _WSL_PATH_RE.match(host_path)
        if match:
            return host_path
        return host_path

    def to_host_path(self, exec_path: str) -> str:
        match = _WSL_PATH_RE.match(exec_path)
        if match:
            drive = match.group(1).upper()
            rest = match.group(2).replace('/', '\\')
            return f"{drive}:\\{rest}"
        if exec_path.startswith('/home/'):
            return exec_path
        return exec_path

    @property
    def env_not_found_message(self) -> str:
        return (
            "wsl.exe not found. Make sure WSL is installed.\n\n"
            "Run: wsl --install\n"
            "See: https://learn.microsoft.com/en-us/windows/wsl/install"
        )
