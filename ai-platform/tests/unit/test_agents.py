"""Tests for agent implementations."""

from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest

from agents import CodingAgent
from agents.base import BaseAgent as BaseAgentABC
from providers.base import BaseProvider
from tools.registry import ToolRegistry


# ── Mock Provider ──────────────────────────────────────────

class MockProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__()
        self._generate_result: dict = {
            "content": "",
            "model": "mock-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "provider": "mock",
        }

    @property
    def name(self) -> str:
        return "mock"

    @property
    def display_name(self) -> str:
        return "Mock Provider"

    async def initialize(self) -> None:
        pass

    async def cleanup(self) -> None:
        pass

    async def generate(self, messages: list[dict], **kwargs: Any) -> dict:
        return self._generate_result

    async def stream(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncGenerator[dict, None]:
        yield {"type": "chunk", "content": "mock"}
        yield {"type": "done", "content": "", "model": "mock-model"}

    async def models(self) -> list[dict]:
        return [{"id": "mock", "name": "Mock Model", "created": "2024-01-01"}]

    async def health(self) -> dict:
        return {"status": "ok", "message": "Mock OK", "model": "mock"}

    def provider_info(self) -> dict:
        return {
            "name": "mock",
            "display_name": "Mock Provider",
            "streaming": True,
            "tools": True,
            "models_endpoint": "",
            "website": "",
        }


# ── Fixtures ───────────────────────────────────────────────

@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider()


@pytest.fixture
def tool_registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def coding_agent(mock_provider: MockProvider, tool_registry: ToolRegistry) -> CodingAgent:
    return CodingAgent(name="test-agent", provider=mock_provider, tools=tool_registry)


# ── CodingAgent Tests ──────────────────────────────────────

class TestCodingAgent:
    def test_agent_type(self, coding_agent: CodingAgent):
        assert coding_agent.agent_type == "coding"

    def test_description(self, coding_agent: CodingAgent):
        assert "Generates" in coding_agent.description

    @pytest.mark.anyio
    async def test_initialize_requires_provider(self):
        agent = CodingAgent(name="no-provider")
        with pytest.raises(RuntimeError, match="requires a provider"):
            await agent.initialize()

    @pytest.mark.anyio
    async def test_run_without_provider(self, tool_registry: ToolRegistry):
        agent = CodingAgent(name="no-provider", tools=tool_registry)
        result = await agent.run("test task")
        assert result["status"] == "error"
        assert "No provider" in result["output"]

    @pytest.mark.anyio
    async def test_run_returns_success(self, coding_agent: CodingAgent):
        coding_agent.provider._generate_result = {
            "content": '{"plan": "test", "files": [], "commands": []}',
            "model": "mock-model",
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
            "provider": "mock",
        }
        await coding_agent.initialize()
        result = await coding_agent.run("write a test file")
        assert result["status"] == "success"

    @pytest.mark.anyio
    async def test_complete_returns_metadata(self, coding_agent: CodingAgent):
        await coding_agent.initialize()
        await coding_agent.run("test")
        result = await coding_agent.complete()
        assert result["status"] == "success"
        assert "task" in result["output"]

    @pytest.mark.anyio
    async def test_cleanup_resets_state(self, coding_agent: CodingAgent):
        await coding_agent.initialize()
        await coding_agent.run("test")
        await coding_agent.cleanup()
        result = await coding_agent.complete()
        assert "{}" in result["output"]

    def test_parse_response_json_block(self, coding_agent: CodingAgent):
        content = '```json\n{"plan": "test plan", "files": [{"path": "a.py", "content": "print(1)"}], "commands": ["echo done"]}\n```'
        plan, files, commands = coding_agent._parse_response(content)
        assert plan == "test plan"
        assert len(files) == 1
        assert files[0]["path"] == "a.py"
        assert commands == ["echo done"]

    def test_parse_response_bare_json(self, coding_agent: CodingAgent):
        content = '{"plan": "bare", "files": [], "commands": []}'
        plan, files, commands = coding_agent._parse_response(content)
        assert plan == "bare"

    def test_parse_response_no_json(self, coding_agent: CodingAgent):
        content = "Just some text without JSON"
        plan, files, commands = coding_agent._parse_response(content)
        assert plan == ""
        assert files == []
        assert commands == []

    def test_parse_response_invalid_json(self, coding_agent: CodingAgent):
        content = "```json\n{invalid json}\n```"
        plan, files, commands = coding_agent._parse_response(content)
        assert plan == ""


# ── BaseAgent Contract Tests ───────────────────────────────

class TestBaseAgentContract:
    def test_abstract_class_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            BaseAgentABC()  # type: ignore

    def test_concrete_agent_has_required_properties(self, coding_agent: CodingAgent):
        assert hasattr(coding_agent, "agent_type")
        assert hasattr(coding_agent, "description")
        assert hasattr(coding_agent, "initialize")
        assert hasattr(coding_agent, "run")
        assert hasattr(coding_agent, "complete")
        assert hasattr(coding_agent, "cleanup")

    def test_run_is_async(self, coding_agent: CodingAgent):
        import inspect
        assert inspect.iscoroutinefunction(coding_agent.run)

    def test_initialize_is_async(self, coding_agent: CodingAgent):
        import inspect
        assert inspect.iscoroutinefunction(coding_agent.initialize)

    def test_complete_is_async(self, coding_agent: CodingAgent):
        import inspect
        assert inspect.iscoroutinefunction(coding_agent.complete)

    def test_cleanup_is_async(self, coding_agent: CodingAgent):
        import inspect
        assert inspect.iscoroutinefunction(coding_agent.cleanup)
