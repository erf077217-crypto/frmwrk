from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from fastapi.responses import StreamingResponse

logger = logging.getLogger("ai-platform.streaming")

SSE_MEDIA_TYPE = "text/event-stream"


def sse_format(event: str, data: object) -> str:
    """Format a Server-Sent Event message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_generator(
    provider_name: str,
    message_generator: AsyncGenerator[dict, None],
) -> AsyncGenerator[bytes, None]:
    """Wrap a provider's stream() output into SSE bytes.

    Yields ``event: chunk`` for each content fragment and
    ``event: done`` when finished.
    """
    try:
        async for chunk in message_generator:
            if chunk["type"] == "chunk":
                yield sse_format("chunk", {"content": chunk["content"]}).encode()
            elif chunk["type"] == "done":
                yield sse_format("done", {"provider": provider_name, "model": chunk.get("model", "")}).encode()
                return
    except Exception as exc:
        logger.exception("Stream error for %s", provider_name)
        yield sse_format("error", {"message": str(exc)}).encode()


def streaming_response(
    provider_name: str,
    message_generator: AsyncGenerator[dict, None],
) -> StreamingResponse:
    """Create a StreamingResponse from a provider's stream generator."""
    return StreamingResponse(
        stream_generator(provider_name, message_generator),
        media_type=SSE_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
