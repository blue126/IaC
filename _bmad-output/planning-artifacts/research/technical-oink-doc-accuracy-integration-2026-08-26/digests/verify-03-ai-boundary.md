# Fresh-context verification: AI 文档维护边界

核验日期：2026-08-26  
核验范围：仅以 `03-ai-doc-maintenance.md` 为待核验 digest；以下证据未复用该 digest 的来源。检索时主动寻找能证明“完整性判断”或“无人工自治发布”可靠的反例。

## 结论

| Ref | Status | 结论 | 置信度 |
|---|---|---|---|
| A | VERIFIED WITH SCOPE | LLM 适合受限 claim extraction 和候选草稿；在没有封闭且权威的参考事实全集时，不能证明事实完整性。 | High (0.91) |
| B | VERIFIED | Structured output / constrained decoding 可保证受支持约束下的 shape 或语法，不保证字段值真实、语义正确或行动安全。 | Very high (0.97) |
| C | QUALIFIED | “确定性验证 + PR 审批”是当前可辩护的默认生产基线，但“所有变更都必须人工审批、绝不可自治发布”证据不足；低风险、封闭范围可在策略门控和持续监测下逐步获得自治权限。 | Medium-high (0.82) |

## A. Claim extraction 不等于完整性证明

**Status：VERIFIED WITH SCOPE**

**独立来源**

1. Ullrich, Mlynář, Drchal, *Claim Extraction for Fact-Checking: Data, Models, and Automated Metrics*，arXiv:2502.04955，2025。https://arxiv.org/html/2502.04955
2. Liu et al., *VERIFACT: Enhancing Long-Form Factuality Evaluation with Refined Fact Extraction and Reference Facts*，EMNLP 2025。https://aclanthology.org/2025.emnlp-main.905.pdf
3. Dejl et al., *Comprehensiveness Metrics for Automatic Evaluation of Factual Recall in Text Generation*，Findings of ACL 2026。https://aclanthology.org/2026.findings-acl.1744.pdf

**理由**

- Ullrich et al. 显示现代模型生成的单条 claim 在 atomicity、fluency、decontextualization、faithfulness 上表现较好，支持把 LLM 用作 claim 候选提取器；但最佳系统的综合 `F_fact` 仅 0.64，并存在 coverage 与 focus 的明显权衡。这直接否定“能可靠抽全”的强说法。
- VERIFACT 对已有 fact-extraction 流程的人工分析发现，12.68% 的抽取事实不完整，且每个回答平均遗漏 1.24 个事实；增加 refinement 后，遗漏事实虽下降 37%，仍未归零。作者同时承认 recall 依赖参考事实集本身的完整性。
- Dejl et al. 明确指出，开放任务中几乎不可能确定一个“应包含的原子事实全集”；其完整性度量只有在预先给定、假定覆盖关键事实的 corpus 后才变得可处理，而且错误分析仍包括 `MISS_ATOM` 和遗漏相关陈述。
- 找到的最强反例是：当事实宇宙被封闭为权威 corpus、API schema、配置契约或测试 oracle 时，可以自动估算乃至确定相对于该集合的 coverage。这不是 LLM 自己证明开放世界完整性，而是外部参考集把问题改造成有限集合比对。
- 因此，A 应理解为能力和证据边界，而非“LLM 永远不能参与 completeness evaluation”。它能抽取、起草并估算 coverage，但不能单独证明参考集合之外没有遗漏。

## B. Structured output 只约束 shape，不保证 truth

**Status：VERIFIED**

**独立来源**

1. Schall, de Melo, *The Hidden Cost of Structure: How Constrained Decoding Affects Language Model Performance*，RANLP 2025。https://aclanthology.org/anthology-files/anthology-files/pdf/ranlp/2025.ranlp-1.124.pdf
2. Geng et al., *Generating Structured Outputs from Language Models: Benchmark and Studies*，arXiv:2501.10868。https://arxiv.org/html/2501.10868
3. *When JSON Is Not Enough: Semantic Reliability of Schema-Constrained LLM Ordering Agents*，arXiv:2607.18261，2026。https://arxiv.org/abs/2607.18261

**理由**

