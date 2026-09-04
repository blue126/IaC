---
id: SPEC-ai-review-loop-gate
status: done
baseline_commit: d9cd1c8c0c8b095a6309745b68bc3f66704199d4
current_phase: phase-2b-review-consolidation-complete
companions:
  - state-machines.md
  - validation-matrix.md
  - security-boundary.md
  - rollout-and-rollback.md
  - brownfield.md
  - implementation-phases.md
sources: []
---

> **Canonical contract.** 本 SPEC 与 `companions:` 是 IaC 项目接入公共 AI PR governance runtime 的完整实现与验证合同。

# IaC AI PR Review Loop Adoption / IaC AI PR 审查闭环接入

## Why

IaC 已有 Claude PR review 和合并后 Jenkins 流程，但缺少当前 SHA 的确定性 PR 验证、机器可读 AI gate、自动修复—复审闭环及受保护的自动合并。本接入在不向 PR workflow 暴露生产凭据、不自动执行基础设施写入的前提下，复用公共 bootstrap runtime 补齐闭环。

## Capabilities

- **CAP-1**
  - **intent:** IaC 为每个 PR HEAD SHA 运行与变更范围匹配的无部署确定性验证。
  - **success:** `repo-validation` 仅在当前 SHA 的全部适用 Terraform、Ansible、文档、脚本和治理策略检查通过时成功；任何跳过均有可审计原因。
- **CAP-2**
  - **intent:** Claude 审查初始 PR 和每个新 HEAD SHA，并由受限 fixer 处理明确可修复的 finding。
  - **success:** 每次修复普通 push 都产生新的 `synchronize` 审查，循环在通过、三轮上限或安全停止条件之一结束。
- **CAP-3**
  - **intent:** IaC 为 Claude 对当前 SHA 的结构化结论发布 required check。
  - **success:** `review-policy-gate` 仅在唯一一次 Claude 审查成功、`reviewed_sha` 等于当前 HEAD 且不存在 blocking finding 时通过。
- **CAP-4**
  - **intent:** GitHub 只自动合并通过代码、审查、信任和分支规则的普通 IaC 变更。
  - **success:** 当前 SHA 的两个 gate 和 Ruleset 满足后执行 squash auto-merge；治理敏感路径始终等待人工确认。
- **CAP-5**
  - **intent:** 合并后清理 GitHub 远端任务残留而不破坏审计链。
  - **success:** 已合并 head branch 自动删除，旧 run 被取消，artifact 按保留期过期，PR、review、commit 和 gate 记录保留。
- **CAP-6**
  - **intent:** 合并后的 Jenkins 交付与合并前 PR validation 保持权限和责任分离。
  - **success:** `main` push 可以启动 Jenkins，但 Terraform Apply 与 Ansible Deploy 仍需独立人工输入；PR workflow 无生产凭据或外部写能力。

## Constraints

- IaC 以薄 caller workflow 引用 public reusable workflow 的 immutable commit SHA；项目专属 adapter、敏感路径策略与 secrets 显式保留在本仓库。
- 空项目或未配置 adapter 的状态必须是 `validation: pending` 且禁止 auto-merge；不得使用永远成功的占位检查。
- 禁止使用 `pull_request_target` 执行 PR head；写凭据仅处理 owner/allowlist 创建的同仓库可信任务分支和不可变 SHA。
- 自动 reviewer 每个 PR HEAD 只调用一次 Claude Code Action；模型只读，结构化 verdict 由确定性步骤渲染为评论并交给独立 `review-policy-gate` 校验。fixer 使用独立最小权限 Fixer App，不使用默认 `GITHUB_TOKEN` 推送。
- 自动循环最多三轮；重复 finding 指纹、冲突、验证失败、治理敏感路径、不可修复结论或权限异常必须 fail closed。
- PR validation 不得 deploy、publish、apply、push image、release、读取生产 secrets、刷新动态生产 state 或写入外部系统。
- `.github/workflows/**`、`Jenkinsfile`、validation/gate/bootstrap 配置及 secret/部署审批相关文件禁止 AI 自动修复和自动合并。
- 仅命名自动化主体获得范围明确的 commit、merge 和远端分支清理例外；其他 agent 继续受 `AGENTS.md` 禁令约束。

## Non-goals

- 不自动批准或执行 Terraform Apply、Ansible Deploy、发布或任何生产写操作。
- 不自动修复 fork PR、未知 bot 或未获准 actor 的 PR。
- 不由 public runtime 携带 Terraform、Ansible 或 Jenkins 的项目实现。
- 不提供或执行本地 worktree、branch、sandbox cleanup；其生命周期由各 agent 自身规则负责。
- 本规范阶段不修改 GitHub 设置、提交代码、创建 PR 或执行部署。

## Success signal

一个可信的普通 IaC PR 无需人工对话即可在最多三轮内完成逐 SHA 验证、Claude 审查、修复和复审；当前 SHA 的 `repo-validation` 与 `review-policy-gate` 通过后自动 squash merge。治理敏感变更仍等待人工确认，任何合并触发的 Jenkins 流程仍在 Apply 与 Deploy 前停于人工输入。

## Assumptions

- Claude Code Action 能在一次只读调用中稳定返回符合有界 schema 的 verdict；评论由确定性 renderer 从同一 verdict 生成，不解析自然语言评论。
- 官方 `/code-review --comment` plugin 会在 PR 已有 Claude 评论时跳过，且其自然语言终端输出不构成 gate 合同，因此不用于逐 SHA 自动循环。
- Public reusable workflow 在 public 与 private consumer 中都能保持正确的 secret、permission 和 check provenance；实施前使用 fixture 验证。

## Suggested Review Order

**Single-call review path**

- One read-only Claude call exports the bounded verdict for the current HEAD.
  [`claude-review.yml:15`](../../../.github/workflows/claude-review.yml#L15)

- Fail-closed policy job validates identity before rendering or evaluating.
  [`claude-review.yml:93`](../../../.github/workflows/claude-review.yml#L93)

- Sanitized, SHA-marked comments update idempotently without becoming gate input.
  [`claude-review.yml:154`](../../../.github/workflows/claude-review.yml#L154)

**Independent contract enforcement**

- Read-only repository CI independently runs the review workflow contract.
  [`repo-validation.yml:55`](../../../.github/workflows/repo-validation.yml#L55)

- Runtime fixtures, permissions, shell extraction, and API stubs guard the data flow.
  [`review-policy-gate-test.sh:143`](../../../tests/ci/review-policy-gate-test.sh#L143)

**Architecture record**

- Phase 2B supersedes the dual-call shadow while leaving enforcement unchanged.
  [`cicd-architecture.md:121`](../../../docs/designs/cicd-architecture.md#L121)
