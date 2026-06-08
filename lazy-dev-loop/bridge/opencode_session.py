import asyncio
import os
import shlex
import signal
import subprocess
import time
from datetime import datetime
import uuid

import config
import workspace_manager as wm

SESSION_PORT = 14096


class OpenCodeSession:
    def __init__(self):
        self.session_id: str | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.port: int = SESSION_PORT
        self.started_at: float | None = None
        self.finished: bool = False
        self._read_task: asyncio.Task | None = None

    @property
    def uptime(self) -> float | None:
        if self.started_at and not self.finished:
            return time.time() - self.started_at
        return None

    @property
    def pid(self) -> int | None:
        if self.process and self.process.pid:
            return self.process.pid
        return None

    def _build_wsl_cmd(self, inner: str, cwd: str | None = None) -> list[str]:
        flag = "-ic" if config.USE_INTERACTIVE_SHELL else "-lc"
        cmd = ["wsl.exe"]
        if config.WSL_DISTRO:
            cmd.extend(["-d", config.WSL_DISTRO])
        if cwd:
            cmd.extend(["--cd", cwd])
        cmd.extend(["bash", flag, inner])
        return cmd

    async def start(self) -> dict:
        ws = wm.get_workspace()
        wsl_path = ws.get("wsl_path")
        if not wsl_path:
            return {"success": False, "error": "No workspace set. Set a workspace first."}

        port = self.port
        inner = f"{config.OPENCODE_COMMAND} serve --port {port}"
        cmd = self._build_wsl_cmd(inner, cwd=wsl_path)

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        self.session_id = uuid.uuid4().hex[:12]
        self.started_at = time.time()
        self._read_task = asyncio.create_task(self._read_output())

        await asyncio.sleep(2)

        alive = self.process.returncode is None
        if not alive:
            return {"success": False, "error": "opencode serve failed to start"}

        return {
            "success": True,
            "session_id": self.session_id,
            "port": port,
            "pid": self.pid,
            "workspace": ws,
        }

    async def stop(self) -> dict:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self._read_task:
            self._read_task.cancel()
        self.finished = True
        return {"success": True, "session_id": self.session_id}

    async def send_prompt(self, prompt: str) -> dict:
        if not self.session_id or self.finished:
            return {"success": False, "error": "No active session. Start a session first.", "output": ""}

        ws = wm.get_workspace()
        wsl_path = ws.get("wsl_path", "")
        port = self.port

        inner = f"{config.OPENCODE_COMMAND} run --attach http://localhost:{port} {shlex.quote(prompt)}"
        cmd = self._build_wsl_cmd(inner, cwd=wsl_path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=config.RUN_TIMEOUT)
            text = stdout.decode("utf-8", errors="replace")
            return {
                "success": proc.returncode == 0,
                "output": text,
                "returncode": proc.returncode,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": "Timed out", "output": ""}
        except Exception as e:
            return {"success": False, "error": str(e), "output": ""}

    async def _read_output(self):
        try:
            while True:
                data = await self.process.stdout.read(4096)
                if not data:
                    break
        except Exception:
            pass
        finally:
            if self.process:
                await self.process.wait()
            self.finished = True

    def status(self) -> dict:
        ws = wm.get_workspace()
        if not self.session_id:
            return {"active": False, "workspace": ws}
        return {
            "active": not self.finished and self.process is not None and self.process.returncode is None,
            "session_id": self.session_id,
            "port": self.port,
            "pid": self.pid,
            "uptime": self.uptime,
            "started_at": datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            "workspace": ws,
        }

    def open_terminal(self) -> dict:
        if not self.session_id or self.finished:
            return {"success": False, "error": "No active session"}

        ws = wm.get_workspace()
        wsl_path = ws.get("wsl_path", "")
        port = self.port

        inner = f"{config.OPENCODE_COMMAND} attach http://localhost:{port}"
        flag = "-ic" if config.USE_INTERACTIVE_SHELL else "-lc"
        cmd = ["wsl.exe"]
        if config.WSL_DISTRO:
            cmd.extend(["-d", config.WSL_DISTRO])
        if wsl_path:
            cmd.extend(["--cd", wsl_path])
        cmd.extend(["bash", flag, inner])

        try:
            creationflags = 0
            if hasattr(subprocess, 'CREATE_NEW_CONSOLE'):
                creationflags = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(cmd, creationflags=creationflags)
            return {"success": True, "message": "Terminal launched"}
        except Exception as e:
            return {"success": False, "error": str(e)}


_active_session = OpenCodeSession()


def get_active_session() -> OpenCodeSession:
    return _active_session


async def start_session() -> dict:
    if _active_session.session_id and not _active_session.finished:
        return {"success": False, "error": "Session already active. Stop it first."}
    return await _active_session.start()


async def stop_session() -> dict:
    return await _active_session.stop()


async def send_prompt(prompt: str) -> dict:
    return await _active_session.send_prompt(prompt)


def get_session_status() -> dict:
    return _active_session.status()


def open_terminal() -> dict:
    return _active_session.open_terminal()
