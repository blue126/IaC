# Epic 1 学习笔记 — NetBox 数据建模与 Webhook 基础设施

**日期**: 2026-02-09
**Epic**: Epic 1 — NetBox 数据建模与 Webhook 基础设施
**背景**: 第一次接触 Jenkins 和 NetBox，从零搭建事件驱动的基础设施自动化

---

## Story 1-1: 定义核心 Custom Fields

### 核心概念 — Custom Fields

NetBox 的可扩展元数据系统。你可以给 VM、Device 等对象附加自定义字段。支持 Selection（下拉选择）、Integer（整数）、Text（文本）、Multiple Selection（多选）等类型。

### 我们创建的 6 个字段

| 字段 | 类型 | 作用 |
|------|------|------|
| `infrastructure_platform` | Selection | **路由核心** — proxmox/esxi/physical，决定走哪条 pipeline |
| `automation_level` | Selection | 自动化级别 — fully_automated/requires_approval/manual_only |
| `proxmox_node` | Selection | Proxmox 节点 — pve0/pve1/pve2 |
| `proxmox_vmid` | Integer | VM ID — 100-999，分段分配 |
| `ansible_groups` | Multiple Selection | Ansible 分组 — docker, tailscale 等 |
| `playbook_name` | Text | 部署用的 playbook 名称 |

### 遇到的问题

- NetBox **不支持条件必填**（比如 `proxmox_node` 只在平台是 proxmox 时才必填）。解决方案：在 Pipeline 里做验证，不靠 NetBox 本身
- 命名规范：字段名 `snake_case`，选项值全小写加下划线

### 关键学习

- 这 6 个字段是下游所有工具（Jenkins、Terraform、Ansible）的**数据源** — 一切自动化从这里开始
- `automation_level` 默认是 `requires_approval`（安全第一）
- VMID 分段策略：100-199 LXC，200-299 基础设施 VM，300-399 应用 VM
- UI Group 和 Weight 用来组织字段在界面上的分组和排序

### 关键 API

- 查询 Custom Field 定义：`GET /api/extras/custom-fields/`
- 查询 VM 的 Custom Fields：`GET /api/virtualization/virtual-machines/?name=<name>` → `.results[0].custom_fields`
- 更新 Custom Field 值：`PATCH /api/virtualization/virtual-machines/<id>/` body: `{"custom_fields": {"automation_level": "fully_automated"}}`

---

## Story 1-2: 配置 NetBox Webhook 到 Jenkins

### 核心概念 — 事件驱动架构

```
NetBox (用户创建/编辑 VM)
    │
    │ Event Rule 检测到 object_created / object_updated
    ▼
Webhook (HTTP POST 到 Jenkins)
    │
    │ Generic Webhook Trigger 插件接收
    ▼
Jenkins Pipeline 被触发
```

### NetBox 4.x 的关键架构（最大的坑）

- NetBox **3.x**：Webhook 对象上直接配事件类型
- NetBox **4.x**：Webhook 和事件触发条件**分离**成两个对象
  - **Webhook** — 只定义 HTTP 配置（URL、method、headers）
  - **Event Rule** — 定义什么事件触发什么 webhook

**忘记创建 Event Rule = webhook 永远不会触发**，而且没有任何报错。

### 配置详情

**NetBox Webhook**:
- Name: `Jenkins Infrastructure Automation`
- URL: `http://192.168.1.107:8080/generic-webhook-trigger/invoke`
- Method: POST, Content-Type: application/json
- Additional Headers: `token: <credential-value>` (Epic 2 code review 后改为 header 传递)

**NetBox Event Rule**:
- Name: `Trigger Jenkins on VM/Device Changes`
- Object types: `virtualization.virtualmachine`, `dcim.device`
- Event types: `object_created`, `object_updated`
- Action type: `webhook`, linked to Webhook

