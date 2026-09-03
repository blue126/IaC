---
title: 'PBS iSCSI Target for Veeam'
slug: 'pbs-iscsi-veeam'
created: '2026-02-03'
status: 'completed'
stepsCompleted: [1, 2, 3, 4]
final_spec: 'docs/specs/pbs-iscsi-veeam-spec.md'
tech_stack: [ansible, terraform, zfs, iscsi, targetcli]
files_to_modify:
  - ansible/roles/pbs_iscsi/tasks/main.yml
  - ansible/roles/pbs_iscsi/defaults/main.yml
  - ansible/playbooks/deploy-pbs-iscsi.yml
  - terraform/esxi/windows-server.tf
  - terraform/esxi/variables.tf
code_patterns:
  - existing pbs role structure
  - esxi-vm terraform module
test_patterns:
  - ansible verify play with wait_for
---

# Tech-Spec: PBS iSCSI Target for Veeam

**Created:** 2026-02-03

## Overview

### Problem Statement

T7910 冷备份服务器上的 PBS VM 通过 HBA 直通独占物理硬盘。需要在不改变硬件配置的情况下，让同主机的 Windows Server VM 能够使用底层 ZFS 存储空间运行 Veeam VBR。

### Solution

在 PBS 的 ZFS 存储池上创建 ZVol，通过 LIO iSCSI Target 服务共享给 Windows Server。Windows 将 iSCSI 盘格式化为 ReFS，供 Veeam 使用 Fast Clone 功能。

### Scope

**In Scope:**
- 创建 `pbs_iscsi` Ansible role（ZVol + iSCSI Target 配置）
- 创建 Windows Server VM 的 Terraform 定义
- 部署 playbook 和验证任务

**Out of Scope:**
- Windows 内部配置（iSCSI initiator、ReFS 格式化、Veeam 安装）—— 本期手动，后续自动化
- Veeam 备份作业调度配置
- ZFS quota 或空间告警

## Context for Development

### Codebase Patterns

- Ansible role 遵循标准结构：`tasks/main.yml`, `defaults/main.yml`, `handlers/main.yml`
- Terraform 每个服务一个 `.tf` 文件，包含 module 调用 + ansible_host + outputs
- 变量命名：`pbs_iscsi_*` 前缀
- Playbook 必须包含 `[verify]` tagged play

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `ansible/roles/pbs/tasks/zfs-pool.yml` | ZFS 操作模式参考 |
| `ansible/roles/pbs/defaults/main.yml` | 变量命名风格参考 |
| `terraform/esxi/pbs.tf` | ESXi VM 定义模式参考 |
| `terraform/modules/esxi-vm/` | VM module 接口 |

### Technical Decisions

| 决策点 | 选择 | 理由 |
|--------|------|------|
| ZVol 大小 | 固定 2TB | 简单，后续手动扩容 (`zfs set volsize=`) |
| iSCSI 认证 | Demo 模式（无 ACL） | 内网环境，简单优先 |
| ZVol blocksize | 64K | iSCSI + ReFS 最佳实践 |
| IQN 命名 | `iqn.2026-02.lan.pbs:veeam` | 遵循 RFC 3720 |

## Implementation Plan

### 文件清单

```
ansible/
  roles/
    pbs_iscsi/
      tasks/
        main.yml          # 主入口
        zvol.yml          # ZVol 创建
        iscsi-target.yml  # iSCSI 配置
      defaults/
        main.yml          # 变量定义
      handlers/
        main.yml          # 服务重启
  playbooks/
    deploy-pbs-iscsi.yml  # 部署 playbook

terraform/
  esxi/
    windows-server.tf     # Windows VM 定义
    variables.tf          # 新增变量（追加）
```

### Tasks

#### Phase 1: Ansible Role `pbs_iscsi`

**1.1 `defaults/main.yml`** — 变量定义

```yaml
# ZVol Configuration
pbs_iscsi_zvol_name: "veeam-vol"
pbs_iscsi_zvol_size: "2T"
pbs_iscsi_zvol_blocksize: "64K"
pbs_iscsi_zvol_compression: "lz4"

# iSCSI Target Configuration
pbs_iscsi_iqn: "iqn.2026-02.lan.pbs:veeam"
pbs_iscsi_portal_ip: "0.0.0.0"
pbs_iscsi_portal_port: 3260

# 依赖现有 pbs role 的变量
# pbs_zfs_pool_name (from pbs role)
```

**1.2 `tasks/main.yml`** — 主入口

```yaml
- include_tasks: zvol.yml
  tags: [zvol]

- include_tasks: iscsi-target.yml
  tags: [iscsi]
```

**1.3 `tasks/zvol.yml`** — ZVol 创建

关键任务：
- 安装 ZFS 工具（若未安装）
- 检查 ZVol 是否存在
- 创建 ZVol：`zfs create -V {{ size }} -s -o volblocksize=64K -o compression=lz4 {{ pool }}/{{ name }}`
- `-s` = sparse（精简置备）

**1.4 `tasks/iscsi-target.yml`** — iSCSI 配置

关键任务：
- 安装 `targetcli-fb`
- 创建 backstore：`/backstores/block create {{ name }} /dev/zvol/{{ pool }}/{{ zvol }}`
- 创建 IQN：`/iscsi create {{ iqn }}`
- 创建 portal：`/iscsi/{{ iqn }}/tpg1/portals create {{ ip }} {{ port }}`
- 创建 LUN：`/iscsi/{{ iqn }}/tpg1/luns create /backstores/block/{{ name }}`
- 设置 demo 模式：`/iscsi/{{ iqn }}/tpg1 set attribute authentication=0 demo_mode_write_protect=0 generate_node_acls=1 cache_dynamic_acls=1`
- 保存配置：`saveconfig`
- Enable target 服务

