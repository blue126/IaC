# MCP Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create VM 109 on `pve0`, install Docker and a locally managed Cloudflared connector, and protect `https://mcp.willfan.me/mcp` with a shared Cloudflare Access Service Token and an explicit cache bypass rule.

**Architecture:** Terraform provisions the Ubuntu VM and exports it through the Terraform Ansible inventory provider. A generic Cloudflared role installs the package on every consumer and configures a locally managed Tunnel only when inventory enables it. Cloudflare owns the DNS, Access Application, Service Auth policy, Service Token, and cache rule; Ansible Vault is the only persistent store for Tunnel and Access secrets.

**Tech Stack:** Terraform 1.x, `bpg/proxmox` 0.70.0, Ansible Core 2.20, Docker Engine/Compose, Cloudflared, Cloudflare Tunnel/Access/Rulesets APIs.

**Spec:** `docs/superpowers/specs/2026-08-28-mcp-gateway-design.md`

## Global Constraints

- VM: `mcp-gateway`, VMID `109`, `pve0`, `192.168.1.109/24`, 2 vCPU, 4096 MB RAM, 32 GB disk, Ubuntu 24.04 template.
- Ansible inventory membership is only `pve_vms`; do not add an `mcp_gateway` group.
- Public endpoint is exactly `https://mcp.willfan.me/mcp`; origin base is `http://127.0.0.1:3000`, so the effective origin URL is `http://127.0.0.1:3000/mcp`.
- Tunnel is independently named `mcp-gateway` with `config_src: local`; do not reuse Jenkins or n8n Tunnels.
- Access uses one shared enabled Service Token named `mcp-agents` with duration `8760h`.
- Access Application protects `mcp.willfan.me/mcp` with a Service Auth policy; cache bypass matches the same host and exact path.
- All secrets remain in `ansible/inventory/group_vars/all/vault.yml`; never print TunnelSecret or Access Client Secret.
- The MCP application itself is out of scope. A valid authenticated request may end at origin `502` until something listens on port 3000.
- Configuration-file TDD exception was explicitly approved. Use native Terraform/Ansible validators and API readback instead of introducing a test framework.
- Do not run `git commit` without explicit user authorization. At each suggested commit checkpoint, ask exactly: `Ready to commit?`
- Do not run Terraform apply until the saved plan proves the approved shape: create VM 109, update the existing partial `ansible_host.mcp_gateway` in place from `192.168.1.108` to `192.168.1.109`, and perform zero replacements or deletions.
- Do not silently overwrite conflicting Cloudflare resources. Stop and report the existing object and conflict.

## File Structure

| Path | Responsibility |
|---|---|
| `terraform/proxmox/mcp-gateway.tf` | VM 109 and Terraform-backed Ansible host |
| `ansible/roles/cloudflared/defaults/main.yml` | Generic install/tunnel defaults |
| `ansible/roles/cloudflared/tasks/main.yml` | Package installation, optional credentials/config/service lifecycle |
| `ansible/roles/cloudflared/templates/config.yml.j2` | Generic ingress list plus 404 catch-all |
| `ansible/inventory/host_vars/jenkins.yml` | Jenkins-only Tunnel routing configuration |
| `ansible/inventory/host_vars/mcp-gateway.yml` | VM metadata and MCP Tunnel routing configuration |
| `ansible/playbooks/deploy-cloudflared.yml` | Jenkins Tunnel deployment and verification compatibility |
| `ansible/playbooks/deploy-mcp-gateway.yml` | MCP VM Docker/Cloudflared deployment and verification |
| `ansible/inventory/group_vars/all/vault.yml` | Encrypted Tunnel credentials and Access Service Token credentials |
| `docs/designs/ansible-role-architecture.md` | Generic Cloudflared role contract |
| `docs/designs/ansible-vault-architecture.md` | New MCP secret ownership and flow |
| `docs/learningnotes/2026-08-28-mcp-gateway-deployment.md` | Final resource IDs, validation evidence, and operational Q&A |

---

### Task 1: Finish and validate the generic Cloudflared role

**Files:**
- Modify: `ansible/roles/cloudflared/defaults/main.yml`
- Modify: `ansible/roles/cloudflared/tasks/main.yml`
- Modify: `ansible/roles/cloudflared/templates/config.yml.j2`
- Modify: `ansible/inventory/host_vars/jenkins.yml`
- Modify: `ansible/playbooks/deploy-cloudflared.yml`
- Modify: `docs/designs/ansible-role-architecture.md`

**Interfaces:**
- Consumes: existing `docker`, `common`, and `cloudflared` repository conventions.
- Produces: `cloudflared_configure_tunnel: bool`, `cloudflared_tunnel_name: string`, `cloudflared_tunnel_id: string`, `cloudflared_tunnel_credentials: dict|null`, and `cloudflared_ingress_rules: list[{hostname, path?, service}]`.

