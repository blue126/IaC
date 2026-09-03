# Fresh-context 核验：证据调度

核验日期：2026-08-26

核验方法：仅以 `02-evidence-scheduling.md` 为待核验摘要；另找不同发布方及不同底层机制的一手材料进行反证式交叉核验。`status` 区分厂商明示事实与由事实推出的架构约束。

## A

- **ref**: A
- **claim**: 定时 reconciliation 必须承担完整性主线，webhook 只能用于加速。
- **status**: **VERIFIED_WITH_SCOPE（成立，但“必须”限于要求最终完整、可自愈的同步系统）**
- **来源**:
  - Amazon Web Services, *Delivery level for AWS service events*, accessed 2026-08-26: https://docs.aws.amazon.com/eventbridge/latest/ref/event-delivery-level.html
  - Stripe, *Receive Stripe events in your webhook endpoint*, accessed 2026-08-26: https://docs.stripe.com/webhooks
  - Stripe, *Handle webhook event generation failures*, accessed 2026-08-26: https://docs.stripe.com/webhooks/handle-irrecoverable-events
- **理由**: AWS 明确区分 best-effort 与 durable 事件，前者在少数情况下可能根本未送达，后者也只是至少一次；因此事件消费者还要处理重复，不能从“收到的事件集合”证明“源端对象集合已完整覆盖”。Stripe 提供了更强的反例：事件可能无法生成，届时既不能 webhook 投递，也不会出现在 List Events API；其官方恢复路径是重新轮询权威对象 API 以重新对齐状态。Stripe 同时说明 webhook 重试有期限、可能乱序及重复。故 webhook 可降低发现延迟并触发定向读取，但无法独立给出全量覆盖证明。若系统的目标包含最终完整性、漏事件修复和漂移收敛，就需要一个不依赖事件生成/投递成功的独立 reconciliation 通道；周期全量或可证明覆盖的增量扫描是该通道的主线。若业务明确接受永久漏报，则“必须”不成立，但这不符合本 claim 的完整性前提。
- **置信度**: **高（0.96）**

## B

- **ref**: B
- **claim**: HCP state revision 可绑定，而 Ansible/Proxmox 需自行记录 observation revision。
- **status**: **VERIFIED_WITH_QUALIFICATION（能力差异成立；“自行记录 observation revision”是必要的 provenance 设计推论，不是厂商规范中的同名要求）**
- **来源**:
  - HashiCorp, *State versions API reference*, accessed 2026-08-26: https://developer.hashicorp.com/terraform/cloud-docs/api-docs/state-versions
  - Ansible Core Team, *ansible.builtin.setup module*, accessed 2026-08-26: https://docs.ansible.com/ansible/latest/collections/ansible/builtin/setup_module.html
  - Proxmox Server Solutions GmbH, generated *Proxmox VE API schema* (`apidoc.js`), accessed 2026-08-26: https://pve.proxmox.com/pve-docs/api-viewer/apidoc.js
  - W3C, *PROV-O: The PROV Ontology*, W3C Recommendation, 2013-04-30: https://www.w3.org/TR/prov-o/
- **理由**: HCP 的底层 API 把每份 state 暴露为有独立 `state-version` resource ID 的对象，并提供 workspace relationship、单调 `serial`、`lineage`、创建时间、run relationship 与可选 VCS commit SHA；按 state-version ID 读取可绑定到具体保存版本，而不是含糊的“当前状态”。Ansible `setup` 的返回契约是每台目标机的 `ansible_facts` 字典，可选择 `machine_id`、`date_time` 等 subset；它描述的是逐主机采集结果，没有跨主机 snapshot/version 标识。Proxmox 生成的 API schema 对 `/cluster/resources` 等读取接口描述当前资源记录；schema 中虽有部分配置文件 `digest` 用于并发修改保护，但没有覆盖所有资源与 endpoint 的全局、不可变 snapshot revision。局部 config digest 不能冒充集群观测 revision。W3C PROV 将实体生成时间、生成活动、revision/derivation 关系作为 provenance 的独立属性，这支持在上游不提供统一版本时由采集方创建观测实体并记录 `observed_at`、采集运行 ID、范围/成功集以及响应摘要。限定：不能用“文档中未找到字段”严格证明未来或私有接口永远不存在该能力；结论针对当前公开接口契约，且 `observation revision` 应理解为采集方版本，不宣称观测跨主机/跨 endpoint 原子。
- **置信度**: **中高（0.88）**

## C

- **ref**: C
- **claim**: raw Terraform state 与日志不能进入 LLM。
- **status**: **VERIFIED_AS_SECURITY_CONTROL（作为默认数据边界成立；不是关于所有 LLM 服务必然留存/训练输入的事实断言）**
- **来源**:
  - GitLab, *GitLab-managed Terraform/OpenTofu state*, accessed 2026-08-26: https://docs.gitlab.com/user/infrastructure/iac/terraform_state/
  - OWASP GenAI Security Project, *LLM02:2025 Sensitive Information Disclosure*, 2025, accessed 2026-08-26: https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/
  - OWASP Cheat Sheet Series, *Logging Cheat Sheet*, accessed 2026-08-26: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
  - Microsoft, *Data, privacy, and security for Foundry Models sold by Azure*, updated 2026-06-05, accessed 2026-08-26: https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy
- **理由**: GitLab 独立确认 state 可能包含密码、私钥、API token 与数据库连接串，并明确 `sensitive` 仅阻止 CLI/plan 展示，值仍留在 state。OWASP 的日志指南要求 access token、密码、连接串、加密密钥及高于日志系统安全级别的数据通常不得直接记录，并指出日志本身可能含技术秘密。OWASP LLM02 又要求限制模型数据源、最小权限，并在模型处理前清洗、遮蔽或 tokenization 敏感内容；仅靠 system prompt 的“不泄露”限制可能被 prompt injection 绕过。Microsoft 的服务说明进一步证明输入 prompt 和 augmented data 确实会被模型服务处理，某些 stateful 功能会持久化内容，滥用监控条件下还可能存储样本供审查；即使其受管服务承诺默认不用于基础模型训练，也不消除处理、留存配置、权限和误披露风险。因此 raw state 和未经字段级筛选的日志不应进入 LLM trust boundary；应先在确定性管道中 allowlist、摘要化和脱敏，只把完成任务所需的非敏感派生事实交给模型。限定：经验证不含秘密的结构化日志片段或脱敏后的 state 派生元数据不属于这里的“raw”。
- **置信度**: **高（0.95）**

## 总体状态

**PASS_WITH_QUALIFICATIONS**：三项 load-bearing claims 均有独立底层证据支撑；A、C 的绝对措辞应保留其完整性/安全边界前提，B 应明确 observation revision 是采集方 provenance，而非上游提供的原子 revision。
