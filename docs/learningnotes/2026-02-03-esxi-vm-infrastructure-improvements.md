# ESXi VM 基础设施改进学习笔记

> **日期**: 2026-02-03  
> **主题**: Terraform esxi-vm 模块增强、VMX 参数配置、Ansible Windows 支持

## 1. 背景

在部署 PBS iSCSI + Veeam 混合备份架构过程中，遇到了几个基础设施层面的问题，需要对 Terraform 模块和 Ansible 配置进行改进。

## 2. 问题与解决方案

### 2.1 VMX 自定义参数支持

**问题**: 需要为不同 VM 添加特定的 VMX 配置参数：
- PBS VM: Samsung NVMe PCIe 直通设备在关机时会触发 FLR (Function Level Reset) 崩溃
- Windows VM: 虚拟机分辨率被限制在 1280x800

**解决方案**: 在 esxi-vm 模块中添加 `extra_config` 变量

**修改文件**: `terraform/modules/esxi-vm/variables.tf`

```hcl
variable "extra_config" {
  description = "Extra VMX configuration parameters"
  type        = map(string)
  default     = {}
}
```

**修改文件**: `terraform/modules/esxi-vm/main.tf`

```hcl
resource "vsphere_virtual_machine" "vm" {
  # ... 其他配置 ...
  
  # Extra VMX configuration parameters
  extra_config = var.extra_config
  
  lifecycle {
    ignore_changes = [pci_device_id, extra_config]
  }
}
```

**使用示例 - PBS VM (NVMe FLR 修复)**:

```hcl
module "pbs" {
  source = "../modules/esxi-vm"
  # ... 其他配置 ...
  
  extra_config = {
    "pciPassthru.use64bitMMIO"    = "TRUE"
    "pciPassthru.64bitMMIOSizeGB" = "64"
    "pciPassthru0.resetMethod"    = "d3d0"
    "pciPassthru1.resetMethod"    = "d3d0"
  }
}
```

**使用示例 - Windows VM (高分辨率支持)**:

```hcl
module "windows_server" {
  source = "../modules/esxi-vm"
  # ... 其他配置 ...
  
  extra_config = {
    "svga.maxWidth"  = "1920"
    "svga.maxHeight" = "1080"
  }
}
```

### 2.2 Samsung NVMe FLR 问题

**问题描述**: 

Samsung SM963 NVMe SSD 通过 PCIe 直通给 PBS VM 时，VM 关机会触发 FLR (Function Level Reset)。某些 NVMe 固件不支持 FLR，导致 ESXi 主机卡死或 VM 无法正常关机。

**根本原因**:

- ESXi 默认使用 FLR 来重置 PCIe 设备
- Samsung SM963 固件不正确响应 FLR 命令
- 需要改用 D3->D0 电源状态转换来重置设备

**解决方案**:

在 VMX 配置中添加：

```
pciPassthru0.resetMethod = "d3d0"
pciPassthru1.resetMethod = "d3d0"
```

**参数说明**:

| 参数 | 值 | 说明 |
|------|-----|------|
| `pciPassthruX.resetMethod` | `flr` | 默认，使用 Function Level Reset |
| `pciPassthruX.resetMethod` | `d3d0` | 使用 D3->D0 电源状态转换 |
| `pciPassthruX.resetMethod` | `none` | 不重置（不推荐） |

**注意**: `X` 是直通设备的索引号 (0, 1, 2...)

### 2.3 VMware 虚拟机分辨率限制

**问题描述**:

Windows Server VM 在 ESXi 上运行时，即使安装了 VMware Tools，分辨率最高只能到 1280x800。通过 RustDesk 远程连接时界面很小。

**根本原因**:

VMware SVGA 虚拟显卡在没有物理显示器连接的情况下，默认限制最大分辨率。

**解决方案**:

在 VMX 配置中添加：

```
svga.maxWidth = "1920"
svga.maxHeight = "1080"
```

**生效条件**:

- 需要关闭 VM 后重新启动
- 需要已安装 VMware Tools
- 在 Windows Display Settings 中选择新分辨率

### 2.4 vsphere Provider PCI Passthrough Bug

**问题描述**:

运行 `terraform apply` 时出现 panic 错误：

```
panic: interface conversion: types.BaseVirtualDeviceBackingInfo is 
*types.VirtualPCIPassthroughDynamicBackingInfo, not 
*types.VirtualPCIPassthroughDeviceBackingInfo
```

**根本原因**:

vsphere provider v2.15.0 在处理已有 PCI 直通设备的 VM 时存在 bug。即使 Terraform 配置中 `pci_device_ids = []`，provider 读取现有 VM 状态时仍会尝试处理手动配置的直通设备。

**解决方案**:

