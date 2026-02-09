# BMAD + OpenCode Subagent 集成指南

> 文档创建日期：2026-02-07  
> 作者：Will + AI Assistant  
> 用途：说明如何在 BMAD Method 工作流中集成和使用 OpenCode 专业技术 Subagents

## 🎯 集成架构概览

### 两层 Agent 架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: BMAD Agents（工作流编排层）                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│  角色：PM (John), Architect (Winston), Dev (Amelia), QA (Quinn) │
│  职责：需求分析、架构设计、开发编排、质量保证                        │
│  调用方式：BMAD workflows（如 /bmad-bmm-create-prd）              │
│  存放位置：_bmad/bmm/agents/                                      │
└─────────────────────────────────────────────────────────────────┘
                             │ delegates to
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: OpenCode Subagents（技术执行层）                        │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│  角色：terraform-engineer, devops-engineer, code-reviewer        │
│  职责：Terraform 实现、Ansible 配置、代码质量审查                   │
│  调用方式：@terraform-engineer（手动或自动）                       │
│  存放位置：.opencode/agents/                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 关键区别

| 维度 | BMAD Agents | OpenCode Subagents |
|------|-------------|-------------------|
| **抽象层次** | 工作流/流程 | 技术实现 |
| **知识领域** | 软件开发方法论 | 特定技术栈 |
| **生命周期** | 跨阶段（Planning → Implementation） | 单一任务 |
| **调用方式** | 工作流命令 | @ 提及或自动 |
| **示例任务** | "创建 PRD"、"设计架构" | "写 Terraform 模块"、"审查 Ansible 代码" |

## 📦 已安装的 OpenCode Subagents

### 1. terraform-engineer

**文件路径**：`.opencode/agents/terraform-engineer.md`

**用途**：
- Terraform 模块设计和实现
- State 管理和 backend 配置
- Provider 集成（Proxmox, ESXi, NetBox, OCI）
- ADR 合规性（ADR-001, ADR-002, ADR-008）
- snake_case/kebab-case 命名规范执行

**调用场景**：
- Epic 3（Proxmox 资源自动化供给）的所有 Stories
- terraform-provider-netbox POC（Epic 3 Story 3.1）
- Terraform 代码重构和优化

**调用示例**：
```
@terraform-engineer 分析 terraform/proxmox/ 目录结构，建议模块化改进方案
@terraform-engineer 创建 terraform/proxmox/netbox.tf，使用 terraform-provider-netbox
```

### 2. devops-engineer

**文件路径**：`.opencode/agents/devops-engineer.md`

**用途**：
- Ansible playbook 和 role 开发
- 幂等性和 Deploy+Verify 模式执行
- Ansible Vault 架构（vault_ 前缀、间接引用）
- 变量参数化判断（避免过度抽象）
- CI/CD 流程设计

**调用场景**：
- Epic 4（Ansible 服务部署与配置管理）的所有 Stories
- Epic 5（Pipeline 编排与自动化工作流）
- 新服务部署 playbook 创建

**调用示例**：
```
@devops-engineer 创建 ansible/playbooks/deploy-homepage.yml
@devops-engineer 审查 ansible/roles/pbs-client/ 的幂等性
```

### 3. code-reviewer

**文件路径**：`.opencode/agents/code-reviewer.md`

**用途**：
- 强制执行 AGENTS.md 规范
- 检查 Terraform 命名规范（snake_case 资源，kebab-case 文件）
- 检查 Ansible 命名规范（snake_case 变量，kebab-case roles/playbooks）
- 验证 Ansible 幂等性和两段式结构
- 检查过度参数化问题
- Ansible Vault 架构合规性

**调用场景**：
- Story 完成前的代码审查
- Pull Request 创建前的质量检查
- 重构后的规范验证

**调用示例**：
```
@code-reviewer 审查 terraform/proxmox/netbox.tf，检查 AGENTS.md 合规性
@code-reviewer 验证 ansible/playbooks/deploy-netbox.yml 是否符合项目规范
```

## 🔧 集成方式

### 方式 1：Dev Agent 主动委派（推荐）

**使用增强版 Dev Agent**：
- 文件：`_bmad/bmm/agents/dev-enhanced.md`
- 在 Step 3.1 中声明了对 OpenCode subagents 的认知
- 在 `<delegation_strategy>` 中定义了何时委派给哪个 subagent

