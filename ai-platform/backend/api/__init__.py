from fastapi import APIRouter

from .agents import router as agents_router
from .chat import router as chat_router
from .health import router as health_router
from .providers import router as providers_router
from .tools import router as tools_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(providers_router)
api_router.include_router(chat_router)
api_router.include_router(agents_router)
api_router.include_router(tools_router)