- [ ] **Step 1: Review the current diff and preserve unrelated Jenkins inventory data**

Run:

```bash
git diff -- ansible/roles/cloudflared ansible/inventory/host_vars/jenkins.yml ansible/playbooks/deploy-cloudflared.yml
git show HEAD:ansible/inventory/host_vars/jenkins.yml
```

Expected: `proxmox_node: pve0` and `proxmox_vmid: 107` remain unchanged; Jenkins routing values exist only in `host_vars/jenkins.yml`.

- [ ] **Step 2: Add per-ingress-rule validation**

Immediately after the top-level Tunnel assertion in `tasks/main.yml`, add:

```yaml
    - name: Validate Cloudflare Tunnel ingress rules
      assert:
        that:
          - item.hostname is defined
          - item.hostname | length > 0
          - item.service is defined
          - item.service | length > 0
        fail_msg: >
          Each cloudflared_ingress_rules entry requires non-empty hostname and
          service values.
      loop: "{{ cloudflared_ingress_rules }}"
```

- [ ] **Step 3: Document the generic role contract**

Update `docs/designs/ansible-role-architecture.md` so Cloudflared appears as an infrastructure role. Document that it installs the package by default and optionally manages a locally managed Tunnel when `cloudflared_configure_tunnel` is true. Add the five interface variables from this task without Jenkins-specific defaults.

- [ ] **Step 4: Create an isolated Ansible syntax-test config**

Use `apply_patch` to create `.ansible-test.cfg` temporarily:

```ini
[defaults]
roles_path = /workspaces/IaC/ansible/roles
collections_path = /workspaces/IaC/ansible/collections
```

This avoids reading the production Vault while still loading repository roles and collections.

- [ ] **Step 5: Run Jenkins compatibility syntax and template tests**

Run inside the Dev Container:

```bash
cd ansible
ANSIBLE_CONFIG=/workspaces/IaC/.ansible-test.cfg \
  ansible-playbook playbooks/deploy-cloudflared.yml --syntax-check -i localhost,

ANSIBLE_CONFIG=/workspaces/IaC/.ansible-test.cfg \
  ansible localhost -i localhost, -c local \
  -m ansible.builtin.template \
  -a "src=roles/cloudflared/templates/config.yml.j2 dest=/tmp/cloudflared-config-test.yml mode=0600" \
  -e '{"cloudflared_tunnel_id":"test-tunnel-id","cloudflared_credentials_dir":"/root/.cloudflared","cloudflared_ingress_rules":[{"hostname":"jenkins.example.com","path":"/github-webhook/","service":"http://localhost:8080"}]}'

grep -F 'hostname: "jenkins.example.com"' /tmp/cloudflared-config-test.yml
grep -F 'path: "/github-webhook/"' /tmp/cloudflared-config-test.yml
grep -F 'service: "http://localhost:8080"' /tmp/cloudflared-config-test.yml
grep -F 'service: http_status:404' /tmp/cloudflared-config-test.yml
```

Expected: syntax check exits 0; all four `grep` commands find exactly the intended Jenkins route and catch-all.

- [ ] **Step 6: Remove temporary test files and run final static checks**

Delete `.ansible-test.cfg` with `apply_patch`, remove `/tmp/cloudflared-config-test.yml`, then run:

```bash
git diff --check
rg -n 'jenkins-webhook|github-webhook|vault_cloudflared_hostname' ansible/roles/cloudflared
```

Expected: `git diff --check` exits 0; `rg` returns no role matches.

- [ ] **Step 7: Review checkpoint**

Show the focused diff and ask `Ready to commit?`. If explicitly authorized, suggested commit:

```bash
git add ansible/roles/cloudflared ansible/inventory/host_vars/jenkins.yml ansible/playbooks/deploy-cloudflared.yml docs/designs/ansible-role-architecture.md
git commit -m "refactor(ansible): decouple cloudflared role from Jenkins"
```

---

### Task 2: Complete the VM definition and MCP deployment playbook

**Files:**
- Modify: `terraform/proxmox/mcp-gateway.tf`
- Create: `ansible/playbooks/deploy-mcp-gateway.yml`

**Interfaces:**
- Consumes: `proxmox-vm` module and exact VM parameters from Global Constraints.
- Produces: Terraform inventory host `mcp-gateway` in `pve_vms`; playbook that consumes the future `host_vars/mcp-gateway.yml` from Task 4.

- [ ] **Step 1: Verify the Terraform resource content**

Ensure `terraform/proxmox/mcp-gateway.tf` contains exactly:

