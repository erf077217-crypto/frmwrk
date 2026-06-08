import asyncio
import re
import shlex
import time
import uuid

import config


_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


class Session:
    def __init__(self, session_id: str, prompt: str):
        self.session_id = session_id
        self.prompt = prompt
        self.process: asyncio.subprocess.Process | None = None
        self.output_lines: list[str] = []
        self.raw_output: list[str] = []
        self.started_at: float = time.time()
        self.last_active: float = time.time()
        self.finished: bool = False
        self.returncode: int | None = None
        self._read_task: asyncio.Task | None = None
        self._websockets: set = set()

    @property
    def age(self) -> float:
        return time.time() - self.started_at

    def add_websocket(self, ws):
        self._websockets.add(ws)

    def remove_websocket(self, ws):
        self._websockets.discard(ws)


_session_map: dict[str, Session] = {}
_CLEANUP_INTERVAL = 60
_SESSION_TTL = 300


def _build_wsl_cmd(inner: str) -> list[str]:
    flag = "-ic" if config.USE_INTERACTIVE_SHELL else "-lc"
    cmd = ["wsl.exe"]
    if config.WSL_DISTRO:
        cmd.extend(["-d", config.WSL_DISTRO])
    cmd.extend(["bash", flag, inner])
    return cmd


async def start_session(prompt: str) -> str:
    session_id = uuid.uuid4().hex[:12]
    session = Session(session_id, prompt)

    inner_cmd = f"{config.OPENCODE_COMMAND} run {shlex.quote(prompt)}"
    script_cmd = f"script -qfc {shlex.quote(inner_cmd)} /dev/null"
    cmd = _build_wsl_cmd(script_cmd)

    session.process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    session._read_task = asyncio.create_task(_read_output(session))
    _session_map[session_id] = session

    return session_id


def get_session(session_id: str) -> Session | None:
    return _session_map.get(session_id)


def list_sessions() -> list[dict]:
    return [
        {
            "session_id": s.session_id,
            "prompt": s.prompt[:80],
            "finished": s.finished,
            "started_at": s.started_at,
        }
        for s in _session_map.values()
    ]


async def stop_session(session_id: str) -> bool:
    session = _session_map.get(session_id)
    if not session:
        return False
    if session.process and session.process.returncode is None:
        session.process.terminate()
        try:
            await asyncio.wait_for(session.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            session.process.kill()
            await session.process.wait()
    if session._read_task:
        session._read_task.cancel()
    return True


def remove_session(session_id: str) -> bool:
    return _session_map.pop(session_id, None) is not None


def get_full_output(session: Session) -> str:
    return "\n".join(session.output_lines)


async def _read_output(session: Session) -> None:
    line_buffer = ""
    try:
        while True:
            data = await session.process.stdout.read(4096)
            if not data:
                break
            decoded = data.decode("utf-8", errors="replace")
            session.raw_output.append(decoded)
            session.last_active = time.time()

            clean_chunk = strip_ansi(decoded)
            line_buffer += clean_chunk
            while "\n" in line_buffer:
                line, line_buffer = line_buffer.split("\n", 1)
                session.output_lines.append(line)

            await _broadcast(session, {
                "type": "output",
                "raw": decoded,
                "clean": clean_chunk,
            })
    except Exception:
        pass
    finally:
        if line_buffer:
            session.output_lines.append(line_buffer)
        session.returncode = await session.process.wait()
        session.finished = True
        await _broadcast(session, {
            "type": "done",
            "returncode": session.returncode,
        })


async def _broadcast(session: Session, data: dict) -> None:
    dead = set()
    for ws in list(session._websockets):
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    session._websockets -= dead


async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        now = time.time()
        stale = [
            sid
            for sid, s in _session_map.items()
            if s.finished and (now - s.last_active) > _SESSION_TTL
        ]
        for sid in stale:
            _session_map.pop(sid, None)
