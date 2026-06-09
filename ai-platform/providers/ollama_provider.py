from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import httpx

from .base import BaseProvider


class OllamaProvider(BaseProvider):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._base_url: str = "http://localhost:11434"
        self._client: httpx.AsyncClient | None = None

    # ── Identity ────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama (Local)"

    # ── Lifecycle ───────────────────────────────────────────

    async def initialize(self) -> None:
        self._base_url = self.config.get("base_url", "http://localhost:11434").rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120)

    async def cleanup(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Core ────────────────────────────────────────────────

    async def generate(self, messages: list[dict], **kwargs: Any) -> dict:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        model = kwargs.pop("model", self.config.get("model", "llama3"))
        prompt = self._to_prompt(messages)
        response = await self._client.post(
            "/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, **kwargs},
        )
        response.raise_for_status()
        data = response.json()
        return {
            "content": data.get("response", ""),
            "model": data.get("model", model),
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            "provider": self.name,
        }

    async def stream(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncGenerator[dict, None]:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        model = kwargs.pop("model", self.config.get("model", "llama3"))
        prompt = self._to_prompt(messages)
        async with self._client.stream(
            "POST",
            "/api/generate",
            json={"model": model, "prompt": prompt, "stream": True, **kwargs},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("done"):
                    yield {"type": "done", "content": "", "model": chunk.get("model", model)}
                elif chunk.get("response"):
                    yield {"type": "chunk", "content": chunk["response"]}

    # ── Discovery ───────────────────────────────────────────

    async def models(self) -> list[dict]:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        response = await self._client.get("/api/tags")
        response.raise_for_status()
        data = response.json()
        return [
            {"id": m["name"], "name": m["name"], "created": m.get("modified_at", "")}
            for m in data.get("models", [])
        ]

    async def health(self) -> dict:
        try:
            response = await self._client.get("/") if self._client else None
            return {
                "status": "ok",
                "message": f"Ollama reachable at {self._base_url}" if response else "Not connected",
                "model": self.config.get("model", "llama3"),
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "model": self.config.get("model", "llama3")}

    # ── Metadata ────────────────────────────────────────────

    def provider_info(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "streaming": True,
            "tools": False,
            "models_endpoint": f"{self._base_url}/api/tags",
            "website": "https://ollama.com",
        }

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _to_prompt(messages: list[dict]) -> str:
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        return "\n".join(parts)
