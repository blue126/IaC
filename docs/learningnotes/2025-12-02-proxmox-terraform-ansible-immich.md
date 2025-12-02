# Learning Notes: Proxmox, Terraform & Ansible

## 1. Terraform & Proxmox Networking
### DNS Inheritance Issue
- **Problem**: New VMs created via Terraform/Cloud-Init were inheriting the Proxmox host's DNS settings. Since the host was using Tailscale MagicDNS (`100.100.100.100`), and the new VM wasn't yet authenticated to Tailscale, DNS resolution failed during bootstrapping.
- **Solution**: Explicitly define `nameserver` in the Terraform `proxmox_vm_qemu` resource.
- **Best Practice**: Refactor the Terraform module to accept global `nameserver` and `gateway` variables (defaulting to the LAN gateway, e.g., `192.168.1.1`) to ensure all VMs have reliable connectivity before Tailscale is installed.

### IP Address Configuration
- **Refactoring**: Separating the IP CIDR from the Gateway configuration in Terraform variables allows for cleaner code and global gateway management.
  - Old: `ip_address = "ip=192.168.1.101/24,gw=192.168.1.1"`
  - New: `ip_address = "192.168.1.101/24"` (Module handles the `gw=` part using a global variable).

## 2. Ansible Deployment Patterns
### Robust Verification
- **Issue**: Services like Immich take time to initialize. A simple HTTP check immediately after container start often fails with `Connection reset by peer`.
- **Fix**: Use `retries` and `delay` in the `ansible.builtin.uri` module.
  ```yaml
  until: result.status == 200
  retries: 12
  delay: 10
  ```

### Hostname Management
- **Observation**: Cloud-Init doesn't always reliably set the hostname based on the Proxmox VM name.
- **Workaround**: Use an Ansible `pre_task` to explicitly set the hostname:
  ```yaml
  - name: Set hostname
    ansible.builtin.hostname:
      name: "{{ inventory_hostname }}"
  ```

### Inventory Structure
- **Naming**: Renaming hosts to match their service names (e.g., `immich` instead of `immich-node`) is cleaner but triggers Ansible warnings if group names are identical. This is acceptable for single-node services.
- **Tailscale Grouping**: Ensure new inventory groups (like `pve_vms`) are added as children to the `tailscale` group so the VPN role is applied automatically.

## 3. Homepage Dashboard
### YAML Layout Quirks
- **Issue**: Defining a service as a list of items (nested list) causes Homepage to render it as a separate row/group.
  ```yaml
  - Group:
      - Item:  # <--- This nesting causes layout issues
          ...
  ```
- **Fix**: Flatten the structure for single items to render them as cards within the parent group.
  ```yaml
  - Group:
      icon: ...
      href: ...
  ```

### Secrets Management
- **Vault**: Always use Ansible Vault for API keys. Updating the vault requires re-running the deployment playbook to regenerate the config files.
