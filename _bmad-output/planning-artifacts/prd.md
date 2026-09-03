---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish']
inputDocuments: 
  - '_bmad-output/planning-artifacts/product-brief-IaC-2026-01-31.md'
  - 'README.md'
  - 'AGENTS.md'
  - 'docs/README.md'
  - 'docs/designs/ansible-role-architecture.md'
  - 'docs/designs/cicd-architecture.md'
  - 'docs/improvement/PLANNING.md'
workflowType: 'prd'
documentCounts:
  briefCount: 1
  researchCount: 0
  brainstormingCount: 0
  projectDocsCount: 6
classification:
  projectType: 'developer_tool'
  projectSubtype: 'infrastructure_automation_platform'
  domain: 'devops'
  complexity: 'medium-high'
  projectContext: 'brownfield'
  architecturePattern: 'event_driven_infrastructure'
  keyTechnologies:
    - 'NetBox (DCIM/IPAM - SSOT)'
    - 'Terraform (IaC - Multi-platform)'
    - 'Ansible (Configuration Management)'
    - 'Jenkins (CI/CD Orchestration)'
  platforms:
    - 'Proxmox VE (Primary virtualization)'
    - 'VMware ESXi (Secondary virtualization)'
    - 'Physical Servers (Inventory only)'
  architecturalShift:
    from: 'Terraform Push模式 (静态.tf文件作为配置源)'
    to: 'NetBox Pull模式 (NetBox作为单一事实来源SSOT)'
  keyArchitecturalDecisions:
    - id: 'ADR-001'
      title: '数据流反转策略'
      decision: '渐进式迁移 (Incremental Migration)'
      rationale: '降低风险，支持学习和回滚'
    - id: 'ADR-002'
      title: 'Terraform集成模式'
      decision: 'terraform-provider-netbox data source'
      rationale: '原生Terraform语法，自动State管理'
    - id: 'ADR-003'
      title: '触发机制'
      decision: 'Webhook + Git混合模式'
      rationale: '即时响应 + 审计追踪'
    - id: 'ADR-004'
      title: '多平台路由策略'
      decision: 'Router Pipeline + Custom Field驱动'
      rationale: '集中管理，支持Proxmox/ESXi/Physical异构资源'
    - id: 'ADR-005'
      title: 'NetBox数据建模'
      decision: '核心字段先行，逐步扩展'
      rationale: '平衡完整性与复杂度'
    - id: 'ADR-006'
      title: '错误恢复策略'
      decision: '状态标记 + 重试机制'
      rationale: '保留意图，支持修复'
    - id: 'ADR-007'
      title: '物理服务器处理'
      decision: '跳过Terraform，仅Inventory + Ansible'
      rationale: '物理资源无需provisioning，仅配置管理'
    - id: 'ADR-008'
      title: 'Terraform工作区隔离'
      decision: '独立目录 (proxmox/ esxi/)'
      rationale: '完全隔离，降低爆炸半径'
---

# Product Requirements Document - IaC

**Author:** Will
**Date:** 2026-02-04

---

## Success Criteria

### User Success

**运维效率提升：**
- **简化的资源创建流程**：从 NetBox UI 点击"创建" → 自动触发 Pipeline → VM/LXC 可用，无需手动编写 Terraform 文件
- **可视化进度反馈**：Pipeline 执行过程中可在 Jenkins 界面查看实时进度（Check Changes → Setup → Plan → Approval → Apply → Deploy）
- **明确的成功信号（Aha Moment）**：
  - NetBox 中资源状态从 `planned` → `provisioning` → `active`
  - 能够成功 SSH 连接到新创建的 VM/LXC 或物理服务器
  - Ansible inventory 自动更新，资源出现在正确的 group 中

**学习与职业发展：**
- **可展示的完整 IaC 项目**：从 SSOT（NetBox）→ 触发器（Webhook）→ 编排（Jenkins）→ 配置（Terraform）→ 部署（Ansible）的端到端 CI/CD 流水线
- **掌握的核心技能**：
  - NetBox 数据建模（Custom Fields、Device Types、Virtual Machine 模型）
  - Terraform 动态配置（`terraform-provider-netbox` data source + `for_each` 循环）
  - 事件驱动架构（Webhook Router + 条件触发）
  - Multi-platform IaC（Proxmox / ESXi / Physical 异构环境管理）
- **面试展示亮点**：能够清晰讲解"Infrastructure as Data"理念和 SSOT 架构演进过程

### Business Success

**1 个月内 MVP 达成标准：**
- ✅ **NetBox 数据建模完成**：定义 `infrastructure_platform`、`automation_level` 等关键 Custom Fields
- ✅ **Router Pipeline 上线**：实现 Webhook → Router → Platform-specific Pipeline 的路由逻辑
- ✅ **至少 3 个简单 LXC 服务迁移**：Anki、Caddy、n8n 从静态 `.tf` 文件迁移到 NetBox Pull 模式
- ✅ **Proxmox 平台完整验证**：端到端流程（NetBox 创建 → Terraform apply → Ansible 配置 → SSH 可用）完整打通
- ✅ **物理服务器 Inventory 同步**：至少 1 台物理服务器通过 NetBox 更新 Ansible Inventory（跳过 Terraform）

**扩展目标（1 个月内可选）：**
- ⭐ ESXi 平台 POC：至少 1 个 ESXi VM 通过 NetBox 创建（验证多平台支持）
- ⭐ IP 自动分配基础功能：NetBox Prefix 池中自动选择可用 IP

**未来愿景（Post-MVP）：**
- 所有虚拟资源（包括 Jenkins、Netbox 本身）迁移到 NetBox Pull 模式
- Drift Detection 功能：定期对比 NetBox 期望状态 vs Terraform 实际状态
- 网络拓扑可视化：NetBox 成为完整的网络拓扑和连接关系中心

### Technical Success

**可靠性指标：**
- Webhook 触发成功率 > 95%（NetBox → Jenkins Generic Trigger）
- Terraform Apply 成功率 > 90%（无需人工修复）
- Pipeline 失败时自动在 NetBox 更新状态为 `failed_provisioning`

**幂等性保证：**
- 重复触发相同 Webhook 不会创建重复资源（通过 Terraform state 检测）
- Pipeline 失败后可以安全重试（状态机支持从 `failed_provisioning` → `provisioning`）
- 手动修改的资源不会被 Pipeline 覆盖（通过 `ignore_changes` 保护关键字段）

**可维护性要求：**
- **架构扩展性**：新增平台（如未来的 OCI Cloud）只需添加新的 Pipeline，Router 逻辑无需修改
- **数据模型演进**：NetBox Custom Fields 变更不会破坏现有 Terraform 代码（向后兼容）
- **清晰的审计追踪**：每次资源创建都在 Git 留下记录（Terraform state + Pipeline logs）

**性能目标：**
- 单个 LXC 创建（从 Webhook 触发到 SSH 可用）< 5 分钟
- Router Pipeline 路由决策 < 10 秒
- NetBox 数据查询（Terraform data source）< 30 秒

