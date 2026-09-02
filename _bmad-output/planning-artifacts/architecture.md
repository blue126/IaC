---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/product-brief-IaC-2026-01-31.md'
  - 'docs/improvement/PLANNING.md'
  - 'docs/designs/homelab-iac-architecture.md'
  - 'docs/designs/cicd-architecture.md'
workflowType: 'architecture'
project_name: 'IaC'
user_name: 'Will'
date: '2026-02-05'
---

# Architecture Decision Document - IaC

_本文档通过逐步协作发现来构建。随着我们一起完成每个架构决策，章节会逐步添加。_

## 项目上下文分析

### 需求概览

**功能性需求：**

本项目包含 **49 个功能性需求**，分为 7 个核心能力领域：

1. **配置管理（FR1-FR8）**：NetBox 中定义虚拟机配置、IP 分配、平台类型标记、Ansible 角色变量配置
2. **基础设施供给（FR9-FR16）**：Terraform 从 NetBox 拉取数据、多平台资源创建（Proxmox/ESXi）、生命周期管理、状态反馈
3. **服务部署（FR17-FR23）**：Ansible dynamic inventory 生成、应用部署、健康检查验证
4. **自动化编排（FR24-FR30）**：Jenkins Pipeline 编排、Webhook 触发、人工审批、失败通知
5. **平台路由（FR31-FR35）**：基于 NetBox Custom Field 的智能路由、物理服务器跳过 Terraform 逻辑
6. **错误处理与恢复（FR36-FR42）**：失败状态标记、自动重试机制、错误日志关联
7. **可观测性与追踪（FR43-FR49）**：变更历史记录、Pipeline 执行追踪、审计日志生成

**非功能性需求：**

本项目包含 **40 个非功能性需求**，聚焦以下质量属性：

**性能（NFR-P1 至 NFR-P9）：**
- Webhook 触发延迟 < 5 秒
- LXC 容器创建总时间 < 3 分钟
- QEMU VM 创建总时间 < 5 分钟（含 Cloud-Init）
- Terraform Plan 生成时间 < 30 秒
- 10x 资源增长时性能退化 < 20%

**安全（NFR-S1 至 NFR-S10）：**
- 所有凭据通过 Ansible Vault/Jenkins Secrets 加密存储
- 传输层 TLS 加密（NetBox Webhook、API 调用）
- 强制人工审批（`automation_level == requires_approval`）
- SSH 密钥使用非对称加密（Ed25519/RSA 4096）
- 完整的 Git 审计追踪（90 天保留）

**可靠性（NFR-R1 至 NFR-R11）：**
- Webhook 触发成功率 > 95%（MVP 阶段 > 80%）
- Terraform Apply 成功率 > 90%
- 幂等性保证（重复触发不创建重复资源）
- Pipeline 失败后可安全重试
- NetBox 与 Terraform state 最终一致性

**可扩展性（NFR-SC1 至 NFR-SC8）：**
- 支持至少 100 个资源（VMID 100-999 范围）
- 并发 Pipeline 执行 2-3 个
- 新平台扩展仅需添加 Pipeline，Router 逻辑无需修改
- NetBox Custom Fields 变更向后兼容

**集成（NFR-I1 至 NFR-I10）：**
- NetBox API Token 认证
- Terraform provider 版本锁定（>= 3.0）
- Ansible Inventory JSON 格式规范
- 外部 API 失败记录详细日志

**可维护性（NFR-M1 至 NFR-M14）：**
- Terraform 按平台隔离目录
- Ansible Roles 按服务划分
- 所有架构决策记录在 ADR 中
- 支持平滑迁移（静态 .tf 与 NetBox Pull 模式并存）

### 规模与复杂度

**项目规模：**
- **复杂度等级**：中高（Medium-High）
- **主要技术领域**：Infrastructure Automation Platform / DevOps Toolchain
- **项目类型**：Developer Tool（基础设施自动化平台）
- **预估架构组件**：15-20 个核心组件

**复杂度指标：**
- ✅ **事件驱动架构**：NetBox Webhook → Jenkins Router → Platform Pipelines
- ✅ **多平台异构环境**：Proxmox VE / VMware ESXi / Physical Servers
- ✅ **数据流反转**：从 Terraform Push 模式到 NetBox Pull 模式的架构演进
- ✅ **状态同步挑战**：NetBox 期望状态 ↔ Terraform 实际状态的最终一致性
- ⚠️ **渐进式迁移**：两种模式并存，逐步切换，降低风险

**用户交互复杂度：**
- 主要通过 NetBox UI 进行资源定义（低代码体验）
- Jenkins Pipeline 提供人工审批节点（Terraform Plan 预览）
- 实时进度反馈（NetBox 状态字段：`planned` → `provisioning` → `active`）

**数据复杂度：**
- NetBox Custom Fields 驱动路由决策（`infrastructure_platform`, `automation_level`, `ansible_groups`）
- Terraform state 作为中间层（HCP Terraform Cloud）
- Ansible Vault 作为密钥单一数据源（18 个加密密码）

### 技术约束与依赖

**已有基础设施约束：**
- Proxmox VE 8.x 集群（3 节点：pve0, pve1, pve2）
- VMware ESXi 8.x（仅用于 PBS 备份服务器）
- NetBox 4.1.x 已部署（当前为被动文档工具，需转变为主动配置源）
- Jenkins LXC 已部署（192.168.1.107，2C/2GB，Cloudflare Tunnel 已配置）

**技术栈锁定：**
- Terraform >= 1.14（与 HCP Terraform Cloud 兼容）
- Ansible >= 2.16（支持 `cloud.terraform` collection）
- Terraform Provider: `bpg/proxmox` 0.70.0, `e-breuninger/netbox` 3.10.0
- Python 3.12（devcontainer 环境）

**关键依赖服务：**
- HCP Terraform Cloud（远程状态存储与锁定）
- GitHub（代码仓库 + Webhook 触发）
- Cloudflare Tunnel（Jenkins Webhook 接收）
- Ansible Vault（密钥管理，`.vault_pass` 文件 gitignored）

**已知风险与缓解：**
1. **terraform-provider-netbox 成熟度不确定**
   - **缓解**：Week 1 POC 验证；Plan B：Python 脚本生成静态 `.tf`
2. **Webhook 触发失败率**
   - **缓解**：Generic Trigger 重试 + 手动触发兜底
3. **NetBox 数据模型设计不当**
   - **缓解**：Week 1 测试数据验证 + Custom Fields 灵活扩展

### 跨领域关注点

**安全性（Security）：**
- 凭据管理：Ansible Vault 统一加密（AES256）
- 传输加密：所有 API 调用强制 TLS（拒绝 `tls_insecure`）
- 访问控制：Jenkins 强制人工审批 + Proxmox API Token RBAC
- 审计追踪：Git commit 记录所有 Terraform state 变更

**可观测性（Observability）：**
- Pipeline 日志：Jenkins 保留最近 10 个构建历史
- 状态追踪：NetBox 状态字段（`active` / `provisioning` / `failed_provisioning`）
- 变更历史：NetBox Change Log（90 天保留）+ Git commit message
- 健康检查：所有 Ansible playbook 内置 `[verify]` tagged tasks

**容错与恢复（Resilience）：**
- Webhook 失败处理：自动重试 + 手动触发兜底
- 幂等性保证：Terraform state 检测已存在资源
- Pipeline 重试：失败虚拟机可自动重试最多 3 次
- 回滚能力：Git revert → 重新运行 Pipeline

