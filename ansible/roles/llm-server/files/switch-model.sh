#!/bin/bash
# Switch between llama-server model instances.
# Usage: switch-model.sh <m25|qwen3-32b|glm-4.7>
set -euo pipefail

MODEL="${1:-}"
CONFIG_DIR="/opt/llm-server/models"

# Validate: model name must have a corresponding .env file
if [[ -z "$MODEL" || ! -f "${CONFIG_DIR}/${MODEL}.env" ]]; then
    echo "Usage: switch-model.sh <model-name>"
    echo ""
    echo "Available models:"
    for f in "${CONFIG_DIR}"/*.env; do
        [[ -f "$f" ]] && echo "  $(basename "$f" .env)"
    done
    # Show current status
    CURRENT=$(systemctl list-units 'llama-server@*' --state=active --no-legend --plain | awk '{print $1}')
    if [[ -n "$CURRENT" ]]; then
        echo ""
        echo "Current: $CURRENT"
    fi
    exit 1
fi

echo "→ Stopping current instances..."
sudo systemctl stop 'llama-server@*' 2>/dev/null || true

echo "→ Starting llama-server@${MODEL}..."
sudo systemctl start "llama-server@${MODEL}"

# Source config to get port
source "${CONFIG_DIR}/${MODEL}.env"
PORT="${LLAMA_PORT:-8080}"

echo "  Waiting for health check (port ${PORT})..."
timeout 120 bash -c "until curl -sf http://localhost:${PORT}/health >/dev/null 2>&1; do sleep 2; done" \
    || { echo "✗ Health check timeout"; exit 1; }
echo "✓ ${MODEL} ready"