### Measurable Outcomes

**定量指标：**
- **创建速度提升**：手动编写 `.tf` 文件（5-10分钟）→ NetBox UI 填表（<2分钟）
- **错误率降低**：手动配置错误率（~20%）→ 模板化配置错误率（<5%）
- **迁移完成度**：至少 3 个服务迁移到 NetBox Pull 模式（Anki, Caddy, n8n）
- **Pipeline 成功率**：> 90% 的 Webhook 触发能成功创建资源

**定性成果：**
- **完整的 Portfolio 项目**：可在 GitHub 展示的端到端 IaC + CI/CD 系统
- **架构文档完整**：8 个 ADR（Architecture Decision Records）记录关键决策
- **技能树解锁**：NetBox 建模 + Terraform dynamic config + Event-driven architecture

---

## Product Scope

### MVP - Minimum Viable Product（1 个月内）

**Phase 1: NetBox 数据建模（Week 1）**
- [ ] 定义核心 Custom Fields：
  - `infrastructure_platform` (proxmox / esxi / physical)
  - `automation_level` (fully_automated / requires_approval / manual_only)
  - `proxmox_node`, `proxmox_vmid`, `ansible_groups`, `playbook_name`
- [ ] 创建 Device Types / VM Templates
- [ ] 手动录入 3-5 个测试资源（2 VM + 1 LXC + 1 Physical）

**Phase 2: Webhook Router（Week 1-2）**
- [ ] 开发 `Jenkinsfile-webhook-router`
- [ ] 配置 NetBox Webhook → Jenkins Generic Trigger
- [ ] 实现路由逻辑（解析 `infrastructure_platform` 并触发对应 Pipeline）
- [ ] 测试 Router 手动触发

**Phase 3: Proxmox Provisioning Pipeline（Week 2-3）**
- [ ] 开发 `scripts/netbox-to-terraform.py`（从 NetBox API 读取数据）
- [ ] 更新 `Jenkinsfile-proxmox-provisioning`：
  - [ ] 添加 NetBox data pull 阶段
  - [ ] 使用 `terraform-provider-netbox` data source
  - [ ] 实现动态 `for_each` 循环创建资源
- [ ] 人工审批 gate（`automation_level == requires_approval`）
- [ ] Ansible Inventory 自动刷新

**Phase 4: 迁移测试服务（Week 3-4）**
- [ ] 迁移 Anki LXC（简单服务，无复杂依赖）
- [ ] 迁移 Caddy LXC（验证网络配置）
- [ ] 迁移 n8n LXC（验证完整流程）
- [ ] 端到端验证：NetBox 创建 → Jenkins 触发 → Terraform apply → Ansible 配置 → SSH 成功

**Phase 5: 物理服务器同步（Week 4）**
- [ ] 开发 `Jenkinsfile-physical-device-sync`
- [ ] 实现仅 Inventory 更新逻辑（跳过 Terraform）
- [ ] 测试至少 1 台物理服务器的配置管理

### Growth Features (Post-MVP)

**Multi-Platform 支持：**
- [ ] ESXi Provisioning Pipeline（复用 Proxmox 架构）
- [ ] 适配 ESXi 特有字段（`esxi_host`, `esxi_datastore`）
- [ ] 至少 1 个 ESXi VM 端到端验证

**网络自动化：**
- [ ] IP 自动分配（从 NetBox Prefix 池中选择可用 IP）
- [ ] 端口冲突检测（防止 `proxmox_vmid` 重复）
- [ ] VLAN 自动配置

**监控与告警：**
- [ ] Pipeline 失败时发送通知（Telegram / Slack）
- [ ] NetBox 状态变更历史记录
- [ ] Drift Detection 定期任务（对比 NetBox vs Terraform state）

### Vision (Future)

**完整迁移：**
- [ ] 所有 LXC 容器迁移到 NetBox Pull 模式
- [ ] 所有 Proxmox VM 迁移（包括 Jenkins, Netbox 本身）
- [ ] 删除所有静态 `.tf` 文件（仅保留 module 定义）

**高级功能：**
- [ ] GitOps 层：NetBox 变更 → 自动生成 Git PR → 审批后 apply
- [ ] 自动回滚：Apply 失败时自动恢复 NetBox 状态
- [ ] 网络拓扑可视化：NetBox 作为完整的 L2/L3 网络文档中心
- [ ] Container 平台支持（Docker / Kubernetes）

**可观测性集成：**
- [ ] 与 Phase 4 监控系统集成（Prometheus + Grafana）
- [ ] NetBox 作为 monitoring target 的数据源
- [ ] 自动发现新资源并添加到监控

---

## User Journeys

### Journey 1: Will (DevOps Learner / Homelab Owner) - 部署新服务的喜悦

**角色背景：**
Will，网络工程师出身，正在向 DevOps 工程师转型。拥有一定的 IaC 基础，运营着自己的 Homelab 作为学习实验场。渴望通过自动化项目提升职业竞争力，同时享受"代码即基础设施"带来的掌控感。

#### 开场：周五晚上的新项目

又是一个周五晚上，Will 想为 Homelab 添加一个新的 n8n 工作流自动化服务。以前，这意味着：

- 打开 VSCode，创建 `terraform/proxmox/n8n-new.tf`
- 从其他服务的配置文件复制粘贴，小心翼翼地修改 VMID、IP、资源参数
- 更新 `variables.tf`、`outputs.tf`、inventory 配置...
- 反复检查拼写错误，担心漏掉某个配置导致 apply 失败
- 30 分钟过去了，还在编辑文件，咖啡都凉了

**情绪状态：** 疲惫、焦虑（"又要手动编辑一堆文件，千万别出错..."）

#### 转折：NetBox SSOT 系统上线后

现在，Will 打开了他精心设计的 **实施文档**（Deployment Specification）。他登录 **NetBox UI**，导航到 `Virtual Machines > Add`，根据实施文档填写表单（不到 2 分钟），点击 "Create"。

**情绪状态：** 期待、兴奋（"就这么简单？"）

#### 高潮：自动化流程启动

页面跳转到资源详情页，显示 `🔄 Provisioning`（创建中）。Will 点击链接查看 Jenkins Pipeline 实时进度：

- Router 检测平台并路由到 Proxmox Pipeline
- Terraform 从 NetBox 拉取数据并生成配置
- Plan 显示将创建的资源
- **Approval Gate** 等待人工审批
- Will 检查 Plan 无误后点击 "Approve"
- Terraform Apply 创建 LXC 容器
- Ansible 自动部署服务
- 验证通过：端口监听 + HTTP 健康检查

3 分钟后，Jenkins 显示 **✓ SUCCESS**。Will 切回 NetBox，状态显示 `✅ Active`。他打开终端 `ssh n8n-prod`，成功登录！访问 `http://192.168.1.108:5678`，n8n 界面完美显示。

**情绪状态（Aha Moment）：** 满足、自豪、解放感

