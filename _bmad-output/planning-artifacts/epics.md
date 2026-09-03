---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/architecture.md'
  - 'README.md'
validationStatus: 'complete'
validationDate: '2026-02-07'
---

# IaC - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for IaC, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

**配置管理（Configuration Management）- FR1-FR8:**

- FR1: DevOps Engineer 可以在 NetBox 中定义新虚拟机的配置（名称、CPU、内存、磁盘、网络）
- FR2: DevOps Engineer 可以在 NetBox 中为虚拟机分配 IP 地址并关联到接口
- FR3: DevOps Engineer 可以使用 NetBox Custom Fields 定义基础设施平台类型（Proxmox/ESXi/Physical）
- FR4: DevOps Engineer 可以使用 NetBox Custom Fields 定义 Ansible 角色和变量
- FR5: DevOps Engineer 可以在 NetBox 中标记虚拟机为"Planned"状态以触发自动化流程
- FR6: System 可以从 NetBox 通过 REST API 获取所有虚拟机配置数据
- FR7: DevOps Engineer 可以在 NetBox 中修改现有虚拟机的配置（内存、CPU 等）
- FR8: System 可以识别 NetBox 中配置变更并触发相应的自动化流程

**基础设施供给（Infrastructure Provisioning）- FR9-FR16:**

- FR9: System 可以通过 Terraform 从 NetBox 数据源拉取虚拟机配置
- FR10: System 可以使用 Terraform 在 Proxmox VE 上创建新虚拟机
- FR11: System 可以使用 Terraform 在 VMware ESXi 上创建新虚拟机
- FR12: System 可以通过 Terraform 管理虚拟机的生命周期（创建、修改、删除）
- FR13: System 可以在 Terraform 执行成功后生成 Ansible inventory host 资源
- FR14: System 可以将 Terraform 执行状态反馈回 NetBox（更新虚拟机状态）
- FR15: DevOps Engineer 可以通过 NetBox 配置变更触发 Terraform plan 操作
- FR16: DevOps Engineer 可以手动批准 Terraform apply 操作（Manual Gate）

**服务部署（Service Deployment）- FR17-FR23:**

- FR17: System 可以从 Terraform state 生成 Ansible dynamic inventory
- FR18: System 可以使用 Ansible 在新创建的虚拟机上部署应用服务
- FR19: System 可以使用 Ansible 对现有虚拟机进行配置变更
- FR20: System 可以从 NetBox Custom Fields 获取 Ansible 角色和变量配置
- FR21: System 可以在 Ansible 部署后执行健康检查验证（verify tagged tasks）
- FR22: System 可以将 Ansible 部署结果（成功/失败）反馈回 NetBox
- FR23: DevOps Engineer 可以通过 NetBox 配置 Ansible playbook 参数（tags, extra-vars）

**自动化编排（Automation Orchestration）- FR24-FR30:**

- FR24: System 可以通过 Jenkins Pipeline 编排 Terraform 和 Ansible 的执行顺序
- FR25: System 可以接收 NetBox Webhook 事件并触发 Jenkins Pipeline
- FR26: System 可以接收 Git 仓库 push 事件并触发 Jenkins Pipeline
- FR27: DevOps Engineer 可以在 Jenkins 界面查看 Pipeline 执行日志和状态
- FR28: DevOps Engineer 可以在 Jenkins Pipeline 中手动批准 Terraform apply 步骤
- FR29: System 可以在 Jenkins Pipeline 失败时发送通知（Slack/Email）
- FR30: DevOps Engineer 可以手动重新运行失败的 Jenkins Pipeline

**平台路由（Platform Routing）- FR31-FR35:**

- FR31: System 可以根据 NetBox Custom Field "Platform Type" 路由到正确的 Terraform 目录（proxmox/esxi）
- FR32: System 可以识别标记为 "Physical" 的服务器并跳过 Terraform 步骤
- FR33: System 可以为 Physical 服务器直接生成 Ansible inventory（无 Terraform 步骤）
- FR34: System 可以为不同平台类型使用不同的 Terraform module（proxmox-vm/esxi-vm）
- FR35: DevOps Engineer 可以在 NetBox 中查看虚拟机的路由决策结果（目标平台）

**错误处理与恢复（Error Handling & Recovery）- FR36-FR42:**

- FR36: System 可以在 Terraform 执行失败时将虚拟机标记为 "Failed" 状态
- FR37: System 可以在 Ansible 执行失败时将虚拟机标记为 "Degraded" 状态
- FR38: System 可以对失败的虚拟机自动重试 Terraform/Ansible 操作（最多 3 次）
- FR39: DevOps Engineer 可以在 NetBox 中手动重置虚拟机状态以触发重试
- FR40: System 可以记录错误日志并关联到 NetBox 虚拟机对象（Comments/Notes）
- FR41: System 可以在连续失败后发送告警通知并暂停自动重试
- FR42: DevOps Engineer 可以在 Jenkins 中查看详细的错误堆栈和失败原因

**可观测性与追踪（Observability & Tracking）- FR43-FR49:**

- FR43: DevOps Engineer 可以在 NetBox Change Log 中查看虚拟机配置的所有历史变更
- FR44: DevOps Engineer 可以在 Jenkins 中查看与特定虚拟机相关的所有 Pipeline 执行历史
- FR45: System 可以记录每次 Terraform apply 的变更内容（plan diff）
- FR46: System 可以记录每次 Ansible playbook 执行的变更内容（--diff 输出）
- FR47: DevOps Engineer 可以通过 NetBox 查看虚拟机的当前运行状态（Active/Planned/Failed）
- FR48: DevOps Engineer 可以追溯特定配置变更的触发来源（Webhook/Git commit）
- FR49: System 可以生成基础设施变更的审计日志（谁、何时、改了什么）

### Non-Functional Requirements

**性能（Performance）- NFR-P1 至 NFR-P9:**

- NFR-P1: NetBox Webhook 触发到 Jenkins Pipeline 启动的延迟 < 5 秒
- NFR-P2: Router Pipeline 路由决策时间（解析 Payload + 触发目标 Pipeline）< 10 秒
- NFR-P3: LXC 容器从 Webhook 触发到 SSH 可用的总时间 < 3 分钟
- NFR-P4: QEMU VM 从 Webhook 触发到 SSH 可用的总时间 < 5 分钟（包括 Cloud-Init）
- NFR-P5: Physical Server Inventory 更新时间 < 1 分钟（仅 Inventory 同步，无 Terraform）
- NFR-P6: Terraform 从 NetBox data source 查询单个资源的时间 < 30 秒
- NFR-P7: Terraform Plan 生成时间（NetBox 数据查询 + 动态配置生成）< 30 秒
- NFR-P8: 从 NetBox UI "Create" 点击到状态变为 "Provisioning" 的反馈时间 < 10 秒（用户能看到进度反馈）
- NFR-P9: 在 10x 资源增长（从 10 个资源到 100 个资源）时，Pipeline 执行时间增长 < 20%

**安全（Security）- NFR-S1 至 NFR-S10:**

- NFR-S1: 所有敏感凭据（Proxmox API Token、Ansible Vault 密码、NetBox API Token）必须通过 Ansible Vault 或 Jenkins Secrets 加密存储，严禁明文存储
- NFR-S2: `secrets.auto.tfvars` 必须在 `.gitignore` 中排除，严禁提交到 Git 仓库
- NFR-S3: API Tokens 必须定期轮换（建议周期：90 天）
- NFR-S4: NetBox Webhook 到 Jenkins 的通信必须通过 HTTPS（Cloudflare Tunnel）加密
- NFR-S5: Proxmox/ESXi API 调用必须使用 TLS 加密（拒绝 `tls_insecure = false`）
- NFR-S6: NetBox 必须使用 RBAC（Role-Based Access Control），限制 Webhook 触发和 API 访问权限
- NFR-S7: Jenkins Pipeline 的 Terraform apply 步骤必须强制人工审批（当 `automation_level == requires_approval` 时）
- NFR-S8: SSH 密钥访问必须使用非对称加密（Ed25519 或 RSA 4096 位），禁止密码认证
- NFR-S9: 所有 Terraform state 变更必须提交到 Git 仓库，保留审计记录（谁、何时、改了什么）
- NFR-S10: NetBox Change Log 必须记录所有配置变更历史（保留至少 90 天）

**可靠性（Reliability）- NFR-R1 至 NFR-R11:**

- NFR-R1: Webhook 触发成功率 > 95%（MVP 阶段目标 > 80%）
- NFR-R2: Terraform Apply 成功率 > 90%（无需人工修复）
- NFR-R3: Pipeline 失败时，必须在 NetBox 中自动更新虚拟机状态为 `failed_provisioning`
- NFR-R4: 重复触发相同 Webhook 不会创建重复资源（通过 Terraform state 检测已存在资源）
- NFR-R5: Pipeline 失败后可以安全重试，不会导致状态不一致（状态机支持 `failed_provisioning` → `provisioning` 转换）
- NFR-R6: 手动修改的资源不会被 Pipeline 覆盖（通过 `lifecycle { ignore_changes = [...] }` 保护关键字段）
- NFR-R7: Webhook 触发失败时，必须提供手动触发兜底机制（通过 Jenkins UI 传入 Resource ID）
- NFR-R8: API 调用超时设置必须合理（Terraform 默认 30 分钟，可通过 `timeouts` block 调整）
- NFR-R9: 失败的虚拟机可以自动重试最多 3 次，连续失败后暂停并发送告警
- NFR-R10: NetBox 配置与 Terraform state 必须最终一致（允许短暂延迟，但 Pipeline 完成后必须同步）
- NFR-R11: Ansible Inventory 必须在 Terraform Apply 成功后 30 秒内自动刷新

**可扩展性（Scalability）- NFR-SC1 至 NFR-SC8:**

- NFR-SC1: 系统必须支持至少 100 个资源（Proxmox VMID 范围 100-999，理论上限 900 个）
- NFR-SC2: 并发 Pipeline 执行数量至少支持 2-3 个（受 Jenkins executor 限制，可通过增加 executor 扩展）
- NFR-SC3: NetBox API 调用频率 < 100 req/min（避免触发 Rate Limiting）
- NFR-SC4: Proxmox API 调用必须支持超时重试机制（避免单次失败导致整个 Pipeline 失败）
- NFR-SC5: 架构必须支持新平台扩展（如 Oracle Cloud）时，仅需添加新 Pipeline，Router 逻辑无需修改
- NFR-SC6: NetBox Custom Fields 变更不会破坏现有 Terraform 代码（向后兼容性）
- NFR-SC7: 从 10 个资源增长到 50 个资源时，Terraform Plan 时间增长 < 50%
- NFR-SC8: NetBox data source 查询必须支持分页或过滤，避免全量查询导致性能下降

**集成（Integration）- NFR-I1 至 NFR-I10:**

- NFR-I1: NetBox API 集成必须支持 API Token 认证，避免使用用户名/密码
- NFR-I2: Terraform provider 版本必须锁定（`terraform-provider-netbox >= 3.0`），避免自动升级导致兼容性问题
- NFR-I3: Jenkins Generic Webhook Trigger 必须支持 Payload 验证（确保请求来自 NetBox）
- NFR-I4: NetBox Custom Fields 必须使用标准数据类型（Selection、Integer、Text、Object），避免自定义格式
- NFR-I5: Terraform 输出的 Ansible Inventory 必须符合 Ansible Dynamic Inventory 规范（JSON 格式）
- NFR-I6: 系统必须支持 NetBox 3.x 及以上版本（当前 Homelab 版本）
- NFR-I7: Terraform 版本锁定在 >= 1.14（与 HCP Terraform Cloud 兼容）
- NFR-I8: Ansible 版本锁定在 >= 2.16（支持 `cloud.terraform` collection）
- NFR-I9: 外部 API 调用失败时，Pipeline 必须记录详细错误日志（HTTP 状态码、响应 Body）
- NFR-I10: Git Push 失败不会导致整个 Pipeline 失败（允许手动补推）

**可维护性（Maintainability）- NFR-M1 至 NFR-M14:**