```hcl
module "mcp_gateway" {
  source = "../modules/proxmox-vm"

  vm_name     = "mcp-gateway"
  target_node = "pve0"
  vmid        = 109
  cores       = 2
  memory      = 4096
  disk_size   = "32G"
  ip_address  = "192.168.1.109/24"

  storage_pool = var.storage_pool
  sshkeys      = var.sshkeys
}

output "mcp_gateway_ip" {
  value = module.mcp_gateway.default_ip
}

resource "ansible_host" "mcp_gateway" {
  name   = "mcp-gateway"
  groups = ["pve_vms"]
  variables = {
    ansible_user = "ubuntu"
    ansible_host = "192.168.1.109"
  }
}
```

- [ ] **Step 2: Create the deployment playbook**

Create `ansible/playbooks/deploy-mcp-gateway.yml`:

```yaml
---
- name: Deploy MCP Gateway host
  hosts: mcp-gateway
  gather_facts: true
  become: true
  roles:
    - common
    - docker
    - cloudflared

- name: Verify MCP Gateway host
  hosts: mcp-gateway
  gather_facts: false
  become: true
  tags: [verify]
  tasks:
    - name: Check Docker service status
      systemd:
        name: docker
      register: docker_status

    - name: Assert Docker service is active
      assert:
        that:
          - docker_status.status.ActiveState == "active"
        fail_msg: Docker service is not active

    - name: Check Docker Compose version
      command: docker compose version
      changed_when: false

    - name: Check cloudflared service status
      systemd:
        name: cloudflared
      register: cloudflared_status

    - name: Assert cloudflared service is active
      assert:
        that:
          - cloudflared_status.status.ActiveState == "active"
        fail_msg: cloudflared service is not active

    - name: Validate cloudflared ingress configuration
      command: >-
        cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate
      changed_when: false

    - name: Check MCP ingress rule
      command: >-
        cloudflared tunnel --config /etc/cloudflared/config.yml ingress rule
        https://mcp.willfan.me/mcp
      register: mcp_ingress_rule
      changed_when: false

    - name: Display MCP ingress rule
      debug:
        msg: "{{ mcp_ingress_rule.stdout }}"
```

- [ ] **Step 3: Run local validation**

Inside the Dev Container:

```bash
cd terraform/proxmox
terraform fmt -check -recursive
terraform init -backend=false -input=false
terraform validate

cd /workspaces/IaC/ansible
ANSIBLE_CONFIG=/workspaces/IaC/.ansible-test.cfg \
  ansible-playbook playbooks/deploy-mcp-gateway.yml --syntax-check -i localhost,
```

Expected: Terraform reports `Success! The configuration is valid.`; Ansible syntax check exits 0 with only the expected unmatched-host warning. Create and remove `.ansible-test.cfg` exactly as in Task 1.

- [ ] **Step 4: Review checkpoint**

Show the focused diff and ask `Ready to commit?`. If explicitly authorized, suggested commit:

```bash
git add terraform/proxmox/mcp-gateway.tf ansible/playbooks/deploy-mcp-gateway.yml
git commit -m "feat(mcp-gateway): add VM and deployment playbook"
```

---

### Task 3: Plan and create VM 109

**Files:**
- Runtime only: Terraform local initialization directory and saved plan under `/tmp`

**Interfaces:**
- Consumes: valid `terraform/proxmox/mcp-gateway.tf`, HCP Terraform credentials, Proxmox credentials, Ubuntu template.
- Produces: running VM 109 at `192.168.1.109` and a Terraform-backed Ansible inventory host.

- [ ] **Step 1: Initialize the real backend without changing infrastructure**

Inside the Dev Container:

```bash
cd terraform/proxmox
terraform init -input=false
```

Expected: workspace `iac-proxmox-lab` initializes successfully. If Terraform reports a backend migration, stop and ask before proceeding.

- [ ] **Step 2: Create a saved plan**

```bash
terraform plan -input=false \
  -target=module.mcp_gateway \
  -target=ansible_host.mcp_gateway \
  -out=/tmp/mcp-gateway-109-targeted.tfplan
terraform show -no-color /tmp/mcp-gateway-109-targeted.tfplan
```

Expected resource actions:

```text
module.mcp_gateway.proxmox_virtual_environment_vm.vm  create (VMID 109)
ansible_host.mcp_gateway                              update (ansible_host 192.168.1.108 -> 192.168.1.109)
```

Data-source reads and Terraform's resource-targeting warning are allowed. The expected shape is exactly 1 create, 1 in-place update, 0 replacements, and 0 deletions. Any other resource action is a blocker. The targeted plan intentionally excludes unrelated Homepage and legacy guest drift; do not expand this apply to include that drift.

