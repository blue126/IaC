#!/bin/bash

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="${1:-}"
EVALUATOR="${RUNTIME_DIR}/scripts/evaluate-ai-review-gate.sh"
VALIDATOR="${RUNTIME_DIR}/scripts/validate-review-verdict.sh"
WORKFLOW="${REPOSITORY_ROOT}/.github/workflows/claude-review.yml"
REPOSITORY_WORKFLOW="${REPOSITORY_ROOT}/.github/workflows/repo-validation.yml"
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

assert_count() {
  local path="$1"
  local pattern="$2"
  local expected="$3"
  local actual

  actual="$(grep -Ec -- "${pattern}" "${path}" || true)"
  [[ "${actual}" -eq "${expected}" ]] || {
    fail "${path} must contain ${expected} matches for ${pattern}, got ${actual}"
  }
}

extract_run_step() {
  local step_name="$1"
  local output_path="$2"

  awk -v target="      - name: ${step_name}" '
    $0 == target { found = 1; next }
    found && $0 == "        run: |" { capture = 1; next }
    capture && /^      - name:/ { exit }
    capture {
      sub(/^          /, "")
      print
    }
  ' "${WORKFLOW}" > "${output_path}"
  [[ -s "${output_path}" ]] || fail "unable to extract run step: ${step_name}"
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
[[ -x "${VALIDATOR}" ]] || fail "runtime validator is missing or not executable: ${VALIDATOR}"
command -v jq >/dev/null 2>&1 || fail "jq is required"

write_verdict "${FIXTURE_DIR}/pass.json" pass \
  0123456789abcdef0123456789abcdef01234567 '[]'
run_evaluator "${FIXTURE_DIR}/pass.json" >/dev/null || fail "pass verdict must pass"

non_blocking_finding='[{"fingerprint":"advisory-1","severity":"non_blocking","actionable":true,"path":"docs/example.md","summary":"A non-blocking suggestion"}]'
write_verdict "${FIXTURE_DIR}/pass-with-advisory.json" pass \
  0123456789abcdef0123456789abcdef01234567 "${non_blocking_finding}"
run_evaluator "${FIXTURE_DIR}/pass-with-advisory.json" >/dev/null || {
  fail "pass verdict with only non-blocking findings must pass"
}

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

jq '.repository = "other/repository"' "${FIXTURE_DIR}/pass.json" \
  > "${FIXTURE_DIR}/wrong-repository.json"
if run_evaluator "${FIXTURE_DIR}/wrong-repository.json" >/dev/null 2>&1; then
  fail "a verdict for another repository must fail"
fi

jq '.pull_request = 28' "${FIXTURE_DIR}/pass.json" \
  > "${FIXTURE_DIR}/wrong-pull-request.json"
if run_evaluator "${FIXTURE_DIR}/wrong-pull-request.json" >/dev/null 2>&1; then
  fail "a verdict for another pull request must fail"
fi

printf '%s\n' '{"status":"pass"}' > "${FIXTURE_DIR}/malformed.json"
if run_evaluator "${FIXTURE_DIR}/malformed.json" >/dev/null 2>&1; then
  fail "a malformed verdict must fail"
fi

[[ -f "${WORKFLOW}" ]] || fail "Claude Review workflow is missing"
[[ ! -e "${REPOSITORY_ROOT}/.github/workflows/claude-code-review.yml" ]] || {
  fail "legacy Claude comment workflow must be removed"
}
[[ ! -e "${REPOSITORY_ROOT}/.github/workflows/ai-review-gate.yml" ]] || {
  fail "legacy AI review gate workflow must be removed"
}

assert_file_contains "${WORKFLOW}" "name: Claude Review"
assert_file_contains "${WORKFLOW}" "types: [opened, synchronize, ready_for_review, reopened]"
assert_file_contains "${WORKFLOW}" 'group: claude-review-${{ github.event.pull_request.number }}'
assert_file_contains "${WORKFLOW}" 'if: github.event.pull_request.draft == false'
assert_file_contains "${WORKFLOW}" 'if: ${{ always() && github.event.pull_request.draft == false }}'
assert_file_contains "${WORKFLOW}" "name: claude-review"
assert_file_contains "${WORKFLOW}" "name: review-policy-gate"
assert_file_contains "${WORKFLOW}" "needs: claude-review"
assert_file_contains "${WORKFLOW}" 'verdict: ${{ steps.export-verdict.outputs.verdict }}'
assert_file_contains "${WORKFLOW}" 'STRUCTURED_OUTPUT: ${{ needs.claude-review.outputs.verdict }}'
assert_file_contains "${WORKFLOW}" 'REVIEW_RESULT: ${{ needs.claude-review.result }}'
assert_file_contains "${WORKFLOW}" "repository: blue126/agent-project-bootstrap"
assert_file_contains "${WORKFLOW}" "ref: 3c6e3ada5ebe3790b9bbecf44c594ffa03be716e"
assert_file_contains "${WORKFLOW}" "maxItems\":20"
assert_file_contains "${WORKFLOW}" "maxLength\":512"
assert_file_contains "${WORKFLOW}" 'marker="<!-- claude-review-head:${HEAD_SHA} -->"'
assert_file_contains "${WORKFLOW}" 'github-actions[bot]'
assert_file_contains "${WORKFLOW}" "Claude verdict is empty or was redacted"
assert_file_contains "${WORKFLOW}" "validate-review-verdict.sh"
assert_file_contains "${WORKFLOW}" "persist-credentials: false"
assert_file_contains "${WORKFLOW}" "not a required check"
assert_count "${WORKFLOW}" 'uses: anthropics/claude-code-action@' 1
assert_count "${WORKFLOW}" '^[[:space:]]+github_token:[[:space:]]+\$\{\{ github\.token \}\}' 1

claude_job="$({
  sed -n '/^  claude-review:/,/^  review-policy-gate:/p' "${WORKFLOW}"
} | sed '$d')"
gate_job="$(sed -n '/^  review-policy-gate:/,$p' "${WORKFLOW}")"

