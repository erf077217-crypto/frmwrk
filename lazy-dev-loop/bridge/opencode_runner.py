import shlex
import subprocess

import config


def run_opencode(prompt: str, timeout: int | None = None) -> dict:
    if timeout is None:
        timeout = config.RUN_TIMEOUT

    cmd = _build_wsl_cmd(f"{config.OPENCODE_COMMAND} run {shlex.quote(prompt)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding='utf-8',
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "response": f"OpenCode timed out after {timeout} seconds.",
            "success": False,
        }
    except FileNotFoundError:
        return {
            "response": (
                "wsl.exe not found. Make sure WSL is installed.\n\n"
                "Run: wsl --install\n"
                "See: https://learn.microsoft.com/en-us/windows/wsl/install"
            ),
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
    try:
        subprocess.run(
            ["wsl.exe", "--status"],
            capture_output=True,
            timeout=10,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_opencode() -> bool:
    return find_opencode_path() is not None


def find_opencode_path() -> str | None:
    candidates = [
        f"command -v {config.OPENCODE_COMMAND}",
        f"which {config.OPENCODE_COMMAND}",
        f"source ~/.bashrc >/dev/null 2>&1 && command -v {config.OPENCODE_COMMAND}",
    ]
    for candidate in candidates:
        cmd = _build_wsl_cmd(candidate)
        try:
            result = subprocess.run(cmd, capture_output=True, encoding='utf-8', timeout=10)
            path = result.stdout.strip()
            if path:
                return path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return None


def run_diagnostics() -> dict:
    _shell_flag = "-ic" if config.USE_INTERACTIVE_SHELL else "-lc"
    out: dict = {}

    whoami_healthy = _run_wsl("whoami", _shell_flag)
    out["whoami"] = whoami_healthy.get("stdout", whoami_healthy.get("error", ""))

    out["pwd"] = _run_wsl("pwd", _shell_flag).get("stdout", "")
    out["path"] = _run_wsl("echo $PATH", _shell_flag).get("stdout", "")
    out["command_v"] = _run_wsl("command -v opencode", _shell_flag)
    out["which_opencode"] = _run_wsl("which opencode", _shell_flag)
    out["type_opencode"] = _run_wsl("type opencode", _shell_flag)

    out["shell_mode_comparison"] = {}
    for flag in ["-lc", "-ic"]:
        key = f"bash_{flag}"
        out["shell_mode_comparison"][key] = {
            "command_v": _run_wsl("command -v opencode", flag),
            "which": _run_wsl("which opencode", flag),
            "whoami": _run_wsl("whoami", flag),
        }

    out["user_mismatch"] = {
        "health_check_whoami": out.get("whoami", ""),
        "shell_mode_whoami": {
            k: v.get("whoami", {}).get("stdout", "")
            if isinstance(v, dict) and "whoami" in v
            else v.get("stdout", "")
            for k, v in out.get("shell_mode_comparison", {}).items()
        },
    }

    discovered = find_opencode_path()
    out["discovered_opencode_path"] = discovered

    return out


def _run_wsl(command: str, shell_flag: str | None = None) -> dict:
    cmd = _build_wsl_cmd(command, shell_flag=shell_flag)
    try:
        result = subprocess.run(cmd, capture_output=True, encoding='utf-8', timeout=10)
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except FileNotFoundError:
        return {"error": "wsl.exe not found"}
    except Exception as e:
        return {"error": str(e)}


def _build_wsl_cmd(inner: str, shell_flag: str | None = None) -> list[str]:
    flag = shell_flag or ("-ic" if config.USE_INTERACTIVE_SHELL else "-lc")
    cmd = ["wsl.exe"]
    if config.WSL_DISTRO:
        cmd.extend(["-d", config.WSL_DISTRO])
    cmd.extend(["bash", flag, inner])
    return cmd