- NFR-M1: Terraform 代码必须按平台隔离目录（`terraform/proxmox/`, `terraform/esxi/`），避免单一目录爆炸半径
- NFR-M2: Ansible Roles 必须按服务划分（`roles/netbox/`, `roles/caddy/`），每个 Role 独立可测试
- NFR-M3: Jenkinsfiles 必须按功能命名（`Jenkinsfile-router`, `Jenkinsfile-proxmox-provisioning`），清晰表达用途
- NFR-M4: 所有架构决策必须记录在 ADR 文档中（已定义 8 个 ADR）
- NFR-M5: 每个服务部署必须有对应的实施文档（Deployment Specification）
- NFR-M6: README.md 必须提供 5-10 分钟的快速开始指南（Quick Start）
- NFR-M7: Terraform 代码必须通过 `terraform validate` 和 `terraform fmt -check` 验证
- NFR-M8: Ansible Playbooks 必须通过 `ansible-playbook --syntax-check` 和 `ansible-lint` 验证
- NFR-M9: Pipeline 必须支持手动触发测试（使用测试 Resource ID）
- NFR-M10: Jenkins 必须保留最近 10 个构建历史（用于故障排查）
- NFR-M11: NetBox 状态追踪必须清晰区分 `active` / `provisioning` / `failed_provisioning` 状态
- NFR-M12: Git commit 必须包含有意义的 commit message（遵循 Conventional Commits 规范）
- NFR-M13: 系统必须支持平滑迁移（从静态 `.tf` 到 NetBox Pull 模式），允许两种模式并存
- NFR-M14: 新增 Custom Fields 不会破坏现有 Pipeline（向后兼容）

### Additional Requirements

**架构决策要求（来自 Architecture.md）:**

- **ADR-001**: 渐进式迁移策略 - 从 Terraform Push 模式到 NetBox Pull 模式，允许两种模式并存
- **ADR-002**: terraform-provider-netbox data source 集成模式 - Week 1 POC 验证必需
- **ADR-003**: 内网直连 Webhook 触发机制 - NetBox (192.168.1.104) → Jenkins (192.168.1.107:8080) HTTP 直连
- **ADR-004**: Router Pipeline + Custom Field 驱动路由策略 - 根据 `infrastructure_platform` 字段路由
- **ADR-005**: 核心字段先行数据建模 - 6 个核心 Custom Fields 支持 MVP
- **ADR-006**: 状态标记 + 重试机制错误恢复 - NetBox 状态机 + Pipeline 幂等性保证
- **ADR-007**: 物理服务器跳过 Terraform，仅 Inventory + Ansible
- **ADR-008**: 独立目录 + 独立 Backend 的 Terraform 工作区隔离

**关键技术约束（来自 Architecture.md）:**

- Terraform >= 1.14
- Ansible >= 2.16
- Terraform Provider: `bpg/proxmox` 0.70.0, `e-breuninger/netbox` 3.10.0
- Python 3.12
- HCP Terraform Cloud 远程状态存储
- Ansible Vault 密钥管理

**MVP 阶段关键里程碑（来自 PRD）:**

- Week 1: NetBox 数据建模 + Router Pipeline
- Week 2-3: Proxmox Provisioning Pipeline
- Week 3-4: 迁移 3 个 LXC 服务（Anki, Caddy, n8n）
- Week 4: 物理服务器 Inventory 同步

**关键技术验证点:**

- Week 1 POC: terraform-provider-netbox 稳定性验证（最大风险点）
- 内网 Webhook 连通性测试
- Terraform 幂等性验证
- Ansible 健康检查模式验证

### FR Coverage Map

**配置管理（Configuration Management）:**
- FR1 → Epic 1 - NetBox 中定义虚拟机配置
- FR2 → Epic 1 - NetBox 中分配 IP 地址
- FR3 → Epic 1 - Custom Fields 定义平台类型
- FR4 → Epic 1 - Custom Fields 定义 Ansible 角色和变量
- FR5 → Epic 1 - 标记虚拟机为 "Planned" 状态触发流程
- FR6 → Epic 1 - 通过 REST API 获取配置数据
- FR7 → Epic 3 - 修改现有虚拟机配置
- FR8 → Epic 1 - 识别配置变更并触发自动化

**基础设施供给（Infrastructure Provisioning）:**
- FR9 → Epic 3 - Terraform 从 NetBox 拉取配置
- FR10 → Epic 3 - Terraform 在 Proxmox 创建虚拟机
- FR11 → Epic 9 - Terraform 在 ESXi 创建虚拟机（Post-MVP）
- FR12 → Epic 3 - Terraform 管理虚拟机生命周期
- FR13 → Epic 3 - 生成 Ansible inventory host 资源
- FR14 → Epic 3 - 状态反馈回 NetBox
- FR15 → Epic 3 - 配置变更触发 Terraform plan
- FR16 → Epic 3 - 人工批准 Terraform apply

**服务部署（Service Deployment）:**
- FR17 → Epic 4 - 从 Terraform state 生成 Ansible dynamic inventory
- FR18 → Epic 4 - Ansible 在新虚拟机上部署服务
- FR19 → Epic 4 - Ansible 对现有虚拟机配置变更
- FR20 → Epic 4 - 从 NetBox Custom Fields 获取 Ansible 配置
- FR21 → Epic 4 - Ansible 部署后健康检查验证
- FR22 → Epic 4 - Ansible 部署结果反馈到 NetBox
- FR23 → Epic 4 - 通过 NetBox 配置 Ansible playbook 参数

**自动化编排（Automation Orchestration）:**
- FR24 → Epic 5 - Jenkins Pipeline 编排 Terraform 和 Ansible
- FR25 → Epic 1 - 接收 NetBox Webhook 事件触发 Pipeline
- FR26 → Epic 5 - 接收 Git push 事件触发 Pipeline
- FR27 → Epic 5 - Jenkins 界面查看执行日志和状态
- FR28 → Epic 5 - Jenkins Pipeline 人工批准步骤
- FR29 → Epic 5 - Pipeline 失败时发送通知
- FR30 → Epic 5 - 手动重新运行失败的 Pipeline

**平台路由（Platform Routing）:**
- FR31 → Epic 2 - 根据 Platform Type 路由到正确目录
- FR32 → Epic 2 - 识别 Physical 服务器跳过 Terraform
- FR33 → Epic 2 - Physical 服务器直接生成 Ansible inventory
- FR34 → Epic 2 - 不同平台使用不同 Terraform module
- FR35 → Epic 2 - NetBox 中查看路由决策结果

**错误处理与恢复（Error Handling & Recovery）:**
- FR36 → Epic 6 - Terraform 失败时标记 "Failed" 状态
- FR37 → Epic 6 - Ansible 失败时标记 "Degraded" 状态
- FR38 → Epic 6 - 失败虚拟机自动重试（最多 3 次）
- FR39 → Epic 6 - NetBox 中手动重置状态触发重试
- FR40 → Epic 6 - 错误日志关联到 NetBox 虚拟机对象
- FR41 → Epic 6 - 连续失败后告警并暂停重试
- FR42 → Epic 6 - Jenkins 查看详细错误堆栈

**可观测性与追踪（Observability & Tracking）:**
- FR43 → Epic 7 - NetBox Change Log 查看配置历史
- FR44 → Epic 7 - Jenkins 查看虚拟机相关 Pipeline 历史
- FR45 → Epic 7 - 记录 Terraform apply 变更内容
- FR46 → Epic 7 - 记录 Ansible playbook 执行变更内容
- FR47 → Epic 7 - NetBox 查看虚拟机当前运行状态
- FR48 → Epic 7 - 追溯配置变更触发来源
- FR49 → Epic 7 - 生成基础设施变更审计日志

**物理服务器管理（Physical Server Management）:**
- Epic 8 主要支持 FR32, FR33，以及物理服务器的 FR18, FR19, FR20, FR21

**覆盖统计：**
- 所有 49 个功能性需求已完整映射到 9 个史诗
- MVP 阶段覆盖 Epic 1-8（47 个 FRs）
- Post-MVP 阶段覆盖 Epic 9（2 个 FRs）

## Epic List

### Epic 1: NetBox 数据建模与 Webhook 基础设施
DevOps Engineer 可以在 NetBox 中定义完整的虚拟机配置（包括平台类型、自动化级别、Ansible 配置），并且系统能够通过 Webhook 感知这些变更。

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR8, FR25

### Epic 2: 智能路由与平台隔离
系统可以根据 NetBox 中定义的平台类型（Proxmox/ESXi/Physical）自动路由到正确的处理流程，确保不同平台完全隔离且可并行处理。

**FRs covered:** FR31, FR32, FR33, FR34, FR35

### Epic 3: Proxmox 资源自动化供给
DevOps Engineer 可以通过 NetBox 创建 Proxmox 虚拟机/容器，系统自动使用 Terraform 从 NetBox 拉取配置并在 Proxmox 上创建资源，支持人工审批和状态反馈。

**FRs covered:** FR9, FR10, FR12, FR13, FR14, FR15, FR16, FR7

### Epic 4: Ansible 服务部署与配置管理
系统可以在 Terraform 创建的资源上自动运行 Ansible playbook 进行服务部署和配置，支持从 NetBox 获取 Ansible 配置参数，并执行健康检查验证。

**FRs covered:** FR17, FR18, FR19, FR20, FR21, FR22, FR23

### Epic 5: Pipeline 编排与自动化工作流
DevOps Engineer 可以通过统一的 Jenkins Pipeline 编排整个端到端流程（Webhook → Router → Terraform → Ansible），查看实时执行日志和状态，并在关键节点进行人工审批。

**FRs covered:** FR24, FR26, FR27, FR28, FR29, FR30

### Epic 6: 错误处理与恢复机制
当 Pipeline 执行失败时，系统能够自动标记资源状态、记录详细错误日志、支持安全重试，并在连续失败时发送告警，确保运维人员可以快速定位和修复问题。

**FRs covered:** FR36, FR37, FR38, FR39, FR40, FR41, FR42

### Epic 7: 可观测性与审计追踪
DevOps Engineer 可以完整追踪每个资源的配置历史、Pipeline 执行记录、变更审计日志，了解当前运行状态，并追溯变更的触发来源和责任人。

**FRs covered:** FR43, FR44, FR45, FR46, FR47, FR48, FR49

### Epic 8: 物理服务器配置管理
DevOps Engineer 可以在 NetBox 中管理物理服务器，系统自动生成 Ansible Inventory 并执行配置管理，跳过 Terraform provisioning 步骤，实现物理和虚拟资源的统一管理。

**FRs covered:** FR32, FR33（以及物理服务器的 FR18, FR19, FR20, FR21）

### Epic 9: ESXi 平台支持（Post-MVP）
DevOps Engineer 可以在 NetBox 中创建 ESXi 虚拟机，系统自动使用 Terraform 在 VMware ESXi 上创建资源，复用 Proxmox 的架构模式，验证多平台支持能力。

**FRs covered:** FR11（以及 ESXi 版本的 FR9, FR12, FR13, FR14, FR15, FR16）

---

## Epic 1: NetBox 数据建模与 Webhook 基础设施

DevOps Engineer 可以在 NetBox 中定义完整的虚拟机配置（包括平台类型、自动化级别、Ansible 配置），并且系统能够通过 Webhook 感知这些变更。

### Story 1.1: 定义核心 Custom Fields

As a DevOps Engineer,
I want to define 6 个核心 Custom Fields 在 NetBox 中,
So that 我可以为虚拟机配置平台类型、自动化级别和 Ansible 参数。

**Acceptance Criteria:**

**Given** 我已登录 NetBox Admin UI
**When** 我导航到 Customization > Custom Fields > Add
**Then** 我可以成功创建以下 Custom Fields：
- `infrastructure_platform` (Selection): choices = [proxmox, esxi, physical], required = true
- `automation_level` (Selection): choices = [fully_automated, requires_approval, manual_only], required = true
- `proxmox_node` (Selection): choices = [pve0, pve1, pve2], required = conditional
- `proxmox_vmid` (Integer): min = 100, max = 999, required = conditional
- `ansible_groups` (Multiple Selection): choices = [pve_vms, pve_lxc, docker, tailscale], required = false
- `playbook_name` (Text): max_length = 100, required = false

**And** 所有 Custom Fields 应用到 virtualization.virtualmachine 和 dcim.device content types
**And** Custom Fields 在虚拟机创建/编辑表单中可见
**And** 验证必填字段约束正常工作（创建虚拟机时缺少 infrastructure_platform 会报错）

### Story 1.2: 配置 NetBox Webhook 到 Jenkins

