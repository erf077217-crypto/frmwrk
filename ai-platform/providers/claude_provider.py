from __future__ import annotations

from typing import Any, AsyncGenerator

from anthropic import AsyncAnthropic

from .base import BaseProvider


class ClaudeProvider(BaseProvider):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._client: AsyncAnthropic | None = None

    # ── Identity ────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "claude"

    @property
    def display_name(self) -> str:
        return "Anthropic Claude"

    # ── Lifecycle ───────────────────────────────────────────

    async def initialize(self) -> None:
        api_key = self.config.get("api_key")
        if not api_key:
            msg = "ANTHROPIC_API_KEY is not configured"
            raise ValueError(msg)
        self._client = AsyncAnthropic(api_key=api_key)

    async def cleanup(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    # ── Core ────────────────────────────────────────────────

    async def generate(self, messages: list[dict], **kwargs: Any) -> dict:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        system, msgs = self._split_system(messages)
        response = await self._client.messages.create(
            model=kwargs.pop("model", self.config.get("model", "claude-3-5-sonnet-20241022")),
            messages=msgs,
            system=system or None,
            max_tokens=kwargs.pop("max_tokens", 4096),
            **kwargs,
        )
        return {
            "content": response.content[0].text if response.content else "",
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
            "provider": self.name,
        }

    async def stream(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncGenerator[dict, None]:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        system, msgs = self._split_system(messages)
        model = kwargs.pop("model", self.config.get("model", "claude-3-5-sonnet-20241022"))
        async with self._client.messages.stream(
            model=model,
            messages=msgs,
            system=system or None,
            max_tokens=kwargs.pop("max_tokens", 4096),
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield {"type": "chunk", "content": text}
        yield {"type": "done", "content": "", "model": model}

    # ── Discovery ───────────────────────────────────────────

    async def models(self) -> list[dict]:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        response = await self._client.models.list()
        return [
            {"id": m.id, "name": m.display_name or m.id, "created": m.created_at}
            for m in response.data
        ]

    async def health(self) -> dict:
        try:
            models_resp = await self._client.models.list() if self._client else None
            count = len(models_resp.data) if models_resp else 0
            return {
                "status": "ok",
                "message": f"Connected, {count} models available",
                "model": self.config.get("model", "claude-3-5-sonnet-20241022"),
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "model": self.config.get("model", "claude-3-5-sonnet-20241022")}

    # ── Metadata ────────────────────────────────────────────

    def provider_info(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "streaming": True,
            "tools": True,
            "models_endpoint": "https://api.anthropic.com/v1/models",
            "website": "https://anthropic.com",
        }

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _split_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
        system = None
        msgs = []
        for m in messages:
            if m.get("role") == "system" and system is None:
                system = m["content"]
            else:
                msgs.append(m)
        return system, msgs