- [ ] **Step 3: Stop for apply approval**

Summarize the exact plan counts and resource addresses. Do not apply until the user explicitly approves this saved plan.

- [ ] **Step 4: Apply only the approved saved plan**

```bash
terraform apply -input=false /tmp/mcp-gateway-109-targeted.tfplan
```

Expected: VM 109 is created and `ansible_host.mcp_gateway` is updated from `192.168.1.108` to `192.168.1.109`, without any replacement, deletion, or other resource action.

- [ ] **Step 5: Verify VM readiness**

```bash
terraform output mcp_gateway_ip

mcp_container_id="$(docker ps -q \
  --filter label=devcontainer.local_folder=/Users/weierfu/.codex/worktrees/2d6bb827-d3ee-425c-9b15-8c83f912ef9f/IaC)"
test -n "${mcp_container_id}"
docker cp /Users/weierfu/Projects/IaC/ansible/.vault_pass \
  "${mcp_container_id}:/tmp/iac-vault-pass"
docker exec "${mcp_container_id}" chmod 0600 /tmp/iac-vault-pass

ANSIBLE_VAULT_PASSWORD_FILE=/tmp/iac-vault-pass \
  ansible-inventory --host mcp-gateway
ANSIBLE_VAULT_PASSWORD_FILE=/tmp/iac-vault-pass \
  ansible mcp-gateway -m ansible.builtin.wait_for_connection -a 'timeout=300'

docker exec "${mcp_container_id}" rm -f /tmp/iac-vault-pass
```

Expected: inventory resolves `ansible_host: 192.168.1.109`; SSH becomes reachable. Because this is a targeted apply, `terraform output mcp_gateway_ip` can remain absent from state; record that as a non-blocking follow-up and do not run a refresh or broader apply only to update the root output.

---

### Task 4: Create the locally managed Tunnel and persist its credentials

**Files:**
- Create: `ansible/inventory/host_vars/mcp-gateway.yml`
- Modify: `ansible/inventory/group_vars/all/vault.yml`

**Interfaces:**
- Consumes: Cloudflare account ID `8e80132a8538b3f0312a8929bb065417`, named Tunnel `mcp-gateway`, primary checkout Vault password file.
- Produces: `tunnel_id: UUID`, `tunnel_secret: base64 string`, Vault dictionary `vault_mcp_gateway_cloudflared_credentials`, and complete MCP host vars.

- [ ] **Step 1: Preflight exact-name conflicts**

Using the Cloudflare API connector, list active Tunnels and filter `name == "mcp-gateway"`. Also confirm `mcp.willfan.me` still has no DNS record.

Expected: no matching Tunnel and no matching DNS record. If a match exists, compare all attributes and stop for user direction rather than creating a duplicate.

- [ ] **Step 2: Prepare secure Vault access**

Resolve the current Dev Container ID, then copy the approved primary password file into a container-only temporary file:

```bash
mcp_container_id="$(docker ps -q \
  --filter label=devcontainer.local_folder=/Users/weierfu/.codex/worktrees/2d6bb827-d3ee-425c-9b15-8c83f912ef9f/IaC)"
test -n "${mcp_container_id}"
docker cp /Users/weierfu/Projects/IaC/ansible/.vault_pass \
  "${mcp_container_id}:/tmp/iac-vault-pass"
docker exec "${mcp_container_id}" chmod 0600 /tmp/iac-vault-pass
```

Do not print the file. Verify only metadata:

```bash
docker exec "${mcp_container_id}" stat -c '%a %n' /tmp/iac-vault-pass
```

Expected: `600 /tmp/iac-vault-pass`.

- [ ] **Step 3: Generate and create the Tunnel**

Generate exactly 32 cryptographically random bytes and encode them as base64. Use the Cloudflare API connector:

```javascript
cloudflare.request({
  method: "POST",
  path: `/accounts/${accountId}/cfd_tunnel`,
  body: {
    name: "mcp-gateway",
    config_src: "local",
    tunnel_secret: tunnelSecretBase64
  }
})
```

Capture the returned Tunnel UUID and retain the generated secret only for the immediate Vault write. Do not echo either secret value in commentary or final output.

- [ ] **Step 4: Update the encrypted Vault before creating dependent resources**

Use `apply_patch` to create the temporary helper `.mcp-vault-update.py` with this exact content:

