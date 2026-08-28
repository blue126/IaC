#!/usr/bin/env bash
#
# Everything that has to happen ON THE HOST before the container starts.
# Called from initializeCommand, on create and on every start.
#
#   1. Derive the container's agent configs from your own, rewriting the host
#      loopback endpoints that mean nothing inside a container.
#   2. Bring up Playwright MCP on the host, so agents in the container drive a
#      browser you can actually see.
#
#   host (macOS)          dev container
#   ------------          -------------
#   visible browser  <--  playwright-mcp (HTTP :8931)  <--  agent
#
# The host service binds loopback only. Docker Desktop routes
# host.docker.internal to the host, so the container reaches them without the
# ports being exposed to the LAN.
#
# Why any of this is necessary: .devcontainer/ARCHITECTURE.md

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
generated_root="${repo_root}/.devcontainer/.generated"
container_codex_home="${generated_root}/codex"
container_claude_home="${generated_root}/claude"
container_opencode_home="${generated_root}/opencode"
host_codex_config="${HOME}/.codex/config.toml"
host_claude_config="${HOME}/.claude.json"
host_opencode_config="${HOME}/.config/opencode/opencode.json"
host_playwright_url="http://127.0.0.1:8931/mcp"
container_playwright_url="http://host.docker.internal:8931/mcp"

playwright_port="${PLAYWRIGHT_MCP_PORT:-8931}"
playwright_log="${PLAYWRIGHT_MCP_LOG:-${TMPDIR:-/tmp}/playwright-mcp-host.log}"

# Your installed Google Chrome, driven with the separate profile below rather
# than your day-to-day one. Not "chromium": that now resolves to
# chrome-for-testing, which would be another browser to download and keep
# updated for no gain here.
playwright_browser="${PLAYWRIGHT_MCP_BROWSER:-chrome}"

# Persistent profile, so sites you sign into by hand stay signed in.
playwright_profile="${PLAYWRIGHT_MCP_PROFILE:-${HOME}/.playwright-mcp-profile}"


# ═══════════════════════════════════════════════════════════════════════════
#  1. Container agent configs
#
#  ⚙️ PROJECT — the three agents below are the ones this setup uses. Drop the
#     block for any agent you do not run.
# ═══════════════════════════════════════════════════════════════════════════

mkdir -p \
  "${container_codex_home}" \
  "${container_claude_home}" \
  "${container_opencode_home}"

if ! command -v codex >/dev/null 2>&1; then
  echo "host-setup: Codex CLI is required to prepare the devcontainer config." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "host-setup: jq is required to prepare the devcontainer config." >&2
  exit 1
fi

# Every file is built here first and published only once it passes its checks,
# so a failed run leaves the last good config in place. This is also where
# CODEX_HOME points while the Codex CLI edits its config: it drops lock files
# and other state next to it, none of which belongs in .generated/.
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

# Publish a generated file by truncating the destination and writing into it --
# never by renaming a new file over it.
#
# devcontainer.json bind-mounts each of these files individually, and Docker
# binds a *file* mount to the inode it finds at container start. `perl -i`, the
# Codex CLI's own config writer, and any `mv` into place all replace the file
# rather than rewrite it, which silently detaches the mount: the container goes
# on serving the old inode's bytes until it is recreated, with nothing anywhere
# to explain why regenerating had no effect. Truncating keeps the inode, so a
# re-run reaches a container that is already up.
publish() {
  local src="$1" dst="$2"
  cat "${src}" > "${dst}"
  chmod 0600 "${dst}"
}

codex_work="${work}/codex"
mkdir -p "${codex_work}"
if [[ -f "${host_codex_config}" ]]; then
  cat "${host_codex_config}" > "${codex_work}/config.toml"
else
  : > "${codex_work}/config.toml"
fi

# The generated file overlays only config.toml; all other Codex data continues
# to come from the host ~/.codex bind mount. node_repl is host-only. Rewrite the
# Playwright endpoint so the container can drive visible host Chrome.
if CODEX_HOME="${codex_work}" codex mcp get node_repl >/dev/null 2>&1; then
  CODEX_HOME="${codex_work}" codex mcp remove node_repl >/dev/null
