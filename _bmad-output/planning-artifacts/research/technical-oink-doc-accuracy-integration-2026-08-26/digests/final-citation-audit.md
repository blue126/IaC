# Final Citation Audit

## Verdict

**PASS WITH MATERIAL CITATION CORRECTIONS**

报告的核心方向仍成立：将展示构建与特权采集隔离、让 AI 只提交可审计草稿、保留 reconciliation、区分结构验证与事实验证，均有相符来源或合理的安全工程推导。但若维持当前引文，不能把全部建议都标为“高置信度”。正文存在 5 处部分 mismatch、2 处因来源无法充分读取而需要降级、若干把设计推导写成来源直接结论的情况。

## Audit Scope

- 仅审计指定 `research.md`，未读取其他本地文件。
- 覆盖正文全部 14 个带编号引用的位置，以及 Source Appendix 的 24 个外部 URL。
- 重点复核 OINK/Hugo 版本与输出语义、CI 凭据隔离、事件完整性、state/fact/API observation、LLM 研究结论、Schema/validation 边界、SLSA、GitHub required checks，以及五项最终建议。
- 24 个 URL 均已尝试访问；[16] 直接抓取发生 transport error，[11] 只返回动态 API viewer 外壳，[14] DOI 落地页只暴露书目信息。外部搜索补救因当前搜索服务未认证而不可用，因此这三项不能视为完成了全文核验。

## Pass

| 正文位置 | 引用 | 结论 | 审计结果 |
|---|---|---|---|
| L18 | [1][2][5][6] | OINK 作为展示平面，特权采集与 Pages/Hugo 构建隔离 | **Pass, inferential.** [1][2] 证明 OINK 版本及静态 Markdown/`llms.txt` 输出；[5] 证明 Pages 可拆分 build/deploy job 并以 artifact 交接；[6] 明确要求不可信代码不能访问特权 CI 凭据且 job 使用最小权限。具体“双平面”架构是这些来源支持的安全设计推导，不是来源原文。
| L20 | [13][14][15][16][17] | AI 适合 claim extraction/草稿，Schema 不证明事实，RAG 不消除无支持陈述 | **Pass with downgrades noted below.** [13] 明确报告受限事实 claim extraction 方法及评估结果；[15] 明确保证 JSON Schema adherence；[17] 明确指出 RAG 后仍会出现 unsupported/contradictory claims，并基于近 18,000 个响应构建语料。整体方向成立。
| L22 | [7][8][9][10][11] | Webhook 不能作为完整性证明，应绑定 revision/observation | **Pass, inferential.** [7] 明确区分 best-effort 与 at-least-once；[8] 明确存在不可恢复的事件生成失败并要求重读相关 API 对齐状态；[9] 提供 state version、workspace、serial、run 和可选 VCS SHA；[10] 明确 facts 是针对 remote hosts 采集。独立 reconciliation 是合理推导。
| L30 | [2][3] | 显式启用 Markdown/`llms.txt`；Hugo 不再执行 Extended 检查 | **Pass.** [2] 明确逐页 `index.md`、Markdown alternate link、每语言 `llms.txt` 均需站点在 `outputs` 中启用；[3] 明确 `extended` 在 v0.153.0 deprecated，v0.153.2 起检查禁用。
| L32 | [4] | page/front matter `outputs` 替换而非追加 | **Pass.** v0.165.0 集成测试中，站点 page outputs 为 HTML+JSON，而页面 `outputs: [html]` 后 JSON 不生成，直接证明 replacement semantics。OINK 文档 [2] 也明确写为整体替换。
| L45 | [5][6][23] | 最小权限、artifact 边界、provenance 不能证明文档事实正确 | **Pass.** [5][6] 支持 job/artifact/最小权限隔离；[23] 的验证范围是 artifact、builder、provenance 和预期参数的真实性/完整性，不覆盖文档命题的现实正确性。
| L57 | [13][15][17] | claim extraction 可评估；structured output 只约束结构；RAG 仍会 hallucinate | **Pass.** 三项来源分别直接支持对应核心命题。`precision-first`、保存 source spans、未检索到记为 `unknown` 属于风险控制推导，应保持为建议语气。
| L59 | [18][19] | 自动 grader 通过不等于 maintainer 接受；生产经验仍以 PR 和人工判断为中心 | **Pass.** [18] 由 4 名 maintainer 审查 3 个仓库的 296 个 AI PR，发现 grader 与 maintainer decision 有显著差距，并明确限制；[19] 报告 878 个 CCA PR，全部由 maintainer 显式发起，强调专家审阅、迭代和最终人工责任。
| L71 | [7][8] | 事件可能重复或漏失，因此需要 reconciliation | **Pass except ordering claim.** [7] 的 at-least-once 支持重复风险，best-effort 支持漏失风险；[8] 直接支持事件可能根本未生成及通过 API 重读恢复一致性。
| L73 | [9][10] | HCP state version 可绑定 revision；Ansible facts 是逐目标观察 | **Pass.** [9] 直接列出 workspace relationship、serial、run relationship、VCS SHA，并允许提交 lineage；[10] 直接描述针对 remote host 的 facts gathering。
| L79 | [20][21] | JSON Schema 和 `terraform validate` 不证明 runtime/业务语义 | **Pass.** [20] 的规范范围是 JSON instance 的结构约束，并说明结构验证可能不足以正确使用值；[21] 明确只检查语法和内部一致性，不验证 remote state/provider APIs。
| L104 | [22] | 多维质量信息和 provenance 可分别表达；特定五维优越性未验证 | **Pass with correct caveat.** DQV 明确建模 dimension、metric、measurement、annotation、policy 与 provenance，支持多维报告方法；它没有比较或推荐正文的特定五维 scorecard。正文已准确披露这一限制。

