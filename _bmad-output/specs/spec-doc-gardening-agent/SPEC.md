---
id: SPEC-doc-gardening-agent
companions:
  - evidence-model.md
sources:
  - ../../brainstorming/brainstorm-doc-gardening-agent-2026-08-12/brainstorm-intent.md
---

> **Canonical contract.** 本 SPEC 与 `companions:` 中的文件共同构成下游设计、实现与验证必须遵守的完整契约。`sources:` 仅用于追溯。

# Evidence-Gated Doc-Gardening Agent

## Why

实施文档或架构文档一旦偏离有效 IaC 代码与生产现实，维护者和 coding agent 就可能据此做出错误实现或错误部署。本工作要建立 recurring doc-gardening agent，在完整证据闭环保护下持续发现并修正文档漂移，同时把证据不足或生产漂移交给人判断。

## Capabilities

- **CAP-1**
  - **intent:** 系统能够以有效 IaC 代码和只读生产观察核验实施文档与架构文档中的关键陈述。
  - **success:** 每条被审计陈述都有可追溯的文档、代码、生产三方证据，或被明确标记为无法闭环并升级。

- **CAP-2**
  - **intent:** 系统能够通过 evidence gate 区分一致、文档漂移、生产漂移和证据未决。
  - **success:** 只有证据完整的文档漂移进入自动修复资格；其他结果不修改文档，并按 [evidence-model.md](evidence-model.md) 记录或升级。

- **CAP-3**
  - **intent:** 系统能够自动修复一个可独立验证的文档偏差并开启一个可审阅 PR。
  - **success:** PR 只处理该文档偏差，保持目标文档的结构、术语与格式，并包含修改原因、证据来源、改后验证及结果。

- **CAP-4**
  - **intent:** 系统能够把需要人类判断的候选项升级，而不擅自修改文档。
  - **success:** 证据缺失或冲突、管理边界不明、代码有效性不明、生产漂移或跨时段持续不可达均生成可追溯升级记录，且文档保持不变。

## Constraints

- 完整 evidence loop 是自动修改和开启 PR 的硬门禁；不能以置信度、语言流畅度或单一证据替代。
- IaC 管理范围内以有效代码为期望事实；生产偏离代码属于 production drift，不能据此把文档改成生产漂移状态。
- 明确的代码管理关系优先于冲突的设计文档；非 IaC 管理组件只有在管理边界已确定时才以生产状态为现实依据。
- 生产核验只能使用无影响、无破坏的只读方式，并留下可追溯记录。
- 可达性失败必须在不同时段多次重试；持续失败只能升级，不能作为废弃证据。
- 每个自动 PR 只能处理一个偏差，逻辑必须完整，格式必须遵循目标文档，并附带 [evidence-model.md](evidence-model.md) 规定的证据与验证记录。
- 在“有效 IaC 管理代码”的充分证据标准得到确认前，相关候选项不得进入自动修复路径。

## Non-goals

- 修改 Terraform、Ansible、应用代码或生产环境状态。
- 修复 production drift，或自动决定未声明组件的管理归属。
- 仅凭一次或多次不可达就宣告代码、服务或文档已废弃。
- 自动合并 PR。
- 在 V1 中保证实施文档和架构文档之外的文档覆盖。

## Success signal

用一致、文档漂移、生产漂移、管理边界不明、暂时不可达和持续不可达的代表性案例运行一次完整审计：只有证据闭环的文档漂移产生单一问题文档修复和未自动合并的 PR；其余案例均不改文档，并留下正确的无变更记录或人工升级记录。

## Assumptions

- 根据当前仓库布局，V1 的实施文档对应 `docs/deployment/`，架构文档对应 `docs/designs/`；若预期覆盖更多路径，应在实现前确认。
- V1 开启 PR 供人审阅但不自动合并，因为当前输入只授权了开 PR，没有授权合并。

## Open Questions

- 哪些代码证据足以证明组件仍由 IaC 有效管理，而不是仅存在相关但已废弃的代码？
- 跨时段重试需要多少次、跨越多长观察窗口？
- V1 中哪些文档陈述属于必须审计的“关键陈述”？
- 允许使用哪些生产只读接口与凭据，审计证据必须保留在哪里？