fi
perl -0pi -e \
  "s|\\Q${host_playwright_url}\\E|${container_playwright_url}|g" \
  "${codex_work}/config.toml"
if ! grep -Fq "url = \"${container_playwright_url}\"" \
  "${codex_work}/config.toml"; then
  echo "host-setup: host Codex config must define the direct Playwright MCP endpoint." >&2
  exit 1
fi
publish "${codex_work}/config.toml" "${container_codex_home}/config.toml"

# Claude Code stores user-scoped MCP configuration in ~/.claude.json, outside
# the shared ~/.claude directory. Copy the complete host file. If a user-scoped
# Playwright entry exists, keep it on the direct host endpoint too; this project
# normally supplies that entry through .mcp.json instead.
if [[ -f "${host_claude_config}" ]]; then
  jq --arg playwright_from "${host_playwright_url}" \
    --arg playwright_to "${container_playwright_url}" \
    'if .mcpServers.playwright?.url == $playwright_from then
         .mcpServers.playwright.url = $playwright_to
       else
         .
       end' \
    "${host_claude_config}" > "${work}/claude.json"
else
  printf '{}\n' > "${work}/claude.json"
fi
publish "${work}/claude.json" "${container_claude_home}/.claude.json"

# OpenCode Desktop connects to the server running inside the devcontainer, so
# that server needs its own view of the host's global config. Playwright is
# rewritten here, in the global config, rather than left to a
# per-project .opencode/opencode.json, so a new project inherits it the way
# Codex and Claude Code already do. The host entry is a `local` one that spawns
# npx: left as-is the container would start its own headless browser, which is
# the exact outcome the host Playwright MCP server exists to prevent. A `local`
# entry has no url to patch, so it is replaced outright by a remote one.
if [[ ! -f "${host_opencode_config}" ]]; then
  echo "host-setup: host OpenCode config is required to prepare the devcontainer config." >&2
  exit 1
fi
jq --arg playwright_to "${container_playwright_url}" \
  'if .mcp.playwright == null then
       error("Host OpenCode config must define an mcp.playwright entry")
     else
       .mcp.playwright = {
         type: "remote",
         url: $playwright_to,
         enabled: (.mcp.playwright.enabled // true)
       }
     end' \
  "${host_opencode_config}" > "${work}/opencode.json"
publish "${work}/opencode.json" "${container_opencode_home}/opencode.json"

echo "host-setup: agent configs generated in .devcontainer/.generated/"


# ═══════════════════════════════════════════════════════════════════════════
#  2. Playwright MCP on the host
#
#  Clients reach it directly -- host Codex through ~/.codex/config.toml,
#  everything inside the container through the configs generated above, plus
#  .mcp.json for Claude Code.
# ═══════════════════════════════════════════════════════════════════════════

if lsof -nP -iTCP:"${playwright_port}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "host-setup: playwright-mcp already listening on ${playwright_port}"
else
  mkdir -p "${playwright_profile}"
  # initializeCommand must not block the container coming up, so this detaches.
  # The subshell is what detaches it from this script's job control: macOS has
  # no setsid, and nohup alone would leave it in the caller's process group.
  #
  # --host 127.0.0.1 binds IPv4 loopback explicitly. The default resolves to
  # [::1] only, and Docker Desktop forwards host.docker.internal to the host's
  # IPv4 loopback, so an IPv6-only listener is refused from inside the container.
  #
  # --allowed-hosts is required because the container sends
  # "Host: host.docker.internal:<port>", which the server rejects otherwise.
  (
    nohup npx -y @playwright/mcp@latest \
      --host 127.0.0.1 \
      --port "${playwright_port}" \
      --browser "${playwright_browser}" \
      --user-data-dir "${playwright_profile}" \
      --allowed-hosts "host.docker.internal:${playwright_port},localhost:${playwright_port},127.0.0.1:${playwright_port}" \
      >>"${playwright_log}" 2>&1 </dev/null &
  )
  echo "host-setup: playwright-mcp starting on ${playwright_port} (log: ${playwright_log})"
fi
