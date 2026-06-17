from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
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
    opencode_available: bool
    tmux_available: bool


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        opencode_available=opencode_runner.check_opencode(),
        tmux_available=ocs.check_tmux(),
    )


@app.get("/session/health")
async def session_health():
    return ocs.check_session_health()


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
    mode: str = "summary"


@app.post("/session/prompt")
async def session_prompt(req: SessionPromptRequest):
    return ocs.start_prompt_background(req.prompt, mode=req.mode)


@app.get("/session/fetch-response")
async def session_fetch_response():
    """Manually fetch the latest assistant response from OpenCode.

    Pure read — no side effects.  Works independently of any polling.
    Returns the most recent assistant message content via opencode export.
    """
    status = ocs.get_session_status()
    sid = status.get("session_id")
    if not sid or not status.get("active"):
        return {"success": False, "error": "No active OpenCode session"}
    return ocs.get_latest_response(sid)


@app.get("/session/status")
async def session_status():
    return ocs.get_session_status()


@app.get("/session/preview")
async def session_preview(lines: int = Query(5, ge=1, le=50)):
    from tmux_session import get_active
    return {"preview": get_active().pane_preview(max_lines=lines)}


# ---------------------------------------------------------------------------
# Terminal launch
# ---------------------------------------------------------------------------


@app.post("/terminal/open")
async def open_terminal():
    return ocs.open_terminal()


# ---------------------------------------------------------------------------
# Debug logging toggle (runtime flag, no restart required)
# ---------------------------------------------------------------------------


@app.get("/debug/status")
async def debug_status():
    return {"enabled": ocs.is_debug_enabled()}


@app.post("/debug/enable")
async def debug_enable():
    ocs.set_debug(True)
    return {"enabled": True}


@app.post("/debug/disable")
async def debug_disable():
    ocs.set_debug(False)
    return {"enabled": False}


# ---------------------------------------------------------------------------
# Debug / diagnostics
# ---------------------------------------------------------------------------


@app.get("/debug/session")
async def debug_session():
    from tmux_session import _active, _current_session_id, TMUX_SESSION_NAME, _session_export

    oc_id = _current_session_id
    tmux_alive = _active.active

    opencode_data = None
    if oc_id:
        opencode_data = _session_export(oc_id)

    return {
        "opencode": {
            "session_id": oc_id,
            "export": opencode_data,
        },
        "tmux": {
            "session_name": TMUX_SESSION_NAME,
            "alive": tmux_alive,
        },
        "bridge": {
            "session_id": oc_id,
            "active": tmux_alive,
        },
        "workspace": wm.get_workspace(),
    }
