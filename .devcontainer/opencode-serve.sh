#!/usr/bin/env bash
# Run the opencode server inside the dev container, so the desktop app on the
# host can attach to it. The agent, the repo and the toolchain all stay in the
# container; only the UI runs on the Mac.
#
#   host (macOS)             dev container
#   ------------             -------------
#   opencode desktop app --> opencode serve :4096 --> terraform / ansible / repo
#
# devcontainer.json publishes this to 127.0.0.1:4096 on the host, so it is not
# reachable from the LAN. Point the desktop app at http://127.0.0.1:4096
#
# Started automatically by postStartCommand. Safe to run by hand — it is a no-op
# when the server is already up. Note that `docker start` does NOT run
# postStartCommand, so after starting the container that way, run this yourself.

set -euo pipefail

port="${OPENCODE_SERVE_PORT:-4096}"
workdir="${OPENCODE_SERVE_DIR:-/workspaces/IaC}"
log="${HOME}/.local/share/opencode/serve.log"

# Bind every interface inside the container. Docker's port publishing cannot
# reach a listener sitting on the container's own loopback, and --hostname
# defaults to 127.0.0.1.
bind_host="0.0.0.0"

if pgrep -f "opencode serve" >/dev/null 2>&1; then
  echo "opencode serve: already running"
  exit 0
fi

# Passed through from the host in containerEnv, where an unset variable arrives
# as an empty string. Left set, that would enable basic auth with a blank
# password, which is worse than leaving it off.
if [[ -z "${OPENCODE_SERVER_PASSWORD:-}" ]]; then
  unset OPENCODE_SERVER_PASSWORD
fi

# devcontainer.json bind-mounts the host's opencode credentials, but nothing
# consumed them, so the server came up with no providers configured. Copy rather
# than symlink: opencode rewrites this file when a token refreshes, and a rename
# through a single-file bind mount detaches the mount. The copy means refreshed
# tokens stay in the container and do not flow back to the host.
host_auth="/mnt/opencode-auth.json"
auth="${HOME}/.local/share/opencode/auth.json"
if [[ -r "${host_auth}" ]]; then
  mkdir -p "$(dirname "${auth}")"
  install -m 600 "${host_auth}" "${auth}"
  echo "opencode serve: refreshed credentials from ${host_auth}"
else
  echo "opencode serve: ${host_auth} not readable; server will have no providers" >&2
fi

# WORKAROUND — make the host's path for this repo resolve in here too.
#
# The opencode desktop app runs on the host and its project picker browses the
# HOST filesystem, but the server runs in this container. Picking the project
# hands the server a path like /Users/<you>/Projects/IaC, which it opens
# literally; with no such path here, every prompt dies in FileSystem.realPath
# and the app shows no reply at all — no error, nothing. See
# anomalyco/opencode#44150, and #40136 / #5380 for the same class of bug.
#
# Known limitation: realPath resolves this symlink back to ${workdir}, so
# anything the server reports back to the app carries the container's path,
# which means nothing on the host. Reads work; a round trip may not. Mounting
# the checkout a second time at the host's own path avoids that, at the cost of
# a second mount in devcontainer.json.
#
# HOST_WORKSPACE_FOLDER comes from devcontainer.json's containerEnv.
if [[ -n "${HOST_WORKSPACE_FOLDER:-}" && ! -e "${HOST_WORKSPACE_FOLDER}" ]]; then
  sudo mkdir -p "$(dirname "${HOST_WORKSPACE_FOLDER}")"
  sudo ln -sfn "${workdir}" "${HOST_WORKSPACE_FOLDER}"
  echo "opencode serve: mapped ${HOST_WORKSPACE_FOLDER} -> ${workdir}"
fi

# Keep the server in step with the desktop app, which updates itself on the host.
# Installing here rather than through the devcontainer feature means the version
# is not frozen by the image layer cache, and the installer's target,
# $HOME/.opencode/bin, sits on the iac-home volume so it survives rebuilds.
# The installer exits 0 without doing anything when the latest is already there,
# so a normal start costs one version check.
installer="$(mktemp)"
if curl -fsSL --max-time 20 https://opencode.ai/install -o "${installer}" 2>/dev/null; then
  # Let it put its bin dir on PATH for interactive shells; it checks first, so
  # the line lands in .bashrc once rather than on every start.
  bash "${installer}" 2>&1 | sed 's/^/opencode serve:   /' \
    || echo "opencode serve: update failed, using the installed build" >&2
else
  echo "opencode serve: installer unreachable, using the installed build" >&2
fi
rm -f "${installer}"

# Resolve it explicitly rather than trusting PATH: the installer's PATH line
# goes into .bashrc, which a non-interactive shell like this one does not read.
opencode_bin="${HOME}/.opencode/bin/opencode"
if [[ ! -x "${opencode_bin}" ]] && ! opencode_bin="$(command -v opencode)"; then
  echo "opencode serve: opencode is not installed and could not be fetched" >&2
  exit 1
fi
echo "opencode serve: using ${opencode_bin} ($("${opencode_bin}" --version 2>/dev/null | head -1))"

args=(serve --hostname "${bind_host}" --port "${port}")

# Set OPENCODE_SERVE_CORS to a space-separated list if the desktop app's origin
# turns out to need allowing.
if [[ -n "${OPENCODE_SERVE_CORS:-}" ]]; then
  for origin in ${OPENCODE_SERVE_CORS}; do
    args+=(--cors "${origin}")
  done
fi

mkdir -p "$(dirname "${log}")"
cd "${workdir}"

# setsid, not just nohup. When this runs as postStartCommand, the devcontainer
# tooling tears down the lifecycle exec's process group on the way out, which
# kills a merely nohup'd child — it survives SIGHUP but not a group signal. A
# new session puts the server out of reach.
setsid nohup "${opencode_bin}" "${args[@]}" >>"${log}" 2>&1 </dev/null &
disown 2>/dev/null || true

# Launching it says nothing about whether it stayed up, and this has failed
# intermittently: the process is forked, opens the log, and dies before writing
# a line, while this script happily reports success. That reads as a working
# setup right up until the client says the server is down. Wait for the port to
# actually answer, and fail loudly with the log if it never does.
for _ in $(seq 1 30); do
  if curl -sf -o /dev/null --max-time 1 "http://127.0.0.1:${port}/doc"; then
    echo "opencode serve: listening on ${bind_host}:${port} (log: ${log})"
    exit 0
  fi
  sleep 0.5
done

echo "opencode serve: did not answer on ${port} within 15s. Last log lines:" >&2
tail -n 5 "${log}" >&2 || true
exit 1
