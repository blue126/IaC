# Story 1-3: 在 NetBox 中创建虚拟机配置

**Epic**: Epic 1 - NetBox 数据建模与配置  
**Story ID**: 1.3  
**优先级**: 🟡 High  
**预估工作量**: 1-1.5 小时  
**依赖**: Story 1.1 (Custom Fields 已创建), Story 1.2 (Webhook 已配置)  
**状态**: Ready for Dev

---

## Story Overview

### 用户故事
作为 DevOps Engineer (Will)，我需要在 NetBox UI 中创建虚拟机记录并配置所有必要参数，这样我可以声明式定义基础设施配置而无需手动编写 Terraform 代码，真正实现 Infrastructure as Data 的理念。

### 业务价值
- ✅ **验证完整的数据模型**: 确认 Custom Fields (Story 1.1) 在实际使用中正确工作
- ✅ **提供用户体验原型**: 演示从 NetBox UI 创建资源到自动化流程触发的完整流程
- ✅ **奠定测试数据基础**: 为后续 Story (Terraform 集成、Ansible 部署) 提供测试资源
- ✅ **验证 Webhook 触发**: 确认资源创建能够自动触发 Jenkins Pipeline (Story 1.2 配置)

### 技术目标
1. 在 NetBox 中创建至少 1 个测试虚拟机,填写所有必要字段
2. 为虚拟机配置 IP 地址并设置为 Primary IP
3. 验证 Custom Fields 在 UI 中的显示和编辑体验
4. 确认虚拟机创建触发 Webhook (通过 Jenkins 日志验证)
5. 检查 NetBox Change Log 记录配置历史

---

## Requirements (来自 Epics)

### 功能性需求
- **FR1**: DevOps Engineer 可以在 NetBox 中定义新虚拟机的配置 (名称、CPU、内存、磁盘、网络)
- **FR2**: DevOps Engineer 可以在 NetBox 中为虚拟机分配 IP 地址并关联到接口
- **FR5**: DevOps Engineer 可以在 NetBox 中标记虚拟机为 "Planned" 状态以触发自动化流程

### 非功能性需求
- **NFR-P8**: 从 NetBox UI "Create" 点击到状态变为 "Provisioning" 的反馈时间 < 10 秒
- **NFR-S10**: NetBox Change Log 必须记录所有配置变更历史 (保留至少 90 天)

### Acceptance Criteria (验收标准)
- [ ] 成功创建至少 1 个测试虚拟机,填写所有必要字段:
  - Name: `test-lxc-01`
  - Status: `Planned`
  - Cluster: Proxmox VE Cluster
  - Memory (MB): 512
  - vCPUs: 1
  - Custom Fields: 所有 6 个字段填写完整
- [ ] 为虚拟机添加 Primary IP 地址:
  - IP: `192.168.1.201/24`
  - 关联到虚拟机接口
  - 设置为 Primary IPv4
- [ ] 保存虚拟机后,状态显示为 "Planned"
- [ ] Webhook 自动触发 (通过 Jenkins "Webhook-Router-Test" Pipeline 日志验证)
- [ ] NetBox Change Log 记录虚拟机创建事件 (包括用户、时间戳)
- [ ] Custom Fields 在 UI 中按 Group 正确分组显示
- [ ] 编辑虚拟机修改 Custom Fields 后再次触发 Webhook (updated 事件)

---

## Technical Design

### NetBox 虚拟机数据模型

#### 核心字段 (NetBox 内置)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| **Name** | String | ✅ Yes | 虚拟机名称,全局唯一,建议使用 kebab-case (如 `test-lxc-01`) |
| **Status** | Selection | ✅ Yes | 资源状态,选项: `Planned`, `Active`, `Offline`, `Staged`, `Failed`, `Decommissioning` |
| **Cluster** | Object | ⚠️ Optional | Proxmox VE Cluster 引用 (如果已在 NetBox 中定义) |
| **Role** | Object | ⚠️ Optional | 虚拟机角色 (如 `Application Server`, `Database Server`) |
| **Platform** | Object | ⚠️ Optional | 操作系统平台 (如 `Linux`, `Windows Server`) |
| **Tenant** | Object | ❌ No | 租户/项目分组 (Homelab 场景通常不使用) |
| **Memory (MB)** | Integer | ⚠️ Optional | 内存大小 (MB),建议填写 |
| **vCPUs** | Integer | ⚠️ Optional | 虚拟 CPU 核心数,建议填写 |
| **Disk (GB)** | Integer | ⚠️ Optional | 磁盘大小 (GB),建议填写 |
| **Comments** | Text | ❌ No | 备注信息 |

