#!/bin/bash
# Build the MoE expert cache fork of llama.cpp into an isolated directory.
# Target: llm-server (ubuntu user, passwordless sudo). This does NOT touch the
# pinned mainline build under /opt/deepseek-v4-mainline, so the current runtime
# stays available as a rollback.
#
# Usage on the guest (detached):
#   nohup ./deepseek-v4-moe-cache-build.sh > /tmp/moe-cache-build.log 2>&1 &
#
# Why a separate build rather than a pin bump: the fork branches from upstream
# 15586e2d, an ancestor of our pin 10bf611e, with 153 upstream commits in
# between including six speculative-decoding fixes. The two binaries have to be
# A/B compared before anything is promoted. See the handoff document, section
# 3.14.
#
# Source: leloch/llama.cpp @ moe-cache-v2-pr
# Discussion: https://github.com/ggml-org/llama.cpp/discussions/24528
set -euo pipefail

PIN=e3096b046bb809f7f80bc47801f6579aed1cbc60
FORK=https://github.com/leloch/llama.cpp.git
BRANCH=moe-cache-v2-pr
ROOT=/opt/deepseek-v4-moe-cache
SRC="$ROOT/src"
BUILD="$SRC/build"
# Same image as the mainline build so the binary's rpath and library
# dependencies match what the Compose service already provides.
RUNTIME_IMAGE=approachingai/ktransformers@sha256:5e8f614b5f80ca9d281719a81d65f7dd153d9755696053a7487cd6b90558d1d8

sudo mkdir -p "$ROOT" "$SRC"
sudo chown -R ubuntu:ubuntu "$ROOT"

if [ ! -d "$SRC/.git" ]; then
    echo "[clone] partial clone of $FORK ($BRANCH)"
    git clone --filter=blob:none --branch "$BRANCH" --single-branch "$FORK" "$SRC"
fi
cd "$SRC"
git fetch origin "$BRANCH"
git checkout "$PIN" --force
observed_commit="$(git rev-parse HEAD)"
if [[ "$observed_commit" != "$PIN" ]]; then
    echo "[clone] unexpected HEAD: $observed_commit" >&2
    exit 1
fi
echo "[clone] HEAD=$observed_commit"

echo "[build] building inside pinned runtime image"
docker run --rm --entrypoint /bin/bash \
    -v "$SRC":/src -w /src \
    "$RUNTIME_IMAGE" \
    -lc "cmake -S . -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86 && cmake --build build --target llama-server -j 16"

echo "[build] done: $BUILD/bin/llama-server"
echo "[build] binary SHA-256: $(sha256sum "$BUILD/bin/llama-server" | cut -d ' ' -f 1)"

# The whole point of this build: confirm the cache option is actually present.
docker run --rm --gpus all --entrypoint /bin/bash \
    -e LD_LIBRARY_PATH=/build \
    -v "$BUILD/bin":/build:ro \
    "$RUNTIME_IMAGE" \
    -lc 'set -o pipefail; /build/llama-server --version 2>&1 | head -3; echo "--- moe-cache option ---"; /build/llama-server --help 2>&1 | grep -A 3 -i "moe-cache" || echo "MISSING: --moe-cache not found in help"'
