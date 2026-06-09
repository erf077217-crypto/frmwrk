from fastapi import APIRouter

from backend.core.registries import agent_registry
from backend.models.schemas import AgentListResponse

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    return AgentListResponse(agents=agent_registry.list())
