---
title: "AI-assisted documentation accuracy integrated with OINK / AI 文档准确性与 OINK 集成"
type: technical
intent: deepen
status: complete
created: 2026-08-26
updated: 2026-08-26
claims_verified: 8
claims_unverified: 1
claims_overturned: 1
legacy_input: ../technical-evidence-gated-doc-gardening-research-2026-08-12.md
---

# AI 文档准确性与 OINK 集成研究

## Executive Summary / 执行摘要

**决策：继续 OINK 试点，但不要把 OINK 当成文档准确性系统。** OINK/Hugo 应保持为无生产凭据的展示平面，只消费已审查的 Markdown 和非敏感 manifest；独立的 evidence-gated gardening 控制平面负责定期采集、漂移判定、AI 草稿和 PR。GitHub Pages/Hugo build 与特权采集任务之间必须有 job/workflow、凭据和不可变制品边界。[1][2][5][6]

AI 可以有效缩小审阅范围、提取原子 claim、生成候选修订和解释 diff，但不能独立证明事实正确或文档完整。结构化输出只能保证形状；真实共同改码/改文档基准的最佳对齐仍有限，RAG 也不能消除无支持陈述。[13][14][15][16][17]

动态更新应采用“双触发”：PR/配置事件用于低延迟定向检查，周期 reconciliation 用于发现漏事件、长期漂移和孤儿页面。Webhook 不是完整性证明；权威事实必须绑定 source revision，或绑定 collector-owned observation、范围、时间和 digest。[7][8][9][10][11]

**首轮 OINK 范围：** 发布现有文档、逐页 Markdown、`llms.txt`、状态/provenance 元数据、链接/Schema/secret/golden-build 检查；AI 只生成 draft PR，不访问生产系统，不自动合并。生产采集和有限自治后置。

**最大 caveat：** “coverage、accuracy、unknown、stale、provenance 分开报告”有标准方法论支持，但本研究未找到直接证据证明这一特定五维方案优于所有复合分数，因此它是透明性优先的设计建议，不是已验证定律。[22]

## 1. OINK 的正确边界

OINK `v0.7.0` 可生成显式启用的逐页 `index.md`、Markdown alternate link 和每语言 `llms.txt`；其固定版本配置声明 Hugo `>=0.160.1 Extended`。Hugo 从 `v0.153.2` 起不再为使用方执行 Extended 版本检查。因此，CI 必须固定并验证 Hugo 二进制，不能依赖 module constraint。[1][2][3][25]

页面 front matter 的 `outputs` 在 Hugo `v0.165.0` 实际实现中会**替换** kind-level outputs。Hugo 配置文档曾将该行为描述为追加，但同版本的源码和集成测试表明其实际语义是替换。因此，站点级数组必须完整列出需要保留的格式，并通过 golden build 验证这一关键行为。[4]

推荐边界：

```text
Evidence plane (privileged)       Presentation plane (unprivileged)
read-only APIs / schedules        reviewed Markdown + manifest
        -> normalize/redact -> draft PR -> Hugo/OINK -> Pages
```

- Hugo template/content adapter 不调用 HCP、NetBox、Proxmox 或 Vault。
- Pages build 不持有生产凭据，只获得 checkout、artifact、Pages deploy 所需权限。
- AI/生成器输出先经 Schema、链接、secret 和 clean-diff 检查，再进入 PR。
- 页面 provenance 至少包含 source revision 或 digest、collector/generator version、generated time、observed time、reviewer 和 content hash。SLSA provenance 可证明制品如何生成，但不能证明文档事实正确。[5][6][23]

## 2. AI 能做什么

| 任务 | AI 角色 | 确定性门禁 |
|---|---|---|
| Claim extraction | 从指定文档/diff 提取原子主张、locator、依赖候选 | source span 必须存在；Schema；金标 precision/recall |
| Impact triage | 将代码/配置变更映射为 `possibly-stale/contradiction/unknown` | 文件、符号、资源 identity 与依赖图校验 |
| Draft edit | 生成最小补丁和解释 | 标识符/路径/默认值 contract；示例执行；链接/secret 检查 |
| Completeness | 仅相对封闭权威 claim 集计算 coverage | 不得宣称开放世界“已抽全” |
| Fact judgment | 汇总 evidence，指出冲突 | 最终状态由 oracle/gate 或 owner 签署，不由模型决定 |

Claim extraction 在受限任务中已有较强结果。另一项基于真实代码与文档共同演进（code-doc co-evolution）的基准研究则表明，对齐能力仍然有限；本轮研究对该结果仅有中等置信度。这支持 precision-first 告警而非静默修订。[13][14] Structured Outputs（结构化输出）和同类 schema-constrained decoding（Schema 约束解码）解决的是格式约束，不是语义真实性。[15][16] RAG 可以提供证据，但仍可能生成缺乏支持或相互矛盾的陈述。因此，系统必须保存检索结果集合和 source spans，并将“未检索到相关证据”解释为 `unknown`。[17]

