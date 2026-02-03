# PBS iSCSI Target for Veeam - 实施规范

> **版本**: 1.0  
> **日期**: 2026-02-03  
> **状态**: 已批准  
> **关联文档**: [pbs_iscsi_veeam_guide.md](../deployment/pbs_iscsi_veeam_guide.md)

## 1. 背景概述

本规范基于 `docs/deployment/pbs_iscsi_veeam_guide.md` 中描述的混合备份架构方案，定义具体的 IaC 实施细节。

**核心需求**: T7910 冷备份服务器上的 PBS VM 通过 HBA 直通独占物理硬盘。需要在不改变硬件配置的情况下，让同主机的 Windows Server VM 能够使用底层 ZFS 存储空间运行 Veeam VBR。

**解决方案**: 在 PBS 的 ZFS 存储池上创建 ZVol，通过 LIO iSCSI Target 服务共享给 Windows Server。Windows 将 iSCSI 盘格式化为 ReFS，供 Veeam 使用 Fast Clone 功能。

## 2. 设计决策

| 决策点 | 选项 | 选择 | 理由 |
|--------|------|------|------|
| ZVol 大小策略 | A) 固定 2TB / B) 变量控制 / C) 按比例 | **A** | 简单，后续可通过 `zfs set volsize=` 手动扩容 |
| iSCSI 认证模式 | A) Demo 模式 / B) ACL / C) 可选 | **A** | 内网环境，简单优先，安全性可接受 |
| Windows 管理方式 | A) 纯手动 / B) 后续 Ansible 自动化 / C) 仅 PBS | **B** | 本期 PBS 端自动化，Windows 手动；后续迭代添加 Ansible Windows 支持 |

### 技术参数

| 参数 | 值 | 说明 |
|------|-----|------|
| ZVol 名称 | `backup-pool/veeam-vol` | 在现有 ZFS pool 下创建 |
| ZVol 大小 | 2TB | 精简置备 (sparse) |
| ZVol blocksize | 64K | iSCSI + ReFS 最佳实践 |
| 压缩算法 | lz4 | 低 CPU 开销，适合冷备份场景 |
| IQN | `iqn.2026-02.lan.pbs:veeam` | 遵循 RFC 3720 命名规范 |
| Portal | `0.0.0.0:3260` | 监听所有接口 |

## 3. 文件清单

### 3.1 新建文件

```
ansible/
  roles/
    pbs_iscsi/
      tasks/
        main.yml              # 主入口，包含其他任务文件
        zvol.yml              # ZVol 创建任务
        iscsi-target.yml      # iSCSI Target 配置任务
      defaults/
        main.yml              # 角色变量定义
      handlers/
        main.yml              # 服务处理器
  playbooks/
    deploy-pbs-iscsi.yml      # 部署 playbook（含 verify play）

terraform/
  esxi/
    windows-server.tf         # Windows Server VM 定义
```

### 3.2 修改文件

```
terraform/
  esxi/
    variables.tf              # 追加 Windows VM 相关变量
```

## 4. 详细规范

### 4.1 Ansible Role: `pbs_iscsi`

#### `defaults/main.yml`

```yaml
---
# =============================================================================
# PBS iSCSI Role - Default Variables
# =============================================================================

# -----------------------------------------------------------------------------
# ZVol Configuration
# -----------------------------------------------------------------------------
pbs_iscsi_zvol_name: "veeam-vol"
# ZVol 名称，将创建在 {{ pbs_zfs_pool_name }}/{{ pbs_iscsi_zvol_name }}

pbs_iscsi_zvol_size: "2T"
# ZVol 大小，支持 ZFS 单位格式 (K, M, G, T)

pbs_iscsi_zvol_blocksize: "64K"
# 卷块大小，64K 适合 iSCSI + ReFS 场景

pbs_iscsi_zvol_compression: "lz4"
# 压缩算法，lz4 提供良好的压缩比和低 CPU 开销

pbs_iscsi_zvol_sparse: true
# 精简置备，不预分配全部空间

# -----------------------------------------------------------------------------
# iSCSI Target Configuration
# -----------------------------------------------------------------------------
pbs_iscsi_iqn: "iqn.2026-02.lan.pbs:veeam"
# iSCSI Qualified Name，遵循 RFC 3720 格式

pbs_iscsi_portal_ip: "0.0.0.0"
# Portal 监听 IP，0.0.0.0 表示所有接口

pbs_iscsi_portal_port: 3260
# iSCSI 标准端口

pbs_iscsi_backstore_name: "veeam-backstore"
# LIO backstore 名称

# -----------------------------------------------------------------------------
# Demo Mode (No Authentication)
# -----------------------------------------------------------------------------
pbs_iscsi_demo_mode: true
# 启用 demo 模式，允许任何 initiator 连接
# 生产环境应设为 false 并配置 ACL

# -----------------------------------------------------------------------------
# Dependencies (from pbs role)
# -----------------------------------------------------------------------------
# pbs_zfs_pool_name: "backup-pool"  # 从 pbs role 或 host_vars 获取
```

