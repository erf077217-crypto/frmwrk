from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..base import BaseTool


class DatabaseTool(BaseTool):
    @property
    def name(self) -> str:
        return "database"

    @property
    def description(self) -> str:
        return "Execute SQL queries against a SQLite database."

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
        query = kwargs.get("query", "")
        params = kwargs.get("params", [])

        if not query:
            return {"success": False, "output": None, "error": "query is required"}

        db_path = self.config.get("db_path", "/tmp/workspace/data.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query_upper = query.strip().upper()
            is_read = query_upper.startswith("SELECT") or query_upper.startswith("PRAGMA")

            if is_read:
                cursor.execute(query, params)
                rows = [dict(row) for row in cursor.fetchall()]
                conn.close()
                return {"success": True, "output": rows, "error": None}
            else:
                cursor.execute(query, params)
                conn.commit()
                affected = cursor.rowcount
                last_id = cursor.lastrowid
                conn.close()
                return {
                    "success": True,
                    "output": {
                        "affected_rows": affected,
                        "last_insert_id": last_id,
                    },
                    "error": None,
                }
        except sqlite3.Error as e:
            return {"success": False, "output": None, "error": f"SQLite error: {e}"}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}
