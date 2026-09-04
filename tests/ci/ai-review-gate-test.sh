#!/bin/bash

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="${1:-}"
EVALUATOR="${RUNTIME_DIR}/scripts/evaluate-ai-review-gate.sh"
WORKFLOW="${REPOSITORY_ROOT}/.github/workflows/ai-review-gate.yml"
FIXTURE_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${FIXTURE_DIR}"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_file_contains() {
  local path="$1"
  local expected="$2"

  grep -Fq -- "${expected}" "${path}" || fail "${path} must contain: ${expected}"
}

write_verdict() {
  local path="$1"
  local status="$2"
  local reviewed_sha="$3"
  local findings="$4"

  jq -n \
    --arg repository "blue126/IaC" \
    --argjson pull_request 27 \
    --arg reviewed_sha "${reviewed_sha}" \
    --arg status "${status}" \
    --argjson findings "${findings}" \
    '{repository:$repository,pull_request:$pull_request,reviewed_sha:$reviewed_sha,status:$status,findings:$findings}' \
    > "${path}"
}

run_evaluator() {
  "${EVALUATOR}" \
    --verdict "$1" \
    --repo blue126/IaC \
    --pr 27 \
    --sha 0123456789abcdef0123456789abcdef01234567
}

[[ -x "${EVALUATOR}" ]] || fail "runtime evaluator is missing or not executable: ${EVALUATOR}"
command -v jq >/dev/null 2>&1 || fail "jq is required"

write_verdict "${FIXTURE_DIR}/pass.json" pass \
  0123456789abcdef0123456789abcdef01234567 '[]'
run_evaluator "${FIXTURE_DIR}/pass.json" >/dev/null || fail "pass verdict must pass"

blocking_finding='[{"fingerprint":"blocking-1","severity":"blocking","actionable":true,"path":"scripts/example.sh","summary":"A concrete blocking issue"}]'
write_verdict "${FIXTURE_DIR}/needs-fix.json" needs_fix \
  0123456789abcdef0123456789abcdef01234567 "${blocking_finding}"
set +e
run_evaluator "${FIXTURE_DIR}/needs-fix.json" >/dev/null 2>&1
status=$?
set -e
[[ ${status} -eq 10 ]] || fail "needs_fix verdict must exit 10, got ${status}"

write_verdict "${FIXTURE_DIR}/human-required.json" human_required \
  0123456789abcdef0123456789abcdef01234567 '[]'
set +e
run_evaluator "${FIXTURE_DIR}/human-required.json" >/dev/null 2>&1
status=$?
set -e
[[ ${status} -eq 11 ]] || fail "human_required verdict must exit 11, got ${status}"

write_verdict "${FIXTURE_DIR}/stale.json" pass \
  fedcba9876543210fedcba9876543210fedcba98 '[]'
if run_evaluator "${FIXTURE_DIR}/stale.json" >/dev/null 2>&1; then
  fail "a verdict for a stale SHA must fail"
fi

printf '%s\n' '{"status":"pass"}' > "${FIXTURE_DIR}/malformed.json"
if run_evaluator "${FIXTURE_DIR}/malformed.json" >/dev/null 2>&1; then
  fail "a malformed verdict must fail"
fi

[[ -f "${WORKFLOW}" ]] || fail "AI review gate workflow is missing"
assert_file_contains "${WORKFLOW}" "types: [opened, synchronize, ready_for_review, reopened]"
assert_file_contains "${WORKFLOW}" 'group: ai-review-gate-${{ github.event.pull_request.number }}'
assert_file_contains "${WORKFLOW}" "name: ai-review-gate"
assert_file_contains "${WORKFLOW}" "repository: blue126/agent-project-bootstrap"
assert_file_contains "${WORKFLOW}" "ref: 3c6e3ada5ebe3790b9bbecf44c594ffa03be716e"
assert_file_contains "${WORKFLOW}" "uses: anthropics/claude-code-action@ef8bb1e43bf303cff727a1dd0b8837029fe982a2"
assert_file_contains "${WORKFLOW}" 'HEAD_SHA: ${{ github.event.pull_request.head.sha }}'
assert_file_contains "${WORKFLOW}" "persist-credentials: false"
assert_file_contains "${WORKFLOW}" "id-token: write"
assert_file_contains "${WORKFLOW}" "not a required check"

if grep -E 'pull_request_target|[[:space:]][a-z-]+:[[:space:]]*write' "${WORKFLOW}" | \
  grep -Ev '^[[:space:]]*id-token:[[:space:]]*write([[:space:]]*(#.*)?)?$' | grep -q .; then
  fail "AI review gate must not use pull_request_target or GitHub write permissions"
fi

if grep -Eq '^[[:space:]]*uses:' "${WORKFLOW}" && \
  grep -Ev '^[[:space:]]*uses:[[:space:]]+[^@[:space:]]+@[0-9a-f]{40}([[:space:]]+#.*)?$' \
    < <(grep -E '^[[:space:]]*uses:' "${WORKFLOW}") | grep -q .; then
  fail "all AI review gate actions must be pinned to full commit SHAs"
fi

echo "AI review gate contract tests passed"
