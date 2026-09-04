#!/bin/bash
# Synchronize the host OpenCode provider configuration into an existing Docker
# Sandbox, then run the OpenCode server as a long-lived attached session.

set -euo pipefail

usage() {
    echo "Usage: OPENCODE_SERVER_PASSWORD=... $0 <sandbox-name>" >&2
    exit 2
}

[[ $# -eq 1 ]] || usage
sandbox_name="$1"
host_auth="${HOME}/.local/share/opencode/auth.json"

for command_name in sbx jq mktemp opencode; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Error: required command not found: $command_name" >&2
        exit 1
    fi
done

if [[ ! -r "$host_auth" ]] || ! jq empty "$host_auth" >/dev/null 2>&1; then
    echo "Error: missing, unreadable, or invalid JSON: $host_auth" >&2
    exit 1
fi

sandbox_json="$(sbx ls --json)"
sandbox_count="$(jq --arg name "$sandbox_name" '[.sandboxes[] | select(.name == $name)] | length' <<<"$sandbox_json")"
if [[ "$sandbox_count" != "1" ]]; then
    echo "Error: expected one existing Sandbox named $sandbox_name" >&2
    exit 1
fi

agent_name="$(jq -r --arg name "$sandbox_name" '.sandboxes[] | select(.name == $name) | .agent' <<<"$sandbox_json")"
if [[ "$agent_name" != "opencode" ]]; then
    echo "Error: $sandbox_name uses agent $agent_name, not opencode" >&2
    exit 1
fi

ports_json="$(sbx ports "$sandbox_name" --json)"
server_mapping_count="$(jq '[.[] | select(.sandbox_port == 4096 and .protocol == "tcp")] | length' <<<"$ports_json")"
if [[ "$server_mapping_count" != "1" ]]; then
    echo "Error: expected exactly one TCP mapping for Sandbox port 4096" >&2
    exit 1
fi

host_ip="$(jq -r '.[] | select(.sandbox_port == 4096 and .protocol == "tcp") | .host_ip' <<<"$ports_json")"
if [[ "$host_ip" != "127.0.0.1" ]]; then
    password_length=0
    if [[ -n "${OPENCODE_SERVER_PASSWORD:-}" ]]; then
        password_length="${#OPENCODE_SERVER_PASSWORD}"
    fi
    if [[ "$password_length" -lt 20 ]]; then
        echo "Error: LAN mode requires OPENCODE_SERVER_PASSWORD with at least 20 characters" >&2
        exit 1
    fi
fi

host_stage="$(mktemp -d "${TMPDIR:-/tmp}/opencode-sandbox-sync.XXXXXX")"
sandbox_stage="/tmp/opencode-host-sync-$$"
sandbox_payload="$sandbox_stage/$(basename "$host_stage")"
sandbox_stage_created=false
cleanup() {
    rm -rf "$host_stage"
    if [[ "$sandbox_stage_created" == true ]]; then
        sbx exec "$sandbox_name" sudo rm -rf "$sandbox_stage" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# Let OpenCode resolve both opencode.json and opencode.jsonc. Host MCP entries
# are omitted because Docker Sandboxes manage MCP through their dynamic Gateway.
# Resolved local plugin URLs are remapped to the copied Sandbox plugin directory.
host_plugin_prefix="file://${HOME}/.config/opencode/plugins/"
sandbox_plugin_prefix="file:///home/agent/.config/opencode/plugins/"
opencode debug config --pure | jq \
    --arg host_plugin_prefix "$host_plugin_prefix" \
    --arg sandbox_plugin_prefix "$sandbox_plugin_prefix" \
    --slurpfile host_auth "$host_auth" '
      ((.provider // {}) | keys) as $configured_provider_ids
      | (($host_auth[0] // {}) | keys) as $authenticated_provider_ids
      | (($configured_provider_ids + $authenticated_provider_ids) | unique) as $host_provider_ids
      | del(.mcp)
      | (.plugin // []) |= map(
          if startswith($host_plugin_prefix)
          then $sandbox_plugin_prefix + ltrimstr($host_plugin_prefix)
          else . end)
      | .disabled_providers = (
          ((.disabled_providers // [])
          + (["anthropic", "google", "groq", "openai", "openrouter", "xai"] - $host_provider_ids))
          | unique)
    ' > "$host_stage/opencode.json"
jq empty "$host_stage/opencode.json"
install -m 0600 "$host_auth" "$host_stage/auth.json"

if [[ -f "${HOME}/.config/opencode/antigravity-accounts.json" ]]; then
    install -m 0600 "${HOME}/.config/opencode/antigravity-accounts.json" \
        "$host_stage/antigravity-accounts.json"
fi
if [[ -d "${HOME}/.config/opencode/plugins" ]]; then
    cp -R "${HOME}/.config/opencode/plugins" "$host_stage/plugins"
fi

sbx exec "$sandbox_name" sudo install -d -m 0700 -o 1000 -g 1000 "$sandbox_stage"
sandbox_stage_created=true
sbx cp "$host_stage/." "$sandbox_name:$sandbox_stage"
sbx exec "$sandbox_name" sudo chown -R 1000:1000 "$sandbox_stage"

sbx exec "$sandbox_name" sudo bash -lc '
set -eu
stage="$1"
config_dir=/home/agent/.config/opencode
auth_dir=/home/agent/.local/share/opencode
install -d -m 0700 -o 1000 -g 1000 "$config_dir" "$auth_dir"

base="$(mktemp)"
if [[ -f "$config_dir/opencode.json" ]]; then
    cp "$config_dir/opencode.json" "$base"
else
    printf "%s\n" "{}" > "$base"
fi

jq -s '\''
  def rewrite_loopback:
    if type == "string" then
      sub("^http://localhost(?=[:/]|$)"; "http://host.docker.internal")
      | sub("^http://127[.]0[.]0[.]1(?=[:/]|$)"; "http://host.docker.internal")
    else . end;
  .[0] * .[1]
  | (.provider // {}) |= with_entries(
      if (.value.options.baseURL? | type) == "string"
      then .value.options.baseURL |= rewrite_loopback
      else . end)
'\'' "$base" "$stage/opencode.json" > "$config_dir/opencode.json.new"

jq empty "$config_dir/opencode.json.new"
chown 1000:1000 "$config_dir/opencode.json.new"
chmod 0600 "$config_dir/opencode.json.new"
mv "$config_dir/opencode.json.new" "$config_dir/opencode.json"

install -m 0600 -o 1000 -g 1000 "$stage/auth.json" "$auth_dir/auth.json"
if [[ -f "$stage/antigravity-accounts.json" ]]; then
    install -m 0600 -o 1000 -g 1000 "$stage/antigravity-accounts.json" \
        "$config_dir/antigravity-accounts.json"
fi
if [[ -d "$stage/plugins" ]]; then
    install -d -m 0700 -o 1000 -g 1000 "$config_dir/plugins"
    cp -R "$stage/plugins/." "$config_dir/plugins/"
    chown -R 1000:1000 "$config_dir/plugins"
fi

rm -f "$base"
rm -rf "$stage"
' _ "$sandbox_payload"
sandbox_stage_created=false
cleanup
trap - EXIT

echo "OpenCode host provider configuration synchronized to $sandbox_name"

run_args=(run --name "$sandbox_name")
if [[ -n "${OPENCODE_SERVER_PASSWORD:-}" ]]; then
    run_args+=(--env OPENCODE_SERVER_PASSWORD)
fi
if [[ -n "${OPENCODE_SERVER_USERNAME:-}" ]]; then
    run_args+=(--env OPENCODE_SERVER_USERNAME)
fi

exec sbx "${run_args[@]}" -- serve --hostname 0.0.0.0 --port 4096
