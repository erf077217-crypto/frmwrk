from __future__ import annotations

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
        return {"success": True, "output": None, "error": None}
