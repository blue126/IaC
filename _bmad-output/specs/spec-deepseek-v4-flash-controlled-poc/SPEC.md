---
id: SPEC-deepseek-v4-flash-controlled-poc
companions:
  - architecture.md
  - brownfield.md
  - implementation-phases.md
  - acceptance-contract.md
  - release-manifest.md
  - ../../../docs/designs/ansible-role-architecture.md
sources:
  - ../../planning-artifacts/research/technical-deepseek-flash-v4-deployment-feasibility-research-2026-08-13.md
  - ../../../docs/deployment/llm-server-deployment.md
---

> **Canonical contract.** 本 SPEC 与 `companions:` 中的文件共同构成构建、测试和验收的完整合同。`sources:` 仅用于追溯，不是下游必读材料。

# DeepSeek V4 Flash 受控 PoC

## Why

现有 ESXi `llm-server` VM 具备 340 GiB 全预留内存和两张 RTX 3090，容量上可以探索 DeepSeek V4 Flash 的 CPU/GPU 异构推理，但旧 CPU、双路 NUMA、存储余量和模型专用 API parser 使服务质量仍不确定。本工作要以可逆、证据门控的 PoC 判断该主机能否提供正确、可用且可恢复的服务，而不是把“模型能加载”误当成生产可行。

## Capabilities

- **CAP-1**
  - **intent:** 操作者可以在不访问运行中基础设施的情况下准备一条独立、声明式的 DeepSeek 部署路径。
  - **success:** Phase 0 所需的角色、Playbook、服务定义、发布清单、fixture 和基准入口均可在本地渲染并通过语法检查，且没有 VM 或外部状态变化。

- **CAP-2**
  - **intent:** 系统可以表达 DeepSeek 是唯一未来生产模型、全部 legacy 模型退出服务生命周期的目标状态。
  - **success:** MiniMax、Qwen 和 GLM 均不再被生产目标状态选择、下载或启动，旧 role/handler 也不能重新激活它们。

- **CAP-3**
  - **intent:** 操作者可以在获准开机后，以非变更方式发现容量、兼容性和硬件拓扑事实。
  - **success:** preflight 产出驱动、CUDA、Docker/Toolkit、GPU/PCIe/P2P、CPU flags、NUMA、存储和 artifact 清单的结构化证据，不改变 guest 或 ESXi 配置。

- **CAP-4**
  - **intent:** 操作者可以按可恢复、可审计的顺序准备运行时与模型 artifact。
  - **success:** Open WebUI 已备份、冷重建路径已记录、删除目标已精确解析并单独获批，模型 revision 与镜像 digest 均固定且完整性验证通过。

- **CAP-5**
  - **intent:** 操作者可以启动一个与旧栈隔离的保守 DeepSeek 正确性基线。
  - **success:** 所有 legacy 推理进程均停止，TP1 基线以单卡、16K context、并发 1、关闭 MTP 运行，端点只在批准的私有边界内可达。

- **CAP-6**
  - **intent:** 验证工具可以判定 DeepSeek 是否满足既有客户端所需的完整对话和 agent API 语义。
  - **success:** 同步与 SSE chat、reasoning 分离、单个/并行工具调用、工具结果续接、畸形输出安全失败及 Open WebUI 端到端用例全部通过。

- **CAP-7**
  - **intent:** 操作者可以用可重复证据判断服务的性能、资源安全和可靠性是否可接受。
  - **success:** 固定 corpus、性能指标、NUMA/拓扑、冷启动、重启、长 prefill、一小时 soak 和故障恢复证据完整，并能依合同产生明确的 Go 或 Stop 结论。

- **CAP-8**
  - **intent:** 操作者可以在黄金基线之后逐项评估扩展和优化，而不把未经验证的收益带入生产。
  - **success:** 每次实验只改变一个主变量；任何晋级均保留正确性和稳定性，TP2 还须带来约 10% 的实质收益。

- **CAP-9**
  - **intent:** 操作者可以门控地切换生产后端，并在失败时进入明确、安全且可恢复的状态。
  - **success:** 只有完整资格门通过后 DeepSeek 才成为唯一 boot backend；失败时能停止 DeepSeek、保持 Open WebUI 状态完整，并从固定 manifest 冷重建或重新部署已通过候选。

