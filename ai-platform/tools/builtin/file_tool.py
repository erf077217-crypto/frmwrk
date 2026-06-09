from __future__ import annotations

import os
from pathlib import Path
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
        action = kwargs.get("action")
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")

        if not path:
            return {"success": False, "output": None, "error": "path is required"}

        path = self._resolve_path(path)

        if action == "read":
            return self._read(path)
        elif action == "write":
            if content is None:
                return {"success": False, "output": None, "error": "content is required for write"}
            return self._write(path, content)
        elif action == "delete":
            return self._delete(path)
        elif action == "append":
            if content is None:
                return {"success": False, "output": None, "error": "content is required for append"}
            return self._append(path, content)
        else:
            return {"success": False, "output": None, "error": f"Unknown action: {action}"}

    def _resolve_path(self, path: str) -> str:
        workspace = self.config.get("workspace", "/tmp/workspace")
        resolved = str(Path(workspace).resolve() / Path(path).name)
        return resolved

    def _read(self, path: str) -> dict:
        try:
            if not os.path.isfile(path):
                return {"success": False, "output": None, "error": f"File not found: {path}"}
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"success": True, "output": content, "error": None}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    def _write(self, path: str, content: str) -> dict:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "output": f"Written {len(content)} bytes to {path}", "error": None}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    def _delete(self, path: str) -> dict:
        try:
            if not os.path.isfile(path):
                return {"success": False, "output": None, "error": f"File not found: {path}"}
            size = os.path.getsize(path)
            os.remove(path)
            return {"success": True, "output": f"Deleted {path} ({size} bytes)", "error": None}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    def _append(self, path: str, content: str) -> dict:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "output": f"Appended {len(content)} bytes to {path}", "error": None}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}
