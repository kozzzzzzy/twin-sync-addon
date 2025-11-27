#!/usr/bin/with-contenv bashio
# shellcheck shell=bash

# Get config from HA Add-on options
export GEMINI_API_KEY=$(bashio::config 'gemini_api_key')

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
echo "========================================"

# Run the FastAPI app
cd /app
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8099 --log-level info
