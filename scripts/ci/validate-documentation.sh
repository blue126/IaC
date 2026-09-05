#!/bin/bash

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
GO_BIN="${GO_BIN:-go}"
HUGO_BIN="${HUGO_BIN:-hugo}"
run_hugo="${1:-false}"

if [[ "${run_hugo}" != true && "${run_hugo}" != false ]]; then
  echo "Usage: $0 [true|false]" >&2
  exit 2
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Required tool is unavailable: ${PYTHON_BIN}" >&2
  exit 1
fi

cd "${REPOSITORY_ROOT}"
# Deterministic regression for the six explicitly registered claim pairs.
"${PYTHON_BIN}" tests/doc-claims/doc-claims-test.py
# Offline controller/contract tests; this never invokes the live AI path.
"${PYTHON_BIN}" tests/doc-gardening/doc-gardening-test.py
# Recorded accept/reject fixtures, not a live model quality evaluation.
"${PYTHON_BIN}" tools/doc-gardening/evaluate.py --fixtures tests/doc-gardening/fixtures
# Current repository consistency report for the known claim pairs.
"${PYTHON_BIN}" tools/check-doc-claims.py --root . --output tmp/doc-accuracy/report.json

if [[ "${run_hugo}" == false ]]; then
  echo "documentation_status=passed hugo_status=not_applicable reason=no_site_inputs_changed"
  exit 0
fi

for tool in "${GO_BIN}" "${HUGO_BIN}"; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required tool is unavailable: ${tool}" >&2
    exit 1
  fi
done

hugo_version="$("${HUGO_BIN}" version)"
go_version="$("${GO_BIN}" version)"
module_graph="$("${HUGO_BIN}" mod graph)"
[[ "${hugo_version}" == *"v0.165.0"* && "${hugo_version}" == *"+extended"* ]]
[[ "${go_version}" == *"go1.25.0"* ]]
[[ "${module_graph}" == *"github.com/pgsty/oink@v0.7.0"* ]]

"${PYTHON_BIN}" docs-site/scripts/prepare-content.py

base_url="${BASE_URL:-https://blue126.github.io/IaC/}"
"${HUGO_BIN}" --cleanDestinationDir --gc --minify --environment production \
  --printPathWarnings --panicOnWarning --baseURL "${base_url}"

test -s public/index.html
test -s public/index.md
test -s public/llms.txt
test -s public/docs/designs/homelab-iac-architecture/index.html
test -s public/docs/designs/homelab-iac-architecture/index.md
grep -Fq "rel=canonical href=${base_url}docs/designs/homelab-iac-architecture/" \
  public/docs/designs/homelab-iac-architecture/index.html
grep -Fq "rel=alternate type=text/markdown href=${base_url}docs/designs/homelab-iac-architecture/index.md" \
  public/docs/designs/homelab-iac-architecture/index.html
grep -Fxq '# Homelab IaC 系统架构文档' \
  public/docs/designs/homelab-iac-architecture/index.md
grep -Fq '本文档描述 Homelab Infrastructure as Code 项目的完整系统架构' \
  public/docs/designs/homelab-iac-architecture/index.md
grep -Fq "${base_url}docs/designs/homelab-iac-architecture/index.md" public/llms.txt
grep -Fq '<title>Homelab IaC 系统架构文档 | Homelab IaC Documentation</title>' \
  public/docs/designs/homelab-iac-architecture/index.html
grep -Fq '<span>Homelab IaC 系统架构文档</span></a>' \
  public/docs/designs/homelab-iac-architecture/index.html
grep -Fq 'github.com/blue126/IaC/edit/main/docs/designs/homelab-iac-architecture.md' \
  public/docs/designs/homelab-iac-architecture/index.html
grep -Fq 'Homelab IaC Documentation' public/index.html
grep -Fq 'Browse documentation' public/index.html
grep -Fq 'td-diagram--mermaid' public/docs/designs/cicd-architecture/index.html
grep -Fq 'mermaid-' public/docs/designs/cicd-architecture/index.html

shopt -s nullglob
search_indexes=(public/offline-search-index.*.json)
[[ "${#search_indexes[@]}" -eq 1 ]]
test -s "${search_indexes[0]}"
grep -Fq '"title":"Documentation / 文档"' "${search_indexes[0]}"
grep -Fq '"ref":"/IaC/docs/"' "${search_indexes[0]}"

echo "documentation_status=passed hugo_status=passed"