As a DevOps Engineer,
I want to 配置 NetBox Webhook 自动触发 Jenkins Pipeline,
So that 当我在 NetBox 中创建或修改虚拟机时，系统能自动感知并启动自动化流程。

**Acceptance Criteria:**

**Given** Jenkins Generic Webhook Trigger Plugin 已安装
**When** 我在 NetBox 中导航到 System > Webhooks > Add
**Then** 我可以成功创建 Webhook + Event Rule 配置（NetBox 4.x 架构）：

**Webhook 配置（定义目标端点）：**
- Name: "Jenkins Infrastructure Automation"
- URL: `http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook`
- HTTP Method: POST
- Body Template: `{{ data }}`

**Event Rule 配置（定义触发条件）：**
- Name: "Trigger Jenkins on VM/Device Changes"
- Content types: virtualization.virtualmachine, dcim.device
- Events: created, updated
- Action Type: webhook
- Action Object: → Jenkins Infrastructure Automation

**And** 内网连通性测试成功：
```bash
curl -X POST http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "connectivity"}'
```
返回 HTTP 200 或接受的响应

**And** Webhook 触发延迟 < 5 秒（NFR-P1）
**And** 我可以在 NetBox > System > Webhooks 中查看 Webhook 执行历史
**And** 失败的 Webhook 请求显示错误信息和重试机制

### Story 1.3: 在 NetBox 中创建虚拟机配置

As a DevOps Engineer,
I want to 在 NetBox UI 中创建虚拟机记录并配置所有必要参数,
So that 我可以声明式定义基础设施配置而无需手动编写 Terraform 代码。

**Acceptance Criteria:**

**Given** Custom Fields 已正确配置（Story 1.1 完成）
**When** 我在 NetBox 中导航到 Virtual Machines > Add
**Then** 我可以成功创建虚拟机记录并填写：
- Name: 虚拟机名称（例如 "test-lxc-01"）
- Status: "Planned"（触发自动化流程）
- Cluster: Proxmox VE Cluster
- Memory (MB): 512
- vCPUs: 1
- Custom Fields:
  - infrastructure_platform: "proxmox"
  - automation_level: "requires_approval"
  - proxmox_node: "pve0"
  - proxmox_vmid: 201
  - ansible_groups: ["pve_lxc", "tailscale"]
  - playbook_name: "deploy-test.yml"

**And** 我可以为虚拟机添加 Primary IP 地址：
- 创建 IP Address: 192.168.1.201/24
- 关联到虚拟机的接口
- 设置为 Primary IPv4

**And** 保存虚拟机记录后，状态显示为 "Planned"
**And** Webhook 自动触发（通过 Jenkins 日志验证）
**And** NetBox Change Log 记录虚拟机创建事件（包括用户、时间戳）

### Story 1.4: NetBox API 集成验证

As a System,
I want to 通过 NetBox REST API 查询虚拟机配置数据,
So that Terraform 和 Jenkins Pipeline 可以动态获取配置信息。

**Acceptance Criteria:**

**Given** NetBox API Token 已创建并配置在 Jenkins Secrets 中
**When** 我执行 API 查询请求：
```bash
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  http://192.168.1.104:8080/api/dcim/virtual-machines/?status=planned
```
**Then** 我可以成功获取所有状态为 "planned" 的虚拟机列表
**And** 响应 JSON 包含所有必要字段：
- id, name, status, memory, vcpus
- cluster.name
- primary_ip4.address
- custom_fields.infrastructure_platform
- custom_fields.automation_level
- custom_fields.proxmox_node
- custom_fields.proxmox_vmid
- custom_fields.ansible_groups
- custom_fields.playbook_name

**And** 我可以通过 Custom Fields 过滤查询：
```bash
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/dcim/virtual-machines/?cf_infrastructure_platform=proxmox"
```
返回仅 Proxmox 平台的虚拟机

**And** API 查询响应时间 < 2 秒（NFR-P6 要求 < 30 秒）
**And** API Token 认证失败时返回 HTTP 403 错误（NFR-I1）
**And** API 查询日志记录在 NetBox audit log 中

---

## Epic 2: 智能路由与平台隔离

系统可以根据 NetBox 中定义的平台类型（Proxmox/ESXi/Physical）自动路由到正确的处理流程，确保不同平台完全隔离且可并行处理。

### Story 2.1: 创建 Jenkins Router Pipeline

As a DevOps Engineer,
I want to 创建 Webhook Router Pipeline 解析 NetBox Payload 并路由到平台特定 Pipeline,
So that 系统可以根据虚拟机的平台类型自动选择正确的处理流程。

**Acceptance Criteria:**

**Given** Jenkins Generic Webhook Trigger Plugin 已配置
**When** 我创建 `Jenkinsfile-webhook-router` 文件：

> **注意**: 不使用 `readJSON` 插件。Generic Webhook Trigger 通过 `genericVariables` 直接将 JSONPath 提取到环境变量。

```groovy
pipeline {
    agent any
    triggers {
        GenericTrigger(
            genericVariables: [
                [key: 'netbox_event', value: '$.event'],
                [key: 'netbox_model', value: '$.model'],
                [key: 'netbox_object_id', value: '$.data.id'],
                [key: 'netbox_object_name', value: '$.data.name'],
                [key: 'infrastructure_platform', value: '$.data.custom_fields.infrastructure_platform'],
                [key: 'automation_level', value: '$.data.custom_fields.automation_level']
            ],
            token: 'netbox-webhook',
            regexpFilterExpression: '^(created|updated) (virtualmachine|device)$',
            regexpFilterText: '$netbox_event $netbox_model'
        )
    }
    stages {
        stage('Validate Payload') {
            steps {
                script {
                    // Variables already extracted by GenericTrigger — no readJSON needed
                    env.PLATFORM = env.infrastructure_platform
                    env.AUTOMATION_LEVEL = env.automation_level
                    if (!env.PLATFORM) {
                        error "Missing infrastructure_platform custom field"
                    }
                }
            }
        }
        stage('Route to Platform Pipeline') {
            steps {
                script {
                    switch(env.PLATFORM) {
                        case 'proxmox':
                            build job: 'Proxmox-Provisioning', parameters: [...]
                            break
                        case 'esxi':
                            build job: 'ESXi-Provisioning', parameters: [...]
                            break
                        case 'physical':
                            build job: 'Physical-Device-Sync', parameters: [...]
                            break
                        default:
                            error "Unknown platform: ${env.PLATFORM}"
                    }
                }
            }
        }
    }
}
```
**Then** Pipeline 成功解析 NetBox Webhook Payload
**And** 根据 `infrastructure_platform` 字段路由到正确的 Jenkins Job
**And** 路由决策时间 < 10 秒（NFR-P2）
**And** 未知平台类型时 Pipeline 失败并显示明确错误信息
**And** Router Pipeline 日志记录路由决策（平台类型、目标 Pipeline）

### Story 2.2: 实现平台类型验证和错误处理

As a System,
I want to 验证 NetBox Payload 中的 infrastructure_platform 字段有效性,
So that 只有支持的平台类型才能触发后续处理流程。

**Acceptance Criteria:**

**Given** Router Pipeline 接收到 Webhook Payload
**When** Payload 中 `custom_fields.infrastructure_platform` 字段缺失
**Then** Pipeline 失败并显示错误：
```
ERROR: Missing infrastructure_platform custom field in NetBox payload
```

**And** 当 `infrastructure_platform` 值不在 [proxmox, esxi, physical] 范围内
**Then** Pipeline 失败并显示错误：
```
ERROR: Unknown platform: <value>. Expected: proxmox, esxi, or physical
```

**And** 错误信息记录在 Jenkins Console Output 中
**And** NetBox 中虚拟机状态保持为 "Planned"（不更新为 failed）
**And** 可选：发送通知到 Slack/Email（如果配置）

### Story 2.3: Proxmox 平台路由逻辑验证

As a DevOps Engineer,
I want to 验证 Proxmox 平台虚拟机正确路由到 Proxmox Provisioning Pipeline,
So that Proxmox 资源的创建流程被正确触发。

**Acceptance Criteria:**

**Given** NetBox 中创建了一个虚拟机，`infrastructure_platform = proxmox`
**When** Webhook 触发 Router Pipeline
**Then** Router Pipeline 成功解析 Payload 并识别平台为 "proxmox"
**And** Router Pipeline 触发 "Proxmox-Provisioning" Jenkins Job
**And** 传递以下参数到目标 Pipeline：
- NETBOX_VM_ID: <虚拟机 ID>
- NETBOX_VM_NAME: <虚拟机名称>
- PLATFORM: "proxmox"
- AUTOMATION_LEVEL: <automation_level 值>

**And** Proxmox-Provisioning Job 成功启动（即使后续步骤失败）
**And** Router Pipeline 显示 "SUCCESS" 状态
**And** Jenkins Blue Ocean 界面显示清晰的 Pipeline 调用链

### Story 2.4: Physical 服务器路由逻辑验证

As a DevOps Engineer,
I want to 验证 Physical 服务器正确路由到 Physical Device Sync Pipeline 并跳过 Terraform,
So that 物理服务器仅执行 Inventory 同步和 Ansible 配置管理。

**Acceptance Criteria:**

**Given** NetBox 中创建了一个 Device，`infrastructure_platform = physical`
**When** Webhook 触发 Router Pipeline
**Then** Router Pipeline 成功解析 Payload 并识别平台为 "physical"
**And** Router Pipeline 触发 "Physical-Device-Sync" Jenkins Job（不是 Terraform Pipeline）
**And** 传递以下参数到目标 Pipeline：
- NETBOX_DEVICE_ID: <设备 ID>
- NETBOX_DEVICE_NAME: <设备名称>
- PLATFORM: "physical"

**And** Physical-Device-Sync Pipeline 跳过 Terraform init/plan/apply 阶段
**And** Physical-Device-Sync Pipeline 直接执行 Ansible Inventory 生成和配置管理
**And** Router Pipeline 日志明确显示 "Platform: physical - Skipping Terraform"

### Story 2.5: 平台隔离和并行处理验证

As a System,
I want to 确保不同平台的 Pipeline 完全隔离且可并行执行,
So that Proxmox 和 ESXi 资源可以同时创建而不互相干扰。

**Acceptance Criteria:**

**Given** 两个虚拟机同时创建：
- VM1: infrastructure_platform = "proxmox"
- VM2: infrastructure_platform = "esxi"
**When** 两个 Webhook 几乎同时触发（间隔 < 1 秒）
**Then** 两个 Router Pipeline 实例并发运行
**And** VM1 路由到 Proxmox-Provisioning Pipeline（在 `terraform/proxmox/` 目录）
**And** VM2 路由到 ESXi-Provisioning Pipeline（在 `terraform/esxi/` 目录）
**And** 两个 Pipeline 使用独立的 Terraform workspace：
- Proxmox: `iac-proxmox`
- ESXi: `iac-esxi`

**And** 两个 Pipeline 使用独立的 Terraform state 文件（HCP Terraform Cloud）
**And** Proxmox Pipeline 失败不影响 ESXi Pipeline 执行
**And** 并发执行数量受 Jenkins executor 限制（最多 2-3 个，NFR-SC2）
**And** Jenkins 日志清晰显示两个独立的执行流程

---

## Epic 3: Proxmox 资源自动化供给

DevOps Engineer 可以通过 NetBox 创建 Proxmox 虚拟机/容器，系统自动使用 Terraform 从 NetBox 拉取配置并在 Proxmox 上创建资源，支持人工审批和状态反馈。

### Story 3.1: terraform-provider-netbox POC 验证

As a DevOps Engineer,
I want to 验证 terraform-provider-netbox 的 data source 功能,
So that 确认可以从 NetBox API 动态查询虚拟机配置数据（这是最大技术风险点）。

**Acceptance Criteria:**

**Given** NetBox 中有至少 1 个状态为 "planned"、平台为 "proxmox" 的虚拟机
**When** 我创建 `terraform/proxmox/netbox-data.tf` 文件：
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

output "netbox_vms_count" {
  value = length(data.netbox_virtual_machines.proxmox_vms.virtual_machines)
}

