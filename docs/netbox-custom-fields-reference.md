# NetBox Custom Fields 参考文档

**创建日期**: 2026-02-09  
**Story**: 1.1 - 定义核心 Custom Fields  
**状态**: ✅ 已完成

---

## 概述

本文档定义了 6 个核心 Custom Fields，用于驱动 Infrastructure as Data 自动化流程。这些字段应用于 `virtualization.virtualmachine` 和 `dcim.device` 对象类型。

---

## Custom Fields 列表

### 1. `infrastructure_platform` (基础设施平台)

**用途**: 决定 Router Pipeline 的路由目标

| 属性 | 值 |
|------|-----|
| **Type** | Selection |
| **Required** | ✅ Yes |
| **Default** | `proxmox` |
| **Choices** | `proxmox`, `esxi`, `physical` |
| **Object Types** | Virtual Machine, Device |
| **Group** | Automation |
| **Weight** | 100 |

**描述**: 定义资源的目标基础设施平台。Router Pipeline 读取此字段后路由到对应的 Platform-specific Pipeline。

**路由逻辑**:
- `proxmox` → Proxmox Provisioning Pipeline
- `esxi` → ESXi Provisioning Pipeline
- `physical` → Physical Device Sync Pipeline (跳过 Terraform)

---

### 2. `automation_level` (自动化级别)

**用途**: 控制自动化流程的审批行为

| 属性 | 值 |
|------|-----|
| **Type** | Selection |
| **Required** | ✅ Yes |
| **Default** | `requires_approval` |
| **Choices** | `fully_automated`, `requires_approval`, `manual_only` |
| **Object Types** | Virtual Machine, Device |
| **Group** | Automation |
| **Weight** | 110 |

**描述**: 控制 Terraform Apply 是否需要人工审批。

**审批逻辑**:
- `fully_automated`: Terraform Apply 无需人工审批（测试环境）
- `requires_approval`: Terraform Plan 后暂停，等待人工审批（生产环境推荐）
- `manual_only`: 跳过所有自动化，仅更新 Inventory（仅文档用途）

---

### 3. `proxmox_node` (Proxmox 节点)

**用途**: 指定 Proxmox VE 集群中的目标节点

| 属性 | 值 |
|------|-----|
| **Type** | Selection |
| **Required** | ❌ No (条件必填) |
| **Default** | - |
| **Choices** | `pve0`, `pve1`, `pve2` |
| **Object Types** | Virtual Machine |
| **Group** | Proxmox Configuration |
| **Weight** | 200 |

**描述**: 指定 Terraform 将在哪个 Proxmox 节点上创建 VM/LXC。

**使用场景**:
- 仅当 `infrastructure_platform=proxmox` 时必填
- 根据负载均衡或资源可用性选择目标节点
- 未来可扩展为自动负载均衡选择

---

### 4. `proxmox_vmid` (Proxmox VMID)

**用途**: Proxmox 资源的唯一标识符

| 属性 | 值 |
|------|-----|
| **Type** | Integer |
| **Required** | ❌ No (条件必填) |
| **Default** | - |
| **Validation** | Min: 100, Max: 999 |
| **Object Types** | Virtual Machine |
| **Group** | Proxmox Configuration |
| **Weight** | 210 |

**描述**: Proxmox 资源的唯一 ID，必须在集群中全局唯一。

**VMID 分配策略**:
- **100-199**: LXC 容器
- **200-299**: QEMU VM (基础设施)
- **300-399**: QEMU VM (应用服务)

**示例**:
- Anki LXC: 150
- Caddy LXC: 110
- NetBox VM: 201

---

### 5. `ansible_groups` (Ansible 组)

**用途**: 定义资源所属的 Ansible 组

| 属性 | 值 |
|------|-----|
| **Type** | Multiple Selection |
| **Required** | ❌ No |
| **Default** | - |
| **Choices** | `pve_vms`, `pve_lxc`, `docker`, `tailscale`, `backup_client`, `monitoring_target` |
| **Object Types** | Virtual Machine, Device |
| **Group** | Ansible Configuration |
| **Weight** | 300 |

**描述**: Terraform 的 `ansible_host` 资源根据此字段自动分组，最终体现在 Ansible Dynamic Inventory 中。

**常用组说明**:
- `pve_vms`: Proxmox QEMU 虚拟机
- `pve_lxc`: Proxmox LXC 容器
- `docker`: 安装 Docker 的主机
- `tailscale`: 加入 Tailscale VPN 的主机
- `backup_client`: PBS 备份客户端
- `monitoring_target`: 监控目标主机

---

### 6. `playbook_name` (Playbook 名称)

**用途**: 指定关联的 Ansible Playbook 文件名

| 属性 | 值 |
|------|-----|
| **Type** | Text |
| **Required** | ❌ No |
| **Default** | - (根据 `ansible_groups` 自动推导) |
| **Object Types** | Virtual Machine, Device |
| **Group** | Ansible Configuration |
| **Weight** | 310 |

