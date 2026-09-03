# Verification digest

## Verified claims

- Claim: OpenCode 1.18.21 contains a supported Desktop form for adding arbitrary HTTP servers, including URL, username, and password, and the current settings UI exposes a Servers section.
  - Sources:
    - https://github.com/anomalyco/opencode/blob/v1.18.21/packages/app/src/components/dialog-select-server.tsx
    - https://github.com/anomalyco/opencode/blob/v1.18.21/packages/app/src/components/settings-v2/servers.tsx
    - https://opencode.ai/docs/troubleshooting/#fix-server-connection-issues
  - Publisher: OpenCode / anomalyco
  - Published: release source dated 2026-08-21; docs accessed 2026-08-25
  - Accessed: 2026-08-25
  - Confidence: high
  - Class: version/compatibility
- Claim: In 1.18.21, the new-session workspace selector is gated by a non-production channel and a Git project; its visibility condition does not test whether the server is local.
  - Source: https://github.com/anomalyco/opencode/blob/v1.18.21/packages/app/src/pages/new-session/new-session-workspace-controller.ts
  - Publisher: anomalyco/opencode
  - Published: release source dated 2026-08-21
  - Accessed: 2026-08-25
  - Confidence: high
  - Class: version/compatibility
- Claim: OpenCode 1.18.21 ships native experimental workspace create/list/remove/warp HTTP routes and a built-in Git WorktreeAdapter.
  - Sources:
    - https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/server/routes/instance/httpapi/groups/workspace.ts
    - https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/control-plane/adapters/worktree.ts
  - Publisher: anomalyco/opencode
  - Published: release source dated 2026-08-21
  - Accessed: 2026-08-25
  - Confidence: high
  - Class: version/compatibility
- Claim: Native workspace behavior is experimental and controlled by `OPENCODE_EXPERIMENTAL_WORKSPACES`; the 1.18.21 TUI exposes `/workspaces` and `/warp` when enabled.
  - Sources:
    - https://opencode.ai/docs/cli/#experimental
    - https://github.com/anomalyco/opencode/blob/v1.18.21/packages/tui/src/app.tsx
    - https://github.com/anomalyco/opencode/blob/v1.18.21/packages/tui/src/component/prompt/index.tsx
  - Publisher: OpenCode / anomalyco
  - Published: release source dated 2026-08-21; docs accessed 2026-08-25
  - Accessed: 2026-08-25
  - Confidence: high
  - Class: version/compatibility
- Claim: The official plugin surface can add hooks, events, tools, and limited TUI actions, but it provides no documented Desktop component or menu injection API.
  - Source: https://opencode.ai/docs/plugins/
  - Publisher: OpenCode
  - Published: not stated
  - Accessed: 2026-08-25
  - Confidence: high for the documented surface; medium for absence of private unsupported mechanisms
  - Class: version/compatibility

## Local read-only corroboration

- The running OpenCode 1.18.21 server returned the built-in `worktree` adapter from `GET /experimental/workspace/adapter` and accepted read-only workspace/worktree list requests. This corroborates the release source but is not used as the sole basis for the recommendation.

## Corrections to round 1

- The statement that there is no native TUI workflow was overturned: 1.18.21 contains hidden native `/workspaces` and `/warp` commands.
- Issue 12759 documents a real remote bug in 1.1.53, but the issue is closed and search metadata reports a later version working. It is evidence of experimental maturity risk, not evidence that current remote worktrees are impossible.
