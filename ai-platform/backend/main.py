from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import api_router
from backend.core.logging import configure_logging
from backend.core.registries import (
    build_default_registries,
    provider_registry,
)
from backend.core.startup import run_startup_checks
from configs import settings

logger = logging.getLogger("ai-platform")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level, settings.log_json)
    run_startup_checks()
    build_default_registries(settings)

    # Initialize all registered providers
    initialized = 0
    for p in provider_registry:
        try:
            await p.initialize()
            initialized += 1
            logger.info("Provider initialized: %s (%s)", p.display_name, p.name)
        except Exception as e:
            logger.warning("Provider %s failed to initialize: %s", p.name, e)

    logger.info("Startup complete: providers=%d/%d, agents=%d, tools=%d",
                initialized, len(provider_registry),
                len(provider_registry),  # agents will be separate
                5)  # tools
    yield

    # Cleanup all providers
    for p in provider_registry:
        try:
            await p.cleanup()
        except Exception as e:
            logger.warning("Provider %s cleanup error: %s", p.name, e)
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
