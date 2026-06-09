from __future__ import annotations

from typing import Any

from ..base import BaseTool


class DatabaseTool(BaseTool):
    @property
    def name(self) -> str:
        return "database"

    @property
    def description(self) -> str:
        return "Execute SQL queries against configured databases."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL query string."},
                "params": {
                    "type": "array",
                    "items": {},
                    "description": "Query parameters.",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> dict:
        return {"success": True, "output": None, "error": None}
