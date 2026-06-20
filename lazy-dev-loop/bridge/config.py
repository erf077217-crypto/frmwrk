import os

OPENCODE_COMMAND = os.environ.get("OPENCODE_COMMAND", "opencode")

RUN_TIMEOUT = int(os.environ.get("RUN_TIMEOUT", "120"))

USE_INTERACTIVE_SHELL = False

DEBUG_OUTPUT = os.environ.get("DEBUG_OUTPUT", "true").lower() in ("1", "true", "yes")

TMUX_SESSION_NAME = os.environ.get("TMUX_SESSION_NAME", "lazy-dev-loop")

HOST_MOUNT_PREFIX = "/host"

PERSISTENCE_DIR = os.environ.get(
    "PERSISTENCE_DIR",
    "/home/app/.local/share/lazy-dev-loop",
)