**Will 的内心独白：**
> "这才是真正的自动化！从 30 分钟手动编辑文件，到不到 5 分钟点击几下就完成。更重要的是，整个流程有审批、有验证、有文档，完全符合企业级标准。这个项目，我可以自信地向面试官展示了。"

---

### Journey 2: Virtual Interviewer (Evaluator) - 技术面试展示时刻

**角色背景：**
David，某科技公司的 Senior DevOps Engineer，负责面试候选人。拥有 10 年经验，见过无数"简历上写得天花乱坠，实际项目却是 toy project"的候选人。他希望看到候选人真正理解架构设计、能解决实际问题。

#### 开场：又一个周三下午的技术面试

David 扫了一眼 Will 的简历上的关键词，心想："又是这些关键词。让我看看你是真懂还是假懂。"

**David:** "我看到你简历上写了 'Infrastructure as Code' 和 'CI/CD Pipeline'，能给我展示一下你的项目吗？别只是说理论，show me the code。"

#### 上升行动：Will 的展示策略

**Will:** "当然。让我先给你看一下架构演进的背景。"

他打开精心准备的架构图，展示 Push 模式（Terraform .tf 文件作为配置源）到 Pull 模式（NetBox 作为 SSOT）的转变。

**Will:** "这个项目的核心挑战是：如何将 NetBox 从'被动的文档工具'转变为'主动的配置源'。我实现了事件驱动架构，支持 Proxmox、ESXi 和物理服务器的异构环境。"

**David（眼神开始专注）：** "有意思。给我演示一下实际工作流程。"

#### 高潮：实时创建演示

Will 切换到屏幕共享，在 NetBox UI 中实时创建一个测试 LXC 容器（`test-demo`），演示完整的自动化流程：

1. NetBox 创建资源 → Webhook 触发
2. Jenkins Router Pipeline 路由到 Proxmox Pipeline
3. Terraform 从 NetBox API 拉取数据并动态生成配置
4. Terraform Apply 创建 LXC
5. 验证：NetBox 状态变为 Active + SSH 可用

**耗时：从点击 Create 到 SSH 可用，2 分钟 47 秒。**

#### David 的追问（关键时刻）

**David 的三个关键问题：**

1. **"为什么选择 NetBox 而不是其他 CMDB 工具？"**
   - **Will:** "我是网络工程师出身，NetBox 是专为网络和数据中心设计的 DCIM/IPAM 工具，天然支持 IP 地址管理、VLAN、设备拓扑等网络概念。API-first 设计和活跃社区生态非常适合 Infrastructure as Data 的理念。"

2. **"如果 Webhook 失败了怎么办？"**
   - **Will:** "我设计了多层容错机制：Jenkins Generic Trigger 有重试机制、手动触发兜底、监控告警（NetBox 状态标记为 `failed_provisioning`）、以及幂等性保证（Pipeline 可安全重试）。"

3. **"如何确保 NetBox 和实际基础设施状态一致？"**
   - **Will:** "采用三层同步策略：写入时同步（Pipeline 完成后回写状态）、Git 审计追踪（Terraform state 保存在 HCP Terraform Cloud）、以及未来计划的 Drift Detection（定期对比 NetBox 期望状态 vs 实际 Terraform state）。"

#### 结局：架构认可

**David（点头）：** 
> "你的架构设计很合理。我特别欣赏几点：第一，你从实际痛点出发，而不是为了用新技术而用新技术。第二，你考虑了容错和幂等性。第三，你作为网络工程师，选择 NetBox 是自然且合理的技术决策。"

**David 在笔记上写下：** ✅ **Architecture: Strong** | ✅ **Problem Solving: Solid** | ✅ **Real-world Experience**

**Will 内心（Aha Moment）：**
> "他认可了我的架构！这个项目真的帮我证明了自己的能力，不是纸上谈兵，而是端到端的实战经验。"

---

### Journey 3: Future Will (Future Maintainer) - 3个月后的安全变更

**角色背景：**
3 个月后的 Will，忙于新项目，已经记不清当初是如何配置每个服务的细节。但 Homelab 仍在运行，偶尔需要调整资源配置。他最担心的是："我会不会因为一次手动修改，导致整个环境崩溃？"

#### 开场：性能告警

某个周末早晨，Will 收到 Grafana 告警：**Caddy LXC Memory Usage > 85%**。他确认 Caddy 内存确实不够用了（当前 1GB，需要升级到 2GB）。

**内心对话：**
> "Caddy 的配置在哪里来着？万一改错了导致 Caddy 重启，网站就挂了。用新系统吧，应该更安全。"

#### 上升行动：NetBox 的"安全网"

Will 登录 NetBox，搜索 "Caddy"，进入资源详情页。他点击 "Edit"，只修改一个字段：`Memory: 1024` → `2048`，其他字段保持不变。点击 "Save" 后，系统提示："此变更将触发 Pipeline，是否继续？"

NetBox 状态变为 `🔄 Provisioning (Modification)`，Jenkins Pipeline 自动触发。

#### 高潮：人工审批的安心感

Jenkins 显示 Terraform Plan：

```
~ Update proxmox_lxc.caddy
    ~ memory: 1024 → 2048

Changes: 1 to modify, 0 to add, 0 to destroy.

⚠️ WARNING: This will modify an existing resource.
Modification Type: In-place update (no recreation)
Estimated Downtime: None (memory can be hot-added)
```

Will 仔细检查：
- ✅ 只修改 `memory` 字段，其他配置不变
- ✅ `In-place update`，不会重建容器
- ✅ 不需要重启服务

**Will 点击 "Approve"，心里踏实了：**
> "Plan 告诉我这只是增加内存，不会重启服务。即使出问题，我也可以回滚。有这个'安全网'，我敢放心操作。"

#### 结局：变更成功，信心提升

Pipeline 执行成功：Memory 更新、Caddy 服务仍在运行、HTTP 健康检查通过、变更记录提交到 Git。

NetBox 显示配置历史：
```
2026-02-04 10:23 - Will: Memory 1024MB → 2048MB [View Commit →]
2025-11-15 14:12 - Will: Initial creation
```

监控显示 Caddy Memory Usage 降至 45%，告警解除。

**Will 内心（Aha Moment）：**
> "太棒了！即使 3 个月后忘记了配置细节，系统也能帮我安全地完成变更。Plan 预览、人工审批、自动验证、Git 记录，这才是企业级的变更管理流程。我再也不用担心'一次手动操作毁掉整个环境'了。"

---

### Journey Requirements Summary

通过三个用户旅程，我们识别出以下核心能力需求：

#### 核心工作流能力
1. **NetBox 数据建模** - Custom Fields 定义（platform, automation_level, ansible_groups, playbook_name）
2. **Webhook 触发 + Router** - 事件驱动路由到正确的 Pipeline
3. **Terraform Dynamic Config** - 从 NetBox API 动态生成资源配置
4. **Multi-Platform 支持** - Proxmox / ESXi / Physical 异构环境路由

