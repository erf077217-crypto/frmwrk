#!/usr/bin/env bash
set -euo pipefail

APP_MODULE="main:app"
HOST="0.0.0.0"
PORT="${BRIDGE_PORT:-7777}"

echo "============================================"
echo "  Lazy Developer Loop Bridge (Docker)"
echo "============================================"
echo "  Module : $APP_MODULE"
echo "  Host   : $HOST"
echo "  Port   : $PORT"
echo "============================================"
echo ""

exec uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT"
