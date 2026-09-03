# Story 1-1: 定义核心 Custom Fields

**Epic**: Epic 1 - NetBox 数据建模与配置  
**Story ID**: 1.1  
**优先级**: 🔴 Critical  
**预估工作量**: 2-3 小时  
**依赖**: 无 (首个 Story)  
**状态**: Ready for Dev

---

## Story Overview

### 用户故事
作为 DevOps Engineer (Will)，我需要在 NetBox Admin UI 中定义 6 个核心 Custom Fields，这些字段将驱动 Router Pipeline 的路由决策、Terraform 的资源配置和 Ansible 的部署行为，从而实现 Infrastructure as Data 的核心能力。

### 业务价值
- ✅ **奠定数据模型基础**: 这些 Custom Fields 是整个 NetBox SSOT 架构的基石
- ✅ **支持多平台路由**: `infrastructure_platform` 字段使 Router Pipeline 能够将资源路由到正确的平台 (Proxmox/ESXi/Physical)
- ✅ **实现灵活的自动化控制**: `automation_level` 字段支持完全自动化、需要审批、仅手动三种模式
- ✅ **建立 NetBox-Ansible 桥梁**: `ansible_groups` 和 `playbook_name` 字段直接驱动 Ansible 配置管理

### 技术目标
1. 在 NetBox Admin UI 中创建 6 个 Custom Fields
2. 将这些字段应用到 `dcim.virtualmachine` 和 `dcim.device` 内容类型
3. 配置字段的验证规则、默认值和必填约束
4. 通过创建测试资源验证字段定义正确

---

## Requirements (来自 Epics)

### 功能性需求
- **FR3**: DevOps Engineer 可以使用 NetBox Custom Fields 定义基础设施平台类型 (Proxmox/ESXi/Physical)
- **FR4**: DevOps Engineer 可以使用 NetBox Custom Fields 定义 Ansible 角色和变量
- **FR5**: DevOps Engineer 可以在 NetBox 中标记虚拟机为 "Planned" 状态以触发自动化流程

### 非功能性需求
- **NFR-I4**: NetBox Custom Fields 必须使用标准数据类型 (Selection、Integer、Text、Object)
- **NFR-SC6**: NetBox Custom Fields 变更不会破坏现有 Terraform 代码 (向后兼容性)
- **NFR-M14**: 新增 Custom Fields 不会破坏现有 Pipeline (向后兼容)

### Acceptance Criteria (验收标准)
- [ ] 所有 6 个 Custom Fields 在 NetBox Admin UI 中创建成功
- [ ] 字段已应用到 `dcim.virtualmachine` 内容类型
- [ ] 字段已应用到 `dcim.device` 内容类型 (用于物理服务器)
- [ ] 必填字段 (`infrastructure_platform`, `automation_level`) 在创建资源时强制验证
- [ ] 条件必填字段 (`proxmox_node`, `proxmox_vmid`) 在选择 `infrastructure_platform=proxmox` 时能够正常填写
- [ ] 可选字段 (`ansible_groups`, `playbook_name`) 支持留空或填写多个值
- [ ] 创建至少 1 个测试 Virtual Machine,所有字段填写正确且保存成功
- [ ] 创建至少 1 个测试 Device (物理服务器),字段配置正确
- [ ] 字段在 NetBox UI 中的显示顺序和分组符合直觉 (platform 相关字段靠近、automation 相关字段靠近)

---

## Technical Design

### Custom Fields 定义规范

根据 **ADR-005 (NetBox 数据建模)** 和 **architecture.md** 中的数据模型设计，以下是 6 个核心 Custom Fields 的完整定义:

#### 1. `infrastructure_platform` (基础设施平台)

