import os

OPENCODE_COMMAND = os.environ.get("OPENCODE_COMMAND", "opencode")

RUN_TIMEOUT = int(os.environ.get("RUN_TIMEOUT", "120"))

USE_INTERACTIVE_SHELL = False

DEBUG_OUTPUT = os.environ.get("DEBUG_OUTPUT", "true").lower() in ("1", "true", "yes")

TMUX_SESSION_NAME = os.environ.get("TMUX_SESSION_NAME", "lazy-dev-loop")

WORKSPACE_PATH = os.environ.get("WORKSPACE_PATH", "/workspace")
