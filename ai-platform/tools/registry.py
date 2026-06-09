from __future__ import annotations

from typing import Any

from .base import BaseTool


class ToolRegistry:
    """Central registry that maps tool names → tool instances.

    Tools are registered at startup and can be discovered by
    agents, the API, or LLM function-calling schema generators.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ── Registration ────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance by its ``.name``."""
        if tool.name in self._tools:
            raise KeyError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        self._tools.pop(name, None)

    # ── Lookup ──────────────────────────────────────────────

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())