#### 审批与验证
5. **人工审批 Gate** - 基于 `automation_level` 的条件审批
6. **Plan 预览机制** - 变更前强制显示 Terraform plan
7. **自动化验证** - SSH 可用性 + 服务端口 + HTTP 健康检查

#### 状态管理
8. **状态回写** - Pipeline 完成后更新 NetBox 状态（active / failed_provisioning）
9. **配置历史追踪** - NetBox 和 Git 双重记录变更历史
10. **Ansible Inventory 同步** - Terraform apply 后自动刷新 inventory

#### 容错与恢复
11. **Webhook 失败处理** - 自动重试 + 手动触发兜底
12. **幂等性保证** - Pipeline 可安全重试
13. **回滚能力** - Git 记录支持快速恢复
14. **Drift Detection** - 定期对比 NetBox vs Terraform state（未来）

#### 文档与展示
15. **架构图** - 可视化 Push → Pull 演进
16. **ADR 文档** - 8 个架构决策记录
17. **实时演示能力** - 系统稳定可靠，支持面试演示

---

## Technical Architecture Requirements

### Project-Type Overview

本项目是一个 **Infrastructure Automation Platform**，采用事件驱动架构，实现从 NetBox（DCIM/IPAM）到多平台基础设施的自动化配置管理。作为 Developer Tool 类型，它提供了一套完整的工具链和工作流，使基础设施运维人员能够通过声明式的数据模型（NetBox）驱动基础设施的创建、配置和管理。

**核心价值主张：**
- **Infrastructure as Data**：将基础设施定义从代码（.tf 文件）转移到数据（NetBox 记录）
- **Event-Driven Automation**：通过 Webhook 触发自动化流程，减少人工干预
- **Multi-Platform Abstraction**：统一管理 Proxmox、ESXi 和物理服务器的异构环境
- **Self-Service Infrastructure**：通过 NetBox UI 自助创建资源，降低技术门槛

### Technical Architecture Considerations

#### 1. Platform Support Matrix

| Platform | Type | Provisioning | Configuration | Status |
|----------|------|--------------|---------------|--------|
| **Proxmox VE** | Virtualization | ✅ Terraform (telmate/proxmox) | ✅ Ansible | MVP |
| **VMware ESXi** | Virtualization | ✅ Terraform (vmware/vsphere) | ✅ Ansible | Post-MVP |
| **Physical Servers** | Bare Metal | ❌ N/A | ✅ Ansible | MVP |
| **Oracle Cloud** | Public Cloud | 🔮 Future | 🔮 Future | Vision |

**Platform-Specific Considerations:**

**Proxmox VE:**
- 支持 QEMU VM 和 LXC 容器两种资源类型
- 需要 Proxmox API Token（非 root password）
- 支持 Cloud-Init 注入（VM）和模板克隆
- 资源 ID（VMID）需要全局唯一（100-999）

**VMware ESXi:**
- 仅支持 QEMU VM（无容器支持）
- 需要 vSphere API 凭据
- 依赖 Datastore 和 Network 预配置
- 资源创建速度较 Proxmox 慢（需要考虑超时设置）

**Physical Servers:**
- 跳过 Terraform Provisioning 阶段
- 仅通过 NetBox 更新 Ansible Inventory
- 需要预先配置 SSH 密钥和网络连接
- 支持配置管理（Common / Docker / Tailscale 等 roles）

#### 2. System Configuration Requirements

本系统的配置分为五个层次，需要在实施阶段依次配置：

**Layer 1: NetBox Configuration（数据模型层）**

| Configuration Item | Type | Required | Description |
|--------------------|------|----------|-------------|
| `infrastructure_platform` | Custom Field (Selection) | ✅ | 选项：`proxmox` / `esxi` / `physical`，决定路由目标 |
| `automation_level` | Custom Field (Selection) | ✅ | 选项：`fully_automated` / `requires_approval` / `manual_only` |
| `proxmox_node` | Custom Field (Selection) | Conditional | Proxmox 节点选择（pve0/pve1/pve2），仅当 platform=proxmox 时必填 |
| `proxmox_vmid` | Custom Field (Integer) | Conditional | VM/LXC ID（100-999），必须全局唯一 |
| `esxi_host` | Custom Field (Object) | Conditional | ESXi 主机引用，仅当 platform=esxi 时必填 |
| `esxi_datastore` | Custom Field (Selection) | Conditional | Datastore 选择，仅当 platform=esxi 时必填 |
| `ansible_groups` | Custom Field (Multiple Selection) | Optional | Ansible 组列表，用于自动分组 |
| `playbook_name` | Custom Field (String) | Optional | 关联的 Ansible Playbook（默认：auto-detect） |
| Webhook Configuration | Webhook | ✅ | URL: `https://jenkins.willfan.me/generic-webhook-trigger/invoke?token=netbox-webhook`<br/>Events: `created`, `updated`<br/>Content-types: `dcim.virtualmachine`, `dcim.device` |

**Layer 2: Jenkins Configuration（编排层）**

| Configuration Item | Type | Required | Description |
|--------------------|------|----------|-------------|
| Generic Webhook Trigger Plugin | Jenkins Plugin | ✅ | 接收 NetBox Webhook 并解析 Payload |
| `ansible-vault-password` | Secret Text | ✅ | Ansible Vault 解密密码 |
| `terraform-cloud-token` | Secret Text | ✅ | HCP Terraform Cloud API Token |
| `netbox-api-token` | Secret Text | ✅ | NetBox API Token（用于读取数据） |
| Router Pipeline | Jenkinsfile | ✅ | 路径：`Jenkinsfile-webhook-router`<br/>功能：解析 `infrastructure_platform` 并路由 |
| Proxmox Provisioning Pipeline | Jenkinsfile | ✅ | 路径：`Jenkinsfile-proxmox-provisioning`<br/>功能：Terraform + Ansible 端到端部署 |
| ESXi Provisioning Pipeline | Jenkinsfile | Optional | 路径：`Jenkinsfile-esxi-provisioning`<br/>功能：ESXi 平台部署（Post-MVP） |
| Physical Device Sync Pipeline | Jenkinsfile | ✅ | 路径：`Jenkinsfile-physical-device-sync`<br/>功能：仅 Inventory 同步，跳过 Terraform |

**Layer 3: Terraform Configuration（基础设施层）**

| Configuration Item | Location | Required | Description |
|--------------------|----------|----------|-------------|
| HCP Terraform Cloud Backend | `versions.tf` | ✅ | Organization: `homelab-roseville`<br/>Workspaces: 按平台隔离 |
| Proxmox Provider | `terraform/proxmox/provider.tf` | ✅ | API Endpoint, Token, TLS 设置 |
| ESXi Provider | `terraform/esxi/provider.tf` | Optional | vSphere API Endpoint, Credentials |
| NetBox Data Source | `terraform/proxmox/netbox-data.tf` | ✅ | 使用 `terraform-provider-netbox`<br/>动态查询 Virtual Machines |
| Dynamic Resource Generation | `terraform/proxmox/generated.tf` | ✅ | 使用 `for_each` 循环动态创建资源<br/>基于 NetBox data source 输出 |
| Secrets Injection | `scripts/get-secrets.sh` | ✅ | 从 Ansible Vault 提取密钥<br/>生成 `secrets.auto.tfvars`（gitignored） |