默认发布模型应是“确定性验证 + 可审计 PR + owner 审批”。通过自动 grader 并不意味着维护者愿意合并相应变更；大型生产仓库的公开实践同样以 maintainer 发起、PR 和人工判断为中心。[18][19] 未来只有低风险、封闭、可回滚且积累了足够历史证据的变更类别，才能按显式策略获得有限自治，并持续抽样、监测和保留撤权机制。

## 3. 定期动态更新

建议三种 cadence，不让任一触发器承担它无法证明的保证：

| Trigger | 建议频率 | 作用 | 不保证 |
|---|---|---|---|
| PR/diff | 每次变更 | 定向识别受影响文档、运行静态 oracle、生成候选补丁 | 未变文件没有漂移 |
| Webhook | HCP/NetBox 事件 | 降低 runtime 变化发现延迟，触发权威源重读 | 事件完整、顺序正确、仅一次 |
| Reconciliation | 每夜静态、每周 runtime、每月全量 | 修复漏事件、过期 claim、孤儿对象和 identity 漂移 | 单次跨系统原子 snapshot |

AWS 和 Stripe 的事件语义表明，事件可能重复、乱序，甚至未生成或未送达。要求最终完整性的系统必须保留独立的 reconciliation 路径。[7][8][26]

HCP Terraform state version 可绑定具体的 workspace、serial、lineage、run 和可选 VCS SHA；Ansible facts 则是针对各目标的独立观察。Proxmox 的公开 API 提供当前资源视图。本研究未找到与 HCP state version 等价的全局不可变 snapshot，因此建议 collector 创建 observation revision，记录 identity、scope、success set、`observed_at`、版本和 response digest，并明确标记其非原子性。关于 Proxmox 的这一判断属于接口层面的推论，置信度为中等。[9][10][11]

原始 Terraform state 和未经筛选的日志可能包含凭据；将值标记为 `sensitive` 并不表示该值不会存储在 state 中。确定性 collector 必须按字段 allowlist 提取、归一化和脱敏，LLM 只接收任务所需的派生事实。[12][27]

## 4. 准确性模型

准确性不是“AI confidence”，而是“一个 claim 与指定 oracle 一致”。JSON Schema 检查结构，`terraform validate` 检查语法和内部一致性；二者都不能证明远端/runtime 或业务语义正确。[20][21]

建议 claim registry：

```yaml
id: service.caddy.port
document: docs/deployment/caddy.md
locator: heading-or-stable-anchor
risk: normal
oracle: ansible_role_default
dependencies: [ansible/roles/caddy/defaults/main.yml]
owner: platform
freshness_slo: P7D
```

证据状态必须互斥：

- `verified`：identity、revision、oracle 和 evidence 完整且 fresh。
- `contradiction`：文档与 oracle 明确冲突。
- `unknown`：从未成功采集证据、identity 冲突、覆盖不全或发生 collector error。
- `stale`：last-known evidence 超 SLO 或依赖 revision 已变化。
- `not-applicable`：有 owner、理由和期限的显式豁免。

不得将 `unknown` 或 `stale` 解释为 false，也不得仅通过更新时间戳将状态恢复为 `verified`。普通页面可以展示 last-known value，但必须同时展示 observation time 和证据状态。对于关键运行手册、破坏性命令和安全参数，相关 PR 必须满足 `contradiction=unknown=stale=0`。

建议分别报告 coverage、observed accuracy、unknown、stale 和 provenance completeness，而不合成单一绿灯总分；这是透明性设计建议，尚未被直接比较研究验证。[22]

## 5. OINK 试点路线

### Phase 0：展示与静态卫生，立即纳入

- 固定 OINK/Hugo/Go，运行 golden build。
- 启用逐页 Markdown、`llms.txt` 和本地搜索。
- 为高风险或高价值页面增加 `status`、`owner`、`verified_at` 和 `source_revision`；不要为全部 94 页批量填充未经验证的元数据。
- CI 运行内部链接、Hugo warning、Schema、secret scan 和 Markdown 输出检查。
- 将 `proposal/implemented/verified/stale/superseded/unknown` 状态明显渲染给人和 Agent。

### Phase 1：确定性 claim registry

- 先覆盖端口、域名、资源规格、脚本/路径、版本和 playbook 名等可绑定 oracle 的 claim。
- 对于 PR diff，只重新检查依赖项已发生变化的 claim；每月执行一次全量 reconciliation，以发现依赖图造成的漏报。
- 结果生成无敏感信息的 manifest，OINK 只读取 manifest，不运行 collector。

### Phase 2：AI gardening，draft-only

