# Client and UI digest

## Findings

- Claim: OpenCode Desktop supports connecting to a user-configured server URL in addition to its local sidecar.
  - Source: https://opencode.ai/docs/troubleshooting/
  - Publisher: OpenCode
  - Published: not stated
  - Accessed: 2026-08-25
  - Confidence: high
  - Class: version/compatibility
- Claim: Official CLI documentation describes an experimental workspace feature flag, not a local-only protocol restriction.
  - Source: https://opencode.ai/docs/cli/
  - Publisher: OpenCode
  - Published: not stated
  - Accessed: 2026-08-25
  - Confidence: high
  - Class: version/compatibility
- Claim: A remote Desktop/Web client has been observed invoking server-side worktree creation, but event synchronization and session routing were defective in that report.
  - Source: https://github.com/anomalyco/opencode/issues/12759
  - Publisher: anomalyco/opencode issue tracker
  - Published: 2026-02-08
  - Accessed: 2026-08-25
  - Confidence: medium
  - Class: version/compatibility
- Claim: Full VS Code-style remote workspace support has been requested separately, and no official roadmap or ETA was found.
  - Source: https://github.com/anomalyco/opencode/issues/5608
  - Publisher: anomalyco/opencode issue tracker
  - Published: 2025-12-16
  - Accessed: 2026-08-25
  - Confidence: medium
  - Class: version/compatibility

## Gaps

- The current Beta artifact's exact remote-server UI behavior was not verified from release metadata.
- No maintainer statement was found declaring workspace UI local-only.
- It was not established whether all defects in issue 12759 are fixed in the current release.