- **CAP-10**
  - **intent:** 每个候选版本都可以被精确识别、审计和重现。
  - **success:** 发布清单完整记录模型、镜像、运行时、驱动、参数、拓扑、fixture 与结果，且任何浮动依赖都不被视为已晋级版本。

- **CAP-11**
  - **intent:** 操作者可以依据证据运行、诊断和冷恢复该服务，并保留真实经验。
  - **success:** 操作与恢复材料覆盖“进程健康但输出错误”的识别、IaC 重建、固定 artifact 恢复和真实部署后的中文 learning note，预测与实测明确区分。

## Constraints

- 当前实施授权只覆盖 Phase 0 本地仓库变更与本地验证；Phase 1–5 的运行时动作仍受 `implementation-phases.md` 的独立审批门约束。
- 复用现有 ESXi `llm-server` VM，不新建第二台 VM；已知硬件边界见 `brownfield.md`。
- 两张 RTX 3090 不是透明统一显存，首选路径必须是 CPU/RAM 承载 MoE 专家、GPU 加速其余算子的异构推理。
- 首选模型为 `deepseek-ai/DeepSeek-V4-Flash-0731` 官方 safetensors，首选运行时为 KTransformers/SGLang-KT；现有 `ik_llama.cpp` pin 不得原地升级覆盖。
- 同一时刻只允许一个大模型后端拥有主要 RAM/GPU；该不变量必须由生命周期层强制。
- Terraform、Ansible、Compose 和 systemd 必须各自只有一个声明式责任边界；禁止 ad-hoc 容器、直接 shell 下载和双重 restart owner。
- 模型 revision、镜像 digest、parser、参数与 fixture 作为一个兼容发布集固定和晋级；禁止生产跟随 `main` 或 `latest`。
- 没有独立模型盘时，一次只保留一个主要 DeepSeek checkpoint 格式；官方 safetensors 与 GGUF 比较路线按顺序准备和测试。
- 模型卷只读，容器不得 privileged；仅授予已证明必要的 GPU、IPC 与 `SYS_NICE` 权限。
- 推理 API 默认仅供同 VM 的 Open WebUI 或 loopback 测试使用；任何凭据通过 Ansible Vault 间接注入。
- Open WebUI connection 采用 bootstrap 后转交：首次且数据库未初始化时由 Ansible seed 初始连接；数据库初始化后由 Open WebUI 持久化数据库管理，后续 Ansible 只备份和验证，不覆盖 UI 修改。
- 下载前必须证明约 400 GB 实际可用模型存储余量，或依据证据批准独立模型盘。
- TP1 黄金基线固定为单卡、16K context、并发 1、关闭 MTP 和保守 cache；优化一次只改变一个主变量。
- Ansible 实现必须遵循 adopted role 架构文档及仓库的命名、幂等、Deploy + Verify 和窄标签约定。

## Non-goals

- 不把两张 3090 设计成全 GPU、透明 48 GB 显存的部署。
- 不把 1M context、高并发、横向扩展或高可用集群作为本机 PoC 目标。
- 不引入 Kubernetes、service mesh、消息总线、额外 API gateway 或完整 Prometheus/Grafana。
- 本轮不启动 VM、下载模型/镜像、删除远端 artifact、停止服务、修改 ESXi 拓扑或执行生产切换。
- 不借 Phase 0 顺带重构全部旧 LLM 栈或迁移 Open WebUI 持久化数据库。
- 不因启用 guest 内的 DeepSeek unit 自动启用 ESXi VM auto-start。
- 不在 PoC 前采购新 GPU。

## Success signal

固定候选能在该主机上正确通过完整 API 合同，单请求 median decode 至少达到 8 tok/s，且无持续 swap/OOM，并通过冷启动、重启、长 prefill、一小时 soak 和冷恢复；否则流程以证据明确停止，并记录为“容量可行、服务不可接受”。

## Assumptions

- Phase 0 的本地 desired-state 变更可移除 MiniMax、Qwen 和 GLM 的未来生产声明，但不会删除 guest 中任何文件。
- Open WebUI 是默认且唯一的生产客户端；新增直接 LAN API 客户端将触发新的认证、网络与 TLS 决策。
- 若 Phase 1 证明存储不足，流程会停止并报告证据，由用户另行安排扩盘；系统不自动删除模型或自动扩容。