**Layer 4: Ansible Configuration（配置管理层）**

| Configuration Item | Location | Required | Description |
|--------------------|----------|----------|-------------|
| Vault Password File | `ansible/.vault_pass` | ✅ | Vault 解密密码（gitignored）<br/>由 Jenkins 动态注入 |
| Dynamic Inventory Plugin | `ansible/inventory/terraform.yml` | ✅ | 使用 `cloud.terraform` collection<br/>从 Terraform state 生成 inventory |
| NetBox Dynamic Inventory | `ansible/inventory/netbox.yml` | Optional | 直接从 NetBox API 生成 inventory（未来） |
| Ansible Galaxy Collections | `ansible/requirements.yml` | ✅ | `community.general`, `community.docker`, `cloud.terraform`, `netbox.netbox` |
| Playbook Mapping | Convention-based | ✅ | Custom Field `playbook_name` → `playbooks/deploy-<name>.yml`<br/>如未指定，根据 `ansible_groups` 自动推导 |

**Layer 5: Integration Configuration（集成层）**

| Integration | Configuration | Required | Description |
|-------------|---------------|----------|-------------|
| Git Repository | `origin` remote | ✅ | GitHub repository，用于审计追踪<br/>Pipeline 完成后自动 commit |
| Notion Database | API Token + Database ID | Optional | 用于同步资源文档（`sync-to-notion.py`） |
| Monitoring (Grafana) | Datasource | Future | 从 NetBox 自动发现监控 targets |
| Notification (Telegram/Slack) | Bot Token + Chat ID | Future | Pipeline 失败时发送告警 |

**配置依赖关系：**
```
Layer 1 (NetBox) ← 必须先完成，定义数据模型
    ↓
Layer 2 (Jenkins) ← 配置 Webhook 和 Pipelines
    ↓
Layer 3 (Terraform) ← 读取 NetBox，创建资源
    ↓
Layer 4 (Ansible) ← 配置已创建的资源
    ↓
Layer 5 (Integrations) ← 可选的外部集成
```

#### 3. API Surface & Integration Points

**Inbound APIs（系统接收的调用）：**

| API | Provider | Purpose | Authentication |
|-----|----------|---------|----------------|
| Generic Webhook Trigger | Jenkins | 接收 NetBox Webhook | Token in URL |
| Manual Trigger | Jenkins | 人工触发 Pipeline（Webhook 失败时兜底） | Jenkins Auth |

**Outbound APIs（系统调用的外部 API）：**

| API | Provider | Purpose | Authentication | Usage |
|-----|----------|---------|----------------|-------|
| NetBox API | NetBox | 读取 Virtual Machines / Devices 数据 | API Token | Terraform data source + Router 解析 |
| Proxmox API | Proxmox VE | 创建/修改/删除 VM/LXC | API Token | Terraform provider |
| ESXi API (vSphere) | VMware | 创建/修改/删除 VM | Username/Password | Terraform provider |
| HCP Terraform Cloud API | HashiCorp | 读写 Terraform state | API Token | Backend 配置 |
| Git API (GitHub) | GitHub | Commit 审计记录 | SSH Key | Pipeline post 阶段 |
| Notion API | Notion | 同步资源文档 | Integration Token | 可选的 Sync Pipeline |

**API 调用频率与限制：**
- **NetBox API**: 每次 Pipeline 触发时调用 1 次（读取单个资源）
- **Proxmox/ESXi API**: 每次资源创建时调用 5-10 次（创建、配置、验证）
- **HCP Terraform Cloud**: 每次 Plan/Apply 时调用（无频率限制）
- **Notion API**: 可选，每次成功部署后调用 1 次

**错误处理策略：**
- **API 调用失败**: Pipeline 标记为 FAILED，NetBox 状态更新为 `failed_provisioning`
- **Webhook 丢失**: 依赖手动触发兜底（通过 Jenkins UI 传入 Resource ID）
- **API 超时**: Terraform 默认超时 30 分钟，可通过 `timeouts` block 调整

#### 4. Documentation Requirements

为支持系统的部署、运维和展示，需要以下文档（优先级从高到低）：

| Document Type | Format | Priority | Target Audience | Purpose |
|---------------|--------|----------|-----------------|---------|
| **架构图** | Excalidraw / Mermaid | 🔴 High | 面试官、技术团队 | 可视化展示 Push → Pull 架构演进 |
| **ADR 文档** | Markdown (8 个) | 🔴 High | 技术审查者 | 记录关键架构决策及理由（已在 frontmatter 中定义） |
| **实施文档模板** | Markdown Template | 🔴 High | 运维人员（自己） | 标准化服务部署规范（NetBox 资源定义 + Ansible 配置） |
| **快速开始指南** | README.md | 🟡 Medium | 学习者、协作者 | 5-10 分钟了解如何使用系统 |
| **故障排查指南** | Markdown | 🟡 Medium | 运维人员（自己） | Webhook 失败、Pipeline 失败、State 不一致的处理流程 |
| **迁移指南** | Markdown | 🟡 Medium | 自己（实施阶段） | 如何将现有静态 .tf 迁移到 NetBox Pull 模式 |
| **NetBox 字段参考** | Markdown Table | 🟢 Low | 新用户 | Custom Fields 的含义、选项、约束 |
| **Pipeline 流程图** | Excalidraw / Mermaid | 🟢 Low | 技术团队 | 详细的 Router → Platform Pipeline 流程 |

**文档位置规范：**
- **架构文档**: `docs/designs/netbox-ssot-architecture.md`
- **ADR**: `docs/designs/adr-{number}-{title}.md`（已在 PRD frontmatter 中定义）
- **实施模板**: `docs/templates/service-deployment-spec.md`
- **故障排查**: `docs/troubleshooting/netbox-pipeline-issues.md`
- **快速开始**: `README.md`（项目根目录）

**文档生成时机：**
- **MVP 阶段**: 架构图、ADR、实施模板、故障排查指南
- **Post-MVP**: 迁移指南、字段参考、Pipeline 流程图

#### 5. Installation & Quick Start

**系统依赖（Prerequisites）：**
- ✅ NetBox 实例（已部署，版本 >= 3.0）
- ✅ Jenkins 实例（LXC 容器，已安装 Generic Webhook Trigger Plugin）
- ✅ Terraform CLI >= 1.14（安装在 Jenkins 上）
- ✅ Ansible >= 2.16（安装在 Jenkins 上，via pipx）
- ✅ Git repository（GitHub，用于审计追踪）
- ✅ HCP Terraform Cloud 账号（免费 tier 即可）
- ✅ Proxmox VE 集群（3 节点：pve0, pve1, pve2）
- ⭐ VMware ESXi 主机（可选，Post-MVP）