**描述**: 显式指定 Ansible Playbook 文件名（不含 `.yml` 后缀）。如果留空，Pipeline 根据 `ansible_groups` 自动推导。

**自动推导逻辑**:
- `ansible_groups` 包含 `docker` → 使用 `deploy-docker.yml`
- `ansible_groups` 包含 `netbox` → 使用 `deploy-netbox.yml`
- 可显式指定覆盖自动推导

**示例**:
- `deploy-netbox`
- `deploy-caddy`
- `sync-to-notion`

---

## 使用场景示例

### 场景 1: 创建 Proxmox LXC 容器 (完全自动化)

```json
{
  "name": "anki-sync-server",
  "cluster": 1,
  "status": "planned",
  "memory": 512,
  "vcpus": 1,
  "custom_fields": {
    "infrastructure_platform": "proxmox",
    "automation_level": "fully_automated",
    "proxmox_node": "pve0",
    "proxmox_vmid": 150,
    "ansible_groups": ["pve_lxc", "docker"],
    "playbook_name": null
  }
}
```

**预期流程**:
1. Webhook 触发 Router Pipeline
2. Router 识别 `platform=proxmox`，触发 Proxmox Pipeline
3. Terraform Apply 自动执行（无需审批）
4. Ansible 部署 Docker 和应用
5. 验证通过，状态变为 `active`

---

### 场景 2: 创建生产 VM (需要审批)

```json
{
  "name": "netbox-prod",
  "cluster": 1,
  "status": "planned",
  "memory": 2048,
  "vcpus": 2,
  "custom_fields": {
    "infrastructure_platform": "proxmox",
    "automation_level": "requires_approval",
    "proxmox_node": "pve1",
    "proxmox_vmid": 300,
    "ansible_groups": ["pve_vms", "monitoring_target"],
    "playbook_name": "deploy-netbox"
  }
}
```

**预期流程**:
1. Webhook 触发 Router Pipeline
2. Terraform Plan 生成变更预览
3. ⚠️ Pipeline 暂停，等待人工审批
4. 用户检查 Plan 后点击 "Approve"
5. Terraform Apply 执行
6. Ansible 部署 NetBox
7. 验证通过

---

### 场景 3: 物理服务器配置管理

```json
{
  "name": "pbs-backup-server",
  "device_type": 2,
  "role": 4,
  "site": 1,
  "status": "planned",
  "custom_fields": {
    "infrastructure_platform": "physical",
    "automation_level": "manual_only",
    "ansible_groups": ["backup_client"],
    "playbook_name": null
  }
}
```

**预期流程**:
1. Webhook 触发 Router Pipeline
2. Router 识别 `platform=physical`，触发 Physical Device Sync Pipeline
3. ❌ 跳过 Terraform（物理服务器无需 provisioning）
4. ✅ 从 NetBox 生成 Ansible Inventory
5. Ansible 执行配置管理（安装软件、配置服务）

---

## API 查询示例

### 查询所有 Proxmox 平台的 Planned 状态虚拟机

```bash
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?status=planned&cf_infrastructure_platform=proxmox"
```

### 查询需要审批的虚拟机

```bash
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_automation_level=requires_approval"
```

### 查询特定节点的虚拟机

```bash
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_proxmox_node=pve0"
```

### 查询属于 docker 组的所有资源

```bash
# 虚拟机
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_ansible_groups=docker"

# 物理设备
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/dcim/devices/?cf_ansible_groups=docker"
```

---

## 故障排查

### 问题 1: 创建虚拟机时提示 "This field is required"

**原因**: `infrastructure_platform` 或 `automation_level` 未填写（必填字段）

**解决方法**: 确保两个必填字段都有值

---

### 问题 2: Terraform Plan 显示 `proxmox_node` 为 null

**原因**: 虚拟机的 `infrastructure_platform=proxmox` 但 `proxmox_node` 未填写

**解决方法**: 编辑虚拟机，设置 `proxmox_node` 为 `pve0`/`pve1`/`pve2` 之一

---

### 问题 3: VMID 冲突

**错误**: Terraform Apply 失败，提示 "VMID 199 already exists"

**解决方法**: 
1. 查询已使用的 VMID: `pvesh get /cluster/resources --type vm`
2. 在 NetBox 中修改虚拟机的 `proxmox_vmid` 为未使用的 ID

---

## 相关文档

- **Story 1.1**: `/workspaces/IaC/_bmad-output/implementation-artifacts/1-1-定义核心-custom-fields.md`
- **Architecture ADR-005**: NetBox 数据建模策略
- **PRD**: FR3, FR4, FR5 - Custom Fields 功能性需求

---

## Changelog

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-02-09 | 初始创建，定义 6 个核心 Custom Fields | AI Agent |