**Jenkins GenericTrigger 配置**:
```groovy
genericVariables: [
    [key: 'netbox_event', value: '$.event'],
    [key: 'netbox_model', value: '$.model'],
    [key: 'netbox_object_id', value: '$.data.id'],
    [key: 'infrastructure_platform', value: '$.data.custom_fields.infrastructure_platform'],
]
tokenCredentialId: 'netbox-webhook-token'
regexpFilterExpression: '^(virtualmachine|device)$'
```

### 遇到的问题

1. **Jenkins 端口号文档写错** — 文档写 `8090`，实际是 `8080`。浪费了调试时间
2. **Event Rule 未创建** — 原始设计基于 3.x 文档，没有 Event Rule 的概念
3. **readJSON 插件安装失败** — Pipeline Utility Steps 依赖问题装不上
   - **解决方案**：完全放弃 readJSON，改用 Generic Webhook Trigger 内置的 JSONPath 提取。结果代码更简单、零额外依赖
4. **Payload 格式差异** — 以为数据在 `$.snapshots.postchange`，实际 4.x 在 `$.data`；以为事件值是 `object_created`，实际是 `created`
5. **静默失败** — NetBox 显示 webhook "发送成功"（HTTP 200），但 Jenkins regexp 不匹配，**请求被静默丢弃**。没有报错，没有日志

### 关键学习

- **永远检查你用的工具的实际版本**，不要假设文档是对的
- **遇到插件装不上，先想想平台原生能力能不能解决问题**
- **中间链路必须有可观测性** — webhook → Jenkins 这段需要明确的反馈机制
- `printContributedVariables: true` 和 `printPostContent: true` 对调试非常有价值
- regexp 变更后需**手动首次 build** 才能加载新配置（Jenkins 已知行为）

---

## Story 1-3: 在 NetBox 中创建虚拟机配置

### 核心概念 — NetBox VM 创建流程

```
1. 创建 VM 记录（名称、状态、资源、Custom Fields）
2. 创建 Interface（eth0）
3. 创建 IP Address（192.168.1.201/24）
4. 关联 IP 到 Interface
5. 设置 Primary IPv4
```

**不能在创建 VM 时直接指定 IP**。必须按上面 5 步顺序来，因为 NetBox 的数据模型里 IP 是独立对象。

### 创建的测试 VM

- 名称：`test-lxc-01`，状态：`Planned`
- Memory: 512 MB, vCPUs: 1, Disk: 8 GB
- Custom Fields：`infrastructure_platform=proxmox`, `automation_level=requires_approval`, `proxmox_node=pve0`, `proxmox_vmid=201`
- 接口：`eth0`（Virtual 类型），IP：`192.168.1.201/24`

### 关键学习

- VM 名称在 NetBox 里**全局唯一**，命名用 `kebab-case`
- 每次保存 VM 都会触发一个 webhook — 创建触发 `created`，编辑 IP 再触发 `updated`，一个"逻辑创建"可能触发多次 pipeline
- NetBox 内置 Change Log 自动记录所有变更，API 可查：`/api/extras/object-changes/`
- 设置 `status=Planned` 是触发自动化的关键信号 — "意图声明"

### 关键 API

- 查询 VM：`GET /api/virtualization/virtual-machines/?name=test-lxc-01`
- 查询接口：`GET /api/virtualization/interfaces/?virtual_machine=test-lxc-01`
- 按状态过滤：`GET /api/virtualization/virtual-machines/?status=planned`
- 按 Custom Field 过滤：`GET /api/virtualization/virtual-machines/?cf_infrastructure_platform=proxmox`
- 查询变更日志：`GET /api/extras/object-changes/?changed_object_type=virtualization.virtualmachine&changed_object_id=<id>`

---

## Story 1-4: NetBox API 集成验证

### 核心概念 — API 查询模式

```bash
# 基础查询
GET /api/virtualization/virtual-machines/

# 按状态过滤
GET /api/virtualization/virtual-machines/?status=planned

# 按 Custom Field 过滤（注意 cf_ 前缀）
GET /api/virtualization/virtual-machines/?cf_infrastructure_platform=proxmox

# 组合过滤
GET /api/virtualization/virtual-machines/?status=planned&cf_infrastructure_platform=proxmox&cf_automation_level=requires_approval
```