```python
#!/usr/bin/env python3
import getpass
import pathlib
import sys

import yaml

vault_path = pathlib.Path("/tmp/mcp-vault.yml")
vault = yaml.safe_load(vault_path.read_text()) or {}
mode = sys.argv[1]

if mode == "tunnel":
    tunnel_id = input("TunnelID: ").strip()
    tunnel_secret = getpass.getpass("TunnelSecret: ").strip()
    if not tunnel_id or not tunnel_secret:
        raise SystemExit("Tunnel ID and secret are required")
    vault["vault_mcp_gateway_cloudflared_credentials"] = {
        "AccountTag": "8e80132a8538b3f0312a8929bb065417",
        "TunnelSecret": tunnel_secret,
        "TunnelID": tunnel_id,
    }
elif mode == "access":
    client_id = input("ClientID: ").strip()
    client_secret = getpass.getpass("ClientSecret: ").strip()
    if not client_id or not client_secret:
        raise SystemExit("Access Client ID and secret are required")
    vault["vault_mcp_access_client_id"] = client_id
    vault["vault_mcp_access_client_secret"] = client_secret
else:
    raise SystemExit("Mode must be tunnel or access")

vault_path.write_text(yaml.safe_dump(vault, sort_keys=False))
vault_path.chmod(0o600)
```

Decrypt the Vault, run the helper in `tunnel` mode through a PTY, and enter the Task 4 Step 3 UUID and secret at its prompts. `getpass` prevents the secret from being echoed:

```bash
cd /workspaces/IaC/ansible
ansible-vault decrypt \
  --vault-password-file /tmp/iac-vault-pass \
  --output /tmp/mcp-vault.yml \
  inventory/group_vars/all/vault.yml
chmod 0600 /tmp/mcp-vault.yml
python3 /workspaces/IaC/.mcp-vault-update.py tunnel
ansible-vault encrypt \
  --vault-password-file /tmp/iac-vault-pass \
  --output /tmp/mcp-vault.yml.enc \
  /tmp/mcp-vault.yml
install -m 600 /tmp/mcp-vault.yml.enc inventory/group_vars/all/vault.yml
```

Verify without printing values:

```bash
ansible-vault view --vault-password-file /tmp/iac-vault-pass \
  inventory/group_vars/all/vault.yml \
  | sed -n 's/^\(vault_mcp_gateway_cloudflared_credentials\):.*/\1/p'
```

Expected output is exactly the variable name. If encryption or verification fails, stop; do not create DNS, Access, or cache resources.

- [ ] **Step 5: Create the host-specific inventory file with the actual UUID**

Using `apply_patch`, create `ansible/inventory/host_vars/mcp-gateway.yml` with the literal UUID returned by Step 3. The plan executor must substitute the defined Task 4 interface value `tunnel_id` before applying this YAML:

```yaml
---
proxmox_node: pve0
proxmox_vmid: 109

cloudflared_configure_tunnel: true
cloudflared_tunnel_name: mcp-gateway
cloudflared_tunnel_id: "${tunnel_id}"
cloudflared_tunnel_credentials: "{{ vault_mcp_gateway_cloudflared_credentials }}"
cloudflared_ingress_rules:
  - hostname: mcp.willfan.me
    path: ^/mcp$
    service: http://127.0.0.1:3000
```

`${tunnel_id}` is plan notation, not file content. The resulting YAML must contain the literal API-returned UUID, not `${tunnel_id}` and not a Jinja expression.

- [ ] **Step 6: Validate Vault and inventory resolution**

Inside the Dev Container:

```bash
cd ansible
ANSIBLE_VAULT_PASSWORD_FILE=/tmp/iac-vault-pass \
  ansible-inventory --host mcp-gateway
```

Expected: the host resolves the literal Tunnel UUID and a credentials dictionary. Do not print the full inventory output because it contains secrets; inspect it programmatically and print only boolean checks and non-sensitive fields.

- [ ] **Step 7: Remove transient secret material**

Remove secret-bearing temporary files. Keep the non-secret `.mcp-vault-update.py` only until Task 5 completes:

```bash
rm -f /tmp/mcp-vault.yml /tmp/mcp-vault.yml.enc \
  /tmp/mcp-cloudflare-secrets.json /tmp/iac-vault-pass
test ! -e /tmp/mcp-vault.yml
test ! -e /tmp/mcp-vault.yml.enc
test ! -e /tmp/mcp-cloudflare-secrets.json
test ! -e /tmp/iac-vault-pass
```

- [ ] **Step 8: Review checkpoint**

Show only non-secret diffs and ask `Ready to commit?`. Never display the decrypted Vault diff. If explicitly authorized, suggested commit:

```bash
git add ansible/inventory/host_vars/mcp-gateway.yml ansible/inventory/group_vars/all/vault.yml
git commit -m "feat(mcp-gateway): add encrypted tunnel credentials"
```

---

### Task 5: Create DNS, Access, Service Token, policy, and cache bypass

**Files:**
- Modify: `ansible/inventory/group_vars/all/vault.yml`

