#!/bin/bash

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLASSIFIER="${REPOSITORY_ROOT}/scripts/ci/classify-pr.sh"
TERRAFORM_VALIDATOR="${REPOSITORY_ROOT}/scripts/ci/validate-terraform.sh"
ANSIBLE_VALIDATOR="${REPOSITORY_ROOT}/scripts/ci/validate-ansible.sh"
DOCUMENTATION_VALIDATOR="${REPOSITORY_ROOT}/scripts/ci/validate-documentation.sh"
REPOSITORY_VALIDATOR="${REPOSITORY_ROOT}/scripts/ci/validate-repository.sh"
FIXTURE_REPOSITORY="$(mktemp -d)"
MOCK_BIN="$(mktemp -d)"
MOCK_LOG="${MOCK_BIN}/commands.log"

cleanup() {
  rm -rf "${FIXTURE_REPOSITORY}"
  rm -rf "${MOCK_BIN}"
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

assert_output() {
  local output="$1"
  local expected="$2"

  grep -Fxq "${expected}" <<<"${output}" || fail "expected output line: ${expected}"
}

commit_fixture() {
  local path="$1"
  local content="$2"

  mkdir -p "$(dirname "${FIXTURE_REPOSITORY}/${path}")"
  printf '%s\n' "${content}" >"${FIXTURE_REPOSITORY}/${path}"
  git -C "${FIXTURE_REPOSITORY}" add -- "${path}"
  git -C "${FIXTURE_REPOSITORY}" commit -q -m "test: change ${path}"
}

git -C "${FIXTURE_REPOSITORY}" init -q
git -C "${FIXTURE_REPOSITORY}" config user.email "ci-test@example.invalid"
git -C "${FIXTURE_REPOSITORY}" config user.name "CI Test"
git -C "${FIXTURE_REPOSITORY}" commit -q --allow-empty -m "test: baseline"

base_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
commit_fixture "docs/guide.md" "documentation"
head_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
output="$(cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${base_sha}" "${head_sha}")"
assert_output "${output}" "terraform_applicable=false"
assert_output "${output}" "terraform_roots="
assert_output "${output}" "ansible_applicable=false"
assert_output "${output}" "docs_applicable=true"
assert_output "${output}" "hugo_applicable=true"
assert_output "${output}" "shell_applicable=false"
assert_output "${output}" "python_applicable=false"
assert_output "${output}" "governance_sensitive=false"

base_sha="${head_sha}"
commit_fixture "terraform/oci/main.tf" "terraform {}"
head_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
output="$(cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${base_sha}" "${head_sha}")"
assert_output "${output}" "terraform_applicable=true"
assert_output "${output}" "terraform_roots=terraform/oci"

base_sha="${head_sha}"
commit_fixture "terraform/modules/proxmox-vm/main.tf" "variable \"name\" {}"
head_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
output="$(cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${base_sha}" "${head_sha}")"
assert_output "${output}" "terraform_roots=terraform/proxmox,terraform/esxi,terraform/oci,terraform/netbox-integration"

base_sha="${head_sha}"
commit_fixture "ansible/playbooks/example.yml" "---"
commit_fixture "scripts/example.sh" "#!/bin/bash"
head_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
output="$(cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${base_sha}" "${head_sha}")"
assert_output "${output}" "ansible_applicable=true"
assert_output "${output}" "shell_applicable=true"
assert_output "${output}" "governance_sensitive=false"

base_sha="${head_sha}"
commit_fixture "requirements.txt" "ansible-core>=2.16,<2.21"
head_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
output="$(cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${base_sha}" "${head_sha}")"
assert_output "${output}" "ansible_applicable=true"

base_sha="${head_sha}"
commit_fixture ".github/workflows/repo-validation.yml" "name: validation"
head_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
output="$(cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${base_sha}" "${head_sha}")"
assert_output "${output}" "governance_sensitive=true"

base_sha="${head_sha}"
git -C "${FIXTURE_REPOSITORY}" mv .github/workflows/repo-validation.yml moved-workflow.yml
git -C "${FIXTURE_REPOSITORY}" commit -q -m "test: rename governance workflow"
head_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
output="$(cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${base_sha}" "${head_sha}")"
assert_output "${output}" "governance_sensitive=true"

