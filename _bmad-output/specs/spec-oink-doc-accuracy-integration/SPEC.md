---
id: SPEC-oink-doc-accuracy-integration
companions:
  - claim-registry.md
  - security-boundary.md
  - automation-roadmap.md
sources:
  - ../../planning-artifacts/research/technical-oink-doc-accuracy-integration-2026-08-26/research.md
---

> **Canonical contract.** 本 SPEC 与 `companions:` 中的文件共同构成构建、测试和验证必须遵守的完整契约。`sources:` 仅用于追溯，不是下游必读材料。已完成的 Phase 1/Phase 2 implementation artifacts 保留为交付历史；本契约与 companions 定义当前语义和后续路线。

# OINK 文档准确性集成：确定性基础与 AI 自动化边界

## Why

IaC 文档中的错误端口、镜像、版本或配置会误导维护者和 coding agent。封闭的静态比较能可靠发现少量已登记值的两端不一致，但不能开放式阅读文档、发现新 claim 或撰写修复；这些工作需要 AI。系统因此将 AI 用于候选发现和最小编辑，把证据、权限、范围及验收保留在 deterministic control plane，并让 OINK 继续只承担无特权展示。

项目所有者有意将私人 Notion workspace 用作 credential GUI，并于 2026-09-05 接受直接运行及现有 Jenkins post-deployment stage 所带来的第三方 SaaS/账户和执行风险。该决定取消 Notion 去凭据化对 OINK/AI 路线的阻塞，但不授权文档 AI/CI、OINK 或公开制品读取、转发或发布这些凭据；完整边界见 [security-boundary.md](security-boundary.md)。

## Capabilities

- **CAP-1 — Known-claim consistency gate (`delivered`)**
  - **intent:** 系统能够对 [claim-registry.md](claim-registry.md) 中的封闭 claim，确定性比较 Markdown locator 与 checked-in Ansible defaults scalar。
  - **success:** 当前六个 claim ID 被独立回归基线锁定；相等、矛盾、缺失及歧义 fixture 均产生规定状态、provenance 和 exit code。

- **CAP-2 — Bounded AI analysis contract (`prototype delivered`)**
  - **intent:** 系统能够把单一允许文档、Git diff span 和脱敏 evidence 打包给 AI，并以本地 schema/validator 约束 candidate 与 edit proposal。
  - **success:** 模型不能签发 `verified`、伪造 source/evidence、越出单文档范围或绕过 stale/secret 检查；当前只支持 recorded replay 和显式确认的手动 live analysis，不应用修改。

- **CAP-3 — Automated draft repair loop (`planned`)**
  - **intent:** 系统能够自动发现可能漂移的文档陈述，对可确定性证明的候选生成并验证最小 patch，再创建供人审阅的 Draft PR。
  - **success:** 只有 evidence gate、scope check、修改后 consistency regression 与文档构建全部通过的单文档 patch 可进入 publisher；unknown 或冲突只报告，不修改；永不自动 merge。

## Capability Lineage

2026-09-05 的契约校准重新定义了 capability 编号：旧 CAP-1（Notion 去凭据化门禁）由 accepted-risk 决策取代；旧 CAP-2（closed-claim detector）和旧 CAP-3（report）合并为当前 CAP-1；当前 CAP-2 对应已交付的 Phase 2 controller prototype；当前 CAP-3 是尚未实施的新目标。引用 capability 时应同时给出本 SPEC 日期或名称，避免与旧版本混淆。

## Constraints

- `tools/check-doc-claims.py` 是 **repository consistency gate**，不是开放式发现器或现实世界 truth oracle。`verified` 只证明目标 Markdown 与 checked-in defaults 同类型同值；两端同时错误时仍可能通过。
- `CLAIMS` 是 Phase 1 权威闭集，[claim-registry.md](claim-registry.md) 是其投影；扩大闭集需要单独批准。AI 可发现 registry 外候选，但不能借此静默改变确定性基线。
- AI 负责语义候选发现与写作；普通代码负责 allowlist、引用回验、evidence completeness、revision/digest、secret scanning、状态转换、patch 验收和发布授权。
- OINK/Hugo、GitHub Pages、detector 与 AI manifest/report 均为无特权面，不得 import、调用或消费 `scripts/sync-to-notion.py`、其输出、`.env`、Vault、tfvars/state、Notion 内容或生产凭据。
- 当前 documentation CI 只运行四个离线步骤：known-claim regression suite、doc-gardening controller/contract suite、recorded golden accept/reject fixtures、current repository consistency run；它不调用真实 AI、不衡量模型语义准确率、不应用 patch，也不开 PR。
- 真实 AI、自动调度、patch apply、GitHub write identity、Draft PR publisher、runtime collector 或公开 OINK report 均须作为独立实施边界获得批准。阶段与门禁见 [automation-roadmap.md](automation-roadmap.md)。

## Non-goals

- 让 OINK/Hugo 执行 AI 推理、持有模型/生产/Notion 凭据或调用生产系统。
- 将 pairwise repository consistency 宣称为生产现实、部署有效性或绝对事实正确性。
- 让模型自行决定 evidence gate、修改 IaC/应用代码、修复 production drift、自动 merge 或部署。
- 在本阶段引入 runtime collectors、设备/API 采集、webhook reconciliation 或开放网络发现。
- 向 report、manifest、OINK 页面或 `llms.txt` 发布密码、token、凭据或敏感派生信息。

## Success signal

在干净 checkout 上，六条独立锁定的 known claims 全部通过，所有离线 controller/contract 与 golden accept/reject fixtures 通过，且生成物只含允许的 repository evidence。下一阶段完成后，一个可证明的文档漂移将按 [automation-roadmap.md](automation-roadmap.md) 生成单文档最小 Draft PR；无法证明的候选保持 unknown 并且不产生修改。

## Accepted Risk Review Triggers

出现以下任一变化时，必须重新评估 Notion accepted risk：仓库或运维转为多人协作、Notion 数据库扩大共享、同步进入无人值守运行、凭据进入 AI/CI/OINK/公开 artifact，或发生 Notion 账户、integration token、日志/输出泄漏事件。

## Open Questions

- 非敏感 accuracy report 是否公开渲染到 OINK/Pages，仍需单独批准；当前只作为 local/CI artifact。
