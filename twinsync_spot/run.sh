#!/usr/bin/with-contenv bashio
# shellcheck shell=bash

# TwinSync Spot Startup Script
# Works with Home Assistant s6-overlay

set -e

# Read config from HA Add-on options
if bashio::config.exists 'gemini_api_key'; then
    export GEMINI_API_KEY=$(bashio::config 'gemini_api_key')
fi

# Get HA supervisor token for API access
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN:-}"
export HA_BASE_URL="http://supervisor/core"

# Ingress path
if bashio::var.has_value "${INGRESS_ENTRY:-}"; then
    export INGRESS_PATH="${INGRESS_ENTRY}"
fi

# Data directory for SQLite
export DATA_DIR="/data"

bashio::log.info "========================================"
bashio::log.info "  TwinSync Spot - Starting..."
bashio::log.info "========================================"
bashio::log.info "  Data dir: ${DATA_DIR}"
bashio::log.info "  Ingress: ${INGRESS_PATH:-'(not set)'}"
bashio::log.info "  Gemini API: $([ -n "${GEMINI_API_KEY:-}" ] && echo 'configured' || echo 'not configured')"
bashio::log.info "========================================"

# Run the FastAPI app
cd /app
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8099 --log-level info
