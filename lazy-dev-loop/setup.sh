#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

echo ""
echo "============================================"
echo "  Lazy Dev Loop — Docker Setup"
echo "============================================"
echo ""

# ── Step 1: Docker access ───────────────────────────────────────────────
info "Checking Docker access..."

if docker info &>/dev/null; then
    info "Docker is accessible."
else
    warn "Docker socket not accessible. Attempting to fix..."
    if groups "$USER" | grep -q docker; then
        error "You are in the docker group but need to log out and back in."
        error "Run: newgrp docker"
        error "Then re-run this script."
        exit 1
    fi
    if command -v sudo &>/dev/null; then
        sudo usermod -aG docker "$USER"
        info "Added $USER to the docker group."
        error "You must log out and back in, then re-run this script."
        error "Or run: newgrp docker && bash setup.sh"
        exit 1
    else
        error "sudo not available. Add yourself to the docker group manually:"
        error "  sudo usermod -aG docker \$USER"
        error "Then log out and back in."
        exit 1
    fi
fi

# ── Step 2: .env file ───────────────────────────────────────────────────
info "Checking .env file..."

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        info "Created .env from .env.example"
        warn "  >> Edit .env and set OPENAI_API_KEY=sk-... before using OpenCode"
    else
        info "Creating minimal .env..."
        cat > .env << EOF
OPENAI_API_KEY=
BRIDGE_PORT=7777
RUN_TIMEOUT=120
DEBUG_OUTPUT=true
TMUX_SESSION_NAME=lazy-dev-loop
EOF
        warn "  >> Edit .env and set OPENAI_API_KEY=sk-..."
    fi
else
    info ".env already exists."
fi

# Export vars from .env for docker compose
set -a; source .env; set +a

# ── Step 3: Build ───────────────────────────────────────────────────────
info "Building Docker image..."
docker compose build --pull

# ── Step 4: Start ───────────────────────────────────────────────────────
info "Starting container..."
docker compose up -d

# ── Step 5: Verify ─────────────────────────────────────────────────────
echo ""
info "Waiting for bridge to be ready..."
for i in $(seq 1 15); do
    if curl -sf http://localhost:${BRIDGE_PORT:-7777}/health >/dev/null 2>&1; then
        echo ""
        info "Bridge is ONLINE at http://localhost:${BRIDGE_PORT:-7777}"
        break
    fi
    sleep 1
done

if ! curl -sf http://localhost:${BRIDGE_PORT:-7777}/health >/dev/null 2>&1; then
    warn "Bridge did not respond within 15s. Check logs:"
    warn "  docker compose logs -f"
fi

echo ""
echo "============================================"
info "Container status:"
docker compose ps
echo ""
echo "  Container name: lazy-dev-loop-bridge-1"
echo "  Bridge URL:     http://localhost:${BRIDGE_PORT:-7777}"
echo "  Health check:   curl http://localhost:${BRIDGE_PORT:-7777}/health"
echo ""
echo "  Useful commands:"
echo "    View logs:    docker compose logs -f"
echo "    Stop all:     docker compose down"
echo "    Rebuild:      docker compose build && docker compose up -d"
echo "    Attach tmux:  docker exec -it lazy-dev-loop-bridge-1 tmux attach"
echo "============================================"
