#!/bin/bash

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLASSIFIER_BIN="${CLASSIFIER_BIN:-${REPOSITORY_ROOT}/scripts/ci/classify-pr.sh}"
TERRAFORM_VALIDATOR_BIN="${TERRAFORM_VALIDATOR_BIN:-${REPOSITORY_ROOT}/scripts/ci/validate-terraform.sh}"
ANSIBLE_VALIDATOR_BIN="${ANSIBLE_VALIDATOR_BIN:-${REPOSITORY_ROOT}/scripts/ci/validate-ansible.sh}"
DOCUMENTATION_VALIDATOR_BIN="${DOCUMENTATION_VALIDATOR_BIN:-${REPOSITORY_ROOT}/scripts/ci/validate-documentation.sh}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "$#" -ne 2 ]]; then
  echo "Usage: $0 <base-sha> <head-sha>" >&2
  exit 2
fi

base_sha="$1"
head_sha="$2"
classification="$(cd "${REPOSITORY_ROOT}" && "${CLASSIFIER_BIN}" "${base_sha}" "${head_sha}")"

changed_files_count=""
terraform_applicable=""
terraform_roots=""
ansible_applicable=""
docs_applicable=""
hugo_applicable=""
shell_applicable=""
python_applicable=""
governance_sensitive=""

while IFS='=' read -r key value; do
  case "${key}" in
    changed_files_count) changed_files_count="${value}" ;;
    terraform_applicable) terraform_applicable="${value}" ;;
    terraform_roots) terraform_roots="${value}" ;;
    ansible_applicable) ansible_applicable="${value}" ;;
    docs_applicable) docs_applicable="${value}" ;;
    hugo_applicable) hugo_applicable="${value}" ;;
    shell_applicable) shell_applicable="${value}" ;;
    python_applicable) python_applicable="${value}" ;;
    governance_sensitive) governance_sensitive="${value}" ;;
  esac
done <<<"${classification}"

required_values=(
  "${changed_files_count}"
  "${terraform_applicable}"
  "${ansible_applicable}"
  "${docs_applicable}"
  "${hugo_applicable}"
  "${shell_applicable}"
  "${python_applicable}"
  "${governance_sensitive}"
)
for value in "${required_values[@]}"; do
  if [[ -z "${value}" ]]; then
    echo "Classifier output is incomplete" >&2
    exit 1
  fi
done

for boolean_value in \
  "${terraform_applicable}" "${ansible_applicable}" "${docs_applicable}" \
  "${hugo_applicable}" "${shell_applicable}" "${python_applicable}" \
  "${governance_sensitive}"; do
  if [[ "${boolean_value}" != true && "${boolean_value}" != false ]]; then
    echo "Classifier emitted an invalid boolean: ${boolean_value}" >&2
    exit 1
  fi
done

if [[ "${terraform_applicable}" == true && -z "${terraform_roots}" ]]; then
  echo "Classifier selected Terraform validation without any roots" >&2
  exit 1
fi

printf '%s\n' "${classification}"

if [[ "${terraform_applicable}" == true ]]; then
  IFS=',' read -r -a roots <<<"${terraform_roots}"
  "${TERRAFORM_VALIDATOR_BIN}" "${roots[@]}"
else
  echo "terraform_status=not_applicable reason=no_terraform_changes"
fi

if [[ "${ansible_applicable}" == true ]]; then
  "${ANSIBLE_VALIDATOR_BIN}"
else
  echo "ansible_status=not_applicable reason=no_ansible_changes"
fi

if [[ "${docs_applicable}" == true ]]; then
  "${DOCUMENTATION_VALIDATOR_BIN}" "${hugo_applicable}"
else
  echo "documentation_status=not_applicable reason=no_documentation_changes"
  echo "hugo_status=not_applicable reason=no_site_inputs_changed"
fi

if [[ "${shell_applicable}" == true ]]; then
  checked_shell_files=0
  shell_files_path="$(mktemp)"
  trap 'rm -f "${shell_files_path}"' EXIT
  if ! (cd "${REPOSITORY_ROOT}" && git diff --no-renames --name-only \
    --diff-filter=ACMRTD -z "${base_sha}...${head_sha}" --) >"${shell_files_path}"; then
    echo "Unable to enumerate changed shell files" >&2
    exit 1
  fi
  while IFS= read -r -d '' changed_file; do
    if [[ "${changed_file}" == *.sh && -f "${REPOSITORY_ROOT}/${changed_file}" ]]; then
      bash -n "${REPOSITORY_ROOT}/${changed_file}"
      checked_shell_files=$((checked_shell_files + 1))
    fi
  done <"${shell_files_path}"

  if [[ "${checked_shell_files}" -eq 0 ]]; then
    echo "shell_status=not_applicable reason=only_deleted_shell_files_changed"
  else
    echo "shell_status=passed files=${checked_shell_files}"
  fi
else
  echo "shell_status=not_applicable reason=no_shell_changes"
fi

if [[ "${python_applicable}" == true ]]; then
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Required tool is unavailable: ${PYTHON_BIN}" >&2
    exit 1
  fi
  python_cache_path="$(mktemp -d)"
  python_files_path="$(mktemp)"
  trap 'rm -f "${shell_files_path:-}" "${python_files_path}"; rm -rf "${python_cache_path}"' EXIT
  if ! (cd "${REPOSITORY_ROOT}" && git diff --no-renames --name-only \
    --diff-filter=ACMRTD -z "${base_sha}...${head_sha}" --) >"${python_files_path}"; then
    echo "Unable to enumerate changed Python files" >&2
    exit 1
  fi
  checked_python_files=0
  while IFS= read -r -d '' changed_file; do
    if [[ "${changed_file}" == *.py && -f "${REPOSITORY_ROOT}/${changed_file}" ]]; then
      PYTHONPYCACHEPREFIX="${python_cache_path}" "${PYTHON_BIN}" -m py_compile \
        "${REPOSITORY_ROOT}/${changed_file}"
      checked_python_files=$((checked_python_files + 1))
    fi
  done <"${python_files_path}"
  if [[ "${checked_python_files}" -eq 0 ]]; then
    echo "python_status=not_applicable reason=only_deleted_python_files_changed"
  else
    echo "python_status=passed files=${checked_python_files}"
  fi
else
  echo "python_status=not_applicable reason=no_python_changes"
fi

if [[ "${governance_sensitive}" == true ]]; then
  echo "governance_status=human_required enforcement=shadow"
  echo "::warning title=Human review required::This PR changes governance-sensitive files; Phase 1 remains shadow-only."
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    echo '### ⚠️ Governance-sensitive change: human review required' >>"${GITHUB_STEP_SUMMARY}"
  fi
else
  echo "governance_status=not_applicable reason=no_governance_sensitive_changes"
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "changed_files_count=${changed_files_count}"
    echo "governance_sensitive=${governance_sensitive}"
  } >>"${GITHUB_OUTPUT}"
fi

echo "repo_validation_status=passed"
