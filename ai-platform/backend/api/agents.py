from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.registries import agent_registry
from backend.models.schemas import AgentListResponse

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentExecuteRequest(BaseModel):
    task: str = Field(description="Natural language task description.")
    provider: str | None = Field(default=None, description="Provider name override.")
    model: str | None = Field(default=None, description="Model override.")


class AgentExecuteResponse(BaseModel):
    status: str
    output: str
    metadata: dict


@router.get("", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    return AgentListResponse(agents=agent_registry.list())


@router.post("/{name}/execute", response_model=AgentExecuteResponse)
async def execute_agent(name: str, body: AgentExecuteRequest) -> AgentExecuteResponse:
    agent = agent_registry.get(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    try:
        result = await agent.run(body.task, provider_name=body.provider, model=body.model)
        return AgentExecuteResponse(
            status=result.get("status", "error"),
            output=result.get("output", ""),
            metadata=result.get("metadata", {}),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
