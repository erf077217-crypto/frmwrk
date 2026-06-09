from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.core.registries import provider_registry
from backend.models.schemas import (
    ModelListResponse,
    ProviderListResponse,
    ProviderStatus,
    ProviderStatusListResponse,
)

logger = logging.getLogger("ai-platform.api.providers")
router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=ProviderListResponse)
async def list_providers() -> ProviderListResponse:
    return ProviderListResponse(providers=provider_registry.list())


@router.get("/status", response_model=ProviderStatusListResponse)
async def provider_status() -> ProviderStatusListResponse:
    """Return live health status for all registered providers."""
    statuses: list[ProviderStatus] = []
    for p in provider_registry:
        try:
            h = await p.health()
            statuses.append(
                ProviderStatus(
                    name=p.name,
                    display_name=p.display_name,
                    status=h.get("status", "error"),
                    message=h.get("message", ""),
                    model=h.get("model", ""),
                )
            )
        except Exception as e:
            logger.warning("Health check failed for %s: %s", p.name, e)
            statuses.append(
                ProviderStatus(
                    name=p.name,
                    display_name=p.display_name,
                    status="error",
                    message=str(e),
                    model="",
                )
            )
    return ProviderStatusListResponse(providers=statuses)


@router.get("/{provider_name}/models", response_model=ModelListResponse)
async def provider_models(provider_name: str) -> ModelListResponse:
    """Return available models for a specific provider."""
    provider = provider_registry.get(provider_name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_name}")
    try:
        models = await provider.models()
    except Exception as e:
        logger.warning("Failed to list models for %s: %s", provider_name, e)
        raise HTTPException(status_code=502, detail=str(e))
    return ModelListResponse(provider=provider_name, models=models)


@router.get("/{provider_name}/health", response_model=ProviderStatus)
async def provider_health(provider_name: str) -> ProviderStatus:
    """Return live health for a single provider."""
    provider = provider_registry.get(provider_name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_name}")
    try:
        h = await provider.health()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return ProviderStatus(
        name=provider.name,
        display_name=provider.display_name,
        status=h.get("status", "error"),
        message=h.get("message", ""),
        model=h.get("model", ""),
    )
