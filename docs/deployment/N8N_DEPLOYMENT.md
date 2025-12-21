# n8n Deployment Guide

**Service**: n8n Workflow Automation
**Method**: LXC Container (npm)
**Infrastructure**: Terraform + Ansible

## Architecture
- **Type**: Unprivileged LXC Container
- **OS**: Debian 12 (via TurnKey Node.js template)
- **Networking**: `192.168.1.106/24` (Static), Gateway `192.168.1.1`
- **Reverse Proxy**: Caddy (`n8n.willfan.me` -> `http://192.168.1.106:5678`)

## Infrastructure (Terraform)
Defined in `terraform/proxmox/n8n.tf`.
- **Module**: `proxmox-lxc`
- **Resources**: 2 vCPU, 2GB RAM, 8GB Disk
- **Template**: `debian-12-turnkey-nodejs_18.0-1_amd64.tar.gz`

## Configuration (Ansible)
Defined in `ansible/roles/n8n`.

### Prerequisites Handling
By default, the TurnKey template includes a manual installation of Node.js in `/usr/local/bin` which may be outdated.
- **Action**: The Ansible role **removes** `/usr/local/bin/node` and `/usr/local/bin/npm` to prevent conflicts.
- **Install**: Installs the latest Node.js LTS (v20.x) from NodeSource.

### Service Configuration
Systemd service: `/etc/systemd/system/n8n.service`

**Environment Variables**:
- `N8N_PORT=5678`
- `N8N_SECURE_COOKIE=false`: **Crucial** for accessing n8n via raw IP/HTTP. Without this, n8n enforces HTTPS and the login/setup page will fail with cookie errors.
- `N8N_ENCRYPTION_KEY`: **Left unset**. n8n automatically generates a key in `/root/.n8n/config`.
    - **Warning**: Do NOT dynamically generate this key in Ansible (e.g., `lookup('password', ...)`). Every deployment would change the key, making existing credentials/workflows unreadable and causing n8n to crash on startup with an encryption key mismatch error.

## Maintenance

### Updating n8n
To update n8n to the latest version, run the Ansible playbook again. It uses `npm install -g n8n` which will fetch the latest version.
```bash
ansible-playbook ansible/playbooks/deploy-n8n.yml
```

### Accessing Logs
```bash
ssh root@192.168.1.106
journalctl -u n8n -f
```

## Troubleshooting history

### Encryption Key Mismatch
**Symptom**: Service restarts indefinitely. Logs show `Error: Mismatching encryption keys`.
**Cause**: The `N8N_ENCRYPTION_KEY` env var changed (e.g., Ansible re-generated it), mismatching the key stored in `/root/.n8n/config`.
**Fix**: Stop n8n, remove the environment variable from systemd unit, and let n8n use the config file key. (Or wipe `/root/.n8n` to reset if data loss is acceptable).

### Secure Cookie Error
**Symptom**: "Your n8n server is configured to use a secure cookie, however you are either visiting this via an insecure URL..."
**Fix**: Set `N8N_SECURE_COOKIE=false` if not using HTTPS.
