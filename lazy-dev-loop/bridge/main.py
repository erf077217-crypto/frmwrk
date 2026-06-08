import asyncio
import json

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import opencode_runner
import session_manager
import workspace_manager as wm
import opencode_session as ocs
from session_manager import strip_ansi

app = FastAPI(title="Lazy Developer Loop Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    asyncio.create_task(session_manager.cleanup_loop())


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
# Health / diagnostics
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    wsl_available: bool
    opencode_available: bool


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        wsl_available=opencode_runner.check_wsl(),
        opencode_available=opencode_runner.check_opencode(),
    )


@app.get("/diagnostics")
async def diagnostics():
    return opencode_runner.run_diagnostics()


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
# Persistent Session API
# ---------------------------------------------------------------------------


class SessionStartResponse(BaseModel):
    success: bool
    session_id: str | None = None
    port: int | None = None
    pid: int | None = None
    error: str | None = None
    workspace: dict | None = None


@app.post("/session/start", response_model=SessionStartResponse)
async def session_start():
    result = await ocs.start_session()
    return SessionStartResponse(**result)


class SessionStopResponse(BaseModel):
    success: bool
    session_id: str | None = None


@app.post("/session/stop")
async def session_stop():
    result = await ocs.stop_session()
    return result


class SessionPromptRequest(BaseModel):
    prompt: str


class SessionPromptResponse(BaseModel):
    success: bool
    output: str = ""
    error: str | None = None
    returncode: int | None = None


@app.post("/session/prompt", response_model=SessionPromptResponse)
async def session_prompt(req: SessionPromptRequest):
    result = await ocs.send_prompt(req.prompt)
    return SessionPromptResponse(**result)


@app.get("/session/status")
async def session_status():
    return ocs.get_session_status()


@app.get("/session/list")
async def session_list():
    return {"sessions": [ocs.get_session_status()]}


# ---------------------------------------------------------------------------
# Terminal launch
# ---------------------------------------------------------------------------


@app.post("/terminal/open")
async def open_terminal():
    return ocs.open_terminal()


# ---------------------------------------------------------------------------
# Legacy session API (backward compat)
# ---------------------------------------------------------------------------


class LegacySessionStartRequest(BaseModel):
    prompt: str


@app.post("/legacy/session/start")
async def legacy_session_start(req: LegacySessionStartRequest):
    session_id = await session_manager.start_session(req.prompt)
    return {"session_id": session_id}


@app.post("/legacy/session/stop")
async def legacy_session_stop(session_id: str = Query(...)):
    ok = await session_manager.stop_session(session_id)
    if not ok:
        return JSONResponse({"error": "session_not_found"}, status_code=404)
    return {"stopped": True}


@app.get("/legacy/session/output")
async def legacy_session_output(session_id: str = Query(...), since: int = Query(0)):
    session = session_manager.get_session(session_id)
    if not session:
        return JSONResponse({"error": "session_not_found"}, status_code=404)
    recent = session.output_lines[since:]
    return {
        "session_id": session_id,
        "lines": recent,
        "total_lines": len(session.output_lines),
        "finished": session.finished,
        "returncode": session.returncode,
    }


@app.get("/legacy/session/stream")
async def legacy_session_stream(session_id: str = Query(...)):
    session = session_manager.get_session(session_id)
    if not session:
        return JSONResponse({"error": "session_not_found"}, status_code=404)

    async def event_gen():
        last_index = 0
        while True:
            new_lines = session.output_lines[last_index:]
            if new_lines:
                last_index = len(session.output_lines)
                yield f"data: {json.dumps({'lines': new_lines})}\n\n"
            if session.finished:
                yield f"data: {json.dumps({'finished': True, 'returncode': session.returncode})}\n\n"
                break
            await asyncio.sleep(0.2)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# WebSocket — legacy PTY output
# ---------------------------------------------------------------------------


@app.websocket("/legacy/ws/session/{session_id}")
async def legacy_session_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = session_manager.get_session(session_id)
    if not session:
        await websocket.send_json({"type": "error", "message": "session_not_found"})
        await websocket.close()
        return
    session.add_websocket(websocket)
    try:
        for chunk in session.raw_output:
            await websocket.send_json({
                "type": "output",
                "raw": chunk,
                "clean": strip_ansi(chunk),
            })
        if session.finished:
            await websocket.send_json({
                "type": "done",
                "returncode": session.returncode,
            })
            return
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        session.remove_websocket(websocket)


# ---------------------------------------------------------------------------
# Legacy session listing
# ---------------------------------------------------------------------------


@app.get("/legacy/sessions")
async def legacy_sessions():
    return {
        "total": len(session_manager._session_map),
        "finished": sum(1 for s in session_manager._session_map.values() if s.finished),
        "active": len(session_manager._session_map) - sum(1 for s in session_manager._session_map.values() if s.finished),
    }