**Interfaces:**
- Consumes: Task 4 `tunnel_id`, zone ID `085d9064cc64b076de2d78bf016684dd`, account ID, and Vault access process.
- Produces: DNS record ID, Access Application ID, Service Token ID plus one-time Client ID/Secret, policy ID, ruleset ID, and cache rule ID.

- [ ] **Step 1: Re-run full Cloudflare preflight**

Read active Tunnels, `mcp.willfan.me` DNS, Access apps, Service Tokens, and the zone `http_request_cache_settings` ruleset. Expected state before creation:

```text
Tunnel mcp-gateway: exists with Task 4 UUID and config_src local
DNS mcp.willfan.me: absent
Access app domain mcp.willfan.me/mcp: absent
Service Token mcp-agents: absent
Cache rule description Bypass cache for MCP endpoint: absent
```

Stop on any conflict.

- [ ] **Step 2: Create the proxied Tunnel DNS route**

```javascript
cloudflare.request({
  method: "POST",
  path: `/zones/085d9064cc64b076de2d78bf016684dd/dns_records`,
  body: {
    type: "CNAME",
    name: "mcp",
    content: `${tunnelId}.cfargotunnel.com`,
    proxied: true,
    ttl: 1,
    comment: "MCP Gateway Cloudflare Tunnel"
  }
})
```

Expected: response hostname is `mcp.willfan.me`, type is CNAME, and `proxied` is true.

- [ ] **Step 3: Create the one-year shared Service Token**

```javascript
cloudflare.request({
  method: "POST",
  path: `/accounts/${accountId}/access/service_tokens`,
  body: {
    name: "mcp-agents",
    duration: "8760h",
    enabled: true
  }
})
```

Capture `id`, `client_id`, and the one-time `client_secret`. Do not print the Client Secret outside the tool result needed for immediate secure storage.

- [ ] **Step 4: Persist Access credentials immediately**

Copy the primary `.vault_pass` into the container and decrypt the Vault:

```bash
mcp_container_id="$(docker ps -q \
  --filter label=devcontainer.local_folder=/Users/weierfu/.codex/worktrees/2d6bb827-d3ee-425c-9b15-8c83f912ef9f/IaC)"
test -n "${mcp_container_id}"
docker cp /Users/weierfu/Projects/IaC/ansible/.vault_pass \
  "${mcp_container_id}:/tmp/iac-vault-pass"
docker exec "${mcp_container_id}" chmod 0600 /tmp/iac-vault-pass

cd /workspaces/IaC/ansible
ansible-vault decrypt \
  --vault-password-file /tmp/iac-vault-pass \
  --output /tmp/mcp-vault.yml \
  inventory/group_vars/all/vault.yml
chmod 0600 /tmp/mcp-vault.yml
```

Run the Access update:

```bash
python3 /workspaces/IaC/.mcp-vault-update.py access
```

At the PTY prompts, enter the `client_id` and one-time `client_secret` returned in Step 3. Re-encrypt and install the Vault:

```bash
ansible-vault encrypt \
  --vault-password-file /tmp/iac-vault-pass \
  --output /tmp/mcp-vault.yml.enc \
  /tmp/mcp-vault.yml
install -m 600 /tmp/mcp-vault.yml.enc inventory/group_vars/all/vault.yml
```

Verify only these variable names:

```bash
ansible-vault view --vault-password-file /tmp/iac-vault-pass \
  inventory/group_vars/all/vault.yml \
  | sed -n 's/^\(vault_mcp_access_client_id\|vault_mcp_access_client_secret\):.*/\1/p'
```

Expected: both variable names appear once. If this fails, stop before creating the Application or policy.

- [ ] **Step 5: Create the path-scoped Access Application**

```javascript
cloudflare.request({
  method: "POST",
  path: `/accounts/${accountId}/access/apps`,
  body: {
    name: "MCP Gateway",
    type: "self_hosted",
    domain: "mcp.willfan.me/mcp",
    session_duration: "24h",
    app_launcher_visible: false,
    service_auth_401_redirect: true
  }
})
```

Expected: response domain is exactly `mcp.willfan.me/mcp`.

- [ ] **Step 6: Create the Service Auth policy**

The current OpenAPI represents the Service Auth UI decision as `non_identity`:

```javascript
cloudflare.request({
  method: "POST",
  path: `/accounts/${accountId}/access/apps/${appId}/policies`,
  body: {
    name: "mcp-agents only",
    decision: "non_identity",
    precedence: 1,
    include: [
      { service_token: { token_id: serviceTokenId } }
    ]
  }
})
```

Expected: decision is `non_identity`, precedence is 1, and the include rule references only the `mcp-agents` token ID.

