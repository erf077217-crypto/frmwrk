"""Tests for API endpoints (tools, agents execution)."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from backend.core.registries import (
    agent_registry,
    build_default_registries,
    provider_registry,
    tool_registry,
)
from backend.main import app
from configs.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        workspace_dir=tempfile.mkdtemp(),
        db_path=os.path.join(tempfile.mkdtemp(), "data.db"),
        enable_openai=False,
        enable_anthropic=False,
        enable_gemini=False,
        enable_ollama=False,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    # Clear registries before building to avoid duplicate registration
    provider_registry._providers.clear()
    agent_registry._agents.clear()
    tool_registry._tools.clear()
    build_default_registries(settings)
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert data["app_name"] == "AI Platform"

    def test_health_lists_registrations(self, client: TestClient):
        resp = client.get("/health")
        data = resp.json()
        assert isinstance(data.get("providers_registered"), int)
        assert isinstance(data.get("agents_registered"), int)
        assert isinstance(data.get("tools_registered"), int)


class TestToolsEndpoint:
    def test_list_tools(self, client: TestClient):
        resp = client.get("/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        tool_names = [t["name"] for t in data["tools"]]
        assert "file" in tool_names
        assert "directory" in tool_names
        assert "git" in tool_names
        assert "shell" in tool_names
        assert "database" in tool_names

    def test_execute_file_tool(self, client: TestClient):
        resp = client.post("/tools/file/execute", json={"args": {"action": "read", "path": "/nonexistent"}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "file"
        assert data["success"] is False

    def test_execute_unknown_tool(self, client: TestClient):
        resp = client.post("/tools/unknown/execute", json={"args": {}})
        assert resp.status_code == 404

    def test_execute_tool_writes_file(self, client: TestClient):
        resp = client.post(
            "/tools/file/execute",
            json={"args": {"action": "write", "path": "/tmp/test_write.txt", "content": "test"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


class TestAgentsEndpoint:
    def test_list_agents(self, client: TestClient):
        resp = client.get("/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        agent_names = [a["name"] for a in data["agents"]]
        assert "coding-agent" in agent_names

    def test_execute_agent_unknown(self, client: TestClient):
        resp = client.post("/agents/unknown/execute", json={"task": "test"})
        assert resp.status_code == 404