**快速开始流程（5 步上手）：**

```markdown
## Quick Start

### 1. 配置 NetBox 数据模型（15 分钟）
# 登录 NetBox Admin UI
# Customization > Custom Fields > Add
# 按照 Layer 1 配置表创建 Custom Fields

### 2. 配置 Jenkins Credentials（5 分钟）
# Jenkins > Manage Jenkins > Credentials
# 添加以下 Secrets：
# - ansible-vault-password
# - terraform-cloud-token
# - netbox-api-token

### 3. 部署 Router Pipeline（10 分钟）
# 在 Jenkins 创建新的 Pipeline Job
# Pipeline script from SCM: Jenkinsfile-webhook-router
# 配置 Generic Webhook Trigger

### 4. 配置 NetBox Webhook（5 分钟）
# NetBox > System > Webhooks > Add
# URL: https://jenkins.willfan.me/generic-webhook-trigger/invoke?token=netbox-webhook
# Content Types: dcim.virtualmachine, dcim.device
# Events: created, updated

### 5. 测试端到端流程（10 分钟）
# 在 NetBox 创建测试 LXC 容器
# 观察 Jenkins Pipeline 自动触发
# 验证资源创建成功
```

**预计总时间**: 45 分钟（首次配置）

---

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Experience MVP（体验型 MVP）

本项目采用体验型 MVP 策略，重点不是堆砌功能清单，而是提供**完整的端到端用户体验**。MVP 的核心目标是：
1. 证明 NetBox SSOT 架构的可行性（从数据驱动到基础设施创建的完整闭环）
2. 提供可向面试官展示的实物（完整的 Portfolio 项目）
3. 实际解决运维痛点（至少 3 个真实服务迁移到新系统）

**MVP Philosophy:**
- ✅ **完整的工作流体验**：用户能够在 NetBox 创建资源 → 自动触发 Pipeline → Terraform 创建 → Ansible 配置 → SSH 可用
- ✅ **真实的业务价值**：迁移真实的服务（Anki, Caddy, n8n），而非 Demo 项目
- ✅ **架构可扩展性**：MVP 架构能够平滑扩展到 ESXi、物理服务器等其他平台
- ⚠️ **容错可接受**：MVP 阶段允许 Pipeline 失败，手动排查修复即可（不需要完美的自动化容错）

**Resource Requirements:**
- **人员**：1 人（你自己）
- **时间**：1 个月（4 周）
- **基础设施**：已有的 Homelab 环境（Proxmox 集群、NetBox、Jenkins）
- **技能要求**：Terraform + Ansible + Jenkins Pipeline + NetBox API

### MVP Feature Set (Phase 1 - 1 个月内)

**Core User Journeys Supported:**

✅ **Journey 1: 部署新服务** - 完整支持  
✅ **Journey 3: 安全变更管理** - 部分支持  
⚠️ **Journey 2: 技术面试展示** - 依赖 MVP 完成

**Must-Have Capabilities:**

详见 "Product Scope" 部分的 MVP 定义（Week 1-4 的 5 个 Phase）。

**MVP Success Criteria:**
- ✅ 端到端流程完整打通（NetBox → Router → Proxmox Pipeline → Terraform → Ansible → 验证）
- ✅ 至少 3 个 LXC 服务成功迁移到 NetBox Pull 模式
- ✅ Webhook 触发成功率 > 80%（MVP 阶段可接受较低成功率）
- ✅ 人工审批流程验证通过
- ✅ 配置历史记录在 Git 中可追溯

### Post-MVP Features

#### Phase 2: Growth Features (1-2 个月)

**Multi-Platform 扩展：**
- ESXi Provisioning Pipeline
- 至少 1 个 ESXi VM 端到端验证

**网络自动化：**
- IP 自动分配（从 NetBox Prefix 池）
- VMID 冲突检测

**运维增强：**
- Pipeline 失败通知（Telegram/Slack）
- NetBox 状态变更历史记录

#### Phase 3: Vision Features (3-6 个月)

**完整迁移：**
- 所有服务迁移到 NetBox Pull 模式
- 删除所有静态 `.tf` 文件

**高级自动化：**
- Drift Detection（定期对比 NetBox vs Terraform state）
- GitOps 层（自动生成 Git PR）

**可视化增强：**
- 网络拓扑可视化
- Grafana Dashboard（Pipeline 成功率监控）

### Phase Transition Criteria

**从 MVP 到 Phase 2：**
- ✅ 3 个 LXC 服务稳定运行 > 2 周
- ✅ Webhook 触发成功率 > 90%
- ✅ 至少完成 1 次面试展示
- ✅ 架构图和 ADR 文档完成

**从 Phase 2 到 Phase 3：**
- ✅ ESXi 平台至少有 1 个生产 VM
- ✅ IP 自动分配功能稳定运行
- ✅ Pipeline 失败率 < 5%

### Risk Mitigation Strategy

#### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **terraform-provider-netbox 不稳定** | 🔴 High | **Plan A**: Week 1 POC 验证<br/>**Plan B**: Python 脚本生成静态 `.tf`<br/>**Fallback**: 保留手动编写能力 |
| **Webhook 触发失败率高** | 🟡 Medium | Generic Trigger 重试 + 手动触发兜底 |
| **Terraform Apply 失败率高** | 🟡 Medium | 人工审批 Gate + 幂等性保证 |
| **NetBox 数据模型设计不当** | 🟠 Medium-High | Week 1 测试数据验证 + Custom Fields 灵活扩展 |

**最关键技术风险：** terraform-provider-netbox 成熟度

#### Resource Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **时间不足** | 🟡 Medium | 给自己留 2 周缓冲 + 灵活的 MVP 定义 |
| **学习曲线陡峭** | 🟢 Low | Week 1 手动熟悉 NetBox UI 和工作流 |
| **现有服务迁移出现问题** | 🟠 Medium | 保留静态 `.tf` 备份 + 逐个迁移 |

**最关键资源风险：** 时间管理

---

## Functional Requirements

以下功能性需求定义了系统必须具备的能力（WHAT），是所有后续开发工作的能力契约。每个 FR 都是可测试的能力声明，实现方式（HOW）可以灵活选择。

---

### Configuration Management（配置管理）

- **FR1**: DevOps Engineer 可以在 NetBox 中定义新虚拟机的配置（名称、CPU、内存、磁盘、网络）
- **FR2**: DevOps Engineer 可以在 NetBox 中为虚拟机分配 IP 地址并关联到接口
- **FR3**: DevOps Engineer 可以使用 NetBox Custom Fields 定义基础设施平台类型（Proxmox/ESXi/Physical）
- **FR4**: DevOps Engineer 可以使用 NetBox Custom Fields 定义 Ansible 角色和变量
- **FR5**: DevOps Engineer 可以在 NetBox 中标记虚拟机为"Planned"状态以触发自动化流程
- **FR6**: System 可以从 NetBox 通过 REST API 获取所有虚拟机配置数据
- **FR7**: DevOps Engineer 可以在 NetBox 中修改现有虚拟机的配置（内存、CPU 等）
- **FR8**: System 可以识别 NetBox 中配置变更并触发相应的自动化流程