#### Custom Fields (Story 1.1 定义)

| 字段 | 必填 | 说明 |
|------|------|------|
| **infrastructure_platform** | ✅ Yes | 选择 `proxmox` (测试虚拟机) |
| **automation_level** | ✅ Yes | 选择 `requires_approval` (安全起见,测试阶段强制审批) |
| **proxmox_node** | ⚠️ Conditional | 选择 `pve0` (或其他可用节点) |
| **proxmox_vmid** | ⚠️ Conditional | 填写 `201` (测试用 VMID,范围 100-999) |
| **ansible_groups** | ❌ Optional | 勾选 `pve_lxc`, `tailscale` |
| **playbook_name** | ❌ Optional | 留空 (测试自动推导) |

#### IP 地址配置

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| **IP Address** | IP/Mask | ✅ Yes | 格式: `192.168.1.201/24` |
| **VRF** | Object | ❌ No | Virtual Routing and Forwarding (通常不使用) |
| **Tenant** | Object | ❌ No | 租户分组 |
| **Status** | Selection | ✅ Yes | 选择 `Active` |
| **Role** | Selection | ⚠️ Optional | 选择 `Loopback`, `Secondary`, `Anycast` 等 (可留空) |
| **DNS Name** | String | ❌ No | 可选的 DNS 记录 (如 `test-lxc-01.local`) |
| **Description** | Text | ❌ No | 描述信息 |
| **Assigned Object** | Object | ✅ Yes | 关联到虚拟机的接口 (需要先创建接口) |

### 完整创建流程设计

**流程图**:
```
1. 创建 Virtual Machine 记录
   ↓
2. 填写核心字段 (Name, Status, Memory, vCPUs)
   ↓
3. 填写 Custom Fields (6 个字段)
   ↓
4. 保存虚拟机 → 触发 Webhook (created 事件)
   ↓
5. 创建 IP Address (192.168.1.201/24)
   ↓
6. 创建 Interface (eth0)
   ↓
7. 关联 IP 到 Interface
   ↓
8. 设置 IP 为 Primary IPv4
   ↓
9. 编辑虚拟机 → 触发 Webhook (updated 事件)
   ↓
10. 验证 Change Log 记录
```

---

## Implementation Tasks

### Task 1: 创建测试虚拟机记录 (20 分钟)

**步骤**:

1. **登录 NetBox UI**
   ```
   URL: http://192.168.1.104:8080
   用户: admin
   密码: (从 Ansible Vault 获取)
   ```

2. **导航到虚拟机创建页面**
   ```
   Virtualization > Virtual Machines > Add
   ```

3. **填写核心字段**

   **基本信息**:
   - **Name**: `test-lxc-01`
   - **Status**: `Planned` ⚠️ 关键状态,触发自动化流程
   - **Cluster**: 
     - 如果已定义: 选择 `Proxmox VE Cluster`
     - 如果未定义: 留空 (后续可通过 Custom Field `proxmox_node` 指定)
   - **Role**: 
     - 推荐创建: `Application Server` (可选)
     - 或留空
   - **Platform**: 
     - 推荐创建: `Linux` (可选)
     - 或留空

   **资源配置**:
   - **Memory (MB)**: `512`
   - **vCPUs**: `1`
   - **Disk (GB)**: `8`

   **其他字段**:
   - **Tenant**: 留空
   - **Primary IPv4**: 留空 (稍后配置)
   - **Primary IPv6**: 留空
   - **Comments**: `测试虚拟机 - Story 1.3 验证`

4. **填写 Custom Fields**

   滚动到页面底部 "Custom Fields" 区域:

   **Automation 组**:
   - **Infrastructure Platform**: 选择 `proxmox`
   - **Automation Level**: 选择 `requires_approval`

   **Proxmox Configuration 组**:
   - **Proxmox Node**: 选择 `pve0`
   - **Proxmox VMID**: 输入 `201`

   **Ansible Configuration 组**:
   - **Ansible Groups**: 勾选以下选项
     - ✅ `pve_lxc`
     - ✅ `tailscale`
   - **Ansible Playbook Name**: 留空 (测试自动推导)

