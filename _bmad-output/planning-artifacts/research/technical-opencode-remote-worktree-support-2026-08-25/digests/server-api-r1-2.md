# Server API and plugin digest

## Findings

- Claim: Current upstream source defines native experimental workspace and worktree HTTP routes and an internal WorktreeAdapter.
  - Source: https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/server/routes/instance/httpapi/groups/workspace.ts
  - Publisher: anomalyco/opencode
  - Published: current dev branch, date not stated on blob
  - Accessed: 2026-08-25
  - Confidence: high
  - Class: version/compatibility
- Claim: The worktree routes are normal server HTTP endpoints, so operations execute on the `opencode serve` host and are not protocol-level local-only operations.
  - Source: https://github.com/anomalyco/opencode/commit/a36913022609ec90a26037fa3767cdb60eb49597
  - Publisher: anomalyco/opencode
  - Published: 2026-04-25
  - Accessed: 2026-08-25
  - Confidence: high
  - Class: version/compatibility
- Claim: The documented plugin API exposes hooks, events, custom tools, and limited TUI actions, but no supported Desktop component, menu, route, or DOM injection API.
  - Source: https://opencode.ai/docs/plugins/
  - Publisher: OpenCode
  - Published: not stated
  - Accessed: 2026-08-25
  - Confidence: high for documented surface; medium for absence of private APIs
  - Class: version/compatibility
- Claim: No official stable CLI/TUI worktree management workflow was found; a July 2026 feature request asks for a `--worktree` CLI flag.
  - Source: https://github.com/anomalyco/opencode/issues/35471
  - Publisher: anomalyco/opencode issue tracker
  - Published: 2026-07-05
  - Accessed: 2026-08-25
  - Confidence: medium
  - Class: version/compatibility

## Gaps

- The exact routes present in released OpenCode 1.18.21 were not yet compared with upstream `dev`.
- The complete adapter set was not established.
- Experimental endpoints may change without compatibility guarantees.
