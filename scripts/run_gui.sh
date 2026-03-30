#!/usr/bin/env bash
# ===========================================================================
# Run both FastAPI backend and PyQt GUI
# ===========================================================================
# Usage:
#   chmod +x scripts/run_gui.sh
#   ./scripts/run_gui.sh
#
# This script starts the backend server in the background,
# waits for it to become healthy, then launches the GUI.
# When the GUI is closed, the backend is stopped automatically.
# ===========================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

HOST="${WORKER_HOST:-0.0.0.0}"
PORT="${WORKER_PORT:-8000}"
API_URL="http://localhost:${PORT}/api/v1"
BACKEND_PID=""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null
        wait "$BACKEND_PID" 2>/dev/null || true
        echo -e "${GREEN}Backend stopped.${NC}"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 1. Start backend
# ---------------------------------------------------------------------------
echo -e "${GREEN}Starting FastAPI backend on ${HOST}:${PORT}...${NC}"
python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level info &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# ---------------------------------------------------------------------------
# 2. Wait for backend to be ready
# ---------------------------------------------------------------------------
MAX_WAIT=30
echo -n "Waiting for backend..."
for i in $(seq 1 $MAX_WAIT); do
    if curl -s "http://localhost:${PORT}/api/v1/system/health" > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}Backend is ready!${NC}"
        break
    fi
    echo -n "."
    sleep 1
    if [ "$i" -eq "$MAX_WAIT" ]; then
        echo ""
        echo -e "${YELLOW}Warning: Backend may not be fully ready yet, starting GUI anyway...${NC}"
    fi
done

# ---------------------------------------------------------------------------
# 3. Launch GUI
# ---------------------------------------------------------------------------
echo -e "${GREEN}Launching GUI...${NC}"
export WORKER_GUI_API_URL="$API_URL"
python3 -m gui

echo -e "${GREEN}GUI closed.${NC}"