**学习与展示导向（Learning-Oriented）：**
- 架构设计可向面试官清晰解释
- 8 个 ADR 记录关键决策及理由
- Portfolio 项目展示端到端 IaC + CI/CD 系统
- "Break it to Fix it" 学习方法（通过修复失败深入理解）

**架构演进性（Evolvability）：**
- 支持平滑迁移（静态 `.tf` 与 NetBox Pull 模式并存）
- 新平台扩展仅需添加 Pipeline（Router 逻辑无需修改）
- NetBox Custom Fields 变更向后兼容
- 未来 Drift Detection 预留设计空间

## Starter Template 评估

### 决策：不适用传统 Starter Template

**理由：**

本项目是一个 **Infrastructure Automation Platform**，具有以下特点：

1. **技术栈已明确锁定**：
   - Terraform >= 1.14
   - Ansible >= 2.16
   - NetBox 4.1.x
   - Jenkins LTS
   - Python 3.12

2. **代码库已存在**：
   - Phase 1（IaC 核心）已完成
   - Phase 2（CI/CD）进行中
   - 项目是架构演进而非初始化

3. **项目组织结构已成熟**：
   - Terraform 模块化结构（`modules/proxmox-vm`、`modules/proxmox-lxc`、`modules/esxi-vm`）
   - Ansible Role 标准化结构（`roles/common`、`roles/docker`、`roles/netbox` 等）
   - Jenkins Pipeline 已定义（`Jenkinsfile`）

**架构决策焦点：**

本文档将专注于 **架构决策记录（ADR）**，而非项目初始化：

- ✅ 已在 PRD 中定义 8 个关键 ADR（数据流反转、Terraform 集成模式、触发机制等）
- ✅ 需要详细展开每个 ADR 的上下文、决策、理由和影响
- ✅ 确保 AI Agent 能够基于这些决策一致地实现系统

**当前项目结构参考：**

项目已遵循以下 IaC 最佳实践：

- **Terraform**: Per-service 文件模式（每个服务一个 `.tf` 文件）
- **Ansible**: 标准 Role 结构（`tasks/`、`defaults/`、`templates/`、`handlers/`）
- **密钥管理**: Ansible Vault 单一数据源 + 间接引用模式
- **CI/CD**: Jenkins 声明式 Pipeline + 智能变更检测

---

## 核心架构决策

### 决策优先级分析

**关键决策（阻塞实施）：**

1. **ADR-001**：数据流反转策略 - 定义整体迁移策略
2. **ADR-002**：Terraform 集成模式 - Week 1 POC 必须验证
3. **ADR-004**：多平台路由策略 - Router Pipeline 是核心
4. **ADR-005**：NetBox 数据建模 - Week 1 必须完成 Custom Fields 定义

**重要决策（塑造架构）：**

5. **ADR-003**：触发机制 - 内网 Webhook 已配置，需文档化
6. **ADR-006**：错误恢复策略 - 影响用户体验
7. **ADR-008**：Terraform 工作区隔离 - 已实施，需确认正确性

**可延迟决策（Post-MVP）：**

8. **ADR-007**：物理服务器处理 - Week 4 实施即可

---

### ADR-001: 数据流反转策略

**上下文（Context）：**

当前系统采用 **Terraform Push 模式**：
- 静态 `.tf` 文件是配置的单一事实来源
- 开发者手动编写每个服务的 Terraform 配置
- NetBox 仅作为被动文档工具，记录已部署的资源

**问题（Problem）：**
- 手动编写 `.tf` 文件耗时且容易出错
- NetBox 数据与实际基础设施不同步
- 运维人员需要学习 Terraform HCL 语法才能创建资源

**决策（Decision）：**

采用 **渐进式迁移（Incremental Migration）** 策略，逐步将数据流反转为 **NetBox Pull 模式**：
- 最终目标：NetBox 成为配置的单一事实来源（SSOT）
- Terraform 从 NetBox API 动态拉取配置
- 允许两种模式在过渡期并存

**理由（Rationale）：**

1. **降低风险**：一次性切换所有服务风险过高，渐进式迁移允许逐步验证
2. **支持学习**：通过迁移 3 个简单 LXC 服务（Anki、Caddy、n8n）积累经验
3. **支持回滚**：如果 NetBox Pull 模式出现问题，可以回退到静态 `.tf` 文件
4. **平滑过渡**：现有服务继续使用静态 `.tf`，新服务尝试 NetBox Pull 模式

**影响（Consequences）：**

**正面影响：**
- ✅ MVP 阶段可以快速验证架构可行性
- ✅ 失败成本低，可以灵活调整策略
- ✅ 团队（你自己）有时间学习 NetBox 数据建模

**负面影响：**
- ⚠️ 过渡期需要维护两套系统（静态 `.tf` + 动态配置）
- ⚠️ 需要明确文档说明哪些服务已迁移，哪些未迁移
- ⚠️ 可能导致 Terraform 代码库复杂度暂时增加

**实施指导：**
- Week 1-2: 迁移 Anki LXC（最简单）
- Week 3: 迁移 Caddy LXC（验证网络配置）
- Week 4: 迁移 n8n LXC（验证完整流程）
- Post-MVP: 逐步迁移其他服务

---

### ADR-002: Terraform 集成模式

**上下文（Context）：**

需要实现 Terraform 从 NetBox 动态读取配置的机制。有多种技术方案可选：

**备选方案：**
1. **terraform-provider-netbox data source**：使用官方 Provider 的 data source
2. **Python 脚本生成 `.tf` 文件**：通过 NetBox API 查询数据，生成静态 Terraform 配置
3. **External Data Source**：使用 Terraform external data source 调用脚本
4. **Terraform Cloud Operator**：使用 Kubernetes Operator 模式

**问题（Problem）：**
- 需要在可靠性、可维护性、学习曲线之间权衡
- 需要考虑 `terraform-provider-netbox` 的成熟度
- 需要确保方案支持 Terraform state 管理

**决策（Decision）：**

采用 **terraform-provider-netbox data source** 作为主要集成模式，Python 脚本生成作为 Plan B：

```hcl
# terraform/proxmox/netbox-data.tf
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

# terraform/proxmox/generated.tf
resource "proxmox_virtual_environment_vm" "from_netbox" {
  for_each = {
    for vm in data.netbox_virtual_machines.proxmox_vms.virtual_machines :
    vm.name => vm
  }
  
  name        = each.value.name
  node_name   = each.value.custom_fields.proxmox_node
  vm_id       = each.value.custom_fields.proxmox_vmid
  memory      = each.value.memory
  # ...
}
```

**理由（Rationale）：**

1. **原生 Terraform 语法**：使用标准的 `data` 和 `for_each`，符合 Terraform 最佳实践
2. **自动 State 管理**：Provider 自动处理资源追踪，无需手动同步
3. **类型安全**：Provider 提供 Schema 验证，减少配置错误
4. **社区支持**：`e-breuninger/netbox` Provider 活跃维护（3.10.0 版本）
5. **Plan B 可用**：如果 Provider 不稳定，可快速切换到 Python 脚本生成方案

**影响（Consequences）：**

**正面影响：**
- ✅ 符合 Infrastructure as Code 范式
- ✅ Terraform plan/apply 流程无需修改
- ✅ State 文件自动管理，支持 HCP Terraform Cloud
- ✅ 与现有 Terraform 工作流无缝集成

**负面影响：**
- ⚠️ 依赖第三方 Provider 的稳定性（风险：Week 1 POC 必须验证）
- ⚠️ Provider 升级可能破坏兼容性（缓解：版本锁定 `>= 3.10.0`）
- ⚠️ 复杂查询可能需要多次 API 调用（性能影响：需监控）