output "netbox_vms_details" {
  value = [
    for vm in data.netbox_virtual_machines.proxmox_vms.virtual_machines : {
      name    = vm.name
      vmid    = vm.custom_fields.proxmox_vmid
      node    = vm.custom_fields.proxmox_node
      memory  = vm.memory
      vcpus   = vm.vcpus
    }
  ]
}
```
**Then** `terraform init` 成功安装 `e-breuninger/netbox` provider
**And** `terraform plan` 成功查询 NetBox API 并输出虚拟机列表
**And** `terraform output netbox_vms_details` 显示正确的虚拟机配置数据
**And** Data source 查询时间 < 30 秒（NFR-P6）
**And** API 调用失败时 Terraform 显示清晰的错误信息（连接超时、认证失败等）

**If POC fails:** 切换到 Plan B（Python 脚本生成静态 `.tf` 文件）

### Story 3.2: 动态资源生成配置

As a DevOps Engineer,
I want to 使用 Terraform for_each 循环根据 NetBox 数据动态生成 Proxmox 资源,
So that 无需为每个虚拟机手动编写 Terraform 配置文件。

**Acceptance Criteria:**

**Given** terraform-provider-netbox POC 验证成功（Story 3.1）
**When** 我创建 `terraform/proxmox/generated.tf` 文件：
```hcl
locals {
  netbox_vms_map = {
    for vm in data.netbox_virtual_machines.proxmox_vms.virtual_machines :
    vm.name => vm
  }
}

resource "proxmox_virtual_environment_vm" "from_netbox" {
  for_each = local.netbox_vms_map
  
  name        = each.value.name
  node_name   = each.value.custom_fields.proxmox_node
  vm_id       = each.value.custom_fields.proxmox_vmid
  
  memory {
    dedicated = each.value.memory
  }
  
  cpu {
    cores = each.value.vcpus
  }
  
  # Clone from template
  clone {
    vm_id = 9000  # Debian 12 template
  }
  
  # Network configuration
  network_device {
    bridge = "vmbr0"
  }
  
  # Cloud-init IP configuration
  initialization {
    ip_config {
      ipv4 {
        address = each.value.primary_ip4.address
        gateway = "192.168.1.1"
      }
    }
  }
  
  lifecycle {
    ignore_changes = [
      clone,
      initialization,
      description,
    ]
  }
}

resource "ansible_host" "from_netbox" {
  for_each = proxmox_virtual_environment_vm.from_netbox
  
  name   = each.value.name
  groups = each.value.custom_fields.ansible_groups
  variables = {
    ansible_host = each.value.primary_ip4.address
  }
  depends_on = [proxmox_virtual_environment_vm.from_netbox]
}
```
**Then** `terraform plan` 显示将创建的资源数量与 NetBox 中 "planned" 虚拟机数量一致
**And** Plan 输出显示每个虚拟机的配置参数（name, node, vmid, memory, vcpus）
**And** `for_each` 使用虚拟机名称作为 key，确保唯一性
**And** `lifecycle.ignore_changes` 保护关键字段不被覆盖（NFR-R6）
**And** Plan 生成时间 < 30 秒（NFR-P7）

### Story 3.3: Proxmox Provisioning Pipeline 实现

As a DevOps Engineer,
I want to 创建完整的 Proxmox Provisioning Pipeline 执行 Terraform 工作流,
So that 从 Webhook 触发到虚拟机创建的端到端流程自动化运行。

**Acceptance Criteria:**

**Given** Router Pipeline 已正确配置（Epic 2 完成）
**When** 我创建 `Jenkinsfile-proxmox-provisioning` 文件包含以下阶段：
1. **Checkout**: 拉取 Git 仓库代码
2. **Setup**: 配置 Ansible Vault 密码和 Terraform credentials
3. **Pull NetBox Data**: 运行 `scripts/netbox-to-terraform.py` 获取最新数据
4. **Terraform Init**: 在 `terraform/proxmox/` 目录初始化 Terraform
5. **Terraform Plan**: 生成执行计划并保存为 artifact
6. **Approval Gate**: 如果 `automation_level == requires_approval`，等待人工批准
7. **Terraform Apply**: 执行资源创建
8. **Refresh Ansible Inventory**: 运行 `scripts/refresh-terraform-state.sh`
9. **Update NetBox Status**: 更新虚拟机状态为 "provisioning" → "active"

**Then** Pipeline 成功执行所有阶段
**And** Terraform Plan 输出在 Jenkins Console Log 中可见
**And** Approval Gate 暂停 Pipeline 并显示 "Approve" 按钮（当 automation_level == requires_approval）
**And** Approval Gate 自动通过（当 automation_level == fully_automated）
**And** Terraform Apply 成功创建 Proxmox 虚拟机
**And** Pipeline 执行总时间 < 5 分钟（NFR-P4 要求 LXC < 3 分钟）

### Story 3.4: 人工审批 Gate 实现

As a DevOps Engineer,
I want to 在 Terraform Apply 前人工审批执行计划,
So that 我可以验证变更内容避免意外的资源修改或删除。

**Acceptance Criteria:**

**Given** Proxmox Provisioning Pipeline 运行到 "Approval Gate" 阶段
**When** 虚拟机的 `automation_level = requires_approval`
**Then** Pipeline 暂停并显示审批界面：
```
Terraform Plan Summary:
  + 1 to add
  ~ 0 to change
  - 0 to destroy

Resources to create:
  + proxmox_virtual_environment_vm.from_netbox["test-lxc-01"]

Approve to proceed with Terraform Apply?
```

**And** Jenkins 界面显示 "Approve" 和 "Reject" 按钮
**And** 审批等待超时时间为 30 分钟
**And** 点击 "Approve" 后 Pipeline 继续执行 Terraform Apply
**And** 点击 "Reject" 后 Pipeline 终止并标记为 "ABORTED"
**And** 审批决策记录在 Jenkins 日志中（审批人、时间、决策）

**When** 虚拟机的 `automation_level = fully_automated`
**Then** Pipeline 自动跳过 Approval Gate（显示 "Skipped - Fully Automated"）
**And** Terraform Apply 立即执行

**When** 虚拟机的 `automation_level = manual_only`
**Then** Pipeline 在 Terraform Plan 后自动终止（不执行 Apply）
**And** Pipeline 状态显示 "SUCCESS - Manual Intervention Required"

### Story 3.5: NetBox 状态回写机制

As a System,
I want to 将 Terraform 执行结果反馈回 NetBox 更新虚拟机状态,
So that DevOps Engineer 可以在 NetBox UI 中实时查看资源创建进度。

**Acceptance Criteria:**

**Given** Proxmox Provisioning Pipeline 成功完成 Terraform Apply
**When** Pipeline 执行 "Update NetBox Status" 阶段
**Then** 系统通过 NetBox API 更新虚拟机状态：
```bash
curl -X PATCH "http://192.168.1.104:8080/api/dcim/virtual-machines/${NETBOX_VM_ID}/" \
  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "active",
    "comments": "Provisioned by Jenkins build #'"${BUILD_NUMBER}"' at '"$(date -Iseconds)"'"
  }'
```

**And** NetBox 中虚拟机状态从 "planned" → "active"
**And** NetBox Comments 字段记录 Jenkins build URL 和时间戳
**And** NetBox Change Log 记录状态变更事件

**When** Terraform Apply 失败
**Then** 虚拟机状态更新为 "failed"（对应 NetBox status 值）
**And** Comments 字段记录错误信息和 Jenkins build URL
**And** 状态更新 API 调用失败不会导致整个 Pipeline 失败（记录警告日志）

**And** 状态更新在 Terraform Apply 完成后 30 秒内完成（NFR-R10）

### Story 3.6: 配置变更触发 Terraform Plan

As a DevOps Engineer,
I want to 在 NetBox 中修改虚拟机配置时自动触发 Terraform Plan,
So that 我可以预览变更影响并安全地更新已有资源。

**Acceptance Criteria:**

**Given** Proxmox 虚拟机已创建且状态为 "active"
**When** 我在 NetBox 中修改虚拟机配置：
- Memory: 512 MB → 1024 MB
- 保存变更

**Then** NetBox Webhook 触发（event = "updated"）
**And** Router Pipeline 识别为配置更新（而非新建）
**And** Proxmox Provisioning Pipeline 运行到 Terraform Plan 阶段
**And** Plan 输出显示：
```
~ proxmox_virtual_environment_vm.from_netbox["test-lxc-01"]
    ~ memory.dedicated: 512 → 1024

Plan: 0 to add, 1 to change, 0 to destroy
```

**And** Plan 输出包含变更类型提示：
```
⚠️ WARNING: This will modify an existing resource.
Modification Type: In-place update (no recreation)
Estimated Downtime: None (memory can be hot-added)
```

**And** Approval Gate 显示（如果 automation_level == requires_approval）
**And** 审批通过后 Terraform Apply 执行内存更新
**And** Proxmox 虚拟机内存成功更新，无需重启（热插拔）
**And** NetBox 状态保持 "active"，Comments 追加更新记录

---

## Epic 4: Ansible 服务部署与配置管理

系统可以在 Terraform 创建的资源上自动运行 Ansible playbook 进行服务部署和配置，支持从 NetBox 获取 Ansible 配置参数，并执行健康检查验证。

### Story 4.1: Terraform State 到 Ansible Dynamic Inventory 自动生成

As a System,
I want to 从 Terraform state 自动生成 Ansible dynamic inventory,
So that 新创建的虚拟机立即出现在 Ansible inventory 中供部署使用。

**Acceptance Criteria:**

**Given** Terraform Apply 成功创建虚拟机（Epic 3 完成）
**When** Terraform 执行过程包含 `ansible_host` 资源：
```hcl
resource "ansible_host" "from_netbox" {
  for_each = proxmox_virtual_environment_vm.from_netbox
  
  name   = each.value.name
  groups = jsondecode(each.value.custom_fields.ansible_groups)
  variables = {
    ansible_host = trimspace(split("/", each.value.primary_ip4.address)[0])
  }
  depends_on = [proxmox_virtual_environment_vm.from_netbox]
}
```
**Then** Terraform state 包含 ansible_host 资源
**And** 运行 `scripts/refresh-terraform-state.sh` 后，Ansible inventory 自动刷新
**And** 执行 `ansible-inventory --list` 显示新虚拟机：
```json
{
  "pve_lxc": {
    "hosts": ["test-lxc-01"]
  },
  "tailscale": {
    "hosts": ["test-lxc-01"]
  },
  "_meta": {
    "hostvars": {
      "test-lxc-01": {
        "ansible_host": "192.168.1.201"
      }
    }
  }
}
```

**And** Inventory 刷新时间 < 30 秒（NFR-R11）
**And** Ansible ping 测试成功：`ansible test-lxc-01 -m ping`
**And** Inventory 包含从 NetBox Custom Fields 获取的 ansible_groups

### Story 4.2: 基于 NetBox Custom Fields 的 Playbook 自动选择

As a System,
I want to 根据 NetBox 的 playbook_name Custom Field 自动选择要执行的 Ansible playbook,
So that 不同类型的虚拟机可以自动运行对应的部署脚本。

**Acceptance Criteria:**

**Given** Proxmox Provisioning Pipeline 完成 Terraform Apply 和 Inventory 刷新
**When** Pipeline 执行 "Ansible Deploy" 阶段
**Then** 系统从 NetBox Custom Fields 读取 `playbook_name` 值
**And** 如果 `playbook_name` 有值（例如 "deploy-caddy.yml"）：
- Pipeline 执行 `ansible-playbook playbooks/deploy-caddy.yml`

**And** 如果 `playbook_name` 为空，系统根据 `ansible_groups` 自动推导：
- 如果 groups 包含 "caddy" → 执行 `playbooks/deploy-caddy.yml`
- 如果 groups 包含 "netbox" → 执行 `playbooks/deploy-netbox.yml`
- 如果没有匹配的服务 group → 执行 `playbooks/deploy-common.yml`（通用配置）

**And** Playbook 选择逻辑在 Pipeline 日志中明确显示：
```
Playbook Selection:
  Custom Field: deploy-caddy.yml
  Auto-detected: N/A
  Selected: playbooks/deploy-caddy.yml
