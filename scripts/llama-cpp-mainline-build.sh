#!/bin/bash
# Build mainline llama.cpp in an isolated dir. Shared by every runtime that
# serves through this binary: DeepSeek V4 (MTP+DSpark) on llm-server, Qwen3.8
# on llm-workstation. Does NOT touch the ik_llama.cpp build under
# /opt/deepseek-v4-ik.
#
# Runs unprivileged after the initial chown, on whichever host invokes it --
# llm-server's login user is ubuntu, llm-workstation's is will.
#
# Usage on the guest (detached, resumable-ish):
#   nohup ./llama-cpp-mainline-build.sh > /tmp/mainline-build.log 2>&1 &
#
# Takes an optional absolute install root. Defaults to the path llm-server has
# always used, so existing callers are unaffected; llm-workstation passes
# /opt/llama-cpp-mainline because it never ran DeepSeek. The source is always
# mounted at /src inside the build container, so the host path never reaches
# the compiler and EXPECTED_BINARY_SHA256 holds for either root.
#   nohup ./llama-cpp-mainline-build.sh /opt/llama-cpp-mainline > /tmp/mainline-build.log 2>&1 &
#
# Pinned runtime: ggml-org/llama.cpp @ 10bf611e533d81f739128304991c5e133c6aebd8
# (2026-08-16 master HEAD; >= 596a579 which merged DeepSeek V4 MTP+DSpark #25784).
set -euo pipefail

PIN=10bf611e533d81f739128304991c5e133c6aebd8
ROOT="${1:-/opt/deepseek-v4-mainline}"
if [[ "$ROOT" != /* ]]; then
    echo "install root must be an absolute path, got: $ROOT" >&2
    exit 1
fi
SRC="$ROOT/src"
BUILD="$SRC/build"
RUNTIME_IMAGE=approachingai/ktransformers@sha256:5e8f614b5f80ca9d281719a81d65f7dd153d9755696053a7487cd6b90558d1d8
EXPECTED_BINARY_SHA256=2e63f6a8aa2508d129aaef1d59769754e2ae37558b9eec3dbe8d0307ea4d7074

sudo mkdir -p "$ROOT" "$SRC"
# Not hardcoded to ubuntu: llm-server's login user is ubuntu, llm-workstation's
# is will, and the build runs unprivileged after this point either way.
sudo chown -R "$(id -un):$(id -gn)" "$ROOT"

if [ ! -d "$SRC/.git" ]; then
    echo "[clone] partial clone of ggml-org/llama.cpp"
    git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$SRC"
fi
cd "$SRC"
# Only reach the network when the pin is not already present locally, so a
# rebuild works offline once the objects have been fetched.
if ! git cat-file -e "${PIN}^{commit}" 2>/dev/null; then
    git fetch --tags origin
fi
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
# Addressed as a CDI device, not --gpus all. On llm-workstation the bare
# --gpus all form makes Docker probe every CDI vendor, and the Ryzen iGPU
# makes it look for an AMD spec that does not exist -- it fails with "AMD CDI
# spec not found" before the container starts. Same reason the Compose files
# for this binary use `devices: [nvidia.com/gpu=N]`. Requires the CDI spec the
# nvidia-driver role generates.
docker run --rm --device nvidia.com/gpu=0 --entrypoint /bin/bash \
    -e LD_LIBRARY_PATH=/build \
    -v "$BUILD/bin":/build:ro \
    "$RUNTIME_IMAGE" \
    -lc 'set -o pipefail; /build/llama-server --version 2>&1 | head -5'
