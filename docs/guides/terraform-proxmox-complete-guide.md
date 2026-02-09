# Terraform + Proxmox 完整综合指南

## 文档元数据

**编译时间**: 2026-01-30
**基于学习笔记**:
- `2025-11-28-terraform-proxmox.md` - 核心概念与基础配置
- `2025-11-28-terraform-modules-netbox-debugging.md` - 模块化重构与部署实践
- `2025-11-30-terraform-refactoring-best-practices.md` - 代码重构与状态管理
- `2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md` - 故障排查深度分析
- `2026-01-28-ssh-key-management-strategy.md` - SSH密钥管理策略

**适用范围**: Terraform 0.12+ 与 Proxmox 8.x，使用 `telmate/proxmox` Provider 3.0+

---

## 目录

1. [简介与架构概览](#简介与架构概览)
2. [核心概念基础](#核心概念基础)
3. [Terraform 项目结构](#terraform-项目结构)
4. [基础配置与初始化](#基础配置与初始化)
5. [模块化设计最佳实践](#模块化设计最佳实践)
6. [Cloud-Init 与虚拟机初始化](#cloud-init-与虚拟机初始化)
7. [状态管理与配置漂移](#状态管理与配置漂移)
8. [常见问题与故障排查](#常见问题与故障排查)
9. [SSH 密钥管理策略](#ssh-密钥管理策略)
10. [参考资源与命令速查](#参考资源与命令速查)

---

## 简介与架构概览

本指南整合了在 Proxmox 环境中使用 Terraform 进行基础设施自动化的完整知识体系。通过模块化设计、最佳实践和深度故障排查经验，提供从零搭建到生产级别的完整路线图。

### 核心价值主张

| 方面 | 优势 |
|------|------|
| **可复用性** | 使用模块封装通用配置，支持多个环境快速部署 |
| **幂等性** | Cloud-Init 与 Terraform 结合，确保配置稳定一致 |
| **版本控制** | IaC 代码纳入 Git，实现基础设施版本管理 |
| **可观测性** | 状态文件 (`terraform.tfstate`) 精确追踪资源映射 |

---

## 核心概念基础

### 1.1 Terraform 核心组件

#### Terraform Provider (提供者)
- **定义**: Terraform 与特定 API 交互的插件系统
- **应用场景**: `telmate/proxmox` Provider 负责与 Proxmox API 通信
- **版本建议**: 使用 3.0+ 版本以支持 Proxmox 8 的新特性

#### Resource (资源)
- **定义**: Terraform 管理的基础设施对象，是配置的最小单元
- **例子**: `proxmox_vm_qemu` 代表一台虚拟机，`proxmox_lxc` 代表 LXC 容器
- **特点**: 资源生命周期由 Terraform 全程追踪

#### State (状态)
- **定义**: Terraform 的"大脑"和"记账本"（文件: `terraform.tfstate`）
- **作用**: 记录代码配置与真实基础设施的映射关系
- **重要性**: 是 Terraform 的核心依据，**绝对不要手动编辑**
- **并发安全**: 生产环境建议使用远程状态后端（如 S3、Consul）

#### Module (模块)
- **定义**: 一组相关资源的可复用容器，类似编程中的"函数"或"类"
- **层次**:
  - **Root Module**: 执行 `terraform apply` 的目录
  - **Child Module**: 被 Root Module 调用的模块包

#### Cloud-Init
- **定义**: 云计算行业标准的实例初始化系统
- **执行时机**: VM 首次启动时运行
- **功能**: 设置主机名、注入 SSH 密钥、配置网络、安装软件包等

### 1.2 关键概念深度解读

#### Configuration Drift (配置漂移)
- **现象**: 基础设施实际状态与 IaC 代码不一致
- **原因**: 手动修改、外部系统（Ansible）变更、Provider Bug 等
- **检测**: 运行 `terraform plan` 查看是否有非预期变更
- **解决**: 修改代码匹配实际状态，或使用 `lifecycle { ignore_changes }` 忽略特定字段

#### UEFI/Q35 架构细节
- **UEFI (OVMF)**: 现代虚拟机固件，替代传统 BIOS
- **Q35**: 新型 PCIe 芯片组架构，性能优于 i440fx
- **兼容性问题**: Q35 下 IDE 设备识别问题，需将 Cloud-Init 盘挂载到 SCSI 总线
- **磁盘大小限制**: UEFI 支持 >2TB 磁盘，而 BIOS 受限于 2TB

#### QEMU Guest Agent (QGA)
- **定义**: 运行在 VM 内部的守护进程
- **作用**:
  - 允许 Proxmox 正确执行 Graceful Shutdown（而非强制断电）
  - 辅助文件系统冻结进行备份
  - **关键**: 使 Terraform 能通过 Agent 获取 VM 内部 IP 地址
- **安装方式**:
  - 预制到模板中（最佳实践）
  - 或通过 Cloud-Init 动态安装

---

## Terraform 项目结构

### 2.1 标准项目布局

```
terraform/
├── modules/
│   └── proxmox-vm/              # 可复用 VM 模块
│       ├── main.tf              # 资源定义
│       ├── variables.tf          # 输入参数
│       ├── outputs.tf            # 输出值
│       └── versions.tf           # Provider 版本约束
├── proxmox/                      # 根模块（执行目录）
│   ├── main.tf                   # 资源实例化
│   ├── variables.tf              # 环境级输入
│   ├── outputs.tf                # 环境级输出
│   ├── provider.tf               # Provider 配置
│   ├── terraform.tfvars          # 参数赋值（不提交 Git）
│   └── .terraform/               # 自动生成（不提交 Git）
└── .terraform.lock.hcl           # 版本锁（必须提交 Git）
```

### 2.2 关键文件说明

#### `main.tf` - 主逻辑入口
```hcl
# 根模块中：实例化模块或定义资源
module "samba" {
  source = "../modules/proxmox-vm"
  vm_name = "samba"
  vmid = 102
  cores = 4
  memory = 8192
  # ... 更多参数
}

# 或在模块中：定义资源
resource "proxmox_vm_qemu" "vm" {
  name = var.vm_name
  vmid = var.vmid
  # ... 资源配置
}
```

#### `variables.tf` - 输入参数定义
```hcl
variable "vm_name" {
  type = string
  description = "虚拟机名称"
}

variable "cores" {
  type = number
  default = 2
  description = "CPU 核心数"
}
```

#### `outputs.tf` - 输出值定义
```hcl
# 模块中定义的输出不自动穿透
# 必须在调用方的 main.tf 再次定义才能使用
output "vm_id" {
  value = module.samba.vm_id
  description = "虚拟机 ID"
}
```

#### `provider.tf` - Provider 认证配置
```hcl
terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
      version = "~> 3.0"
    }
  }
}

provider "proxmox" {
  pm_api_url = var.proxmox_api_url
  pm_user = var.proxmox_user
  pm_password = var.proxmox_password
  pm_tls_insecure = true  # 仅用于自签名证书
}
```

#### `terraform.tfvars` - 参数赋值（Git 忽略）
```hcl
proxmox_api_url = "https://pve.example.com:8006/api2/json"
proxmox_user = "terraform@pam"
proxmox_password = "your-password"

vm_cores = 4
vm_memory = 8192
vm_disk_size = "50G"
```

#### `.terraform.lock.hcl` - 版本锁（必须提交）
- 记录下载的 Provider 确切版本和哈希值
- 确保团队协作时版本一致
- 自动生成，不手动编辑

#### `.terraform/` 目录（Git 忽略）
- 存放下载的 Provider 插件
- 存放加载的模块
- 自动生成和维护

---

## 基础配置与初始化

### 3.1 环境准备

#### 前置条件
- Proxmox VE 8.x 以上版本
- Terraform 0.12 或更新版本
- 具有 API 权限的 Proxmox 账户

#### 创建 Proxmox API 用户

```bash
# SSH 连接 Proxmox
ssh root@pve.example.com

# 创建 Terraform 用户
pveum useradd terraform@pam -password

# 授予必要权限（最小化原则）
pveum acl modify / --users terraform@pam --roles PVEAdmin
```

#### Terraform 初始化

```bash
# 进入根模块目录
cd terraform/proxmox

# 初始化：下载 Provider、加载模块、配置 Backend
terraform init

# 验证配置正确性
terraform validate

# 格式化代码
terraform fmt -recursive
```

### 3.2 第一个 VM 部署

#### 最小化 Terraform 配置示例

**provider.tf**
```hcl
terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
      version = "~> 3.0"
    }
  }
}

provider "proxmox" {
  pm_api_url = var.proxmox_api_url
  pm_user = var.proxmox_user
  pm_password = var.proxmox_password
  pm_tls_insecure = true
}
```

**variables.tf**
```hcl
variable "proxmox_api_url" {
  type = string
}

variable "proxmox_user" {
  type = string
}

variable "proxmox_password" {
  type = string
  sensitive = true
}

variable "vm_name" {
  type = string
  default = "test-vm"
}

variable "vmid" {
  type = number
  default = 100
}

variable "target_node" {
  type = string
  default = "pve0"
}

variable "clone_template" {
  type = string
  default = "ubuntu-24.04-template"
}

variable "cores" {
  type = number
  default = 2
}

variable "memory" {
  type = number
  default = 4096
}

variable "disk_size" {
  type = string
  default = "50G"
}

variable "storage_pool" {
  type = string
  default = "local-zfs"
}
```

**main.tf**
```hcl
resource "proxmox_vm_qemu" "test" {
  name = var.vm_name
  vmid = var.vmid
  target_node = var.target_node

  clone = var.clone_template
  full_clone = true

  cores = var.cores
  sockets = 1
  memory = var.memory

  # 网络配置：DHCP
  ipconfig0 = "ip=dhcp"

  # 磁盘配置
  disk {
    slot = 0
    size = var.disk_size
    type = "disk"
    storage = var.storage_pool
  }

  # Cloud-Init 用户配置
  ciuser = "ubuntu"
  cipassword = "your-password"  # 应使用密钥而非密码
  sshkeys = file("~/.ssh/id_rsa.pub")

  # QEMU Guest Agent（用于获取 IP）
  agent = 1

  # 启动顺序
  boot = "order=scsi0;ide2;net0"

  # 生命周期：忽略某些漂移
  lifecycle {
    ignore_changes = [unused_disk, efidisk]
  }
}
```

**outputs.tf**
```hcl
output "vm_ip" {
  value = proxmox_vm_qemu.test.default_ipv4_address
  description = "虚拟机 IP 地址"
}

output "vm_id" {
  value = proxmox_vm_qemu.test.vmid
  description = "虚拟机 ID"
}
```

**terraform.tfvars**
```hcl
proxmox_api_url = "https://192.168.1.50:8006/api2/json"
proxmox_user = "terraform@pam"
proxmox_password = "your-secure-password"

vm_name = "web-server-01"
vmid = 110
cores = 4
memory = 8192
disk_size = "100G"
storage_pool = "local-zfs"
```

#### 执行部署

```bash
# 1. 查看执行计划
terraform plan

# 2. 应用配置（需确认）
terraform apply

# 3. 跳过确认（自动化脚本）
terraform apply -auto-approve

# 4. 查看输出
terraform output
```

#### 验证结果

```bash
# 列出 Terraform 管理的所有资源
terraform state list

# 查看具体资源的详细状态
terraform state show 'proxmox_vm_qemu.test'

# 查看输出值
terraform output vm_ip
```

---

## 模块化设计最佳实践

### 4.1 模块化的核心原则

#### 职责分离
- **模块**: 定义"如何创建"（逻辑）
- **环境**: 定义"创建什么"（具体值）
- **模板**: 提供基础镜像和预配置

#### 接口设计
```
┌─────────────────────┐
│  Input Variables    │  <- 调用方传入参数
│  (variables.tf)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Module Logic       │  <- 模块内部资源定义
│  (main.tf)          │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Output Values      │  <- 返回结果给调用方
│  (outputs.tf)       │
└─────────────────────┘
```

### 4.2 Proxmox VM 模块详细示例

#### 模块目录结构
```
modules/proxmox-vm/
├── main.tf
├── variables.tf
├── outputs.tf
└── versions.tf
```

#### `modules/proxmox-vm/versions.tf`
```hcl
terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
      version = "~> 3.0"
    }
  }
}
```

#### `modules/proxmox-vm/variables.tf`
```hcl
variable "vm_name" {
  type = string
  description = "虚拟机名称"
}

variable "vmid" {
  type = number
  description = "虚拟机 ID（在 Proxmox 集群中唯一）"
}

variable "target_node" {
  type = string
  description = "目标 Proxmox 节点名称"
}

variable "clone_template" {
  type = string
  description = "克隆的模板名称"
}

variable "cores" {
  type = number
  default = 2
  description = "CPU 核心数"
}

variable "sockets" {
  type = number
  default = 1
  description = "CPU 插槽数"
}

variable "memory" {
  type = number
  default = 4096
  description = "内存大小（MB）"
}

variable "disk_size" {
  type = string
  default = "50G"
  description = "系统盘大小（支持 G 或 M 单位）"
}

variable "storage_pool" {
  type = string
  default = "local-zfs"
  description = "存储池名称（local-zfs, local-lvm 等）"
}

variable "efidisk_storage" {
  type = string
  default = "local-zfs"
  description = "EFI 磁盘存储池（UEFI 固件时需要）"
}

variable "ssh_key_pub" {
  type = string
  description = "注入虚拟机的公钥内容（从 ~/.ssh/id_rsa.pub 读取）"
}

variable "ip_config" {
  type = string
  default = "ip=dhcp"
  description = "网络配置（DHCP 或静态 IP）"
}

variable "bios_type" {
  type = string
  default = "ovmf"
  description = "BIOS 类型：seabios 或 ovmf（UEFI）"
  validation {
    condition = contains(["seabios", "ovmf"], var.bios_type)
    error_message = "bios_type 必须是 seabios 或 ovmf"
  }
}
```

#### `modules/proxmox-vm/main.tf`
```hcl
resource "proxmox_vm_qemu" "vm" {
  name = var.vm_name
  vmid = var.vmid
  target_node = var.target_node

  clone = var.clone_template
  full_clone = true

  # CPU 配置
  cores = var.cores
  sockets = var.sockets
  memory = var.memory

  # 网络配置
  ipconfig0 = var.ip_config

  # BIOS 选择
  bios = var.bios_type

  # 磁盘配置
  disk {
    slot = 0
    size = var.disk_size
    type = "disk"
    storage = var.storage_pool
  }

  # UEFI 时的 EFI 磁盘配置
  efidisk {
    efitype = "4m"
    storage = var.efidisk_storage
  }

  # Cloud-Init 用户和密钥
  ciuser = "ubuntu"
  sshkeys = var.ssh_key_pub

  # QEMU Guest Agent
  agent = 1

  # 启动顺序
  boot = "order=scsi0;ide2;net0"

  # Cloud-Init 磁盘位置（Q35 架构下需要 SCSI）
  cloudinit_cdrom_storage = var.storage_pool

  # 忽略无关的配置漂移
  lifecycle {
    ignore_changes = [unused_disk, efidisk, format, tags]
  }
}
```

#### `modules/proxmox-vm/outputs.tf`
```hcl
output "vm_id" {
  value = proxmox_vm_qemu.vm.vmid
  description = "虚拟机 ID"
}

output "vm_name" {
  value = proxmox_vm_qemu.vm.name
  description = "虚拟机名称"
}

output "vm_ip" {
  value = proxmox_vm_qemu.vm.default_ipv4_address
  description = "虚拟机 IP 地址（获取需要 QGA 运行）"
  depends_on = [proxmox_vm_qemu.vm]
}
```

### 4.3 环境配置调用模块

#### 根模块 `terraform/proxmox/main.tf`
```hcl
# 调用模块创建多个 VM
module "samba" {
  source = "../modules/proxmox-vm"

  vm_name = "samba"
  vmid = 102
  target_node = "pve0"
  clone_template = "ubuntu-24.04-template"

  cores = 4
  memory = 8192
  disk_size = "50G"
  storage_pool = "local-zfs"

  ssh_key_pub = file("${path.module}/../keys/terraform_rsa.pub")
  bios_type = "ovmf"
}

module "immich" {
  source = "../modules/proxmox-vm"

  vm_name = "immich"
  vmid = 103
  target_node = "pve0"
  clone_template = "ubuntu-24.04-template"

  cores = 8
  memory = 16384
  disk_size = "100G"
  storage_pool = "local-zfs"
  efidisk_storage = "vmdata"

  ssh_key_pub = file("${path.module}/../keys/terraform_rsa.pub")
  bios_type = "ovmf"
}

module "netbox" {
  source = "../modules/proxmox-vm"

  vm_name = "netbox"
  vmid = var.netbox_vmid
  target_node = var.netbox_node
  clone_template = var.netbox_template

  cores = var.netbox_cores
  memory = var.netbox_memory
  disk_size = var.netbox_disk_size
  storage_pool = var.storage_pool

  ssh_key_pub = file("${path.module}/../keys/terraform_rsa.pub")
  bios_type = "ovmf"
}
```

#### 根模块 `terraform/proxmox/outputs.tf`
```hcl
# 输出传递：模块内定义的输出必须在这里再次声明才能外部看到
output "samba_id" {
  value = module.samba.vm_id
}

output "samba_ip" {
  value = module.samba.vm_ip
}

output "immich_id" {
  value = module.immich.vm_id
}

output "immich_ip" {
  value = module.immich.vm_ip
}

output "netbox_id" {
  value = module.netbox.vm_id
}

output "netbox_ip" {
  value = module.netbox.vm_ip
}

# 汇总输出
output "all_vms" {
  value = {
    samba = {
      id = module.samba.vm_id
      ip = module.samba.vm_ip
    }
    immich = {
      id = module.immich.vm_id
      ip = module.immich.vm_ip
    }
    netbox = {
      id = module.netbox.vm_id
      ip = module.netbox.vm_ip
    }
  }
}
```

### 4.4 关键经验总结

#### 输出穿透问题
- **问题**: 模块内定义的 Output 不会自动对外暴露
- **解决**: 在调用方（Root Module）的 outputs.tf 中再次定义 Output，引用模块的输出
- **原因**: Terraform 设计为显式声明接口，避免隐式耦合

#### 变量参数化
- 所有硬编码值都应提取为变量
- 模块变量应具有有意义的默认值
- 使用 `validation` 块验证参数合法性

#### 模块化的复用性
- 同一模块可在多个环境中使用（dev, staging, prod）
- 版本化模块支持：`source = "git::https://...?ref=v1.0"`
- 私有模块注册表：企业级模块共享

---

## Cloud-Init 与虚拟机初始化

### 5.1 Cloud-Init 工作原理

#### 执行流程
```
VM 首次启动
    ↓
Cloud-Init 进程启动
    ↓
读取 Proxmox 生成的 NoCloud ISO（IDE2 或 SCSI）
    ↓
解析配置（用户、密钥、网络、软件包等）
    ↓
应用配置（创建用户、设置权限、启用服务）
    ↓
标记为 "已初始化"（防止再次运行）
```

#### 关键文件位置
```
VM 内部:
/etc/cloud/              # Cloud-Init 配置目录
/var/lib/cloud/          # Cloud-Init 运行时数据
/var/log/cloud-init.log  # Cloud-Init 日志（排错关键）

Proxmox 宿主机:
/var/lib/vz/snippets/    # Cloud-Init Snippet 文件存储位置
```

### 5.2 Terraform 中的 Cloud-Init 配置

#### 方式 1: 原生参数（推荐）

```hcl
resource "proxmox_vm_qemu" "vm" {
  # ... 其他配置

  # 基础用户配置
  ciuser = "ubuntu"
  cipassword = "initial-password"  # Cloud-Init 不建议注入密码，使用密钥

  # SSH 公钥注入（多个时用换行符分隔）
  sshkeys = var.ssh_key_pub

  # DHCP 网络配置
  ipconfig0 = "ip=dhcp"

  # 或静态 IP 配置
  ipconfig0 = "ip=192.168.1.100/24,gw=192.168.1.1"
  ipconfig1 = "ip=10.0.0.100/24"  # 第二块网卡
}
```

**优点**:
- Terraform 原生支持，无额外文件维护
- 参数可动态化，与变量紧密结合
- 非常稳定，不涉及文件依赖

#### 方式 2: 自定义 Snippet 文件（复杂初始化）

当需要执行复杂的初始化逻辑时（如软件包安装、文件配置、服务启用等），可使用 Cloud-Init YAML 格式的 Snippet：

**创建 Snippet 文件**: `/var/lib/vz/snippets/cloud-init-ubuntu.yaml`
```yaml
#cloud-config
hostname: webserver-01
fqdn: webserver-01.example.com

users:
  - name: ubuntu
    gecos: Ubuntu User
    groups: [adm, sudo]
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    shell: /bin/bash
    ssh_import_id: []  # 从 Terraform 传入的密钥覆盖此处

ssh_authorized_keys:
  - ssh-rsa AAAA... user@example.com

# 更新系统
package_upgrade: true

# 安装软件包
packages:
  - qemu-guest-agent
  - curl
  - wget
  - htop
  - git

# 启用 QEMU Guest Agent
runcmd:
  - systemctl enable qemu-guest-agent
  - systemctl start qemu-guest-agent

# 运行脚本
write_files:
  - path: /opt/init.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      echo "Custom initialization"

final_message: "Cloud-Init completed successfully"
```

**在 Terraform 中引用**:
```hcl
resource "proxmox_vm_qemu" "vm" {
  # ... 其他配置

  # 引用 Snippet 文件（路径相对于 Proxmox 宿主机）
  cicustom = "user=local:snippets/cloud-init-ubuntu.yaml"

  # 注意：使用 cicustom 时，以下参数可能被忽略或冲突
  # ciuser, cipassword 会被 Snippet 中的配置覆盖
}
```

**警告**:
- 使用 `cicustom` 会**完全覆盖** Cloud-Init 默认配置
- 所有参数（用户、密钥、网络）必须在 YAML 中显式定义
- 文件维护成本高，推荐仅在必要时使用

### 5.3 Cloud-Init 常见配置模式

#### 模式 1: 基础 Web 服务器

```hcl
resource "proxmox_vm_qemu" "webserver" {
  name = "nginx-01"
  vmid = 200

  # ... 核心配置

  # 原生 Cloud-Init 参数
  ciuser = "ubuntu"
  sshkeys = file("~/.ssh/id_rsa.pub")
  ipconfig0 = "ip=dhcp"
}

# 配置管理交由 Ansible：
# ansible-playbook -i hosts webserver.yml
```

#### 模式 2: 带初始化脚本的应用服务器

```hcl
resource "proxmox_vm_qemu" "appserver" {
  name = "app-01"
  vmid = 201

  # ... 核心配置

  ciuser = "ubuntu"
  sshkeys = file("~/.ssh/id_rsa.pub")
  ipconfig0 = "ip=192.168.1.150/24,gw=192.168.1.1"

  # 如需复杂初始化，考虑使用 Snippet 或委托给 Ansible
}
```

### 5.4 QEMU Guest Agent 安装与配置

#### 在模板中预装（最佳实践）

使用 Ansible 和 `virt-customize` 在模板创建阶段预装 QGA：

```yaml
# Ansible Playbook
- name: Prepare Ubuntu template
  hosts: proxmox
  tasks:
    - name: Install qemu-guest-agent to template
      shell: |
        virt-customize -a /var/lib/vz/images/ubuntu-24.04-template/disk-0.qcow2 \
          --run-command 'apt-get update && apt-get install -y qemu-guest-agent' \
          --run-command 'systemctl enable qemu-guest-agent'
```

**优点**:
- 避免 Cloud-Init 依赖
- VM 启动后立即可用
- 消除竞态条件

#### 在 Cloud-Init 中动态安装

```yaml
#cloud-config
packages:
  - qemu-guest-agent

runcmd:
  - systemctl enable qemu-guest-agent
  - systemctl start qemu-guest-agent
```

### 5.5 Cloud-Init 故障排查

#### 查看日志
```bash
# SSH 进入 VM 后
cat /var/log/cloud-init.log
cat /var/log/cloud-init-output.log

# 查看初始化状态
cloud-init status
cloud-init query -f

# 强制重新初始化（危险）
rm /etc/cloud/cloud-init.disabled
cloud-init clean --seed --logs --run
reboot
```

#### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| Cloud-Init 未运行 | 模板中的 `/etc/cloud/cloud-init.disabled` 文件存在 | 删除该文件或在模板中清理 |
| Network config 未应用 | ipconfig0 参数与 YAML 配置冲突 | 使用其中一种方式，避免混用 |
| SSH 密钥未注入 | `sshkeys` 格式错误或 cicustom 覆盖 | 检查公钥格式，确认是否使用 cicustom |
| Machine ID 重复 | 克隆的模板具有相同 Machine ID | 模板制作时：`truncate -s 0 /etc/machine-id` |

---

## 状态管理与配置漂移

### 6.1 Terraform State 深度理解

#### State 文件结构

```json
{
  "version": 4,
  "terraform_version": "1.5.0",
  "serial": 42,
  "lineage": "abc-123",
  "outputs": {
    "vm_ip": {
      "value": "192.168.1.100",
      "type": "string"
    }
  },
  "resources": [
    {
      "type": "proxmox_vm_qemu",
      "name": "web",
      "instances": [
        {
          "schema_version": 8,
          "attributes": {
            "vmid": 100,
            "name": "webserver-01",
            "target_node": "pve0",
            "cores": 4,
            "memory": 8192,
            "default_ipv4_address": "192.168.1.100"
          }
        }
      ]
    }
  ]
}
```

#### 关键字段说明
- `serial`: State 版本计数器，每次更新递增
- `lineage`: State 的唯一标识，用于识别同一资源集
- `resources`: 所有托管资源的当前状态快照

#### State 备份与安全
```bash
# Terraform 自动在 apply 前创建备份
ls -la terraform.tfstate*
# terraform.tfstate      # 当前状态
# terraform.tfstate.backup  # 上一次状态的备份

# 远程状态存储（推荐用于生产）
# Terraform Cloud, S3, Consul, etc.
```

### 6.2 配置漂移检测与解决

#### 漂移场景 1: 磁盘大小不一致

**现象**:
```bash
terraform plan
# 输出显示：
# ~ disk {
#   size = "50G" -> "64G"
# }
```

**原因**: Proxmox 中的实际磁盘大小（50G）与代码定义（64G）不一致

**解决**:
```hcl
# 选项 1: 修改代码匹配实际状态（推荐）
variable "disk_size" {
  default = "50G"  # 从 64G 改为 50G
}

# 选项 2: 使用 ignore_changes（如果磁盘不需要管理）
lifecycle {
  ignore_changes = [disk]
}

# 选项 3: 手动扩容后同步代码
# 在 Proxmox GUI 中扩容到 64G
variable "disk_size" {
  default = "64G"
}
terraform plan  # 现在应该显示 "No changes"
```

#### 漂移场景 2: VMID 不稳定（导致重建）

**现象**:
```bash
terraform plan
# proxmox_vm_qemu.web will be destroyed
# proxmox_vm_qemu.web will be created
```

**根因**: State 中的 `vmid = 102`，但代码中指定 `vmid = 0`（未设置），Terraform 认为需要重建

**解决**: 确保代码中 `vmid` 与 State 一致

```hcl
resource "proxmox_vm_qemu" "web" {
  vmid = 102  # 显式指定，不留给 Proxmox 自动分配
}
```

#### 漂移场景 3: 标签与元数据变更

**现象**:
```bash
terraform plan
# ~ tags = " " -> null
# ~ format = "raw" -> null
```

**原因**: Proxmox Provider 返回的默认值与 Terraform 代码中定义的不一致

**解决**:
```hcl
resource "proxmox_vm_qemu" "vm" {
  # 显式定义以匹配 Proxmox 实际值
  format = "raw"
  tags = ""

  lifecycle {
    ignore_changes = [tags, format, description]
  }
}
```

### 6.3 导入现有资源到 Terraform

#### 场景：重构代码后需要导入已有 VM

```bash
# 1. 先在 Terraform 代码中定义资源框架
cat >> main.tf << 'EOF'
resource "proxmox_vm_qemu" "samba" {
  # 暂时留空，import 时会自动填充
}
EOF

# 2. 导入现有 VM 到 Terraform State
# 格式: terraform import <resource-address> <proxmox-id>
terraform import proxmox_vm_qemu.samba pve0/qemu/102

# 3. 查看导入的资源
terraform state show proxmox_vm_qemu.samba

# 4. 将打印出的属性复制到 main.tf 中，逐渐完善配置
# 然后运行 plan 验证
terraform plan
```

#### 导入到模块中

```bash
# 导入到模块资源
terraform import 'module.samba.proxmox_vm_qemu.vm' pve0/qemu/102
```

### 6.4 Lifecycle 规则详解

#### `ignore_changes`

```hcl
resource "proxmox_vm_qemu" "vm" {
  # ... 配置

  lifecycle {
    # 忽略单个字段
    ignore_changes = [tags]

    # 忽略多个字段
    ignore_changes = [tags, format, description, unused_disk, efidisk]

    # 忽略所有字段的变更（不推荐）
    # ignore_changes = all
  }
}
```

**何时使用**:
- 字段由外部系统管理（如 Ansible 修改的 Description）
- Provider 存在 Bug 导致误报变更
- 某些字段不需要 Terraform 管理

#### `prevent_destroy`

```hcl
resource "proxmox_vm_qemu" "production_db" {
  # ... 配置

  lifecycle {
    prevent_destroy = true
  }
}

# 现在执行 terraform destroy 会失败，保护关键资源
```

#### `create_before_destroy`

```hcl
resource "proxmox_vm_qemu" "webserver" {
  # ... 配置

  lifecycle {
    create_before_destroy = true
  }
}

# 修改需要重建的属性时，会先创建新 VM，再销毁旧 VM
# 避免服务中断（如果有负载均衡器）
```

### 6.5 状态同步最佳实践

#### 定期校验状态

```bash
# 刷新状态（重新查询 Proxmox API）
terraform refresh

# 对比计划（应该显示 No changes）
terraform plan

# 若有非预期变更，立即调查原因
```

#### 团队协作中的状态管理

```hcl
# terraform/backend.tf - 配置远程状态
terraform {
  backend "s3" {
    bucket = "my-terraform-state"
    key = "proxmox/terraform.tfstate"
    region = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt = true
  }
}
```

**优势**:
- 状态文件不提交 Git（安全）
- 自动锁机制防止并发修改
- 全团队共享同一份状态

---

## 常见问题与故障排查

### 7.1 磁盘相关问题

#### 问题 1: "Unused Disk" 错误

**现象**:
VM 创建后磁盘显示为 "Unused0"，VM 无法启动或无法找到系统盘

**常见原因**:
1. 模板磁盘大小（20G）> 请求磁盘大小（8G），Proxmox 无法缩容
2. Terraform 执行了 "Detach & Create" 逻辑，卸载了原盘并创建新空盘

**根本原因深度分析**:
```
用户需求: "我要 8G 磁盘的 VM"
模板状态: "模板有 20G 系统盘"
Terraform 逻辑:
  - 发现 request_size (8G) < template_size (20G)
  - 认为需要"收缩"磁盘
  - 但 Proxmox/QEMU 不支持直接收缩
  - 退而求其次：卸载原盘，创建新盘
  - 结果：新盘为空，无法启动
```

**解决方案**:
```hcl
# 方案 A: 调整代码，使 disk_size >= template_size
variable "disk_size" {
  default = "50G"  # >= 模板大小
}

# 方案 B: 重建更小的模板
# 使用 virt-customize 预先将模板磁盘收缩到目标大小
```

**防御性编程** (在生成 Terraform 变量的脚本中):
```python
# Python 脚本：生成 Terraform 变量时进行验证
def generate_tfvars(netbox_vm, template_size_gb):
    # 检查模板大小约束
    if netbox_vm.disk_gb < template_size_gb:
        raise ValueError(
            f"VM disk {netbox_vm.disk_gb}G < template {template_size_gb}G"
        )

    # 确保最终大小 >= 模板大小
    final_size = max(netbox_vm.disk_gb, template_size_gb)
    return {
        "disk_size": f"{final_size}G"
    }
```

#### 问题 2: 磁盘单位混淆

**现象**:
Terraform 试图创建一个 4096G（4TB）的磁盘，实际需要 4GB

**原因**:
Netbox API 返回的 `disk` 字段单位是 **MB**（4096 MB），脚本直接当 GB 处理

**解决**:
```python
# 正确的单位转换
disk_size_gb = vm.disk / 1024  # MB -> GB
disk_size_str = f"{disk_size_gb}G"  # Terraform 格式
```

#### 问题 3: 磁盘启动顺序错误

**现象**:
VM 启动时进入 UEFI Shell 或显示"No bootable device"

**原因**:
未显式指定启动顺序，Proxmox 默认可能先尝试网络或光驱启动

**解决**:
```hcl
resource "proxmox_vm_qemu" "vm" {
  # ... 配置

  # 显式指定启动顺序：SCSI 系统盘 > IDE Cloud-Init 盘 > 网络
  boot = "order=scsi0;ide2;net0"
}
```

### 7.2 Cloud-Init 与网络配置问题

#### 问题 1: Terraform 卡在 "Creating" 状态

**现象**:
```
Apply 执行后长时间停留在 "Creating state"，最终超时
```

**原因链**:
```
Cloud-Init 未能启用 QEMU Guest Agent
    ↓
Terraform 无法从 Agent 获取 VM IP
    ↓
判断 VM 未就绪，持续轮询
    ↓
超时报错
```

**根本原因**:
1. 模板未预装 qemu-guest-agent
2. Cloud-Init YAML 中未定义 `packages: [qemu-guest-agent]`
3. VM 无法从互联网下载软件包

**解决**:
```hcl
# 选项 1: 确保模板中预装 QGA
# 在模板制作阶段：
# virt-customize ... --run-command 'apt-get install -y qemu-guest-agent'

# 选项 2: 通过 Cloud-Init 安装
cicustom = "user=local:snippets/cloud-init-ubuntu.yaml"

# cloud-init-ubuntu.yaml 中：
# packages:
#   - qemu-guest-agent
# runcmd:
#   - systemctl enable qemu-guest-agent
#   - systemctl start qemu-guest-agent

# 选项 3: 调整 Terraform 超时设置
# 虽然标准 apply 无超时参数，但可通过外部脚本控制
```

#### 问题 2: Machine ID 冲突导致网络启动失败

**现象**:
VM 启动后，日志显示：
```
Failed to start systemd-network
Device or resource busy
```

**原因**:
模板中的 `/etc/machine-id` 包含固定值，所有克隆的 VM 拥有相同 ID，导致 DHCP/netplan 冲突

**解决**:
```bash
# 在模板制作阶段执行（Ansible task）
truncate -s 0 /etc/machine-id

# 这会强制 Linux 在首次启动时生成新的、唯一的 Machine ID
```

#### 问题 3: Cloud-Init 驱动器未被检测到

**现象**:
VM 启动后 Cloud-Init 未运行，`lsblk` 看不到 Cloud-Init 盘

**原因**:
Q35 架构下，IDE 设备可能无法被内核识别，Cloud-Init 盘需要挂载到 SCSI 总线

**解决**:
```hcl
resource "proxmox_vm_qemu" "vm" {
  # ... 配置

  # 显式指定 Cloud-Init 盘位置
  cloudinit_cdrom_storage = var.storage_pool

  # 或在 Terraform 3.x 中使用旧版参数：
  # cicustom = ...  # 会自动处理位置
}
```

### 7.3 QEMU Guest Agent 问题

#### 问题 1: "QEMU guest agent is not running"

**现象**:
```
Error: 500 QEMU guest agent is not running
```

**原因**:
1. VM 中 qemu-guest-agent 服务未启动
2. Terraform 的 `agent = 1` 只启用了宿主机端，未实际安装/启动 VM 端的服务

**排查步骤**:
```bash
# SSH 进入 VM
ssh ubuntu@192.168.1.100

# 检查 Agent 是否安装
which qemu-ga
apt list --installed | grep qemu-guest-agent

# 检查服务状态
systemctl status qemu-guest-agent

# 查看日志
journalctl -u qemu-guest-agent -n 50
```

**解决**:
```bash
# 在 VM 中手动安装和启用
sudo apt-get update
sudo apt-get install -y qemu-guest-agent
sudo systemctl enable qemu-guest-agent
sudo systemctl start qemu-guest-agent
```

#### 问题 2: VM 获取 IP 失败

**现象**:
`terraform output vm_ip` 显示为空

**原因**:
Terraform 依赖 QGA 从 VM 内部查询 IP，如果 Agent 未运行或网络未就绪，无法获取

**解决**:
```hcl
# Terraform 中可以添加依赖和延迟
resource "proxmox_vm_qemu" "vm" {
  # ... 配置
  agent = 1

  # 在调用方可以使用 depends_on 确保资源就绪
  # 但这只能保证资源创建顺序，不能保证 IP 获取成功
}

# 更好的方案是配合 Ansible 的等待逻辑
# 或在脚本中进行重试
```

### 7.4 UEFI/Q35 兼容性问题

#### 问题: Cloud-Init 配置无法应用到 UEFI/Q35 VM

**现象**:
切换到 UEFI (OVMF) 和 Q35 后，Cloud-Init 配置未生效

**原因**:
Q35 架构改变了设备总线布局，IDE 驱动器可能无法识别

**解决**:
```hcl
resource "proxmox_vm_qemu" "vm" {
  bios = "ovmf"  # UEFI

  disk {
    slot = 0
    size = var.disk_size
    type = "disk"
    storage = var.storage_pool
    # Q35 下推荐使用 SCSI 或 VirtIO
  }

  # EFI 磁盘配置
  efidisk {
    efitype = "4m"
    storage = var.storage_pool
  }

  # Cloud-Init 盘：确保在支持的总线上
  cloudinit_cdrom_storage = var.storage_pool
}
```

### 7.5 Terraform 资源强制重建问题

#### 问题: 每次 plan 都显示 "will be destroyed"

**现象**:
```
proxmox_vm_qemu.web will be destroyed
proxmox_vm_qemu.web will be created
```

**原因**:
通常由以下几点导致：
1. `vmid` 不一致（State 中是 100，代码中未指定或为 0）
2. Provider 版本升级导致 Schema 变化
3. Proxmox 后端返回值与代码定义不匹配

**调试步骤**:
```bash
# 1. 查看当前状态
terraform state show proxmox_vm_qemu.web

# 2. 对比代码和状态
terraform plan -out=plan.txt

# 3. 检查详细差异
terraform plan -json | jq '.resource_changes[] | select(.change.actions != ["no-op"])'

# 4. 如果差异无关紧要，使用 ignore_changes
```

**防止重建的最佳实践**:
```hcl
resource "proxmox_vm_qemu" "web" {
  vmid = 100  # 显式指定，不留给 Proxmox 自动分配

  lifecycle {
    # 忽略由 Provider Bug 导致的误报
    ignore_changes = [unused_disk, efidisk, format]
  }
}
```

### 7.6 Netbox 集成问题

#### 问题: Netbox 作为 IPAM 数据源时的 API 对接问题

**现象**:
Terraform 从 Netbox 脚本读取参数时，某些字段单位或格式不匹配

**常见场景**:
1. 磁盘大小从 Netbox MB 单位未转换为 Terraform GB
2. VMID 从 IP 地址解析失败
3. 网络 CIDR 格式不正确

**防御性方案**:
```python
#!/usr/bin/env python3
"""
脚本：从 Netbox 读取 VM 信息，生成 Terraform 变量
关键：进行充分的参数验证和转换
"""

import requests
import re

def fetch_vm_from_netbox(vm_name):
    netbox_url = "https://netbox.example.com/api"
    headers = {"Authorization": f"Token {NETBOX_TOKEN}"}

    resp = requests.get(
        f"{netbox_url}/virtualization/virtual-machines/?name={vm_name}",
        headers=headers
    )
    vm = resp.json()['results'][0]
    return vm

def validate_and_convert(vm):
    # 磁盘大小：MB -> GB
    disk_gb = vm['disk'] / 1024
    assert disk_gb >= MIN_DISK_SIZE, "Disk too small"

    # VMID：从 IP 最后一段提取
    ip = vm['primary_ip4']['address'].split('/')[0]
    vmid = int(ip.split('.')[-1])
    assert 0 < vmid < 65536, "Invalid VMID"

    # 网络配置
    cidr = vm['primary_ip4']['address']
    gw = vm.get('gateway', '192.168.1.1')

    return {
        "vmid": vmid,
        "disk_size": f"{int(disk_gb)}G",
        "ip_config": f"ip={cidr},gw={gw}"
    }

def generate_tfvars(vm_name):
    vm = fetch_vm_from_netbox(vm_name)
    params = validate_and_convert(vm)
    return params
```

---

## SSH 密钥管理策略

### 8.1 问题背景

在 IaC 实践中，SSH 密钥管理存在一个经典矛盾：

| 方面 | Terraform | Ansible |
|------|-----------|---------|
| **职责** | 创建 VM | 配置 VM |
| **需要** | 初始化时注入一个 Key | 持续维护多个 Key |
| **问题** | 每次修改 sshkeys 可能触发 VM 重建 | 频繁修改无法通过 IaC 版本管理 |

### 8.2 解决方案：分离职能

#### 架构设计

```
Day 0 (VM 创建)
    ↓
Terraform 使用"Bootstrap Key" (固定不变)
    ↓
VM 成功启动，可通过 Bootstrap Key SSH 进入
    ↓

Day 1 (VM 配置)
    ↓
Ansible 接手，使用 Bootstrap Key 连接
    ↓
Ansible 部署"User Management Role"，注入完整的 Key 列表
    ↓

Day 2+ (日常维护)
    ↓
新增用户 -> 修改 Ansible 变量 -> 运行 Playbook
    ↓
无需修改 Terraform，无需重建 VM
```

### 8.3 Terraform 端配置

#### 只维护一个不变的 Bootstrap Key

```hcl
# variables.tf
variable "bootstrap_ssh_key" {
  type = string
  description = "Bootstrap SSH public key (长期不变)"
  default = file("~/.ssh/terraform_rsa.pub")
}

# main.tf
resource "proxmox_vm_qemu" "vm" {
  # ... 其他配置

  ciuser = "ubuntu"
  sshkeys = var.bootstrap_ssh_key

  # 由于 sshkeys 几乎永不改变，Terraform 就不会因此重建 VM
}
```

**关键点**:
- Bootstrap Key 通常来自 CI/CD 机器人或运维负责人
- 这个 Key 长期有效，不经常轮换
- 作为 VM 初始化的唯一入口

### 8.4 Ansible 端配置

#### User Management Role

```yaml
# roles/users/defaults/main.yml
authorized_users:
  - name: alice
    key: "ssh-rsa AAAA...alice@example.com"
  - name: bob
    key: "ssh-rsa BBBB...bob@example.com"
  - name: charlie
    key: "ssh-rsa CCCC...charlie@example.com"

# roles/users/tasks/main.yml
---
- name: Create user accounts
  user:
    name: "{{ item.name }}"
    groups: sudo
    shell: /bin/bash
  loop: "{{ authorized_users }}"

- name: Configure SSH authorized_keys
  authorized_key:
    user: "{{ item.name }}"
    key: "{{ item.key }}"
    state: present
  loop: "{{ authorized_users }}"
```

#### Playbook 使用示例

```yaml
# site.yml
---
- name: Configure all VMs
  hosts: proxmox_vms
  roles:
    - users
    - security
    - monitoring
```

执行：
```bash
# 初次配置（Day 1）：使用 Bootstrap Key
ansible-playbook -i hosts site.yml \
  --private-key ~/.ssh/terraform_rsa \
  -u ubuntu

# 后续更新（Day 2+）：可使用团队成员自己的 Key
ansible-playbook -i hosts site.yml
```

### 8.5 最佳实践总结

| 场景 | 工具 | 责任 |
|------|------|------|
| VM 创建及初始化 SSH | Terraform | 一次性注入 Bootstrap Key |
| 用户和密钥的日常维护 | Ansible | 幂等化管理完整 Key 列表 |
| 密钥轮换 | Ansible | 更新 group_vars，运行 Playbook |
| 紧急禁用某个 Key | Ansible | 删除对应行，执行 Playbook |

**黄金法则**: "Terraform 建房子，Ansible 装修和发钥匙"

---

## 参考资源与命令速查

### 9.1 常用 Terraform 命令

#### 初始化与验证

```bash
# 初始化工作目录
terraform init

# 验证配置语法正确性
terraform validate

# 格式化代码（自动修复缩进）
terraform fmt -recursive

# 查看代码的详细依赖关系
terraform graph | dot -Tsvg > graph.svg
```

#### 规划与执行

```bash
# 查看执行计划（不执行任何操作）
terraform plan

# 保存执行计划到文件
terraform plan -out=plan.tfplan

# 查看具体资源变更
terraform plan -json | jq .

# 应用配置（需交互确认）
terraform apply

# 应用配置（自动确认，谨慎使用）
terraform apply -auto-approve

# 应用保存的计划（跳过确认）
terraform apply plan.tfplan

# 销毁所有资源
terraform destroy

# 销毁并自动确认
terraform destroy -auto-approve
```

#### 状态管理

```bash
# 列出所有托管资源
terraform state list

# 查看具体资源的详细状态
terraform state show 'proxmox_vm_qemu.web'

# 刷新状态（重新查询 API）
terraform refresh

# 手动修改状态（谨慎！）
terraform state mv 'proxmox_vm_qemu.old' 'proxmox_vm_qemu.new'

# 导入现有资源到状态
terraform import 'proxmox_vm_qemu.web' pve0/qemu/100

# 删除状态中的资源（仅删除跟踪，不删除实际 VM）
terraform state rm 'proxmox_vm_qemu.web'

# 强制解锁状态（如果 apply 中断）
terraform force-unlock LOCK_ID
```

#### 调试

```bash
# 启用详细日志输出
TF_LOG=DEBUG terraform plan

# 保存日志到文件
TF_LOG=DEBUG TF_LOG_PATH=terraform.log terraform apply

# 查看变量值
terraform console
> var.vm_cores
> local.computed_value

# 输出值查询
terraform output
terraform output vm_ip

# 扩展诊断信息
terraform plan -json | jq -r '.diagnostics'
```

### 9.2 Proxmox API 命令参考

#### VM 管理

```bash
# 列出所有 VM
curl -s https://pve:8006/api2/json/nodes/pve0/qemu \
  -H "Authorization: PVEAPIToken=user@pam!token-id=token-value" | jq

# 查询具体 VM
curl -s https://pve:8006/api2/json/nodes/pve0/qemu/100/status/current \
  -H "Authorization: PVEAPIToken=..." | jq

# 查询模板磁盘大小
ssh root@pve "qm config 9000 | grep disksize"

# 创建 Snippet
cat > /var/lib/vz/snippets/cloud-init.yaml << 'EOF'
#cloud-config
...
EOF

# 列出 Snippets
ls -la /var/lib/vz/snippets/

# 删除 Snippet
rm /var/lib/vz/snippets/cloud-init.yaml
```

#### 磁盘操作

```bash
# 查询磁盘大小
qm config 100 | grep -i disk

# 扩展磁盘（需 VM 离线）
qm resize 100 scsi0 +50G

# 查询存储池
pvesm status -content images

# 查询存储池中的镜像
pvesm list local-zfs
```

### 9.3 Terraform 文档链接

- **Official Terraform Docs**: https://www.terraform.io/docs
- **Proxmox Provider Docs**: https://registry.terraform.io/providers/telmate/proxmox
- **Terraform Best Practices**: https://www.terraform.io/docs/cloud/guides/recommended-practices
- **Proxmox VE Documentation**: https://pve.proxmox.com/pve-docs/

### 9.4 常见错误消息解释

| 错误 | 原因 | 解决 |
|------|------|------|
| `Error: 400 No permissions (permission error)` | Proxmox 用户权限不足 | 检查 pveum 权限配置 |
| `Error: 500 QEMU guest agent is not running` | VM 中 qemu-guest-agent 未启动 | 在 VM 中手动安装并启动 agent |
| `Error: invalid vmid` | vmid 已被占用或格式错误 | 使用 `qm list` 查看已有 VM ID |
| `Warning: Unused disk` | 克隆或磁盘操作后留下残留盘 | 使用 `lifecycle { ignore_changes = [unused_disk] }` |
| `Error: Could not find storage 'local-lvm'` | 指定的存储池不存在 | 检查 Proxmox 实际可用存储池 |
| `Error: clone failed` | 克隆操作失败 | 检查磁盘大小、权限、模板状态 |

---

## 总结与建议

### 10.1 核心要点回顾

1. **模块化优先**: 从一开始就设计模块，支持多环境和团队协作
2. **状态管理严肃**: 使用远程状态后端，建立严格的访问控制
3. **显式优于隐式**: 不依赖默认值，显式定义所有关键参数
4. **防御性编程**: 在生成 Terraform 变量的脚本中加入充分的验证
5. **分离职能**: Terraform 负责基础设施，Ansible 负责配置管理，职责清晰

### 10.2 生产环境检查清单

部署生产环境前，确保以下各点：

- [ ] Terraform State 存储在远程后端（S3, Terraform Cloud 等）
- [ ] State 启用加密和版本控制
- [ ] 所有敏感变量（密码、API 密钥）使用 `sensitive = true`
- [ ] 对关键资源启用 `lifecycle { prevent_destroy = true }`
- [ ] 代码通过 CI/CD Pipeline 执行（防止手动 apply）
- [ ] 所有 VM 磁盘大小约束已验证（>= 模板大小）
- [ ] QEMU Guest Agent 已在模板中预装
- [ ] SSH 密钥管理使用 Bootstrap Key 模式
- [ ] 定期运行 `terraform plan` 检查漂移
- [ ] 建立了 Terraform 变更的 Code Review 流程

### 10.3 后续学习方向

- **Terraform 高级特性**: workspaces, for_each, dynamic blocks
- **Provider 深度**: 理解 telmate/proxmox 的详细资源配置
- **集成自动化**: Netbox + Terraform + Ansible 全链路
- **监控与告警**: 集成 Prometheus、Grafana 监控基础设施
- **灾难恢复**: State 备份、VM 快照、集群高可用设计

---

## 附录：快速参考卡片

### A.1 文件模板

#### 最小化 main.tf 模板
```hcl
terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
      version = "~> 3.0"
    }
  }
}

provider "proxmox" {
  pm_api_url = var.proxmox_api_url
  pm_user = var.proxmox_user
  pm_password = var.proxmox_password
  pm_tls_insecure = true
}

resource "proxmox_vm_qemu" "vm" {
  name = var.vm_name
  vmid = var.vmid
  target_node = var.target_node
  clone = var.clone_template
  full_clone = true

  cores = var.cores
  memory = var.memory

  disk {
    slot = 0
    size = var.disk_size
    type = "disk"
    storage = var.storage_pool
  }

  ipconfig0 = "ip=dhcp"
  ciuser = "ubuntu"
  sshkeys = var.ssh_key
  agent = 1

  boot = "order=scsi0;ide2;net0"

  lifecycle {
    ignore_changes = [unused_disk, efidisk]
  }
}

output "vm_ip" {
  value = proxmox_vm_qemu.vm.default_ipv4_address
}
```

### A.2 变量命名约定

```hcl
# 前缀约定
proxmox_*      # Proxmox 基础设施相关
vm_*           # 虚拟机配置
storage_*      # 存储相关
network_*      # 网络相关

# 示例
proxmox_api_url
vm_name
vm_cores
storage_pool
network_gateway
```

---

**文档版本**: 1.0
**最后更新**: 2026-01-30
**编译者**: Opencode AI
**许可证**: CC BY 4.0
