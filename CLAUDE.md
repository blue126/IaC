# Project Workflow Rules

## Environment

- **Never install packages without explicit permission.** No `apt-get install`, `pip install`, `npm install -g`, or any other change to the devcontainer/system, even when it looks like the obvious way to unblock a task. Ask first, and offer the alternative that needs no install.


## Ansible

- **Working directory**: Always `cd /workspaces/IaC/ansible` before running `ansible-playbook`, `ansible-inventory`, or other Ansible commands. Use relative paths (e.g., `playbooks/deploy-llm-server.yml`) instead of absolute paths.
- **Inventory sync**: If Ansible reports "no hosts matched" or inventory parse failures, run `/workspaces/IaC/scripts/refresh-terraform-state.sh` first to pull Terraform state from HCP Terraform. Inventory is managed by Terraform dynamic inventory plugins (`cloud.terraform.terraform_provider`).
