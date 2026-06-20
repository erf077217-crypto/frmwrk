import json
import os
import shlex
from pathlib import Path

import config
from platforms.factory import get_platform

platform = get_platform()

WORKSPACE_FILE = Path(config.WORKSPACE_PATH) / ".lazy-dev-loop-workspace.json"

WORKSPACE_DIRS = [
    config.WORKSPACE_PATH,
    "/workspace",
]


def set_workspace(path: str) -> dict:
    path = path.strip().strip('"').strip("'")

    result = platform.run(
        f'test -d {shlex.quote(path)} && echo OK || echo NOT_FOUND',
        timeout=10,
    )
    if "OK" not in result.stdout.strip():
        return {"success": False, "error": f"Directory not found or inaccessible: {path}"}

    data = {"workspace": path}
    try:
        WORKSPACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        WORKSPACE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except (OSError, PermissionError) as e:
        return {"success": False, "error": f"Cannot save workspace: {e}"}
    return {"success": True, "workspace": path}


def get_workspace() -> dict:
    if WORKSPACE_FILE.exists():
        try:
            data = json.loads(WORKSPACE_FILE.read_text(encoding='utf-8'))
            if data.get("workspace"):
                return data
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    for d in WORKSPACE_DIRS:
        if os.path.isdir(d):
            return {"workspace": d}
    return {"workspace": None}