```

**And** Playbook 文件不存在时 Pipeline 失败并显示清晰错误
**And** 支持传递额外变量：`--extra-vars "service_version=latest"`

### Story 4.3: Ansible Playbook 执行与日志输出

As a DevOps Engineer,
I want to 在 Jenkins Pipeline 中执行 Ansible playbook 并查看实时输出,
So that 我可以监控服务部署进度并快速定位问题。

**Acceptance Criteria:**

**Given** Ansible playbook 已选择（Story 4.2）
**When** Pipeline 执行 Ansible playbook：
```groovy
dir('ansible') {
    sh """
        ansible-playbook playbooks/deploy-caddy.yml \
          --limit test-lxc-01 \
          --diff \
          --check
    """
}
```
**Then** Jenkins Console Output 显示完整的 Ansible 输出：
- PLAY RECAP 汇总（ok, changed, failed, skipped）
- 每个 task 的执行状态和耗时
- `--diff` 模式下的配置文件变更内容

**And** Ansible 输出使用 `stdout_callback = debug` 格式（清晰可读，无 JSON 混杂）
**And** Playbook 执行失败时 Pipeline 状态为 "FAILED"
**And** Playbook 执行成功时 Pipeline 继续到验证阶段
**And** Ansible 执行日志保留在 Jenkins build artifacts 中

**When** Playbook 包含 `--check` 模式（dry-run）
**Then** 不会对目标系统做实际变更
**And** Console Output 显示 "DRY RUN - No changes applied"

### Story 4.4: 内置健康检查验证（Verify Tagged Tasks）

As a System,
I want to 在 Ansible 部署完成后自动执行健康检查验证,
So that 确保服务正确部署并可正常访问。

**Acceptance Criteria:**

**Given** Ansible playbook 部署阶段完成
**When** Pipeline 执行验证阶段：
```groovy
dir('ansible') {
    sh """
        ansible-playbook playbooks/deploy-caddy.yml \
          --limit test-lxc-01 \
          --tags verify
    """
}
```
**Then** Playbook 仅执行带 `tags: [verify]` 的 play 和 tasks
**And** 验证 play 包含以下检查（以 Caddy 为例）：
```yaml
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

**And** 所有验证 tasks 成功执行
**And** 端口监听验证在 30 秒内成功（NFR-P8）
**And** systemd 服务状态为 "active"
**And** HTTP 健康检查返回预期状态码（200/301/302）
**And** 验证失败时 Pipeline 状态为 "FAILED"
**And** 验证成功时 Pipeline Console Output 显示 "✅ Deployment verified successfully"

### Story 4.5: Ansible 部署结果反馈到 NetBox

As a System,
I want to 将 Ansible 部署结果（成功/失败）反馈回 NetBox,
So that DevOps Engineer 可以在 NetBox 中查看服务部署状态。

**Acceptance Criteria:**

**Given** Ansible playbook 执行完成（成功或失败）
**When** Pipeline 执行 "Update NetBox Deployment Status" 阶段
**Then** 如果 Ansible 执行成功且验证通过：
```bash
curl -X PATCH "http://192.168.1.104:8080/api/dcim/virtual-machines/${NETBOX_VM_ID}/" \
  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  -d '{
    "custom_fields": {
      "deployment_status": "deployed",
      "last_deployed_at": "'"$(date -Iseconds)"'"
    },
    "comments": "Service deployed successfully by Jenkins build #'"${BUILD_NUMBER}"'"
  }'
```

**And** 如果 Ansible 执行失败或验证失败：
```bash
curl -X PATCH "http://192.168.1.104:8080/api/dcim/virtual-machines/${NETBOX_VM_ID}/" \
  -d '{
    "status": "failed",
    "custom_fields": {
      "deployment_status": "failed"
    },
    "comments": "Ansible deployment failed. See Jenkins build #'"${BUILD_NUMBER}"' for details."
  }'
```

**And** NetBox 中虚拟机显示部署状态字段（需要先创建 `deployment_status` Custom Field）
**And** Comments 包含 Jenkins build URL 链接
**And** 状态更新在 Ansible 完成后 10 秒内执行

### Story 4.6: 配置变更的幂等性验证

As a DevOps Engineer,
I want to 多次运行 Ansible playbook 不会导致重复变更,
So that Pipeline 可以安全地重试而不破坏已部署的服务。

**Acceptance Criteria:**

**Given** Ansible playbook 已成功部署服务（第一次执行）
**When** Pipeline 再次运行相同的 Ansible playbook（不修改任何配置）
**Then** Ansible 执行结果显示 "changed=0"
**And** PLAY RECAP 显示：
```
test-lxc-01: ok=15 changed=0 unreachable=0 failed=0 skipped=2
```

**And** 服务保持运行状态，无重启
**And** 配置文件内容未修改（通过 `--diff` 验证）

**When** Pipeline 第三次运行（仍无配置修改）
**Then** 结果与第二次一致（changed=0）
**And** 执行时间与首次部署相近（无额外开销）

**And** Ansible tasks 使用幂等性守护：
- `template` 模块：内容未变化时不标记 changed
- `command` 模块：使用 `creates:` 参数
- `systemd` 模块：服务已启动时不重启
- 自定义命令：使用 `changed_when: false` 或条件判断

---

## Epic 5: Pipeline 编排与自动化工作流

DevOps Engineer 可以通过统一的 Jenkins Pipeline 编排整个端到端流程（Webhook → Router → Terraform → Ansible），查看实时执行日志和状态，并在关键节点进行人工审批。

### Story 5.1: 端到端 Pipeline 集成测试

As a DevOps Engineer,
I want to 执行完整的端到端流程从 NetBox 创建到服务部署,
So that 验证所有组件正确集成并能交付可用的虚拟机。

**Acceptance Criteria:**

**Given** 所有前置 Epic 已完成（Epic 1-4）
**When** 我在 NetBox 中创建新虚拟机：
- Name: "integration-test-01"
- Status: "Planned"
- Custom Fields:
  - infrastructure_platform: "proxmox"
  - automation_level: "requires_approval"
  - proxmox_node: "pve0"
  - proxmox_vmid: 250
  - ansible_groups: ["pve_lxc", "tailscale"]
  - playbook_name: "deploy-common.yml"

**Then** 以下流程自动执行：
1. NetBox Webhook 触发 < 5 秒（NFR-P1）
2. Router Pipeline 启动并路由到 Proxmox-Provisioning
3. Terraform Plan 生成并显示将创建的资源
4. Approval Gate 暂停等待审批
5. 审批通过后 Terraform Apply 创建 LXC 容器
6. Ansible Inventory 自动刷新
7. Ansible playbook 执行服务部署
8. 健康检查验证通过
9. NetBox 状态更新为 "active"

**And** 总执行时间 < 3 分钟（NFR-P3）
**And** 虚拟机 SSH 可访问：`ssh root@192.168.1.250`
**And** 虚拟机出现在 Ansible inventory 中
**And** 所有 Pipeline 阶段状态为 "SUCCESS"
**And** NetBox Comments 记录完整的部署历史

### Story 5.2: Jenkins UI 日志和状态展示

As a DevOps Engineer,
I want to 在 Jenkins 界面查看 Pipeline 执行日志和实时状态,
So that 我可以监控自动化进度并快速诊断问题。

**Acceptance Criteria:**

**Given** Pipeline 正在执行
**When** 我打开 Jenkins Blue Ocean 界面或 Classic UI
**Then** 我可以看到：
- **Pipeline 总体状态**：Running / Success / Failed / Aborted
- **当前执行阶段**：高亮显示正在执行的 stage
- **各阶段耗时**：每个 stage 的执行时间（秒/分钟）
- **Console Output**：实时滚动的日志输出
- **Stage View**：可视化的 Pipeline 流程图

**And** Console Output 包含：
- Terraform Plan 完整输出（包括资源变更摘要）
- Ansible playbook 执行日志（task 名称、状态、耗时）
- 健康检查验证结果
- NetBox API 调用响应

**And** 日志中敏感信息已脱敏（API Token、密码等）
**And** 失败的 stage 显示红色标记和错误信息
**And** 可以下载完整日志文件（Console Output as TXT）
**And** Jenkins 保留最近 10 个构建历史（NFR-M10）

### Story 5.3: Git Push 事件触发 Pipeline

As a DevOps Engineer,
I want to 在 Git 仓库 push 代码时自动触发 Pipeline,
So that Terraform/Ansible 代码变更可以自动应用到基础设施。

**Acceptance Criteria:**

**Given** GitHub Webhook 配置指向 Jenkins（通过 Cloudflare Tunnel）
**When** 我在本地修改 Terraform 配置并 push 到 GitHub：
```bash
git add terraform/proxmox/caddy.tf
git commit -m "feat(terraform): increase caddy memory to 1GB"
git push origin main
```
**Then** GitHub Webhook 触发 Jenkins Pipeline
**And** Pipeline 识别为 Git push 触发（而非 NetBox Webhook）
**And** Pipeline 执行：
1. Checkout 最新代码
2. Terraform Plan（检测配置变更）
3. 显示 Terraform Plan diff
4. Approval Gate 等待审批
5. Terraform Apply 应用变更
6. Git commit 审计记录

**And** Terraform Plan 显示：
```
~ proxmox_virtual_environment_vm.caddy
    ~ memory.dedicated: 512 → 1024
```

**And** Pipeline 日志记录 Git commit 信息（commit hash, author, message）
**And** 变更应用后 Git tag 自动创建（可选）：`v1.2.3-applied-at-<timestamp>`

### Story 5.4: Pipeline 失败通知机制

As a DevOps Engineer,
I want to 在 Pipeline 失败时收到通知,
So that 我可以及时处理故障而不需要主动检查 Jenkins。

**Acceptance Criteria:**

**Given** Pipeline 执行过程中某个阶段失败（Terraform Apply / Ansible Deploy / Verification）
**When** Pipeline 进入 `post.failure` 块
**Then** 系统发送通知（如果配置了通知渠道）：

**Slack 通知示例：**
```
❌ Pipeline Failed: Proxmox-Provisioning

VM: integration-test-01
Platform: proxmox
Failed Stage: Terraform Apply
Error: timeout while waiting for VM to start

Build: #42
Duration: 2m 15s
Console: https://jenkins.willfan.me/job/Proxmox-Provisioning/42/console
```

**Email 通知示例：**
```
Subject: ❌ Jenkins Pipeline Failed - Proxmox-Provisioning #42

Failed Stage: Terraform Apply
VM Name: integration-test-01
Error Details:
  timeout while waiting for VM to start (waited 5 minutes)

View full log:
https://jenkins.willfan.me/job/Proxmox-Provisioning/42/console
```

**And** 通知包含：
- Pipeline 名称和 build number
- 失败的 stage 名称
- 错误摘要（前 200 字符）
- Jenkins build URL 链接
- 虚拟机名称和平台信息

**And** 通知在 Pipeline 失败后 30 秒内发送
**And** 如果未配置通知渠道，在 Console Output 显示警告（但不影响 Pipeline 状态）
**And** 重试成功的 Pipeline 发送恢复通知（可选）

### Story 5.5: 手动重新运行失败的 Pipeline

As a DevOps Engineer,
I want to 手动重新运行失败的 Pipeline,
So that 在修复问题后可以重试部署而无需重新创建 NetBox 记录。

**Acceptance Criteria:**

**Given** Pipeline 执行失败（例如 Terraform Apply 超时）
**When** 我在 Jenkins UI 中点击 "Rebuild" 或 "Replay" 按钮
**Then** Pipeline 使用相同的参数重新运行：
- NETBOX_VM_ID: <原 ID>
- NETBOX_VM_NAME: <原名称>
- PLATFORM: <原平台>

**And** Pipeline 从头开始执行所有 stage（不跳过已成功的 stage）
**And** Terraform 检测到已存在的资源（通过 state）
**And** Terraform Plan 显示：
```
No changes. Your infrastructure matches the configuration.
```
或者显示实际的差异（如果配置已修复）

**And** Ansible playbook 幂等性保证安全重试（Story 4.6）
**And** 重试成功后 NetBox 状态更新为 "active"
**And** 重试失败后状态保持 "failed"

**When** 我需要修改参数重新运行
**Then** 我可以在 Jenkins "Build with Parameters" 界面：
- 修改 NETBOX_VM_ID
- 修改 AUTOMATION_LEVEL（例如改为 fully_automated 跳过审批）
- 添加 DEBUG=true 启用详细日志

### Story 5.6: Pipeline 审计追踪和历史记录

As a DevOps Engineer,
I want to 查看特定虚拟机相关的所有 Pipeline 执行历史,
So that 我可以追溯资源的创建、变更和故障历史。

**Acceptance Criteria:**