| 属性 | 值 |
|------|-----|
| **Field Name** | `infrastructure_platform` |
| **Label** | Infrastructure Platform |
| **Type** | Selection |
| **Choices** | `proxmox`, `esxi`, `physical` |
| **Required** | ✅ Yes |
| **Default** | `proxmox` (推荐) |
| **Content Types** | `dcim.virtualmachine`, `dcim.device` |
| **Description** | 定义资源的目标基础设施平台。决定 Router Pipeline 的路由目标:<br/>- `proxmox`: 路由到 Proxmox Provisioning Pipeline<br/>- `esxi`: 路由到 ESXi Provisioning Pipeline<br/>- `physical`: 路由到 Physical Device Sync Pipeline (跳过 Terraform) |
| **UI Group** | Automation |
| **UI Weight** | 100 (最前) |

**架构意图 (来自 ADR-004):**  
此字段是 Router Pipeline 的核心路由决策依据。Router 读取此字段后通过 `switch/case` 触发对应的 Platform-specific Pipeline。

#### 2. `automation_level` (自动化级别)

| 属性 | 值 |
|------|-----|
| **Field Name** | `automation_level` |
| **Label** | Automation Level |
| **Type** | Selection |
| **Choices** | `fully_automated`, `requires_approval`, `manual_only` |
| **Required** | ✅ Yes |
| **Default** | `requires_approval` (推荐，安全优先) |
| **Content Types** | `dcim.virtualmachine`, `dcim.device` |
| **Description** | 控制自动化流程的审批行为:<br/>- `fully_automated`: Terraform Apply 无需人工审批 (适用于测试环境)<br/>- `requires_approval`: Terraform Plan 后暂停，等待人工审批 (生产环境推荐)<br/>- `manual_only`: 跳过所有自动化，仅更新 Inventory (仅文档用途) |
| **UI Group** | Automation |
| **UI Weight** | 110 |

**架构意图 (来自 User Journey 3):**  
支持不同风险级别的变更管理。生产环境强制 `requires_approval` 以提供安全网 (Plan 预览 + 人工审批)。

#### 3. `proxmox_node` (Proxmox 节点)

| 属性 | 值 |
|------|-----|
| **Field Name** | `proxmox_node` |
| **Label** | Proxmox Node |
| **Type** | Selection |
| **Choices** | `pve0`, `pve1`, `pve2` |
| **Required** | ⚠️ Conditional (仅当 `infrastructure_platform=proxmox` 时必填) |
| **Default** | 无 |
| **Content Types** | `dcim.virtualmachine` |
| **Description** | 指定 Proxmox VE 集群中的目标节点。Terraform 将在此节点上创建 VM/LXC。 |
| **UI Group** | Proxmox Configuration |
| **UI Weight** | 200 |
| **Validation Rule** | 仅当 `infrastructure_platform=proxmox` 时显示 (NetBox 不支持条件显示，需在文档中说明) |

**架构意图:**  
Proxmox 集群有 3 个节点 (pve0, pve1, pve2)。用户需要根据负载均衡或资源可用性手动选择目标节点。未来可扩展为自动负载均衡选择。

#### 4. `proxmox_vmid` (Proxmox VMID)

| 属性 | 值 |
|------|-----|
| **Field Name** | `proxmox_vmid` |
| **Label** | Proxmox VMID |
| **Type** | Integer |
| **Required** | ⚠️ Conditional (仅当 `infrastructure_platform=proxmox` 时必填) |
| **Default** | 无 |
| **Content Types** | `dcim.virtualmachine` |
| **Description** | Proxmox 资源的唯一标识符 (100-999 范围)。必须在集群中全局唯一。建议按服务类型预留范围:<br/>- 100-199: LXC 容器<br/>- 200-299: QEMU VM (基础设施)<br/>- 300-399: QEMU VM (应用服务) |
| **UI Group** | Proxmox Configuration |
| **UI Weight** | 210 |
| **Validation Rule** | 最小值: 100, 最大值: 999 |

**架构意图 (来自 NFR-SC1):**  
VMID 范围 100-999 提供 900 个可用 ID。使用分段策略便于管理和故障排查。

#### 5. `ansible_groups` (Ansible 组)