### Infrastructure Provisioning（基础设施供给）

- **FR9**: System 可以通过 Terraform 从 NetBox 数据源拉取虚拟机配置
- **FR10**: System 可以使用 Terraform 在 Proxmox VE 上创建新虚拟机
- **FR11**: System 可以使用 Terraform 在 VMware ESXi 上创建新虚拟机
- **FR12**: System 可以通过 Terraform 管理虚拟机的生命周期（创建、修改、删除）
- **FR13**: System 可以在 Terraform 执行成功后生成 Ansible inventory host 资源
- **FR14**: System 可以将 Terraform 执行状态反馈回 NetBox（更新虚拟机状态）
- **FR15**: DevOps Engineer 可以通过 NetBox 配置变更触发 Terraform plan 操作
- **FR16**: DevOps Engineer 可以手动批准 Terraform apply 操作（Manual Gate）

### Service Deployment（服务部署）

- **FR17**: System 可以从 Terraform state 生成 Ansible dynamic inventory
- **FR18**: System 可以使用 Ansible 在新创建的虚拟机上部署应用服务
- **FR19**: System 可以使用 Ansible 对现有虚拟机进行配置变更
- **FR20**: System 可以从 NetBox Custom Fields 获取 Ansible 角色和变量配置
- **FR21**: System 可以在 Ansible 部署后执行健康检查验证（verify tagged tasks）
- **FR22**: System 可以将 Ansible 部署结果（成功/失败）反馈回 NetBox
- **FR23**: DevOps Engineer 可以通过 NetBox 配置 Ansible playbook 参数（tags, extra-vars）

### Automation Orchestration（自动化编排）

- **FR24**: System 可以通过 Jenkins Pipeline 编排 Terraform 和 Ansible 的执行顺序
- **FR25**: System 可以接收 NetBox Webhook 事件并触发 Jenkins Pipeline
- **FR26**: System 可以接收 Git 仓库 push 事件并触发 Jenkins Pipeline
- **FR27**: DevOps Engineer 可以在 Jenkins 界面查看 Pipeline 执行日志和状态
- **FR28**: DevOps Engineer 可以在 Jenkins Pipeline 中手动批准 Terraform apply 步骤
- **FR29**: System 可以在 Jenkins Pipeline 失败时发送通知（Slack/Email）
- **FR30**: DevOps Engineer 可以手动重新运行失败的 Jenkins Pipeline

### Platform Routing（平台路由）

- **FR31**: System 可以根据 NetBox Custom Field "Platform Type" 路由到正确的 Terraform 目录（proxmox/esxi）
- **FR32**: System 可以识别标记为 "Physical" 的服务器并跳过 Terraform 步骤
- **FR33**: System 可以为 Physical 服务器直接生成 Ansible inventory（无 Terraform 步骤）
- **FR34**: System 可以为不同平台类型使用不同的 Terraform module（proxmox-vm/esxi-vm）
- **FR35**: DevOps Engineer 可以在 NetBox 中查看虚拟机的路由决策结果（目标平台）

### Error Handling & Recovery（错误处理与恢复）

- **FR36**: System 可以在 Terraform 执行失败时将虚拟机标记为 "Failed" 状态
- **FR37**: System 可以在 Ansible 执行失败时将虚拟机标记为 "Degraded" 状态
- **FR38**: System 可以对失败的虚拟机自动重试 Terraform/Ansible 操作（最多 3 次）
- **FR39**: DevOps Engineer 可以在 NetBox 中手动重置虚拟机状态以触发重试
- **FR40**: System 可以记录错误日志并关联到 NetBox 虚拟机对象（Comments/Notes）
- **FR41**: System 可以在连续失败后发送告警通知并暂停自动重试
- **FR42**: DevOps Engineer 可以在 Jenkins 中查看详细的错误堆栈和失败原因

### Observability & Tracking（可观测性与追踪）

- **FR43**: DevOps Engineer 可以在 NetBox Change Log 中查看虚拟机配置的所有历史变更
- **FR44**: DevOps Engineer 可以在 Jenkins 中查看与特定虚拟机相关的所有 Pipeline 执行历史
- **FR45**: System 可以记录每次 Terraform apply 的变更内容（plan diff）
- **FR46**: System 可以记录每次 Ansible playbook 执行的变更内容（--diff 输出）
- **FR47**: DevOps Engineer 可以通过 NetBox 查看虚拟机的当前运行状态（Active/Planned/Failed）
- **FR48**: DevOps Engineer 可以追溯特定配置变更的触发来源（Webhook/Git commit）
- **FR49**: System 可以生成基础设施变更的审计日志（谁、何时、改了什么）

---

## Non-Functional Requirements

以下非功能性需求定义了系统运行的质量属性（HOW WELL）。所有 NFR 都是可测量的，具有明确的验证标准。仅包含与本项目实际相关的质量维度。

---

### Performance（性能）

**Webhook 触发性能：**
- **NFR-P1**: NetBox Webhook 触发到 Jenkins Pipeline 启动的延迟 < 5 秒
- **NFR-P2**: Router Pipeline 路由决策时间（解析 Payload + 触发目标 Pipeline）< 10 秒

**资源创建性能：**
- **NFR-P3**: LXC 容器从 Webhook 触发到 SSH 可用的总时间 < 3 分钟
- **NFR-P4**: QEMU VM 从 Webhook 触发到 SSH 可用的总时间 < 5 分钟（包括 Cloud-Init）
- **NFR-P5**: Physical Server Inventory 更新时间 < 1 分钟（仅 Inventory 同步，无 Terraform）

**API 查询性能：**
- **NFR-P6**: Terraform 从 NetBox data source 查询单个资源的时间 < 30 秒
- **NFR-P7**: Terraform Plan 生成时间（NetBox 数据查询 + 动态配置生成）< 30 秒

**用户感知性能目标：**
- **NFR-P8**: 从 NetBox UI "Create" 点击到状态变为 "Provisioning" 的反馈时间 < 10 秒（用户能看到进度反馈）

**性能退化容忍度：**
- **NFR-P9**: 在 10x 资源增长（从 10 个资源到 100 个资源）时，Pipeline 执行时间增长 < 20%

### Security（安全）

**凭据管理：**
- **NFR-S1**: 所有敏感凭据（Proxmox API Token、Ansible Vault 密码、NetBox API Token）必须通过 Ansible Vault 或 Jenkins Secrets 加密存储，严禁明文存储
- **NFR-S2**: `secrets.auto.tfvars` 必须在 `.gitignore` 中排除，严禁提交到 Git 仓库
- **NFR-S3**: API Tokens 必须定期轮换（建议周期：90 天）

