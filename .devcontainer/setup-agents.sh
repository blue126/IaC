#!/usr/bin/env bash
#
# Everything about the coding agents, INSIDE THE CONTAINER. Two modes, because
# the work splits across two lifecycle hooks:
#
#   --install   postCreateCommand, once per container. Installs the agents,
#               repairs bind-mount ownership, and joins the Claude Code history.
#   --serve     postStartCommand, every start. Keeps opencode up to date and
#               runs the server the desktop app on the host attaches to.
#
# The matching host-side work -- deriving each agent's container config from
# yours -- lives in host-setup.sh, because it has to run before this container
# exists. Nothing here touches the host.
#
# Why any of this is necessary: .devcontainer/ARCHITECTURE.md

set -euo pipefail

mode="${1:-}"
if [[ "${mode}" != "--install" && "${mode}" != "--serve" ]]; then
  echo "usage: ${0##*/} --install | --serve" >&2
  exit 2
fi


# ═══════════════════════════════════════════════════════════════════════════
#  --install : postCreateCommand
# ═══════════════════════════════════════════════════════════════════════════

if [[ "${mode}" == "--install" ]]; then

  # Every agent is installed from its vendor's own script, so each is whatever
  # that vendor currently ships rather than whatever a feature author repackaged.
  #
  #   codex     -> ~/.local/bin      (already first on PATH)
  #   claude    -> ~/.local/bin
  #   opencode  -> ~/.opencode/bin   (--serve puts this on PATH)
  #
  # All three land under $HOME, which is the home volume, so they survive
  # container recreation. That is also why they cannot move to the Dockerfile:
  # the home volume is not mounted during the image build.
  #
  # Deliberately unpinned. These ship several times a week and update themselves
  # at runtime, so a pin here would buy a reproducibility the first launch
  # discards.
  #
  # Claude Code's installer stages its download in ~/.claude/downloads, which is
  # bind-mounted from the host -- the Linux build briefly lands in the macOS
  # Claude directory. The installer removes it once the install succeeds.
  #
  # ⚙️ PROJECT — drop the line for any agent you do not use.
  curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh
  curl -fsSL https://claude.ai/install.sh | bash
  curl -fsSL https://opencode.ai/install | bash

  # Preserve ownership of host bind mounts. Every path listed here comes from
  # the host, and Docker Desktop's uid mapping is not consistent about them:
  # ~/.ssh and ~/.codex/config.toml currently arrive as root while ~/.claude
  # does not. chown on a bind mount can fail outright, and `set -e` would abort.
  #
  # ⚠️ Keep this list in step with the `mounts` array in devcontainer.json.
  sudo find /home/vscode -xdev \
    \( -path /home/vscode/.ssh -o -path /home/vscode/.claude \
       -o -path /home/vscode/.claude.json -o -path /home/vscode/.codex \
       -o -path /home/vscode/.config/opencode/opencode.json \) -prune \
    -o ! -user vscode -exec chown vscode:vscode {} +

  # Claude Code derives its project-history directory name from the workspace
  # path, so host and container sessions would otherwise land in two separate
  # places. Point the container's directory at the host's.
  if [[ -n "${HOST_WORKSPACE_FOLDER:-}" ]]; then
    # postCreateCommand runs with the workspace folder as its working directory,
    # so derive this instead of hardcoding one project's container path.
    host_key="${HOST_WORKSPACE_FOLDER//\//-}"
    container_key="${PWD//\//-}"
    host_project_dir="${HOME}/.claude/projects/${host_key}"
    container_project_dir="${HOME}/.claude/projects/${container_key}"

    if [[ "${host_key}" != "${container_key}" ]]; then
      mkdir -p "${host_project_dir}"

      if [[ -d "${container_project_dir}" && ! -L "${container_project_dir}" ]]; then
        cp -rn "${container_project_dir}/." "${host_project_dir}/"
        rm -rf "${container_project_dir}"
      fi

      ln -sfn "${host_project_dir}" "${container_project_dir}"
    fi
  fi

  echo "setup-agents: agents installed"
  exit 0
fi