**1.5 `handlers/main.yml`**

```yaml
- name: Restart target service
  systemd:
    name: rtslib-fb-targetctl
    state: restarted
    enabled: yes
```

#### Phase 2: Playbook

**2.1 `playbooks/deploy-pbs-iscsi.yml`**

```yaml
- name: Deploy PBS iSCSI Target
  hosts: pbs
  become: yes
  roles:
    - pbs_iscsi

- name: Verify PBS iSCSI Deployment
  hosts: pbs
  become: yes
  tags: [verify]
  tasks:
    - name: Check ZVol exists
      command: zfs list {{ pbs_zfs_pool_name }}/{{ pbs_iscsi_zvol_name }}
      changed_when: false
      
    - name: Check iSCSI target is active
      command: targetcli ls /iscsi/{{ pbs_iscsi_iqn }}
      changed_when: false
      
    - name: Check iSCSI portal is listening
      wait_for:
        port: 3260
        timeout: 10
```

#### Phase 3: Terraform (Windows Server VM)

**3.1 `variables.tf`** — 追加变量

```hcl
variable "windows_vm_name" {
  default = "windows-server"
}
variable "windows_ip_address" {
  type = string
}
variable "windows_num_cpus" {
  default = 4
}
variable "windows_memory_mb" {
  default = 8192
}
variable "windows_system_disk_gb" {
  default = 60
}
```

**3.2 `windows-server.tf`** — VM 定义

```hcl
module "windows_server" {
  source = "../modules/esxi-vm"

  vm_name          = var.windows_vm_name
  resource_pool_id = data.vsphere_host.host.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id
  network_id       = data.vsphere_network.network.id
  host_system_id   = data.vsphere_host.host.id

  num_cpus         = var.windows_num_cpus
  memory           = var.windows_memory_mb
  system_disk_size = var.windows_system_disk_gb

  firmware = "efi"
  guest_id = "windows2019srv_64Guest"  # Windows Server 2019/2022
}

resource "ansible_host" "windows_server" {
  name   = "windows-server"
  groups = ["esxi_vms", "windows"]
  variables = {
    ansible_host = var.windows_ip_address
    # Windows Ansible 连接需要额外配置（WinRM），暂不启用
  }
  depends_on = [module.windows_server]
}

output "windows_server_vm_id" {
  value = module.windows_server.vm_id
}
```

### 实施顺序

```
1. ansible/roles/pbs_iscsi/defaults/main.yml     # 先定义变量
2. ansible/roles/pbs_iscsi/handlers/main.yml     # handler 定义
3. ansible/roles/pbs_iscsi/tasks/zvol.yml        # ZVol 任务
4. ansible/roles/pbs_iscsi/tasks/iscsi-target.yml # iSCSI 任务
5. ansible/roles/pbs_iscsi/tasks/main.yml        # 主入口
6. ansible/playbooks/deploy-pbs-iscsi.yml        # Playbook
   ↓ 验证通过后
7. terraform/esxi/variables.tf                   # 追加变量
8. terraform/esxi/windows-server.tf              # VM 定义
```

### Acceptance Criteria

```gherkin
Feature: PBS iSCSI Target for Veeam

  Scenario: ZVol 创建成功
    Given PBS VM 已运行且 ZFS pool "backup-pool" 存在
    When 执行 `ansible-playbook deploy-pbs-iscsi.yml`
    Then `zfs list backup-pool/veeam-vol` 返回成功
    And volsize = 2T, volblocksize = 64K

  Scenario: iSCSI Target 可访问
    Given ZVol 已创建
    When iSCSI target 配置完成
    Then `ss -tlnp | grep 3260` 显示监听
    And `targetcli ls /iscsi` 显示 iqn.2026-02.lan.pbs:veeam

  Scenario: Windows 可连接 iSCSI 盘
    Given iSCSI target 运行中
    When Windows iSCSI Initiator 连接 PBS IP
    Then 磁盘管理中出现 2TB 未初始化磁盘

  Scenario: Terraform 创建 Windows VM
    Given ESXi 数据存储有足够空间
    When 执行 `terraform apply`
    Then VM "windows-server" 创建成功
    And ansible inventory 包含 windows-server 主机
```

## Additional Context

### Dependencies

- PBS VM 已部署且 ZFS pool `backup-pool` 存在
- PBS IP 地址已知（当前 `192.168.1.249`）
- Windows Server ISO 已上传到 ESXi datastore（手动步骤）
- Windows Server License 已准备

### Testing Strategy

1. **Ansible Dry-run**: `ansible-playbook deploy-pbs-iscsi.yml --check --diff`
2. **Verify Play**: `ansible-playbook deploy-pbs-iscsi.yml --tags verify`
3. **手动验证**: 从 Windows 连接 iSCSI 目标，确认能看到磁盘
4. **Terraform Plan**: `terraform plan` 确认资源正确

### Notes

- ZVol 扩容命令：`zfs set volsize=3T backup-pool/veeam-vol`
- 如需启用 ACL，后续添加变量 `pbs_iscsi_acl_enabled` 和 initiator IQN 配置
- Windows Ansible 自动化需配置 WinRM，考虑使用 `ansible.windows` collection
- ESXi VM 启动顺序：PBS 先启动，Windows 延迟 120s