- AI 从 diff、相关文档和已脱敏 evidence 提取 claim、分类漂移并生成最小 draft PR。
- 强制 source span、evidence ref、unknown reason 和模型/Prompt 版本。
- 需要 CODEOWNER 审批；相关提交的任何变化都会使原有审批和 evidence 失效。GitHub required checks/CODEOWNERS 必须显式处理 skipped、bypass、status source 和自保护边界。[24][28][29]

### Phase 3：runtime evidence

- Jenkins 定期使用专用的只读身份，从 HCP、Ansible、NetBox、Proxmox 和 ESXi 采集非敏感事实。
- 记录 observation coverage 和失败类型；遇到认证失败、Schema 校验失败、revision 回退或 secret 风险时，系统应 fail closed（默认拒绝）。
- Scheduled audit（定期审计）发现漂移时，应创建 issue 或 draft PR，而不是删除或静默重写已发布的文档。

### Deferred：有限自治

只有某类低风险变更经过足量 PR 历史、人工抽审、回滚和 post-merge 监测后，才评估自动 merge。首轮 OINK 试点不包含自治发布、生产回写、拓扑生成或 Vault 内容处理。

## 6. Cross-Dimension Insights / 跨维度结论

1. **发布新鲜度与事实新鲜度必须分离。** Pages 刚构建不代表 runtime claim 刚验证；页面同时需要 `built_at` 和 `observed_at/source_revision`。
2. **动态更新不是定期重写。** 成熟单位是 claim/evidence/PR；周期任务负责重新判定状态，只在有可审阅差异时生成补丁。
3. **Agent-friendly 也必须 evidence-friendly。** `.md` 和 `llms.txt` 让模型更容易读取，但准确性来自 machine-readable provenance、状态和 oracle，不来自格式本身。
4. **高覆盖率可能隐藏未知。** 没有 registry 的 claim 不能从分母消失；否则系统可通过“不检查”制造高准确率。
5. **Oink 与 gardening 应可独立删除。** 删除 gardening 后，人工 Markdown 仍可由 OINK 发布；删除 OINK 后，claim registry、evidence 和 PR gate 仍可服务 GitHub 源码文档。

## 7. Recommendations / 建议

1. **批准 OINK 基础试点，但修订现有规范。** 将 OINK 固定版本更新为经 golden build 验证的版本，并把状态/provenance、静态门禁和无特权构建写入验收标准。置信度：中高；本地 golden build 通过后可升为高。
2. **不要把完整 gardening Agent 设为 OINK 上线前置条件。** 先交付 Phase 0，再以少量高价值 claim 验证 Phase 1；这样可以保持试点简单且可逆。置信度：中高；这是范围控制判断，尚无直接比较实验。
3. **用 Jenkins 承担内网 evidence schedule，GitHub Pages 只发布。** Webhook 用于缩短发现延迟，schedule 和 reconciliation 用于保障完整性；两类流程通过脱敏后的 manifest 或 PR 交接。置信度：中高；Jenkins 是本仓库约束下的选择，不是普适结论。
4. **AI 首版只做分析与 draft PR。** 不向 AI 提供生产 API、Vault 或 GitHub merge token；先积累 precision/recall、FP/FN 和 owner review 数据，再讨论有限自治。置信度：高。
5. **采用多维 scorecard，但标记为待验证设计。** 运行一段时间后用人工随机抽审评估其是否真正改善漏报/误报和审阅效率。置信度：中。

## 8. Open Questions / 未决问题

- 首批 claim registry 选哪些文档与字段，需要基于风险和现有漂移样本进行仓库内盘点。
- runtime freshness SLO 应按数据类型确定；需要观察 API 成本、设备可用性和维护节奏。
- Hugo/OINK 的状态 badge、provenance manifest 与 Markdown 输出形态需要小型 golden prototype 验证。
- OINK `v0.7.0` 与 Hugo `v0.165.0` 的完整站点兼容性缺少独立公开测试，必须本地构建验证。
- 五维 scorecard 的阈值与抽审样本量需要试运行数据，不能由研究预先拍定。

## 9. Source Appendix / 来源

