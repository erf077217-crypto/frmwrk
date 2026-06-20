import json
import os
import shlex
from pathlib import Path

import config
from platforms.factory import get_platform

platform = get_platform()

_host_prefix = config.HOST_MOUNT_PREFIX
_persistence_dir = Path(config.PERSISTENCE_DIR)
WORKSPACE_FILE = _persistence_dir / "workspace.json"


def _host_to_container(host_path: str) -> str:
    """Convert a host path to a container-local path by prepending the mount prefix."""
    path = host_path.strip().strip('"').strip("'")
    if path.startswith(_host_prefix):
        return path
    return f"{_host_prefix}{path}"


def _container_to_host(container_path: str) -> str:
    """Strip the mount prefix to recover the original host path for UI display."""
    if container_path.startswith(_host_prefix):
        return container_path[len(_host_prefix):]
    return container_path


def set_workspace(path: str) -> dict:
    host_path = path.strip().strip('"').strip("'")
    container_path = _host_to_container(host_path)

    result = platform.run(
        f'test -d {shlex.quote(container_path)} && echo OK || echo NOT_FOUND',
        timeout=10,
    )
    if "OK" not in result.stdout.strip():
        return {"success": False, "error": f"Directory not found or inaccessible: {host_path}"}

    data = {"workspace": container_path}
    try:
        _persistence_dir.mkdir(parents=True, exist_ok=True)
        WORKSPACE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except (OSError, PermissionError) as e:
        return {"success": False, "error": f"Cannot save workspace: {e}"}
    return {"success": True, "workspace": host_path}


def get_workspace() -> dict:
    if WORKSPACE_FILE.exists():
        try:
            data = json.loads(WORKSPACE_FILE.read_text(encoding='utf-8'))
            container_path = data.get("workspace")
            if container_path:
                return {"workspace": container_path}
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return {"workspace": None}


def get_workspace_display() -> dict:
    """Return workspace info with host-side paths suitable for UI display."""
    raw = get_workspace()
    container_path = raw.get("workspace")
    if container_path:
        return {"workspace": _container_to_host(container_path)}
    return {"workspace": None}