if grep -Eq 'id-token:[[:space:]]*write|[[:space:]][a-z-]+:[[:space:]]*write' <<< "${claude_job}"; then
  fail "Claude review job must not have OIDC or GitHub write permission"
fi
grep -Fq "pull-requests: write" <<< "${gate_job}" || fail "deterministic renderer must have PR comment permission"
if grep -Eq 'CLAUDE_CODE_OAUTH_TOKEN|id-token:[[:space:]]*write|contents:[[:space:]]*write|issues:[[:space:]]*write|actions:[[:space:]]*write|checks:[[:space:]]*write' <<< "${gate_job}"; then
  fail "review-policy-gate must receive only the documented pull-request comment write permission"
fi

if grep -Eq '^[[:space:]]*uses:' "${WORKFLOW}" && \
  grep -Ev '^[[:space:]]*uses:[[:space:]]+[^@[:space:]]+@[0-9a-f]{40}([[:space:]]+#.*)?$' \
    < <(grep -E '^[[:space:]]*uses:' "${WORKFLOW}") | grep -q .; then
  fail "all Claude Review actions must be pinned to full commit SHAs"
fi

assert_file_contains "${REPOSITORY_WORKFLOW}" "Run review policy gate contract tests"
assert_file_contains "${REPOSITORY_WORKFLOW}" "tests/ci/review-policy-gate-test.sh .governance-runtime"

renderer_script="${FIXTURE_DIR}/render-review-comment.sh"
validator_script="${FIXTURE_DIR}/validate-structured-verdict.sh"
extract_run_step "Render current HEAD review comment" "${renderer_script}"
extract_run_step "Validate structured verdict" "${validator_script}"
bash -n "${renderer_script}"
bash -n "${validator_script}"

mock_bin="${FIXTURE_DIR}/bin"
mock_log="${FIXTURE_DIR}/gh.log"
mkdir -p "${mock_bin}"
cat > "${mock_bin}/gh" <<'SH'
#!/bin/bash
set -euo pipefail
if [[ " $* " == *" --paginate "* ]]; then
  printf '%s\n' "${MOCK_COMMENT_ID:-}"
  exit 0
fi
method=""
body=""
previous=""
for argument in "$@"; do
  if [[ "${previous}" == "--method" ]]; then method="${argument}"; fi
  if [[ "${argument}" == body=* ]]; then body="${argument#body=}"; fi
  previous="${argument}"
done
{
  printf 'method=%s\n' "${method}"
  printf 'body=%s\n' "${body}"
  printf '%s\n' '--END--'
} >> "${MOCK_LOG}"
SH
chmod +x "${mock_bin}/gh"

