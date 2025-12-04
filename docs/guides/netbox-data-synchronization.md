# Netbox 数据同步工作流指南

本文档详细说明了我们项目中用于管理 Netbox 数据的混合工作流（Hybrid Workflow）。该工作流结合了 **Terraform** 的状态管理能力和 **Ansible** 的动态发现能力，实现了对基础设施数据的精确且自动化的管理。

## 1. 核心理念：Terraform 管生，Ansible 管养

我们采用 **"Lifecycle vs. Enrichment"** 的分工模式：

*   **Terraform (Lifecycle)**: 负责资源的**生命周期管理**。即“创建”和“销毁”。它定义了基础设施的**骨架**。
*   **Ansible (Enrichment)**: 负责资源的**信息补全**。即“更新”和“修正”。它填充了基础设施的**血肉**（运行时数据）。

### 为什么这样做？
*   **Terraform 擅长**：确保资源存在（State Management）。如果你删除了代码，Terraform 会自动删除 Netbox 里的条目。
*   **Ansible 擅长**：获取真实信息（Fact Gathering）。Terraform 在运行前不知道虚拟机实际分配了多少磁盘（特别是当磁盘大小由模板决定时），但 Ansible 登录上去一看便知。

## 2. 管辖范围 (Jurisdiction)

| 字段/资源 | 管理者 | 说明 |
| :--- | :--- | :--- |
| **Device / VM 对象** | **Terraform** | 创建 VM 条目，定义其名称、Cluster、Role。 |
| **Interface / IP** | **Terraform** | 分配静态 IP，绑定网卡。 |
| **Services** | **Terraform** | 定义开放端口（如 80, 443, 5432）。 |
| **CPU (vCPUs)** | **Ansible** | Terraform 设定初始值，Ansible 更新为实际值。 |
| **Memory** | **Ansible** | Terraform 设定初始值，Ansible 更新为实际值。 |
| **Disk Size** | **Ansible** | Terraform 设定初始值，Ansible 更新为实际值。 |
| **Serial / Asset Tag** | **Ansible** | 仅 Ansible 能获取到这些硬件信息。 |
| **Comments** | **Ansible** | 注释可能包含动态信息，交由 Ansible 维护。 |

## 3. 冲突解决机制 (Conflict Resolution)

由于两个工具都会修改同一个资源（VM），可能会发生冲突：
1.  Terraform 创建 VM，设置内存为 `4GB`。
2.  Ansible 运行，发现实际内存是 `3.9GB` (系统占用)，更新 Netbox 为 `3.9GB`。
3.  下次 Terraform 运行时，发现 Netbox 里的 `3.9GB` 和代码里的 `4GB` 不一致，试图改回 `4GB`。

**解决方案**：
我们在 Terraform 代码中使用了 `lifecycle { ignore_changes = [...] }` 块。

```hcl
resource "netbox_virtual_machine" "example" {
  # ... 初始定义 ...

  lifecycle {
    ignore_changes = [
      vcpus,
      memory_mb,
      disk_size_mb,
      comments
    ]
  }
}
```
这意味着：**Terraform 只在创建时设置这些值，创建后无论这些值变成什么，Terraform 都视而不见。**

## 4. 标准操作流程 (SOP)

### 场景 A：添加新服务 (Add New Service)

1.  **Terraform 定义**：
    在 `terraform/netbox-integration/` 下创建或修改 `.tf` 文件，定义新的 VM、Interface、IP 和 Service。
    ```bash
    terraform apply
    ```
    *此时 Netbox 里会出现新的 VM，但硬件配置可能只是默认值。*

2.  **Ansible 配置**：
    在 `ansible/inventory/` 中添加主机，并配置 `netbox_name`（如果 Inventory 名字和 Netbox 名字不一致）。
    ```yaml
    # ansible/inventory/pve_lxc/new_service.yml
    new_service:
      ansible_host: 192.168.1.x
      netbox_name: new-service-name
    ```

3.  **Ansible 同步**：
    运行同步 Playbook，补全硬件信息。
    ```bash
    ansible-playbook ansible/playbooks/sync-netbox.yml
    ```
    *此时 Netbox 里的 VM 信息变更为真实值。*

### 场景 B：下线服务 (Decommission Service)

1.  **Terraform 删除**：
    在 `terraform/netbox-integration/` 下删除对应的资源代码。
    ```bash
    terraform apply
    ```
    *Terraform 会自动从 Netbox 中删除该 VM 及其所有关联数据（IP、接口、服务）。*

2.  **Ansible 清理**：
    从 `ansible/inventory/` 中删除对应的主机文件。

## 5. 常见问题与排错

*   **报错 "This field is required"**：
    *   通常是因为 Ansible 试图更新一个不存在的设备，或者把 VM 当成了物理 Device 更新。
    *   **检查**：确保 `ansible/roles/netbox_sync` 里的 `when: ansible_virtualization_role` 判断逻辑正确。

*   **报错 "A virtual machine must be assigned to a site/cluster"**：
    *   通常是因为 Ansible 里的主机名 (`inventory_hostname`) 和 Netbox 里的名字不匹配，导致 Ansible 以为要创建一个新 VM。
    *   **修复**：在 Inventory 里设置 `netbox_name` 变量，使其与 Terraform 定义的名字一致。

*   **OCI/云主机报错**：
    *   如果云主机没有在 Netbox (Terraform) 中定义，Ansible 同步会失败。
    *   **修复**：在 `sync-netbox.yml` 的 `hosts` 范围中排除云主机，只同步 HomeLab 资源。
