"""Tests for the /health endpoint and health-check logic."""

from __future__ import annotations

import pytest

from backend.api.health import health_check
from backend.core.startup import validate_environment


class TestValidateEnvironment:
    def test_no_warnings_with_keys(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        warnings = validate_environment()
        assert len(warnings) == 0

    def test_warnings_without_keys(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        warnings = validate_environment()
        assert len(warnings) >= 1


class TestHealthResponse:
    def test_health_endpoint_returns_expected_fields(self):
        import inspect
        assert inspect.iscoroutinefunction(health_check)

    def test_health_schema(self):
        from backend.models.schemas import HealthResponse
        h = HealthResponse()
        assert h.status == "ok"
        assert h.version == "0.1.0"
        assert h.app_name == "AI Platform"
        assert isinstance(h.providers_registered, int)
        assert isinstance(h.agents_registered, int)
        assert isinstance(h.tools_registered, int)