**实施指导：**
- Week 1: POC 验证 `terraform-provider-netbox` 的可行性
- 测试 data source 的过滤能力、性能和错误处理
- 如果 POC 失败，立即切换到 Plan B（Python 脚本生成）

---

### ADR-003: 触发机制

**上下文（Context）：**

需要实现从 NetBox 变更到基础设施部署的自动化流程。触发方式有多种选择：

**备选方案：**
1. **Webhook 实时触发**：NetBox 配置 Webhook，变更时立即触发 Jenkins
2. **定时轮询**：Jenkins 定期查询 NetBox API，检测变更
3. **Git Push 触发**：手动提交变更到 Git，触发 Pipeline
4. **混合模式**：Webhook + Git 结合

**问题（Problem）：**
- 需要在即时响应和审计追踪之间权衡
- Webhook 可能失败，需要兜底机制
- 需要确保变更可追溯

**决策（Decision）：**

采用 **Webhook + Git 混合模式**：

**实时响应层（Webhook + Event Rule）：**

> **NetBox 4.x 架构说明**: NetBox 4.x 将触发条件从 Webhook 中分离到 Event Rule。Webhook 仅定义 URL 和 HTTP 配置；Event Rule 定义触发条件（content types, events）并关联到 Webhook。

```yaml
# NetBox Webhook 配置 (定义目标端点)
Name: "Jenkins Infrastructure Automation"
URL: http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook
HTTP Method: POST
Body Template: "{{ data }}"

# NetBox Event Rule 配置 (定义触发条件)
Name: "Trigger Jenkins on VM/Device Changes"
Content-types: virtualization.virtualmachine, dcim.device
Events: created, updated
Action Type: webhook
Action Object: → Jenkins Infrastructure Automation (Webhook)
```

**关键设计点：**
- ✅ **内网直连**：NetBox (192.168.1.104) 直接访问 Jenkins (192.168.1.107)，无需 Cloudflare Tunnel
- ✅ **HTTP 即可**：内网通信，使用 HTTP 协议（外部访问 Jenkins 才需要 HTTPS via Cloudflare Tunnel）
- ✅ **低延迟**：内网直连延迟 < 1 秒，远优于外部 Webhook
- ✅ **Payload 格式**：NetBox 4.x 在 `$.data` 中包含完整对象数据（`id`, `name`, `custom_fields` 等），同时 `$.snapshots.postchange` 包含变更快照

**审计追踪层（Git）：**
- Pipeline 成功后自动 `git commit` Terraform state 变更
- 保留完整的变更历史和 commit message

**兜底机制：**
- Webhook 失败时，支持 Jenkins 手动触发（传入 NetBox Resource ID）
- Generic Webhook Trigger Plugin 内置重试机制

**网络拓扑说明：**
```
内网 (192.168.1.0/24)
├── NetBox (192.168.1.104:8080)
│   └── Webhook: http://192.168.1.107:8080/generic-webhook-trigger/...
├── Jenkins (192.168.1.107:8080)
│   ├── 内网访问: http://192.168.1.107:8080
│   └── 外部访问: https://jenkins.willfan.me (via Cloudflare Tunnel)
└── GitHub Webhook → Cloudflare Tunnel → Jenkins (Git push 触发 CI/CD)
```

**Cloudflare Tunnel 的实际用途：**
- ❌ **不用于** NetBox → Jenkins Webhook（内网直连更快更简单）
- ✅ **仅用于** GitHub → Jenkins Webhook（外部到内网，必须经过隧道）
- ✅ **仅用于** 外部访问 Jenkins Web UI（如外网查看构建日志）

**理由（Rationale）：**

1. **即时响应**：内网 Webhook 延迟 < 1 秒，满足用户体验要求（NFR-P1）
2. **审计追踪**：Git commit 记录谁、何时、改了什么（NFR-S9）
3. **容错设计**：Webhook 失败不影响最终部署，可手动触发（NFR-R7）
4. **符合企业级实践**：GitOps 理念，所有变更可追溯
5. **网络简化**：内网直连无需额外的隧道配置，降低复杂度

**影响（Consequences）：**

**正面影响：**
- ✅ 用户在 NetBox UI "Create" 后立即看到进度反馈（< 1 秒触发）
- ✅ 完整的变更审计日志（满足面试展示需求）
- ✅ Webhook 失败有兜底机制，不会导致服务创建失败
- ✅ 内网直连更安全、更快、更简单

**负面影响：**
- ⚠️ 内网 Webhook 依赖网络连通性（但风险低，同一网段）
- ⚠️ Webhook 失败率可能影响自动化体验（目标：> 95% 成功率，内网更易达成）
- ⚠️ Git commit 自动化可能导致 commit message 不够详细

**实施指导：**
- 使用 Jenkins Generic Webhook Trigger Plugin（已配置）
- NetBox Webhook 配置 URL: `http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook`
- 使用 `genericVariables` JSONPath 直接提取 payload 字段到环境变量（无需 `readJSON` 插件）
- 主要数据路径: `$.data.id`, `$.data.name`, `$.data.custom_fields.*`
- 每次 Terraform Apply 成功后执行 `git add . && git commit -m "..."`
- 测试内网 Webhook 连通性：`curl -X POST http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=test`

---

### ADR-004: 多平台路由策略

**上下文（Context）：**

系统需要支持异构环境：Proxmox VE、VMware ESXi、Physical Servers。需要一个路由机制将 NetBox 资源定向到正确的 Terraform 工作区和 Pipeline。

**备选方案：**
1. **单一 Pipeline + 条件分支**：在一个 Jenkinsfile 中用 `if/else` 处理所有平台
2. **Router Pipeline + Platform-specific Pipelines**：专门的路由 Pipeline 根据条件触发不同 Pipeline
3. **多个独立 Pipeline + 手动选择**：为每个平台创建独立 Job，用户手动选择
4. **Terraform Workspace 隔离**：使用 Terraform workspace 区分平台

**问题（Problem）：**
- 需要在代码复杂度和可维护性之间权衡
- 需要支持未来扩展（如 Oracle Cloud）
- 需要确保平台隔离，降低爆炸半径

**决策（Decision）：**

采用 **Router Pipeline + Custom Field 驱动 + 独立目录**：

**架构设计：**
```
NetBox Webhook
    ↓
Jenkins Router Pipeline (Jenkinsfile-webhook-router)
    ↓ 解析 custom_fields.infrastructure_platform
    ├─→ proxmox → Jenkinsfile-proxmox-provisioning (terraform/proxmox/)
    ├─→ esxi    → Jenkinsfile-esxi-provisioning (terraform/esxi/)
    └─→ physical → Jenkinsfile-physical-device-sync (跳过 Terraform)
```

**NetBox Custom Field：**
```yaml
infrastructure_platform:
  type: Selection
  choices: [proxmox, esxi, physical]
  required: true
```

**Router Pipeline 逻辑：**
```groovy
def platform = payload.data.custom_fields.infrastructure_platform
switch(platform) {
    case 'proxmox':
        build job: 'Proxmox-Provisioning', parameters: [...]
        break
    case 'esxi':
        build job: 'ESXi-Provisioning', parameters: [...]
        break
    case 'physical':
        build job: 'Physical-Device-Sync', parameters: [...]
        break
}
```

**Terraform 目录隔离（ADR-008 关联）：**
```
terraform/
├── proxmox/     # 独立 backend, provider, state
├── esxi/        # 独立 backend, provider, state
└── modules/     # 共享模块
```

