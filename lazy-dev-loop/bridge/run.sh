#!/usr/bin/env bash
# Lazy Developer Loop — Bridge startup script (Linux)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_MODULE="main:app"
HOST="0.0.0.0"
PORT="${BRIDGE_PORT:-7777}"

# ── Pre-flight checks ─────────────────────────────────────────────────

check_dep() {
  if ! command -v "$1" &>/dev/null; then
    echo "ERROR: Required dependency '$1' is not installed."
    echo "  Install it with your package manager, e.g.:"
    echo "    sudo apt install $1"
    exit 1
  fi
}

check_dep python3
check_dep tmux

# ── Python venv detection ─────────────────────────────────────────────

# Locate the virtual environment root (look from script dir up to filesystem root)
find_venv_root() {
  local dir="$SCRIPT_DIR"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/pyproject.toml" || -f "$dir/requirements.txt" || -f "$dir/setup.py" || -f "$dir/setup.cfg" ]]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  # Fallback: assume the repo root is two levels up from bridge/
  echo "$(cd "$SCRIPT_DIR/../.." && pwd)"
}

VENV_ROOT="$(find_venv_root)"
VENV_DIR="${VENV_DIR:-$VENV_ROOT/.venv}"

UVICORN_CMD=""
VENV_UVICORN="$VENV_DIR/bin/uvicorn"
if [ -x "$VENV_UVICORN" ]; then
  UVICORN_CMD="$VENV_UVICORN"
fi

# Fallback: try PATH
if [ -z "$UVICORN_CMD" ]; then
  if command -v uvicorn &>/dev/null; then
    UVICORN_CMD="uvicorn"
  fi
fi

if [ -z "$UVICORN_CMD" ]; then
  echo "ERROR: uvicorn not found."
  echo ""
  echo "  Expected at: $VENV_UVICORN"
  echo "  Also checked: PATH"
  echo ""
  echo "  Create and activate a virtual environment:"
  echo "    python3 -m venv \"$VENV_DIR\""
  echo "    source \"$VENV_DIR/bin/activate\""
  echo "    pip install -r \"$SCRIPT_DIR/requirements.txt\""
  echo ""
  echo "  Or set VENV_DIR to point to your venv."
  exit 1
fi

echo "============================================"
echo "  Lazy Developer Loop Bridge"
echo "============================================"
echo "  Module : $APP_MODULE"
echo "  Host   : $HOST"
echo "  Port   : $PORT"
echo "  Uvicorn: $UVICORN_CMD"
echo "============================================"
echo ""

# Release port if already in use
if command -v fuser &>/dev/null; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
fi

exec "$UVICORN_CMD" "$APP_MODULE" --host "$HOST" --port "$PORT"
