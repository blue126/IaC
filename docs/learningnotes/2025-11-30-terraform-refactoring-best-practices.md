 # 学习笔记：Terraform 代码重构与状态对齐 (2025-11-30)

## 1. 背景与目标
为了提高基础设施即代码 (IaC) 的可维护性和扩展性，我们将原本单体式的 Terraform 配置进行了重构。目标是将通用的 VM 配置逻辑提取为模块，并将各个 VM 的定义分散到独立的文件中，同时确保 Terraform 状态与现有的 Proxmox 基础设施保持一致。

## 2. 重构内容 (Refactoring)

### 2.1 模块化 (Modularization)
*   **创建模块**: 新建 `terraform/modules/proxmox-vm` 目录。
*   **逻辑封装**: 将 `proxmox_vm_qemu` 资源的通用配置（如网络、磁盘、Cloud-Init）封装在模块的 `main.tf` 中。
*   **变量抽象**: 通过 `variables.tf` 暴露必要的配置项（如 `vm_name`, `vmid`, `cores`, `memory`, `disk_size` 等），屏蔽底层细节。
*   **特殊处理**: 在模块中增加了对 `efidisk` 的动态处理逻辑，支持为 OVMF BIOS 的 VM 指定独立的 EFI 磁盘存储池 (`efidisk_storage`)。

### 2.2 资源拆分 (Resource Splitting)
*   **去单体化**: 将原本集中在 `main.tf` 中的多个 VM 资源定义拆分。
*   **独立文件**: 为每个 VM 创建独立文件：
    *   `samba.tf`: 定义 Samba 文件服务器。
    *   `immich.tf`: 定义 Immich 照片服务器。
    *   `netbox.tf`: 定义 Netbox IPAM 服务器。
*   **优势**: 提高了代码的可读性，修改某个 VM 的配置时不会影响到其他资源，降低了“爆炸半径”。

## 3. 状态对齐 (State Alignment)

### 3.1 导入现有资源 (Import)
*   **问题**: 重构代码后，Terraform State 中并没有这些新定义的模块资源，直接 `apply` 会导致 Terraform 试图创建重复的 VM。
*   **解决**: 使用 `terraform import` 命令将现有的 Proxmox VM 导入到新的 Terraform 资源地址中。
    ```bash
    terraform import module.samba.proxmox_vm_qemu.vm pve0/qemu/102
    ```

### 3.2 解决配置漂移 (Drift Detection)
*   **磁盘大小不一致**: 发现 Samba VM 的实际磁盘是 50G，而代码中定义为 64G。通过修改代码 (`disk_size = "50G"`) 匹配实际状态，避免了破坏性的磁盘重建。
*   **EFI 存储池灵活配置**: 考虑到某些 VM 的 EFI 磁盘可能位于不同的存储池（虽然 Immich 最终确认在 `vmdata`），我们在模块中新增了 `efidisk_storage` 变量以支持这种灵活性，增强了模块的通用性。
*   **忽略非关键变更**: 针对 `full_clone` 和 `efidisk` 字段，我们使用了 `lifecycle { ignore_changes }` (详见 4.4) 来防止 Provider 误报导致的强制重建。

## 4. 关键概念定义 (Key Concepts)

### 4.1 Root Module vs Child Module
*   **Root Module (根模块)**: 运行 `terraform apply` 的目录 (如 `terraform/proxmox`)。它包含具体的资源实例化代码。
*   **Child Module (子模块)**: 被根模块调用的封装好的配置包 (如 `terraform/modules/proxmox-vm`)。它定义了“如何创建资源”，通常包含 `main.tf`, `variables.tf`, `outputs.tf`。

### 4.2 Terraform Import
Terraform 的一种机制，用于将非 Terraform 管理的（或状态丢失的）现有基础设施资源纳入 Terraform 的状态管理 (`terraform.tfstate`) 中，而不进行创建或修改操作。

### 4.3 Configuration Drift (配置漂移)
指基础设施的实际状态与 IaC 代码中定义的状态不一致的情况。这可能是由于手动修改了基础设施，或者代码定义有误。解决漂移通常需要修改代码以匹配实际状态，或者通过 `apply` 强制覆盖实际状态。

### 4.4 Lifecycle Ignore Changes (忽略变更)
*   **定义**: Terraform 的 `lifecycle { ignore_changes = [...] }` 元参数用于告诉 Terraform：“即使代码中的配置与实际状态不一致，也不要尝试去修改它”。
*   **作用**: 当某些资源属性由外部系统管理，或者 Provider 存在 Bug 导致误报变更时，使用此功能可以防止 Terraform 产生不必要的“修改”或“重建”计划，从而保护基础设施的稳定性。

## 5. 总结
重构 IaC 代码不仅仅是移动文件，更重要的是**保持状态的连续性**。在处理有状态的资源（如 VM、数据库）时，必须极其小心地对比 `terraform plan` 的输出，确保没有意外的 `destroy` 操作。通过模块化和精细的状态管理，我们成功地将遗留的 VM 纳入了现代化的 Terraform 管理体系。
