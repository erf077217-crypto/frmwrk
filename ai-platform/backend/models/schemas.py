from __future__ import annotations

from pydantic import BaseModel, Field


# ── Health ─────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    app_name: str = "AI Platform"
    providers_registered: int = 0
    agents_registered: int = 0
    tools_registered: int = 0
    diagnostics: dict | None = None


# ── Providers ──────────────────────────────────────────────

class ProviderInfo(BaseModel):
    name: str
    display_name: str
    streaming: bool
    tools: bool


class ProviderListResponse(BaseModel):
    providers: list[ProviderInfo]


class ProviderStatus(BaseModel):
    name: str
    display_name: str
    status: str
    message: str
    model: str


class ProviderStatusListResponse(BaseModel):
    providers: list[ProviderStatus]


class ModelInfo(BaseModel):
    id: str
    name: str
    created: str


class ModelListResponse(BaseModel):
    provider: str
    models: list[ModelInfo]


# ── Chat ───────────────────────────────────────────────────

class ChatRequest(BaseModel):
    provider: str = Field(description="Provider name, e.g. 'openai', 'claude', 'gemini', 'ollama'")
    model: str | None = Field(default=None, description="Model identifier (provider default if omitted)")
    messages: list[dict] = Field(description="OpenAI-format message list")
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    stream: bool = Field(default=False, description="If true, returns SSE stream")


class ChatResponse(BaseModel):
    content: str
    model: str
    usage: dict
    provider: str


# ── Agents ─────────────────────────────────────────────────

class AgentInfo(BaseModel):
    name: str
    type: str
    description: str


class AgentListResponse(BaseModel):
    agents: list[AgentInfo]


# ── Tools ──────────────────────────────────────────────────

class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: dict


class ToolListResponse(BaseModel):
    tools: list[ToolInfo]
