import shlex
import shutil
import subprocess

import config
from platforms.factory import get_platform

platform = get_platform()


def _resolve_cmd() -> str:
    cmd = config.OPENCODE_COMMAND
    if '/' not in cmd:
        resolved = shutil.which(cmd)
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


def check_opencode() -> bool:
    return shutil.which(config.OPENCODE_COMMAND) is not None


def run_diagnostics() -> dict:
    out: dict = {}

    whoami_healthy = _run_cmd("whoami")
    out["whoami"] = whoami_healthy.get("stdout", whoami_healthy.get("error", ""))

    out["pwd"] = _run_cmd("pwd").get("stdout", "")
    out["path"] = _run_cmd("echo $PATH").get("stdout", "")
    out["opencode_path"] = shutil.which(config.OPENCODE_COMMAND)

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
