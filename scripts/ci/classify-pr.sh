#!/bin/bash

set -euo pipefail

usage() {
  echo "Usage: $0 <base-sha> <head-sha>" >&2
}

if [[ "$#" -ne 2 ]]; then
  usage
  exit 2
fi

base_sha="$1"
head_sha="$2"

if ! git cat-file -e "${base_sha}^{commit}" 2>/dev/null; then
  echo "Base SHA is not an available commit: ${base_sha}" >&2
  exit 2
fi

if ! git cat-file -e "${head_sha}^{commit}" 2>/dev/null; then
  echo "Head SHA is not an available commit: ${head_sha}" >&2
  exit 2
fi

terraform_proxmox=false
terraform_esxi=false
terraform_oci=false
terraform_netbox=false
ansible_applicable=false
docs_applicable=false
hugo_applicable=false
shell_applicable=false
python_applicable=false
governance_sensitive=false
changed_files_count=0
changed_files_path="$(mktemp)"
trap 'rm -f "${changed_files_path}"' EXIT

if ! git diff --no-renames --name-only --diff-filter=ACMRTD -z \
  "${base_sha}...${head_sha}" -- >"${changed_files_path}"; then
  echo "Unable to calculate changed files for ${base_sha}...${head_sha}" >&2
  exit 1
fi

while IFS= read -r -d '' changed_file; do
  changed_files_count=$((changed_files_count + 1))

  case "${changed_file}" in
    terraform/modules/*)
      terraform_proxmox=true
      terraform_esxi=true
      terraform_oci=true
      terraform_netbox=true
      ;;
    terraform/proxmox/*)
      terraform_proxmox=true
      ;;
    terraform/esxi/*)
      terraform_esxi=true
      ;;
    terraform/oci/*)
      terraform_oci=true
      ;;
    terraform/netbox-integration/*)
      terraform_netbox=true
      ;;
  esac

  case "${changed_file}" in
    ansible/* | requirements.txt | .ansible-lint)
      ansible_applicable=true
      ;;
  esac

  case "${changed_file}" in
    docs/* | docs-site/* | hugo.yaml | go.mod | go.sum | .github/workflows/docs-pages.yml)
      hugo_applicable=true
      ;;
  esac

  case "${changed_file}" in
    docs/* | docs-site/* | hugo.yaml | go.mod | go.sum | \
      README.md | */README.md | CLAUDE.md | \
      tools/check-doc-claims.py | tools/doc-gardening/* | \
      tests/doc-claims/* | tests/doc-gardening/* | \
      .github/workflows/doc-accuracy.yml | .github/workflows/docs-pages.yml)
      docs_applicable=true
      ;;
  esac

  case "${changed_file}" in
    scripts/ci/validate-documentation.sh)
      docs_applicable=true
      hugo_applicable=true
      ;;
  esac

  case "${changed_file}" in
    *.sh)
      shell_applicable=true
      ;;
  esac

  case "${changed_file}" in
    *.py)
      python_applicable=true
      ;;
  esac

  case "${changed_file}" in
    .github/workflows/* | .github/actions/repo-validation/* | AGENTS.md | Jenkinsfile* | \
      scripts/ci/* | tests/ci/* | scripts/get-secrets.sh | scripts/refresh-terraform-state.sh | \
      ansible/inventory/group_vars/all/vault.yml)
      governance_sensitive=true
      ;;
  esac
done <"${changed_files_path}"

terraform_roots=()
[[ "${terraform_proxmox}" == true ]] && terraform_roots+=("terraform/proxmox")
[[ "${terraform_esxi}" == true ]] && terraform_roots+=("terraform/esxi")
[[ "${terraform_oci}" == true ]] && terraform_roots+=("terraform/oci")
[[ "${terraform_netbox}" == true ]] && terraform_roots+=("terraform/netbox-integration")

terraform_roots_csv=""
if [[ "${#terraform_roots[@]}" -gt 0 ]]; then
  terraform_roots_csv="$(IFS=,; echo "${terraform_roots[*]}")"
fi

printf 'changed_files_count=%s\n' "${changed_files_count}"
printf 'terraform_applicable=%s\n' "$([[ "${#terraform_roots[@]}" -gt 0 ]] && echo true || echo false)"
printf 'terraform_roots=%s\n' "${terraform_roots_csv}"
printf 'ansible_applicable=%s\n' "${ansible_applicable}"
printf 'docs_applicable=%s\n' "${docs_applicable}"
printf 'hugo_applicable=%s\n' "${hugo_applicable}"
printf 'shell_applicable=%s\n' "${shell_applicable}"
printf 'python_applicable=%s\n' "${python_applicable}"
printf 'governance_sensitive=%s\n' "${governance_sensitive}"
