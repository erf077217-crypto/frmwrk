import json
import shlex
from pathlib import Path

from platforms.factory import get_platform

platform = get_platform()

WORKSPACE_FILE = Path(__file__).parent / "workspace.json"


def set_workspace(path: str) -> dict:
    path = path.strip().strip('"').strip("'")
    exec_path = platform.to_exec_path(path)

    result = platform.run(
        f'test -d {shlex.quote(exec_path)} && echo OK || echo NOT_FOUND',
        timeout=10,
    )
    if "OK" not in result.stdout.strip():
        return {"success": False, "error": f"Directory not found or inaccessible: {path}"}

    host_path = platform.to_host_path(exec_path)
    data = {"workspace": host_path, "wsl_path": exec_path}
    WORKSPACE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
    return {"success": True, "workspace": host_path, "wsl_path": exec_path}


def get_workspace() -> dict:
    if WORKSPACE_FILE.exists():
        try:
            data = json.loads(WORKSPACE_FILE.read_text(encoding='utf-8'))
            return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"workspace": None, "wsl_path": None}
