#!/bin/bash
# Run the hermetic test suites selected by the PR classifier with this checkout's
# pinned .venv toolchain (scripts/setup-dev-env.sh). The same entry point serves
# local runs and CI. A test whose prerequisite is missing is reported as NOT RUN
# with the reason; REPO_VALIDATION_REQUIRE_ALL=1 (set by CI) turns any NOT RUN
# into a failure. Tests that need root run only with REPO_VALIDATION_ALLOW_ROOT=1,
# so a developer host never creates network namespaces unasked.

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_BIN="${TEST_SUITES_VENV_BIN:-${REPOSITORY_ROOT}/.venv/bin}"
REQUIRE_ALL="${REPO_VALIDATION_REQUIRE_ALL:-0}"
ALLOW_ROOT="${REPO_VALIDATION_ALLOW_ROOT:-0}"
PLATFORM="$(uname -s)"

if [[ "$#" -eq 0 ]]; then
  echo "test_suites_status=not_applicable reason=no_test_suites_selected"
  exit 0
fi

for suite in "$@"; do
  case "${suite}" in
    employee-workspace | oci-hub | hapi-workspace | gateway-backup) ;;
    *)
      echo "Unsupported test suite: ${suite}" >&2
      exit 2
      ;;
  esac
done

for tool in python3 ansible-playbook; do
  if [[ ! -x "${VENV_BIN}/${tool}" ]]; then
    echo "Required toolchain is unavailable: ${VENV_BIN}/${tool}; run ./scripts/setup-dev-env.sh" >&2
    exit 1
  fi
done

# Keep the prefix short: tests bind tmux and AF_UNIX sockets several levels below
# TMPDIR, and socket paths are limited to about 104-108 bytes.
work_root="$(mktemp -d "${TMPDIR:-/tmp}/ts.XXXXXX")"
ran_as_root=false
cleanup() {
  if ! rm -rf "${work_root}" 2>/dev/null && [[ "${ran_as_root}" == true ]]; then
    sudo -n rm -rf "${work_root}"
  fi
}
trap cleanup EXIT

# Keep every test write inside the work root: temporary files and Ansible's
# local/remote temp and home directories (which otherwise default to ~/.ansible).
mkdir -p "${work_root}/.ansible"
export TMPDIR="${work_root}"
export ANSIBLE_HOME="${work_root}/.ansible"
export ANSIBLE_LOCAL_TEMP="${ANSIBLE_HOME}/tmp"
export ANSIBLE_REMOTE_TEMP="${ANSIBLE_HOME}/remote-tmp"
export PATH="${VENV_BIN}:${PATH}:/usr/sbin:/sbin"
unset ANSIBLE_CONFIG ANSIBLE_INVENTORY ANSIBLE_VAULT_PASSWORD_FILE ANSIBLE_VAULT_IDENTITY_LIST
# Generated key and certificate modes must not depend on the caller's umask.
umask 022

tool_path="${TEST_SUITES_TOOL_PATH:-${PATH}}"
suite_passed=0
suite_not_run=0
total_not_run=0

not_run() {
  echo "NOT RUN: $1 ($2)"
  suite_not_run=$((suite_not_run + 1))
  total_not_run=$((total_not_run + 1))
}

