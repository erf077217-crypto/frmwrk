from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract interface every tool must implement.

    Tools are stateless, self-contained capabilities that agents
    can invoke.  Each tool declares its name, description, and
    JSON Schema for parameters so it can be advertised to LLMs
    that support function calling.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    # ── Identity ────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name, e.g. 'file_read', 'git_status'."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""

    # ── Schema ──────────────────────────────────────────────

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema describing the tool's input parameters.

        Used to generate function-calling payloads for LLMs.
        """

    # ── Execution ───────────────────────────────────────────

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict:
        """Run the tool with the given parameters.

        Returns
        -------
        dict with keys:
          - "success" : bool
          - "output"  : Any (tool-specific result)
          - "error"   : str | None
        """

    def __str__(self) -> str:
        return self.name