- [ ] **Step 7: Create the first zone cache ruleset**

Because the zone currently has no `http_request_cache_settings` entrypoint, create it rather than issuing a destructive PUT against an unknown rules list:

```javascript
cloudflare.request({
  method: "POST",
  path: `/zones/085d9064cc64b076de2d78bf016684dd/rulesets`,
  body: {
    name: "MCP Gateway cache rules",
    description: "Cache behavior for MCP Gateway",
    kind: "zone",
    phase: "http_request_cache_settings",
    rules: [
      {
        action: "set_cache_settings",
        action_parameters: { cache: false },
        expression: '(http.host eq "mcp.willfan.me" and http.request.uri.path eq "/mcp")',
        description: "Bypass cache for MCP endpoint",
        enabled: true
      }
    ]
  }
})
```

Expected: returned phase is `http_request_cache_settings` and the rule has `cache: false`.

- [ ] **Step 8: Read back every Cloudflare object**

GET the exact Tunnel, DNS record, Service Token, Access Application, Application policies, and ruleset. Compare names, IDs, domain, duration, decision, expression, and cache action. Never request or print the one-time Client Secret again.

- [ ] **Step 9: Remove temporary Vault material and review**

Run:

```bash
rm -f /tmp/mcp-vault.yml /tmp/mcp-vault.yml.enc /tmp/iac-vault-pass
test ! -e /tmp/mcp-vault.yml
test ! -e /tmp/mcp-vault.yml.enc
test ! -e /tmp/iac-vault-pass
```

Delete `.mcp-vault-update.py` using `apply_patch`. Show the non-secret Cloudflare IDs and ask `Ready to commit?`. If explicitly authorized, suggested commit:

```bash
git add ansible/inventory/group_vars/all/vault.yml
git commit -m "feat(mcp-gateway): store encrypted Access credentials"
```

---

### Task 6: Deploy Docker and Cloudflared to the new VM

**Files:**
- Runtime only: target VM state

**Interfaces:**
- Consumes: reachable VM 109, complete encrypted Vault, `deploy-mcp-gateway.yml`, Cloudflare Tunnel credentials.
- Produces: active Docker and Cloudflared services and a healthy Cloudflare connector.

- [ ] **Step 1: Restore Vault access only for the deployment process**

Run on the host:

```bash
mcp_container_id="$(docker ps -q \
  --filter label=devcontainer.local_folder=/Users/weierfu/.codex/worktrees/2d6bb827-d3ee-425c-9b15-8c83f912ef9f/IaC)"
test -n "${mcp_container_id}"
docker cp /Users/weierfu/Projects/IaC/ansible/.vault_pass \
  "${mcp_container_id}:/tmp/iac-vault-pass"
docker exec "${mcp_container_id}" chmod 0600 /tmp/iac-vault-pass
```

Do not create `ansible/.vault_pass` in the worktree.

- [ ] **Step 2: Run syntax check with the real inventory and Vault**

```bash
cd ansible
ANSIBLE_VAULT_PASSWORD_FILE=/tmp/iac-vault-pass \
  ansible-playbook playbooks/deploy-mcp-gateway.yml --syntax-check
```

Expected: exit 0 with `playbook: playbooks/deploy-mcp-gateway.yml`.

- [ ] **Step 3: Run a check-mode preview**

```bash
ANSIBLE_VAULT_PASSWORD_FILE=/tmp/iac-vault-pass \
  ansible-playbook playbooks/deploy-mcp-gateway.yml --check --diff
```

Expected: package and service tasks report intended changes. Tasks that cannot operate meaningfully in check mode must be identified before real deployment; do not bypass failures with SSH commands.

- [ ] **Step 4: Stop for deployment approval**

Summarize check-mode changes and any modules that skipped check mode. Wait for explicit approval before the real playbook run.

- [ ] **Step 5: Run the full first deployment**

```bash
ANSIBLE_VAULT_PASSWORD_FILE=/tmp/iac-vault-pass \
  ansible-playbook playbooks/deploy-mcp-gateway.yml
```

Expected: `common`, `docker`, and `cloudflared` complete; handlers finish; no failed hosts.

- [ ] **Step 6: Run verification tags**

```bash
ANSIBLE_VAULT_PASSWORD_FILE=/tmp/iac-vault-pass \
  ansible-playbook playbooks/deploy-mcp-gateway.yml --tags verify
```

Expected: Docker active, Compose command succeeds, Cloudflared active, ingress validates, and `/mcp` matches the intended ingress rule.

- [ ] **Step 7: Verify connector health through Cloudflare API**

Poll the Tunnel connections endpoint until at least one active connector exists, bounded to five minutes. Accept Tunnel status `healthy`; stop and inspect systemd logs if it remains `inactive`, `down`, or `degraded`.

