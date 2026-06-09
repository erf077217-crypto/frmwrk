from __future__ import annotations

import logging
from typing import Any

from agents import CodingAgent, DocumentationAgent, TestingAgent
from providers import (
    BaseProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)
from tools.base import BaseTool
from tools.registry import ToolRegistry

logger = logging.getLogger("ai-platform.registry")


class ProviderRegistry:
    """Central registry for LLM providers.

    Providers register themselves by name at startup.  Application
    code looks them up dynamically — no hardcoded imports.
    """

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    # ── Registration ────────────────────────────────────────

    def register(self, provider: BaseProvider) -> None:
        self._providers[provider.name] = provider
        logger.info("Registered provider: %s", provider.display_name)

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)
        logger.info("Unregistered provider: %s", name)

    def get(self, name: str) -> BaseProvider | None:
        return self._providers.get(name)

    def require(self, name: str) -> BaseProvider:
        provider = self.get(name)
        if not provider:
            raise KeyError(f"Unknown provider: {name}. Available: {list(self._providers)}")
        return provider

    # ── Listing ─────────────────────────────────────────────

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "streaming": p.provider_info()["streaming"],
                "tools": p.provider_info()["tools"],
            }
            for p in self._providers.values()
        ]

    def list_status(self) -> list[dict[str, Any]]:
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "ready": True,
            }
            for p in self._providers.values()
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._providers

    def __len__(self) -> int:
        return len(self._providers)

    def __iter__(self):
        return iter(self._providers.values())


class AgentRegistry:
    """Registry that manages available agents."""

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}

    def register(self, agent: Any) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> Any | None:
        return self._agents.get(name)

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": a.name,
                "type": a.agent_type,
                "description": a.description,
            }
            for a in self._agents.values()
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._agents

    def __len__(self) -> int:
        return len(self._agents)


# ── Singleton instances ────────────────────────────────────

provider_registry = ProviderRegistry()
agent_registry = AgentRegistry()
tool_registry = ToolRegistry()


def build_default_registries(settings: Any) -> None:
    """Register default providers, agents, and tools."""

    # ── Providers ───────────────────────────────────────────
    if settings.enable_openai and settings.openai_api_key:
        p = OpenAIProvider({
            "api_key": settings.openai_api_key,
            "org_id": settings.openai_org_id,
            "model": "gpt-4o",
        })
        provider_registry.register(p)

    if settings.enable_anthropic and settings.anthropic_api_key:
        p = ClaudeProvider({
            "api_key": settings.anthropic_api_key,
            "model": "claude-3-5-sonnet-20241022",
        })
        provider_registry.register(p)

    if settings.enable_gemini and settings.gemini_api_key:
        p = GeminiProvider({
            "api_key": settings.gemini_api_key,
            "model": "gemini-2.0-flash",
        })
        provider_registry.register(p)

    if settings.enable_ollama:
        p = OllamaProvider({
            "base_url": settings.ollama_base_url,
            "model": settings.ollama_default_model,
        })
        provider_registry.register(p)

    if len(provider_registry) == 0:
        logger.warning("No providers registered — configure at least one API key")

    # ── Agents ──────────────────────────────────────────────
    agent_registry.register(CodingAgent(name="coding-agent"))
    agent_registry.register(DocumentationAgent(name="docs-agent"))
    agent_registry.register(TestingAgent(name="testing-agent"))

    # ── Tools ───────────────────────────────────────────────
    from tools.builtin import DatabaseTool, DirectoryTool, FileTool, GitTool, ShellTool

    tool_registry.register(FileTool())
    tool_registry.register(DirectoryTool())
    tool_registry.register(GitTool())
    tool_registry.register(ShellTool())
    tool_registry.register(DatabaseTool())