**Given** 虚拟机 "integration-test-01" 已通过 Pipeline 创建
**When** 我在 Jenkins 搜索该虚拟机相关的构建历史
**Then** 我可以看到所有相关的 Pipeline 执行记录：
- Build #42: 2026-02-06 10:23 - SUCCESS - Initial creation
- Build #51: 2026-02-07 14:15 - SUCCESS - Memory update (512MB → 1GB)
- Build #55: 2026-02-08 09:42 - FAILED - Terraform timeout
- Build #56: 2026-02-08 09:50 - SUCCESS - Retry after fix

**And** 每条记录包含：
- Build number 和时间戳
- 执行结果（SUCCESS / FAILED / ABORTED）
- 触发来源（NetBox Webhook / Git push / Manual）
- 变更摘要（created / modified / failed）
- Console Output 链接

**And** 可以通过虚拟机名称过滤构建历史
**And** 可以对比两次构建的 Terraform Plan diff
**And** 构建历史保留至少 30 天（受 Jenkins 配置限制）
**And** 关键构建可以标记为 "Keep this build forever"

---

## Epic 6: 错误处理与恢复机制

当 Pipeline 执行失败时，系统能够自动标记资源状态、记录详细错误日志、支持安全重试，并在连续失败时发送告警，确保运维人员可以快速定位和修复问题。

### Story 6.1: Terraform 失败时标记 NetBox 状态

As a System,
I want to 在 Terraform Apply 失败时自动将 NetBox 虚拟机状态标记为 "failed",
So that DevOps Engineer 可以快速识别失败的资源。

**Acceptance Criteria:**

**Given** Proxmox Provisioning Pipeline 运行到 Terraform Apply 阶段
**When** Terraform Apply 失败（例如 Proxmox API 超时、VMID 冲突、资源不足）
**Then** Pipeline 进入 `post.failure` 块并执行：
```groovy
post {
    failure {
        script {
            sh '''
                curl -X PATCH "http://192.168.1.104:8080/api/dcim/virtual-machines/${NETBOX_VM_ID}/" \
                  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
                  -H "Content-Type: application/json" \
                  -d '{
                    "status": "failed",
                    "comments": "Terraform Apply failed at '"$(date -Iseconds)"'. See Jenkins build '"${BUILD_URL}"' for details."
                  }'
            '''
        }
    }
}
```

**And** NetBox 虚拟机状态从 "planned" 或 "provisioning" → "failed"
**And** NetBox Comments 包含：
- 失败时间戳
- Jenkins build URL 链接
- 失败阶段标识（"Terraform Apply"）

**And** NetBox Change Log 记录状态变更事件
**And** 状态回写在 Pipeline 失败后 10 秒内完成
**And** 如果状态回写 API 调用失败，Pipeline 记录警告但不再次失败

### Story 6.2: Ansible 失败时标记降级状态

As a System,
I want to 在 Ansible 部署失败时将虚拟机标记为 "degraded" 状态,
So that 区分"资源已创建但服务未部署"和"资源创建失败"两种情况。

**Acceptance Criteria:**

**Given** Terraform Apply 成功创建虚拟机，但 Ansible playbook 执行失败
**When** Pipeline 检测到 Ansible 失败（退出码非 0）
**Then** Pipeline 更新 NetBox 状态：
```bash
curl -X PATCH "http://192.168.1.104:8080/api/dcim/virtual-machines/${NETBOX_VM_ID}/" \
  -d '{
    "status": "active",
    "custom_fields": {
      "deployment_status": "degraded",
      "ansible_last_error": "Service deployment failed - docker service failed to start"
    },
    "comments": "VM created successfully but Ansible deployment failed. Manual intervention required. See Jenkins build '"${BUILD_URL}"'"
  }'
```

**And** 虚拟机基础状态为 "active"（资源存在）
**And** 部署状态 Custom Field 为 "degraded"（服务未正常运行）
**And** Comments 明确说明"资源已创建，但服务部署失败"
**And** DevOps Engineer 可以在 NetBox 中过滤 `deployment_status=degraded` 查看所有部署失败的虚拟机
**And** NetBox UI 中显示警告图标（如果配置了 Custom Field 显示样式）

### Story 6.3: 失败资源自动重试机制

As a System,
I want to 对失败的虚拟机自动重试 Pipeline 最多 3 次,
So that 临时网络问题或 API 超时不会导致永久失败。

**Acceptance Criteria:**

**Given** 虚拟机首次创建失败（例如 Proxmox API 超时）
**When** Pipeline 检测到失败原因是临时性错误（可重试）
**Then** Pipeline 在 60 秒后自动重试
**And** 重试前在 NetBox Custom Field 记录重试次数：
```json
{
  "custom_fields": {
    "retry_count": 1,
    "last_retry_at": "2026-02-06T10:25:00Z"
  }
}
```

**And** 如果第 1 次重试成功，Pipeline 标记为 SUCCESS，清除 retry_count
**And** 如果第 1 次重试仍失败，等待 120 秒后进行第 2 次重试（retry_count = 2）
**And** 如果第 2 次重试仍失败，等待 180 秒后进行第 3 次重试（retry_count = 3）

**When** 第 3 次重试仍失败
**Then** Pipeline 停止自动重试
**And** NetBox 状态标记为 "failed"，retry_count = 3
**And** 发送告警通知："VM creation failed after 3 retries. Manual intervention required."
**And** Pipeline 日志记录所有重试历史和失败原因

**And** 以下错误类型被识别为"临时性可重试"：
- Proxmox API timeout
- Network connection errors
- Temporary resource unavailability

**And** 以下错误类型被识别为"永久性不可重试"：
- VMID 冲突（已被占用）
- 认证失败（API Token 无效）
- 配置错误（无效的 node name）

### Story 6.4: 手动重置状态触发重试

As a DevOps Engineer,
I want to 在 NetBox 中手动重置虚拟机状态以触发重试,
So that 在修复问题后可以重新运行自动化流程。

**Acceptance Criteria:**

**Given** 虚拟机状态为 "failed"，retry_count = 3（已达重试上限）
**When** 我在 NetBox 中编辑虚拟机：
- 将 Status 从 "failed" 改回 "planned"
- 保存变更

**Then** NetBox Webhook 触发（event = "updated"）
**And** Router Pipeline 识别为"状态重置"（从 failed → planned）
**And** Pipeline 清除 retry_count Custom Field（重置为 0）
**And** Pipeline 重新开始完整的创建流程（Terraform Plan → Apply → Ansible Deploy）

**And** 如果问题已修复，Pipeline 成功完成并将状态标记为 "active"
**And** 如果问题仍存在，Pipeline 再次失败并进入新一轮重试机制（最多 3 次）

**And** DevOps Engineer 可以在重置前：
- 修改虚拟机配置（例如更换 proxmox_node）
- 修改 automation_level（例如改为 fully_automated 跳过审批）
- 添加 Comments 说明修复操作

### Story 6.5: 错误日志关联到 NetBox 虚拟机对象

As a DevOps Engineer,
I want to 在 NetBox 虚拟机 Comments 中查看详细错误日志,
So that 无需切换到 Jenkins 就能初步诊断问题。

**Acceptance Criteria:**

**Given** Pipeline 执行失败（Terraform 或 Ansible）
**When** Pipeline `post.failure` 块执行
**Then** 系统提取错误信息并更新 NetBox Comments：
```python
# scripts/log-error-to-netbox.py
error_summary = extract_error_from_jenkins_log(BUILD_URL)
netbox_api.patch(
    f"/api/dcim/virtual-machines/{VM_ID}/",
    {
        "comments": f"""
[FAILED] Pipeline Execution Failed
Time: {datetime.now().isoformat()}
Build: {BUILD_URL}
Stage: Terraform Apply
Error:
{error_summary[:500]}  # 限制为 500 字符
Full log: {BUILD_URL}/console
"""
    }
)
```

**And** Comments 包含：
- 失败时间戳
- 失败阶段（Terraform Apply / Ansible Deploy / Verification）
- 错误摘要（前 500 字符）
- Jenkins build URL（完整日志链接）

**And** 如果错误信息超过 500 字符，Comments 包含 "... (truncated)" 提示
**And** NetBox Comments 支持多次失败追加记录（不覆盖之前的记录）
**And** Comments 格式清晰，易于阅读（使用换行和缩进）

### Story 6.6: 连续失败告警机制

As a System,
I want to 在虚拟机连续失败 3 次后发送告警通知并暂停自动重试,
So that 避免系统无限循环浪费资源并及时提醒运维人员。

**Acceptance Criteria:**

**Given** 虚拟机创建失败并已自动重试 3 次，仍然失败
**When** Pipeline 检测到 retry_count = 3 且仍失败
**Then** 系统发送告警通知：

**Slack 告警示例：**
```
🚨 ALERT: VM Creation Failed After 3 Retries

VM Name: integration-test-01
Platform: proxmox
VMID: 250
Status: failed (permanent)

Error Pattern: Proxmox API timeout (consistent across all retries)

Manual intervention required. Possible actions:
1. Check Proxmox node pve0 connectivity
2. Verify API token permissions
3. Reset VM status to 'planned' in NetBox to retry

Latest build: https://jenkins.willfan.me/job/Proxmox-Provisioning/56/console
NetBox VM: http://192.168.1.104:8080/dcim/virtual-machines/<id>/
```

**And** 告警包含：
- 虚拟机详细信息（名称、平台、VMID）
- 失败模式分析（一致的错误 vs 不同错误）
- 推荐的修复操作
- Jenkins 和 NetBox 链接

**And** 告警在第 3 次重试失败后 1 分钟内发送
**And** Pipeline 状态标记为 "FAILED - Manual Intervention Required"
**And** NetBox Custom Field `requires_manual_intervention = true`
**And** 系统暂停该虚拟机的自动重试，直到手动重置状态

### Story 6.7: Jenkins 详细错误堆栈展示

As a DevOps Engineer,
I want to 在 Jenkins Console Output 查看详细的错误堆栈和失败原因,
So that 我可以快速定位根本问题并进行修复。

**Acceptance Criteria:**

**Given** Pipeline 执行失败
**When** 我打开 Jenkins Console Output
**Then** 我可以看到详细的错误信息：

**Terraform 失败示例：**
```
[Terraform Apply] FAILED
╷
│ Error: timeout while waiting for VM 250 to start
│ 
│   on generated.tf line 15, in resource "proxmox_virtual_environment_vm" "from_netbox":
│   15: resource "proxmox_virtual_environment_vm" "from_netbox" {
│ 
│ Waited 5 minutes for VM to reach 'running' state.
│ Current state: 'starting'
│ Proxmox node: pve0
│ Last API response: {"status": "starting", "uptime": 0}
╵

Troubleshooting steps:
1. Check Proxmox web UI: https://192.168.1.100:8006/#v1:0:=qemu/250
2. Verify node pve0 has sufficient resources (CPU, memory, storage)
3. Check Proxmox logs: journalctl -u pve-cluster
```

**Ansible 失败示例：**
```
[Ansible Deploy] FAILED

TASK [docker : Install Docker packages] ***********************************
fatal: [integration-test-01]: FAILED! => {
    "changed": false,
    "msg": "Failed to update apt cache: W: Failed to fetch http://deb.debian.org/debian/dists/bookworm/InRelease  Temporary failure resolving 'deb.debian.org'"
}

PLAY RECAP *****************************************************************
integration-test-01        : ok=3    changed=0    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0

Root cause: DNS resolution failure
Possible fix: Check /etc/resolv.conf on the VM
```

**And** 错误信息包含：
- 失败的具体命令或资源
- 错误消息（原始输出）
- 上下文信息（文件名、行号）
- 故障排查步骤建议
- 相关日志文件路径

**And** 关键错误信息高亮显示（通过 ANSI 颜色代码）
**And** 可以搜索 Console Output（Ctrl+F）定位错误关键词
**And** 长日志输出不截断（完整保留，NFR-M10）

---

## Epic 7: 可观测性与审计追踪

DevOps Engineer 可以完整追踪每个资源的配置历史、Pipeline 执行记录、变更审计日志，了解当前运行状态，并追溯变更的触发来源和责任人。

### Story 7.1: NetBox Change Log 配置历史追踪

As a DevOps Engineer,
I want to 在 NetBox Change Log 中查看虚拟机的所有配置变更历史,
So that 我可以追溯谁在何时修改了虚拟机配置。

**Acceptance Criteria:**

