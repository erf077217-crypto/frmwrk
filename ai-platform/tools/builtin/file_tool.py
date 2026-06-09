from __future__ import annotations

from typing import Any

from ..base import BaseTool


class FileTool(BaseTool):
    @property
    def name(self) -> str:
        return "file"

    @property
    def description(self) -> str:
        return "Read, write, or delete files on the filesystem."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "delete", "append"],
                    "description": "File operation to perform.",
                },
                "path": {"type": "string", "description": "Absolute file path."},
                "content": {
                    "type": "string",
                    "description": "Content to write (write/append only).",
                },
            },
            "required": ["action", "path"],
        }

    async def execute(self, **kwargs: Any) -> dict:
        return {"success": True, "output": None, "error": None}