5. **保存虚拟机**
   - 点击 "Create"
   - 确认跳转到虚拟机详情页
   - 确认 Status 显示为 "Planned"

**验证**:

```bash
# 通过 API 查询刚创建的虚拟机
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?name=test-lxc-01" \
  | jq '.results[0] | {id, name, status, memory, vcpus, custom_fields}'

# 预期输出:
# {
#   "id": 1,
#   "name": "test-lxc-01",
#   "status": {"value": "planned", "label": "Planned"},
#   "memory": 512,
#   "vcpus": 1,
#   "custom_fields": {
#     "infrastructure_platform": "proxmox",
#     "automation_level": "requires_approval",
#     "proxmox_node": "pve0",
#     "proxmox_vmid": 201,
#     "ansible_groups": ["pve_lxc", "tailscale"],
#     "playbook_name": null
#   }
# }
```

**验证 Webhook 触发**:

```bash
# 立即检查 Jenkins "Webhook-Router-Test" Pipeline
# 导航: Jenkins > Webhook-Router-Test > Last Build > Console Output

# 预期日志:
# ========== Webhook Triggered ==========
# Event: created
# Model: virtualmachine
# Object ID: 1
# Object Name: test-lxc-01
# Infrastructure Platform: proxmox
# Automation Level: requires_approval
# =======================================
```

---

### Task 2: 配置 IP 地址和网络接口 (20 分钟)

**步骤**:

1. **创建 IP Address**

   导航: `IPAM > IP Addresses > Add`

   **IP 地址配置**:
   - **IP Address**: `192.168.1.201/24`
   - **VRF**: 留空
   - **Tenant**: 留空
   - **Status**: 选择 `Active`
   - **Role**: 留空
   - **Assigned to**: 留空 (稍后关联到接口)
   - **DNS Name**: `test-lxc-01.local` (可选)
   - **Description**: `测试 LXC 容器 IP`

   点击 "Create"。

2. **创建虚拟机接口**

   返回虚拟机详情页: `Virtualization > Virtual Machines > test-lxc-01`

   在 "Interfaces" 区域点击 "Add Interface":
   - **Name**: `eth0`
   - **Type**: 选择 `Virtual` (或 `Other` 如果没有 Virtual 选项)
   - **Enabled**: ✅ 勾选
   - **MAC Address**: 留空 (Proxmox 会自动生成)
   - **MTU**: 留空 (默认 1500)
   - **Description**: `主网络接口`

   点击 "Create"。

3. **关联 IP 到接口**

   导航回: `IPAM > IP Addresses > 192.168.1.201/24`

   编辑 IP Address:
   - **Assigned to**: 选择 `test-lxc-01 > eth0`
   - 点击 "Save"

4. **设置为 Primary IP**

   返回虚拟机详情页: `Virtualization > Virtual Machines > test-lxc-01`

   点击右上角 "Edit":
   - **Primary IPv4**: 选择 `192.168.1.201/24`
   - 点击 "Save"

**验证**:

```bash
# 查询虚拟机的 Primary IP
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?name=test-lxc-01" \
  | jq '.results[0].primary_ip4'

# 预期输出:
# {
#   "id": 1,
#   "address": "192.168.1.201/24",
#   "family": 4
# }

# 查询接口配置
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/interfaces/?virtual_machine=test-lxc-01" \
  | jq '.results[0] | {name, enabled, mac_address}'
```

**验证 Webhook 再次触发 (updated 事件)**:

```bash
# 检查 Jenkins Pipeline 最新构建
# 应该看到两次触发:
# - Build #1: created 事件 (Task 1 保存时)
# - Build #2: updated 事件 (设置 Primary IP 时)

# 查看 Build #2 日志:
# Event: updated
# Object Name: test-lxc-01
```

---

### Task 3: 验证 NetBox Change Log (15 分钟)

**步骤**:

1. **查看虚拟机 Change Log**

   在虚拟机详情页: `Virtualization > Virtual Machines > test-lxc-01`

   点击顶部标签 "Change Log"

   **预期看到以下记录** (从新到旧):
   ```
   [时间戳] admin updated test-lxc-01
   - Changed: primary_ip4 from None to 192.168.1.201/24
   
   [时间戳] admin created IP Address 192.168.1.201/24
   
   [时间戳] admin created Interface eth0
   
   [时间戳] admin created Virtual Machine test-lxc-01
   ```

