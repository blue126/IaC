#!/bin/bash

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ANSIBLE_ROOT="${REPOSITORY_ROOT}/ansible"
CI_INVENTORY="${REPOSITORY_ROOT}/tests/ci/fixtures/inventory.yml"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ANSIBLE_GALAXY_BIN="${ANSIBLE_GALAXY_BIN:-ansible-galaxy}"
ANSIBLE_LINT_BIN="${ANSIBLE_LINT_BIN:-ansible-lint}"
ANSIBLE_PLAYBOOK_BIN="${ANSIBLE_PLAYBOOK_BIN:-ansible-playbook}"

required_tools=("${PYTHON_BIN}")
for tool in "${required_tools[@]}"; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required tool is unavailable: ${tool}" >&2
    exit 1
  fi
done

if [[ ! -f "${CI_INVENTORY}" ]]; then
  echo "CI-only inventory is unavailable: ${CI_INVENTORY}" >&2
  exit 1
fi

export ANSIBLE_CONFIG="${ANSIBLE_ROOT}/ansible.cfg"
export ANSIBLE_INVENTORY="${CI_INVENTORY}"
export ANSIBLE_COLLECTIONS_PATH="${ANSIBLE_ROOT}/collections"
export ANSIBLE_VAULT_PASSWORD_FILE="/dev/null"

"${PYTHON_BIN}" -m pip install --disable-pip-version-check -r "${REPOSITORY_ROOT}/requirements.txt"

required_ansible_tools=("${ANSIBLE_GALAXY_BIN}" "${ANSIBLE_LINT_BIN}" "${ANSIBLE_PLAYBOOK_BIN}")
for tool in "${required_ansible_tools[@]}"; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required tool is unavailable: ${tool}" >&2
    exit 1
  fi
done

"${ANSIBLE_GALAXY_BIN}" collection install -r "${ANSIBLE_ROOT}/requirements.yml" -p "${ANSIBLE_ROOT}/collections"
"${PYTHON_BIN}" - "${ANSIBLE_ROOT}" <<'PY'
from pathlib import Path
import os
import sys

import yaml

ansible_root = Path(sys.argv[1])
vault_path = ansible_root / "inventory/group_vars/all/vault.yml"
for directory, subdirs, filenames in os.walk(ansible_root):
    directory = Path(directory)
    if directory == ansible_root:
        # Downloaded collections contain third-party fixtures, including
        # Ansible-specific YAML tags that PyYAML's SafeLoader cannot parse.
        subdirs[:] = [name for name in subdirs if name != "collections"]
    for filename in sorted(filenames):
        path = directory / filename
        if path.suffix not in (".yml", ".yaml") or path == vault_path:
            continue
        with path.open(encoding="utf-8") as stream:
            yaml.safe_load(stream)
PY

(
  cd "${ANSIBLE_ROOT}"
  "${ANSIBLE_LINT_BIN}" -c "${REPOSITORY_ROOT}/.ansible-lint" playbooks roles

  shopt -s nullglob
  playbooks=(playbooks/*.yml playbooks/*.yaml)
  [[ "${#playbooks[@]}" -gt 0 ]]
  for playbook in "${playbooks[@]}"; do
    "${ANSIBLE_PLAYBOOK_BIN}" -i "${CI_INVENTORY}" "${playbook}" --syntax-check
  done
)

echo "ansible_status=passed"
