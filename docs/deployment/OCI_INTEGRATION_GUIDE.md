# Oracle Cloud Infrastructure (OCI) Integration Guide

## 1. Overview
This guide documents the process of integrating an external Oracle Cloud Infrastructure (OCI) compute instance into the local Homelab Infrastructure-as-Code (IaC) environment. The goal is to manage the OCI instance via Terraform, configure it via Ansible, and monitor it via the Homepage dashboard using Tailscale for secure connectivity.

## 2. Architecture
*   **Management**: Terraform (State), Ansible (Configuration).
*   **Connectivity**: Tailscale VPN (Mesh network between Proxmox, LXC containers, and OCI).
*   **Monitoring**: Homepage Dashboard (running in LXC) pinging OCI via Tailscale IP.

## 3. Terraform Integration

### 3.1 Prerequisites
*   OCI API Key Pair (Private Key `.pem` and Public Key `.pem`).
*   Tenancy OCID, User OCID, Compartment OCID.
*   Fingerprint of the API Key.

### 3.2 Provider Configuration
Configure the `oci` provider in `terraform/oci/provider.tf` and variables in `terraform.tfvars`:
```hcl
provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}
```

### 3.3 Importing Existing Instances
If the instance already exists, use `terraform import` to bring it into state without recreation:
1.  Define the `oci_core_instance` resource in `compute.tf`.
2.  Run import command:
    ```bash
    terraform import oci_core_instance.ubuntu_instance <Instance_OCID>
    ```
3.  **Critical**: Handle mutable attributes that change on every API call (like metadata or Oracle-managed tags) to prevent Terraform from forcing a replacement.
    ```hcl
    lifecycle {
      ignore_changes = [
        metadata,
        defined_tags,
        freeform_tags,
        create_vnic_details[0].defined_tags
      ]
    }
    ```

## 4. Ansible & Tailscale Configuration

### 4.1 Inventory Setup
Add the OCI host to `inventory/oci/hosts.yml` using its **Public IP** for initial SSH access:
```yaml
oci:
  hosts:
    oracle-cloud-ubuntu2404:
      ansible_host: 152.67.113.23
      ansible_user: ubuntu
      ansible_ssh_private_key_file: ~/.ssh/id_ed25519
```

### 4.2 Tailscale Deployment
Deploy Tailscale to both the OCI host and local LXC containers.
*   **Role**: Use a reusable `tailscale` role.
*   **Auth Key**: Store `tailscale_auth_key` in `group_vars/tailscale.yml` (encrypted via Ansible Vault recommended).

### 4.3 LXC Specific Configuration (The "Tricky" Part)
To run Tailscale inside an unprivileged Proxmox LXC container (like Homepage), specific configurations are required:

#### A. Tun Device Passthrough
Tailscale needs `/dev/net/tun`. On the Proxmox host:
```yaml
# Ansible Task (delegate_to: proxmox_node)
- name: Configure LXC device passthrough
  blockinfile:
    path: "/etc/pve/lxc/{{ proxmox_vmid }}.conf"
    block: |
      lxc.cgroup2.devices.allow: c 10:200 rwm
      lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
```

#### B. DNS Resolution Fix
Proxmox attempts to overwrite `/etc/resolv.conf` in LXC containers with its own settings (often MagicDNS IPs if the host has Tailscale). This breaks DNS in the container if Tailscale isn't fully up yet.
**Fix**: Prevent overwriting and force a valid nameserver.
```yaml
# Ansible Task (inside LXC)
- name: Prevent Proxmox from overwriting resolv.conf
  file:
    path: /etc/.pve-ignore.resolv.conf
    state: touch

- name: Set temporary DNS
  copy:
    dest: /etc/resolv.conf
    content: "nameserver 8.8.8.8"
```

## 5. Homepage Dashboard Integration

### 5.1 Service Configuration
Configure `services.yaml` to monitor the OCI instance.
*   **Href**: Use `ssh://` with the Public IP for clickable links.
*   **Ping**: Use the **Tailscale IP** (`100.x.y.z`) for status checks. This bypasses OCI Security List (Firewall) restrictions that might block ICMP on the public interface.

```yaml
- Oracle Cloud:
    - oracle-cloud-ubuntu2404:
        icon: oracle.png
        href: ssh://ubuntu@152.67.113.23
        description: OCI Compute Instance
        ping: 100.114.121.121  # Tailscale IP
```

### 5.2 Proxmox Widget Permissions
If using the Proxmox widget, ensure the API Token has correct permissions.
*   **Issue**: Widget shows "Unknown" or "API Error".
*   **Cause**: "Privilege Separation" is enabled, so the Token doesn't inherit user permissions.
*   **Fix**: In Proxmox GUI > Datacenter > Permissions > API Tokens, explicitly grant `PVEAuditor` role to the Token on path `/`.

## 6. Troubleshooting Checklist
1.  **Terraform Plan shows Replacement?** Check `lifecycle.ignore_changes`.
2.  **LXC `apt update` fails?** Check `/etc/resolv.conf` and ensure `.pve-ignore.resolv.conf` exists.
3.  **Tailscale in LXC fails?** Verify `/dev/net/tun` is accessible (`ls -l /dev/net/tun`).
4.  **Homepage OCI Status Down?** Verify Homepage container can ping the OCI Tailscale IP (`ansible homepage-node -m shell -a "ping 100.x.y.z"`).
