#!/bin/bash
# Build mainline llama.cpp (DeepSeek V4 MTP+DSpark support) in an isolated dir.
# Target: llm-server (ubuntu user, passwordless sudo). This does NOT touch the
# current ik_llama.cpp build under /opt/deepseek-v4-ik.
#
# Usage on the guest (detached, resumable-ish):
#   nohup ./deepseek-v4-mainline-build.sh > /tmp/mainline-build.log 2>&1 &
#
# Pinned runtime: ggml-org/llama.cpp @ 10bf611e533d81f739128304991c5e133c6aebd8
# (2026-08-16 master HEAD; >= 596a579 which merged DeepSeek V4 MTP+DSpark #25784).
set -euo pipefail

PIN=10bf611e533d81f739128304991c5e133c6aebd8
ROOT=/opt/deepseek-v4-mainline
SRC="$ROOT/src"
BUILD="$SRC/build"
RUNTIME_IMAGE=approachingai/ktransformers@sha256:5e8f614b5f80ca9d281719a81d65f7dd153d9755696053a7487cd6b90558d1d8
EXPECTED_BINARY_SHA256=2e63f6a8aa2508d129aaef1d59769754e2ae37558b9eec3dbe8d0307ea4d7074

sudo mkdir -p "$ROOT" "$SRC"
sudo chown -R ubuntu:ubuntu "$ROOT"

if [ ! -d "$SRC/.git" ]; then
    echo "[clone] partial clone of ggml-org/llama.cpp"
    git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$SRC"
fi
cd "$SRC"
git fetch --tags origin
git checkout "$PIN" --force
git rev-parse HEAD

echo "[build] building inside pinned runtime image"
docker run --rm --entrypoint /bin/bash \
    -v "$SRC":/src -w /src \
    "$RUNTIME_IMAGE" \
    -lc "cmake -S . -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86 && cmake --build build --target llama-server -j 16"

echo "[build] done: $BUILD/bin/llama-server"
observed_binary_sha256="$(sha256sum "$BUILD/bin/llama-server" | cut -d ' ' -f 1)"
if [[ "$observed_binary_sha256" != "$EXPECTED_BINARY_SHA256" ]]; then
    echo "[build] unexpected binary SHA-256: $observed_binary_sha256" >&2
    exit 1
fi
docker run --rm --gpus all --entrypoint /bin/bash \
    -e LD_LIBRARY_PATH=/build \
    -v "$BUILD/bin":/build:ro \
    "$RUNTIME_IMAGE" \
    -lc 'set -o pipefail; /build/llama-server --version 2>&1 | head -5'
