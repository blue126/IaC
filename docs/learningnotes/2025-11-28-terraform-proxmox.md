# Terraform Learning Notes - Proxmox Deployment

**Date**: 2025-11-28
**Topic**: Infrastructure as Code (IaC) with Terraform & Proxmox

## 1. Core Concepts (核心概念)

在此次学习中，我们涉及了以下 Terraform 和 Proxmox 的核心概念：

*   **Terraform Provider (提供者)**:
    *   *定义*: Terraform 的插件，负责与特定的 API 进行交互（如 AWS, Azure, Proxmox）。
    *   *场景*: 我们使用了 `telmate/proxmox` Provider 来通过 API 控制 Proxmox 服务器。

*   **Resource (资源)**:
    *   *定义*: Terraform 的基本构建块，描述了一个具体的基础设施对象。
    *   *场景*: `proxmox_vm_qemu` 是一个资源，代表一台虚拟机。

*   **State (状态)**:
    *   *定义*: Terraform 的“数据库”（`terraform.tfstate`），用于记录真实世界的资源与代码配置的对应关系。
    *   *重要性*: 它是 Terraform 的记忆。**永远不要手动修改此文件**。它让 Terraform 知道哪些资源需要创建、更新或销毁。

*   **Cloud-Init**:
    *   *定义*: 云计算领域的工业标准，用于在实例首次启动时进行初始化（设置主机名、用户密钥、安装软件等）。
    *   *场景*: 我们利用它来解决 Proxmox 模板中没有预装 Agent 的问题，并设置默认用户 `ubuntu`。

*   **Snippet (Proxmox)**:
    *   *定义*: 存储在 Proxmox 宿主机特定目录（如 `/var/lib/vz/snippets/`）下的文件，可被 VM 引用。
    *   *场景*: 由于 `telmate` Provider 不支持直接在代码里写 Cloud-Init YAML，我们需要将配置保存为 Snippet 文件供 `cicustom` 参数调用。

*   **Module (模块)**:
    *   *定义*: 一组资源的容器，相当于编程中的“函数”或“类”。它是可复用的“模具”。
    *   *场景*: 我们将 `sandbox` 中的代码重构为了 `modules/proxmox-vm`。

*   **Environment (环境)**:
    *   *定义*: 模块的具体实例化（如 Dev, Staging, Prod）。它是用模具生产出来的“产品”。
    *   *场景*: 我们创建了 `environments/dev` 来调用模块。

### 1.1 Terraform Internals (内部机制文件)
这些是 Terraform 自动生成或管理的关键文件：

*   **`.terraform/` (文件夹)**:
    *   *定义*: Terraform 的“工具箱”。存放下载的 Provider 插件和 Modules。
    *   *注意*: 不需要提交到 Git。

*   **`terraform.tfstate`**:
    *   *定义*: Terraform 的“记账本”或“大脑”。记录了代码资源与真实基础设施的映射关系。
    *   *重要性*: **绝对不要手动修改**。它是 Terraform 工作的基石。

*   **`.terraform.lock.hcl`**:
    *   *定义*: “版本锁”。记录了当前使用的 Provider 的确切版本和哈希值。
    *   *作用*: 确保团队协作时每个人使用的插件版本完全一致。需要提交到 Git。

### 1.2 Project Files (项目文件结构)
我们在项目中创建的标准 Terraform 文件：

*   **`main.tf`**:
    *   *作用*: **主逻辑入口**。定义资源（Resource）或调用模块（Module）。

*   **`variables.tf`**:
    *   *作用*: **输入定义**。声明项目接受哪些参数（如 `vm_name`, `cores`），相当于函数的参数列表。

*   **`outputs.tf`**:
    *   *作用*: **输出定义**。执行完成后打印给用户看的信息（如 `vm_ip`），相当于函数的返回值。

*   **`provider.tf`**:
    *   *作用*: **插件配置**。配置 Provider 的认证信息（如 Proxmox URL, User, Password）。

*   **`terraform.tfvars`**:
    *   *作用*: **参数赋值**。给 `variables.tf` 中定义的变量赋予具体的值（如 `cores = 4`）。

### 1.1 Terraform Internals (内部机制文件)
这些是 Terraform 自动生成或管理的关键文件：

*   **`.terraform/` (文件夹)**:
    *   *定义*: Terraform 的“工具箱”。存放下载的 Provider 插件和 Modules。
    *   *注意*: 不需要提交到 Git。

*   **`terraform.tfstate`**:
    *   *定义*: Terraform 的“记账本”或“大脑”。记录了代码资源与真实基础设施的映射关系。
    *   *重要性*: **绝对不要手动修改**。它是 Terraform 工作的基石。

*   **`.terraform.lock.hcl`**:
    *   *定义*: “版本锁”。记录了当前使用的 Provider 的确切版本和哈希值。
    *   *作用*: 确保团队协作时每个人使用的插件版本完全一致。需要提交到 Git。

### 1.2 Project Files (项目文件结构)
我们在项目中创建的标准 Terraform 文件：

*   **`main.tf`**:
    *   *作用*: **主逻辑入口**。定义资源（Resource）或调用模块（Module）。

*   **`variables.tf`**:
    *   *作用*: **输入定义**。声明项目接受哪些参数（如 `vm_name`, `cores`），相当于函数的参数列表。

*   **`outputs.tf`**:
    *   *作用*: **输出定义**。执行完成后打印给用户看的信息（如 `vm_ip`），相当于函数的返回值。

