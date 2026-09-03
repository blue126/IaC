# Semantic citation audit

## Corrections

- `/experimental/worktree` is defined in `packages/opencode/src/server/routes/instance/httpapi/groups/experimental.ts`, not the workspace route group.
- `WorktreeAdapter` is registered as the built-in `worktree` adapter in `packages/opencode/src/control-plane/adapters/index.ts`.
- `OPENCODE_EXPERIMENTAL_WORKSPACES` gates the intended workspace/session synchronization behavior and native TUI commands, but the experimental HTTP routes remain mounted. Avoid saying every route requires the flag.
- The public plugin guide documents hooks, tools, and basic TUI actions. OpenCode 1.18.21 additionally exports a rich TUI plugin API with route registration, JSX UI, dialogs, prompts, and slots. No documented Desktop UI injection API was found; phrase this as an absence from documented/exported surfaces, not proof that private hacks are impossible.
- Issue #5608 was automatically closed as not planned after inactivity. It is not evidence of a maintainer decision to reject remote development.

## Additional official sources

- https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/server/routes/instance/httpapi/groups/experimental.ts
- https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/control-plane/adapters/index.ts
- https://github.com/anomalyco/opencode/blob/v1.18.21/packages/plugin/src/tui.ts
