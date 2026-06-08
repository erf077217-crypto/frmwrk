from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import opencode_runner
import opencode_session as ocs
import workspace_manager as wm

app = FastAPI(title="Lazy Developer Loop Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health / diagnostics
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    wsl_available: bool
    opencode_available: bool
    tmux_available: bool


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        wsl_available=opencode_runner.check_wsl(),
        opencode_available=opencode_runner.check_opencode(),
        tmux_available=ocs.check_tmux(),
    )


@app.get("/diagnostics")
async def diagnostics():
    return opencode_runner.run_diagnostics()


# ---------------------------------------------------------------------------
# Legacy prompt endpoint
# ---------------------------------------------------------------------------


class PromptRequest(BaseModel):
    prompt: str


class PromptResponse(BaseModel):
    response: str
    success: bool


@app.post("/prompt", response_model=PromptResponse)
async def handle_prompt(req: PromptRequest):
    result = opencode_runner.run_opencode(req.prompt)
    return PromptResponse(**result)


# ---------------------------------------------------------------------------
# Workspace API
# ---------------------------------------------------------------------------


class WorkspaceRequest(BaseModel):
    path: str


@app.get("/workspace")
async def get_workspace():
    return wm.get_workspace()


@app.post("/workspace")
async def set_workspace(req: WorkspaceRequest):
    return wm.set_workspace(req.path)


# ---------------------------------------------------------------------------
# Session API  —  backed by TmuxSession + OpenCode
# ---------------------------------------------------------------------------


@app.post("/session/start")
async def session_start(session_id: str | None = Query(None)):
    return await ocs.start_session(session_id)


@app.post("/session/stop")
async def session_stop():
    return await ocs.stop_session()


class SessionPromptRequest(BaseModel):
    prompt: str


@app.post("/session/prompt")
async def session_prompt(req: SessionPromptRequest):
    return await ocs.send_prompt(req.prompt)


@app.get("/session/status")
async def session_status():
    return ocs.get_session_status()


@app.get("/session/preview")
async def session_preview(lines: int = Query(5, ge=1, le=50)):
    from tmux_session import get_active
    return {"preview": get_active().pane_preview(max_lines=lines)}


# ---------------------------------------------------------------------------
# Session history  —  sourced from OpenCode CLI
# ---------------------------------------------------------------------------


@app.get("/sessions")
async def list_sessions():
    return {"sessions": ocs.list_sessions()}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    data = ocs.get_session(session_id)
    if not data:
        return JSONResponse({"error": "session_not_found"}, status_code=404)
    return data


@app.post("/sessions/load/{session_id}")
async def load_session(session_id: str):
    return await ocs.load_session(session_id)


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    return {"success": True, "deleted": session_id}


# ---------------------------------------------------------------------------
# Terminal launch
# ---------------------------------------------------------------------------


@app.post("/terminal/open")
async def open_terminal():
    return ocs.open_terminal()
