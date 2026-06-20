import shlex
import shutil
import subprocess

import config


class LinuxPlatform:

    @property
    def name(self) -> str:
        return "linux"

    def _shell_cmd(self, command: str) -> list[str]:
        cmd: list[str] = ["bash", "-c", command]
        return cmd

    def run(self, command: str, *, timeout: int | None = None, **kwargs) -> subprocess.CompletedProcess:
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("stdin", subprocess.DEVNULL)
        kwargs.setdefault("start_new_session", True)
        cmd = self._shell_cmd(command)
        return subprocess.run(cmd, timeout=timeout, **kwargs)

    def popen(self, command: str, **kwargs) -> subprocess.Popen:
        kwargs.setdefault("text", True)
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("stdin", subprocess.DEVNULL)
        kwargs.setdefault("start_new_session", True)
        cmd = self._shell_cmd(command)
        return subprocess.Popen(cmd, **kwargs)

    def check_command(self, command: str) -> bool:
        return shutil.which(command) is not None

    def is_available(self) -> bool:
        try:
            subprocess.run(["bash", "--version"], capture_output=True, timeout=5)
            return True
        except Exception:
            return False

    def open_terminal(self, session_name: str) -> dict:
        return {
            "success": False,
            "error": (
                "This feature requires a desktop terminal emulator.\n\n"
                "In Docker, attach to the running tmux session with:\n\n"
                f"  docker exec -it lazy-dev-loop-bridge tmux attach -t {session_name}\n\n"
                "Or find the container name with:\n"
                "  docker ps\n"
                "Then replace 'lazy-dev-loop-bridge' with the actual container name."
            ),
        }

    def to_exec_path(self, host_path: str) -> str:
        return host_path

    def to_host_path(self, exec_path: str) -> str:
        return exec_path

    @property
    def env_not_found_message(self) -> str:
        return "Shell execution environment not available. Ensure bash is installed."
