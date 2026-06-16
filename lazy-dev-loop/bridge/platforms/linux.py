import os
import pwd
import shlex
import subprocess

import config


class LinuxPlatform:

    def __init__(self):
        self._run_as_user: str | None = None
        self._user_env: dict[str, str] = {}
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user and os.geteuid() == 0:
            self._run_as_user = sudo_user
            self._user_env = self._discover_user_env()

    def _discover_user_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        try:
            pw = pwd.getpwnam(self._run_as_user)
            uid = pw.pw_uid
            home = pw.pw_dir
        except (KeyError, TypeError):
            return env
        env["DISPLAY"] = ":0"
        xauth = os.path.join(home, ".Xauthority")
        if os.path.isfile(xauth):
            env["XAUTHORITY"] = xauth
        xdg_rt = f"/run/user/{uid}"
        if os.path.isdir(xdg_rt):
            env["XDG_RUNTIME_DIR"] = xdg_rt
            bus_path = os.path.join(xdg_rt, "bus")
            if os.path.exists(bus_path):
                env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus_path}"
        xdg_rt_val = env.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        for wl_name in ("wayland-0", "wayland-1"):
            if os.path.exists(os.path.join(xdg_rt_val, wl_name)):
                env["WAYLAND_DISPLAY"] = wl_name
                break
        return env

    @property
    def name(self) -> str:
        return "linux"

    def _shell_cmd(self, command: str) -> list[str]:
        flag = "-ic" if config.USE_INTERACTIVE_SHELL else "-lc"
        cmd: list[str] = ["bash", flag, command]
        if self._run_as_user:
            cmd = ["sudo", "-u", self._run_as_user] + cmd
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

    def _resolve_command(self, command: str, _dbg_extra: str = "") -> str | None:
        for flag in ["-ic", "-ilc", "-lc"]:
            try:
                cmd = ["bash", flag, f"command -v {shlex.quote(command)}"]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=10, stdin=subprocess.DEVNULL)
                path = result.stdout.strip()
                if path:
                    print(f"[linux.py] _resolve_command{_dbg_extra}: bash {flag} found {path!r}", file=__import__('sys').stderr)
                    return path
            except Exception as e:
                print(f"[linux.py] _resolve_command{_dbg_extra}: bash {flag} exception: {e}", file=__import__('sys').stderr)
                continue
        import shutil, glob as _glob
        process_path = os.environ.get("PATH", "")
        shutil_path = shutil.which(command)
        print(f"[linux.py] _resolve_command{_dbg_extra}: PATH={process_path!r}", file=__import__('sys').stderr)
        print(f"[linux.py] _resolve_command{_dbg_extra}: shutil.which -> {shutil_path!r}", file=__import__('sys').stderr)
        if shutil_path:
            return shutil_path
        home = os.path.expanduser("~")
        print(f"[linux.py] _resolve_command{_dbg_extra}: HOME={home!r}", file=__import__('sys').stderr)
        candidates = [f"{home}/.opencode/bin", "/usr/local/bin", "/usr/bin",
                      f"{home}/.local/bin", "/snap/bin"]
        sudo_user = os.environ.get("SUDO_USER") or os.environ.get("LOGNAME")
        if sudo_user and sudo_user != os.environ.get("USER", ""):
            sudo_home = f"/home/{sudo_user}"
            candidates = [f"{sudo_home}/.opencode/bin"] + candidates
        for base in candidates:
            candidate = f"{base}/{command}"
            exists = os.path.isfile(candidate)
            executable = os.access(candidate, os.X_OK)
            print(f"[linux.py] _resolve_command{_dbg_extra}: check {candidate!r} -> exists={exists} exec={executable}", file=__import__('sys').stderr)
            if exists and executable:
                return candidate
        for home_dir in _glob.glob("/home/*"):
            candidate = f"{home_dir}/.opencode/bin/{command}"
            exists = os.path.isfile(candidate)
            executable = os.access(candidate, os.X_OK)
            print(f"[linux.py] _resolve_command{_dbg_extra}: glob-check {candidate!r} -> exists={exists} exec={executable}", file=__import__('sys').stderr)
            if exists and executable:
                return candidate
        return None

    def check_command(self, command: str) -> bool:
        found = self._resolve_command(command)
        print(f"[linux.py] check_command({command!r}) -> {found!r}", file=__import__('sys').stderr)
        return found is not None

    def is_available(self) -> bool:
        try:
            subprocess.run(["bash", "--version"], capture_output=True, timeout=5)
            return True
        except Exception:
            return False

    def open_terminal(self, session_name: str) -> dict:
        import time as _time
        import sys as _sys

        _dbg = lambda msg: print(f"[linux.py open_terminal] {msg}", file=_sys.stderr, flush=True)
        _dbg(f"called with session_name={session_name!r}, _run_as_user={self._run_as_user!r}")

        terminals = [
            ("x-terminal-emulator", ["-e"]),
            ("gnome-terminal", ["--"]),
            ("konsole", ["-e"]),
            ("xfce4-terminal", ["-e"]),
            ("lxterminal", ["-e"]),
            ("xterm", ["-e"]),
        ]
        attach_cmd = ["tmux", "attach", "-t", session_name]
        for term_cmd, term_args in terminals:
            try:
                cmd = [term_cmd] + term_args + attach_cmd
                if self._run_as_user:
                    env_prefix = [f"{k}={v}" for k, v in self._user_env.items()]
                    cmd = ["sudo", "-u", self._run_as_user] + env_prefix + cmd
                _dbg(f"trying: {cmd!r}")
                t0 = _time.monotonic()
                proc = subprocess.Popen(cmd, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                pid = proc.pid
                _dbg(f"Popen returned pid={pid}, elapsed={_time.monotonic()-t0:.3f}s")
                _time.sleep(0.8)
                ret = proc.poll()
                _dbg(f"after 0.8s poll: retcode={ret!r}")
                if ret is not None:
                    _dbg(f"term died early (ret={ret}), continuing")
                    continue
                _dbg(f"terminal launched successfully via {term_cmd} (pid={pid})")
                return {"success": True, "message": f"Terminal launched via {term_cmd}"}
            except FileNotFoundError:
                _dbg(f"term {term_cmd} not found")
                continue
            except Exception as e:
                _dbg(f"exception: {e}")
                return {"success": False, "error": str(e)}
        _dbg("no terminal emulator found")
        return {"success": False, "error": "No terminal emulator found. Install xterm, gnome-terminal, konsole, or xfce4-terminal."}

    def to_exec_path(self, host_path: str) -> str:
        return host_path

    def to_host_path(self, exec_path: str) -> str:
        return exec_path

    @property
    def env_not_found_message(self) -> str:
        return "Shell execution environment not available. Ensure bash is installed."