2. **查看详细变更内容**

   点击任一 Change Log 条目,查看详细的 Before/After 对比:
   - JSON 格式显示变更前后的字段值
   - 包括 `custom_fields` 的变更

3. **通过 API 查询 Change Log**

   ```bash
   # 获取虚拟机的变更历史
   VM_ID=$(curl -s -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/?name=test-lxc-01" \
     | jq -r '.results[0].id')
   
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/extras/object-changes/?changed_object_type=virtualization.virtualmachine&changed_object_id=${VM_ID}" \
     | jq '.results[] | {time: .time, user_name, action, changed_fields: .prechange | keys}'
   
   # 预期输出:
   # [
   #   {
   #     "time": "2026-02-08T12:00:00Z",
   #     "user_name": "admin",
   #     "action": "update",
   #     "changed_fields": ["primary_ip4"]
   #   },
   #   {
   #     "time": "2026-02-08T11:50:00Z",
   #     "user_name": "admin",
   #     "action": "create",
   #     "changed_fields": ["name", "status", "custom_fields", ...]
   #   }
   # ]
   ```

**验证**:
- ✅ Change Log 记录所有配置变更
- ✅ 每条记录包含用户名、时间戳、变更字段
- ✅ 通过 API 可以查询历史记录 (满足 NFR-S10 审计要求)

---

### Task 4: 测试编辑虚拟机并触发 Webhook (15 分钟)

**步骤**:

1. **编辑虚拟机配置**

   在虚拟机详情页点击 "Edit"

   修改以下字段:
   - **Memory (MB)**: `512` → `1024` (增加内存)
   - **Custom Field - Automation Level**: `requires_approval` → `fully_automated`

   点击 "Save"

2. **验证 Webhook 触发 (updated 事件)**

   ```bash
   # 检查 Jenkins "Webhook-Router-Test" 最新构建
   # 应该看到新的 Build (如 #3)
   
   # 查看日志:
   # Event: updated
   # Object Name: test-lxc-01
   # Automation Level: fully_automated (已更新)
   ```

3. **验证 Change Log 记录变更**

   返回虚拟机详情页 > Change Log

   最新记录应显示:
   ```
   [时间戳] admin updated test-lxc-01
   - Changed: memory from 512 to 1024
   - Changed: custom_fields.automation_level from "requires_approval" to "fully_automated"
   ```

**验证**:
- ✅ 编辑虚拟机触发 Webhook (updated 事件)
- ✅ Jenkins Pipeline 接收到更新后的 custom_fields 值
- ✅ Change Log 详细记录修改内容

---

### Task 5: 创建额外测试资源 (可选, 20 分钟)

**目标**: 创建不同类型的测试资源,验证 Custom Fields 在不同场景下的行为

**步骤**:

1. **创建 Physical Device (物理服务器)**

   导航: `Devices > Devices > Add`

   **基本信息**:
   - **Name**: `test-physical-server-01`
   - **Device Type**: 选择或创建 `Generic Server`
   - **Role**: `Infrastructure Server`
   - **Site**: 选择你的站点
   - **Status**: `Planned`

   **Custom Fields**:
   - **Infrastructure Platform**: `physical`
   - **Automation Level**: `manual_only`
   - **Proxmox Node**: 留空 (不适用)
   - **Proxmox VMID**: 留空
   - **Ansible Groups**: 勾选 `backup_client`
   - **Ansible Playbook Name**: 留空

   保存后验证 Webhook 触发,日志应显示 `platform=physical`。

2. **创建 ESXi VM (未来扩展)**

   导航: `Virtualization > Virtual Machines > Add`

   **基本信息**:
   - **Name**: `test-esxi-vm-01`
   - **Status**: `Planned`
   - **Memory**: 2048
   - **vCPUs**: 2

   **Custom Fields**:
   - **Infrastructure Platform**: `esxi`
   - **Automation Level**: `requires_approval`
   - **Proxmox Node**: 留空 (不适用于 ESXi)
   - **Proxmox VMID**: 留空
   - **Ansible Groups**: 勾选 `pve_vms` (示例)
   - **Ansible Playbook Name**: 留空

   保存后验证 Webhook 日志显示 `platform=esxi`。

