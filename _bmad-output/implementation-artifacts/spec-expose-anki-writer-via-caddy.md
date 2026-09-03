---
title: 'Expose Anki Writer through reusable Caddy site configuration'
type: 'bugfix'
created: '2026-08-14'
status: 'in-review'
review_loop_iteration: 0
baseline_commit: '0d6ad67bc93bc19ff27d9643b4acb197f2a909bb'
context:
  - '{project-root}/docs/designs/ansible-role-architecture.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Browser card creation fails because OCI serves `anki-writer` on port 5051, while the OCI NSG intentionally exposes only HTTP/HTTPS. The existing generic Caddy role is coupled to the Proxmox Alpine/WebDAV deployment and cannot safely be run wholesale on the OCI Ubuntu host.

**Approach:** Add an OS-neutral Caddy task entry point for managing one reverse-proxy site on a host where Caddy is already installed. Use it from the OCI Anki playbook to publish `https://ankiwriter.willfan.me` to loopback port 5051 while preserving the Caddyfile owned by unified-proxy.

## Boundaries & Constraints

**Always:** Limit changes to OCI inventory, the `caddy` role, the `anki-api` role, and the OCI Anki playbook. Keep ports 5050/5051 closed in OCI NSG. Preserve the existing `proxy.willfan.me` site. Validate candidate Caddy configuration before reload. Manage the DNS A record `ankiwriter.willfan.me -> 159.13.46.201` through the requested Cloudflare plugin when connected. Use anonymous public access as explicitly accepted by the user.

**Ask First:** Any solution that requires replacing the installed Caddy package, restarting instead of reloading Caddy, changing OCI NSG rules, or modifying files outside the stated scope.

**Never:** Modify the `unified-proxy` role or playbook. Run the existing full `deploy-caddy.yml` against OCI. Expose `ldoce5-api` publicly. Store Cloudflare credentials or other plaintext secrets in the repository. Commit automatically.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Public health request | DNS resolves and Caddy is active | `GET https://ankiwriter.willfan.me/health` returns HTTP 200 from localhost:5051 | Verification fails without changing NSG |
| Existing proxy request | `proxy.willfan.me` is already configured | Existing site remains valid and reachable after reload | Candidate validation prevents invalid combined config deployment |
| Backend unavailable | anki-writer is stopped | Caddy returns upstream failure; existing proxy remains available | Verification reports failure without opening port 5051 |
| Future unified-proxy deploy | `/etc/caddy/Caddyfile` is replaced | Caddy's managed aggregate continues importing the replaced base file and the Anki site fragment | Caddy reload validates the aggregate before activation |

</frozen-after-approval>

## Code Map

- `ansible/roles/caddy/tasks/reverse-proxy.yml` -- OS-neutral entry point for a Caddy installation that already exists.
- `ansible/roles/caddy/templates/managed.Caddyfile.j2` -- aggregate importing the externally owned base Caddyfile and managed site fragments.
- `ansible/roles/caddy/templates/reverse-proxy.Caddyfile.j2` -- one HTTPS reverse-proxy site definition.
- `ansible/roles/caddy/templates/caddy.service.override.conf.j2` -- makes service start/reload consume the aggregate without editing the base Caddyfile.
- `ansible/roles/caddy/handlers/main.yml` -- daemon-reload and validated Caddy reload behavior.
- `ansible/roles/caddy/defaults/main.yml` -- paths and required reverse-proxy inputs.
- `ansible/inventory/host_vars/oracle-cloud-ubuntu2404.yml` -- `ankiwriter.willfan.me` site variables.
- `ansible/playbooks/deploy-anki-oci.yml` -- configuration-only Caddy play and HTTPS verification.
- `ansible/roles/anki-api/templates/docker-compose.yml.j2` -- bind published API ports to loopback while preserving container-to-container access.

## Tasks & Acceptance

**Execution:**
- [x] `ansible/roles/caddy/{defaults,tasks,templates,handlers}` -- add an idempotent, existing-install reverse-proxy entry point that validates the aggregate before reload.
- [x] `ansible/inventory/host_vars/oracle-cloud-ubuntu2404.yml` -- declare the Anki Writer hostname and loopback upstream.
- [x] `ansible/playbooks/deploy-anki-oci.yml` -- call only the Caddy reverse-proxy entry point under `config` tags and assert public HTTPS health under `verify` tags.
- [x] `ansible/roles/anki-api/templates/docker-compose.yml.j2` -- restrict host publication of 5050/5051 to loopback.
- [x] Cloudflare DNS -- create or update the DNS-only A record for `ankiwriter.willfan.me` after the plugin is installed and connected.

**Acceptance Criteria:**
- Given the existing OCI Caddy and Anki containers, when the config-only play runs, then Caddy loads both `proxy.willfan.me` and `ankiwriter.willfan.me` without changing unified-proxy files.
- Given a future unified-proxy Caddyfile replacement, when Caddy reloads, then both the replaced base site and the Anki site fragment remain loaded.
- Given no OCI ingress rule for 5050/5051, when a browser calls the HTTPS hostname, then `/health` and `/add-word` route through port 443 while direct public port access still times out.
- Given a second config-only run, when no inputs changed, then Ansible reports no configuration changes.

## Spec Change Log

## Design Notes

The existing base `/etc/caddy/Caddyfile` remains owned by unified-proxy. A separate aggregate imports that file plus `/etc/caddy/conf.d/*.caddy`; a systemd drop-in points both `ExecStart` and `ExecReload` at the aggregate. This avoids file ownership overlap while allowing the existing unified-proxy handler to reload the complete configuration after future base-file updates.

Anonymous access is a user-approved risk. The public route exposes only `anki-writer`; `ldoce5-api` stays on the Docker network and loopback host binding.

## Verification

**Commands:**
- `cd ansible && ANSIBLE_LOCAL_TEMP=/tmp/ansible-anki-caddy ansible-playbook -i inventory/oci/hosts.yml -i inventory/groups.yml playbooks/deploy-anki-oci.yml --syntax-check` -- expected: syntax succeeds.
- `cd ansible && ANSIBLE_LOCAL_TEMP=/tmp/ansible-anki-caddy ansible-playbook -i inventory/oci/hosts.yml -i inventory/groups.yml playbooks/deploy-anki-oci.yml --limit oracle-cloud-ubuntu2404 --check --diff --tags config` -- expected: only scoped Caddy/Anki configuration changes are proposed.
- `sudo caddy validate --config /etc/caddy/managed.Caddyfile --adapter caddyfile` -- expected: valid configuration on OCI.
- `curl -fsS https://ankiwriter.willfan.me/health` -- expected: HTTP 200 JSON health response.
- `curl --max-time 10 http://159.13.46.201:5051/health` -- expected: timeout, proving the direct port remains closed.