#### `tasks/main.yml`

```yaml
---
# PBS iSCSI Role - Main Entry Point

- name: Include ZVol creation tasks
  ansible.builtin.include_tasks: zvol.yml
  tags: [zvol, iscsi]

- name: Include iSCSI target configuration tasks
  ansible.builtin.include_tasks: iscsi-target.yml
  tags: [iscsi]
```

#### `tasks/zvol.yml`

```yaml
---
# ZVol Creation Tasks

- name: Check if ZVol already exists
  ansible.builtin.command:
    cmd: "zfs list {{ pbs_zfs_pool_name }}/{{ pbs_iscsi_zvol_name }}"
  register: zvol_check
  failed_when: false
  changed_when: false

- name: Create ZVol for iSCSI target
  ansible.builtin.command:
    cmd: >-
      zfs create
      -V {{ pbs_iscsi_zvol_size }}
      {{ '-s' if pbs_iscsi_zvol_sparse else '' }}
      -o volblocksize={{ pbs_iscsi_zvol_blocksize }}
      -o compression={{ pbs_iscsi_zvol_compression }}
      {{ pbs_zfs_pool_name }}/{{ pbs_iscsi_zvol_name }}
  when: zvol_check.rc != 0

- name: Verify ZVol device exists
  ansible.builtin.stat:
    path: "/dev/zvol/{{ pbs_zfs_pool_name }}/{{ pbs_iscsi_zvol_name }}"
  register: zvol_device
  failed_when: not zvol_device.stat.exists
```

#### `tasks/iscsi-target.yml`

```yaml
---
# iSCSI Target Configuration Tasks

- name: Install targetcli-fb package
  ansible.builtin.apt:
    name: targetcli-fb
    state: present
    update_cache: yes

- name: Enable and start target service
  ansible.builtin.systemd:
    name: rtslib-fb-targetctl
    enabled: yes
    state: started

- name: Check if backstore exists
  ansible.builtin.command:
    cmd: "targetcli ls /backstores/block/{{ pbs_iscsi_backstore_name }}"
  register: backstore_check
  failed_when: false
  changed_when: false

- name: Create block backstore from ZVol
  ansible.builtin.command:
    cmd: >-
      targetcli /backstores/block create
      {{ pbs_iscsi_backstore_name }}
      /dev/zvol/{{ pbs_zfs_pool_name }}/{{ pbs_iscsi_zvol_name }}
  when: backstore_check.rc != 0
  notify: Save targetcli config

- name: Check if iSCSI target exists
  ansible.builtin.command:
    cmd: "targetcli ls /iscsi/{{ pbs_iscsi_iqn }}"
  register: target_check
  failed_when: false
  changed_when: false

- name: Create iSCSI target
  ansible.builtin.command:
    cmd: "targetcli /iscsi create {{ pbs_iscsi_iqn }}"
  when: target_check.rc != 0
  notify: Save targetcli config

- name: Configure iSCSI portal
  ansible.builtin.command:
    cmd: >-
      targetcli /iscsi/{{ pbs_iscsi_iqn }}/tpg1/portals create
      {{ pbs_iscsi_portal_ip }} {{ pbs_iscsi_portal_port }}
  register: portal_result
  failed_when: portal_result.rc != 0 and 'already exists' not in portal_result.stderr
  changed_when: portal_result.rc == 0
  notify: Save targetcli config

- name: Create LUN mapping
  ansible.builtin.command:
    cmd: >-
      targetcli /iscsi/{{ pbs_iscsi_iqn }}/tpg1/luns create
      /backstores/block/{{ pbs_iscsi_backstore_name }}
  register: lun_result
  failed_when: lun_result.rc != 0 and 'already exists' not in lun_result.stderr
  changed_when: lun_result.rc == 0
  notify: Save targetcli config

- name: Configure demo mode (no authentication)
  ansible.builtin.command:
    cmd: >-
      targetcli /iscsi/{{ pbs_iscsi_iqn }}/tpg1 set attribute
      authentication=0
      demo_mode_write_protect=0
      generate_node_acls=1
      cache_dynamic_acls=1
  when: pbs_iscsi_demo_mode
  notify: Save targetcli config
```

#### `handlers/main.yml`

```yaml
---
# PBS iSCSI Role - Handlers

- name: Save targetcli config
  ansible.builtin.command:
    cmd: targetcli saveconfig
  listen: Save targetcli config

- name: Restart target service
  ansible.builtin.systemd:
    name: rtslib-fb-targetctl
    state: restarted
```