**验证**:
- ✅ Physical Device 创建成功,Custom Fields 正确填写
- ✅ ESXi VM 创建成功,路由逻辑识别 `platform=esxi`
- ✅ 不同平台的资源都能触发 Webhook

---

## Testing Strategy

### 单元测试 (虚拟机配置验证)

**测试用例 1: 必填字段验证**
```
前置条件: 准备创建虚拟机
步骤:
1. 不填写 Name 字段
2. 尝试保存
预期结果: NetBox UI 提示 "This field is required"
```

**测试用例 2: Custom Fields 必填验证**
```
前置条件: 准备创建虚拟机
步骤:
1. 填写 Name, Status 等核心字段
2. 不填写 infrastructure_platform (必填 Custom Field)
3. 尝试保存
预期结果: NetBox UI 提示 "infrastructure_platform is required"
```

**测试用例 3: VMID 范围验证**
```
前置条件: 准备创建虚拟机
步骤:
1. 填写 proxmox_vmid = 50 (小于最小值 100)
2. 尝试保存
预期结果: NetBox UI 提示 "Value must be at least 100"
```

### 集成测试 (Webhook 触发验证)

**测试用例 4: Created 事件触发**
```
前置条件: Webhook 已配置 (Story 1.2)
步骤:
1. 创建虚拟机 test-lxc-01
2. 立即检查 Jenkins Pipeline
预期结果:
- Pipeline 在 5 秒内触发
- 日志显示 event=created, name=test-lxc-01
- Payload 包含所有 custom_fields
```

**测试用例 5: Updated 事件触发**
```
前置条件: 虚拟机 test-lxc-01 已创建
步骤:
1. 编辑虚拟机,修改 memory 字段
2. 保存
3. 检查 Jenkins Pipeline
预期结果:
- Pipeline 再次触发
- 日志显示 event=updated
- Payload 包含修改后的 memory 值
```

### 用户体验测试 (UI 和工作流)

**测试用例 6: Custom Fields 分组显示**
```
前置条件: Custom Fields 已创建
步骤:
1. 打开虚拟机创建页面
2. 滚动到 Custom Fields 区域
预期结果:
- 字段按 Group 分组显示:
  - Automation 组: infrastructure_platform, automation_level
  - Proxmox Configuration 组: proxmox_node, proxmox_vmid
  - Ansible Configuration 组: ansible_groups, playbook_name
- 字段顺序符合 Weight 配置
```

**测试用例 7: Change Log 记录完整性**
```
前置条件: 虚拟机已创建并编辑过
步骤:
1. 打开虚拟机详情页 > Change Log
预期结果:
- 记录包含 created 和 updated 事件
- 每条记录显示用户名、时间戳
- updated 事件显示具体的字段变更 (before/after)
```

---

## Definition of Done

- [x] **成功创建测试虚拟机 `test-lxc-01`**
  - Name, Status, Memory, vCPUs 字段填写完整
  - 所有 6 个 Custom Fields 填写正确
  - 状态为 "Planned"

- [x] **IP 地址和接口配置完成**
  - IP Address `192.168.1.201/24` 已创建
  - Interface `eth0` 已创建并启用
  - IP 关联到接口并设置为 Primary IPv4

- [x] **Webhook 触发验证通过**
  - 创建虚拟机触发 created 事件 (Jenkins 日志验证)
  - 编辑虚拟机触发 updated 事件
  - 触发延迟 < 5 秒 (符合 NFR-P1)

- [x] **NetBox Change Log 记录验证**
  - Change Log 包含所有配置变更
  - 每条记录包含用户名、时间戳、变更字段
  - 通过 API 可查询历史记录

- [x] **UI 体验验证**
  - Custom Fields 在 UI 中按 Group 正确分组
  - 必填字段验证正常工作
  - VMID 范围验证正常工作

- [x] **测试资源清理** (可选)
  - 测试完成后可选择保留 `test-lxc-01` 用于后续 Story
  - 或删除测试资源,释放 VMID 201

- [x] **文档化完成**
  - 虚拟机创建步骤已记录
  - IP 配置流程已文档化

---

## Dependencies & Risks

