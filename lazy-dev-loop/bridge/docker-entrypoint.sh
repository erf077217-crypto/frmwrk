#!/usr/bin/env bash
set -euo pipefail

APP_MODULE="main:app"
HOST="0.0.0.0"
PORT="${BRIDGE_PORT:-7777}"
APP_USER="app"
APP_UID=1000
APP_GID=1000

echo "============================================"
echo "  Lazy Developer Loop Bridge (Docker)"
echo "============================================"
echo "  Module : $APP_MODULE"
echo "  Host   : $HOST"
echo "  Port   : $PORT"
echo "============================================"
echo ""

# Fix ownership on persisted directories (Docker named volumes
# are created as root on first mount; the app user needs write access).
for dir in \
    /home/app/.local/share/opencode \
    /home/app/.config/opencode \
    /home/app/.cache/opencode \
    /home/app/.local/share/lazy-dev-loop; do
    if [ -d "$dir" ]; then
        chown -R "$APP_USER:$APP_USER" "$dir" 2>/dev/null || true
    fi
done

# Drop privileges to the app user and start the server.
# setpriv does NOT change $HOME — OpenCode (Bun) reads HOME to find its
# data dir, so we must set it explicitly via env.
exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --init-groups \
    env HOME=/home/app \
    uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT"
