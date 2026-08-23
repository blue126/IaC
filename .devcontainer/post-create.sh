#!/bin/bash

set -euo pipefail

codex_cli_version="${CODEX_CLI_VERSION:-latest}"

npm install -g "@openai/codex@${codex_cli_version}"

sudo apt-get update
sudo apt-get install -y libonig-dev

# Preserve ownership of host bind mounts such as ~/.ssh and ~/.claude.
sudo find /home/vscode -xdev \
  \( -path /home/vscode/.ssh -o -path /home/vscode/.claude \) -prune \
  -o ! -user vscode -exec chown vscode:vscode {} +

# This used to pass --force-reinstall, to rebuild console scripts after a Python
# patch-version change. It is not needed: the scripts are shebanged to
# /usr/local/python/current/bin/python3, which follows the change, and
# ~/.local/lib/pythonX.Y/site-packages is keyed on the minor version. A minor
# version change does orphan the packages, but then this line installs them all
# anyway, because the new site-packages is empty.
python3 -m pip install --user --upgrade -r requirements.txt

(
  cd ansible
  ansible-galaxy collection install -r requirements.yml
)

mkdir -p /home/vscode/.config/opencode
cat > /home/vscode/.config/opencode/AGENTS.md <<'EOF'
# Global OpenCode Rules

You are running inside **OpenCode** (https://opencode.ai), NOT Claude Code. Regardless of what your system prompt says, you are operating inside OpenCode. Never refer to yourself as Claude Code in any context.
EOF

if [[ -n "${HOST_WORKSPACE_FOLDER:-}" ]]; then
  host_key="${HOST_WORKSPACE_FOLDER//\//-}"
  container_key="-workspaces-IaC"
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