**理由（Rationale）：**

1. **集中管理**：Router Pipeline 是唯一的路由决策点，便于维护
2. **平台隔离**：独立目录 + 独立 state，完全隔离，降低爆炸半径（ADR-008）
3. **易于扩展**：新增平台只需添加新 Pipeline，Router 逻辑仅增加一个 case 分支
4. **Custom Field 驱动**：NetBox 数据模型是路由决策的单一来源，无需硬编码
5. **职责分离**：Router 只负责路由，具体的 Terraform/Ansible 逻辑在 Platform Pipeline 中

**影响（Consequences）：**

**正面影响：**
- ✅ 新平台扩展仅需 10-15 分钟（创建 Jenkinsfile + 添加 case）
- ✅ Proxmox 故障不会影响 ESXi 资源（完全隔离）
- ✅ Router 逻辑简单，易于测试和调试
- ✅ 符合单一职责原则和开闭原则

**负面影响：**
- ⚠️ 需要维护多个 Jenkinsfile（Router + Proxmox + ESXi + Physical）
- ⚠️ Router Pipeline 本身成为单点故障（缓解：轻量级逻辑，失败概率低）
- ⚠️ 调试时需要跨多个 Pipeline 查看日志

**实施指导：**
- Week 1-2: 实现 Router Pipeline + Proxmox Pipeline
- Week 3-4: 添加 Physical Device Sync Pipeline
- Post-MVP: 添加 ESXi Pipeline（仅在需要时）

---

### ADR-005: NetBox 数据建模

**上下文（Context）：**

NetBox 需要存储足够的元数据来驱动 Terraform 和 Ansible。数据建模有两种策略：

**备选方案：**
1. **核心字段先行**：只定义必需的 Custom Fields，逐步扩展
2. **完整建模一次性设计**：预先定义所有可能需要的字段
3. **最小化建模**：仅使用 NetBox 内置字段，避免 Custom Fields

**问题（Problem）：**
- 过于简单的模型可能无法满足后续需求
- 过于复杂的模型增加学习成本和维护负担
- Custom Fields 设计不当可能导致后期重构

**决策（Decision）：**

采用 **核心字段先行，逐步扩展** 策略：

**MVP 阶段 Custom Fields（Week 1）：**

| Field Name | Type | Choices/Description | Required |
|------------|------|---------------------|----------|
| `infrastructure_platform` | Selection | `proxmox`, `esxi`, `physical` | ✅ |
| `automation_level` | Selection | `fully_automated`, `requires_approval`, `manual_only` | ✅ |
| `proxmox_node` | Selection | `pve0`, `pve1`, `pve2` | Conditional |
| `proxmox_vmid` | Integer | 100-999 | Conditional |
| `ansible_groups` | Multiple Selection | `pve_vms`, `pve_lxc`, `docker`, `tailscale` | Optional |
| `playbook_name` | Text | 例如 `deploy-netbox.yml` | Optional |

**Post-MVP 扩展字段（按需添加）：**
- `esxi_host`：ESXi 主机引用
- `esxi_datastore`：Datastore 选择
- `backup_policy`：PBS 备份策略
- `monitoring_enabled`：是否启用监控

**理由（Rationale）：**

1. **平衡完整性与复杂度**：6 个核心字段足以支持 MVP，不会让用户（自己）感到困惑
2. **降低前期设计负担**：避免过度设计，基于实际需求迭代
3. **支持向后兼容**：NetBox 支持动态添加 Custom Fields，不会破坏现有数据
4. **快速验证**：Week 1 可以完成数据模型定义并开始测试

**影响（Consequences）：**

**正面影响：**
- ✅ Week 1 可以快速完成 NetBox 配置并进入实施
- ✅ 减少学习曲线，专注核心功能
- ✅ 灵活应对需求变化

**负面影响：**
- ⚠️ 可能需要后期添加字段（但 NetBox 支持平滑添加）
- ⚠️ 初期字段命名不当可能导致后期重命名（缓解：Week 1 仔细评审）

**实施指导：**
- Week 1: 创建 6 个核心 Custom Fields
- Week 1: 手动录入 3-5 个测试资源验证字段设计
- Week 2-4: 根据实际使用反馈调整字段
- Post-MVP: 按需添加扩展字段

---

### ADR-006: 错误恢复策略

**上下文（Context）：**

Pipeline 执行过程中可能出现多种失败：
- Terraform Apply 失败（API 错误、资源冲突）
- Ansible 部署失败（SSH 连接失败、服务启动失败）
- Webhook 触发失败（网络问题）

**备选方案：**
1. **失败即终止，手动修复**：Pipeline 失败后不自动重试，需要人工干预
2. **自动重试 N 次**：失败后自动重试固定次数
3. **状态标记 + 手动重试**：在 NetBox 标记失败状态，支持手动触发重试
4. **自动回滚**：失败后自动回滚到上一个稳定状态

**问题（Problem）：**
- 自动重试可能掩盖真正的问题
- 手动修复增加运维负担
- 需要保留失败意图，支持后续修复

**决策（Decision）：**

采用 **状态标记 + 重试机制**：

**状态机设计：**
```
planned → provisioning → active
   ↓            ↓
   └─→ failed_provisioning ←┘
```

**Pipeline 失败处理：**
```groovy
post {
    failure {
        script {
            // 回写 NetBox 状态为 failed_provisioning
            sh '''
                curl -X PATCH http://192.168.1.104:8080/api/dcim/virtual-machines/${NETBOX_VM_ID}/ \
                  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
                  -d '{"status": "failed"}'
            '''
            // 记录错误日志到 NetBox Comments
            sh 'python3 scripts/log-error-to-netbox.py "${BUILD_URL}" "${BUILD_NUMBER}"'
        }
    }
}
```

**重试机制：**
- 用户在 NetBox 中手动将状态从 `failed_provisioning` 改回 `planned`
- 触发 Webhook，Pipeline 重新执行
- 支持最多 3 次自动重试（通过 Custom Field `retry_count` 追踪）

**幂等性保证（NFR-R4, NFR-R5）：**
- Terraform 通过 state 检测资源已存在，不会重复创建
- Ansible 使用 `creates:`、`when:` 等幂等性守护
- Pipeline 可以安全地多次执行

**理由（Rationale）：**

1. **保留意图**：失败的资源标记为 `failed_provisioning`，不会丢失创建意图
2. **支持修复**：用户可以查看 Pipeline 日志，修复根本问题后重试
3. **避免无限重试**：手动触发重试，避免掩盖真正的问题
4. **错误追踪**：NetBox Comments 记录错误日志和 Jenkins build URL，便于故障排查
5. **符合幂等性原则**：重试不会导致资源重复创建或状态不一致

**影响（Consequences）：**

**正面影响：**
- ✅ 失败的虚拟机不会丢失，可以后续修复
- ✅ 错误日志集中存储在 NetBox，便于查看
- ✅ 支持安全重试，不会破坏已创建的资源

**负面影响：**
- ⚠️ 需要手动触发重试，增加运维负担（可接受，Homelab 场景）
- ⚠️ 需要开发 NetBox 状态回写脚本（额外工作量约 1-2 小时）

**实施指导：**
- Week 2: 实现 Pipeline `post.failure` 块的状态回写逻辑
- Week 3: 测试 Terraform 和 Ansible 的幂等性
- Week 4: 测试完整的失败 → 修复 → 重试流程

---

### ADR-007: 物理服务器处理