base_sha="${head_sha}"
commit_fixture "tests/ci/policy-test.sh" "#!/bin/bash"
head_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
output="$(cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${base_sha}" "${head_sha}")"
assert_output "${output}" "governance_sensitive=true"

base_sha="${head_sha}"
commit_fixture "scripts/ci/validate-documentation.sh" "#!/bin/bash"
head_sha="$(git -C "${FIXTURE_REPOSITORY}" rev-parse HEAD)"
output="$(cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${base_sha}" "${head_sha}")"
assert_output "${output}" "docs_applicable=true"
assert_output "${output}" "hugo_applicable=true"

if (cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "not-a-commit" "${head_sha}") >/dev/null 2>&1; then
  fail "invalid base SHA must fail"
fi

empty_tree="$(git -C "${FIXTURE_REPOSITORY}" mktree </dev/null)"
orphan_sha="$(printf '%s\n' 'test: orphan' | git -C "${FIXTURE_REPOSITORY}" commit-tree "${empty_tree}")"
if (cd "${FIXTURE_REPOSITORY}" && "${CLASSIFIER}" "${orphan_sha}" "${head_sha}") >/dev/null 2>&1; then
  fail "commits without a merge base must fail classification"
fi

cat >"${MOCK_BIN}/mock-tool" <<'EOF'
#!/bin/bash
set -euo pipefail
tool="${0##*/}"
printf '%s %s\n' "${tool}" "$*" >>"${MOCK_LOG}"
if [[ -n "${MOCK_FAIL_MATCH:-}" && "${tool} $*" == *"${MOCK_FAIL_MATCH}"* ]]; then
  exit 9
fi
EOF
chmod +x "${MOCK_BIN}/mock-tool"
for tool in terraform python3 ansible-galaxy ansible-lint ansible-playbook; do
  ln -s "${MOCK_BIN}/mock-tool" "${MOCK_BIN}/${tool}"
done
for tool in terraform-validator ansible-validator documentation-validator; do
  ln -s "${MOCK_BIN}/mock-tool" "${MOCK_BIN}/${tool}"
done

cat >"${MOCK_BIN}/classifier" <<'EOF'
#!/bin/bash
set -euo pipefail
printf '%s\n' "${MOCK_CLASSIFICATION}"
EOF
chmod +x "${MOCK_BIN}/classifier"

export MOCK_LOG
TERRAFORM_BIN="${MOCK_BIN}/terraform" \
  "${TERRAFORM_VALIDATOR}" terraform/oci terraform/proxmox >/dev/null
grep -Fq "terraform -chdir=${REPOSITORY_ROOT} fmt -check -recursive terraform" "${MOCK_LOG}" || \
  fail "Terraform formatting command was not executed"
grep -Fq "terraform -chdir=${REPOSITORY_ROOT}/terraform/oci init -backend=false -input=false" "${MOCK_LOG}" || \
  fail "Terraform OCI init command was not executed without a backend"
grep -Fq "terraform -chdir=${REPOSITORY_ROOT}/terraform/proxmox validate" "${MOCK_LOG}" || \
  fail "Terraform Proxmox validation command was not executed"

if TERRAFORM_BIN="${MOCK_BIN}/terraform" MOCK_FAIL_MATCH="terraform/oci validate" \
  "${TERRAFORM_VALIDATOR}" terraform/oci >/dev/null 2>&1; then
  fail "Terraform validation failure must propagate"
fi

if TERRAFORM_BIN="${MOCK_BIN}/missing-terraform" \
  "${TERRAFORM_VALIDATOR}" terraform/oci >/dev/null 2>&1; then
  fail "missing Terraform must fail"
fi

: >"${MOCK_LOG}"
PYTHON_BIN="${MOCK_BIN}/python3" \
ANSIBLE_GALAXY_BIN="${MOCK_BIN}/ansible-galaxy" \
ANSIBLE_LINT_BIN="${MOCK_BIN}/ansible-lint" \
ANSIBLE_PLAYBOOK_BIN="${MOCK_BIN}/ansible-playbook" \
  "${ANSIBLE_VALIDATOR}" >/dev/null
