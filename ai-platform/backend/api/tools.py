from fastapi import APIRouter

from backend.core.registries import tool_registry
from backend.models.schemas import ToolListResponse

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    return ToolListResponse(tools=tool_registry.list())