| Ref | Supports | Publisher | Published/updated | Accessed | Confidence |
|---|---|---|---|---|---|
| [1] | OINK release/version | [PGSTY/OINK](https://github.com/pgsty/oink/releases/tag/v0.7.0) | 2026-08-25 | 2026-08-26 | High |
| [2] | Markdown and llms.txt outputs | [PGSTY/OINK](https://oink.pgsty.com/zh/docs/customize/agents/) | 2026-08-25 | 2026-08-26 | High |
| [3] | Hugo module/Extended checks | [Hugo Authors](https://gohugo.io/configuration/module/) | 2026-06-18 | 2026-08-26 | High |
| [4] | Page outputs replacement behavior | [Hugo source test](https://raw.githubusercontent.com/gohugoio/hugo/v0.165.0/hugolib/pagesfromdata/pagesfromgotmpl_integration_test.go) | 2026-08 | 2026-08-26 | High |
| [5] | Custom Pages workflow | [GitHub](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) | n.d. | 2026-08-26 | High |
| [6] | CI credential separation | [OpenSSF](https://baseline.openssf.org/versions/devel.html) | current draft | 2026-08-26 | High |
| [7] | Event delivery limits | [AWS](https://docs.aws.amazon.com/eventbridge/latest/ref/event-delivery-level.html) | n.d. | 2026-08-26 | High |
| [8] | Webhook generation/delivery failures | [Stripe](https://docs.stripe.com/webhooks/handle-irrecoverable-events) | n.d. | 2026-08-26 | High |
| [9] | State-version identity | [HashiCorp](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/state-versions) | 2025-05-27 | 2026-08-26 | High |
| [10] | Per-host fact collection | [Ansible Project](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/setup_module.html) | n.d. | 2026-08-26 | High |
| [11] | Proxmox current-view API schema | [Proxmox](https://pve.proxmox.com/pve-docs/api-viewer/) | 2026 | 2026-08-26 | Medium-high |
| [12] | Sensitive information and LLM boundary | [OWASP GenAI](https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/) | 2025 | 2026-08-26 | High |
| [13] | Claim extraction limits | [ACL Anthology](https://aclanthology.org/2025.acl-long.348/) | 2025-07 | 2026-08-26 | High |
| [14] | Real code-doc alignment limits | [IEEE/ACM MSR](https://doi.org/10.1109/MSR66628.2025.00077) | 2025-04-28 | 2026-08-26 | Medium-high |
| [15] | Structured outputs guarantee/limits | [OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs) | continuously updated | 2026-08-26 | High |
| [16] | Constrained shape does not ensure factual performance | [RANLP/Schall and de Melo](https://aclanthology.org/anthology-files/anthology-files/pdf/ranlp/2025.ranlp-1.124.pdf) | 2025 | 2026-08-26 | High |
| [17] | RAG hallucination evidence | [ACL Anthology/RAGTruth](https://aclanthology.org/2024.acl-long.585/) | 2024-08 | 2026-08-26 | High |
| [18] | Automated grader vs maintainer merge gap | [METR](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/) | 2026-03-10 | 2026-08-26 | Medium-high |
| [19] | Production coding-agent PR experience | [Microsoft .NET](https://devblogs.microsoft.com/dotnet/ten-months-with-cca-in-dotnet-runtime/) | 2026-03-23 | 2026-08-26 | Medium-high |
| [20] | Structural validation limits | [JSON Schema](https://json-schema.org/draft/2020-12/json-schema-validation) | 2022-06-16 | 2026-08-26 | High |
| [21] | Terraform validate limits | [HashiCorp](https://developer.hashicorp.com/terraform/cli/commands/validate) | n.d. | 2026-08-26 | High |
| [22] | Multi-dimensional data quality model | [W3C DQV](https://www.w3.org/TR/vocab-dqv/) | 2016-12-15 | 2026-08-26 | Medium-high; recommendation unverified |
| [23] | Provenance verification boundary | [SLSA](https://slsa.dev/spec/v1.2/verifying-artifacts) | v1.2 | 2026-08-26 | High |
| [24] | Required-check and CODEOWNERS limits | [GitHub](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks) | n.d. | 2026-08-26 | High |
| [25] | OINK pinned Hugo requirement | [PGSTY/OINK config](https://raw.githubusercontent.com/pgsty/oink/v0.7.0/hugo.yaml) | 2026-08-25 | 2026-08-26 | High |
| [26] | Webhook ordering and retries | [Stripe](https://docs.stripe.com/webhooks) | n.d. | 2026-08-26 | High |
| [27] | Sensitive values remain in Terraform state | [HashiCorp](https://developer.hashicorp.com/terraform/language/manage-sensitive-data) | 2025-11-19 | 2026-08-26 | High |
| [28] | CODEOWNERS behavior and self-protection | [GitHub](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners) | n.d. | 2026-08-26 | High |
| [29] | Ruleset bypass and status-source controls | [GitHub](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) | n.d. | 2026-08-26 | High |

## 10. Staleness Map / 时效地图

| Claim class | Re-check |
|---|---|
| Hugo `outputs` semantics | 2026-09-23 |
| OINK/Hugo versions and compatibility | 2026-09-25 |
| AI role and autonomy evidence | 2026-11-26 |
| Architecture/integration/verification patterns | 2028-08-26 |

当前无 stale claim；最早复核日期为 **2026-09-23**。版本兼容结论必须在实施时以锁定版本的本地 golden build 再验证。
