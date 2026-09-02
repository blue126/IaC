# AI/LLM 文档维护：成熟做法与角色边界

**结论（推论）**：截至 2026-08-26，可生产化的不是“让 LLM 证明文档正确”，而是**变更触发、确定性缩小范围、LLM 生成候选、机器验证可执行事实、责任人审批**。成熟单位是 PR/merge，而非定期全库重写。

## 证据与成熟度

**事实**：Emergent 的生产流水线以合并 PR 为触发，检索现有知识库，把差异分为 NEW/INCOMPLETE/OUTDATED，低置信度过滤、建议进入人工队列，批准后才开文档 PR；其自报草稿一分钟内生成、合并到已审建议中位约 4 天，116 项 OUTDATED 修订获批率 83%。这是单一厂商自报，能证明工作流可运行，不能证明通用准确率。[1]

**事实**：纯提示式语义判定仍噪声高。DocPrism 2026-07 修订版报告，直接 LLM 会标记逾 90% 函数；把任务拆成局部类别并外部过滤后，标记率降至 17%、跨四种语言 precision 仅 0.63。[2] METAMON 在 9,482 对 Java 样本上 precision 0.72、recall 0.48。[3] CASCADE 不再信任二元判断，而让 LLM 从文档生成测试，再以执行和“文档生成实现”交叉验证；在额外仓库发现 13 项未知不一致，其中 10 项后来被修复。[4] **推论**：semantic diff 适合 precision-first 的“待复核告警”，不适合静默放行；行为可执行时，应把自然语言判断降级为测试生成器。

**事实**：受限 claim extraction 已较可靠，但完整性没有。ACL 2025 的 Claimify 对“句子是否含事实 claim”达到 91.8% accuracy/91.2% macro-F1，对元素级覆盖为 87.9%/83.7%，并主动放弃歧义项。[5] 相反，CoDocBench 的真实共同改码/改文档数据上，所测模型更新文档的最佳对齐约 58%，严格时序对齐仅约 18%。[6] **推论**：原子 claim、引用位置、符号/API/默认值抽取可自动化；“已抽全”“文档充分描述所有副作用”不可由 LLM 证明。

## Grounding、结构化输出与人工复核

**事实**：Structured Outputs 已解决旧的 JSON/字段漂移问题：OpenAI 当前文档保证所支持 JSON Schema 的形状，但明确提示无关输入可能迫使模型产生合 schema 的幻觉；Google 同类文档也明确“语法正确不等于值在语义上正确”，要求应用校验。[7][8] **推论**：schema 应含 `claim`、`source_span`、`change_anchor`、`confidence`、`unknown_reason`，但不能把 schema-valid 当 truth-valid。

**事实**：RAG 只能提供证据面。RAGTruth 的近 18,000 条人工标注响应显示，接入检索后仍会产生无支持或矛盾陈述；RAGChecker 则发现 claim-level 诊断与人工判断相关性更好，并要求分别评估 retrieval 与 generation。[9][10] GitHub 当前 Copilot application card同样承认漏报、误报、幻觉和不完整反馈，明确要求补充人工 review。[11] **建议**：保存检索集合与 source span；“未检索到”只能输出 unknown，不能输出一致；高风险文档需 owner 审批和 CI/测试证据。

## 可验证的 LLM 角色边界

| 角色 | 允许自动化 | 验收门槛 |
|---|---|---|
| Claim extractor | 从指定 diff/doc 段提取原子主张与锚点 | schema 校验；span 必须逐字存在；金标集测 precision/recall |
| Semantic triager | 对已映射 claim 标记 `contradiction/possibly-stale/unknown` | 按语言/文档类型报告 precision；只允许 precision-first 阻断 |
| Draft editor | 生成最小 FIND/REPLACE 或补丁 PR | 标识符、路径、签名确定性校验；测试/示例执行；人工 merge |
| Fact/completeness judge | **不得**宣称代码真实意图、运行事实或文档完整 | 仅在可执行 oracle、权威配置/契约或责任人签署后升级为 verified |

## 来源

1. Emergent（Ketan），2026-08-21，accessed 2026-08-26，https://emergent.sh/blog/our-knowledge-base-is-code
2. Xu et al./arXiv（将发表于 ACM ISSTA 2026），2026-07-29，accessed 2026-08-26，https://arxiv.org/abs/2511.00215
3. Lee et al./arXiv（LLM4Code 2025），2025-02-05，accessed 2026-08-26，https://arxiv.org/abs/2502.02794
4. Kiecker et al./arXiv（FSE 2026），2026-04-21，accessed 2026-08-26，https://arxiv.org/abs/2604.19400
5. Metropolitansky & Larson/ACL，2025-07，accessed 2026-08-26，https://aclanthology.org/2025.acl-long.348/
6. Pai et al./IEEE-ACM MSR，2025-04-28，accessed 2026-08-26，https://doi.org/10.1109/MSR66628.2025.00077
7. OpenAI API Docs，持续更新（页面快照 2026-08-26），accessed 2026-08-26，https://developers.openai.com/api/docs/guides/structured-outputs
8. Google AI for Developers，持续更新（页面快照 2026-08-26），accessed 2026-08-26，https://ai.google.dev/gemini-api/docs/generate-content/structured-output
9. Niu et al./ACL，2024-08，accessed 2026-08-26，https://aclanthology.org/2024.acl-long.585/
10. Ru et al./arXiv（Amazon Science），2024-08-17，accessed 2026-08-26，https://arxiv.org/abs/2408.08067
11. GitHub Docs，持续更新（页面快照 2026-08-26），accessed 2026-08-26，https://docs.github.com/en/copilot/responsible-use/code-review
