# Caddy Deployment Guide

## 1. Overview
This document details the deployment of Caddy as a centralized Reverse Proxy and WebDAV server on an Alpine Linux LXC container. The deployment is fully automated via Ansible.

## 2. Architecture
*   **Host**: Alpine Linux LXC (VMID 105, `caddy`).
*   **Function**:
    *   **WebDAV**: Secure file access via `https://webdav.willfan.me` and `http://<IP>:8080`.
    *   **Reverse Proxy**: Exposes internal services (Homepage, Immich, etc.) via subdomains (`*.willfan.me`).
    *   **SSL**: Automatic HTTPS via Cloudflare DNS Challenge.

## 3. Role Configuration (`roles/caddy`)

The `caddy` role is designed to be flexible. Key configuration is managed via variables in `inventory/pve_lxc/caddy.yml` or `group_vars`.

### 3.1 Core Variables
| Variable | Default | Description |
| :--- | :--- | :--- |
| `caddy_version` | `2.8.4` | Version of Caddy to install. |
| `caddy_domain` | `localhost` | Base domain for the server (e.g., `willfan.me`). |
| `caddy_email` | `hello@willfan.me` | Email for Let's Encrypt registration. |
| `cloudflare_api_token` | `""` | **Required**. Cloudflare API Token for DNS challenges (store in Vault). |

### 3.2 WebDAV Configuration
| Variable | Default | Description |
| :--- | :--- | :--- |
| `caddy_webdav_root` | `/var/www/webdav` | Directory to serve via WebDAV. |
| `caddy_webdav_port` | `8080` | Port for direct HTTP access (internal only). |
| `caddy_webdav_user` | `admin` | Username for Basic Auth. |
| `caddy_webdav_password_hash`| `""` | **Required**. Bcrypt hash of the password. |

### 3.3 Reverse Proxy Configuration (`caddy_reverse_proxies`)
This is a list of dictionaries defining the services to proxy.

**Structure:**
```yaml
caddy_reverse_proxies:
  - subdomain: "service_name"       # e.g., "immich" -> immich.willfan.me
    upstream: "http://ip:port"      # Internal backend URL
    insecure_skip_verify: false     # (Optional) Set true if backend uses self-signed certs
```

**Example:**
```yaml
caddy_reverse_proxies:
  - subdomain: "homepage"
    upstream: "http://192.168.1.103:3000"
  - subdomain: "proxmox"
    upstream: "https://192.168.1.50:8006"
    insecure_skip_verify: true
```

## 4. Deployment Steps

### 4.1 Prerequisites
1.  **Cloudflare Token**: Ensure `vault_cloudflare_api_token` is defined in `inventory/group_vars/all/vault.yml`.
2.  **Password Hash**: Generate a password hash for WebDAV:
    ```bash
    caddy hash-password --plaintext 'YourPassword'
    ```
    Add it to `inventory/pve_lxc/caddy.yml` as `caddy_webdav_password_hash`.

### 4.2 Run Playbook
Execute the deployment playbook:
```bash
ansible-playbook playbooks/deploy-caddy.yml
```

### 4.3 Verify
1.  **WebDAV**: Connect to `https://webdav.willfan.me` (requires DNS) or `http://192.168.1.105:8080`.
2.  **Reverse Proxy**: Visit `https://homepage.willfan.me`, etc.

## 5. Maintenance
*   **Add New Service**: Simply add a new entry to `caddy_reverse_proxies` in `inventory/pve_lxc/caddy.yml` and re-run the playbook.
*   **Logs**: Check logs via `rc-service caddy status` or `/var/log/caddy/access.log`.
