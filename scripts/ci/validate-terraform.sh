#!/bin/bash

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TERRAFORM_BIN="${TERRAFORM_BIN:-terraform}"

if [[ "$#" -eq 0 ]]; then
  echo "terraform_status=not_applicable reason=no_terraform_roots_selected"
  exit 0
fi

if ! command -v "${TERRAFORM_BIN}" >/dev/null 2>&1; then
  echo "Required tool is unavailable: ${TERRAFORM_BIN}" >&2
  exit 1
fi

selected_roots=()
for root in "$@"; do
  case "${root}" in
    terraform/proxmox | terraform/esxi | terraform/oci | terraform/netbox-integration)
      selected_roots+=("${root}")
      ;;
    *)
      echo "Unsupported Terraform root: ${root}" >&2
      exit 2
      ;;
  esac
done

"${TERRAFORM_BIN}" -chdir="${REPOSITORY_ROOT}" fmt -check -recursive terraform

for root in "${selected_roots[@]}"; do
  "${TERRAFORM_BIN}" -chdir="${REPOSITORY_ROOT}/${root}" init -backend=false -input=false
  "${TERRAFORM_BIN}" -chdir="${REPOSITORY_ROOT}/${root}" validate
done

echo "terraform_status=passed roots=$(IFS=,; echo "${selected_roots[*]}")"
