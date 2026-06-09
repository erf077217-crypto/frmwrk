from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.api.streaming import streaming_response
from backend.core.registries import provider_registry
from backend.models.schemas import ChatRequest, ChatResponse
from providers.exceptions import ProviderError

logger = logging.getLogger("ai-platform.api.chat")
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat_completion(body: ChatRequest) -> ChatResponse:
    """Unified chat completion endpoint.

    Works with any registered provider.  Select the provider
    and model in the request body.
    """
    provider = provider_registry.require(body.provider)
    kwargs = _build_kwargs(body)

    try:
        result = await provider.generate(body.messages, **kwargs)
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=f"Provider unreachable: {e}")
    except Exception as e:
        logger.exception("Chat completion failed for %s", body.provider)
        raise HTTPException(status_code=500, detail=str(e))

    return ChatResponse(
        content=result["content"],
        model=result["model"],
        usage=result["usage"],
        provider=result["provider"],
    )


@router.post("/stream")
async def chat_stream(body: ChatRequest):
    """Unified streaming chat completion.

    Returns a Server-Sent Events (SSE) stream.  The same request
    format as the non-streaming endpoint with ``stream: true``.
    """
    provider = provider_registry.require(body.provider)
    if not provider.provider_info()["streaming"]:
        raise HTTPException(status_code=400, detail=f"Provider '{body.provider}' does not support streaming")

    kwargs = _build_kwargs(body)
    gen = provider.stream(body.messages, **kwargs)
    return streaming_response(body.provider, gen)


def _build_kwargs(body: ChatRequest) -> dict:
    kwargs = {}
    if body.model:
        kwargs["model"] = body.model
    if body.temperature is not None:
        kwargs["temperature"] = body.temperature
    if body.max_tokens is not None:
        kwargs["max_tokens"] = body.max_tokens
    return kwargs
