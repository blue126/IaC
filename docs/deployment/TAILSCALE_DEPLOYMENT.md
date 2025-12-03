# Tailscale Deployment Guide

## 1. Overview
This document details the automated deployment of Tailscale across the infrastructure, including Proxmox hosts, LXC containers, and external OCI instances. The deployment is managed via Ansible with a unified inventory and a feature-rich role.

## 2. Architecture

### 2.1 Inventory Structure
All Tailscale nodes are grouped under `tailscale` in `inventory/groups.yml`. This group aggregates:
*   `proxmox_cluster`: Physical Proxmox nodes.
*   `oci`: External Oracle Cloud instances.
*   `pve_lxc`: Local LXC containers (e.g., Homepage, Anki).

### 2.2 Variable Management
*   **Auth Key**: Centralized in `inventory/group_vars/tailscale.yml`.
*   **Key Rotation**: Update the key in this single file to rotate it across the entire fleet.

## 3. Role Capabilities (`roles/tailscale`)

The `tailscale` role is self-contained and handles environment-specific logic:

### 3.1 Standard Installation
*   Installs `curl`.
*   Downloads and runs the official install script.
*   Enables IP forwarding (`net.ipv4.ip_forward`).
*   Authenticates and brings up the interface (`tailscale up`).

### 3.2 LXC-Specific Logic
For unprivileged LXC containers, the role automatically performs the following (delegated to the Proxmox host where necessary):

1.  **Device Passthrough**:
    *   Modifies `/etc/pve/lxc/<vmid>.conf` on the host.
    *   Adds `lxc.cgroup2.devices.allow` and `lxc.mount.entry` for `/dev/net/tun`.
    *   **Condition**: `ansible_facts.virtualization_type == 'lxc'`.

2.  **DNS Fix**:
    *   Creates `/etc/.pve-ignore.resolv.conf` to prevent Proxmox from overwriting DNS.
    *   Sets `/etc/resolv.conf` to a valid resolver (e.g., `8.8.8.8`) to ensure connectivity before Tailscale is up.

3.  **Automatic Restart**:
    *   If the LXC configuration is modified, the container is automatically restarted to apply the changes.

### 3.3 Tailscale Serve (Optional)
The role includes a dedicated task file for configuring Tailscale Serve, which exposes local services to the Tailscale network via a magic DNS URL (e.g., `https://service.wyrm-wall.ts.net`).

*   **Usage**: Include the role with `tasks_from: serve`.
*   **Variable**: `tailscale_serve_target` (e.g., `http://127.0.0.1:3000`).
*   **Behavior**:
    *   If `tailscale_serve_target` is defined: Configures Serve (HTTP/HTTPS).
    *   If `tailscale_serve_target` is undefined: Resets/Cleans up Serve configuration.

**Example Playbook Snippet**:
```yaml
- include_role:
    name: tailscale
    tasks_from: serve
  vars:
    tailscale_serve_target: "http://127.0.0.1:3000"
```

## 4. Usage

### 4.1 Run the Playbook
```bash
ansible-playbook playbooks/install-tailscale.yml
```

### 4.2 Verify Status
The playbook outputs the Tailscale IP for each node. You can also check manually:
```bash
tailscale status
```

## 5. Troubleshooting

### 5.1 LXC Container Fails to Connect
*   **Check Tun Device**: Ensure `/dev/net/tun` exists inside the container.
*   **Check DNS**: Verify `/etc/resolv.conf` is not pointing to an unreachable internal IP.
*   **Restart**: If configuration changed, ensure the container was restarted.

### 5.2 Auth Key Expiration
If nodes fail to authenticate, check if the `tailscale_auth_key` in `inventory/group_vars/tailscale.yml` has expired. Generate a new Reusable Key in the Tailscale Admin Console and update the file.