**上下文（Context）：**

系统需要管理三种资源类型：
- Proxmox VM/LXC：需要 Terraform provisioning + Ansible 配置
- ESXi VM：需要 Terraform provisioning + Ansible 配置
- Physical Servers：**不需要** provisioning（已存在的物理机）

**备选方案：**
1. **物理服务器也走 Terraform 流程**：使用 Terraform null_resource 仅做占位
2. **跳过 Terraform，仅 Ansible**：物理服务器直接从 NetBox 生成 Ansible Inventory
3. **手动维护物理服务器 Inventory**：不通过 NetBox 管理物理服务器

**问题（Problem）：**
- 物理服务器无需"创建"，Terraform 的价值仅在于资源生命周期管理
- 使用 Terraform null_resource 会增加不必要的复杂度
- 手动维护 Inventory 违背 NetBox SSOT 理念

**决策（Decision）：**

采用 **跳过 Terraform，仅 Inventory + Ansible**：

**架构设计：**
```
NetBox Physical Device (custom_fields.infrastructure_platform = "physical")
    ↓ Webhook
Router Pipeline
    ↓ 识别 platform = "physical"
Physical Device Sync Pipeline
    ↓ 跳过 Terraform
    ↓ 直接从 NetBox 生成 Ansible Inventory
Ansible Playbook (配置管理)
```

**Jenkinsfile-physical-device-sync：**
```groovy
stage('Sync Inventory') {
    steps {
        sh 'python3 scripts/netbox-to-inventory.py --platform physical'
    }
}

stage('Ansible Deploy') {
    steps {
        dir('ansible') {
            sh 'ansible-playbook playbooks/deploy-physical.yml'
        }
    }
}
```

**理由（Rationale）：**

1. **物理资源无需 provisioning**：物理服务器已存在，Terraform 的 CRUD 操作不适用
2. **简化流程**：跳过 Terraform 减少不必要的复杂度
3. **Ansible 足够**：物理服务器仅需配置管理（安装软件、配置服务），Ansible 完全胜任
4. **NetBox 仍为 SSOT**：物理服务器信息仍存储在 NetBox，Inventory 仍从 NetBox 生成

**影响（Consequences）：**

**正面影响：**
- ✅ Pipeline 执行时间更短（跳过 Terraform init/plan/apply）
- ✅ 逻辑更清晰，职责分离（虚拟资源走 Terraform，物理资源走 Ansible）
- ✅ 减少 Terraform state 文件大小

**负面影响：**
- ⚠️ 需要额外的 Physical Device Sync Pipeline（开发成本约 2-3 小时）
- ⚠️ 物理服务器和虚拟资源的处理流程不统一（可接受，因为本质不同）

**实施指导：**
- Week 4: 开发 `Jenkinsfile-physical-device-sync`
- Week 4: 测试至少 1 台物理服务器的配置管理（如 PBS 主机）
- Post-MVP: 将所有物理服务器（Proxmox 节点、ESXi 主机）纳入管理

---

### ADR-008: Terraform 工作区隔离

**上下文（Context）：**

多平台管理需要在以下方案中选择：

**备选方案：**
1. **单一 Terraform 目录 + Workspace**：使用 `terraform workspace` 切换环境
2. **独立目录 + 独立 Backend**：每个平台一个目录（`terraform/proxmox/`, `terraform/esxi/`）
3. **Monorepo + Module**：所有平台在同一目录，使用 Module 区分

**问题（Problem）：**
- Workspace 模式下，所有平台共享 provider 和 state backend，爆炸半径大
- 独立目录增加代码重复，但隔离性更好
- 需要在隔离性和可维护性之间权衡

**决策（Decision）：**

采用 **独立目录（proxmox/ esxi/）+ 独立 Backend**：

**目录结构：**
```
terraform/
├── proxmox/
│   ├── versions.tf        # terraform { cloud { workspaces { name = "iac-proxmox" } } }
│   ├── provider.tf        # provider "proxmox" { ... }
│   ├── netbox-data.tf     # data source
│   ├── generated.tf       # 动态资源
│   └── ...
├── esxi/
│   ├── versions.tf        # terraform { cloud { workspaces { name = "iac-esxi" } } }
│   ├── provider.tf        # provider "vsphere" { ... }
│   └── pbs.tf
└── modules/
    ├── proxmox-vm/
    ├── proxmox-lxc/
    └── esxi-vm/
```

**Backend 隔离：**
```hcl
# terraform/proxmox/versions.tf
terraform {
  cloud {
    organization = "homelab-roseville"
    workspaces {
      name = "iac-proxmox"  # 独立 workspace
    }
  }
}

# terraform/esxi/versions.tf
terraform {
  cloud {
    organization = "homelab-roseville"
    workspaces {
      name = "iac-esxi"  # 独立 workspace
    }
  }
}
```

**共享 Module 复用：**
```hcl
# terraform/proxmox/netbox.tf
module "netbox" {
  source = "../modules/proxmox-vm"  # 共享模块
  # ...
}
```

**理由（Rationale）：**

1. **完全隔离，降低爆炸半径**：Proxmox 的 Terraform 错误不会影响 ESXi 资源
2. **独立 Provider 配置**：每个平台使用不同的 Provider，避免冲突
3. **独立 State 文件**：State 文件分离，Terraform lock 不会互相影响
4. **Pipeline 并行执行**：不同平台的 Pipeline 可以并发运行，不会争抢 state lock
5. **Module 复用减少重复**：共享的逻辑放在 `modules/`，避免代码重复

**影响（Consequences）：**

**正面影响：**
- ✅ Proxmox 和 ESXi 完全隔离，故障不会蔓延
- ✅ 支持并行部署，提升效率
- ✅ 符合 Terraform 最佳实践（按环境/平台隔离）

**负面影响：**
- ⚠️ 每个目录需要独立执行 `terraform init`（增加初始化时间）
- ⚠️ 跨平台的全局变量需要在每个目录重复定义（可通过 `variables.tf` 部分解决）
- ⚠️ 增加目录数量，可能让新手感到困惑（缓解：文档清晰说明）

**实施指导：**
- 当前已按此模式实施（`terraform/proxmox/`, `terraform/esxi/`, `terraform/oci/`）
- Week 1: 确保每个目录的 Backend 配置正确
- Week 2-4: 测试并行执行的可行性

---

### 决策影响分析

**实施顺序：**

1. **Week 1 优先**：ADR-002（POC 验证）、ADR-005（数据建模）
2. **Week 1-2 并行**：ADR-001（迁移首个服务）、ADR-004（Router Pipeline）
3. **Week 2-3**：ADR-003（Webhook 配置）、ADR-006（错误处理）
4. **Week 4**：ADR-007（物理服务器）
5. **持续验证**：ADR-008（已实施，需确认）

**跨组件依赖：**

- ADR-001 依赖 ADR-002：数据流反转需要先验证 Terraform 集成可行性
- ADR-004 依赖 ADR-005：Router 需要读取 Custom Fields 进行路由决策
- ADR-003 依赖 ADR-004：Webhook 触发 Router Pipeline
- ADR-006 依赖 ADR-003：错误状态回写需要 NetBox API 连接

**关键风险决策：**

- **ADR-002 是最大风险点**：terraform-provider-netbox 的稳定性未知，Week 1 POC 必须验证，否则切换到 Plan B
- **ADR-001 定义整体策略**：渐进式迁移是降低风险的核心决策
- **ADR-008 已实施**：需要验证当前的目录隔离是否正确配置

---
## 实施模式与一致性规则

