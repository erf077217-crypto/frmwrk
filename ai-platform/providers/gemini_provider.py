from __future__ import annotations

from typing import Any, AsyncGenerator

from google import genai
from google.genai import types as genai_types

from .base import BaseProvider


class GeminiProvider(BaseProvider):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._client: genai.Client | None = None

    # ── Identity ────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Google Gemini"

    # ── Lifecycle ───────────────────────────────────────────

    async def initialize(self) -> None:
        api_key = self.config.get("api_key")
        if not api_key:
            msg = "GEMINI_API_KEY is not configured"
            raise ValueError(msg)
        self._client = genai.Client(api_key=api_key)

    async def cleanup(self) -> None:
        self._client = None

    # ── Core ────────────────────────────────────────────────

    async def generate(self, messages: list[dict], **kwargs: Any) -> dict:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        model = kwargs.pop("model", self.config.get("model", "gemini-2.0-flash"))
        contents = self._to_gemini_contents(messages)
        response = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                temperature=kwargs.get("temperature", 0.7),
                max_output_tokens=kwargs.get("max_tokens", 8192),
            ),
        )
        return {
            "content": response.text or "",
            "model": model,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
            },
            "provider": self.name,
        }

    async def stream(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncGenerator[dict, None]:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        model = kwargs.pop("model", self.config.get("model", "gemini-2.0-flash"))
        contents = self._to_gemini_contents(messages)
        response = self._client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                temperature=kwargs.get("temperature", 0.7),
                max_output_tokens=kwargs.get("max_tokens", 8192),
            ),
        )
        for chunk in response:
            if chunk.text:
                yield {"type": "chunk", "content": chunk.text}
        yield {"type": "done", "content": "", "model": model}

    # ── Discovery ───────────────────────────────────────────

    async def models(self) -> list[dict]:
        if not self._client:
            raise RuntimeError("Provider not initialized")
        response = self._client.models.list()
        items = []
        for m in response:
            items.append({"id": m.name, "name": m.display_name or m.name, "created": ""})
        return items

    async def health(self) -> dict:
        try:
            if self._client:
                self._client.models.list()
            return {
                "status": "ok",
                "message": "Connected",
                "model": self.config.get("model", "gemini-2.0-flash"),
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "model": self.config.get("model", "gemini-2.0-flash")}

    # ── Metadata ────────────────────────────────────────────

    def provider_info(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "streaming": True,
            "tools": True,
            "models_endpoint": "https://generativelanguage.googleapis.com/v1/models",
            "website": "https://deepmind.google/gemini",
        }

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _to_gemini_contents(messages: list[dict]) -> list[genai_types.Content]:
        role_map = {"user": "user", "assistant": "model", "system": "user"}
        contents = []
        for m in messages:
            if m.get("role") == "system":
                continue
            role = role_map.get(m.get("role", "user"), "user")
            contents.append(
                genai_types.Content(
                    role=role,
                    parts=[genai_types.Part.from_text(text=m.get("content", ""))],
                )
            )
        return contents