# ═══════════════════════════════════════════════════════════════════════════
#  --serve : postStartCommand
#
#  Run the opencode server inside the container, so the desktop app on the host
#  can attach to it. The agent, the repo and the toolchain all stay here; only
#  the UI runs on the Mac.
#
#    host (macOS)             dev container
#    ------------             -------------
#    opencode desktop app --> opencode serve :4096 --> terraform / ansible / repo
#
#  devcontainer.json publishes this to 127.0.0.1:4096 on the host, so it is not
#  reachable from the LAN. Point the desktop app at http://127.0.0.1:4096
#
#  Safe to run by hand -- it is a no-op when the server is already up. Note that
#  `docker start` does NOT run postStartCommand, so after starting the container
#  that way, run this yourself.
# ═══════════════════════════════════════════════════════════════════════════

# The server inherits this PATH and hands it to every command the agent runs, so
# it has to be right regardless of how this script was invoked. A lifecycle hook
# gets the profile-probed PATH, but a plain `docker exec` gets the bare container
# one — and then the agent cannot find ansible, which lives in ~/.local/bin.
# Declare both user bin directories rather than depending on the caller.
for d in "${HOME}/.local/bin" "${HOME}/.opencode/bin"; do
  case ":${PATH}:" in
    *":${d}:"*) ;;
    *) PATH="${d}:${PATH}" ;;
  esac
done
export PATH

port="${OPENCODE_SERVE_PORT:-4096}"

# Lifecycle hooks run with the workspace folder as the working directory, so
# derive this rather than hardcoding one project's path.
workdir="${OPENCODE_SERVE_DIR:-${PWD}}"

log="${HOME}/.local/share/opencode/serve.log"

# Bind every interface inside the container. Docker's port publishing cannot
# reach a listener sitting on the container's own loopback, and --hostname
# defaults to 127.0.0.1.
bind_host="0.0.0.0"

if pgrep -f "opencode serve" >/dev/null 2>&1; then
  echo "setup-agents: opencode serve already running"
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
  echo "setup-agents: refreshed opencode credentials from ${host_auth}"
else
  echo "setup-agents: ${host_auth} not readable; server will have no providers" >&2
fi

# Keep the server in step with the desktop app, which updates itself on the host.
# --install runs this same installer, but only when the container is created;
# running it again here is what stops the server drifting behind a client that
# updated in the meantime. The installer's target, $HOME/.opencode/bin, sits on
# the home volume so it survives rebuilds, and the installer exits 0 without
# doing anything when the latest is already there -- a normal start costs one
# version check.
installer="$(mktemp)"
if curl -fsSL --max-time 20 https://opencode.ai/install -o "${installer}" 2>/dev/null; then
  # Let it put its bin dir on PATH for interactive shells; it checks first, so
  # the line lands in .bashrc once rather than on every start.
  bash "${installer}" 2>&1 | sed 's/^/setup-agents:   /' \
    || echo "setup-agents: opencode update failed, using the installed build" >&2
else
  echo "setup-agents: opencode installer unreachable, using the installed build" >&2
fi
rm -f "${installer}"

# Resolve it explicitly rather than trusting PATH: the installer's PATH line
# goes into .bashrc, which a non-interactive shell like this one does not read.
opencode_bin="${HOME}/.opencode/bin/opencode"
if [[ ! -x "${opencode_bin}" ]] && ! opencode_bin="$(command -v opencode)"; then
  echo "setup-agents: opencode is not installed and could not be fetched" >&2
  exit 1
fi
echo "setup-agents: using ${opencode_bin} ($("${opencode_bin}" --version 2>/dev/null | head -1))"

# Enable OpenCode's built-in Exa web search for non-OpenCode providers.
export OPENCODE_ENABLE_EXA="${OPENCODE_ENABLE_EXA:-1}"

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
# ⚠️ 带上凭据。设了 OPENCODE_SERVER_PASSWORD 之后服务端会对所有端点要求 basic
#    auth，不带凭据的探测拿到 401，curl -f 判定失败 —— 于是这个"防止服务死了还
#    报成功"的检查，会在服务活得好好的时候报失败。
auth_args=()
if [[ -n "${OPENCODE_SERVER_PASSWORD:-}" ]]; then
  auth_args=(-u "${OPENCODE_SERVER_USERNAME:-opencode}:${OPENCODE_SERVER_PASSWORD}")
fi

for _ in $(seq 1 30); do
  if curl -sf -o /dev/null --max-time 1 "${auth_args[@]}" "http://127.0.0.1:${port}/doc"; then
    echo "setup-agents: opencode serve listening on ${bind_host}:${port} (log: ${log})"
    exit 0
  fi
  sleep 0.5
done

echo "setup-agents: opencode serve did not answer on ${port} within 15s. Last log lines:" >&2
tail -n 5 "${log}" >&2 || true
exit 1
