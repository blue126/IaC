# 混合 IaC 工作流：Terraform 与 Ansible 协同管理 Netbox

**日期**: 2025-12-04
**背景**: 我们希望实现 Netbox 数据的自动化填充，同时利用 Terraform 的状态管理和 Ansible 的动态发现能力。

## 1. 核心挑战：状态冲突

在 Infrastructure as Code (IaC) 中，通常只有一个 "Source of Truth" (真理来源)。
*   **Terraform** 认为代码是真理。
*   **Ansible** (Gather Facts) 认为运行时状态是真理。

当两者都试图更新同一个系统（Netbox）时，会发生冲突。例如：
1.  Terraform 定义内存为 `4GB`。
2.  Ansible 发现实际可用内存为 `3.9GB` 并更新 Netbox。
3.  Terraform 下次运行时会强制把 Netbox 改回 `4GB`。

## 2. 解决方案：Lifecycle Management

我们采用了 **"Lifecycle vs. Enrichment"** 的分层策略：

### Terraform (骨架)
负责资源的**创建与销毁**。
*   创建 VM 对象
*   分配静态 IP
*   定义服务端口

为了避免冲突，我们在 Terraform 资源中使用了 `lifecycle` 块：
```hcl
resource "netbox_virtual_machine" "example" {
  # ...
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
这告诉 Terraform：**“只管生，不管养”**。创建后，这些字段的变化由其他工具（Ansible）负责。

### Ansible (血肉)
负责资源的**信息补全**。
*   使用 `netbox.netbox` Collection。
*   通过 `gather_facts: yes` 收集真实硬件信息。
*   将 Serial, Asset Tag, 真实 Disk Usage 更新到 Netbox。

## 3. 实施细节

*   **Ansible Role**: `netbox-sync`
    *   逻辑：判断是物理机还是虚拟机，分别调用 `netbox_device` 或 `netbox_virtual_machine` 模块。
    *   技巧：使用 `default(omit)` 处理缺失字段，使用 Jinja2 过滤器处理磁盘大小计算。
*   **Playbook**: `sync-netbox.yml`
    *   范围：`hosts: pve_lxc:pve_vms:proxmox_cluster` (排除云主机)。

## 4. 价值

这种混合模式结合了：
1.  **Terraform 的严谨**：保证了基础设施的基线配置和生命周期管理。
2.  **Ansible 的灵活**：保证了 CMDB (Netbox) 里的数据是真实、实时的，而不是纸上谈兵。