### 潜在冲突点识别

本项目中识别出 **23 个潜在冲突点**，AI Agent 在实施时可能做出不同选择，需要明确的一致性规则。

---

### 命名模式（Naming Patterns）

#### Terraform 命名规范

**HCL 标识符命名：**
- **规则**：`snake_case`（全小写 + 下划线）
- **适用于**：resources, variables, modules, outputs, locals
- **示例**：
  ```hcl
  resource "proxmox_virtual_environment_vm" "netbox_vm" { }
  variable "vm_password" { }
  module "windows_server" { }
  output "netbox_ip" { }
  ```
- **禁止**：`camelCase`, `PascalCase`, `kebab-case`

**文件命名：**
- **规则**：`kebab-case.tf`（全小写 + 连字符）
- **示例**：`netbox.tf`, `windows-server.tf`, `pve-cluster.tf`
- **特殊文件**：`versions.tf`, `provider.tf`, `variables.tf`, `outputs.tf`, `main.tf`（标准名称，无需 kebab-case）
- **禁止**：`netbox_vm.tf`, `NetBox.tf`

**模块目录命名：**
- **规则**：`kebab-case/`
- **示例**：`modules/proxmox-vm/`, `modules/esxi-vm/`
- **禁止**：`modules/proxmox_vm/`, `modules/ProxmoxVM/`

**变量描述格式：**
- **规则**：简洁的单行描述，复杂说明使用多行字符串
- **示例**：
  ```hcl
  variable "vm_name" {
    description = "Name of the virtual machine"
    type        = string
  }
  
  variable "network_config" {
    description = <<-EOT
      Network configuration for the VM.
      Must include: bridge, vlan, ip_address, gateway.
      Optional: dns_servers (list of strings).
    EOT
    type = object({...})
  }
  ```

#### Ansible 命名规范

**变量命名：**
- **规则**：`snake_case`（全小写 + 下划线）
- **服务前缀**：变量名以服务名开头
- **示例**：`netbox_port`, `pbs_zfs_pool_name`, `immich_upload_dir`
- **禁止**：`netboxPort`, `PbsZfsPoolName`

**Vault 变量命名：**
- **规则**：`vault_` 前缀 + 描述性名称
- **示例**：`vault_proxmox_password`, `vault_tailscale_auth_key`, `vault_cloudflare_api_token`
- **别名变量**：去掉 `vault_` 前缀
  ```yaml
  # inventory/group_vars/tailscale.yml
  tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
  ```

**任务名称：**
- **规则**：描述性英文，动词开头，首字母大写
- **示例**：
  - "Install required packages"
  - "Deploy systemd service file"
  - "Enable and start service"
  - "Wait for service port"
- **禁止**：
  - "install packages"（首字母小写）
  - "Packages installation"（名词开头）
  - "安装软件包"（中文）

**文件命名：**
- **规则**：`kebab-case`
- **Playbook**：`deploy-<service>.yml`, `sync-<target>.yml`
- **Role 目录**：`roles/service-name/`
- **示例**：`deploy-netbox.yml`, `pbs-client/`, `netbox-sync/`
- **禁止**：`deploy_netbox.yml`, `PbsClient/`

**Host/Group 命名：**
- **Host 名称**：`kebab-case`（`windows-server`, `esxi-01`）
- **Group 名称**：`snake_case`（`pve_vms`, `proxmox_cluster`）
- **原因**：Host 是基础设施名称（类似文件名），Group 是代码标识符（类似变量名）

#### Python 脚本命名

**文件命名：**
- **规则**：`kebab-case.py`
- **示例**：`get-secrets.sh`, `sync-to-notion.py`, `netbox-to-terraform.py`
- **禁止**：`getSecrets.py`, `sync_to_notion.py`

**函数/变量命名：**
- **规则**：`snake_case`（遵循 PEP 8）
- **示例**：`fetch_netbox_data()`, `vm_config`, `terraform_state`

#### NetBox Custom Fields 命名

**字段名称：**
- **规则**：`snake_case`
- **示例**：`infrastructure_platform`, `automation_level`, `proxmox_node`, `proxmox_vmid`
- **禁止**：`infrastructurePlatform`, `Automation-Level`

---

### 结构模式（Structure Patterns）

#### Terraform 项目结构

**Per-Service 文件模式：**

每个服务独立一个 `.tf` 文件，包含：

```hcl
# terraform/proxmox/netbox.tf

# 1. 模块调用
module "netbox" {
  source = "../modules/proxmox-vm"
  # 配置...
}

# 2. Ansible 动态清单
resource "ansible_host" "netbox" {
  name   = "netbox"
  groups = ["pve_vms"]
  variables = {
    ansible_host = "192.168.1.104"
  }
  depends_on = [module.netbox]
}

# 3. 输出
output "netbox_ip" {
  value = module.netbox.default_ip
}
```

**目录隔离：**
```
terraform/
├── proxmox/        # 独立 backend, provider, state
├── esxi/           # 独立 backend, provider, state
├── oci/            # 独立 backend, provider, state
├── netbox-integration/  # Netbox 数据推送
└── modules/        # 共享模块（3-file 标准）
```

**模块标准结构：**
```
modules/proxmox-vm/
├── main.tf         # 资源定义
├── variables.tf    # 输入变量
└── outputs.tf      # 输出值
```

**禁止**：
- ❌ 在模块中添加 `provider.tf`（由调用方定义）
- ❌ 在模块中添加 `versions.tf`（由调用方定义）
- ❌ 创建超过 3 个文件的模块（除非有充分理由）

#### Ansible 项目结构

**Role 标准结构：**
```
roles/service-name/
├── tasks/
│   └── main.yml       # 主要任务
├── defaults/
│   └── main.yml       # 默认变量
├── templates/         # Jinja2 模板（可选）
├── handlers/          # Handler（可选）
│   └── main.yml
└── files/             # 静态文件（可选）
```

**禁止**：
- ❌ 创建空目录（如果没有 templates，不创建 `templates/` 目录）
- ❌ 在 Role 中创建 `vars/main.yml`（使用 `defaults/` 即可）
- ❌ 在 Role 中创建 `meta/main.yml`（除非定义依赖关系）

**Playbook 两阶段模式：**
```yaml
# ansible/playbooks/deploy-netbox.yml

# ===== 第一阶段：部署 =====
- name: Deploy Netbox Service
  hosts: netbox
  become: yes
  roles:
    - docker
    - netbox

# ===== 第二阶段：验证 =====
- name: Verify Netbox Deployment
  hosts: netbox
  become: yes
  tags: [verify]
  tasks:
    - name: Wait for service port
      wait_for:
        port: 8080
        timeout: 60
    
    - name: Check HTTP endpoint
      uri:
        url: "http://localhost:8080"
        status_code: [200, 302]
```

**Inventory 组织：**
```
ansible/inventory/
├── terraform.yml           # Proxmox 动态清单
├── terraform-esxi.yml      # ESXi 动态清单
├── groups.yml              # 组层次结构
├── group_vars/
│   ├── all/
│   │   ├── common.yml
│   │   └── vault.yml       # 加密密码
│   ├── proxmox_cluster.yml
│   └── tailscale.yml
└── host_vars/
    ├── homepage.yml
    └── netbox.yml
```

#### 辅助脚本位置

**规则**：所有脚本统一放在 `scripts/` 目录

```
scripts/
├── get-secrets.sh              # Vault 密码提取
├── refresh-terraform-state.sh  # State 刷新
├── sync-to-notion.py           # Notion 同步
├── netbox-to-terraform.py      # NetBox 数据转换
└── setup-env.sh                # 环境初始化
```