renderer_verdict='{"repository":"blue126/IaC","pull_request":27,"reviewed_sha":"0123456789abcdef0123456789abcdef01234567","status":"pass","findings":[{"fingerprint":"advisory-1","severity":"non_blocking","actionable":false,"path":"docs/<unsafe>.md","summary":"Review <img src=x> @octocat"}]}'
: > "${mock_log}"
PATH="${mock_bin}:${PATH}" MOCK_LOG="${mock_log}" MOCK_COMMENT_ID="" \
  RUNNER_TEMP="${FIXTURE_DIR}" REPOSITORY="blue126/IaC" PULL_REQUEST="27" \
  HEAD_SHA="0123456789abcdef0123456789abcdef01234567" \
  STRUCTURED_OUTPUT="${renderer_verdict}" bash "${renderer_script}"
grep -Fq 'method=POST' "${mock_log}" || fail "renderer must create the first HEAD comment"
grep -Fq '&lt;img src=x&gt;' "${mock_log}" || fail "renderer must HTML-escape finding content"
grep -Fq '&amp;#64;octocat' "${mock_log}" || fail "renderer must neutralize user mentions"
grep -Fq 'actionable: false' "${mock_log}" || fail "renderer must display actionable state"

: > "${mock_log}"
PATH="${mock_bin}:${PATH}" MOCK_LOG="${mock_log}" MOCK_COMMENT_ID="123" \
  RUNNER_TEMP="${FIXTURE_DIR}" REPOSITORY="blue126/IaC" PULL_REQUEST="27" \
  HEAD_SHA="0123456789abcdef0123456789abcdef01234567" \
  STRUCTURED_OUTPUT="${renderer_verdict}" bash "${renderer_script}"
grep -Fq 'method=PATCH' "${mock_log}" || fail "renderer must update an existing HEAD comment"

mkdir -p "${FIXTURE_DIR}/gate/.governance-runtime/scripts"
cat > "${FIXTURE_DIR}/gate/.governance-runtime/scripts/validate-review-verdict.sh" <<'SH'
#!/bin/bash
printf '%s\n' called > "${VALIDATOR_LOG}"
SH
chmod +x "${FIXTURE_DIR}/gate/.governance-runtime/scripts/validate-review-verdict.sh"
if (cd "${FIXTURE_DIR}/gate" && \
  RUNNER_TEMP="${FIXTURE_DIR}" VALIDATOR_LOG="${FIXTURE_DIR}/validator.log" \
  REVIEW_RESULT="failure" REVIEW_CONCLUSION="success" \
  STRUCTURED_OUTPUT="${renderer_verdict}" REPOSITORY="blue126/IaC" PULL_REQUEST="27" \
  HEAD_SHA="0123456789abcdef0123456789abcdef01234567" bash "${validator_script}") >/dev/null 2>&1; then
  fail "gate preconditions must reject a failed Claude review job"
fi
[[ ! -e "${FIXTURE_DIR}/validator.log" ]] || fail "failed review must not reach the runtime validator"

for rejected_case in \
  'skipped|success|valid' \
  'success|failure|valid' \
  'success|success|empty'; do
  IFS='|' read -r review_result review_conclusion output_kind <<< "${rejected_case}"
  structured_output="${renderer_verdict}"
  if [[ "${output_kind}" == "empty" ]]; then structured_output=""; fi
  if (cd "${FIXTURE_DIR}/gate" && \
    RUNNER_TEMP="${FIXTURE_DIR}" VALIDATOR_LOG="${FIXTURE_DIR}/validator.log" \
    REVIEW_RESULT="${review_result}" REVIEW_CONCLUSION="${review_conclusion}" \
    STRUCTURED_OUTPUT="${structured_output}" REPOSITORY="blue126/IaC" PULL_REQUEST="27" \
    HEAD_SHA="0123456789abcdef0123456789abcdef01234567" \
    bash "${validator_script}") >/dev/null 2>&1; then
    fail "gate preconditions accepted rejected case: ${rejected_case}"
  fi
done
[[ ! -e "${FIXTURE_DIR}/validator.log" ]] || fail "rejected inputs must not reach the runtime validator"

(cd "${FIXTURE_DIR}/gate" && \
  RUNNER_TEMP="${FIXTURE_DIR}" VALIDATOR_LOG="${FIXTURE_DIR}/validator.log" \
  REVIEW_RESULT="success" REVIEW_CONCLUSION="success" \
  STRUCTURED_OUTPUT="${renderer_verdict}" REPOSITORY="blue126/IaC" PULL_REQUEST="27" \
  HEAD_SHA="0123456789abcdef0123456789abcdef01234567" bash "${validator_script}") >/dev/null
[[ -s "${FIXTURE_DIR}/validator.log" ]] || fail "valid upstream output must reach the runtime validator"

echo "Review policy gate contract tests passed"
