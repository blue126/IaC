# Learning Note: Cloudflare Tunnel Ansible Role Code Review

**Date:** 2026-02-04
**Topic:** Ansible Role Design & Code Review Patterns
**Context:** Implementing `cloudflared` role for Jenkins Webhook exposure

## 1. Architectural Decision: Separate Role

**Decision:** Created a dedicated `cloudflared` role instead of adding tasks to the `jenkins` role.
**Reasoning:**
- **Separation of Concerns:** `cloudflared` is network infrastructure, Jenkins is application logic.
- **Reusability:** The tunnel role can be reused for other services (e.g., exposing a temporary demo app or another internal tool) without dragging in Jenkins dependencies.
- **Lifecycle Management:** Tunnel updates (cloudflared binary) and Jenkins updates often happen on different schedules.

## 2. Key Code Review Findings & Fixes

### A. Idempotency & Config Conflicts (High Severity)
**Issue:** `cloudflared service install` creates a systemd service that might copy an existing `~/.cloudflared/config.yml` to `/etc/cloudflared/config.yml`. If we deploy our template *before* installing the service, the service install command might overwrite our managed config with a stale one from the user's home directory.
**Fix:** Reordered tasks:
1. `cloudflared service install` (establish the service)
2. Deploy config template (ensure desired state, overwriting anything the install step did)
3. Start service

### B. Verification Play Patterns (Medium Severity)
**Issue:** Using `ignore_errors: yes` in a verify play without a subsequent `assert` defeats the purpose of verification. The play would pass even if the tunnel check failed.
**Fix:**
```yaml
- name: Verify tunnel
  command: ...
  register: result
  failed_when: false  # Don't crash ansible, just capture result

- name: Assert success
  assert:
    that: result.rc == 0
    fail_msg: "Tunnel check failed: {{ result.stderr }}"
```

### C. Variable Scoping in Independent Plays (Medium Severity)
**Issue:** The verify play is a separate play in the same playbook (`hosts: jenkins`). It does not automatically load role defaults from the deploy play's `roles:` section. Hardcoding variables in `vars:` led to duplication (DRY violation).
**Fix:** Used `include_vars` in `pre_tasks` to explicitly load the role's defaults, ensuring the verify play uses the exact same configuration sources as the deploy play.

## 3. Accepted Risks
- **GPG Key Checksum:** Decided not to enforce `checksum` on the Cloudflare GPG key download to match existing project patterns (Jenkins role) and avoid maintenance burden when keys rotate.
- **Config Permissions:** Config is `0600` (root only). Assumed `cloudflared` runs as root (standard in LXC/systemd), noted this assumption in comments.

## 4. Q&A Summary

**Q: Should we include the `common` role in the cloudflared playbook?**
A: Yes, for consistency and completeness, even if the target host (Jenkins) has likely already run it. It ensures the playbook is standalone-capable.

**Q: Why separate variables for URL vs Port in design doc vs implementation?**
A: Implementation used `service_url` (full URL) instead of `service_port`. This is better as it allows flexible upstreams (e.g., https://, non-localhost, subpaths) without code changes. Updated documentation to match.