- Constrained decoding 的机制是屏蔽会违反 grammar/schema 的 token；它证明的是输出属于允许的形式语言，而不是字段陈述与外部世界一致。
- Schall 与 de Melo 在 11 个模型上的实验显示，结构约束下输出可以保持格式有效却事实错误，且部分 instruction-tuned 模型的任务表现会下降。
- JSONSchemaBench 将 schema compliance、schema feature coverage 和 downstream quality 分开评估，本身就说明结构有效性与任务正确性不是同一性质；其结果最多显示 constrained decoding 有时改善任务质量，而不是提供语义保证。
- OrderBench 提供直接反例：最强被测模型在 schema validity 为 100% 时，semantic success 仅约 81%；较弱模型同样 100% schema-valid，却出现两位数 unsafe acceptance。即使该研究为单领域、合成 benchmark，它足以反证逻辑命题“schema-valid ⇒ truth-valid”。
- 未找到任何结构化输出技术能在没有领域 oracle、证据核验或业务规则验证器时给出 truth guarantee。更强 decoding 方法改善准确率，不改变保证的类型。

## C. 默认生产模式与自治发布边界

**Status：QUALIFIED**

**独立来源**

1. Whitfill / METR, *Many SWE-bench-Passing PRs Would Not Be Merged into Main*，2026-03-10。https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/
2. Toub / Microsoft .NET, *Ten Months with Copilot Coding Agent in dotnet/runtime*，2026-03-23。https://devblogs.microsoft.com/dotnet/ten-months-with-cca-in-dotnet-runtime/
3. NIST, *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile*，NIST AI 600-1，2024。https://doi.org/10.6028/NIST.AI.600-1
4. PagerDuty Engineering, *Before AI Ships Code, Show Me the Receipts*，2026-07-08。https://www.pagerduty.com/eng/before-ai-ships-code-show-me-the-receipts/
5. kai-linux, *Agent OS autonomous multi-agent PR workflow case study*，2026，项目自报。https://github.com/kai-linux/agent-os/discussions/167

**理由**

- METR 让仓库维护者复核已通过 SWE-bench 自动 grader 的 agent PR；维护者 merge 判断平均比自动 grader 低约 24 个百分点。自动测试通过并不能覆盖代码质量、边界条件、架构适配和需求判断，因此支持“确定性验证之后仍需独立审批”的当前默认值。
- `.NET/runtime` 是更接近生产的正面证据：878 个 Copilot Coding Agent PR 中 535 个合并，合并后可识别 revert 率为 0.6%，未显出明显质量红旗。但每个任务由有 maintainer 权限的人明确发起，工作流仍以 PR 和人的判断为中心；作者明确主张 AI 加速 review mechanics，而不是替代 human judgment。这支持“候选 + 验证 + 审批”能大规模运行。
- NIST AI 600-1 要求测试、评估、验证与核验（TEVV）、风险相称的独立评估、明确 human-AI oversight 责任。它支持确定性验证和治理，但没有规定每一个低风险发布都必须人工逐项批准。
- 最强自治反例来自真实但自报的小型系统：Agent OS 报告 24 天内无人工干预合并 59+ PR、PR merge rate 91%，以测试和 CI 绿灯自动合并；同时它记录了一个已自动合并的细微错误引发 8+ 个级联 issue。该案例证明自治发布“可运行”，但不能证明其错误率、长期维护性或对成熟生产仓库的普适可靠性。
- PagerDuty 给出比“永久人工审批”更强、也更精确的目标模式：按变更类型与影响等级积累 changeless-approval、revert、rollback、incident 等证据，只有显式策略覆盖且越过阈值的组别才获得自动批准，其余继续人工 review；截至文章发布，该系统仍只收集证据，尚未执行自治 merge。
- 因而 C 的强版本过度概括。当前证据支持：默认采用确定性验证、可审计 PR 和人工 owner 审批；只有对低风险、封闭、可回滚且已有足量历史证据的变更，才可由明确策略授予有限自治，并持续抽样复核、监测 post-merge outcome 和保留撤权机制。没有找到足以支持“通用 AI 文档维护可直接自治发布”的独立生产质量证据。

## 最终判定

- A：保留，但应明确“相对于开放事实空间不能证明完整；相对于封闭权威集合可以度量 coverage”。
- B：原 claim 可直接保留。
- C：改写为风险分层原则，不应写成无例外禁令。推荐表述：**生产默认是确定性验证、可审计 PR 与人工审批；自治发布仅限经历史证据证明的低风险类别，并受显式策略、回滚、持续监测与抽样人工复核约束。**