### API 认证

- Token 方式：`Authorization: Token <40位字符>`
- Token 在 NetBox 创建时**只显示一次**，错过了只能删除重建
- 需要 Write 权限（后续 story 要回写状态）
- Jenkins 里存为 Secret text credential，ID 是 `netbox-api-token`

### 遇到的问题

- **无效过滤参数静默忽略** — 查 `cf_nonexistent_field=value` 返回空结果而不是报错，容易掩盖配置错误
- **Token 只显示一次** — 创建时要立刻记录下来

### 关键学习

- **`jq` 是 JSON 处理的必备工具**：
  - `.results[].name` — 提取所有名称
  - `.results | length` — 计数
  - `select(.custom_fields.infrastructure_platform == "proxmox")` — 客户端过滤
- **API 过滤用 `cf_` 前缀** — 这是 NetBox 的约定
- 所有查询 < 500ms，远超 NFR 要求的 < 30s
- **性能测量技巧**：`curl -w "\nTime: %{time_total}s\n" -o /dev/null -s`

### Jenkins Pipeline 集成模式

```groovy
withCredentials([string(credentialsId: 'netbox-api-token', variable: 'TOKEN')]) {
    sh '''
        curl -H "Authorization: Token ${TOKEN}" \
          http://192.168.1.104:8080/api/virtualization/virtual-machines/?status=planned \
          | jq -r '.results[].name'
    '''
}
```

---

## Epic 1 全景图

```
Story 1.1 定义 Custom Fields（数据基础）
    ↓
Story 1.2 配置 Webhook（事件桥梁）
    ↓
Story 1.3 创建 VM（端到端验证数据模型）
    ↓
Story 1.4 API 验证（确认下游可用）
```

### 端到端数据流

```
NetBox UI (用户创建/编辑 VM with Custom Fields)
    │
    │ [Event Rule 检测到 object_created/object_updated]
    ▼
NetBox Webhook (HTTP POST + token header)
    │
    │ [POST http://192.168.1.107:8080/generic-webhook-trigger/invoke]
    ▼
Jenkins Generic Webhook Trigger (JSONPath 提取变量)
    │
    │ [读取 infrastructure_platform, automation_level 等]
    ▼
Router Pipeline (switch/case on infrastructure_platform)
    │
    ├──→ proxmox  → Proxmox-Provisioning Pipeline (Terraform)
    ├──→ esxi     → ESXi-Provisioning Pipeline (Terraform)
    └──→ physical → Physical-Device-Sync Pipeline (skip Terraform)
```

---

## 基础设施参考

| 服务 | IP | 端口 | 备注 |
|------|-----|------|------|
| NetBox | 192.168.1.104 | 8080 | Docker Compose, v4.1.11 |
| Jenkins | 192.168.1.107 | 8080 | LXC, v2.541.1 |
| Proxmox | 192.168.1.50 | 8006 | |

---

## Epic 1 核心教训总结

1. **NetBox 4.x 的 webhook 架构与 3.x 完全不同** — 需要 Webhook + Event Rule 两个对象配合
2. **遇到插件障碍，优先考虑平台原生能力** — readJSON → GenericTrigger JSONPath
3. **验证端口号和 URL** — 8090 vs 8080 的教训
4. **Custom Field 过滤用 `cf_` 前缀** — `?cf_infrastructure_platform=proxmox`
5. **IP 分配在 NetBox 里是多步操作** — Interface → IP → 关联 → 设 Primary
6. **安全第一的默认值** — `automation_level` 默认 `requires_approval`
7. **无效 API 参数静默失败** — 返回空结果不报错，注意验证字段名
8. **中间链路需要可观测性** — webhook 静默丢弃问题
9. **Jenkins trigger 配置变更后需手动首次 build**
