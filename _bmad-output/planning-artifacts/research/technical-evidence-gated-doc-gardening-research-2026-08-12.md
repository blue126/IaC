---
stepsCompleted: [1, 2]
inputDocuments:
  - '_bmad-output/specs/spec-doc-gardening-agent/SPEC.md'
  - '_bmad-output/specs/spec-doc-gardening-agent/evidence-model.md'
workflowType: 'research'
lastStep: 2
research_type: 'technical'
research_topic: 'Evidence-gated doc-gardening for the IaC repository'
research_goals: 'Research a repository-specific agent implementation model and resolve the four open questions in SPEC.md without implementing code.'
user_name: 'Will'
date: '2026-08-12'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-08-12
**Author:** Will
**Research Type:** technical

---

## Research Overview

## Technical Research Scope Confirmation

**Research Topic:** Evidence-gated doc-gardening for the IaC repository

**Research Goals:** Research a repository-specific agent implementation model and resolve the four open questions in SPEC.md without implementing code.

**Technical Research Scope:**

- Architecture Analysis — agent runtime, evidence collection, gate, escalation, and PR lifecycle
- Implementation Approaches — active-code criteria, claim model, retry policy, audit strategy, and agent contract
- Technology Stack — Jenkins, GitHub, Terraform, Ansible, infrastructure APIs, and candidate agent runtimes
- Integration Patterns — Terraform state/HCP, Proxmox, ESXi, NetBox, Ansible inventory, and GitHub PR integration
- Performance and Safety — read-only production access, load control, concurrency, credential isolation, evidence retention, and failure recovery

**Research Methodology:**

- Current web data with rigorous source verification
- Primary and official sources for technical claims
- Multi-source validation for load-bearing recommendations
- Explicit separation of facts, inferences, recommendations, and unresolved decisions
- Repository-local evidence used to constrain the recommendation

**Scope Confirmed:** 2026-08-12

---

## Technology Stack Analysis

### Programming Languages

**推荐语言：Python 3.12。** 当前仓库已将 Python 3.12 用于 Ansible 与辅助脚本，`requirements.txt`、`.devcontainer/` 和 `scripts/` 已形成 Python 运行基础。V1 用 Python 编写 deterministic controller 与 collectors，可直接调用 Terraform/Ansible CLI、HTTP APIs、SQLite、JSON Schema/Pydantic，并避免引入第二种业务编排语言。

Groovy 继续只承担 Jenkins Pipeline orchestration；Shell 只用于受控命令封装。TypeScript 虽是官方 `openai/codex-action` 的实现语言，但本项目无需为调用 Action 或 GitHub API 引入 Node application layer。

_Popular Languages:_ Python（controller/collectors）、Groovy（Jenkinsfile）、Shell（受控 CLI glue）  
_Emerging Languages:_ 当前问题没有需要 Rust/Go 的性能或部署约束  
_Language Evolution:_ 维持仓库现有 Python-first automation，减少运行环境分裂  
_Performance Characteristics:_ 工作负载受网络/API/LLM 延迟主导，Python 性能足够；正确性、可测试性和 SDK 兼容性更重要  
_Local evidence:_ `requirements.txt`, `.devcontainer/devcontainer.json`, `Jenkinsfile`, `scripts/`

### Development Frameworks and Libraries

**V1 首选官方 `openai-codex` Python SDK，而不是单独依赖 prompt + shell，也不先引入多-agent framework。** 官方 SDK 要求 Python ≥3.10，提供 thread start/resume/fork、turn-level sandbox override、structured `output_schema`、streaming，以及单客户端并发 active turns。需要注意，turn 上的 sandbox override 会作用于该 turn 及后续 turns，因此 controller 必须对每个安全阶段显式设置或重置 sandbox。由此可将 analysis 阶段固定为 `read_only`，仅把通过 gate 的单一文档修复交给隔离 worktree 中的 `workspace_write` 阶段。[OpenAI Codex Python SDK API](https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md)