# run_test PATH [--linux] [--root] [--needs TOOL...]
run_test() {
  local path="$1"
  shift
  local linux_only=false
  local needs_root=false
  local tools=()
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --linux) linux_only=true ;;
      --root) needs_root=true; linux_only=true ;;
      --needs) shift; tools+=("$1") ;;
    esac
    shift
  done

  if [[ "${linux_only}" == true && "${PLATFORM}" != Linux ]]; then
    not_run "${path}" "needs Linux"
    return 0
  fi
  local tool
  for tool in "${tools[@]+"${tools[@]}"}"; do
    if ! PATH="${tool_path}" command -v "${tool}" >/dev/null 2>&1; then
      not_run "${path}" "needs ${tool}"
      return 0
    fi
  done

  local command=()
  case "${path}" in
    *.py) command=("${VENV_BIN}/python3" "${path}") ;;
    *.sh) command=(bash "${path}") ;;
  esac
  if [[ "${needs_root}" == true ]]; then
    if [[ "${ALLOW_ROOT}" != 1 ]]; then
      not_run "${path}" "needs root; set REPO_VALIDATION_ALLOW_ROOT=1 on a disposable host"
      return 0
    fi
    if [[ "$(id -u)" -ne 0 ]]; then
      if ! sudo -n true 2>/dev/null; then
        not_run "${path}" "needs passwordless sudo"
        return 0
      fi
      ran_as_root=true
      command=(sudo -n env "PATH=${PATH}" "TMPDIR=${TMPDIR}" "ANSIBLE_HOME=${ANSIBLE_HOME}"
        "ANSIBLE_LOCAL_TEMP=${ANSIBLE_LOCAL_TEMP}" "ANSIBLE_REMOTE_TEMP=${ANSIBLE_REMOTE_TEMP}"
        "${command[@]}")
    fi
  fi

  local started="${SECONDS}"
  local status=0
  (cd "${REPOSITORY_ROOT}" && "${command[@]}") || status=$?
  if [[ "${status}" -eq 77 ]]; then
    # The test itself reported NOT RUN (for example missing kernel capabilities).
    not_run "${path}" "test reported NOT RUN"
    return 0
  fi
  if [[ "${status}" -ne 0 ]]; then
    echo "FAIL: ${path} (exit ${status})" >&2
    exit 1
  fi
  echo "PASS: ${path} ($((SECONDS - started))s)"
  suite_passed=$((suite_passed + 1))
}

run_suite() {
  case "$1" in
    employee-workspace)
      # test-desktop-oci.py also loads test-desktop-lifecycle.py and test-browser-lifecycle.py.
      run_test tests/employee-workspace/test-desktop-oci.py --needs openssl
      run_test tests/employee-workspace/test-desktop-update.py --needs openssl
      run_test tests/employee-workspace/test-locale.py --needs sshd --needs ssh-keygen
      run_test tests/employee-workspace/test-login-browser-unit.py
      run_test tests/employee-workspace/test-login.py --needs tmux
      ;;
    oci-hub)
      run_test tests/oci-hub/test-offline.py
      run_test tests/oci-hub/test-host-forward.py
      run_test tests/oci-hub/test-native-mosh.py --needs sshd --needs ssh-keygen
      # The authorization tasks set the group to the user name (Linux user-private groups).
      run_test tests/oci-hub/test-native-authorization.py --linux --needs ssh-keygen
      run_test tests/oci-hub/test-spoke-reconcile.py --root --needs wg-quick
      run_test tests/oci-hub/test-network.py --root --needs ip --needs nft --needs iptables
      ;;
    hapi-workspace)
      run_test tests/hapi-workspace/test-login-agent.py --needs tmux
      run_test tests/hapi-workspace/test-hub-config.py
      run_test tests/hapi-workspace/test-hub-boundary.py
      ;;
    gateway-backup)
      run_test tests/gateway-backup/gateway-backup-test.sh
      run_test tests/gateway-backup/gateway-backup-ctl-test.sh --linux --needs setsid --needs flock
      ;;
  esac
}

for suite in "$@"; do
  suite_passed=0
  suite_not_run=0
  run_suite "${suite}"
  echo "test_suite_status=passed suite=${suite} passed=${suite_passed} not_run=${suite_not_run}"
done

if [[ "${total_not_run}" -gt 0 && "${REQUIRE_ALL}" == 1 ]]; then
  echo "${total_not_run} test(s) NOT RUN while REPO_VALIDATION_REQUIRE_ALL=1" >&2
  exit 1
fi

echo "test_suites_status=passed suites=$(IFS=,; echo "$*") not_run=${total_not_run}"
