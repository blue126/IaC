#!/bin/bash

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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

assert_file_lacks() {
  local path="$1"
  local pattern="$2"

  if grep -Eq -- "${pattern}" "${path}"; then
    fail "${path} must not reference: ${pattern}"
  fi
}

assert_step_precedes() {
  local first_step="$1"
  local second_step="$2"
  local first_line
  local second_line

  first_line="$(grep -nF "      - name: ${first_step}" "${WORKFLOW}" | cut -d: -f1 | sed -n '1p')"
  second_line="$(grep -nF "      - name: ${second_step}" "${WORKFLOW}" | cut -d: -f1 | sed -n '1p')"
  [[ -n "${first_line}" && -n "${second_line}" && "${first_line}" -lt "${second_line}" ]] || {
    fail "${first_step} must precede ${second_step}"
  }
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

run_validator() {
  local verdict_path="$1"
  local review_result="${2-success}"
  local review_conclusion="${3-success}"

  RUNNER_TEMP="${FIXTURE_DIR}" \
    REVIEW_RESULT="${review_result}" \
    REVIEW_CONCLUSION="${review_conclusion}" \
    STRUCTURED_OUTPUT="$(<"${verdict_path}")" \
    bash "${validator_script}"
}

run_evaluator() {
  STRUCTURED_OUTPUT="$(<"$1")" bash "${evaluator_script}"
}

write_verdict() {
  local path="$1"
  local status="$2"
  local findings="$3"

  jq -n --arg status "${status}" --argjson findings "${findings}" \
    '{status:$status,findings:$findings}' > "${path}"
}

[[ -f "${WORKFLOW}" ]] || fail "Claude Review workflow is missing"
[[ ! -e "${REPOSITORY_ROOT}/.github/workflows/claude-code-review.yml" ]] || {
  fail "legacy Claude comment workflow must be removed"
}
[[ ! -e "${REPOSITORY_ROOT}/.github/workflows/ai-review-gate.yml" ]] || {
  fail "legacy AI review gate workflow must be removed"
}
command -v jq >/dev/null 2>&1 || fail "jq is required"

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
assert_file_contains "${WORKFLOW}" '${{ github.event.pull_request.base.sha }}'
assert_file_contains "${WORKFLOW}" '"required":["status","findings"]'
assert_file_lacks "${WORKFLOW}" '"repository"|"pull_request"|"reviewed_sha"'
assert_file_contains "${WORKFLOW}" "maxItems\":20"
assert_file_contains "${WORKFLOW}" "maxLength\":512"
assert_file_contains "${WORKFLOW}" 'marker="<!-- claude-review-head:${HEAD_SHA} -->"'
assert_file_contains "${WORKFLOW}" 'github-actions[bot]'
assert_file_contains "${WORKFLOW}" "Claude verdict is empty or was redacted"
assert_file_contains "${WORKFLOW}" "persist-credentials: false"
assert_file_contains "${WORKFLOW}" "Validated verdict has an unknown status"
assert_file_contains "${WORKFLOW}" "not a required check"
assert_count "${WORKFLOW}" 'uses: anthropics/claude-code-action@' 1
assert_count "${WORKFLOW}" '^[[:space:]]+github_token:[[:space:]]+\$\{\{ github\.token \}\}' 1
assert_file_lacks "${WORKFLOW}" 'agent-project-bootstrap|\.governance-runtime|validate-review-verdict\.sh|evaluate-ai-review-gate\.sh'
assert_file_lacks "${REPOSITORY_WORKFLOW}" 'agent-project-bootstrap|\.governance-runtime'
assert_step_precedes "Validate structured verdict" "Render current HEAD review comment"
assert_file_contains "${REPOSITORY_WORKFLOW}" "Run review policy gate contract tests"
grep -Fxq '        run: tests/ci/review-policy-gate-test.sh' "${REPOSITORY_WORKFLOW}" || {
  fail "repository validation must invoke the local review policy gate test without arguments"
}

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

validator_script="${FIXTURE_DIR}/validate-structured-verdict.sh"
evaluator_script="${FIXTURE_DIR}/evaluate-structured-verdict.sh"
renderer_script="${FIXTURE_DIR}/render-review-comment.sh"
extract_run_step "Validate structured verdict" "${validator_script}"
extract_run_step "Evaluate structured verdict" "${evaluator_script}"
extract_run_step "Render current HEAD review comment" "${renderer_script}"
bash -n "${validator_script}"
bash -n "${evaluator_script}"
bash -n "${renderer_script}"

pass_verdict="${FIXTURE_DIR}/pass.json"
needs_fix_verdict="${FIXTURE_DIR}/needs-fix.json"
human_required_verdict="${FIXTURE_DIR}/human-required.json"
write_verdict "${pass_verdict}" pass '[]'
write_verdict "${needs_fix_verdict}" needs_fix \
  '[{"fingerprint":"blocking-1","severity":"blocking","actionable":true,"path":"scripts/example.sh","summary":"A concrete blocking issue"}]'
write_verdict "${human_required_verdict}" human_required \
  '[{"fingerprint":"ambiguous-1","severity":"blocking","actionable":false,"path":"docs/example.md","summary":"A blocking concern needs human judgment"}]'
pass_with_advisory_verdict="${FIXTURE_DIR}/pass-with-advisory.json"
write_verdict "${pass_with_advisory_verdict}" pass \
  '[{"fingerprint":"advisory-1","severity":"non_blocking","actionable":true,"path":"docs/example.md","summary":"A non-blocking suggestion"}]'

run_validator "${pass_verdict}" >/dev/null || fail "valid pass verdict must validate"
run_evaluator "${pass_verdict}" >/dev/null || fail "pass verdict must exit 0"
run_validator "${pass_with_advisory_verdict}" >/dev/null || fail "pass verdict with an advisory must validate"
run_evaluator "${pass_with_advisory_verdict}" >/dev/null || fail "pass verdict with an advisory must exit 0"
run_validator "${needs_fix_verdict}" >/dev/null || fail "valid needs_fix verdict must validate"
set +e
run_evaluator "${needs_fix_verdict}" >/dev/null 2>&1
status=$?
set -e
[[ ${status} -eq 10 ]] || fail "needs_fix verdict must exit 10, got ${status}"
run_validator "${human_required_verdict}" >/dev/null || fail "valid human_required verdict must validate"
set +e
run_evaluator "${human_required_verdict}" >/dev/null 2>&1
status=$?
set -e
[[ ${status} -eq 11 ]] || fail "human_required verdict must exit 11, got ${status}"

human_required_actionable_verdict="${FIXTURE_DIR}/human-required-actionable.json"
jq '.status = "human_required"' "${needs_fix_verdict}" > "${human_required_actionable_verdict}"
run_validator "${human_required_actionable_verdict}" >/dev/null || {
  fail "human_required verdict may retain an actionable blocking finding"
}

invalid_verdict="${FIXTURE_DIR}/invalid.json"
for invalid_case in extra-top-level invalid-finding unknown-severity duplicate-fingerprint absolute-path parent-path oversized-path oversized-fingerprint oversized-summary too-many-findings inconsistent-pass inconsistent-needs-fix malformed empty bad-upstream; do
  case "${invalid_case}" in
    extra-top-level)
      jq '.repository = "blue126/IaC"' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    invalid-finding)
      jq '.findings = [{"fingerprint":7,"severity":"blocking","actionable":"yes","path":"docs/example.md","summary":"Bad types"}]' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    unknown-severity)
      jq '.findings = [{"fingerprint":"unknown-severity","severity":"unexpected","actionable":false,"path":"docs/example.md","summary":"Unknown severity"}]' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    duplicate-fingerprint)
      jq '.findings = [
        {"fingerprint":"duplicate","severity":"non_blocking","actionable":true,"path":"docs/one.md","summary":"One"},
        {"fingerprint":"duplicate","severity":"non_blocking","actionable":false,"path":"docs/two.md","summary":"Two"}
      ]' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    absolute-path)
      jq '.findings = [{"fingerprint":"absolute","severity":"non_blocking","actionable":true,"path":"/etc/passwd","summary":"Illegal path"}]' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    parent-path)
      jq '.findings = [{"fingerprint":"parent","severity":"non_blocking","actionable":true,"path":"docs/../secret","summary":"Illegal path"}]' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    oversized-path)
      jq --arg path "$(printf 'a%.0s' {1..513})" '.findings = [{"fingerprint":"oversized","severity":"non_blocking","actionable":true,"path":$path,"summary":"Oversized path"}]' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    oversized-fingerprint)
      jq --arg fingerprint "$(printf 'a%.0s' {1..257})" '.findings = [{"fingerprint":$fingerprint,"severity":"non_blocking","actionable":true,"path":"docs/example.md","summary":"Oversized fingerprint"}]' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    oversized-summary)
      jq --arg summary "$(printf 'a%.0s' {1..2001})" '.findings = [{"fingerprint":"summary","severity":"non_blocking","actionable":true,"path":"docs/example.md","summary":$summary}]' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    too-many-findings)
      jq '.findings = [range(0; 21) | {fingerprint:("finding-" + tostring),severity:"non_blocking",actionable:true,path:"docs/example.md",summary:"Too many"}]' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    inconsistent-pass)
      jq '.status = "pass"' "${needs_fix_verdict}" > "${invalid_verdict}"
      ;;
    inconsistent-needs-fix)
      jq '.status = "needs_fix" | .findings = []' "${pass_verdict}" > "${invalid_verdict}"
      ;;
    malformed)
      printf '%s\n' '{"status":"pass"}' > "${invalid_verdict}"
      ;;
    empty)
      : > "${invalid_verdict}"
      ;;
    bad-upstream)
      cp "${pass_verdict}" "${invalid_verdict}"
      ;;
  esac

  if [[ "${invalid_case}" == "bad-upstream" ]]; then
    if run_validator "${invalid_verdict}" failure success >/dev/null 2>&1; then
      fail "failed upstream review must fail before validation"
    fi
  elif run_validator "${invalid_verdict}" >/dev/null 2>&1; then
    fail "${invalid_case} verdict must fail local validation"
  fi
