---
title: 'Add auditable Git worktree management / 添加可审计的 Git worktree 管理'
type: 'feature'
created: '2026-08-23'
status: 'draft'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 多个 OpenCode 会话共享同一 checkout 并切换分支，已造成会话间干扰；社区方案包含未校验二进制、自动提交、强制删除或工具拦截，不符合 vanilla、可调试和可回滚目标。 Shared sessions currently interfere through one checkout; existing tools add intrusive automation.

**Approach:** 在全局配置中增加无第三方依赖的薄插件，仅暴露 list/create/remove；仓库单独启用宿主机可见且已忽略的根目录。 Add three explicit tools with repository opt-in and no lifecycle hooks.

## Boundaries & Constraints

**Always:** 参数数组调用 Git；create/remove 触发 permission ask；分支固定为 `opencode/<slug>`、起点为 `HEAD`；路径固定为 `${HOST_WORKSPACE_FOLDER}/.opencode-worktrees/<slug>`；remove 仅接受已注册、非主/当前、非 locked、完全 clean 的目标，并保留分支。

**Ask First:** 修改 tracked 文件、删除分支、hydration、`--force`、路径映射无法证明、重启当前 OpenCode Server。

**Never:** 自动 commit/fetch/pull/push/prune；shell 字符串；event/workspace/tool/shell hooks；复制 `.worktreeinclude`、secret、认证或项目 `.opencode`；回退到容器 home；安装第三方 worktree 包、scheduler 或框架。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| List | Git repo | Return porcelain data, no mutation | Explain non-repo state |
| Create | Unused ASCII slug; enabled ignored root | Create `opencode/<slug>` from `HEAD` | Reject invalid/ref/path/symlink/root |
| Remove | Managed, clean, unlocked target | Non-force remove; preserve branch | Reject dirty/current/primary/unknown |
| Concurrent | Same slug calls | At most one Git action succeeds | Surface Git lock/conflict |

</frozen-after-approval>

## Code Map

- `/home/vscode/.config/opencode/plugins/worktree-tools.ts` -- global plugin; SDK provides directory/worktree/session/ask context.
- `/home/vscode/.config/opencode/opencode.jsonc` -- add only three tool permissions.
- `/home/vscode/.config/opencode/tests/worktree-tools.test.ts` -- tests outside auto-loaded `plugins/`.
- `/home/vscode/.config/opencode/HARNESS.md` -- capability and rollback record.
- `.git/info/exclude` -- local per-repository opt-in for `/.opencode-worktrees/`; never commit this setting.
- `.devcontainer/devcontainer.json:84-113` -- home volume, dual host bind and host path; read-only.
- `.devcontainer/opencode-serve.sh:19-34,94-111` -- server environment; read-only with user changes.
- `.worktreeinclude:1-31` -- Claude-only secret/runtime list; do not consume.
- `.gitignore:23-30` -- project `.opencode` and runtime files are ignored; do not modify.
- `AGENTS.md:98-121` and `CLAUDE.md:3-10` -- no automatic commits, incremental verification, container path and relative-Ansible constraints.

## Tasks & Acceptance

**Execution:**
- [ ] `/home/vscode/.config/opencode/plugins/worktree-tools.ts` -- implement stateless tools, strict validation, porcelain `-z` parsing and non-shell Git.
- [ ] `/home/vscode/.config/opencode/opencode.jsonc` and `.git/info/exclude` -- require confirmation for mutations and explicitly opt this repository into a host-visible ignored root without changing tracked files.
- [ ] `/home/vscode/.config/opencode/tests/worktree-tools.test.ts` -- test matrix in disposable repos, including symlink, untracked dirt and concurrency.
- [ ] `/home/vscode/.config/opencode/HARNESS.md` -- document surface, no hooks/state, missing runtime files and rollback.

**Acceptance Criteria:**
- Given the plugin is disabled or removed, when OpenCode starts, then upstream tools and existing Git worktrees continue to work unchanged.
- Given OpenCode loads the plugin, when tool IDs are inspected, then exactly three worktree tools are added and no lifecycle hook exists.
- Given an approved valid slug, when creation succeeds, then the main checkout branch remains unchanged and Desktop can address the returned host path.
- Given a managed worktree contains any modification, when removal is requested, then removal is refused without commit, force, branch deletion or data loss.
- Given a fresh worktree, when inspected, then no ignored secret/runtime file has been copied automatically.

## Design Notes

Global source avoids project `.opencode`; local opt-in prevents hidden paths in arbitrary repos. Git is the only state store: no SQLite, registry, daemon or cleanup hook. The root must be a real directory under the dual-mounted host workspace; symlinks are rejected.

## Verification

**Commands:**
- `bun test /home/vscode/.config/opencode/tests/worktree-tools.test.ts` -- all validation and disposable-repository integration cases pass.
- `opencode debug config` -- global config parses and reports the intended permission rules.
- `git worktree list --porcelain` -- main checkout is unchanged and only explicitly created worktrees appear.
- `git status --short --branch` -- no tracked project file was changed by plugin setup or smoke tests.

**Manual checks (if no CLI):**
- Restart OpenCode only after approval, inspect the three new tool descriptions, and open one disposable worktree from Desktop using the returned host path.
