from __future__ import annotations

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
        return {"success": True, "output": None, "error": None}
