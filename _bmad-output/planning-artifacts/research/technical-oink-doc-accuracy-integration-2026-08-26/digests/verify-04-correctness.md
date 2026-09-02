# Fresh-context verification: correctness gates

**核验范围：** 仅以 `04-correctness-gates.md` 提供待核验声明；结论证据均来自本轮独立访问的外部来源。  
**核验日期：** 2026-08-26

## A

- **ref:** A
- **claim:** 准确性需要 claim-specific oracle，schema/lint 不等于语义正确。
- **status:** verified
- **来源:** JSON Schema, *JSON Schema Validation: A Vocabulary for Structural Validation of JSON*, Internet-Draft, 2022-06-16, accessed 2026-08-26, https://json-schema.org/draft/2020-12/json-schema-validation
- **来源:** HashiCorp, *terraform validate command*, current documentation, accessed 2026-08-26, https://developer.hashicorp.com/terraform/cli/commands/validate
- **来源:** Barr, Harman, McMinn, Shahbaz and Yoo, *The Oracle Problem in Software Testing: A Survey*, IEEE Transactions on Software Engineering 41(5), 2015, DOI metadata accessed 2026-08-26, https://doi.org/10.1109/TSE.2014.2372785
- **理由:** JSON Schema 规范把其核心能力明确限定为对实例数据的结构约束，并直接说明结构验证可能不足以让应用正确使用值；即使启用 `format` assertion，最低要求仍是句法检查，不要求验证邮箱、URL 等实体真实存在。HashiCorp 同样明确说明 `terraform validate` 只检查语法有效性和内部一致性，不检查 remote state 或 provider API，并要求用具体运行上下文中的 `plan` 做进一步验证。IEEE 综述将判断程序行为是否正确所需的预期结果来源归为 test-oracle problem。三者合起来支持：检查结果只能回答其 oracle 所定义的问题；结构、lint 或内部一致性通过不能外推为业务或运行语义正确，语义声明必须绑定能够判定该声明的规范、实现、执行结果或其他专用 oracle。
- **置信度:** high

## B

- **ref:** B
- **claim:** required checks/CODEOWNERS 仍有 skipped/bypass 等边界，必须显式硬化。
- **status:** verified
- **来源:** GitHub, *Troubleshooting required status checks*, current documentation, accessed 2026-08-26, https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
- **来源:** GitHub, *Available rules for rulesets*, current documentation, accessed 2026-08-26, https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
- **来源:** GitHub, *About code owners*, current documentation, accessed 2026-08-26, https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- **理由:** GitHub 明确把 `success`、`skipped`、`neutral` 都列为成功 check 状态；条件跳过的 job 报 `Success`，依赖失败 job 的下游 job 可能被跳过且不阻断合并，而被路径、分支或提交信息过滤掉的 required workflow 会保持 Pending。Ruleset 文档明确允许角色、团队或 GitHub App 获得 bypass，并说明选择 `any source` 时任何有写权限的人或集成都可设置状态；loose checks 不要求分支基于最新 base。CODEOWNERS 文档明确说明 code-owner approval 是可选门禁、非法行会被跳过、无效或权限不足 owner 不会被分配、多 owner 中任一批准即满足，而且要保护 CODEOWNERS 自身才可防止未授权改写。因此仅“启用 required check/存在 CODEOWNERS”不足以证明门禁闭合，需显式配置触发覆盖、失败传播、预期状态来源、bypass、最新提交审批和 CODEOWNERS 自保护。这里的“必须”是达到不可静默绕过这一安全目标所需的工程结论，不是 GitHub 对所有仓库的强制规范。
- **置信度:** high

## C

- **ref:** C
- **claim:** coverage/accuracy/unknown/stale/provenance 分开报告优于单一分数。
- **status:** unverified
- **来源:** Statistics Canada, *Statistics Canada Quality Guidelines: Data quality evaluation*, archived official guidance, modified 2015-11-27, accessed 2026-08-26, https://www150.statcan.gc.ca/n1/pub/12-539-x/2009001/quality-qualite-eng.htm
- **来源:** W3C, *Data on the Web Best Practices: Data Quality Vocabulary*, Working Group Note, 2016-12-15, accessed 2026-08-26, https://www.w3.org/TR/vocab-dqv/
- **来源:** European Commission Joint Research Centre, *Step 6: Weighting*, updated 2020-12-01, accessed 2026-08-26, https://knowledge4policy.ec.europa.eu/composite-indicators/toolkit_en/navigation-page/10-step-guide_en/step-6-weighting_en
- **理由:** Statistics Canada 指南称单一一维质量指数通常被认为难以编制，并分别讨论 timeliness、accuracy、coherence、coverage 等指标；W3C DQV 以独立 dimension、metric、measurement 和 provenance 表达质量，而非规定一个总分；欧盟 JRC 指出复合指标权重会显著影响总值和排名，且权重本质上包含价值判断。这些来源支持“保留维度可见性、避免不透明聚合”的设计动机，但没有直接比较该五项拆分方案与单一分数的决策效果，也没有证明这五项完备或普遍更优。因此该声明仍是有依据的设计建议，不能升级为已验证事实。
- **置信度:** medium-high

## Verdict

- **A:** verified
- **B:** verified
- **C:** unverified（有官方方法论支持其设计动机，但缺少对指定五维报告方案“优于单一分数”的直接证据）
