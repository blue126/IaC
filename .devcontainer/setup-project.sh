#!/usr/bin/env bash
#
# ⚙️ PROJECT — this is the file a new project rewrites. Everything else in
# .devcontainer/ is reusable plumbing; the project's own toolchain goes here.
#
# Runs in the container from postCreateCommand, once per container, with the
# workspace folder as the working directory.
#
# Installs into $HOME, which is the home volume, so a container rebuild does not
# have to fetch any of it again. Every step must be safe to repeat.

set -euo pipefail

# Python dependencies. Ansible and its collections' Python requirements live in
# requirements.txt, which pins an ansible-core ceiling for a reason -- read the
# comment at the top of that file before raising it.
#
# This used to pass --force-reinstall, to rebuild console scripts after a Python
# patch-version change. It is not needed: the scripts are shebanged to
# /usr/local/python/current/bin/python3, which follows the change, and
# ~/.local/lib/pythonX.Y/site-packages is keyed on the minor version. A minor
# version change does orphan the packages, but then this line installs them all
# anyway, because the new site-packages is empty.
python3 -m pip install --user --upgrade -r requirements.txt

# Ansible collections. ansible.cfg sets collections_path, which puts them in
# ansible/collections/ inside the repo rather than under $HOME -- which is why
# .worktreeinclude lists that directory: a worktree without it has no dynamic
# inventory. The subshell keeps the cd from leaking into anything after it.
(
  cd ansible
  ansible-galaxy collection install -r requirements.yml
)

echo "setup-project: project toolchain ready"
