from __future__ import annotations

from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._client: AsyncOpenAI | None = None

    # ── Identity ────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "openai"

    @property
    def display_name(self) -> str:
        return "OpenAI"

    # ── Lifecycle ───────────────────────────────────────────

    async def initialize(self) -> None:
        api_key = self.config.get("api_key")
        if not api_key:
            msg = "OPENAI_API_KEY is not configured"
            raise ValueError(msg)
        self._client = AsyncOpenAI(
            api_key=api_key,
            organization=self.config.get("org_id"),
        )

    async def cleanup(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    # ── Core ────────────────────────────────────────────────

    async def generate(self, messages: list[dict], **kwargs: Any) -> dict:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        response = await self._client.chat.completions.create(
            messages=messages,
            model=kwargs.pop("model", self.config.get("model", "gpt-4o")),
            **kwargs,
        )
        choice = response.choices[0]
        return {
            "content": choice.message.content or "",
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            "provider": self.name,
        }

    async def stream(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncGenerator[dict, None]:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        stream = await self._client.chat.completions.create(
            messages=messages,
            model=kwargs.pop("model", self.config.get("model", "gpt-4o")),
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        model_used = kwargs.get("model", self.config.get("model", "gpt-4o"))
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield {"type": "chunk", "content": delta.content}
        yield {"type": "done", "content": "", "model": model_used}

    # ── Discovery ───────────────────────────────────────────

    async def models(self) -> list[dict]:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        response = await self._client.models.list()
        return [
            {"id": m.id, "name": m.id, "created": m.created}
            for m in response.data
            if m.id.startswith("gpt-") or m.id.startswith("o")
        ]

    async def health(self) -> dict:
        try:
            models_resp = await self._client.models.list() if self._client else None
            return {
                "status": "ok",
                "message": f"Connected, {len(models_resp.data)} models available" if models_resp else "Connected",
                "model": self.config.get("model", "gpt-4o"),
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "model": self.config.get("model", "gpt-4o")}

    # ── Metadata ────────────────────────────────────────────

    def provider_info(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "streaming": True,
            "tools": True,
            "models_endpoint": "https://api.openai.com/v1/models",
            "website": "https://openai.com",
        }