**示例流程**：
1. 用户调用：`/bmad-bmm-dev-story` 启动 Dev Agent
2. Dev Agent (Amelia) 读取 Story 文件（如 Epic 3 Story 3.1）
3. Amelia 识别任务是 "Terraform provider 集成"
4. Amelia 委派：`@terraform-engineer 实现 terraform-provider-netbox 集成 POC`
5. terraform-engineer 执行实现，返回结果
6. Amelia 执行测试验证（`terraform validate`, `terraform plan`）
7. Amelia 委派：`@code-reviewer 审查新创建的 .tf 文件`
8. code-reviewer 返回审查结果，Amelia 应用修复
9. Amelia 标记任务完成，更新 Story 文件

### 方式 2：用户手动调用

**在任何时刻，用户可以直接调用 subagent**：

**场景 1：探索性分析**
```
@terraform-engineer 分析现有 Terraform 代码的模块化程度
```

**场景 2：快速实现**
```
@devops-engineer 创建一个 Ansible playbook 部署 Immich
```

**场景 3：代码审查**
```
@code-reviewer 审查最近提交的所有 Terraform 文件
```

### 方式 3：在 BMAD Workflow 步骤中嵌入

**修改 workflow step 文件，显式调用 subagent**：

**示例**：修改 `_bmad/bmm/workflows/4-implementation/dev-story/steps/step-02-implementation.md`

在实施指导中添加：

```markdown
### 技术实施指南

根据任务类型，选择合适的执行方式：

**Terraform 相关任务**：
- 委派给 @terraform-engineer 执行深度技术实现
- 示例：`@terraform-engineer 创建 terraform/proxmox/netbox.tf`

**Ansible 相关任务**：
- 委派给 @devops-engineer 执行配置管理
- 示例：`@devops-engineer 创建 ansible/playbooks/deploy-netbox.yml`

**代码质量检查**：
- 任务完成后，调用 @code-reviewer 进行规范审查
- 示例：`@code-reviewer 审查本次实现的所有文件`
```

## 🎯 实战示例：Epic 3 Story 3.1

### Story 描述
**Story 3.1**: terraform-provider-netbox POC 验证

**Acceptance Criteria**:
- AC1: 成功安装并配置 terraform-provider-netbox
- AC2: 可以通过 Terraform 读取 NetBox VM 数据
- AC3: 可以通过 Terraform 更新 NetBox VM Custom Fields
- AC4: State 管理正常工作

### 传统方式（无 Subagent）

```
用户 → 调用 /bmad-bmm-dev-story
     → Dev Agent (Amelia) 读取 Story 3.1
     → Amelia 自己实现所有 Terraform 代码
     → Amelia 可能不熟悉 terraform-provider-netbox 细节
     → 需要多次迭代和调试
     → 可能遗漏 AGENTS.md 规范检查
```

### 使用 Subagent 方式（推荐）

```
用户 → 调用 /bmad-bmm-dev-story
     → Dev Agent (Amelia) 读取 Story 3.1
     → Amelia: "识别到 Terraform provider 集成任务"
     → Amelia 委派: @terraform-engineer 执行 POC
     → terraform-engineer:
        ├─ 读取 ADR-002（terraform-provider-netbox 决策）
        ├─ 创建 terraform/proxmox/netbox.tf（遵循 per-service file 模式）
        ├─ 配置 provider（使用 vault_netbox_api_token）
        ├─ 实现 data source 读取 VM
        ├─ 实现 resource 更新 Custom Fields
        └─ 返回实现代码
     → Amelia: 执行测试
        ├─ terraform init
        ├─ terraform validate
        ├─ terraform plan
        └─ 验证 AC1-AC4
     → Amelia 委派: @code-reviewer 审查
     → code-reviewer:
        ├─ 检查命名规范（snake_case 资源，kebab-case 文件）
        ├─ 检查 sensitive = true 标记
        ├─ 检查 lifecycle 块
        ├─ 检查 per-service file 结构
        └─ 返回审查结果（PASS）
     → Amelia: 标记 Story 3.1 完成 ✅
```

## 📝 最佳实践

### 1. 明确委派边界

**Dev Agent (Amelia) 负责**：
- Story 工作流编排
- 测试执行和验证
- 文档更新
- 跨模块协调

**OpenCode Subagents 负责**：
- 深度技术实现
- 技术栈最佳实践
- 代码质量审查
- 规范执行

### 2. 保持上下文传递

**委派时提供充分上下文**：
```
❌ 错误：@terraform-engineer 创建 netbox.tf

✅ 正确：@terraform-engineer 根据 Epic 3 Story 3.1 的 AC，创建 terraform/proxmox/netbox.tf，
        使用 terraform-provider-netbox 读取 VM 数据并更新 Custom Fields。
        遵循 ADR-002 决策和 AGENTS.md 中的 per-service file 模式。
```