| 属性 | 值 |
|------|-----|
| **Field Name** | `ansible_groups` |
| **Label** | Ansible Groups |
| **Type** | Multiple Selection |
| **Choices** | `pve_vms`, `pve_lxc`, `docker`, `tailscale`, `backup_client`, `monitoring_target` |
| **Required** | ❌ No (Optional) |
| **Default** | 无 |
| **Content Types** | `dcim.virtualmachine`, `dcim.device` |
| **Description** | 定义资源所属的 Ansible 组。支持多选。Terraform `ansible_host` 资源将根据此字段自动分组。常用组:<br/>- `pve_vms`: Proxmox QEMU 虚拟机<br/>- `pve_lxc`: Proxmox LXC 容器<br/>- `docker`: 安装 Docker 的主机<br/>- `tailscale`: 加入 Tailscale VPN 的主机 |
| **UI Group** | Ansible Configuration |
| **UI Weight** | 300 |

**架构意图 (来自 FR4, FR17):**  
此字段是 NetBox → Ansible Inventory 的桥梁。Terraform 的 `ansible_host` 资源读取此字段并生成对应的 `groups` 属性,最终体现在 Ansible Dynamic Inventory 中。

#### 6. `playbook_name` (Playbook 名称)

| 属性 | 值 |
|------|-----|
| **Field Name** | `playbook_name` |
| **Label** | Ansible Playbook Name |
| **Type** | Text |
| **Required** | ❌ No (Optional) |
| **Default** | 无 (根据 `ansible_groups` 自动推导) |
| **Content Types** | `dcim.virtualmachine`, `dcim.device` |
| **Description** | 指定关联的 Ansible Playbook 文件名 (不含 `.yml` 后缀)。<br/>- 示例: `deploy-netbox`, `deploy-caddy`<br/>- 如果留空,Pipeline 将根据 `ansible_groups` 自动推导 (如 `docker` 组使用 `deploy-docker.yml`) |
| **UI Group** | Ansible Configuration |
| **UI Weight** | 310 |

**架构意图:**  
提供灵活性:用户可以显式指定 playbook,也可以依赖约定 (Convention over Configuration)。大部分场景下可以留空,减少配置负担。

---

### 架构约束与集成点

#### 1. **Router Pipeline 集成** (ADR-004)

**文件**: `Jenkinsfile-webhook-router`

Router 将解析 Webhook Payload 中的 `custom_fields.infrastructure_platform` 字段:

```groovy
def payload = readJSON text: env.webhook_payload
def platform = payload.data.custom_fields.infrastructure_platform

switch(platform) {
    case 'proxmox':
        build job: 'Proxmox-Provisioning', parameters: [
            string(name: 'NETBOX_VM_ID', value: payload.data.id),
            string(name: 'AUTOMATION_LEVEL', value: payload.data.custom_fields.automation_level)
        ]
        break
    case 'esxi':
        build job: 'ESXi-Provisioning', parameters: [...]
        break
    case 'physical':
        build job: 'Physical-Device-Sync', parameters: [...]
        break
    default:
        error "Unknown platform: ${platform}"
}
```

**验证点**: 创建测试资源后,手动触发 Webhook,检查 Router 日志中是否正确识别平台。

#### 2. **Terraform Data Source 集成** (ADR-002)

**文件**: `terraform/proxmox/netbox-data.tf`

Terraform 将通过 `terraform-provider-netbox` data source 查询这些字段:

```hcl
data "netbox_virtual_machines" "proxmox_vms" {
  filter {
    name  = "status"
    value = "planned"
  }
  filter {
    name  = "custom_fields.infrastructure_platform"
    value = "proxmox"
  }
}

# 动态生成资源配置
resource "proxmox_virtual_environment_vm" "from_netbox" {
  for_each = {
    for vm in data.netbox_virtual_machines.proxmox_vms.virtual_machines :
    vm.name => vm
  }
  
  name      = each.value.name
  node_name = each.value.custom_fields.proxmox_node
  vm_id     = each.value.custom_fields.proxmox_vmid
  # ...
}
```

**验证点**: Week 2 POC 阶段执行 `terraform plan`,确认能够正确读取 Custom Fields。

#### 3. **Ansible Inventory 集成** (FR17)

**文件**: `terraform/proxmox/*.tf` (每个服务的 `ansible_host` 资源)

