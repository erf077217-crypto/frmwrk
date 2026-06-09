from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator


class BaseProvider(ABC):
    """Abstract interface every LLM provider must implement.

    Application code never imports a concrete provider — it works
    exclusively through this interface and the ``ProviderRegistry``.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    # ── Identity ────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name, e.g. 'openai', 'claude'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name, e.g. 'OpenAI', 'Anthropic Claude'."""

    # ── Lifecycle ───────────────────────────────────────────

    @abstractmethod
    async def initialize(self) -> None:
        """One-time setup (validate credentials, create client)."""

    @abstractmethod
    async def cleanup(self) -> None:
        """Release resources (close HTTP sessions, etc.)."""

    # ── Core Operations ─────────────────────────────────────

    @abstractmethod
    async def generate(self, messages: list[dict], **kwargs: Any) -> dict:
        """Send a chat-completion request and return the complete response.

        Parameters
        ----------
        messages : list[dict]
            Standard OpenAI-format message list
            ``[{"role": "user", "content": "..."}]``.
        **kwargs
            Per-provider parameters (model, temperature, max_tokens,
            stop sequences, etc.).

        Returns
        -------
        dict with keys:
          - ``"content"``  : str
          - ``"model"``    : str
          - ``"usage"``    : dict (prompt_tokens, completion_tokens)
          - ``"provider"`` : str
        """

    @abstractmethod
    async def stream(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncGenerator[dict, None]:
        """Stream a chat-completion response.

        Yields dicts with keys:
          - ``"type"``    : "chunk" | "done" | "error"
          - ``"content"`` : str
          - ``"model"``   : str (only on "done")

        The caller is responsible for iterating the generator
        and forwarding chunks to the client.
        """

    # ── Discovery ───────────────────────────────────────────

    @abstractmethod
    async def models(self) -> list[dict]:
        """Return available models for this provider.

        Returns a list of dicts:
          ``{"id": "...", "name": "...", "created": "..."}``
        """

    @abstractmethod
    async def health(self) -> dict:
        """Check provider connectivity.

        Returns a dict:
          ``{"status": "ok" | "error", "message": "...", "model": "..."}``
        """

    # ── Metadata ────────────────────────────────────────────

    @abstractmethod
    def provider_info(self) -> dict:
        """Return static metadata about this provider.

        Returns a dict with keys:
          ``name``, ``display_name``, ``streaming``, ``tools``,
          ``models_endpoint``, ``website``.
        """

    def __str__(self) -> str:
        return f"{self.display_name}"
