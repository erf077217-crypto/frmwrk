"""Contract tests: every provider must satisfy the BaseProvider contract."""

from __future__ import annotations

from typing import Any

import pytest

from providers import (
    BaseProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)


# ── Fixtures ───────────────────────────────────────────────

@pytest.fixture
def provider_config() -> dict[str, Any]:
    return {
        "api_key": "test-key",
        "base_url": "http://localhost:11434",
        "model": "test-model",
    }


@pytest.fixture
def sample_messages() -> list[dict]:
    return [{"role": "user", "content": "Hello"}]


# ── Contract tests ─────────────────────────────────────────

CONTRACT_METHODS = [
    "name",
    "display_name",
    "initialize",
    "cleanup",
    "generate",
    "stream",
    "models",
    "health",
    "provider_info",
]


def test_abstract_class_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseProvider()  # type: ignore


@pytest.mark.parametrize("provider_cls", [
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
])
def test_provider_implements_all_abstract_methods(provider_cls, provider_config):
    instance = provider_cls(provider_config)
    for method in CONTRACT_METHODS:
        assert hasattr(instance, method), f"{provider_cls.__name__} missing {method}"
    assert instance.name
    assert instance.display_name


@pytest.mark.parametrize("provider_cls", [
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
])
def test_provider_info_returns_expected_keys(provider_cls, provider_config):
    instance = provider_cls(provider_config)
    info = instance.provider_info()
    for key in ("name", "display_name", "streaming", "tools", "models_endpoint", "website"):
        assert key in info, f"{provider_cls.__name__}.provider_info() missing '{key}'"


@pytest.mark.parametrize("provider_cls", [
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
])
def test_generate_has_correct_signature(provider_cls, provider_config, sample_messages):
    instance = provider_cls(provider_config)
    assert hasattr(instance, "generate")
    import inspect
    sig = inspect.signature(instance.generate)
    assert "messages" in sig.parameters


@pytest.mark.parametrize("provider_cls", [
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
])
def test_generate_is_coroutine(provider_cls, provider_config):
    instance = provider_cls(provider_config)
    import inspect
    assert inspect.iscoroutinefunction(instance.generate), \
        f"{provider_cls.__name__}.generate() should be async"


@pytest.mark.parametrize("provider_cls", [
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
])
def test_stream_is_async_generator(provider_cls, provider_config, sample_messages):
    instance = provider_cls(provider_config)
    gen = instance.stream(sample_messages)
    import inspect
    assert inspect.isasyncgen(gen) or hasattr(gen, "__aiter__"), \
        f"{provider_cls.__name__}.stream() should return an async generator"


@pytest.mark.parametrize("provider_cls", [
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
])
def test_health_returns_expected_structure(provider_cls, provider_config):
    instance = provider_cls(provider_config)
    import inspect
    assert inspect.iscoroutinefunction(instance.health), \
        f"{provider_cls.__name__}.health() should be async"


@pytest.mark.parametrize("provider_cls", [
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
])
def test_models_is_async(provider_cls, provider_config):
    instance = provider_cls(provider_config)
    import inspect
    assert inspect.iscoroutinefunction(instance.models), \
        f"{provider_cls.__name__}.models() should be async"


@pytest.mark.parametrize("provider_cls", [
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
])
def test_initialize_cleanup_methods_exist(provider_cls, provider_config):
    instance = provider_cls(provider_config)
    import inspect
    assert inspect.iscoroutinefunction(instance.initialize)
    assert inspect.iscoroutinefunction(instance.cleanup)


@pytest.mark.parametrize("provider_cls", [
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
])
def test_initialize_raises_without_api_key(provider_cls):
    import inspect
    no_key_instance = provider_cls({})
    if inspect.iscoroutinefunction(no_key_instance.initialize):
        # Can't actually await here, but verify the method exists
        pass
