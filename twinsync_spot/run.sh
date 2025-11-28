#!/bin/bash
set -e

# Read config from /data/options.json (HA add-on config)
if [ -f /data/options.json ]; then
    GEMINI_API_KEY=$(jq -r '.gemini_api_key // empty' /data/options.json)
    if [ -n "$GEMINI_API_KEY" ]; then
        export GEMINI_API_KEY
    fi
fi

# Get HA supervisor token for API access  
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN:-}"
export HA_BASE_URL="http://supervisor/core"

# Set ingress path if running as add-on
export INGRESS_PATH="${INGRESS_PATH:-}"

# Data directory for SQLite
export DATA_DIR="/data"

echo "========================================"
echo "  TwinSync Spot - Starting..."
echo "========================================"
echo "  Data dir: ${DATA_DIR}"
echo "  Ingress path: ${INGRESS_PATH:-'(none)'}"
echo "  Gemini API: $([ -n "${GEMINI_API_KEY:-}" ] && echo 'configured' || echo 'not configured')"
echo "========================================"

# Run the FastAPI app
cd /app
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8099 --log-level info