### 4.2 Playbook: `deploy-pbs-iscsi.yml`

```yaml
---
# Deploy PBS iSCSI Target for Veeam
# Usage:
#   ansible-playbook playbooks/deploy-pbs-iscsi.yml
#   ansible-playbook playbooks/deploy-pbs-iscsi.yml --tags verify

- name: Deploy PBS iSCSI Target
  hosts: pbs
  become: yes
  roles:
    - role: pbs_iscsi
      tags: [pbs_iscsi]

- name: Verify PBS iSCSI Deployment
  hosts: pbs
  become: yes
  tags: [verify]
  tasks:
    - name: Verify ZVol exists
      ansible.builtin.command:
        cmd: "zfs list {{ pbs_zfs_pool_name }}/{{ pbs_iscsi_zvol_name }}"
      changed_when: false

    - name: Verify ZVol properties
      ansible.builtin.command:
        cmd: "zfs get volsize,volblocksize,compression {{ pbs_zfs_pool_name }}/{{ pbs_iscsi_zvol_name }}"
      changed_when: false
      register: zvol_props

    - name: Display ZVol properties
      ansible.builtin.debug:
        var: zvol_props.stdout_lines

    - name: Verify iSCSI target exists
      ansible.builtin.command:
        cmd: "targetcli ls /iscsi/{{ pbs_iscsi_iqn }}"
      changed_when: false

    - name: Verify iSCSI portal is listening
      ansible.builtin.wait_for:
        port: "{{ pbs_iscsi_portal_port }}"
        timeout: 10

    - name: Display iSCSI target summary
      ansible.builtin.command:
        cmd: "targetcli ls /iscsi"
      changed_when: false
      register: iscsi_summary

    - name: Show iSCSI configuration
      ansible.builtin.debug:
        var: iscsi_summary.stdout_lines
```

### 4.3 Terraform: Windows Server VM

#### `variables.tf` (追加内容)

```hcl
# -----------------------------------------------------------------------------
# Windows Server VM Variables
# -----------------------------------------------------------------------------

variable "windows_vm_name" {
  description = "Windows Server VM name"
  default     = "windows-server"
}

variable "windows_ip_address" {
  description = "Windows Server static IP address"
  type        = string
}

variable "windows_num_cpus" {
  description = "Number of vCPUs for Windows Server"
  default     = 4
}

variable "windows_memory_mb" {
  description = "Memory in MB for Windows Server"
  default     = 8192
}

variable "windows_system_disk_gb" {
  description = "System disk size in GB for Windows Server"
  default     = 60
}
```

#### `windows-server.tf`

```hcl
# =============================================================================
# Windows Server VM Definition (Veeam Host)
# =============================================================================

module "windows_server" {
  source = "../modules/esxi-vm"

  # Basic Configuration
  vm_name          = var.windows_vm_name
  resource_pool_id = data.vsphere_host.host.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id
  network_id       = data.vsphere_network.network.id
  host_system_id   = data.vsphere_host.host.id

  # Hardware Resources
  num_cpus         = var.windows_num_cpus
  memory           = var.windows_memory_mb
  system_disk_size = var.windows_system_disk_gb

  # Firmware & Guest OS
  firmware = "efi"
  guest_id = "windows2019srv_64Guest" # Compatible with Windows Server 2019/2022
}

# -----------------------------------------------------------------------------
# Ansible Inventory Registration
# -----------------------------------------------------------------------------

resource "ansible_host" "windows_server" {
  name   = "windows-server"
  groups = ["esxi_vms", "windows"]

  variables = {
    ansible_host = var.windows_ip_address

    # Windows Ansible connection (WinRM) - requires manual setup first
    # ansible_connection        = "winrm"
    # ansible_winrm_transport   = "ntlm"
    # ansible_winrm_server_cert_validation = "ignore"

    # iSCSI connection info (for future automation)
    iscsi_target_ip  = var.pbs_ip_address
    iscsi_target_iqn = "iqn.2026-02.lan.pbs:veeam"
  }

  depends_on = [module.windows_server]
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "windows_server_vm_id" {
  value       = module.windows_server.vm_id
  description = "Windows Server VM Managed Object ID"
}

output "windows_server_ip" {
  value       = var.windows_ip_address
  description = "Windows Server IP Address"
}
```

