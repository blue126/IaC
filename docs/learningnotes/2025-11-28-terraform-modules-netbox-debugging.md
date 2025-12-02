# Terraform 模块化重构、Netbox 部署与 Cloud-Init 深度调试

**日期:** 2025-11-28
**标签:** Terraform, Proxmox, Cloud-Init, Ansible, Netbox, Debugging

## 1. 核心概念定义 (Concepts)

在本次实践中，我们接触并应用了以下关键技术概念：

*   **Terraform Modules (模块)**:
    *   **定义**: Terraform 配置的容器，用于封装一组相关的资源。
    *   **作用**: 类似于编程中的“函数”或“类”。我们将通用的 VM 配置逻辑（如 CPU、内存、磁盘、网络）封装在 `modules/proxmox-vm` 中，然后在 `environments/proxmox` 中多次调用它。这极大地提高了代码的复用性和可维护性。
*   **Source of Truth (SoT, 单一事实来源)**:
    *   **定义**: 在基础设施管理中，指存储所有资产（IP、VM、机架位置等）权威数据的系统。
    *   **应用**: 我们部署 **Netbox** 作为 SoT。理想流程是：Terraform 从 Netbox 获取 IP -> 创建 VM -> 将 VM 信息写回 Netbox。
*   **Cloud-Init**:
    *   **定义**: 用于云实例初始化的行业标准多发行版方法。它在第一次启动时运行，用于设置主机名、SSH 密钥、用户、网络配置等。
    *   **应用**: 我们通过 Terraform 的 `ciuser`, `sshkeys` 参数将配置传递给 Proxmox，Proxmox 生成 ISO 挂载给 VM，Cloud-Init 读取并应用这些配置。
*   **QEMU Guest Agent (QGA)**:
    *   **定义**: 运行在虚拟机内部的一个守护进程，用于辅助宿主机（Proxmox）管理 VM。
    *   **作用**: 允许 Proxmox 正确执行关机/重启（而不是强制断电），冻结文件系统以进行备份，以及获取 VM 内部的 IP 地址。
*   **UEFI (OVMF) & Q35**:
    *   **定义**: 现代虚拟机的固件和芯片组架构。
        *   **UEFI (OVMF)**: 替代传统的 BIOS (SeaBIOS)，支持更大的磁盘 (>2TB) 和安全启动。
        *   **Q35**: 模拟较新的 PCIe 芯片组（相对于老旧的 i440fx），提供更好的 PCIe 直通支持和性能。
    *   **注意**: 切换到 Q35/UEFI 后，传统的 IDE 总线可能不再被识别，需要将 Cloud-Init 驱动器挂载到 SCSI 总线上。

## 2. 架构演进 (Architecture Evolution)

### 2.1 模块化重构
我们将原本单文件的 `sandbox` 实验环境重构为了标准的模块化结构：
*   `terraform/modules/proxmox-vm/`: 定义了通用的 VM 蓝图。
*   `terraform/proxmox/`: 定义了具体的环境（Environment），在此处实例化 Netbox VM。

### 2.2 模板策略："Baking In" (预制)
我们改变了策略，不再依赖 Cloud-Init 在运行时安装所有东西，而是使用 Ansible (`virt-customize`) 将核心组件**预制**到模板中：
*   **预装 QEMU Guest Agent**: 避免了 Terraform 等待 Agent 启动的竞态条件。
*   **预配 GRUB 串口控制台**: 确保 `qm terminal` 和 xterm.js 控制台开箱即用。

## 3. 遇到的问题与解决方案 (Troubleshooting)

本次部署 Netbox VM 过程中，我们解决了一系列深层次的集成问题：

### A. "Unused Disk" 错误 (磁盘无法收缩)
*   **现象**: Terraform 创建 VM 后，磁盘显示为 "Unused0"，VM 无法启动。
*   **原因**: 模板的基础镜像磁盘大小为 50GB，但我们在 Terraform 中请求创建一个 20GB 的 VM。Proxmox (QEMU) 不支持在克隆时**缩小**磁盘。
*   **解决**: 修改 Ansible 变量 `vm_template_disk_size` 为 20GB，重建模板。**原则：模板磁盘应小于或等于目标 VM 磁盘。**

### B. 网络启动失败 (Machine ID 冲突)
*   **现象**: VM 启动后无网络，日志显示 `failed to start systemd-network`。
*   **原因**: Ubuntu 24.04 的模板中包含了一个生成的 `/etc/machine-id`。克隆出的所有 VM 拥有相同的 Machine ID，导致 DHCP 获取 IP 失败或 Netplan 冲突。
*   **解决**: 在制作模板时执行 `truncate -s 0 /etc/machine-id`。这会强制 Linux 在首次启动时生成一个新的、唯一的 Machine ID。

### C. Cloud-Init 驱动器未检测到 (UEFI/Q35 兼容性)
*   **现象**: 切换到 UEFI/Q35 后，Cloud-Init 不运行，`lsblk` 看不到 Cloud-Init 盘。
*   **原因**: 在 Q35 架构下，Linux 内核可能无法识别默认挂载在 `ide2` 总线上的 Cloud-Init 盘。
*   **解决**: 修改 Terraform 模块，将 Cloud-Init 盘挂载到 `scsi1` 总线（`type = "cloudinit", slot = "scsi1"`）。

### D. Hostname 与 SSH Key 注入失败
*   **现象**: 主机名一直是 `ubuntu`，SSH Key 无法注入。
*   **原因**: 使用自定义 Snippet (`cicustom`) 时，如果配置不当，会覆盖或忽略 Proxmox 传递的元数据。且 Snippet 文件维护成本高。
*   **解决**: 弃用 `cicustom`，重构 Terraform 模块使用**原生参数** (`ciuser`, `sshkeys`)。这样 Terraform 可以直接动态注入主机名和密钥，更加稳定。

## 4. 关键问答 (Q&A)

**Q: Hostname 只能在 Cloud-Init 文件里设置吗？不能在 Terraform 声明吗？**
**A:** 不，完全可以在 Terraform 中声明。事实上，使用 Terraform 的 `name` 属性配合原生的 Cloud-Init 参数是最佳实践。之前失败是因为我们混用了自定义 Snippet，导致 Cloud-Init 忽略了 Terraform 传来的名字。重构为原生参数后，`name = "netbox"` 即可自动生效。


**Q: 我们是否一定需要指定 Cloud-Init 文件？**
**A:** 不一定。对于基础配置（用户、密码、SSH Key、IP），直接使用 Terraform 的 `proxmox_vm_qemu` 资源提供的参数（`ciuser`, `sshkeys`, `ipconfig0`）是最简单且推荐的方式。只有当需要非常复杂的初始化逻辑（如 `runcmd`, `write_files`）时，才需要使用自定义 Snippet。

## 5. 下一步计划
*   利用 Ansible 部署 Netbox 应用容器。
*   配置 Netbox 作为动态 Inventory 源，实现 Terraform 和 Ansible 的闭环管理。
