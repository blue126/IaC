#!/bin/bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
installer="$project_root/.sandbox-kit/files/home/.local/bin/install-iac-agent-instructions"
source_file="$project_root/.sandbox-kit/files/home/.local/share/iac-agent/sandbox-rules.md"
test_root="$(mktemp -d)"
agent_home="$test_root/home/agent"

cleanup() {
  rm -rf "$test_root"
}
trap cleanup EXIT

targets=(
  "$agent_home/.codex/AGENTS.md"
  "$agent_home/.claude/CLAUDE.md"
  "$agent_home/.config/opencode/AGENTS.md"
)

run_installer() {
  IAC_AGENT_HOME="$agent_home" \
  IAC_AGENT_UID="$(id -u)" \
  IAC_AGENT_GID="$(id -g)" \
  IAC_SANDBOX_RULES_SOURCE="$source_file" \
    "$installer"
}

for target in "${targets[@]}"; do
  mkdir -p "$(dirname "$target")"
  printf 'vendor-policy:%s\n' "$(basename "$(dirname "$target")")" > "$target"
done

run_installer
first_checksums="$(cksum "${targets[@]}")"
run_installer
second_checksums="$(cksum "${targets[@]}")"
[[ "$first_checksums" == "$second_checksums" ]]

for target in "${targets[@]}"; do
  [[ "$(grep -Fc 'vendor-policy:' "$target")" == "1" ]]
  [[ "$(grep -Fxc '<!-- BEGIN IAC SANDBOX RULES -->' "$target")" == "1" ]]
  [[ "$(grep -Fxc '<!-- END IAC SANDBOX RULES -->' "$target")" == "1" ]]
  [[ "$(grep -Fc 'iac-sandbox-v1.3.0' "$target")" == "1" ]]
  diff -u "$source_file" <(
    awk '
      $0 == "<!-- BEGIN IAC SANDBOX RULES -->" { inside = 1; next }
      $0 == "<!-- END IAC SANDBOX RULES -->" { inside = 0; next }
      inside { print }
    ' "$target"
  )
done

sed -i.bak 's/iac-sandbox-v1\.3\.0/iac-sandbox-v1\.2\.0/' "${targets[0]}"
rm -f "${targets[0]}.bak"
run_installer
if grep -Fq 'iac-sandbox-v1.2.0' "${targets[0]}"; then
  echo 'Installer did not replace the old ruleset marker' >&2
  exit 1
fi
grep -Fq 'iac-sandbox-v1.3.0' "${targets[0]}"

printf '%s\n' '<!-- BEGIN IAC SANDBOX RULES -->' >> "${targets[1]}"
before_checksums="$(cksum "${targets[@]}")"
if run_installer 2> "$test_root/malformed-marker-error.txt"; then
  echo 'Installer unexpectedly accepted malformed markers' >&2
  exit 1
fi
grep -Fq 'Malformed managed instruction block' "$test_root/malformed-marker-error.txt"
after_checksums="$(cksum "${targets[@]}")"
[[ "$before_checksums" == "$after_checksums" ]]

printf '%s\n' 'Sandbox agent instruction installer tests passed.'