done

for upstream_case in 'skipped|success' 'success|failure' 'success|' 'success|redacted'; do
  IFS='|' read -r review_result review_conclusion <<< "${upstream_case}"
  if run_validator "${pass_verdict}" "${review_result}" "${review_conclusion}" >/dev/null 2>&1; then
    fail "upstream state must fail before local validation: ${upstream_case}"
  fi
done

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

: > "${mock_log}"
PATH="${mock_bin}:${PATH}" MOCK_LOG="${mock_log}" MOCK_COMMENT_ID="" \
  RUNNER_TEMP="${FIXTURE_DIR}" REPOSITORY="blue126/IaC" PULL_REQUEST="27" \
  HEAD_SHA="0123456789abcdef0123456789abcdef01234567" \
  STRUCTURED_OUTPUT="$(<"${pass_verdict}")" bash "${renderer_script}"
grep -Fq 'method=POST' "${mock_log}" || fail "renderer must create the first HEAD comment"

renderer_verdict="${FIXTURE_DIR}/renderer.json"
write_verdict "${renderer_verdict}" pass \
  '[{"fingerprint":"advisory-1","severity":"non_blocking","actionable":false,"path":"docs/unsafe.md","summary":"Review <img src=x> @octocat"}]'
run_validator "${renderer_verdict}" >/dev/null || fail "renderer fixture must validate"
: > "${mock_log}"
PATH="${mock_bin}:${PATH}" MOCK_LOG="${mock_log}" MOCK_COMMENT_ID="123" \
  RUNNER_TEMP="${FIXTURE_DIR}" REPOSITORY="blue126/IaC" PULL_REQUEST="27" \
  HEAD_SHA="0123456789abcdef0123456789abcdef01234567" \
  STRUCTURED_OUTPUT="$(<"${renderer_verdict}")" bash "${renderer_script}"
grep -Fq 'method=PATCH' "${mock_log}" || fail "renderer must update an existing HEAD comment"
grep -Fq '&lt;img src=x&gt;' "${mock_log}" || fail "renderer must HTML-escape finding content"
grep -Fq '&amp;#64;octocat' "${mock_log}" || fail "renderer must neutralize user mentions"
grep -Fq 'actionable: false' "${mock_log}" || fail "renderer must display actionable state"

echo "Review policy gate contract tests passed"
