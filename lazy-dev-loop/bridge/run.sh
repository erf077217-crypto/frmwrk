#!/usr/bin/env bash
# Lazy Developer Loop — Bridge startup script
# Works in Git Bash, WSL, and other Unix-like shells on Windows.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_MODULE="main:app"
HOST="0.0.0.0"
PORT=7777

# Try known venv locations relative to the repo root
VENV_PATHS=(
  "$SCRIPT_DIR/../../.venv/Scripts/uvicorn.exe"
  "$SCRIPT_DIR/../../.venv/bin/uvicorn"
  "$SCRIPT_DIR/../../venv/Scripts/uvicorn.exe"
  "$SCRIPT_DIR/../../venv/bin/uvicorn"
)

UVIOCRN_CMD=""
for candidate in "${VENV_PATHS[@]}"; do
  if [ -x "$candidate" ]; then
    UVICORN_CMD="$candidate"
    break
  fi
done

# Fallback: try PATH
if [ -z "$UVICORN_CMD" ]; then
  if command -v uvicorn &>/dev/null; then
    UVICORN_CMD="uvicorn"
  else
    echo "ERROR: uvicorn not found."
    echo ""
    echo "  Tried:"
    for p in "${VENV_PATHS[@]}"; do echo "    $p"; done
    echo ""
    echo "  Activate your venv or install dependencies:"
    echo "    pip install -r \"$SCRIPT_DIR/requirements.txt\""
    exit 1
  fi
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

exec "$UVICORN_CMD" "$APP_MODULE" --host "$HOST" --port "$PORT"