grep -Fq "python3 -m pip install --disable-pip-version-check -r ${REPOSITORY_ROOT}/requirements.txt" "${MOCK_LOG}" || \
  fail "Ansible Python dependencies were not installed from the repository manifest"
grep -Fq "ansible-galaxy collection install -r ${REPOSITORY_ROOT}/ansible/requirements.yml" "${MOCK_LOG}" || \
  fail "Ansible collections were not installed from the repository manifest"
grep -Fq "python3 - ${REPOSITORY_ROOT}/ansible" "${MOCK_LOG}" || \
  fail "Ansible YAML files were not parsed with the CI Python runtime"
grep -Fq "ansible-lint -c ${REPOSITORY_ROOT}/.ansible-lint playbooks roles" "${MOCK_LOG}" || \
  fail "Ansible lint was not executed"
grep -Fq "ansible-playbook -i ${REPOSITORY_ROOT}/tests/ci/fixtures/inventory.yml" "${MOCK_LOG}" || \
  fail "Ansible syntax checks did not use the CI-only inventory"

if PYTHON_BIN="${MOCK_BIN}/python3" \
  ANSIBLE_GALAXY_BIN="${MOCK_BIN}/ansible-galaxy" \
  ANSIBLE_LINT_BIN="${MOCK_BIN}/ansible-lint" \
  ANSIBLE_PLAYBOOK_BIN="${MOCK_BIN}/ansible-playbook" \
  MOCK_FAIL_MATCH="ansible-lint" \
  "${ANSIBLE_VALIDATOR}" >/dev/null 2>&1; then
  fail "Ansible lint failure must propagate"
fi

: >"${MOCK_LOG}"
PYTHON_BIN="${MOCK_BIN}/python3" "${DOCUMENTATION_VALIDATOR}" false >/dev/null
grep -Fq "python3 tests/doc-claims/doc-claims-test.py" "${MOCK_LOG}" || \
  fail "Documentation claim fixtures were not executed"
grep -Fq "python3 tools/check-doc-claims.py --root . --output tmp/doc-accuracy/report.json" "${MOCK_LOG}" || \
  fail "Repository documentation claims were not checked"

if PYTHON_BIN="${MOCK_BIN}/missing-python" \
  "${DOCUMENTATION_VALIDATOR}" false >/dev/null 2>&1; then
  fail "missing Python must fail documentation validation"
fi

mock_classification="$(printf '%s\n' \
  'changed_files_count=2' \
  'terraform_applicable=true' \
  'terraform_roots=terraform/proxmox,terraform/oci' \
  'ansible_applicable=true' \
  'docs_applicable=true' \
  'hugo_applicable=false' \
  'shell_applicable=false' \
  'python_applicable=false' \
  'governance_sensitive=true')"
: >"${MOCK_LOG}"
output="$(
  MOCK_CLASSIFICATION="${mock_classification}" \
  CLASSIFIER_BIN="${MOCK_BIN}/classifier" \
  TERRAFORM_VALIDATOR_BIN="${MOCK_BIN}/terraform-validator" \
  ANSIBLE_VALIDATOR_BIN="${MOCK_BIN}/ansible-validator" \
  DOCUMENTATION_VALIDATOR_BIN="${MOCK_BIN}/documentation-validator" \
  GITHUB_OUTPUT="" \
  GITHUB_STEP_SUMMARY="${MOCK_BIN}/summary.md" \
    "${REPOSITORY_VALIDATOR}" base-sha head-sha
)"
assert_output "${output}" "governance_status=human_required enforcement=shadow"
assert_output "${output}" "repo_validation_status=passed"
grep -Fq "terraform-validator terraform/proxmox terraform/oci" "${MOCK_LOG}" || \
  fail "Repository validator did not forward selected Terraform roots"
grep -Fxq "ansible-validator " "${MOCK_LOG}" || \
  fail "Repository validator did not run Ansible validation"
grep -Fq "documentation-validator false" "${MOCK_LOG}" || \
  fail "Repository validator did not forward Hugo applicability"
grep -Fq "Governance-sensitive change" "${MOCK_BIN}/summary.md" || \
  fail "Governance-sensitive changes must be visible in the job summary"