**传输加密：**
- **NFR-S4**: NetBox Webhook 到 Jenkins 的通信必须通过 HTTPS（Cloudflare Tunnel）加密
- **NFR-S5**: Proxmox/ESXi API 调用必须使用 TLS 加密（拒绝 `tls_insecure = false`）

**访问控制：**
- **NFR-S6**: NetBox 必须使用 RBAC（Role-Based Access Control），限制 Webhook 触发和 API 访问权限
- **NFR-S7**: Jenkins Pipeline 的 Terraform apply 步骤必须强制人工审批（当 `automation_level == requires_approval` 时）
- **NFR-S8**: SSH 密钥访问必须使用非对称加密（Ed25519 或 RSA 4096 位），禁止密码认证

**审计追踪：**
- **NFR-S9**: 所有 Terraform state 变更必须提交到 Git 仓库，保留审计记录（谁、何时、改了什么）
- **NFR-S10**: NetBox Change Log 必须记录所有配置变更历史（保留至少 90 天）

### Reliability（可靠性）

**系统可用性：**
- **NFR-R1**: Webhook 触发成功率 > 95%（MVP 阶段目标 > 80%）
- **NFR-R2**: Terraform Apply 成功率 > 90%（无需人工修复）
- **NFR-R3**: Pipeline 失败时，必须在 NetBox 中自动更新虚拟机状态为 `failed_provisioning`

**幂等性保证：**
- **NFR-R4**: 重复触发相同 Webhook 不会创建重复资源（通过 Terraform state 检测已存在资源）
- **NFR-R5**: Pipeline 失败后可以安全重试，不会导致状态不一致（状态机支持 `failed_provisioning` → `provisioning` 转换）
- **NFR-R6**: 手动修改的资源不会被 Pipeline 覆盖（通过 `lifecycle { ignore_changes = [...] }` 保护关键字段）

**容错机制：**
- **NFR-R7**: Webhook 触发失败时，必须提供手动触发兜底机制（通过 Jenkins UI 传入 Resource ID）
- **NFR-R8**: API 调用超时设置必须合理（Terraform 默认 30 分钟，可通过 `timeouts` block 调整）
- **NFR-R9**: 失败的虚拟机可以自动重试最多 3 次，连续失败后暂停并发送告警

**数据一致性：**
- **NFR-R10**: NetBox 配置与 Terraform state 必须最终一致（允许短暂延迟，但 Pipeline 完成后必须同步）
- **NFR-R11**: Ansible Inventory 必须在 Terraform Apply 成功后 30 秒内自动刷新

### Scalability（可扩展性）

**资源增长规划：**
- **NFR-SC1**: 系统必须支持至少 100 个资源（Proxmox VMID 范围 100-999，理论上限 900 个）
- **NFR-SC2**: 并发 Pipeline 执行数量至少支持 2-3 个（受 Jenkins executor 限制，可通过增加 executor 扩展）

**API 调用限制：**
- **NFR-SC3**: NetBox API 调用频率 < 100 req/min（避免触发 Rate Limiting）
- **NFR-SC4**: Proxmox API 调用必须支持超时重试机制（避免单次失败导致整个 Pipeline 失败）

**增长路径支持：**
- **NFR-SC5**: 架构必须支持新平台扩展（如 Oracle Cloud）时，仅需添加新 Pipeline，Router 逻辑无需修改
- **NFR-SC6**: NetBox Custom Fields 变更不会破坏现有 Terraform 代码（向后兼容性）

**性能退化控制：**
- **NFR-SC7**: 从 10 个资源增长到 50 个资源时，Terraform Plan 时间增长 < 50%
- **NFR-SC8**: NetBox data source 查询必须支持分页或过滤，避免全量查询导致性能下降

### Integration（集成）

**API 集成可靠性：**
- **NFR-I1**: NetBox API 集成必须支持 API Token 认证，避免使用用户名/密码
- **NFR-I2**: Terraform provider 版本必须锁定（`terraform-provider-netbox >= 3.0`），避免自动升级导致兼容性问题
- **NFR-I3**: Jenkins Generic Webhook Trigger 必须支持 Payload 验证（确保请求来自 NetBox）

**数据格式兼容性：**
- **NFR-I4**: NetBox Custom Fields 必须使用标准数据类型（Selection、Integer、Text、Object），避免自定义格式
- **NFR-I5**: Terraform 输出的 Ansible Inventory 必须符合 Ansible Dynamic Inventory 规范（JSON 格式）

**版本兼容性：**
- **NFR-I6**: 系统必须支持 NetBox 3.x 及以上版本（当前 Homelab 版本）
- **NFR-I7**: Terraform 版本锁定在 >= 1.14（与 HCP Terraform Cloud 兼容）
- **NFR-I8**: Ansible 版本锁定在 >= 2.16（支持 `cloud.terraform` collection）

**失败恢复：**
- **NFR-I9**: 外部 API 调用失败时，Pipeline 必须记录详细错误日志（HTTP 状态码、响应 Body）
- **NFR-I10**: Git Push 失败不会导致整个 Pipeline 失败（允许手动补推）

### Maintainability（可维护性）

**代码组织：**
- **NFR-M1**: Terraform 代码必须按平台隔离目录（`terraform/proxmox/`, `terraform/esxi/`），避免单一目录爆炸半径
- **NFR-M2**: Ansible Roles 必须按服务划分（`roles/netbox/`, `roles/caddy/`），每个 Role 独立可测试
- **NFR-M3**: Jenkinsfiles 必须按功能命名（`Jenkinsfile-router`, `Jenkinsfile-proxmox-provisioning`），清晰表达用途

**文档要求：**
- **NFR-M4**: 所有架构决策必须记录在 ADR 文档中（已定义 8 个 ADR）
- **NFR-M5**: 每个服务部署必须有对应的实施文档（Deployment Specification）
- **NFR-M6**: README.md 必须提供 5-10 分钟的快速开始指南（Quick Start）

**测试覆盖：**
- **NFR-M7**: Terraform 代码必须通过 `terraform validate` 和 `terraform fmt -check` 验证
- **NFR-M8**: Ansible Playbooks 必须通过 `ansible-playbook --syntax-check` 和 `ansible-lint` 验证
- **NFR-M9**: Pipeline 必须支持手动触发测试（使用测试 Resource ID）

**可观测性：**
- **NFR-M10**: Jenkins 必须保留最近 10 个构建历史（用于故障排查）
- **NFR-M11**: NetBox 状态追踪必须清晰区分 `active` / `provisioning` / `failed_provisioning` 状态
- **NFR-M12**: Git commit 必须包含有意义的 commit message（遵循 Conventional Commits 规范）

**架构演进：**
- **NFR-M13**: 系统必须支持平滑迁移（从静态 `.tf` 到 NetBox Pull 模式），允许两种模式并存
- **NFR-M14**: 新增 Custom Fields 不会破坏现有 Pipeline（向后兼容）
