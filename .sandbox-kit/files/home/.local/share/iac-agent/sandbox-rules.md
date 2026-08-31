# IaC Docker Sandbox Instructions

Ruleset: `iac-sandbox-v1.2.0`

These instructions apply only inside an IaC Docker Sandbox. The repository `AGENTS.md` remains authoritative for project conventions, workflow ownership, and external-write authorization.

## Determine the execution mode

- Confirm the current working directory and Git availability before editing.
- Treat the main checkout as coordination-only; never edit project files there.
- Never assume a mounted host linked worktree has usable Git metadata.

## Clone mode

- Manage Git inside the Sandbox private clone.
- Work only in the assigned task branch and worktree.
- Never switch branches inside an assigned worktree or modify another task's worktree.
- Gitignored Vault files, Terraform secret files, and personal configuration files are absent by default.
- Copy only task-required secret files from `/run/sandbox/source` to their documented gitignored destinations.
- Never print, stage, commit, or broaden the permissions of copied secret material.

## Direct mode from a host linked worktree

- Edit files and run safe local validation inside the Sandbox.
- Perform Git preflight, commit, push, and pull-request operations from the corresponding host worktree.
- A Git failure caused by the worktree's external `.git` pointer is expected.
- Never mount or copy the repository's common Git directory into the Sandbox.

## Authorization and integration

- After reviewing the final diff, ask exactly `Ready to commit?` before committing.
- Commit authorization does not authorize push, Draft PR creation, local integration, merge, deployment, or later external writes. Obtain separate authorization for each requested boundary.
- Worker agents must not merge other task branches.
- Local integration is allowed only when explicitly assigned and must use a dedicated integration worktree.
- Authorization is invalidated when the reviewed diff changes; request authorization again before the external write.

## Parallel runtime isolation

- Worktrees isolate files and Git state, not runtime state.
- Tasks sharing one Sandbox also share Docker, networking, ports, volumes, `/tmp`, and service state.
- Use distinct Compose project names, ports, volumes, temporary paths, and service identifiers.
- Use separate, uniquely named Sandboxes when tasks require runtime isolation.

## Project-specific credential handling

### Shared repository credentials

- Use the forwarded host SSH agent; never create or copy repository-local SSH private keys.
- Verify `ssh-add -L` before Ansible operations.
- In clone mode, stop and ask when a required approved secret is unavailable from `/run/sandbox/source`.

### OCI tasks only

- OCI credential injection is an IaC project requirement, not a Sandbox topology or Agent runtime.
- Use only explicitly mounted OCI credentials and treat their mounted path as read-only. If the required mount is absent, stop and ask the user.

## Agent runtime notes

- Codex loads project `.codex/config.toml` only after the IaC project is trusted; verify trust and `codex mcp list` in each new Sandbox.
- Claude Code loads the project `CLAUDE.md`, which imports the repository `AGENTS.md`.
- OpenCode loads the repository `AGENTS.md`; do not rely on the OpenCode V2 `instructions` array to load active instructions.