if MOCK_CLASSIFICATION="${mock_classification}" \
  CLASSIFIER_BIN="${MOCK_BIN}/classifier" \
  TERRAFORM_VALIDATOR_BIN="${MOCK_BIN}/terraform-validator" \
  ANSIBLE_VALIDATOR_BIN="${MOCK_BIN}/ansible-validator" \
  DOCUMENTATION_VALIDATOR_BIN="${MOCK_BIN}/documentation-validator" \
  MOCK_FAIL_MATCH="terraform-validator" \
  GITHUB_OUTPUT="" \
  "${REPOSITORY_VALIDATOR}" base-sha head-sha >/dev/null 2>&1; then
  fail "Repository validator must propagate child validation failures"
fi

invalid_classification="${mock_classification/ansible_applicable=true/ansible_applicable=invalid}"
if MOCK_CLASSIFICATION="${invalid_classification}" \
  CLASSIFIER_BIN="${MOCK_BIN}/classifier" \
  GITHUB_OUTPUT="" \
  "${REPOSITORY_VALIDATOR}" base-sha head-sha >/dev/null 2>&1; then
  fail "Repository validator must reject invalid classifier booleans"
fi

missing_roots_classification="${mock_classification/terraform_roots=terraform\/proxmox,terraform\/oci/terraform_roots=}"
if MOCK_CLASSIFICATION="${missing_roots_classification}" \
  CLASSIFIER_BIN="${MOCK_BIN}/classifier" \
  GITHUB_OUTPUT="" \
  "${REPOSITORY_VALIDATOR}" base-sha head-sha >/dev/null 2>&1; then
  fail "Repository validator must reject applicable Terraform without roots"
fi

workflow="${REPOSITORY_ROOT}/.github/workflows/repo-validation.yml"
jenkinsfile="${REPOSITORY_ROOT}/Jenkinsfile"
[[ -f "${workflow}" ]] || fail "repository validation workflow is missing"
assert_file_contains "${workflow}" "types: [opened, synchronize, reopened]"
if grep -Fq "ready_for_review" "${workflow}"; then
  fail "repository validation must not rerun for an unchanged SHA on ready_for_review"
fi
assert_file_contains "${workflow}" 'group: repo-validation-${{ github.event.pull_request.number }}'
assert_file_contains "${workflow}" "cancel-in-progress: true"
assert_file_contains "${workflow}" "name: repo-validation"
assert_file_contains "${workflow}" "contents: read"
assert_file_contains "${workflow}" "persist-credentials: false"
assert_file_contains "${workflow}" 'BASE_SHA: ${{ github.event.pull_request.base.sha }}'
assert_file_contains "${workflow}" 'HEAD_SHA: ${{ github.event.pull_request.head.sha }}'
assert_file_contains "${workflow}" 'scripts/ci/validate-repository.sh "${BASE_SHA}" "${HEAD_SHA}"'

if grep -Eq '^[[:space:]]*uses:' "${workflow}" && \
  grep -Ev '^[[:space:]]*uses:[[:space:]]+[^@[:space:]]+@[0-9a-f]{40}([[:space:]]+#.*)?$' \
    < <(grep -E '^[[:space:]]*uses:' "${workflow}") | grep -q .; then
  fail "every third-party Action must use a full commit SHA"
fi

if grep -Eq 'pull_request_target|secrets\.|[[:space:]][a-z-]+:[[:space:]]*write' \
  "${workflow}"; then
  fail "repository validation workflow contains a privileged trigger, secret, or write permission"
fi

if grep -Eiq 'terraform[[:space:]]+(plan|apply)|ansible-playbook|deploy-pages|upload-pages|docker[[:space:]]+push' \
  "${workflow}"; then
  fail "repository validation workflow contains a deploy, publish, plan, or apply command"
fi

assert_file_contains "${jenkinsfile}" "stage('Approval - Terraform Apply')"
assert_file_contains "${jenkinsfile}" "Review the Terraform plan above. Proceed with apply?"
assert_file_contains "${jenkinsfile}" "stage('Approval - Ansible Deploy')"
assert_file_contains "${jenkinsfile}" "Proceed with Ansible deployment?"
input_count="$(grep -c 'input message:' "${jenkinsfile}")"
[[ "${input_count}" -eq 2 ]] || fail "Jenkinsfile must retain exactly two deployment input gates"

echo "PASS: repository validation fixtures"