本机的 `codex-cli 0.146.0` 已验证支持非交互式 `codex exec`、JSONL event 输出 `--json`、`--output-schema`、`--output-last-message` 与 sandbox 参数，因此 CLI 可用于早期 PoC；但调度、跨时段业务状态、证据门禁和发布授权仍必须由外部 controller 负责。[Codex CLI source: exec options](https://github.com/openai/codex/blob/main/codex-rs/exec/src/cli.rs)

OpenAI Agents SDK 提供 handoffs、guardrails、sessions、human-in-the-loop、MCP 和 tracing，适合未来的多-specialist orchestration。V1 仅包含“分析”和“受限编辑”两个阶段，直接引入该框架会增加运行状态与安全边界复杂度。作为本项目的设计原则，SDK session 不作为业务事实账本，guardrail 也不替代 deterministic evidence gate。[OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)

所有进入 deterministic gate 的 LLM 最终输出都应先解析，再用 Pydantic 或明确版本的 JSON Schema 做本地验证；runtime 接受 `output_schema` 只约束输出形状，不能替代 controller 侧校验，更不能证明事实完整性。JSON Schema 当前正式版本为 2020-12，规范分为 Core 与 Validation，可作为 agent/controller 间的版本化契约。[JSON Schema specification](https://json-schema.org/specification) 截至 2026-08-12，Codex 官方仓库仍有一个开放 bug 报告指出：在 CLI 0.125.0 的 `codex exec --json --output-schema` 流中，中间 `agent_message` 也可能被最终输出 schema 塑形。因此实现应 pin SDK/CLI 版本、只消费明确的最终结果，并对目标版本执行输出契约回归测试；该 issue 本身不足以证明 0.146.0 或 Python SDK 仍受影响。[OpenAI Codex issue #19816](https://github.com/openai/codex/issues/19816)

_Major Frameworks:_ Codex Python SDK + Python controller  
_Micro-frameworks:_ Pydantic/JSON Schema；标准库 `sqlite3`；HTTP client 由实现阶段选择  
_Evolution Trends:_ 多-agent SDK 保留到确有 handoff/HITL/durable orchestration 需求时再引入  
_Ecosystem Maturity:_ Codex SDK 满足 coding-agent worker；Jenkins/Python/CLI 与当前仓库最匹配

### Database and Storage Technologies

V1 需要两类不同存储，不能把 Codex thread 或 Jenkins console log 当成事实账本：

1. **SQLite retry ledger**：记录 claim identity、source revision、observation attempts、timestamps、normalized outcomes、gate state、PR/upgrade correlation。SQLite 是进程内、serverless、zero-configuration、transactional 的单文件数据库，适合当前单 Jenkins controller、低并发工作负载。[SQLite overview](https://www.sqlite.org/about.html)
2. **Immutable evidence bundle**：每次 observation 生成 schema-versioned、脱敏 JSON，带来源 hash、采集时间和 collector version；作为 Jenkins build artifact 保存，并由 ledger 引用。Jenkins 官方 `archiveArtifacts` 能随 build 保存可下载 artifact，但其寿命受 build retention 影响，因此 retention 必须在架构阶段明确。[Jenkins archiveArtifacts](https://www.jenkins.io/doc/pipeline/steps/core/)

不推荐 V1 新建 PostgreSQL/Redis：当前没有多 controller、高写并发或分布式锁需求。若未来 controller 横向扩展，再评估 server database。SQLite WAL 可提升本机读写并发，但不能放在 network filesystem；V1 应把数据库放在 Jenkins persistent local volume。[SQLite WAL](https://www.sqlite.org/wal.html)

原始 Terraform state 不得作为普通 evidence bundle 交给 LLM。HashiCorp 明确说明 `terraform show -json` 会以明文显示 sensitive values；collector 必须按 allowlist 提取所需资源字段并脱敏。[Terraform show](https://developer.hashicorp.com/terraform/cli/commands/show)

_Relational Database:_ SQLite，V1 单 controller 状态账本  
_NoSQL / In-memory:_ 不需要；JSON 是证据交换格式，不是唯一 durable state  
_Data Warehousing:_ 不需要  
_Artifact Storage:_ Jenkins archived, redacted evidence bundles；GitHub PR 只保存人类可审阅摘要

### Development Tools and Platforms

**Deterministic evidence tools：**

- Terraform：`terraform show -json` 可将 state 或已保存 plan 转换为面向外部软件的机器可读 JSON。HCP Terraform 可通过 current-state-version endpoint 获取当前 state-version 元数据，并从其下载 URL 获取 state；Terraform 1.3+ 创建的 state 可提供稳定 JSON 下载格式。HCP 也提供 plan JSON endpoint，但其下载 URL 临时有效且有 token/权限限制。collector 应使用这些文档化接口、检查格式版本与异步处理状态，而不是直接解析原始 state 文件或 human-readable CLI output。[Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format) [HCP state versions API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/state-versions) [HCP plans API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/plans)
- Ansible：`ansible-inventory --list` 或 `--host` 可输出 Ansible 解析后的 inventory 数据，`--graph` 可展示 inventory 关系图。`ansible-playbook --check --diff` 只能作为补充证据：check mode 是模拟，不支持它的模块不会执行或报告，依赖已注册结果的条件任务也可能缺失输出；diff 仅适用于支持它的模块，并可能泄露敏感内容。[ansible-inventory](https://docs.ansible.com/projects/ansible-core/devel/cli/ansible-inventory.html) [Ansible check/diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)
- NetBox：REST API 主要使用 token authentication；token 可关闭 write ability，并可限制允许的 client IP。GraphQL API 是 read-only 查询接口，使用同一套 token authentication。V1 collector 应使用专用、最小用户权限、write-disabled 的 token，并在 NetBox 4.5+ 优先采用 v2 token。[NetBox REST API](https://netbox.readthedocs.io/en/stable/integrations/rest-api/) [NetBox GraphQL API](https://netbox.readthedocs.io/en/stable/integrations/graphql-api/)
- Proxmox VE：其 JSON/JSON-Schema REST API 可作为直接资源证据源。collector 应使用启用 privilege separation 的专用 API token，并通过路径级 ACL 与只读角色（例如适用范围内的 `PVEAuditor`）实施最小权限；token 的有效权限不会超过 backing user，且在 privilege separation 下还受 token 自身 ACL 限制。具体 endpoint 与 ACL path allowlist 留待 integration research 确定。[Proxmox VE Administration Guide](https://pve.proxmox.com/pve-docs/pve-admin-guide.pdf)

**Agent and publishing tools：**

- Jenkins Declarative Pipeline 已是仓库现有执行平台。官方支持 cron、`disableConcurrentBuilds`、timeout、build retention 与 credentials binding；它适合内网调度，但 credentials masking 只是 best effort，归档前必须由 collector 脱敏。[Jenkins Pipeline syntax](https://www.jenkins.io/doc/book/pipeline/syntax/) [Using a Jenkinsfile](https://www.jenkins.io/doc/book/pipeline/jenkinsfile/)
- GitHub App 是长期无人值守发布身份的首选。每次 publisher run 临时签发约一小时有效的 installation token，并在签发请求中显式限定目标仓库和最小 permissions；否则 token 会继承 installation 可访问的仓库和 App 已获权限。创建 branch 需要 `Contents: write`，创建 PR 需要 `Pull requests: write`。[GitHub App token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app) [Git refs API](https://docs.github.com/en/rest/git/refs) [Pull requests API](https://docs.github.com/en/rest/pulls/pulls)
- `openai/codex-action@v1` 是未来 GitHub-native 替代方案，支持 output schema，并可通过 `permission-profile` 限制文件系统/网络权限、通过 `safety-strategy` 降低进程权限（默认 `drop-sudo`）；但 GitHub-hosted runner 通常无法直接访问 homelab 内网，仍需 self-hosted runner 或 private networking。[OpenAI Codex Action](https://github.com/openai/codex-action) [Codex Action security](https://github.com/openai/codex-action/blob/main/docs/security.md)

_IDE and Editors:_ 不参与运行时设计  
_Version Control:_ Git worktree/automation branch + GitHub draft PR  
_Build Systems:_ Jenkins Pipeline  
_Testing Frameworks:_ Python unit/contract tests、fixture-based collector tests、JSON Schema validation；具体框架在 architecture/implementation planning 决定

### Cloud Infrastructure and Deployment

**推荐控制平面：现有 Jenkins，而非新建 GitHub Actions evidence collector。** 本项目的关键生产接口位于 homelab 内网；Jenkins 已有 Terraform、Ansible 和凭据集成，而 GitHub-hosted runner 要获得同等访问能力仍需 self-hosted runner/private networking。GitHub Actions `schedule` 还可能在高负载时延迟，严重时 queued job 被丢弃，因此不应把其时间精度当成 evidence retry guarantee。[GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)

Jenkins cron 使用 `H` 对计划时刻做基于 job 名称的稳定散列以分散负载，并为 gardening job 启用 `disableConcurrentBuilds()`，使重叠 build 排队。跨时段 observation 由新 run + durable ledger 实现；这是本项目的设计结论，不能用同一次 Pipeline 的立即 `retry()` 伪装，也不能依赖不能跨 run 的临时状态。[Jenkins Pipeline syntax](https://www.jenkins.io/doc/book/pipeline/syntax/)

GitHub 仅承担 source control、branch、PR 和 review boundary。V1 不自动 merge；但需要注意 `Contents: write` 也足以调用 PR merge endpoint，因此必须在 default branch 上要求 PR review/required checks、启用不允许绕过（或确保 publisher App 不在 bypass list），并由 controller 对可调用 publisher 的任务与仓库做 allowlist；不能只依赖 token scope。[GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) [GitHub pull requests API](https://docs.github.com/en/rest/pulls/pulls)

_Major Cloud Providers:_ 无新增需求  
_Container Technologies:_ 可用隔离 Jenkins agent/container 固化 collector 与 Codex runtime；不是 V1 的业务目标  
_Serverless Platforms:_ 不适合需要内网访问与跨时段本地状态的首版 collector  
_Edge/CDN:_ Cloudflare Tunnel 继续服务现有 webhook，不作为 gardening evidence channel

### Technology Adoption Trends

本研究不以行业流行度决定选型，而以现有 brownfield 约束和最小权限决定。可观察到的技术方向是：

- **LLM 作为 specialist，普通代码作为 control plane。** Agent 负责跨文档语义比对和受限编辑；collector、schema validation、evidence completeness、state transition 和 publishing authorization 均为 deterministic code。
- **Structured output 不等于可信判定。** Schema 只保证形状，不能证明事实完整或真相优先级正确。
- **短期身份替代长期个人 token。** GitHub App installation token 约一小时过期，并能进一步限制仓库与 permissions，适合无人值守 publisher。[GitHub App REST API](https://docs.github.com/en/rest/apps/apps)
- **受限运行环境替代全权 agent。** analysis turn 使用 read-only sandbox；只有通过硬门禁后的单文档编辑 turn 获得 isolated worktree 的 workspace-write 权限。
- **多-agent 延后。** OpenAI Agents SDK/Codex MCP 在需要多个 specialist、长时间 HITL 或复杂 handoff 时再采用；V1 不为尚不存在的复杂度付费。

**Step 2 初步技术选择（待后续步骤验证）：** `Jenkins → Python controller/collectors → SQLite + redacted JSON evidence → Codex Python SDK → deterministic gate → isolated editor → GitHub App publisher`。

**Confidence:** 高（Jenkins、GitHub、Terraform、Ansible、NetBox 和 Codex runtime 的官方能力）；中（SQLite ledger 与 Codex Python SDK 作为 V1 最优组合属于基于当前仓库约束的架构推论，需在 integration 与 architecture 阶段验证）。

---

## Integration Patterns Analysis

### API Design Patterns

**推荐模式是 controller-owned adapters，而不是 agent-owned tools。** Python controller 为每个事实源实现窄、只读 adapter；adapter 只接受 allowlisted resource identity，返回统一 evidence envelope。Codex 只读取已经脱敏、带 provenance 的 envelope，不直接持有 HCP Terraform、NetBox、Proxmox、vSphere、Jenkins 或 GitHub 凭据。这样 API 权限、分页、版本差异、超时和脱敏都留在 deterministic boundary 内。

| 集成边界 | V1 调用方式 | 允许用途 | 关键约束 |
|---|---|---|---|
| Git / repository | 本地只读 Git 与文件解析 | 锁定 source commit、读取文档和 IaC 声明 | 同一 audit 固定 commit SHA；不把未提交工作树当作有效代码 |
| HCP Terraform | State Versions API，必要时 `terraform show -json` | 取得 state-version 元数据及 allowlisted state 字段 | 等待 `resources-processed=true`；记录 state version、Terraform version、VCS SHA；原始 state 不进入 LLM |
| Ansible | `ansible-inventory --list/--host`；专用只读验证 play | 解析有效 inventory 和有限 runtime observation | inventory 解析失败即证据不完整；`--check --diff` 不能替代生产观察 |
| NetBox | 优先 read-only GraphQL；REST GET 用于 GraphQL 未覆盖字段 | 读取管理边界、设备、VM、接口与 IPAM 事实 | 专用 write-disabled v2 token；固定字段投影、分页与 API version |
| Proxmox VE | HTTPS REST GET `/api2/json/...` | 读取 VM/LXC/node 的 config、status 与资源值 | privilege-separated token + path ACL/PVEAuditor；禁止 POST/PUT/DELETE |
| ESXi/vSphere | pyVmomi / vSphere Web Services API 的属性读取 | 读取 VM identity、config 与 runtime properties | 专用 read-only role；显式 property set，不能调用 lifecycle methods |
| 服务端点 | HTTPS health/readiness GET，必要时受限 TCP connect | 验证 SPEC 要求的服务可访问性 | URL、method、状态码和响应字段 allowlist；不执行登录、写入或业务交易 |
| Codex worker | 官方 Python SDK + schema-constrained turn | 语义提取、证据对照、受限文档编辑 | analysis 为 `read_only`；仅接收 normalized evidence；gate 不由模型决定 |
| GitHub publisher | Git data/contents + Pull Requests REST API | 创建 automation branch、写入单文档 change、开启 draft PR | 仅在 deterministic gate 成功后调用；显式缩减 installation token；不调用 merge endpoint |

HCP state-version 对象只携带元数据和下载 URL，不直接包含完整 state；部分元数据异步生成。Plan JSON endpoint 则返回一分钟有效的临时重定向，且不能使用 organization token。V1 的 recurring audit 主要读取 current state，不应为了证明代码有效而自动生成 plan；如果未来采用 speculative plan，必须作为独立 collector，并重新评估 workspace admin token 与执行副作用。[HCP Terraform State Versions API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/state-versions) [HCP Terraform Plans API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/plans)

NetBox REST API 使用 HTTP/JSON，支持 `API-Version`、`X-Request-ID`、`ETag` 和 `If-Match`；GraphQL 是 read-only 且允许精确选择嵌套字段。对本项目的批量只读投影，GraphQL 可减少 over-fetching；对 endpoint-specific 字段或兼容性更重要的查询，使用 REST GET。两者都必须归一化到相同的内部 schema，不能让下游依赖 NetBox 原始响应形状。[NetBox REST API](https://netbox.readthedocs.io/en/stable/integrations/rest-api/) [NetBox GraphQL API](https://netbox.readthedocs.io/en/stable/integrations/graphql-api/)

_RESTful APIs:_ HCP Terraform、NetBox、Proxmox 和 GitHub 的主要集成方式；每个 adapter 固定 API/version、method 与 endpoint allowlist。  
_GraphQL APIs:_ 只用于 NetBox 的字段精确只读查询；不引入 GitHub GraphQL，因为 V1 发布操作简单且 REST 权限/endpoint 更易审计。  
_RPC and gRPC:_ V1 不需要；vSphere 保留仓库已有 `pyvmomi`/Web Services 路径，避免同时引入第二套 vSphere client。  
_Webhook Patterns:_ NetBox webhook 可作为“可能发生变化”的加速提示，但 payload 不是权威快照，接收后仍需重新读取所有证据源。  

### Communication Protocols

外部 API 全部通过 HTTPS；controller 对证书校验、连接/读取 timeout、最大响应体和 redirects 做显式限制。Proxmox、NetBox 与 vSphere 使用内网 DNS/IP，但仍不得通过关闭 TLS 验证来简化 PoC。GitHub 临时下载 URL等需要 redirect 的接口只允许跳转到预期 host class，且 URL 不写入日志。

Ansible 是唯一合理保留的 SSH-based integration：它已经承载仓库 inventory 与 verify patterns。用于 gardening 的验证内容必须拆成专用 read-only play/tasks，不能直接复用可能包含部署或 handler 的 Deploy play。`ansible-inventory` 是代码侧解析证据；SSH/HTTP observation 才是生产侧证据，两者不能合并成一个模糊的“Ansible 结果”。[Ansible inventory CLI](https://docs.ansible.com/projects/ansible-core/devel/cli/ansible-inventory.html) [Ansible check and diff mode](https://docs.ansible.com/projects/ansible-core/devel/playbook_guide/playbooks_checkmode.html)

API transport error 与 domain observation 必须分层：连接 reset、429 或短暂 5xx 可在单次 collector call 内按 bounded exponential backoff 重试；而“目标在一次 audit 中不可达”必须写成 observation outcome，并由后续 Jenkins run 跨时段复查。HTTP 401/403、schema/version 不兼容、凭据缺失和解析失败不是“目标不可达”，应立即归类为 collector/configuration failure 并升级，避免把控制面故障误判为生产状态。GitHub 发布端应读取 rate-limit headers，并遵循 `Retry-After` 或 `x-ratelimit-reset`。[GitHub REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

_HTTP/HTTPS Protocols:_ 所有平台 API 与服务 health probe 的默认协议。  
_SSH Protocol:_ 仅由受限 Ansible verify collector 使用。  
_WebSocket Protocols:_ 不需要；audit 是批处理，不存在双向实时会话需求。  
_Message Queue Protocols:_ V1 不引入 AMQP/MQTT/Kafka；SQLite ledger 与 Jenkins schedule 已覆盖低吞吐、单 controller 的 durable handoff。  
_gRPC and Protocol Buffers:_ 不需要；没有高吞吐内部 RPC，也不应为一个本地 controller 增加独立服务边界。  

### Data Formats and Standards

所有 adapter 输出同一版本化 JSON evidence envelope，并在写入 ledger、归档或发送给 Codex 前通过 JSON Schema/Pydantic 验证。建议最小结构如下：

```json
{
  "schema_version": "1.0",
  "audit_id": "uuid",
  "claim_id": "stable-hash",
  "source_revision": {
    "git_commit": "sha",
    "terraform_state_version": "sv-..."
  },
  "observation": {
    "collector": "proxmox_vm",
    "collector_version": "...",
    "target": "vm:100",
    "started_at": "RFC3339",
    "completed_at": "RFC3339",
    "outcome": "observed|unreachable|collector_error",
    "normalized_facts": {},
    "raw_evidence_ref": "artifact-relative-path",
    "content_sha256": "..."
  },
  "redactions": []
}
```

`claim_id` 必须由规范化文档路径、稳定 locator 和 claim type 生成，不能只用行号，因为普通文档编辑会移动行号。`source_revision` 将 Git commit、Terraform state version/VCS SHA 与 observation time 绑在一起；如果审计期间代码 HEAD 或 state version 发生变化，本轮结果标为 stale/unresolved，重新采集，不能拼接不同时间点的“完整”证据。

原始响应可作为短期 artifact 供故障诊断，但必须先按字段 allowlist 过滤并脱敏；规范化事实才进入 gate。JSON object key 排序、单位归一化（bytes/MiB/GiB、CPU count、IP/CIDR）、`null` 与 missing 的区分、时间统一为 UTC RFC 3339，都是 collector contract 的一部分。证据 hash 用于完整性和关联，不用于证明来源真实性；真实性仍依赖受控 collector、TLS、凭据和 artifact access control。

_JSON:_ controller、schema、ledger payload 与 LLM structured output 的唯一交换格式。  
_YAML/HCL/Markdown:_ 仅作为 repository source，由 parser/agent 读取后转为 typed claims；不作为跨组件 runtime contract。  
_XML:_ Jenkins 支持但 V1 选择 JSON；vSphere SDK 在内部处理 Web Services wire format。  
_Protobuf/MessagePack:_ 不需要，体量与性能不构成约束。  
_CSV/Flat Files:_ 不作为 evidence contract，避免类型和嵌套语义丢失。  

### System Interoperability Approaches

V1 是刻意受限的 hub-and-spoke：Python controller 是唯一 orchestration hub，各 adapter 是 anti-corruption layer。平台原始模型不得彼此直接耦合，例如 NetBox VM、Terraform resource address 和 Proxmox VMID 先分别映射到内部 `ManagedComponentIdentity`，只有 identity resolution 成功后才能比较。建议 identity 至少携带 `platform`、`environment/workspace`、`resource_address`、`provider_native_id`、`hostname` 与可选 IP；名称或 IP 单独相同不足以自动建立管理关系。

integration pipeline 应保持单向阶段边界：

`discover claims → resolve management identity → collect code evidence → collect production evidence → normalize/redact → deterministic gate → Codex edit → local validation → GitHub draft PR`

每一阶段只能消费上一阶段的 schema-valid 输出。collector 不判断 `document_drift`，Codex 不签发发布 token，publisher 不重跑证据采集；这避免职责混合造成 bypass。当前仓库已经存在 Jenkins、HCP Terraform、动态 inventory、NetBox API 与 `pyvmomi`，因此不需要 API gateway、service mesh 或 enterprise service bus。

_Point-to-Point Integration:_ controller 到各官方 API/CLI 的受控连接，适合有限且稳定的 homelab source 集合。  
_API Gateway:_ V1 不需要；若未来多个 controller 共享生产访问，再评估集中式 evidence proxy。  
_Service Mesh:_ 不适用；没有由多个长期运行服务组成的数据平面。  
_Enterprise Service Bus:_ 不适用；会扩大运维面且不改善 evidence correctness。  

### Microservices Integration Patterns

controller、ledger、collectors、gate 和 publisher 应首先作为一个可测试的 Python application 内的模块部署，而不是微服务。其内部接口仍要像远程边界一样版本化，以便未来在多 controller 或独立 evidence proxy 出现时拆分。collector failure 由明确的 typed result 返回，不能吞掉异常后产生空事实；gate 采用 fail-closed：未知 schema、缺字段、identity 冲突、revision 改变或 collector error 一律禁止编辑。

_API Gateway Pattern:_ 不采用。  
_Service Discovery:_ 静态配置/仓库 inventory 即可；禁止让 agent 自行扫描网络发现资产。  
_Circuit Breaker Pattern:_ 可为持续失败的平台 adapter 增加 run-level circuit breaker，减少对故障控制面的重复请求，但必须给每个 claim 记录“未观察”，不能把熔断解释成资产不存在。  
_Saga Pattern:_ 不适用；V1 没有跨服务写事务。唯一外部写路径是 gate 后的 GitHub branch/PR 发布，并以 correlation ID 做可恢复、可查询的幂等流程。  

### Event-Driven Integration

**权威触发器是 Jenkins schedule，事件触发器只是提示。** 定时 run 保证即使 webhook 丢失也会重新审计；NetBox webhook 可以把相关 component identity 放入优先队列，但 receiver 必须验证共享 secret/token、限制 payload 大小、去重，并重新调用 NetBox 与生产 collectors。仓库现有 `Jenkinsfile-webhook-router` 已证明 NetBox → Jenkins 的事件路径存在，但该流水线包含部署路由语义，不能直接复用为 gardening evidence gate。

ledger 是轻量 durable queue/state machine：`discovered → collecting → pending_observation → gate_ready → consistent/document_drift/production_drift/unresolved → published/escalated`。状态转换使用 transaction 和唯一键；Jenkins build number、audit ID、claim ID、source revision 和 PR number 形成 correlation chain。重复 schedule、Jenkins restart 或 publisher timeout 后，controller 先查询 ledger/GitHub 再采取动作，避免为同一 claim/revision 创建多个 PR。

_Publish-Subscribe Patterns:_ 不引入 broker；webhook receiver 到 ledger 的持久化相当于单消费者 inbox。  
_Event Sourcing:_ 不采用完整 event-sourced architecture；append-only observation attempts 与 state-transition audit log 足以追溯。  
_Message Broker Patterns:_ V1 不需要 RabbitMQ/Kafka；当出现多 controller、高并发或明确 delivery SLA 时再评估。  
_CQRS Patterns:_ 不采用；SQLite transaction model 足够。  

### Integration Security Patterns

每个 adapter 使用独立机器身份和最小权限凭据，凭据只在对应 collector 的短生命周期进程中注入。NetBox 使用 write-disabled v2 token 并限制 Jenkins agent IP；Proxmox 使用 privilege-separated token 与 path-level read-only ACL；vSphere 使用只读 role；HCP token 只给 state read 能力；GitHub App publisher 单独持有 `Contents: write` 和 `Pull requests: write`，analysis/collector job 不得获得该 token。NetBox 官方明确指出 write restriction 与 client-IP restriction 的行为；Proxmox 则规定 token 权限不超过 backing user，并在 privilege separation 下与 token ACL 取交集。[NetBox REST API authentication](https://netbox.readthedocs.io/en/stable/integrations/rest-api/) [Proxmox VE Administration Guide](https://pve.proxmox.com/pve-docs/pve-admin-guide.pdf)

GitHub installation token 每次发布临时签发并显式限制 repository 与 permissions，过期或不确定结果时先按 deterministic branch name/PR marker 查询再重试。GitHub App installation 默认可访问 installation 已授权的全部仓库，所以“创建短期 token”本身不等于最小权限。[GitHub App installation token](https://docs.github.com/en/rest/apps/apps) [GitHub App best practices](https://docs.github.com/en/enterprise-cloud@latest/apps/creating-github-apps/about-creating-github-apps/best-practices-for-creating-a-github-app)

Jenkins credentials 只按 job/folder scope 暴露，console log、Codex prompt、SQLite、JSON artifact 与 PR body 均执行 secret scanner。Jenkins Remote Access API 不在内部 scheduled job 的主链上；若未来允许外部触发，只使用 HTTPS + API token，并给触发账户单 job 权限。Jenkins 官方提供 REST-like JSON API，且 API-token authenticated POST 可免 CSRF crumb，但这不减少 authentication/authorization 要求。[Jenkins Remote Access API](https://www.jenkins.io/doc/book/using/remote-access-api/) [Jenkins CSRF protection](https://www.jenkins.io/doc/book/security/csrf-protection/)

_OAuth 2.0 and JWT:_ GitHub App 用私钥签 JWT 换 installation token；V1 不自行实现通用 OAuth server。  
_API Key Management:_ 独立身份、最小 scope、短期 token（可用时）、定期轮换、usage audit；禁止共享现有 superuser token。  
_Mutual TLS:_ 当前平台未要求；若以后引入 evidence proxy，再评估 mTLS，不作为 V1 前置条件。  
_Data Encryption:_ 所有网络传输使用验证证书的 TLS；ledger/artifact 所在 Jenkins volume 依赖主机级加密与严格 ACL，敏感原始数据原则上不落盘。  

### Cross-Integration Conclusions

1. **统一契约比统一协议重要。** 各平台 API 不同，但都必须输出同一 schema-versioned、revision-bound、redacted evidence envelope。
2. **事件不能替代观察。** Webhook、Jenkins build cause、Terraform VCS SHA 都是 provenance 或 freshness signal，不是生产状态本身。
3. **失败类型必须可区分。** `unreachable`、`unauthorized`、`rate_limited`、`schema_mismatch`、`identity_ambiguous` 和 `stale_revision` 进入不同状态；只有真正的 reachability failure 进入跨时段观察策略。
4. **发布是独立特权阶段。** collector 与 Codex 无 GitHub write token；只有 deterministic gate 与验证全部成功后，publisher 才获得短期身份。
5. **V1 不需要分布式集成基础设施。** 单 Jenkins controller、模块化 Python application、SQLite ledger 和 archived evidence 已满足当前吞吐；新增 broker/gateway/mesh 会扩大故障与凭据面。

**Confidence:** 高（各平台 API、token、数据格式与 Jenkins/GitHub能力均由官方文档支持）；中（统一 identity model、envelope 字段、REST/GraphQL 分工和 webhook inbox 属于针对本仓库的设计推论，需在 architecture 与 fixture-based contract tests 中验证）。

---

<!-- Content will be appended sequentially through research workflow steps -->
