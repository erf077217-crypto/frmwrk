import json
import time
from datetime import datetime, timezone
from pathlib import Path

STORE_DIR = Path(__file__).parent / "sessions"


def _ensure_dir():
    STORE_DIR.mkdir(exist_ok=True)


def _path(session_id: str) -> Path:
    return STORE_DIR / f"{session_id}.json"


def create_session(
    session_id: str,
    workspace: dict,
    port: int,
    model: str = "default",
) -> dict:
    _ensure_dir()
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "session_id": session_id,
        "workspace": workspace,
        "port": port,
        "model": model,
        "started_at": now,
        "finished_at": None,
        "archived": False,
        "metadata": {
            "total_prompts": 0,
        },
        "messages": [],
    }
    _path(session_id).write_text(json.dumps(data, indent=2))
    return data


def append_message(
    session_id: str,
    role: str,
    content: str,
) -> dict | None:
    path = _path(session_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "role": role,
        "content": content,
        "timestamp": now,
    }
    data["messages"].append(entry)
    if role == "user":
        data["metadata"]["total_prompts"] = data["metadata"].get("total_prompts", 0) + 1
    path.write_text(json.dumps(data, indent=2))
    return entry


def finalize_session(session_id: str) -> dict | None:
    path = _path(session_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    data["finished_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, indent=2))
    return data


def get_session(session_id: str) -> dict | None:
    path = _path(session_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_sessions() -> list[dict]:
    _ensure_dir()
    sessions = []
    for f in sorted(STORE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            sessions.append({
                "session_id": data["session_id"],
                "workspace": data.get("workspace", {}).get("workspace"),
                "started_at": data.get("started_at"),
                "finished_at": data.get("finished_at"),
                "archived": data.get("archived", False),
                "total_prompts": data.get("metadata", {}).get("total_prompts", 0),
                "total_messages": len(data.get("messages", [])),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return sessions


def archive_session(session_id: str) -> dict | None:
    path = _path(session_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    data["archived"] = True
    path.write_text(json.dumps(data, indent=2))
    return data


def delete_session(session_id: str) -> bool:
    path = _path(session_id)
    if not path.exists():
        return False
    path.unlink()
    return True
