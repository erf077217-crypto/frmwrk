from __future__ import annotations

from typing import Any

from .base import BaseAgent


class TestingAgent(BaseAgent):
    @property
    def agent_type(self) -> str:
        return "testing"

    @property
    def description(self) -> str:
        return "Generates and runs unit / integration tests for given code."

    async def initialize(self) -> None:
        pass

    async def run(self, task: str, **kwargs: Any) -> dict:
        return {"status": "success", "output": "", "metadata": {}}

    async def complete(self) -> dict:
        return {"status": "success", "output": "", "metadata": {}}

    async def cleanup(self) -> None:
        pass
