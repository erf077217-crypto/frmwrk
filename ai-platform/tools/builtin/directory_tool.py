from __future__ import annotations

from typing import Any

from ..base import BaseTool


class DirectoryTool(BaseTool):
    @property
    def name(self) -> str:
        return "directory"

    @property
    def description(self) -> str:
        return "List, create, or remove directories on the filesystem."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "remove"],
                    "description": "Directory operation to perform.",
                },
                "path": {"type": "string", "description": "Directory path."},
            },
            "required": ["action", "path"],
        }

    async def execute(self, **kwargs: Any) -> dict:
        return {"success": True, "output": None, "error": None}
