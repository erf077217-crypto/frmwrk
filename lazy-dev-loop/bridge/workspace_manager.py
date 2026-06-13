import json
import re
import shlex
import subprocess
from pathlib import Path

import config

WORKSPACE_FILE = Path(__file__).parent / "workspace.json"

_WIN_PATH_RE = re.compile(r'^([a-zA-Z]):\\(.*)')


def win_to_wsl_path(win_path: str) -> str:
    match = _WIN_PATH_RE.match(win_path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace('\\', '/')
        return f"/mnt/{drive}/{rest}"
    return win_path


def wsl_to_win_path(wsl_path: str) -> str:
    match = re.match(r'^/mnt/([a-z])/(.*)', wsl_path)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2).replace('/', '\\')
        return f"{drive}:\\{rest}"
    if wsl_path.startswith('/home/'):
        return wsl_path
    return wsl_path


def normalize_path(path: str) -> str:
    path = path.strip().strip('"').strip("'")
    if path.startswith('/'):
        return wsl_to_win_path(path)
    return path


def set_workspace(win_path: str) -> dict:
    win_path = normalize_path(win_path)
    wsl_path = win_to_wsl_path(win_path)
    cmd = ["wsl.exe"]
    if config.WSL_DISTRO:
        cmd.extend(["-d", config.WSL_DISTRO])
    cmd.extend(["bash", "-ic", f'test -d {shlex.quote(wsl_path)} && echo OK || echo NOT_FOUND'])
    try:
        result = subprocess.run(cmd, capture_output=True, encoding='utf-8', timeout=10)
        if "OK" not in result.stdout.strip():
            return {"success": False, "error": f"Directory not found or inaccessible: {win_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    data = {"workspace": win_path, "wsl_path": wsl_path}
    WORKSPACE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
    return {"success": True, "workspace": win_path, "wsl_path": wsl_path}


def get_workspace() -> dict:
    if WORKSPACE_FILE.exists():
        try:
            data = json.loads(WORKSPACE_FILE.read_text(encoding='utf-8'))
            return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"workspace": None, "wsl_path": None}