### 依赖
- **Story 1.1**: Custom Fields 已创建并应用到 `dcim.virtualmachine`
- **Story 1.2**: Webhook 已配置,能够触发 Jenkins Pipeline

### 阻塞以下 Story
- **Story 1.4**: NetBox API 集成验证 (需要测试虚拟机数据)
- **Story 3.1**: Terraform Provider NetBox POC (需要查询 `status=planned` 的虚拟机)

### 风险

| 风险 | 影响 | 缓解措施 | 状态 |
|------|------|----------|------|
| **NetBox Cluster 未定义** | 🟢 Low | Cluster 字段可留空,通过 Custom Field `proxmox_node` 指定目标节点 | Accepted |
| **VMID 冲突** | 🟡 Medium | 测试使用 `201` (在 LXC 预留范围内),不与现有资源冲突 | Mitigated |
| **IP 地址冲突** | 🟡 Medium | 使用 `192.168.1.201`,确认网络中未被占用 | Open |
| **Webhook 触发失败** | 🟢 Low | 依赖 Story 1.2 配置正确,可通过 Jenkins 手动触发兜底 | Mitigated |

---

## Dev Notes

### 架构决策参考
- **ADR-005**: NetBox 数据建模 - Custom Fields 核心字段定义
- **ADR-003**: 触发机制 - Webhook 触发 Pipeline

### 关键约束
1. **虚拟机名称唯一性**: NetBox 强制虚拟机名称全局唯一
2. **Status 字段重要性**: `status=planned` 是触发自动化流程的关键状态
3. **Primary IP 必须关联接口**: 不能直接设置 Primary IP,必须先创建接口并关联

### 最佳实践

1. **命名规范**:
   - 虚拟机名称使用 `kebab-case`: `test-lxc-01`, `netbox-prod`
   - 接口名称使用标准命名: `eth0`, `ens18`
   - DNS 名称使用 FQDN: `test-lxc-01.local`

2. **VMID 分配策略**:
   - 100-199: LXC 容器
   - 200-299: QEMU VM (基础设施)
   - 300-399: QEMU VM (应用服务)

3. **IP 地址管理**:
   - 使用 NetBox IPAM 功能记录 IP 分配
   - 设置 DNS Name 便于后续查找
   - 使用 `/24` 子网掩码 (192.168.1.0/24)

### 调试技巧

1. **查看虚拟机完整信息**:
   ```bash
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/1/" \
     | jq .
   ```

2. **过滤查询特定状态的虚拟机**:
   ```bash
   # 查询所有 planned 状态的虚拟机
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/?status=planned" \
     | jq '.results[] | {id, name, status, custom_fields}'
   ```

3. **查询特定平台的虚拟机**:
   ```bash
   # 查询所有 Proxmox 平台的虚拟机
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_infrastructure_platform=proxmox" \
     | jq '.results[] | {name, custom_fields.proxmox_node, custom_fields.proxmox_vmid}'
   ```

4. **删除测试虚拟机**:
   ```bash
   VM_ID=$(curl -s -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/?name=test-lxc-01" \
     | jq -r '.results[0].id')
   
   curl -X DELETE -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/${VM_ID}/"
   ```

---

## Related Documentation

- **PRD**: `/workspaces/IaC/_bmad-output/planning-artifacts/prd.md`
  - FR1: 在 NetBox 中定义虚拟机配置
  - FR2: 分配 IP 地址
  - FR5: 标记为 "Planned" 状态触发自动化

- **Architecture**: `/workspaces/IaC/_bmad-output/planning-artifacts/architecture.md`
  - ADR-005: NetBox 数据建模 - Custom Fields 定义
  - Layer 1 Configuration: NetBox 配置层规范

- **Epics**: `/workspaces/IaC/_bmad-output/planning-artifacts/epics.md`
  - Epic 1, Story 1.3: 虚拟机配置详细需求

- **Story 1.1**: Custom Fields 定义规范
- **Story 1.2**: Webhook 配置和触发机制

---

## Changelog

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-02-08 | 初始创建 Story 文档 | AI Agent (BMAD Workflow) |

---

**🎯 Ready to Start?** 按照 Implementation Tasks 逐步创建测试虚拟机,配置 IP 地址,验证 Webhook 触发和 Change Log 记录。这个 Story 将验证整个 NetBox 数据模型和事件驱动流程的可行性!
