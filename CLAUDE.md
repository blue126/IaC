# Project Workflow Rules

## Environment

- **Never install packages without explicit permission.** No `apt-get install`, `pip install`, `npm install -g`, or any other change to the devcontainer/system, even when it looks like the obvious way to unblock a task. Ask first, and offer the alternative that needs no install.


## Ansible

- **Working directory**: Always `cd ansible` from the repository root before running `ansible-playbook`, `ansible-inventory`, or other Ansible commands, and use relative paths (e.g. `playbooks/deploy-llm-server.yml`). Keep the path relative: in a worktree session an absolute `/workspaces/IaC/...` silently sends you back to the main checkout. Ansible finds `ansible.cfg` in the current directory, and resolves the relative paths inside it against that file's own directory, so the whole toolchain follows you into the worktree on its own.
- **Inventory sync**: If Ansible reports "no hosts matched" or inventory parse failures, run `./scripts/refresh-terraform-state.sh` from the repository root first to pull Terraform state from HCP Terraform. Inventory is managed by Terraform dynamic inventory plugins (`cloud.terraform.terraform_provider`).
