from __future__ import annotations

import pytest

from backend.core.registries import ProviderRegistry
from providers import OpenAIProvider


@pytest.fixture
def registry() -> ProviderRegistry:
    return ProviderRegistry()


@pytest.fixture
def openai_provider() -> OpenAIProvider:
    return OpenAIProvider({"api_key": "test", "model": "gpt-4o"})


class TestProviderRegistry:
    def test_register_and_get(self, registry: ProviderRegistry, openai_provider: OpenAIProvider):
        registry.register(openai_provider)
        assert registry.get("openai") is openai_provider

    def test_get_unknown(self, registry: ProviderRegistry):
        assert registry.get("nonexistent") is None

    def test_require_existing(self, registry: ProviderRegistry, openai_provider: OpenAIProvider):
        registry.register(openai_provider)
        assert registry.require("openai") is openai_provider

    def test_require_unknown_raises(self, registry: ProviderRegistry):
        with pytest.raises(KeyError, match="Unknown provider"):
            registry.require("nonexistent")

    def test_unregister(self, registry: ProviderRegistry, openai_provider: OpenAIProvider):
        registry.register(openai_provider)
        assert "openai" in registry
        registry.unregister("openai")
        assert "openai" not in registry

    def test_contains(self, registry: ProviderRegistry, openai_provider: OpenAIProvider):
        assert "openai" not in registry
        registry.register(openai_provider)
        assert "openai" in registry

    def test_len(self, registry: ProviderRegistry, openai_provider: OpenAIProvider):
        assert len(registry) == 0
        registry.register(openai_provider)
        assert len(registry) == 1

    def test_iter(self, registry: ProviderRegistry, openai_provider: OpenAIProvider):
        registry.register(openai_provider)
        providers = list(registry)
        assert providers == [openai_provider]

    def test_list_returns_metadata(self, registry: ProviderRegistry, openai_provider: OpenAIProvider):
        registry.register(openai_provider)
        entries = registry.list()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["name"] == "openai"
        assert entry["display_name"] == "OpenAI"

    def test_list_status(self, registry: ProviderRegistry, openai_provider: OpenAIProvider):
        registry.register(openai_provider)
        statuses = registry.list_status()
        assert len(statuses) == 1
        assert statuses[0]["name"] == "openai"
        assert statuses[0]["ready"] is True

    def test_register_duplicate_name(self, registry: ProviderRegistry, openai_provider: OpenAIProvider):
        registry.register(openai_provider)
        openai2 = OpenAIProvider({"api_key": "test2"})
        # Should overwrite
        registry.register(openai2)
        assert registry.get("openai") is openai2
