#!/bin/bash
set -euo pipefail

if [[ "${1:-}" != "--allow-sandbox-install" || "$#" -ne 1 ]]; then
  printf 'Usage: bash .claude/skills/run-iac/driver.sh --allow-sandbox-install\n' >&2
  printf 'Obtain user approval for Sandbox creation and Kit dependency installation first.\n' >&2
  exit 2
fi
if [[ -n "${SANDBOX_ID:-}" ]]; then
  printf 'ERROR: Run the driver on the host, not inside a Sandbox.\n' >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
root=$(cd -- "$script_dir/../../.." && pwd -P)
cd -- "$root"
if [[ ! -f .git ]]; then
  printf 'ERROR: Use an assigned linked task worktree, not the main checkout.\n' >&2
  exit 1
fi
branch=$(git symbolic-ref --short HEAD)
if [[ "$branch" = main || "$branch" = master ]]; then
  printf 'ERROR: Main and master are coordination-only branches.\n' >&2
  exit 1
fi
for executable in sbx python3; do
  if ! command -v "$executable" >/dev/null; then
    printf 'ERROR: Missing host prerequisite: %s. Ask before installing it.\n' "$executable" >&2
    exit 1
  fi
done
if ! grep -qx 'version: "1.3.0"' .sandbox-kit/spec.yaml; then
  printf 'ERROR: Re-verify this driver and its Sandbox naming for the current Kit version.\n' >&2
  exit 1
fi
sbx version
sbx kit validate ./.sandbox-kit

name="iac-claude-run-iac-$(date -u +%Y%m%d%H%M%S)-$$-direct-v130"
existing=$(sbx ls --quiet)
if printf '%s\n' "$existing" | grep -Fxq "$name"; then
  printf 'ERROR: Refusing to reuse existing Sandbox %s.\n' "$name" >&2
  exit 1
fi
printf 'Task branch: %s\nWorkspace: %s\nNew Sandbox: %s\n' "$branch" "$root" "$name"
created=false
stop_created_sandbox() {
  result=$?
  trap - EXIT
  if [[ "$created" = true ]]; then
    if sbx stop "$name"; then
      printf 'Stopped task Sandbox; retained for inspection: %s\n' "$name"
    else
      printf 'ERROR: Could not stop task Sandbox: %s\n' "$name" >&2
      result=1
    fi
  else
    printf 'Creation did not succeed; no existing Sandbox was stopped or removed.\n' >&2
  fi
  exit "$result"
}
trap stop_created_sandbox EXIT

sbx create --name "$name" --kit ./.sandbox-kit claude "$root"
created=true
sbx exec --workdir "$root" "$name" bash "$script_dir/smoke.sh"
