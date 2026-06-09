from __future__ import annotations

import os
from pathlib import Path
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
        action = kwargs.get("action")
        path = kwargs.get("path", "")

        if not path:
            return {"success": False, "output": None, "error": "path is required"}

        if action == "list":
            return self._list(path)
        elif action == "create":
            return self._create(path)
        elif action == "remove":
            return self._remove(path)
        else:
            return {"success": False, "output": None, "error": f"Unknown action: {action}"}

    def _list(self, path: str) -> dict:
        try:
            if not os.path.isdir(path):
                return {"success": False, "output": None, "error": f"Directory not found: {path}"}
            entries = []
            for entry in sorted(os.listdir(path)):
                full = os.path.join(path, entry)
                entry_type = "dir" if os.path.isdir(full) else "file"
                size = os.path.getsize(full) if os.path.isfile(full) else 0
                entries.append({"name": entry, "type": entry_type, "size": size})
            return {"success": True, "output": entries, "error": None}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    def _create(self, path: str) -> dict:
        try:
            os.makedirs(path, exist_ok=True)
            return {"success": True, "output": f"Created directory: {path}", "error": None}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    def _remove(self, path: str) -> dict:
        try:
            if not os.path.isdir(path):
                return {"success": False, "output": None, "error": f"Directory not found: {path}"}
            os.rmdir(path)
            return {"success": True, "output": f"Removed directory: {path}", "error": None}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}