**禁止**：
- ❌ `terraform/scripts/`
- ❌ `ansible/scripts/`
- ❌ 在 `.tf` 文件中使用相对路径 `../scripts/`（使用项目根目录的绝对路径）

#### 临时文件与 Gitignore

**临时文件位置：**
- Terraform secrets：`terraform/*/secrets.auto.tfvars`（每个平台目录下）
- Ansible Vault 密码：`ansible/.vault_pass`
- Terraform state 缓存：`ansible_host` 资源生成的本地缓存

**必须 Gitignore：**
```gitignore
# Secrets
*.auto.tfvars
.vault_pass

# Terraform
.terraform/
*.tfstate
*.tfstate.backup

# Ansible
*.retry
collections/

# Python
__pycache__/
*.pyc
.venv/
```

---

### 格式模式（Format Patterns）

#### Git Commit Message

**规则**：Conventional Commits（英文）

**格式**：
```
<type>(<scope>): <subject>

<body>
```

**Type 类型：**
- `feat`: 新功能
- `fix`: Bug 修复
- `chore`: 杂项（依赖更新、配置变更）
- `docs`: 文档变更
- `refactor`: 重构
- `test`: 测试相关

**示例：**
```
feat(terraform): add netbox vm provisioning

- Implement terraform-provider-netbox data source
- Add dynamic resource generation with for_each
- Update ansible inventory to include new VMs

Closes #123
```

**禁止：**
- ❌ "update files"（无意义的 subject）
- ❌ "修复 bug"（中文）
- ❌ 无 type 前缀的 commit

#### Terraform 代码格式

**Lifecycle Block：**
```hcl
resource "proxmox_virtual_environment_vm" "example" {
  # ...
  
  lifecycle {
    ignore_changes = [
      clone,
      full_clone,
      efidisk,
      ostemplate,
      description,
    ]
  }
}
```

**条件表达式：**
- **简单条件**：单行
  ```hcl
  count = var.create_vm ? 1 : 0
  ```
- **复杂条件**：多行
  ```hcl
  memory = (
    var.vm_type == "large" ? 8192 :
    var.vm_type == "medium" ? 4096 :
    2048
  )
  ```

#### Ansible 代码格式

**YAML 列表格式：**
- **短列表**（≤ 3 项）：单行
  ```yaml
  packages: [git, curl, vim]
  ```
- **长列表**（> 3 项）：多行
  ```yaml
  packages:
    - git
    - curl
    - vim
    - docker.io
    - python3-pip
  ```

**复杂条件格式：**
```yaml
- name: Install package
  apt:
    name: docker.io
    state: present
  when:
    - ansible_distribution == "Ubuntu"
    - ansible_distribution_major_version | int >= 20
    - docker_enabled | default(true) | bool
```

**变量引用：**
- **简单引用**：`{{ variable_name }}`
- **复杂表达式**：使用过滤器和管道
  ```yaml
  path: "{{ base_path | default('/opt') }}/{{ service_name }}"
  ```

#### 文档格式

**学习笔记命名：**
- **格式**：`YYYY-MM-DD-topic-description.md`
- **示例**：`2026-02-05-netbox-ssot-architecture.md`
- **位置**：`docs/learningnotes/`

**其他文档命名：**
- 设计文档：`docs/designs/<topic>-architecture.md`
- 部署指南：`docs/deployment/<service>-deployment.md`
- 故障排查：`docs/troubleshooting/<issue>-troubleshooting.md`

---

### 通信模式（Communication Patterns）

#### NetBox Webhook Payload 解析

**标准解析模式（genericVariables JSONPath 提取）：**

> **注意**: 不使用 `readJSON` 插件。Generic Webhook Trigger 插件通过 `genericVariables` 配置直接将 JSONPath 提取到环境变量，无需额外 JSON 解析。

```groovy
// Jenkinsfile-webhook-router — GenericTrigger 配置
GenericTrigger(
    genericVariables: [
        [key: 'netbox_event', value: '$.event'],
        [key: 'netbox_model', value: '$.model'],
        [key: 'netbox_object_id', value: '$.data.id'],
        [key: 'netbox_object_name', value: '$.data.name'],
        [key: 'netbox_object_status', value: '$.data.status.value'],
        [key: 'infrastructure_platform', value: '$.data.custom_fields.infrastructure_platform'],
        [key: 'automation_level', value: '$.data.custom_fields.automation_level'],
        [key: 'proxmox_node', value: '$.data.custom_fields.proxmox_node'],
        [key: 'proxmox_vmid', value: '$.data.custom_fields.proxmox_vmid'],
        [key: 'ansible_groups', value: '$.data.custom_fields.ansible_groups']
    ],
    token: 'netbox-webhook',
    regexpFilterExpression: '^(created|updated) (virtualmachine|device)$',
    regexpFilterText: '$netbox_event $netbox_model'
)

// Pipeline 中直接使用环境变量
def platform = env.infrastructure_platform
def vmId = env.netbox_object_id
def vmName = env.netbox_object_name
```

**错误处理：**
```groovy
if (!platform) {
    error "Missing infrastructure_platform custom field in NetBox payload"
}

if (!['proxmox', 'esxi', 'physical'].contains(platform)) {
    error "Unknown platform: ${platform}. Expected: proxmox, esxi, or physical"
}
```

#### NetBox API 调用模式

**状态回写：**
```bash
# scripts/update-netbox-status.sh
curl -X PATCH "http://192.168.1.104:8080/api/dcim/virtual-machines/${VM_ID}/" \
  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "active",
    "comments": "Provisioned by Jenkins build #'"${BUILD_NUMBER}"'"
  }'
```

**错误处理：**
```bash
response=$(curl -s -w "\n%{http_code}" -X PATCH ...)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" -ne 200 ]; then
    echo "ERROR: NetBox API returned $http_code: $body" >&2
    exit 1
fi
```

#### Ansible Facts 变量命名

**自定义 Facts：**
- **前缀**：`ansible_local_<service>_`（避免与内置 facts 冲突）
- **示例**：`ansible_local_netbox_version`, `ansible_local_pbs_datastore`

**使用场景：**
```yaml
- name: Set custom fact
  set_fact:
    ansible_local_netbox_version: "{{ netbox_version }}"
    cacheable: yes
```

#### Jenkins Pipeline 参数传递

**标准参数格式：**
```groovy
build job: 'Proxmox-Provisioning', parameters: [
    string(name: 'NETBOX_VM_ID', value: vmId),
    string(name: 'NETBOX_VM_NAME', value: vmName),
    string(name: 'PLATFORM', value: platform),
    booleanParam(name: 'DRY_RUN', value: false)
]
```

---

### 流程模式（Process Patterns）

#### 错误处理模式

**Ansible 任务错误处理：**

**规则**：优先使用 `failed_when` 而非 `ignore_errors`

**示例：**
```yaml
# ✅ 推荐：明确定义失败条件
- name: Check service status
  command: systemctl is-active netbox
  register: service_status
  failed_when:
    - service_status.rc != 0
    - service_status.rc != 3  # 3 = inactive，可接受
  changed_when: false

# ❌ 避免：忽略所有错误
- name: Check service status
  command: systemctl is-active netbox
  ignore_errors: yes
```

**异常情况使用 `ignore_errors`：**
```yaml
- name: Attempt optional optimization
  command: some_optional_command
  ignore_errors: yes
  tags: [optional]
```

#### 重试逻辑