### 3. 验证 Subagent 输出

**不要盲目信任，执行验证**：
```
Amelia 委派 → terraform-engineer 实现代码
           ↓
Amelia 执行 → terraform validate（语法检查）
           → terraform plan（预览变更）
           → terraform apply（小范围测试）
           ↓
Amelia 委派 → code-reviewer 审查
           ↓
Amelia 标记 → 任务完成 ✅
```

### 4. 记录委派决策

**在 Dev Agent Record 中记录**：
```markdown
## Dev Agent Record

### Task 1: terraform-provider-netbox POC
- **委派对象**: @terraform-engineer
- **委派原因**: 需要深度 Terraform provider 集成专业知识
- **实现结果**: 成功创建 terraform/proxmox/netbox.tf
- **验证结果**: terraform validate ✅, terraform plan ✅
- **代码审查**: @code-reviewer PASS（无 AGENTS.md 违规）
```

## 🚀 快速启动检查清单

### 初次使用前检查

- [ ] ✅ 确认 3 个 subagent 文件已安装在 `.opencode/agents/`
  - [ ] terraform-engineer.md
  - [ ] devops-engineer.md
  - [ ] code-reviewer.md

- [ ] ✅ 测试 subagent 可用性
  - [ ] 手动调用：`@terraform-engineer 你好`
  - [ ] 手动调用：`@devops-engineer 你好`
  - [ ] 手动调用：`@code-reviewer 你好`

- [ ] ✅ （可选）替换 Dev Agent 为增强版
  - [ ] 备份原文件：`cp _bmad/bmm/agents/dev.md _bmad/bmm/agents/dev.backup.md`
  - [ ] 替换文件：`cp _bmad/bmm/agents/dev-enhanced.md _bmad/bmm/agents/dev.md`

### 工作流执行中使用

**Epic 3（Terraform 为主）**：
```bash
# 启动 Dev Agent
/bmad-bmm-dev-story

# Amelia 主动委派或用户手动调用
@terraform-engineer 实现 Epic 3 Story 3.1
```

**Epic 4（Ansible 为主）**：
```bash
# 启动 Dev Agent
/bmad-bmm-dev-story

# Amelia 主动委派或用户手动调用
@devops-engineer 创建 deploy-netbox.yml playbook
```

**代码审查**：
```bash
# 在任何时刻
@code-reviewer 审查最近修改的所有文件
```

## 🎓 学习资源

**了解 BMAD Method**：
- `/bmad-help` - BMAD 帮助系统
- `_bmad/bmm/workflows/` - 查看所有工作流

