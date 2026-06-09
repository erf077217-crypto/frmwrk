from fastapi import APIRouter, HTTPException

from backend.core.registries import tool_registry
from backend.models.schemas import ToolExecuteRequest, ToolExecuteResponse, ToolListResponse

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    return ToolListResponse(tools=tool_registry.list())


@router.post("/{name}/execute", response_model=ToolExecuteResponse)
async def execute_tool(name: str, body: ToolExecuteRequest) -> ToolExecuteResponse:
    tool = tool_registry.get(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")
    try:
        result = await tool.execute(**body.args)
        return ToolExecuteResponse(
            name=name,
            success=result.get("success", False),
            output=result.get("output"),
            error=result.get("error"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