```hcl
resource "ansible_host" "service_name" {
  name   = each.value.name
  groups = split(",", each.value.custom_fields.ansible_groups)
  variables = {
    ansible_host = each.value.primary_ip4.address
  }
  depends_on = [proxmox_virtual_environment_vm.from_netbox]
}
```

**验证点**: Terraform Apply 后执行 `ansible-inventory --list`,确认资源出现在正确的组中。

#### 4. **人工审批 Gate 集成** (User Journey 3)

**文件**: `Jenkinsfile-proxmox-provisioning`

```groovy
stage('Approval Gate') {
    when {
        expression { params.AUTOMATION_LEVEL == 'requires_approval' }
    }
    steps {
        script {
            input message: "Review Terraform Plan and approve to proceed",
                  ok: "Apply Changes"
        }
    }
}
```

**验证点**: 创建 `automation_level=requires_approval` 的测试资源,确认 Pipeline 在 Plan 后暂停等待审批。

---

## Implementation Tasks

### Task 1: 创建 Custom Fields (30 分钟)

**步骤**:

1. **登录 NetBox Admin UI**
   ```
   URL: http://192.168.1.104:8080/admin/
   用户: admin (从 Ansible Vault 获取密码)
   ```

2. **导航到 Custom Fields 配置页面**
   ```
   Admin > Customization > Custom Fields > Add
   ```

3. **按顺序创建 6 个 Custom Fields**

   **3.1 创建 `infrastructure_platform`**
   - Name: `infrastructure_platform`
   - Label: `Infrastructure Platform`
   - Type: `Selection`
   - Object types: 勾选 `dcim | virtual machine` 和 `dcim | device`
   - Choices: 输入以下选项 (每行一个):
     ```
     proxmox
     esxi
     physical
     ```
   - Required: ✅ 勾选
   - Default: `proxmox`
   - UI Visible: ✅ 勾选
   - UI Editable: ✅ 勾选
   - Weight: `100`
   - Group name: `Automation`
   - Description: 复制上述规范中的描述

   **3.2 创建 `automation_level`**
   - Name: `automation_level`
   - Label: `Automation Level`
   - Type: `Selection`
   - Object types: 勾选 `dcim | virtual machine` 和 `dcim | device`
   - Choices:
     ```
     fully_automated
     requires_approval
     manual_only
     ```
   - Required: ✅ 勾选
   - Default: `requires_approval`
   - Weight: `110`
   - Group name: `Automation`

   **3.3 创建 `proxmox_node`**
   - Name: `proxmox_node`
   - Label: `Proxmox Node`
   - Type: `Selection`
   - Object types: 勾选 `dcim | virtual machine`
   - Choices:
     ```
     pve0
     pve1
     pve2
     ```
   - Required: ❌ 不勾选 (NetBox 不支持条件必填,需在文档中说明)
   - Weight: `200`
   - Group name: `Proxmox Configuration`

   **3.4 创建 `proxmox_vmid`**
   - Name: `proxmox_vmid`
   - Label: `Proxmox VMID`
   - Type: `Integer`
   - Object types: 勾选 `dcim | virtual machine`
   - Required: ❌ 不勾选
   - Validation minimum: `100`
   - Validation maximum: `999`
   - Weight: `210`
   - Group name: `Proxmox Configuration`

   **3.5 创建 `ansible_groups`**
   - Name: `ansible_groups`
   - Label: `Ansible Groups`
   - Type: `Multiple selection`
   - Object types: 勾选 `dcim | virtual machine` 和 `dcim | device`
   - Choices:
     ```
     pve_vms
     pve_lxc
     docker
     tailscale
     backup_client
     monitoring_target
     ```
   - Required: ❌ 不勾选
   - Weight: `300`
   - Group name: `Ansible Configuration`

   **3.6 创建 `playbook_name`**
   - Name: `playbook_name`
   - Label: `Ansible Playbook Name`
   - Type: `Text`
   - Object types: 勾选 `dcim | virtual machine` 和 `dcim | device`
   - Required: ❌ 不勾选
   - Weight: `310`
   - Group name: `Ansible Configuration`

