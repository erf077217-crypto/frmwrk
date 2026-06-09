from __future__ import annotations

import asyncio
from typing import Any

from ..base import BaseTool


class ShellTool(BaseTool):
    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Execute arbitrary shell commands in the workspace."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "workdir": {
                    "type": "string",
                    "description": "Working directory for the command.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds.",
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> dict:
        command = kwargs.get("command", "")
        workdir = kwargs.get("workdir") or self.config.get("workspace", "/tmp/workspace")
        timeout = kwargs.get("timeout", 30)

        if not command:
            return {"success": False, "output": None, "error": "command is required"}

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "success": proc.returncode == 0,
                "output": stdout.decode("utf-8", errors="replace"),
                "error": stderr.decode("utf-8", errors="replace") if proc.returncode != 0 else None,
            }
        except asyncio.TimeoutError:
            return {"success": False, "output": None, "error": f"Shell command timed out after {timeout} seconds"}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}
