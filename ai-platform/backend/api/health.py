from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.core.registries import agent_registry, provider_registry, tool_registry
from backend.core.startup import validate_environment
from backend.models.schemas import HealthResponse
from configs import settings

logger = logging.getLogger("ai-platform.api")
router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    warnings = validate_environment()

    provider_statuses = {}
    for p in provider_registry:
        try:
            h = await p.health()
            provider_statuses[p.name] = h.get("status", "error")
        except Exception:
            provider_statuses[p.name] = "error"

    return HealthResponse(
        status="ok" if not warnings and "error" not in provider_statuses.values() else "degraded",
        providers_registered=len(provider_registry),
        agents_registered=len(agent_registry),
        tools_registered=len(tool_registry),
        diagnostics={
            "warnings": warnings,
            "providers_configured": settings.provider_keys_present,
            "provider_health": provider_statuses,
            "log_level": settings.log_level,
            "debug": settings.debug,
        },
    )
