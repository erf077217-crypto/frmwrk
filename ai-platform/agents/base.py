from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from providers.base import BaseProvider
from tools.registry import ToolRegistry


class BaseAgent(ABC):
    """Abstract interface every agent must implement.

    Agents follow a standard lifecycle:
        1. initialize   — set up resources, assign provider & tools
        2. run          — execute the agent's core logic
        3. complete     — finalise / collect results
        4. cleanup      — release resources
    """

    def __init__(
        self,
        name: str,
        provider: BaseProvider | None = None,
        tools: ToolRegistry | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.provider = provider
        self.tools = tools or ToolRegistry()
        self.config = config or {}

    # ── Identity ────────────────────────────────────────────

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Human-readable type, e.g. 'coding', 'documentation'."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of what this agent does."""

    # ── Lifecycle ───────────────────────────────────────────

    @abstractmethod
    async def initialize(self) -> None:
        """Prepare the agent (load prompts, validate config)."""

    @abstractmethod
    async def run(self, task: str, **kwargs: Any) -> dict:
        """Execute the agent on *task* and return results.

        Returns
        -------
        dict with keys:
          - "status"  : str ("success" | "error")
          - "output"  : str
          - "metadata": dict
        """

    @abstractmethod
    async def complete(self) -> dict:
        """Finalise and return accumulated results / metrics."""

    @abstractmethod
    async def cleanup(self) -> None:
        """Release any resources held by the agent."""

    def __str__(self) -> str:
        return f"{self.agent_type}@{self.name}"
