import shlex
import subprocess

import config
from platforms.factory import get_platform

platform = get_platform()


def _resolve_cmd() -> str:
    cmd = config.OPENCODE_COMMAND
    if '/' not in cmd:
        resolver = getattr(platform, '_resolve_command', None)
        if resolver:
            resolved = resolver(cmd)
            if resolved:
                return resolved
    return cmd


def run_opencode(prompt: str, timeout: int | None = None) -> dict:
    if timeout is None:
        timeout = config.RUN_TIMEOUT

    try:
        result = platform.run(
            f"{_resolve_cmd()} run {shlex.quote(prompt)}",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "response": f"OpenCode timed out after {timeout} seconds.",
            "success": False,
        }
    except FileNotFoundError:
        return {
            "response": platform.env_not_found_message,
            "success": False,
        }
    except Exception as e:
        return {
            "response": f"Unexpected error while running OpenCode: {e}",
            "success": False,
        }

    output = result.stdout.strip()
    if result.stderr:
        err = result.stderr.strip()
        if output:
            output += "\n\n--- stderr ---\n" + err
        else:
            output = err

    if result.returncode != 0:
        return {
            "response": output or f"OpenCode exited with code {result.returncode}.",
            "success": False,
        }

    return {"response": output or "(no output)", "success": True}


def check_wsl() -> bool:
    return platform.is_available()


def check_opencode() -> bool:
    return find_opencode_path() is not None


def find_opencode_path() -> str | None:
    candidates = [
        f"command -v {config.OPENCODE_COMMAND}",
        f"which {config.OPENCODE_COMMAND}",
        f"source ~/.bashrc >/dev/null 2>&1 && command -v {config.OPENCODE_COMMAND}",
    ]
    for candidate in candidates:
        try:
            result = platform.run(candidate, timeout=10)
            path = result.stdout.strip()
            if path:
                return path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    if hasattr(platform, '_resolve_command'):
        path = platform._resolve_command(config.OPENCODE_COMMAND)
        if path:
            return path
    return None


def run_diagnostics() -> dict:
    out: dict = {}

    whoami_healthy = _run_cmd("whoami")
    out["whoami"] = whoami_healthy.get("stdout", whoami_healthy.get("error", ""))

    out["pwd"] = _run_cmd("pwd").get("stdout", "")
    out["path"] = _run_cmd("echo $PATH").get("stdout", "")
    out["command_v"] = _run_cmd("command -v opencode")
    out["which_opencode"] = _run_cmd("which opencode")
    out["type_opencode"] = _run_cmd("type opencode")

    for flag in ["-lc", "-ic"]:
        key = f"bash_{flag}"
        if key not in out:
            out[key] = {}
        for sub_cmd in ["command -v opencode", "which opencode", "whoami"]:
            out[key][sub_cmd] = _run_cmd(sub_cmd)

    out["user_mismatch"] = {
        "health_check_whoami": out.get("whoami", ""),
    }

    discovered = find_opencode_path()
    out["discovered_opencode_path"] = discovered

    return out


def _run_cmd(command: str) -> dict:
    try:
        result = platform.run(command, timeout=10)
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except FileNotFoundError:
        return {"error": platform.env_not_found_message}
    except Exception as e:
        return {"error": str(e)}