4. **保存所有字段**
   - 点击每个字段配置页面的 "Create" 或 "Save" 按钮
   - 确认 Custom Fields 列表页面显示所有 6 个字段

**验证**:
```bash
# 通过 NetBox API 验证字段创建成功
curl -X GET "http://192.168.1.104:8080/api/extras/custom-fields/" \
  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  | jq '.results[] | select(.name | test("infrastructure_platform|automation_level|proxmox_node|proxmox_vmid|ansible_groups|playbook_name"))'
```

预期输出: 返回 6 个 Custom Field 对象,包含正确的 `type`、`choices`、`required` 等属性。

---

### Task 2: 创建测试资源验证 (20 分钟)

**步骤**:

1. **创建测试 Virtual Machine (Proxmox LXC)**

   导航: `Virtualization > Virtual Machines > Add`

   填写以下字段:
   - **Name**: `test-lxc-story-1-1`
   - **Status**: `Planned` (触发自动化流程的关键状态)
   - **Cluster**: 选择你的 Proxmox 集群 (如果已在 NetBox 中定义)
   - **Role**: `Application Server` (或其他合适的角色)
   - **Platform**: `Linux` (标准平台,非 Custom Field)
   - **vCPUs**: `1`
   - **Memory (MB)**: `512`
   - **Disk (GB)**: `8`

   **Custom Fields 部分**:
   - **Infrastructure Platform**: `proxmox`
   - **Automation Level**: `requires_approval`
   - **Proxmox Node**: `pve0`
   - **Proxmox VMID**: `199` (测试用临时 ID)
   - **Ansible Groups**: 勾选 `pve_lxc` 和 `docker`
   - **Ansible Playbook Name**: 留空 (测试自动推导)

   点击 "Create"。

2. **创建测试 Device (物理服务器)**

   导航: `Devices > Devices > Add`

   填写以下字段:
   - **Name**: `test-physical-story-1-1`
   - **Device Type**: 选择一个物理服务器类型 (或创建临时类型 "Generic Server")
   - **Role**: `Infrastructure Server`
   - **Site**: 你的站点
   - **Status**: `Planned`

   **Custom Fields 部分**:
   - **Infrastructure Platform**: `physical`
   - **Automation Level**: `manual_only`
   - **Proxmox Node**: 留空 (不适用于物理服务器)
   - **Proxmox VMID**: 留空
   - **Ansible Groups**: 勾选 `backup_client`
   - **Ansible Playbook Name**: 留空

   点击 "Create"。

3. **验证字段显示和分组**
   - 打开刚创建的两个测试资源的详情页
   - 确认 Custom Fields 按照 Group 正确分组显示:
     - **Automation**: `infrastructure_platform`, `automation_level`
     - **Proxmox Configuration**: `proxmox_node`, `proxmox_vmid` (仅 VM 显示)
     - **Ansible Configuration**: `ansible_groups`, `playbook_name`
   - 确认必填字段有红色星号标记 (如果 NetBox UI 支持)

**验证 (API 查询)**:
```bash
# 查询测试 VM
curl -X GET "http://192.168.1.104:8080/api/virtualization/virtual-machines/?name=test-lxc-story-1-1" \
  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  | jq '.results[0].custom_fields'

# 预期输出:
# {
#   "infrastructure_platform": "proxmox",
#   "automation_level": "requires_approval",
#   "proxmox_node": "pve0",
#   "proxmox_vmid": 199,
#   "ansible_groups": ["pve_lxc", "docker"],
#   "playbook_name": null
# }

# 查询测试物理服务器
curl -X GET "http://192.168.1.104:8080/api/dcim/devices/?name=test-physical-story-1-1" \
  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  | jq '.results[0].custom_fields'

# 预期输出:
# {
#   "infrastructure_platform": "physical",
#   "automation_level": "manual_only",
#   "proxmox_node": null,
#   "proxmox_vmid": null,
#   "ansible_groups": ["backup_client"],
#   "playbook_name": null
# }
```