- [ ] **Step 8: Remove temporary Vault access**

Run:

```bash
rm -f /tmp/iac-vault-pass
test ! -e /tmp/iac-vault-pass
```

---

### Task 7: Verify Access behavior and document the deployment

**Files:**
- Modify: `docs/designs/ansible-vault-architecture.md`
- Create: `docs/learningnotes/2026-08-28-mcp-gateway-deployment.md`

**Interfaces:**
- Consumes: all Cloudflare resource IDs, healthy connector, encrypted Access credentials.
- Produces: evidence-backed operational handoff without disclosing secrets.

- [ ] **Step 1: Verify unauthenticated Access denial**

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://mcp.willfan.me/mcp
```

Expected: Access denial or 401 response; it must not reach the origin.

- [ ] **Step 2: Verify authenticated Access traversal without printing headers**

Read Client ID and Secret from Vault into process memory and send:

```text
CF-Access-Client-Id: vault_mcp_access_client_id
CF-Access-Client-Secret: vault_mcp_access_client_secret
```

Expected: request passes Access. Until the MCP app is deployed, origin `502` is acceptable and proves the request reached the Tunnel/origin boundary. A Cloudflare Access denial is not acceptable.

- [ ] **Step 3: Verify non-MCP paths are rejected**

Request `https://mcp.willfan.me/not-mcp`. Expected: the Tunnel catch-all returns 404 once the request reaches ingress. If Access intercepts the host before ingress, use `cloudflared tunnel ingress rule` locally to prove the 404 rule selection and document that boundary.

- [ ] **Step 4: Verify cache rule by API readback**

GET the zone `http_request_cache_settings` entrypoint. Expected exact expression:

```text
(http.host eq "mcp.willfan.me" and http.request.uri.path eq "/mcp")
```

Expected action is `set_cache_settings` with `action_parameters.cache == false`.

- [ ] **Step 5: Update Vault architecture documentation**

Add the three MCP Vault variables, consumers, and scope to `docs/designs/ansible-vault-architecture.md`. State that `vault_mcp_gateway_cloudflared_credentials` is host-specific server configuration, while the Access Client ID/Secret are shared client credentials for agent consumers.

- [ ] **Step 6: Write the learning note**

Create `docs/learningnotes/2026-08-28-mcp-gateway-deployment.md` in Chinese. Include:

- VM and non-secret Cloudflare resource IDs.
- Locally managed Tunnel and Access request flow.
- Why ingress matches `^/mcp$` while service uses `http://127.0.0.1:3000`.
- Why authenticated `502` is expected before the MCP app exists.
- How to use the two Access headers without showing values.
- Q&A summary covering shared-token trade-offs, one-year refresh, rotation grace period, and cache bypass.
- Exact verification commands with secret values omitted.

- [ ] **Step 7: Run final repository verification**

```bash
git diff --check
cd terraform/proxmox
terraform fmt -check -recursive
terraform validate
cd /workspaces/IaC/ansible
ANSIBLE_VAULT_PASSWORD_FILE=/tmp/iac-vault-pass \
  ansible-playbook playbooks/deploy-cloudflared.yml --syntax-check
ANSIBLE_VAULT_PASSWORD_FILE=/tmp/iac-vault-pass \
  ansible-playbook playbooks/deploy-mcp-gateway.yml --syntax-check
```

Before these commands, recreate `/tmp/iac-vault-pass` with:

```bash
mcp_container_id="$(docker ps -q \
  --filter label=devcontainer.local_folder=/Users/weierfu/.codex/worktrees/2d6bb827-d3ee-425c-9b15-8c83f912ef9f/IaC)"
test -n "${mcp_container_id}"
docker cp /Users/weierfu/Projects/IaC/ansible/.vault_pass \
  "${mcp_container_id}:/tmp/iac-vault-pass"
docker exec "${mcp_container_id}" chmod 0600 /tmp/iac-vault-pass
```

Expected: every validation command exits 0. Then run:

```bash
rm -f /tmp/iac-vault-pass
test ! -e /tmp/iac-vault-pass
```

- [ ] **Step 8: Final review checkpoint**

Report VM state, service state, Tunnel health, Access behavior, cache readback, files changed, and any expected `502` limitation. Ask `Ready to commit?`. If explicitly authorized, suggested final documentation commit:

```bash
git add docs/designs/ansible-vault-architecture.md docs/learningnotes/2026-08-28-mcp-gateway-deployment.md docs/superpowers/specs/2026-08-28-mcp-gateway-design.md docs/superpowers/plans/2026-08-28-mcp-gateway.md
git commit -m "docs(mcp-gateway): document secure deployment"
```