## 5. 实施顺序

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: Ansible Role (pbs_iscsi)                               │
├─────────────────────────────────────────────────────────────────┤
│ 1. ansible/roles/pbs_iscsi/defaults/main.yml     ← 先定义变量   │
│ 2. ansible/roles/pbs_iscsi/handlers/main.yml     ← handler      │
│ 3. ansible/roles/pbs_iscsi/tasks/zvol.yml        ← ZVol 任务    │
│ 4. ansible/roles/pbs_iscsi/tasks/iscsi-target.yml← iSCSI 任务   │
│ 5. ansible/roles/pbs_iscsi/tasks/main.yml        ← 主入口       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: Playbook                                               │
├─────────────────────────────────────────────────────────────────┤
│ 6. ansible/playbooks/deploy-pbs-iscsi.yml        ← 部署脚本     │
│    → 语法检查: --syntax-check                                   │
│    → 干跑验证: --check --diff                                   │
│    → 实际部署 (在 PBS 上执行)                                   │
│    → 验证部署: --tags verify                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: Terraform (可与 Phase 2 并行)                          │
├─────────────────────────────────────────────────────────────────┤
│ 7. terraform/esxi/variables.tf                   ← 追加变量     │
│ 8. terraform/esxi/windows-server.tf              ← VM 定义      │
│    → terraform validate                                         │
│    → terraform plan                                             │
│    → terraform apply (创建 VM shell)                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 4: 手动配置 (Windows 端)                                  │
├─────────────────────────────────────────────────────────────────┤
│ 9.  安装 Windows Server (从 ISO)                                │
│ 10. 配置静态 IP                                                 │
│ 11. iSCSI Initiator → 连接 PBS IP                               │
│ 12. 磁盘管理 → GPT 初始化 → ReFS 格式化 (64K 分配单元)          │
│ 13. 安装 Veeam VBR Community Edition                            │
│ 14. 配置 Backup Repository (ReFS 卷)                            │
└─────────────────────────────────────────────────────────────────┘
```

## 6. 验证方法

### 6.1 Ansible 验证

```bash
# 语法检查
ansible-playbook ansible/playbooks/deploy-pbs-iscsi.yml --syntax-check

# 干跑模式 (不实际执行)
ansible-playbook ansible/playbooks/deploy-pbs-iscsi.yml --check --diff

# 部署后验证
ansible-playbook ansible/playbooks/deploy-pbs-iscsi.yml --tags verify
```

### 6.2 手动验证命令 (在 PBS 上执行)

```bash
# 检查 ZVol
zfs list backup-pool/veeam-vol
zfs get volsize,volblocksize,compression backup-pool/veeam-vol

# 检查 iSCSI Target
targetcli ls /iscsi
ss -tlnp | grep 3260

# 检查设备
ls -la /dev/zvol/backup-pool/veeam-vol
```

### 6.3 Terraform 验证

```bash
cd terraform/esxi

# 格式检查
terraform fmt -check

# 语法验证
terraform validate

# 计划预览
terraform plan
```

### 6.4 Windows 端验证

1. **iSCSI Initiator** → Quick Connect → 输入 PBS IP → 应显示 Target
2. **磁盘管理** → 应出现 2TB 未初始化磁盘
3. **Veeam Repository** → 添加 ReFS 卷后，检查 Fast Clone 是否启用

## 7. 后续工作

### 7.1 Windows Ansible 自动化 (Phase 2)

计划通过 `ansible.windows` collection 自动化以下任务：

```yaml
# 未来的 windows-iscsi role 草案
- name: Start iSCSI Initiator service
  win_service:
    name: MSiSCSI
    start_mode: auto
    state: started

- name: Connect to iSCSI target
  win_shell: |
    New-IscsiTargetPortal -TargetPortalAddress {{ iscsi_target_ip }}
    Connect-IscsiTarget -NodeAddress {{ iscsi_target_iqn }} -IsPersistent $true

- name: Initialize and format disk
  win_shell: |
    $disk = Get-Disk | Where-Object { $_.OperationalStatus -eq 'Offline' }
    Set-Disk -Number $disk.Number -IsOffline $false
    Initialize-Disk -Number $disk.Number -PartitionStyle GPT
    New-Partition -DiskNumber $disk.Number -UseMaximumSize -AssignDriveLetter |
      Format-Volume -FileSystem ReFS -AllocationUnitSize 65536 -NewFileSystemLabel "VeeamRepo"
```

### 7.2 可选增强

- **ZFS 空间监控**: 添加 Prometheus exporter 或简单的 cron 告警脚本
- **iSCSI ACL**: 如需提高安全性，可配置 initiator IQN 白名单
- **自动扩容**: 监控 ZVol 使用率，达到阈值时自动扩容

### 7.3 相关文档更新

部署完成后需更新：
- `docs/deployment/pbs_iscsi_veeam_guide.md` — 标记实施状态为"已完成"
- `ansible/README.md` — 添加 `pbs_iscsi` role 说明
