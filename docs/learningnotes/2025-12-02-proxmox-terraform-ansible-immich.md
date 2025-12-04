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

## 4. Key Concepts

*   **DNS Inheritance (DNS 继承)**:
    *   **定义**: 虚拟机在启动时从宿主机 (Proxmox) 获取 DNS 配置的行为。
    *   **问题**: 如果宿主机使用 Tailscale MagicDNS (100.x.x.x)，而新 VM 尚未加入 Tailnet，就会导致 DNS 解析失败。
    *   **解决**: 在 Terraform 中显式指定 `nameserver` 指向局域网网关 (如 192.168.1.1)。
*   **Ansible `uri` Module Retries**:
    *   **定义**: Ansible 的一种机制，允许任务在失败后重试。
    *   **应用**: 用于检测服务启动。容器启动不代表应用就绪，使用 `until` + `retries` + `delay` 循环检测 HTTP 200 状态码，确保服务真正可用。

## 5. Q&A

**Q: 为什么新创建的 VM 无法解析域名？**
**A:** 因为 Proxmox 宿主机配置了 Tailscale MagicDNS，新 VM 继承了这个配置，但它自己还没有 Tailscale 凭据，所以无法访问 MagicDNS 服务器。

**Q: 为什么 `docker compose up` 成功了，但 HTTP 检测还是失败？**
**A:** `docker compose up` 只是启动了容器进程。应用内部初始化（如数据库连接、迁移）需要时间。这就是为什么我们需要在 Ansible 中使用 `wait_for` 或 `uri` 模块配合重试机制来等待应用真正就绪。

