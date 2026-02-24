#!/bin/bash
# Wrapper script for llama-server — reads per-model .env/.ot config and builds command line.
# Called by systemd template unit: llama-server@.service → ExecStart=launch-llama.sh %i
set -euo pipefail

MODEL_NAME="$1"
CONFIG_DIR="/opt/llm-server/models"
ENV_FILE="${CONFIG_DIR}/${MODEL_NAME}.env"
OT_FILE="${CONFIG_DIR}/${MODEL_NAME}.ot"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Model config not found: $ENV_FILE" >&2
    exit 1
fi

source "$ENV_FILE"

# Build -ot arguments (only when .ot file exists)
OT_ARGS=()
if [[ -f "$OT_FILE" ]]; then
    while IFS= read -r line; do
        line=$(sed 's/^[[:space:]]*//' <<< "$line")
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        OT_ARGS+=(-ot "$line")
    done < "$OT_FILE"
fi

# Optional sampling parameters (only passed when set in .env)
EXTRA_ARGS=()
[[ -n "${LLAMA_MMPROJ:-}" ]] && EXTRA_ARGS+=(--mmproj "$LLAMA_MMPROJ")
[[ -n "${LLAMA_REASONING_FORMAT:-}" ]] && EXTRA_ARGS+=(--reasoning-format "$LLAMA_REASONING_FORMAT")
[[ -n "${LLAMA_TEMP:-}" ]] && EXTRA_ARGS+=(--temp "$LLAMA_TEMP")
[[ -n "${LLAMA_TOP_P:-}" ]] && EXTRA_ARGS+=(--top-p "$LLAMA_TOP_P")
[[ -n "${LLAMA_TOP_K:-}" ]] && EXTRA_ARGS+=(--top-k "$LLAMA_TOP_K")
[[ -n "${LLAMA_FLASH_ATTN:-}" ]] && EXTRA_ARGS+=(--flash-attn "$LLAMA_FLASH_ATTN")

exec /usr/bin/numactl --interleave=all \
    /opt/llm-server/ik_llama.cpp/build/bin/llama-server \
    --model "$LLAMA_MODEL" \
    --alias "$LLAMA_ALIAS" \
    -ngl "$LLAMA_GPU_LAYERS" \
    "${OT_ARGS[@]}" \
    --split-mode "$LLAMA_SPLIT_MODE" \
    --tensor-split "$LLAMA_TENSOR_SPLIT" \
    --jinja \
    --ctx-size "$LLAMA_CTX_SIZE" \
    --cache-type-k "$LLAMA_CACHE_TYPE_K" \
    --cache-type-v "$LLAMA_CACHE_TYPE_V" \
    --threads "$LLAMA_THREADS" \
    --threads-batch "$LLAMA_THREADS_BATCH" \
    "${EXTRA_ARGS[@]}" \
    --host "$LLAMA_HOST" \
    --port "$LLAMA_PORT" \
    --parallel "$LLAMA_PARALLEL"