## Mismatch

| 正文位置 | 引用 | 不匹配内容 | 严重性与处理 |
|---|---|---|---|
| L30 | [1][2][3] | “OINK 声明 Hugo `>=0.160.1 Extended`”未被访问到的 [1] release notes 或 [2] Agent 支持页证明。[2] 只说需要 Hugo Extended；[3] 只说明 Hugo 自身的版本约束机制和 Extended 检查变化。 | **Material partial mismatch.** 精确最低版本 `0.160.1` 必须补一个固定到 v0.7.0 的 OINK module/config source，或将该数字标为未核验。当前不得给此数字 High。
| L71 | [7][8] | “事件可能乱序”未出现在访问到的 AWS delivery-level 页面或 Stripe generation-failure 页面。[7] 支持 best-effort/at-least-once，[8] 支持 generation failure，但两者均未在所引页面说明 ordering。 | **Partial mismatch.** “重复或漏失”可保留高置信度；“乱序”应补官方 ordering 文档或降为一般分布式系统风险推导。
| L75 | [12] | [12] 支持 LLM sensitive-information disclosure、sanitization、least privilege、限制数据源和 redaction，但不支持“Terraform state 可能含凭据”或“`sensitive` 不代表值不在 state”。 | **Material partial mismatch.** LLM 只接收脱敏派生事实的安全建议有支持；Terraform state 的产品特定结论需另引 HashiCorp sensitive-data/state 文档。该段整体不能仅凭 [12] 标 High。
| L73 | [11] | Proxmox API viewer 的抓取结果只有标题，无法从该 URL 的可读内容核验“current-view API schema”，更不能直接证明“逐目标观察而非全局原子快照”。 | **Verification gap.** 结论工程上合理，但 [11] 当前只应算 Medium/Unverified，需固定具体 endpoint 文档或可归档 schema。
| L126 | [24] | [24] 支持 latest SHA、`skipped`/`neutral` 状态、特定 GitHub App 作为 status source，以及 skipped workflow 的阻塞差异；该页不支持 `CODEOWNERS`、bypass 或“自保护边界”。 | **Material partial mismatch.** required-check 子结论通过；CODEOWNERS/bypass/self-protection 必须增加 GitHub branch/ruleset/CODEOWNERS 官方文档，或拆成未引用的设计要求。

## Confidence Downgrades