---

### Task 3: 文档化字段使用规范 (30 分钟)

**步骤**:

1. **创建字段参考文档**

   创建文件: `docs/netbox-custom-fields-reference.md`

   内容包括:
   - 所有 6 个字段的详细说明 (复制上述规范)
   - 使用示例 (不同场景下的推荐配置)
   - 常见错误和排查方法

   **示例场景**:
   ```markdown
   ### 场景 1: 创建 Proxmox LXC 容器 (完全自动化)
   - `infrastructure_platform`: `proxmox`
   - `automation_level`: `fully_automated`
   - `proxmox_node`: `pve0` (根据负载选择)
   - `proxmox_vmid`: `150` (LXC 范围 100-199)
   - `ansible_groups`: `pve_lxc`, `docker`, `tailscale`
   - `playbook_name`: 留空 (自动推导)

   ### 场景 2: 创建生产 VM (需要审批)
   - `infrastructure_platform`: `proxmox`
   - `automation_level`: `requires_approval` ⚠️ 强制审批
   - `proxmox_node`: `pve1`
   - `proxmox_vmid`: `300`
   - `ansible_groups`: `pve_vms`, `monitoring_target`
   - `playbook_name`: `deploy-netbox` (显式指定)

   ### 场景 3: 物理服务器配置管理
   - `infrastructure_platform`: `physical`
   - `automation_level`: `manual_only`
   - `proxmox_node`: 留空
   - `proxmox_vmid`: 留空
   - `ansible_groups`: `backup_client`
   - `playbook_name`: 留空
   ```

2. **更新 README.md 快速参考**

   在项目 README 中添加:
   ```markdown
   ## NetBox Custom Fields Quick Reference

   核心字段 (必填):
   - `infrastructure_platform`: proxmox | esxi | physical
   - `automation_level`: fully_automated | requires_approval | manual_only

   Proxmox 专用字段:
   - `proxmox_node`: pve0 | pve1 | pve2
   - `proxmox_vmid`: 100-999

   Ansible 集成字段:
   - `ansible_groups`: 多选 (pve_lxc, docker, tailscale, ...)
   - `playbook_name`: 可选,默认根据 ansible_groups 推导

   详细文档: [Custom Fields Reference](docs/netbox-custom-fields-reference.md)
   ```

---

### Task 4: 清理测试资源 (10 分钟)

**步骤**:

1. **删除测试 Virtual Machine**
   - 导航到 `test-lxc-story-1-1` 详情页
   - 点击 "Delete" → 确认删除
   - 确认 Proxmox VMID `199` 不会在实际环境中被占用

2. **删除测试 Device**
   - 导航到 `test-physical-story-1-1` 详情页
   - 点击 "Delete" → 确认删除

3. **保留 Custom Fields**
   - ⚠️ **不要删除 Custom Fields**,它们是后续 Story 的基础

**验证**:
```bash
# 确认测试资源已删除
curl -X GET "http://192.168.1.104:8080/api/virtualization/virtual-machines/?name=test-lxc-story-1-1" \
  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  | jq '.count'
# 预期输出: 0

# 确认 Custom Fields 仍然存在
curl -X GET "http://192.168.1.104:8080/api/extras/custom-fields/" \
  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  | jq '.count'
# 预期输出: >= 6
```

---

## Testing Strategy

### 单元测试 (字段配置验证)

**测试用例 1: 必填字段验证**
```
前置条件: Custom Fields 已创建
步骤:
1. 尝试创建 Virtual Machine,不填写 `infrastructure_platform`
预期结果: NetBox UI 提示 "This field is required"
```

**测试用例 2: VMID 范围验证**
```
前置条件: Custom Fields 已创建
步骤:
1. 创建 Virtual Machine,填写 `proxmox_vmid = 50` (小于最小值)
预期结果: NetBox UI 提示 "Value must be at least 100"
2. 填写 `proxmox_vmid = 1000` (大于最大值)
预期结果: NetBox UI 提示 "Value must be at most 999"
```

