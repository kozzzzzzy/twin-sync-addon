#!/usr/bin/with-contenv bashio
set -e

echo "=========================================="
echo "TwinSync Spot - Starting..."
echo "=========================================="

# Read Gemini API key from addon options
if bashio::config.exists 'gemini_api_key'; then
    GEMINI_API_KEY=$(bashio::config 'gemini_api_key')
    export GEMINI_API_KEY
    echo "Gemini API key: configured"
elif [ -f /data/options.json ]; then
    GEMINI_API_KEY=$(python3 -c "import json; print(json.load(open('/data/options.json')).get('gemini_api_key', ''))")
    export GEMINI_API_KEY
    echo "Gemini API key: configured (fallback)"
else
    echo "Warning: Gemini API key not found"
fi

# Get supervisor token - with-contenv should have it, but let's be thorough
SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN:-${HASSIO_TOKEN:-}}"

if [ -n "$SUPERVISOR_TOKEN" ]; then
    export SUPERVISOR_TOKEN
    export HASSIO_TOKEN="$SUPERVISOR_TOKEN"
    # Write to file as backup for Python process
    echo "$SUPERVISOR_TOKEN" > /data/.supervisor_token
    chmod 600 /data/.supervisor_token
    echo "Supervisor token: available (length: ${#SUPERVISOR_TOKEN})"
else
    echo "WARNING: Supervisor token not available at startup"
    # Try to get it from supervisor API (belt and suspenders)
    if command -v bashio &> /dev/null; then
        SUPERVISOR_TOKEN=$(bashio::supervisor.token 2>/dev/null || echo "")
        if [ -n "$SUPERVISOR_TOKEN" ]; then
            export SUPERVISOR_TOKEN
            export HASSIO_TOKEN="$SUPERVISOR_TOKEN"
            echo "$SUPERVISOR_TOKEN" > /data/.supervisor_token
            chmod 600 /data/.supervisor_token
            echo "Supervisor token: retrieved via bashio"
        fi
    fi
fi

# Set data directory
export DATA_DIR="/data"

# Get ingress path from supervisor if available
if [ -n "$SUPERVISOR_TOKEN" ]; then
    INGRESS_INFO=$(curl -s -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" http://supervisor/addons/self/info 2>/dev/null || echo "{}")
    INGRESS_ENTRY=$(echo "$INGRESS_INFO" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('data', {}).get('ingress_entry', d.get('ingress_entry', '')))" 2>/dev/null || echo "")
    if [ -n "$INGRESS_ENTRY" ]; then
        export INGRESS_PATH="$INGRESS_ENTRY"
        echo "Ingress path: $INGRESS_PATH"
    fi
fi

echo "Starting FastAPI server on port 8099..."
echo "=========================================="

# Run the FastAPI app
cd /app
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8099