| Claim / Recommendation | 当前 | 建议 | 原因 |
|---|---:|---:|---|
| L20/L57 “真实 code-doc co-evolution 仍有明显对齐缺口” [14] | Medium-high/隐含 High | **Medium** | DOI URL 只返回论文标题、作者和会议信息，未暴露 abstract/results；题名与主题相关，但本次无法核验结果强度。不能据此确认“明显缺口”的措辞。
| L20/L57 “同类 Schema constrained decoding 只保证形状、不保证语义” [16] | High | **Medium-high** | [15] 足以界定 OpenAI Structured Outputs 的 schema guarantee；[16] 直接访问失败，无法完成独立来源复核。结论本身合理，但“双来源高置信度”不成立。
| Recommendation 1：批准 OINK 基础试点 | High | **Medium-high** | 静态输出与隔离架构证据充分，但精确 Hugo 最低版本未获引用支持，且报告自己承认 OINK v0.7.0/Hugo v0.165.0 完整站点兼容性尚无独立公开测试。完成本地 golden build 后可恢复 High。
| Recommendation 2：gardening Agent 不作为 OINK 前置 | High | **Medium-high** | 这是可逆性和范围控制驱动的架构判断，来源支持风险背景，但没有直接比较研究证明该 rollout 顺序优越。High 应留给 prototype/运行数据验证之后。
| Recommendation 3：Jenkins schedule、Pages 只发布 | High | **Medium-high** | [5][6][7][8] 强力支持权限隔离与 reconciliation；“由 Jenkins 承担”是本地环境选择，不是这些来源验证的普适结论。
| Recommendation 4：AI 首版仅分析和 draft PR | High | **High** | [6][12][17][18][19] 共同支持最小权限、敏感数据边界、RAG 风险、grader/maintainer gap 和 human-owned PR 工作流。虽然具体 token 清单是设计选择，风险结论充分。
| Recommendation 5：采用多维 scorecard，标记待验证 | Medium | **Medium** | [22] 支持多维质量与 provenance 表达，但不证明特定五维组合或优于单分数；正文 caveat 和置信度恰当。
| L126 GitHub required checks/CODEOWNERS 整体安全边界 | 隐含 High | **Medium** | [24] 仅覆盖 required status-check 的部分机制，不能承载 CODEOWNERS、bypass 与自保护全部结论。

## Source-Level Disposition

| Ref | Disposition | 备注 |
|---|---|---|
| [1] | Pass / partial | 证明 v0.7.0 release；不证明精确 Hugo 最低版本。 |
| [2] | Pass | 直接证明显式输出、逐页 Markdown、alternate link、每语言 `llms.txt`、outputs replacement。 |
| [3] | Pass | 直接证明 Extended check 在 v0.153.2+ 被禁用。 |
| [4] | Pass | v0.165.0 integration test 证明 page-level outputs replacement。 |
| [5] | Pass | 证明 Pages artifact 及 build/deploy job/权限模型。 |
| [6] | Pass | 证明 CI 最小权限及不可信 snapshot 与特权凭据隔离。 |
| [7] | Pass / partial | 证明 best-effort 与 at-least-once；不证明 ordering。 |
| [8] | Pass | 证明事件可能无法生成，以及通过 API 重读恢复同步。 |
| [9] | Pass | 证明 state-version identity/revision 字段及 relationships。 |
| [10] | Pass | 证明 remote-host fact gathering。 |
| [11] | Downgrade | 动态 viewer 内容不可审计，不能承载具体 snapshot 语义。 |
| [12] | Pass / mismatch | 支持 LLM 脱敏和最小数据访问；不支持 Terraform state 产品结论。 |
| [13] | Pass | 支持 claim extraction framework、Claimify 与受歧义约束的结果。 |
| [14] | Downgrade | 只能核验书目信息，无法核验实证结果。 |
| [15] | Pass | 支持 schema adherence；其保证范围不包括事实真实性。 |
| [16] | Downgrade | URL transport error，未完成独立核验。 |
| [17] | Pass | 直接证明 RAG 后仍有 unsupported/contradictory claims；近 18,000 responses。 |
| [18] | Pass | 直接证明 automated grader 与 maintainer merge decision gap，并披露样本限制。 |
| [19] | Pass | 直接证明生产 PR 经验以 maintainer 发起、review、iteration 和人工责任为核心。 |
| [20] | Pass | 支持 structural validation 的范围与限制。 |
| [21] | Pass | 明确不验证 remote services，只检查语法与内部一致性。 |
| [22] | Pass with caveat | 支持多维质量/metric/provenance；不验证特定五维方案。 |
| [23] | Pass | 支持 artifact/provenance authenticity 范围及其边界。 |
| [24] | Pass / mismatch | 支持 status source、latest SHA、skipped behavior；不支持全部 CODEOWNERS/bypass 结论。 |

## Residual Risks

- [1][2] 是 OINK 自身发布者资料，能证明声明和功能文档，但不是独立兼容性测试；最终版本兼容性仍必须由锁定版本 golden build 证明。
- [18][19] 的实证对象是 code PR，不是文档 gardening PR。它们支持人工 review gate，但不能直接量化文档任务的 precision、recall、审阅成本或自治阈值。
- [13][17] 分别研究通用事实 claim extraction 与 RAG hallucination，不是基础设施文档的同分布评估。将结果迁移到 IaC 文档时仍需本地金标集。
- [22] 是 W3C Working Group Note，且明确不提供完整、客观的质量定义；它适合支持表示方法，不适合证明 scorecard 的决策效度。
- 安全架构结论依赖实际 workflow 权限、runner trust boundary、artifact integrity、secret handling 和 branch/ruleset 配置。引用证明原则，不证明本仓库未来实现一定符合原则。
