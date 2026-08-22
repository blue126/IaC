#!/usr/bin/env bash
# Run Playwright MCP on the host, so agents inside the dev container drive a
# browser you can actually see.
#
#   host (macOS)          dev container
#   ------------          -------------
#   visible browser  <--  playwright-mcp (HTTP :8931)  <--  agent
#
# The server binds to loopback only. Docker Desktop still routes
# host.docker.internal to the host's loopback, so the container reaches it
# without the port being exposed to the LAN. devcontainer.json maps that name
# with --add-host, because the container's --dns bypasses Docker's resolver.
#
# Clients are already configured to use http://host.docker.internal:8931/mcp:
#   .mcp.json                  Claude Code
#   .opencode/opencode.json    opencode
#
# Run this on the host, not in the container. Leave it running.

set -euo pipefail

port="${PLAYWRIGHT_MCP_PORT:-8931}"
log="${PLAYWRIGHT_MCP_LOG:-${TMPDIR:-/tmp}/playwright-mcp-host.log}"

# --detach: start in the background and return, for devcontainer.json's
# initializeCommand, which runs on the host and must not block the container
# coming up. A no-op when the port is already served.
if [[ "${1:-}" == "--detach" ]]; then
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "playwright-mcp: already listening on ${port}"
    exit 0
  fi
  # The subshell detaches it from this script's job control; macOS has no
  # setsid, and nohup alone would still leave it in the caller's process group.
  ( nohup "${BASH_SOURCE[0]}" >>"${log}" 2>&1 </dev/null & )
  echo "playwright-mcp: starting on ${port} (log: ${log})"
  exit 0
fi

# Your installed Google Chrome, driven with the separate profile below rather
# than your day-to-day one. Not "chromium": that now resolves to
# chrome-for-testing, which would be another browser to download and keep
# updated for no gain here.
browser="${PLAYWRIGHT_MCP_BROWSER:-chrome}"

# Persistent profile, so sites you sign into by hand stay signed in.
profile="${PLAYWRIGHT_MCP_PROFILE:-${HOME}/.playwright-mcp-profile}"

mkdir -p "${profile}"

# The container sends "Host: host.docker.internal:<port>", which the server
# rejects unless that name is allowed.

# Bind IPv4 loopback explicitly. The default resolves to [::1] only, and Docker
# Desktop forwards host.docker.internal to the host's IPv4 loopback, so an
# IPv6-only listener is refused from inside the container.
exec npx -y @playwright/mcp@latest \
  --host 127.0.0.1 \
  --port "${port}" \
  --browser "${browser}" \
  --user-data-dir "${profile}" \
  --allowed-hosts "host.docker.internal:${port},localhost:${port},127.0.0.1:${port}"