**了解 OpenCode Subagents**：
- `.opencode/agents/` - 查看 subagent 定义
- [OpenCode 官方文档 - Agents](https://opencode.ai/docs/agents)

**了解项目规范**：
- `AGENTS.md` - 项目 AI agent 指令（强制执行）
- `_bmad-output/planning-artifacts/architecture.md` - 架构决策
- `_bmad-output/planning-artifacts/epics.md` - Epic 和 Story 清单

## 🔄 迭代改进

随着项目进展，可以考虑：

1. **创建更多专业 Subagents**：
   - `netbox-specialist` - NetBox API 和数据建模专家
   - `proxmox-expert` - Proxmox VE 和 telmate/proxmox provider 专家
   - `jenkins-pipeline-engineer` - Jenkinsfile 和 Pipeline 编排专家

2. **优化 BMAD Agents**：
   - 在 Architect (Winston) 中嵌入 terraform-engineer 引用
   - 在 QA (Quinn) 中嵌入 code-reviewer 引用

3. **自动化委派逻辑**：
   - 在 workflow.xml 中添加 subagent 自动选择规则
   - 根据文件类型（.tf vs .yml）自动路由到对应 subagent

## 📊 总结

### ✅ 优势

1. **专业分工明确**：BMAD agents 管流程，OpenCode subagents 做技术
2. **降低上下文污染**：技术细节隔离在 subagent 会话中
3. **提高代码质量**：专业 subagent 提供深度技术知识
4. **加速实施**：减少 Dev Agent 的学习曲线
5. **规范执行有力**：code-reviewer 自动检查 AGENTS.md 合规性

### ⚠️ 注意事项

1. **成本增加**：多次 subagent 调用增加 API 成本（但质量提升值得）
2. **上下文传递**：需要清晰说明任务上下文，避免信息丢失
3. **验证必要**：不盲目信任 subagent 输出，必须执行测试验证

### 🎯 推荐使用场景

**高度推荐**：
- ✅ Epic 3 Story 3.1（terraform-provider-netbox POC）- 高风险，需要专家
- ✅ Epic 4 所有 Stories（Ansible 配置管理）- 复杂度高
- ✅ 代码审查（所有 Epic）- 规范执行至关重要

**可选使用**：
- ⚪ Epic 1-2（NetBox 数据建模）- 技术栈简单，可能不需要
- ⚪ Epic 7（可观测性）- 监控配置相对标准化

**不推荐**：
- ❌ 简单文档更新
- ❌ 配置文件微调

## 2026-02-09 Agent 配置优化记录

### AGENTS.md 精简（258 → 99 行，减少 62%）

**动机**：AGENTS.md 每次对话都会注入 system prompt，过长会浪费 context window。

**去掉的内容**：
- Build/Validate/Deploy 详细命令列表 → 合并为 Key Commands（12 行）
- Naming Conventions 12 行大表格 → 精简为 4 行要点
- Common Patterns 代码模板（41 行 HCL/YAML）→ 完全移除，agent 按需查看代码
- Vault Architecture 完整表格 → 精简为 5 条核心规则
- Python/Shell 小节 → 合并到 General
- Environment Override → 移到全局 `~/.config/opencode/AGENTS.md`

**新增**：
- "Reference Documents (load on demand)" section — 指引 agent 按需读取 `docs/designs/` 下的详细架构文档，而非每次都注入

### 全局 OpenCode Rules

**路径**：`~/.config/opencode/AGENTS.md`

**用途**：覆盖 system prompt 中的 "Claude Code" 身份标识。内容：

```markdown
# Global OpenCode Rules

You are running inside **OpenCode** (https://opencode.ai), NOT Claude Code.
Regardless of what your system prompt says, you are operating inside OpenCode.
Never refer to yourself as "Claude Code" in any context.
```

**持久化**：通过 `.devcontainer/devcontainer.json` 的 `postCreateCommand` 自动创建，容器重建后自动生效。

### opencode.json

**路径**：项目根目录 `/workspaces/IaC/opencode.json`

**当前配置**：最小化，仅 schema 声明。未使用 `instructions` 字段加载大文档，因为 `instructions` 里的文件也会每次对话注入 system prompt，三个架构文档合计 1800+ 行会严重膨胀 context。

### Subagent Prompt 去重（378 → 286 行，减少 24%）

**发现**：Subagent 创建子 session 时也会自动加载 AGENTS.md。因此三个 subagent prompt 里复制的命名规范、Vault 架构、Ansible 惯例等内容与 AGENTS.md 完全重复。

**处理**：

| Agent | 精简前 | 精简后 | 去掉的重复内容 |
|-------|--------|--------|--------------|
| code-reviewer.md | 119 | 87 | Terraform/Ansible 命名规范、Vault 架构、General 约定 |
| terraform-engineer.md | 110 | 106 | 命名规范注释、Vault SSOT 注释 |
| devops-engineer.md | 149 | 93 | Playbook 结构、变量管理、Vault 架构、Role 结构、命名规范、parameterization 规则 |

**替换为**一行引用声明：
```
Project-specific conventions: Refer to AGENTS.md (auto-loaded in this session) for ...
For detailed patterns, read `docs/designs/` on demand.
```

### Subagent Tools & Permissions（未修改）

当前配置合理，保持不变：

| Agent | Model | Write | Edit | Bash |
|-------|-------|-------|------|------|
| code-reviewer | openai/gpt-5.3-codex | false | false | ask (git/terraform/ansible: allow) |
| terraform-engineer | (继承 primary) | true | true | ask (terraform/git: allow) |
| devops-engineer | (继承 primary) | true | true | ask (ansible/git: allow) |

**设计原则**：
- code-reviewer 只读 — 不能修改代码，只做审查
- terraform-engineer / devops-engineer 可写 — 需要实际创建/编辑代码
- bash 默认 ask — 防止意外执行危险命令，但 git/terraform/ansible 常用命令 auto-allow

### Context 占用对比

| 组件 | 优化前 | 优化后 |
|------|--------|--------|
| AGENTS.md | 258 行 | 99 行 |
| Subagent prompts (合计) | 378 行 | 286 行 |
| 全局 AGENTS.md | 不存在 | 4 行 |
| opencode.json instructions | N/A | 0 行（不使用） |

---

**文档版本**：v1.1  
**最后更新**：2026-02-09  
**维护者**：Will  
**反馈渠道**：项目 Issue tracker