**标准重试参数：**
- `retries: 3`（最多重试 3 次）
- `delay: 5`（重试间隔 5 秒）
- `until`：明确的成功条件

**示例：**
```yaml
- name: Wait for service to be ready
  uri:
    url: "http://localhost:8080/health"
    status_code: 200
  register: health_check
  retries: 12
  delay: 5
  until: health_check.status == 200
```

#### 条件执行模式

**简单条件：**
```yaml
- name: Install Docker
  apt:
    name: docker.io
    state: present
  when: docker_enabled | default(true) | bool
```

**复杂条件限制：**
- **规则**：`when` 条件不超过 5 个逻辑判断
- **超过限制**：提取到变量或使用 `block` + `when`

**示例：**
```yaml
# ✅ 推荐：提取复杂条件到变量
- name: Check if deployment is needed
  set_fact:
    should_deploy: >-
      {{
        (netbox_version != current_version | default('')) and
        (deployment_enabled | default(true) | bool) and
        (ansible_distribution == 'Ubuntu') and
        (ansible_distribution_major_version | int >= 20)
      }}

- name: Deploy Netbox
  include_tasks: deploy.yml
  when: should_deploy | bool
```

#### 幂等性保证模式

**文件创建幂等性：**
```yaml
- name: Create configuration file
  template:
    src: config.yml.j2
    dest: /etc/service/config.yml
    owner: root
    group: root
    mode: '0644'
  # template 模块天然幂等，内容变化才会标记 changed
```

**命令执行幂等性：**
```yaml
- name: Initialize database
  command: /opt/service/init-db.sh
  args:
    creates: /var/lib/service/.initialized
  # creates 参数确保幂等性
```

**手动幂等性守护：**
```yaml
- name: Run one-time setup
  command: /opt/service/setup.sh
  register: setup_result
  changed_when: "'Already configured' not in setup_result.stdout"
```

---

### 强制执行指南（Enforcement Guidelines）

#### 所有 AI Agent 必须遵守（MUST）

1. **命名约定绝对统一**：
   - Terraform HCL 标识符必须使用 `snake_case`
   - 文件名必须使用 `kebab-case`
   - Ansible 变量必须使用 `snake_case` 且带服务前缀

2. **结构模式强制执行**：
   - Terraform 每个服务一个 `.tf` 文件，包含 module + ansible_host + output
   - Ansible 每个 playbook 必须包含 Deploy play 和 Verify play
   - 模块必须遵循 3-file 标准（`main.tf`, `variables.tf`, `outputs.tf`）

3. **幂等性强制要求**：
   - 所有 Terraform 资源必须可安全重跑
   - 所有 Ansible 任务必须幂等，使用 `creates:`、`when:`、`changed_when:` 守护
   - Pipeline 失败后必须可安全重试

4. **错误处理统一**：
   - Ansible 优先使用 `failed_when` 而非 `ignore_errors`
   - Pipeline 失败必须回写 NetBox 状态为 `failed_provisioning`
   - 错误日志必须包含 Jenkins build URL 和详细信息

5. **密码管理统一**：
   - 所有密码必须存储在 `ansible/inventory/group_vars/all/vault.yml`
   - 密码变量必须使用 `vault_` 前缀
   - 别名变量去掉 `vault_` 前缀，放在 inventory 或 role defaults

#### 模式验证方法

**自动验证：**
```bash
# Terraform 格式检查
terraform fmt -check -recursive terraform/

# Ansible 语法检查
ansible-playbook playbooks/*.yml --syntax-check

# Ansible Lint（部分规则已禁用）
ansible-lint ansible/
```

**手动验证清单：**
- [ ] 新增 `.tf` 文件是否遵循 per-service 模式？
- [ ] 新增 playbook 是否包含 verify play？
- [ ] 新增变量是否使用正确的命名约定？
- [ ] Commit message 是否符合 Conventional Commits？

#### 模式违规处理

**发现违规时：**
1. 立即在代码审查中指出（人工审查或 AI Agent 自查）
2. 引用本文档的相关章节
3. 要求修正后再合并

**更新模式流程：**
1. 在项目 Issue 中提出模式变更建议
2. 讨论并达成共识
3. 更新本架构文档
4. 通知所有 AI Agent（更新 AGENTS.md 或相关配置）

---

### 模式示例（Pattern Examples）

#### ✅ 正确示例

**Terraform Per-Service 文件：**
```hcl
# terraform/proxmox/caddy.tf

module "caddy" {
  source = "../modules/proxmox-lxc"
  
  vm_name      = "caddy"
  target_node  = "pve0"
  vmid         = 110
  ip_address   = "192.168.1.110/24"
  cores        = 1
  memory       = 512
  storage_pool = var.storage_pool
  template     = "debian-12-standard"
}

resource "ansible_host" "caddy" {
  name   = "caddy"
  groups = ["pve_lxc", "tailscale"]
  variables = {
    ansible_host = "192.168.1.110"
  }
  depends_on = [module.caddy]
}

output "caddy_ip" {
  value       = module.caddy.default_ip
  description = "Caddy reverse proxy IP address"
}
```

**Ansible Playbook 两阶段：**
```yaml
# ansible/playbooks/deploy-caddy.yml

- name: Deploy Caddy Reverse Proxy
  hosts: caddy
  become: yes
  roles:
    - common
    - tailscale
    - caddy

- name: Verify Caddy Deployment
  hosts: caddy
  become: yes
  tags: [verify]
  tasks:
    - name: Wait for Caddy HTTP port
      wait_for:
        port: 80
        timeout: 30
    
    - name: Wait for Caddy HTTPS port
      wait_for:
        port: 443
        timeout: 30
    
    - name: Check Caddy service status
      systemd:
        name: caddy
      register: caddy_status
    
    - name: Assert Caddy is running
      assert:
        that:
          - caddy_status.status.ActiveState == "active"
        fail_msg: "Caddy service is not active"
        success_msg: "✅ Caddy deployment verified successfully"
```

**Vault 密码间接引用：**
```yaml
# ansible/inventory/group_vars/all/vault.yml (加密)
vault_cloudflare_api_token: "secret_token_here"

# ansible/roles/caddy/defaults/main.yml
cloudflare_api_token: "{{ vault_cloudflare_api_token }}"
# Comment: vault indirect reference
```

#### ❌ 反模式（Anti-Patterns）

**❌ 错误：混合命名风格**
```hcl
# 错误示例 - 不要这样写
resource "proxmox_virtual_environment_vm" "NetBox-VM" {  # ❌ PascalCase + kebab-case
  name = "netBox"  # ❌ camelCase
}

variable "vmPassword" {  # ❌ camelCase
  description = "VM password"
}
```

**❌ 错误：缺少 Verify Play**
```yaml
# 错误示例 - 不完整的 playbook
- name: Deploy Service
  hosts: myservice
  roles:
    - myservice
# ❌ 缺少 Verify play！
```

**❌ 错误：不幂等的任务**
```yaml
# 错误示例 - 不幂等
- name: Initialize database
  command: /opt/service/init-db.sh
  # ❌ 没有 creates 或 when 守护，每次都会执行
```

**❌ 错误：滥用 ignore_errors**
```yaml
# 错误示例
- name: Deploy service
  command: /opt/deploy.sh
  ignore_errors: yes  # ❌ 掩盖真正的错误
```

**正确做法：**
```yaml
- name: Deploy service
  command: /opt/deploy.sh
  register: deploy_result
  failed_when:
    - deploy_result.rc != 0
    - "'Already deployed' not in deploy_result.stderr"
```

---