**Given** 虚拟机在 NetBox 中已创建并经历多次配置变更
**When** 我在 NetBox 虚拟机详情页点击 "Change Log" 标签
**Then** 我可以看到完整的变更历史列表：
```
2026-02-08 14:23 | will | Updated memory from 512 to 1024 MB
2026-02-07 10:15 | will | Updated status from 'planned' to 'active'
2026-02-06 09:42 | will | Created virtual machine integration-test-01
```

**And** 每条变更记录包含：
- 时间戳（精确到秒）
- 操作用户（NetBox 用户名）
- 变更类型（Created / Updated / Deleted）
- 变更字段和值（before → after）

**And** 可以查看 Custom Fields 的变更历史：
```
2026-02-07 11:30 | will | automation_level: requires_approval → fully_automated
2026-02-06 10:00 | will | proxmox_node: pve0 → pve1
```

**And** Change Log 保留至少 90 天（NFR-S10）
**And** 可以过滤变更类型（仅显示 Updated）
**And** 可以导出变更历史为 CSV/JSON 格式

### Story 7.2: Jenkins Pipeline 执行历史关联

As a DevOps Engineer,
I want to 查看与特定虚拟机相关的所有 Pipeline 执行历史,
So that 我可以了解该资源的完整自动化生命周期。

**Acceptance Criteria:**

**Given** 虚拟机 "integration-test-01" 已通过多次 Pipeline 执行
**When** 我在 Jenkins 中搜索该虚拟机相关的构建
**Then** 我可以看到所有相关 Pipeline 执行：

**方法 1: 通过 Jenkins Search Box**
- 搜索关键词 "integration-test-01"
- 显示所有包含该虚拟机名称的构建

**方法 2: 通过 NetBox Comments 中的 Jenkins 链接**
- NetBox Comments 包含每次 Pipeline 的 build URL
- 点击链接直接跳转到对应的 Jenkins build

**方法 3: 通过 Jenkins Build Parameters**
- 在 "Proxmox-Provisioning" Job 的 Build History 中过滤 `NETBOX_VM_NAME=integration-test-01`