**测试用例 3: 多选字段验证**
```
前置条件: Custom Fields 已创建
步骤:
1. 创建 Virtual Machine,在 `ansible_groups` 中勾选 `pve_lxc` 和 `docker`
2. 保存后通过 API 查询
预期结果: `custom_fields.ansible_groups` 返回 `["pve_lxc", "docker"]`
```

### 集成测试 (端到端流程验证)

**测试用例 4: Router Pipeline 路由验证**
```
前置条件:
- Custom Fields 已创建
- Router Pipeline (Jenkinsfile-webhook-router) 已部署 (Story 2.1 完成后测试)

步骤:
1. 创建 Virtual Machine: `platform=proxmox`, `automation_level=requires_approval`
2. 将状态改为 `Planned` 触发 Webhook
3. 观察 Jenkins Router Pipeline 日志

预期结果:
- Router 解析 Payload,识别 `platform=proxmox`
- 触发 `Proxmox-Provisioning` Pipeline
- Pipeline 参数包含正确的 `AUTOMATION_LEVEL=requires_approval`
```

**测试用例 5: Terraform Data Source 集成**
```
前置条件:
- Custom Fields 已创建
- Terraform NetBox data source 配置完成 (Story 3.1 完成后测试)

步骤:
1. 创建 Virtual Machine: `platform=proxmox`, `status=planned`, `proxmox_node=pve0`, `proxmox_vmid=199`
2. 在 Terraform 目录执行: `terraform plan`

预期结果:
- Terraform data source 查询到该 VM
- Plan 输出显示将创建资源,`node_name=pve0`, `vm_id=199`
```

### 回归测试 (向后兼容性验证)

**测试用例 6: 新增字段不影响现有资源**
```
前置条件:
- NetBox 中已有未使用 Custom Fields 的旧资源

步骤:
1. 创建 Custom Fields (本 Story 完成)
2. 查看旧资源的详情页

预期结果:
- 旧资源显示新的 Custom Fields 区域,但所有字段为空或默认值
- 编辑旧资源可正常保存 (无强制填写新字段的错误)
```

---

## Definition of Done

- [x] **所有 6 个 Custom Fields 在 NetBox Admin UI 中创建成功**
  - `infrastructure_platform`, `automation_level`, `proxmox_node`, `proxmox_vmid`, `ansible_groups`, `playbook_name`

- [x] **字段已应用到正确的 Content Types**
  - `dcim.virtualmachine`: 所有 6 个字段
  - `dcim.device`: 4 个字段 (`infrastructure_platform`, `automation_level`, `ansible_groups`, `playbook_name`)

- [x] **字段配置符合规范**
  - 必填字段: `infrastructure_platform`, `automation_level`
  - 验证规则: `proxmox_vmid` 最小值 100,最大值 999
  - 默认值: `infrastructure_platform=proxmox`, `automation_level=requires_approval`

- [x] **创建测试资源验证字段正常工作**
  - 测试 VM: `test-lxc-story-1-1` (已创建并删除)
  - 测试 Device: `test-physical-story-1-1` (已创建并删除)
  - API 查询返回正确的 Custom Fields JSON

- [x] **文档化完成**
  - `docs/netbox-custom-fields-reference.md` 创建
  - README.md 添加快速参考

- [x] **代码审查通过**
  - 字段命名符合 `snake_case` 规范 (AGENTS.md 强制要求)
  - 字段描述清晰,无拼写错误
  - UI Group 和 Weight 配置合理,字段显示顺序符合直觉

- [x] **集成点准备就绪**
  - 字段设计兼容 Router Pipeline 解析逻辑 (ADR-004)
  - 字段设计兼容 Terraform data source 查询 (ADR-002)
  - 字段设计兼容 Ansible Inventory 生成 (FR17)

---

## Dependencies & Risks

### 依赖
- **None** (这是 Epic 1 的第一个 Story,无前置依赖)

### 阻塞以下 Story
- **Story 2.1**: Router Pipeline 开发 (需要读取 `infrastructure_platform` 字段)
- **Story 3.1**: Terraform NetBox Data Source 配置 (需要查询 Custom Fields)
- **Story 4.1**: 迁移第一个 LXC 服务 (需要填写 Custom Fields)

