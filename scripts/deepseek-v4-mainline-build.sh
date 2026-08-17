#!/bin/bash
# Build mainline llama.cpp (DeepSeek V4 MTP+DSpark support) in an isolated dir.
# Target: llm-server (ubuntu user, passwordless sudo). This does NOT touch the
# production ik_llama.cpp build under /opt/deepseek-v4-ik.
#
# Usage on the guest (detached, resumable-ish):
#   nohup ./deepseek-v4-mainline-build.sh > /tmp/mainline-build.log 2>&1 &
#
# Pinned runtime: ggml-org/llama.cpp @ 10bf611e533d81f739128304991c5e133c6aebd8
# (2026-08-16 master HEAD; >= 596a579 which merged DeepSeek V4 MTP+DSpark #25784).
set -e

PIN=10bf611e533d81f739128304991c5e133c6aebd8
ROOT=/opt/deepseek-v4-mainline
SRC="$ROOT/src"
BUILD="$ROOT/build"
RUNTIME_IMAGE=approachingai/ktransformers@sha256:5e8f614b5f80ca9d281719a81d65f7dd153d9755696053a7487cd6b90558d1d8

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

if command -v nvcc >/dev/null 2>&1 && command -v cmake >/dev/null 2>&1; then
    echo "[build] host toolchain found; building natively"
    cmake -S . -B "$BUILD" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86
    cmake --build "$BUILD" --target llama-server -j "$(nproc)"
else
    echo "[build] no host nvcc; building inside pinned runtime image"
    docker run --rm --entrypoint /bin/bash \
        -v "$SRC":/src -w /src \
        "$RUNTIME_IMAGE" \
        -lc "cmake -S . -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86 && cmake --build build --target llama-server -j 16"
fi

echo "[build] done: $BUILD/bin/llama-server"
"$BUILD/bin/llama-server" --version 2>&1 | head -5