**And** 每条 Pipeline 记录显示：
- Build number (#42, #51, #55, #56)
- 时间戳和持续时间
- 执行结果（SUCCESS / FAILED / ABORTED）
- 触发来源（Webhook / Git / Manual）
- 关键参数（VM_NAME, PLATFORM, AUTOMATION_LEVEL）

**And** 可以对比两次构建的差异（Terraform Plan diff）
**And** 可以查看每次构建的完整 Console Output
**And** Jenkins 保留最近 10 个构建历史（NFR-M10）

### Story 7.3: Terraform Plan Diff 记录

As a DevOps Engineer,
I want to 记录每次 Terraform Apply 的变更内容,
So that 我可以准确了解每次部署实际修改了哪些资源。

**Acceptance Criteria:**

**Given** Terraform Plan 生成并执行 Apply
**When** Pipeline 保存 Terraform Plan 输出为 artifact
**Then** Jenkins build artifacts 包含：
- `terraform-plan.txt`: 完整的 Plan 输出
- `terraform-plan-summary.json`: 变更摘要（JSON 格式）

**Plan Summary JSON 示例：**
```json
{
  "build_number": 42,
  "timestamp": "2026-02-06T10:23:45Z",
  "changes": {
    "add": 1,
    "change": 0,
    "destroy": 0
  },
  "resources": [
    {
      "address": "proxmox_virtual_environment_vm.from_netbox[\"integration-test-01\"]",
      "mode": "managed",
      "type": "proxmox_virtual_environment_vm",
      "name": "from_netbox",
      "action": "create",
      "changes": {
        "name": "integration-test-01",
        "node_name": "pve0",
        "vm_id": 250,
        "memory": 512
      }
    }
  ]
}
```

**And** Plan diff 在 Console Output 中完整显示：
```
Terraform will perform the following actions:

  # proxmox_virtual_environment_vm.from_netbox["integration-test-01"] will be created
  + resource "proxmox_virtual_environment_vm" "from_netbox" {
      + name        = "integration-test-01"
      + node_name   = "pve0"
      + vm_id       = 250
      + memory      = 512
      + ...
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

**And** Plan artifacts 保留 30 天
**And** 可以下载 Plan 文件进行离线分析
**And** Plan JSON 可被外部工具解析（例如生成变更报告）

### Story 7.4: Ansible Playbook Diff 输出记录

As a DevOps Engineer,
I want to 记录每次 Ansible Playbook 执行的配置文件变更,
So that 我可以了解 Ansible 实际修改了哪些文件和配置。

**Acceptance Criteria:**

**Given** Ansible playbook 以 `--diff` 模式执行
**When** Playbook 修改配置文件（使用 template 或 copy 模块）
**Then** Console Output 显示文件变更 diff：
```
TASK [caddy : Deploy Caddyfile] *******************************************
--- before: /etc/caddy/Caddyfile
+++ after: /tmp/ansible-tmp-12345/Caddyfile.j2
@@ -1,3 +1,7 @@
 {
     admin off
 }
+
+example.com {
+    reverse_proxy localhost:8080
+}

changed: [integration-test-01]
```

**And** Diff 输出包含：
- 文件路径
- 变更行（+ 新增, - 删除, 修改的上下文）
- 变更任务名称

**And** 如果文件未变化，显示 "ok: [host] (no changes)"
**And** Ansible PLAY RECAP 总结所有变更：
```
PLAY RECAP *****************************************************************
integration-test-01: ok=15 changed=3 unreachable=0 failed=0
```

**And** `changed=3` 表示有 3 个任务修改了系统状态
**And** Diff 输出保留在 Jenkins Console Log 中
**And** 敏感数据（密码、API Token）在 diff 中自动脱敏

### Story 7.5: 虚拟机当前运行状态展示

As a DevOps Engineer,
I want to 在 NetBox 中查看虚拟机的当前运行状态,
So that 我可以快速了解资源是否正常运行。

**Acceptance Criteria:**

**Given** 虚拟机已成功创建并部署
**When** 我在 NetBox 虚拟机详情页查看状态
**Then** 我可以看到以下状态字段：

**内置状态字段：**
- Status: "Active" （资源已创建）

**Custom Fields 状态：**
- `deployment_status`: "deployed" （服务已部署）
- `last_deployed_at`: "2026-02-06T10:25:30Z"
- `terraform_applied_at`: "2026-02-06T10:23:45Z"
- `ansible_run_status`: "success"
- `health_check_status`: "passed"

**And** 状态字段有颜色标识（如果配置了 NetBox UI 样式）：
- "active" / "deployed" / "passed": 绿色
- "failed" / "degraded": 红色
- "planned" / "provisioning": 黄色

**And** 可以通过状态过滤虚拟机列表：
```
Filter: status=active AND deployment_status=deployed
Result: 显示所有正常运行的虚拟机
```

**And** 可以通过 API 查询状态：
```bash
curl -H "Authorization: Token ${TOKEN}" \
  "http://192.168.1.104:8080/api/dcim/virtual-machines/?status=active&cf_deployment_status=deployed"
```

### Story 7.6: 变更触发来源追踪

As a DevOps Engineer,
I want to 追溯特定配置变更的触发来源,
So that 我可以了解是 Webhook 还是 Git commit 导致了某次变更。

**Acceptance Criteria:**

**Given** Pipeline 执行完成（成功或失败）
**When** 我查看 Pipeline 执行记录
**Then** 我可以看到触发来源信息：

**NetBox Webhook 触发示例：**
```
Trigger Source: NetBox Webhook
Event Type: created
VM ID: 123
VM Name: integration-test-01
Triggered by: will (NetBox user)
Webhook Payload:
  {
    "event": "created",
    "timestamp": "2026-02-06T10:23:00Z",
    "username": "will",
    "data": { ... }
  }
```

**Git Push 触发示例：**
```
Trigger Source: Git Push
Commit: a1b2c3d4
Author: will <will@example.com>
Commit Message: feat(terraform): increase caddy memory to 1GB
Branch: main
Files Changed:
  - terraform/proxmox/caddy.tf
  - ansible/inventory/host_vars/caddy.yml
```

**Manual 触发示例：**
```
Trigger Source: Manual (Jenkins UI)
Triggered by: will (Jenkins user)
Build Parameters:
  NETBOX_VM_ID: 123
  AUTOMATION_LEVEL: fully_automated
  DEBUG: true
```

**And** 触发来源记录在：
- Jenkins build description
- Jenkins build parameters
- Pipeline 环境变量（`TRIGGER_SOURCE`, `TRIGGER_USER`）

**And** NetBox Comments 包含触发来源：
```
Provisioned by Jenkins build #42
Trigger: NetBox Webhook (created by will)
Time: 2026-02-06 10:25:30
```

### Story 7.7: 基础设施变更审计日志生成

As a System,
I want to 生成基础设施变更的审计日志,
So that 满足合规要求并支持安全审计。

**Acceptance Criteria:**

**Given** Pipeline 执行成功完成资源创建或变更
**When** Pipeline 执行 Git commit 记录审计日志
**Then** Git commit 包含完整的变更信息：

**Commit Message 格式（Conventional Commits）：**
```
feat(proxmox): create VM integration-test-01

- Platform: proxmox
- Node: pve0
- VMID: 250
- Memory: 512 MB
- vCPUs: 1
- IP: 192.168.1.250/24
- Deployed by: will
- Jenkins build: #42
- NetBox VM ID: 123

Terraform changes:
  + proxmox_virtual_environment_vm.from_netbox["integration-test-01"]
  + ansible_host.from_netbox["integration-test-01"]

Ansible playbook: deploy-common.yml
Deployment status: success
```

**And** Git commit 自动生成并 push 到仓库
**And** Commit 包含：
- 谁（NetBox user / Jenkins user）
- 何时（timestamp）
- 改了什么（Terraform Plan summary）
- 为什么（Trigger source - Webhook/Git/Manual）
- 结果（成功/失败）

**And** Git history 可通过 `git log --grep="integration-test-01"` 搜索
**And** 审计日志保留在 Git 仓库永久历史中
**And** 可以通过 GitHub/GitLab UI 查看图形化的变更历史
**And** Git commit 符合 Conventional Commits 规范（NFR-M12）

---

## Epic 8: 物理服务器配置管理

DevOps Engineer 可以在 NetBox 中管理物理服务器，系统自动生成 Ansible Inventory 并执行配置管理，跳过 Terraform provisioning 步骤，实现物理和虚拟资源的统一管理。

### Story 8.1: 创建 Physical Device Sync Pipeline

As a DevOps Engineer,
I want to 创建专门的 Physical Device Sync Pipeline,
So that 物理服务器可以跳过 Terraform 直接执行 Ansible 配置管理。

**Acceptance Criteria:**

**Given** Router Pipeline 识别到 `infrastructure_platform = physical`
**When** Router 触发 "Physical-Device-Sync" Jenkins Job
**Then** Pipeline 包含以下阶段：
1. **Checkout**: 拉取 Git 仓库
2. **Setup**: 配置 Ansible Vault 密码
3. **Generate Inventory**: 从 NetBox 生成 Ansible Inventory（跳过 Terraform）
4. **Verify SSH Connectivity**: 测试物理服务器 SSH 连接
5. **Ansible Deploy**: 执行配置管理 playbook
6. **Health Check**: 运行验证 tasks
7. **Update NetBox Status**: 更新物理设备状态

**And** Pipeline 明确跳过 Terraform 阶段：
```groovy
stage('Skip Terraform') {
    steps {
        echo "Platform is 'physical' - Skipping Terraform provisioning"
        echo "Physical devices are pre-existing infrastructure"
    }
}
```

**And** Pipeline 日志清晰显示："Physical Device Mode - Terraform Skipped"
**And** Pipeline 执行时间 < 1 分钟（NFR-P5）
**And** 物理服务器配置管理复用现有 Ansible roles（common, docker, tailscale 等）

### Story 8.2: 从 NetBox 生成物理服务器 Inventory

As a System,
I want to 从 NetBox Device 数据直接生成 Ansible Inventory,
So that 物理服务器无需 Terraform state 即可纳入自动化管理。

**Acceptance Criteria:**

**Given** NetBox 中创建了 Device 记录：
- Device Type: Dell PowerEdge R720
- Site: Homelab
- Primary IP: 192.168.1.50/24
- Status: "Active"
- Custom Fields:
  - infrastructure_platform: "physical"
  - ansible_groups: ["physical_servers", "docker", "tailscale"]
  - playbook_name: "deploy-physical.yml"

**When** Pipeline 执行 `scripts/netbox-to-inventory.py --platform physical`
**Then** 脚本通过 NetBox API 查询所有 `infrastructure_platform=physical` 的 Device
**And** 生成 Ansible Inventory JSON：
```json
{
  "physical_servers": {
    "hosts": ["dell-r720-01"]
  },
  "docker": {
    "hosts": ["dell-r720-01"]
  },
  "tailscale": {
    "hosts": ["dell-r720-01"]
  },
  "_meta": {
    "hostvars": {
      "dell-r720-01": {
        "ansible_host": "192.168.1.50",
        "device_type": "Dell PowerEdge R720",
        "site": "Homelab"
      }
    }
  }
}
```

**And** Inventory 文件保存到 `ansible/inventory/physical-devices.json`
**And** Ansible 可以使用该 inventory：`ansible-playbook -i inventory/physical-devices.json playbooks/deploy-physical.yml`
**And** Inventory 生成时间 < 10 秒
**And** 脚本处理多个物理服务器（支持批量生成）

### Story 8.3: 物理服务器 SSH 连接验证

As a System,
I want to 在执行 Ansible 前验证物理服务器 SSH 连接,
So that 早期发现连接问题避免浪费时间在失败的部署上。

**Acceptance Criteria:**

**Given** Physical Device Sync Pipeline 生成了 Inventory
**When** Pipeline 执行 "Verify SSH Connectivity" 阶段
**Then** 系统测试 SSH 连接：
```bash
ansible physical_servers -m ping -i inventory/physical-devices.json
```

**And** 如果 SSH 连接成功，输出：
```
dell-r720-01 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

**And** 如果 SSH 连接失败，Pipeline 立即终止：
```
dell-r720-01 | UNREACHABLE! => {
    "changed": false,
    "msg": "Failed to connect to the host via ssh: Connection timed out",
    "unreachable": true
}

ERROR: Physical device SSH connectivity check failed
```

**And** SSH 验证超时设置为 30 秒
**And** 验证失败时 NetBox Device 状态标记为 "offline"
**And** 验证成功后 Pipeline 继续执行 Ansible 配置管理

### Story 8.4: 物理服务器 Ansible 配置管理

As a DevOps Engineer,
I want to 在物理服务器上执行 Ansible playbook,
So that 物理服务器可以自动安装和配置所需的软件和服务。

**Acceptance Criteria:**

**Given** SSH 连接验证成功
**When** Pipeline 执行 Ansible playbook：
```bash
ansible-playbook playbooks/deploy-physical.yml \
  -i inventory/physical-devices.json \
  --limit dell-r720-01 \
  --diff
```
**Then** Playbook 执行以下 roles：
- `common`: 基础配置（时区、NTP、SSH 安全加固）
- `docker`: 安装 Docker Engine
- `tailscale`: 配置 Tailscale VPN
- 其他服务 roles（根据 ansible_groups 自动选择）

**And** Playbook 使用与虚拟机相同的 roles（代码复用）
**And** Playbook 执行成功，PLAY RECAP 显示：
```
dell-r720-01: ok=20 changed=5 unreachable=0 failed=0
```

**And** 物理服务器配置管理遵循幂等性原则（Story 4.6）
**And** Playbook 执行日志完整记录在 Jenkins Console Output
**And** 配置文件变更通过 `--diff` 模式显示

### Story 8.5: 物理服务器状态更新

As a System,
I want to 将物理服务器配置管理结果反馈到 NetBox,
So that DevOps Engineer 可以在 NetBox 中查看物理服务器的配置状态。

**Acceptance Criteria:**

**Given** Ansible playbook 在物理服务器上执行完成
**When** Pipeline 执行 "Update NetBox Status" 阶段
**Then** 如果配置管理成功：
```bash
curl -X PATCH "http://192.168.1.104:8080/api/dcim/devices/${NETBOX_DEVICE_ID}/" \
  -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  -d '{
    "custom_fields": {
      "configuration_status": "configured",
      "last_configured_at": "'"$(date -Iseconds)"'"
    },
    "comments": "Configuration applied successfully by Jenkins build #'"${BUILD_NUMBER}"'"
  }'
```

**And** NetBox Device 显示配置状态 Custom Field：
- `configuration_status`: "configured"
- `last_configured_at`: "2026-02-06T11:30:00Z"

**And** 如果配置管理失败：
- `configuration_status`: "configuration_failed"
- Comments 包含错误信息和 Jenkins build URL

**And** NetBox Change Log 记录状态更新事件
**And** 物理服务器可以在 NetBox 中通过 `configuration_status` 过滤

### Story 8.6: 物理和虚拟资源统一管理验证

As a DevOps Engineer,
I want to 验证物理服务器和虚拟机可以通过统一的 NetBox 界面管理,
So that 所有基础设施资源都在同一个 SSOT 中。

**Acceptance Criteria:**

**Given** NetBox 中同时存在虚拟机和物理设备
**When** 我在 NetBox 中搜索资源
**Then** 我可以看到统一的资源列表：
```
Virtual Machines:
  - integration-test-01 (Proxmox, Active, Deployed)
  - caddy (Proxmox, Active, Deployed)

Devices:
  - dell-r720-01 (Physical, Active, Configured)
  - pve0 (Proxmox Node, Active, Configured)
```

**And** 两种资源类型使用相同的 Custom Fields：
- infrastructure_platform
- automation_level
- ansible_groups
- playbook_name
- deployment_status / configuration_status

**And** 两种资源都可以触发 Webhook 自动化流程
**And** Router Pipeline 正确路由虚拟机和物理设备到不同的 Pipeline
**And** 物理服务器和虚拟机都出现在 Ansible inventory 中（不同 group）
**And** 可以对所有资源执行统一的 Ansible playbook（例如 `common` role）

---

## Epic 9: ESXi 平台支持（Post-MVP）

DevOps Engineer 可以在 NetBox 中创建 ESXi 虚拟机，系统自动使用 Terraform 在 VMware ESXi 上创建资源，复用 Proxmox 的架构模式，验证多平台支持能力。

### Story 9.1: ESXi Custom Fields 定义

As a DevOps Engineer,
I want to 定义 ESXi 平台特有的 Custom Fields,
So that 可以配置 ESXi 虚拟机创建所需的参数。

**Acceptance Criteria:**

**Given** NetBox Custom Fields 配置界面
**When** 我创建 ESXi 特有的 Custom Fields
**Then** 以下字段成功创建：
- `esxi_host` (Object - dcim.device): ESXi 主机引用
- `esxi_datastore` (Selection): Datastore 选择（例如 "datastore1", "datastore2"）
- `esxi_network` (Selection): Network 选择（例如 "VM Network", "Production"）
- `esxi_folder` (Text): VM 文件夹路径（例如 "/Datacenter/vm/homelab"）

**And** 这些字段仅在 `infrastructure_platform = esxi` 时必填（条件必填逻辑）
**And** `esxi_host` 字段关联到 NetBox Device 对象（ESXi 主机）
**And** Datastore 和 Network 选项与实际 ESXi 环境匹配
**And** 创建 ESXi 虚拟机时表单验证 ESXi 特有字段

### Story 9.2: ESXi Provisioning Pipeline 实现

As a DevOps Engineer,
I want to 创建 ESXi Provisioning Pipeline,
So that ESXi 虚拟机可以通过 Terraform 自动创建。

**Acceptance Criteria:**

**Given** Router Pipeline 识别到 `infrastructure_platform = esxi`
**When** Router 触发 "ESXi-Provisioning" Jenkins Job
**Then** Pipeline 包含以下阶段：
1. Checkout
2. Setup (配置 vSphere credentials)
3. Pull NetBox Data
4. Terraform Init (在 `terraform/esxi/` 目录)
5. Terraform Plan
6. Approval Gate (基于 automation_level)
7. Terraform Apply
8. Refresh Ansible Inventory
9. Update NetBox Status

**And** Pipeline 使用独立的 Terraform workspace: `iac-esxi`（ADR-008）
**And** Pipeline 使用 `vmware/vsphere` provider
**And** Pipeline 日志清晰显示 "Platform: ESXi"
**And** ESXi Pipeline 与 Proxmox Pipeline 完全隔离（独立目录、独立 state）

### Story 9.3: terraform-provider-vsphere 集成

As a System,
I want to 使用 terraform-provider-vsphere 从 NetBox 动态创建 ESXi 虚拟机,
So that ESXi 虚拟机创建流程与 Proxmox 保持一致。

**Acceptance Criteria:**

**Given** NetBox 中有状态为 "planned"、平台为 "esxi" 的虚拟机
**When** Terraform 执行 data source 查询和资源创建：
```hcl
# terraform/esxi/netbox-data.tf
data "netbox_virtual_machines" "esxi_vms" {
  filter {
    name  = "status"
    value = "planned"
  }
  filter {
    name  = "custom_fields.infrastructure_platform"
    value = "esxi"
  }
}

# terraform/esxi/generated.tf
resource "vsphere_virtual_machine" "from_netbox" {
  for_each = local.netbox_esxi_vms_map
  
  name             = each.value.name
  resource_pool_id = data.vsphere_resource_pool.pool.id
  datastore_id     = data.vsphere_datastore[each.value.custom_fields.esxi_datastore].id
  
  num_cpus = each.value.vcpus
  memory   = each.value.memory
  
  network_interface {
    network_id = data.vsphere_network[each.value.custom_fields.esxi_network].id
  }
  
  disk {
    label = "disk0"
    size  = 20
  }
  
  clone {
    template_uuid = data.vsphere_virtual_machine.template.id
  }
}
```
**Then** Terraform Plan 显示将创建的 ESXi 虚拟机
**And** Terraform Apply 成功在 ESXi 上创建虚拟机
**And** 创建的虚拟机出现在 vSphere Web Client 中
**And** Ansible inventory 包含新创建的 ESXi 虚拟机

### Story 9.4: 多平台并行处理验证

As a DevOps Engineer,
I want to 验证 Proxmox 和 ESXi 虚拟机可以同时创建而不互相干扰,
So that 确认多平台支持的完整性和隔离性。

**Acceptance Criteria:**

**Given** 同时在 NetBox 中创建两个虚拟机：
- VM1: infrastructure_platform = "proxmox"
- VM2: infrastructure_platform = "esxi"
**When** 两个 Webhook 触发（间隔 < 5 秒）
**Then** 两个 Router Pipeline 并发运行
**And** VM1 路由到 Proxmox-Provisioning（`terraform/proxmox/`）
**And** VM2 路由到 ESXi-Provisioning（`terraform/esxi/`）
**And** 两个 Pipeline 使用不同的 Terraform workspace 和 state
**And** Proxmox Pipeline 失败不影响 ESXi Pipeline
**And** 两个虚拟机都成功创建并出现在各自的平台中
**And** 两个虚拟机都出现在 Ansible inventory 的不同 group 中（`pve_vms` vs `esxi_vms`）

### Story 9.5: ESXi 平台端到端验证

As a DevOps Engineer,
I want to 执行至少 1 个 ESXi 虚拟机的完整端到端测试,
So that 验证 ESXi 平台支持的完整性。

**Acceptance Criteria:**

**Given** 所有 ESXi 前置配置完成（Story 9.1-9.3）
**When** 我在 NetBox 中创建 ESXi 测试虚拟机：
- Name: "esxi-test-01"
- Status: "Planned"
- Custom Fields:
  - infrastructure_platform: "esxi"
  - automation_level: "requires_approval"
  - esxi_host: (reference to ESXi host Device)
  - esxi_datastore: "datastore1"
  - esxi_network: "VM Network"
  - ansible_groups: ["esxi_vms", "docker"]

**Then** 完整流程自动执行：
1. Webhook 触发 Router Pipeline
2. Router 路由到 ESXi-Provisioning
3. Terraform Plan 生成（使用 vsphere provider）
4. Approval Gate 等待审批
5. Terraform Apply 在 ESXi 上创建虚拟机
6. Ansible inventory 刷新
7. Ansible playbook 部署服务
8. 健康检查验证
9. NetBox 状态更新为 "active"

**And** ESXi 虚拟机 SSH 可访问
**And** 虚拟机出现在 vSphere Web Client 中
**And** 虚拟机出现在 Ansible inventory `esxi_vms` group 中
**And** 总执行时间 < 5 分钟（NFR-P4）
**And** 所有 Pipeline 阶段状态为 "SUCCESS"