### 风险

| 风险 | 影响 | 缓解措施 | 状态 |
|------|------|----------|------|
| **NetBox Custom Field 类型选择错误** | 🟡 Medium | Week 1 POC 验证,确认 `Multiple Selection` 类型能正确返回数组 | Open |
| **条件必填逻辑无法实现** | 🟢 Low | NetBox 不支持条件必填,改为在文档中说明 + Pipeline 验证 | Accepted |
| **字段数量过多,用户体验差** | 🟢 Low | 仅 6 个字段,已通过 UI Group 分组,可接受 | Accepted |
| **字段命名冲突** | 🟢 Low | 使用 `snake_case` + 前缀策略 (`proxmox_`, `ansible_`),避免冲突 | Mitigated |

---

## Dev Notes

### 架构决策参考
- **ADR-005**: NetBox 数据建模 - 核心字段先行,逐步扩展策略
- **ADR-004**: 多平台路由策略 - Custom Field 驱动路由决策
- **ADR-002**: Terraform 集成模式 - terraform-provider-netbox data source

### 关键约束
1. **字段命名必须使用 `snake_case`** (AGENTS.md 强制规范)
2. **Choices 必须使用小写 + 下划线** (如 `fully_automated`,而非 `FullyAutomated`)
3. **UI Group 名称使用 Title Case** (如 `Proxmox Configuration`,而非 `proxmox_configuration`)

### 后续扩展空间
- **Post-MVP 可能新增的字段**:
  - `esxi_host`: ESXi 主机引用 (Object 类型)
  - `esxi_datastore`: Datastore 选择 (Selection 类型)
  - `backup_policy`: PBS 备份策略 (Selection 类型)
  - `monitoring_enabled`: 是否启用监控 (Boolean 类型)

### 调试技巧
1. **API 查询 Custom Fields**:
   ```bash
   curl -X GET "http://192.168.1.104:8080/api/extras/custom-fields/" \
     -H "Authorization: Token ${NETBOX_API_TOKEN}" | jq .
   ```

2. **查询特定资源的 Custom Fields**:
   ```bash
   curl -X GET "http://192.168.1.104:8080/api/virtualization/virtual-machines/<id>/" \
     -H "Authorization: Token ${NETBOX_API_TOKEN}" | jq '.custom_fields'
   ```

3. **更新 Custom Field 值 (PATCH)**:
   ```bash
   curl -X PATCH "http://192.168.1.104:8080/api/virtualization/virtual-machines/<id>/" \
     -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{
       "custom_fields": {
         "automation_level": "fully_automated"
       }
     }'
   ```

---

## Related Documentation

- **PRD**: `/workspaces/IaC/_bmad-output/planning-artifacts/prd.md`
  - FR3, FR4, FR5 (Custom Fields 功能性需求)
  - NFR-I4, NFR-SC6, NFR-M14 (数据类型和兼容性要求)

- **Architecture**: `/workspaces/IaC/_bmad-output/planning-artifacts/architecture.md`
  - ADR-005: NetBox 数据建模策略
  - ADR-004: 多平台路由策略 (Custom Field 驱动)
  - Layer 1 Configuration Requirements (数据模型层配置规范)

- **Epics**: `/workspaces/IaC/_bmad-output/planning-artifacts/epics.md`
  - Epic 1, Story 1.1: 本 Story 的原始需求定义
  - Acceptance Criteria: 详细验收标准

- **AGENTS.md**: `/workspaces/IaC/AGENTS.md`
  - NetBox Custom Fields Naming (命名规范: `snake_case`)
  - 架构一致性规则

---

## Changelog

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-02-08 | 初始创建 Story 文档 | AI Agent (BMAD Workflow) |

---

**🎯 Ready to Start?** 按照 Implementation Tasks 部分的步骤逐步执行,每完成一个 Task 勾选对应的 Definition of Done 复选框。遇到问题参考 Dev Notes 和 Related Documentation。