*   **`provider.tf`**:
    *   *作用*: **插件配置**。配置 Provider 的认证信息（如 Proxmox URL, User, Password）。

*   **`terraform.tfvars`**:
    *   *作用*: **参数赋值**。给 `variables.tf` 中定义的变量赋予具体的值（如 `cores = 4`）。

## 2. Journey & Troubleshooting (实战与排错)

### Phase 1: The Sandbox (单文件模式)
我们首先在一个文件中尝试跑通 VM 的创建。

*   **问题 1: Permission Error (`VM.Monitor`)**
    *   *原因*: 使用的 Provider 版本过旧，与 Proxmox 8 不兼容。
    *   *解决*: 将 `telmate/proxmox` 升级到 `3.0.2-rc05`。

*   **问题 2: Storage & Disk Errors**
    *   *原因*: 代码中硬编码了 `local-lvm`，但宿主机使用的是 ZFS (`local-zfs`)。同时磁盘 `type` 设置为了错误的 `scsi`。
    *   *解决*: 将存储池参数化并设为 `local-zfs`，将磁盘类型修正为 `disk`。

*   **问题 3: Cloud-Init & QEMU Agent**
    *   *现象*: VM 创建成功，但 Proxmox 无法获取 IP，Terraform 卡在 Creating 状态。
    *   *原因*: 官方 Ubuntu 模板未预装 `qemu-guest-agent`。Terraform 的 `agent = 1` 只是开启了宿主机端的通道，并没有安装虚拟机里的软件。
    *   *解决*: 使用 `cicustom` 参数引用宿主机上的 Snippet (`cloud-init-ubuntu2404.yml`)，在 User Data 中添加 `packages: [qemu-guest-agent]`。

*   **问题 4: "Cloud-init enabled but no IP config"**
    *   *原因*: 在清理代码时意外删除了 `ipconfig0`。
    *   *解决*: 恢复 `ipconfig0 = "ip=dhcp"`，告诉 Cloud-Init 如何配置网络。

### Phase 2: Refactoring to Modules (模块化)
我们将代码从“硬编码”重构为“可复用架构”。

*   **架构设计**:
    *   **Modules (`modules/proxmox-vm`)**: 封装逻辑。通过 `variables.tf` 暴露接口（如 CPU 核数、内存），隐藏底层细节（如 EFI 磁盘配置）。
    *   **Environments (`environments/dev`)**: 配置参数。调用模块并传入具体的值。

*   **关键经验**:
    *   **封装 (Encapsulation)**: 使用者不需要关心底层实现，只需关心业务参数。
    *   **输出传递 (Output Propagation)**: 模块内部的 Output（如 `vm_id`）不会自动穿透。如果需要在最外层看到它，必须在 Environment 的 `main.tf` 中再次定义 `output`。

## 3. Q&A Summary (问答精华)

*   **Q: 我们能不能直接在 `main.tf` 里写 Cloud-Init 的 YAML 内容？**
    *   **A**: 不行。`telmate/proxmox` Provider 限制了必须使用文件路径（Snippet）。

*   **Q: 如果使用了 `cicustom`，之前的 `ciuser` 和 `cipassword` 还有效吗？**
    *   **A**: 无效。`cicustom` 会完全覆盖默认生成的 User Data。所有的用户和密码配置必须在你的 YAML 文件里定义。

*   **Q: 为什么部署成功了却没看到 VM ID？**
    *   **A**: 因为 Terraform 的 Output 不具有传递性。模块输出了 ID，但我们在环境层的 `main.tf` 里忘记把这个值“接出来”打印到屏幕上了。

## 4. Essential Commands (常用指令)

我们在实战中使用了以下 Terraform 指令：

*   **`terraform init`**
    *   *作用*: 初始化工作目录。下载 Provider 插件，配置 Backend，加载 Modules。
    *   *场景*: 在创建新环境（如 `environments/dev`）或修改了 Module 来源后必须执行。

*   **`terraform plan`**
    *   *作用*: 预览变更。对比代码与当前状态，生成执行计划。
    *   *场景*: 在执行修改前，先看一眼会发生什么（比如是 Update 还是 Destroy）。

*   **`terraform apply`**
    *   *作用*: 应用变更。开始创建或修改资源。
    *   *参数*: `-auto-approve` (跳过交互式确认，直接执行。慎用！但在自动化脚本或确信无误时很方便)。

*   **`terraform destroy`**
    *   *作用*: 销毁资源。删除该环境管理的所有基础设施。
    *   *参数*: `-auto-approve` (跳过确认)。

*   **`terraform refresh`**
    *   *作用*: 刷新状态。重新查询 API 获取最新的资源状态，更新 `terraform.tfstate`。
    *   *场景*: 当我们修改了 `outputs` 但不想触发资源变更，只想看最新的输出值时使用。

## 5. Project References (项目引用)

本次学习涉及的代码位于以下目录：

*   **Module (模具)**: [`terraform/modules/proxmox-vm`](../../terraform/modules/proxmox-vm)
*   **Module (模具)**: [`terraform/modules/proxmox-vm`](../../terraform/modules/proxmox-vm)
*   **Environment (环境)**: [`terraform/proxmox`](../../terraform/proxmox)
*   **Sandbox (废弃/参考)**: [`terraform/proxmox/sandbox`](../../terraform/proxmox/sandbox)

---
*Generated by Antigravity Agent for User Will*
