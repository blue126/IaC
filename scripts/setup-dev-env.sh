#!/bin/bash
# Build this checkout's host toolchain with uv: Python packages into .venv and
# pinned Ansible collections into ansible/collections. Each worktree gets its own
# copy; uv's shared cache keeps repeated setups fast. Re-run after either
# requirements file changes.

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANSIBLE_ROOT="${REPOSITORY_ROOT}/ansible"
VENV_DIR="${REPOSITORY_ROOT}/.venv"
# Matches the Python version used by repository validation.
PYTHON_VERSION="3.13"

if ! command -v uv >/dev/null 2>&1; then
  echo "Required tool is unavailable: uv" >&2
  exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  uv venv --python "${PYTHON_VERSION}" "${VENV_DIR}"
fi
uv pip install --python "${VENV_DIR}/bin/python" -r "${REPOSITORY_ROOT}/requirements.txt"

"${VENV_DIR}/bin/ansible-galaxy" collection install \
  -r "${ANSIBLE_ROOT}/requirements.yml" -p "${ANSIBLE_ROOT}/collections"

echo "Toolchain ready. Activate with: source ${VENV_DIR}/bin/activate"
