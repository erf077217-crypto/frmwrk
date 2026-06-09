from __future__ import annotations

import asyncio
from typing import Any

from ..base import BaseTool


class GitTool(BaseTool):
    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Execute Git commands (status, diff, log, commit, etc.)."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Git sub-command, e.g. 'status', 'diff', 'log'.",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional arguments passed to the command.",
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> dict:
        command = kwargs.get("command", "")
        args = kwargs.get("args", [])
        workdir = self.config.get("workspace", "/tmp/workspace")

        if not command:
            return {"success": False, "output": None, "error": "command is required"}

        cmd = ["git", command] + list(args)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode == 0:
                return {
                    "success": True,
                    "output": stdout.decode("utf-8", errors="replace"),
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "output": None,
                    "error": stderr.decode("utf-8", errors="replace"),
                }
        except asyncio.TimeoutError:
            return {"success": False, "output": None, "error": "Git command timed out after 30 seconds"}
        except FileNotFoundError:
            return {"success": False, "output": None, "error": "Git is not installed or not in PATH"}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}