在 lifecycle 块中忽略 `pci_device_id` 变更：

```hcl
lifecycle {
  ignore_changes = [pci_device_id]
}
```

**最佳实践**:

对于 PCIe 直通设备，建议通过 ESXi Web UI 手动管理，不通过 Terraform 管理，以避免意外的 VM 重建。

## 3. Ansible Windows 支持

### 3.1 添加 ansible.windows Collection

**问题**: 需要使用 Ansible 管理 Windows Server

**解决方案**:

**修改文件**: `ansible/requirements.yml`

```yaml
collections:
  - name: community.general
  - name: community.vmware
  - name: cloud.terraform
  - name: community.docker
  - name: ansible.posix
  - name: netbox.netbox
  - name: ansible.windows  # 新增
```

**安装**:

```bash
ansible-galaxy collection install ansible.windows -p ./collections
```

### 3.2 配置 collections_path

**问题**: Ansible 找不到本地安装的 collection

**解决方案**:

**修改文件**: `ansible/ansible.cfg`

```ini
[defaults]
roles_path = roles
collections_path = collections  # 新增
```

### 3.3 Windows 连接配置

**Terraform 端** (ansible_host 资源):

```hcl
resource "ansible_host" "windows_server" {
  name   = "windows-server"
  groups = ["esxi_vms", "windows"]

  variables = {
    ansible_host                         = var.windows_ip_address
    ansible_user                         = "Administrator"
    ansible_connection                   = "winrm"
    ansible_winrm_transport              = "ntlm"
    ansible_winrm_server_cert_validation = "ignore"
  }
}
```

**Ansible 端** (group_vars/windows.yml):

```yaml
---
ansible_user: Administrator
ansible_password: "{{ vault_windows_admin_password }}"
ansible_port: 5985
ansible_winrm_scheme: http
```

### 3.4 Windows Server WinRM 配置

在 Windows Server 上启用 WinRM：

```powershell
# 启用 WinRM 服务
Enable-PSRemoting -Force

# 允许未加密连接（内网环境）
Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $true

# 启用 Basic 认证
Set-Item WSMan:\localhost\Service\Auth\Basic -Value $true

# 验证配置
winrm get winrm/config/service
```

### 3.5 Python WinRM 依赖

在 Ansible 控制节点上安装 pywinrm：

```bash
pip install pywinrm
```

## 4. Terraform 变量优先级问题

### 4.1 问题描述

Windows VM 的 `ansible_user` 被设置为 `root`，而不是预期的 `Administrator`。

### 4.2 原因分析

Ansible 变量优先级：
1. `ansible.cfg` 中的 `remote_user = root` (全局默认)
2. Terraform `ansible_host` 资源中的 `ansible_user`
3. `group_vars/windows.yml` 中的 `ansible_user`

Terraform 生成的 inventory 变量优先级高于 group_vars。

### 4.3 解决方案

在 Terraform 的 `ansible_host` 资源中明确设置 `ansible_user`：

```hcl
variables = {
  ansible_host = var.windows_ip_address
  ansible_user = "Administrator"  # 明确设置
  # ...
}
```

## 5. 经验总结

### 5.1 VMX 参数管理

| 场景 | 解决方案 |
|------|----------|
| PCIe 直通设备问题 | `pciPassthruX.resetMethod` |
| 虚拟显卡分辨率 | `svga.maxWidth/maxHeight` |
| 64 位 MMIO 支持 | `pciPassthru.use64bitMMIO` |

### 5.2 Ansible Windows 管理检查清单

- [ ] 安装 `ansible.windows` collection
- [ ] 配置 `collections_path`
- [ ] 安装 `pywinrm` Python 包
- [ ] Windows 端启用 WinRM
- [ ] 配置正确的认证方式 (NTLM/Basic)
- [ ] 设置正确的端口 (5985/5986)

### 5.3 Terraform 最佳实践

- 使用 `extra_config` 变量传递自定义 VMX 参数
- 对于手动管理的资源（如 PCI 直通），使用 `ignore_changes`
- 在 `ansible_host` 资源中明确设置所有必要的连接参数

## 6. 相关文件

| 文件 | 修改内容 |
|------|----------|
| `terraform/modules/esxi-vm/variables.tf` | 添加 `extra_config` 变量 |
| `terraform/modules/esxi-vm/main.tf` | 应用 `extra_config`，更新 lifecycle |
| `terraform/esxi/pbs.tf` | 添加 NVMe FLR 修复参数 |
| `terraform/esxi/windows-server.tf` | 添加高分辨率参数 |
| `ansible/ansible.cfg` | 添加 `collections_path` |
| `ansible/requirements.yml` | 添加 `ansible.windows` |
| `ansible/inventory/group_vars/windows.yml` | 新增 Windows 连接配置 |
