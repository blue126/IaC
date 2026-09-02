# Acceptance contract

## Decision rule

服务必须分别证明：artifact 完整、进程 ready、输出正确、API 语义兼容、性能可用、资源安全、运行稳定和可以冷恢复。HTTP 200、端口开放或模型成功加载均不能单独构成通过。

## Phase 0 static acceptance

| Gate | Pass criterion |
|---|---|
| Ansible syntax | 专用 Playbook `--syntax-check` 返回成功 |
| Role structure | 默认变量、tasks、templates/files、handlers 仅创建实际需要的目录；依赖在 playbook 显式排序 |
| Task scope | 本地检查证明 Phase 0 不含远端连接、下载、删除、启动或部署动作 |
| Desired state | MiniMax、Qwen 和 GLM 均不能被未来生产路径下载或启动，旧 lifecycle 入口已退役 |
| Lifecycle | DeepSeek 与 legacy backend 的互斥可由配置审查判定，且只有一个 restart owner |
| Compose | 配置可离线渲染，模型 mount 只读，端口默认 loopback/私网，无 privileged |
| Open WebUI bootstrap | 未初始化数据库时可 seed 初始 DeepSeek connection；模拟已有数据库时不会生成覆盖动作 |
| Release data | 必填 pin 和 runtime 参数无值时 fail fast，不默默采用 `main`/`latest` |
| Fixtures | corpus、API、benchmark 和输出 schema 均受版本控制且可单独运行 |

## Powered-on preflight

| Evidence | Pass criterion |
|---|---|
| CPU | AVX2 与 FMA 存在；vCPU/vNUMA 记录完整 |
| GPU | 两张 RTX 3090 identity 稳定；PCI address/topology/P2P 证据已保存 |
| Driver/runtime | actual driver 与所选 CUDA 12.8 image 兼容；优先满足 CUDA 12.8 GA 对应的 570.26+ 基线；Docker GPU smoke 成功；任何 driver 变更另行批准 |
| Memory | 340 GiB guest 可见；基线无持续 swap；host 资源争用可接受 |
| Storage | 下载前约 400 GB 实际余量，或独立模型盘方案获批；guest/VMDK/datastore 三层均有证据 |
| Legacy artifacts | MiniMax/Qwen/GLM 的精确路径、大小与 desired-state 归属已解析；任何删除另行批准 |
| NUMA | guest topology 与 ESXi `N%L/%RDY/%CSTP` 有可比较基线 |

## Readiness and correctness

| Gate | Required evidence |
|---|---|
| Process | Compose/container 状态符合预期，无无界 restart churn |
| Health | `/health` 成功并能区分 loading 与 ready（若 runtime 支持） |
| Identity | `/v1/models` 返回 manifest 中的实际模型 identity |
| Generation | 确定性生成 probe 成功；不能只测空响应或 HTTP 状态 |
| Corpus | 固定数理、代码、事实、中文和长上下文用例零乱码、零空答、零静默结构错误 |
| Long prefill | 超过 2,048 tokens 的请求完成 lazy allocation 路径，无 OOM 或输出破坏 |

固定 corpus 必须保存输入、seed、sampling、期望判定方式和版本。不能用主观聊天体验替代可重复 fixture。

## OpenAI and DeepSeek API contract

| Gate | Required evidence |
|---|---|
| Non-streaming chat | OpenAI SDK 与 Open WebUI 的多轮 Chat Completions 均通过 |
| SSE | delta 顺序正确、以标准终止结束，不泄漏原始 `<think>` 或 DSML |
| Reasoning | `low`、`high`、`max` 均被覆盖，`reasoning_content` 与最终 `content` 分离 |
| Tool calls | 单个和并行调用均生成结构化 `tool_calls`；字符串与嵌套 JSON 参数可解析 |
| Continuation | tool results 按调用顺序回填并能继续下一轮 |
| Failure safety | 截断或畸形 DSML 不会被当作可执行成功调用 |
| Parser config | 有效 entrypoint/OpenAPI 证明 `deepseek-v4` reasoning parser 与 `deepseekv4` tool parser 已启用或等价实现已验证 |
| UI integration | 临时 connection 不与 legacy model identity 冲突，用户可完成普通 chat、reasoning 和批准的 tool flow |
| Config authority | 首次 seed 后数据库内的管理员修改在重复 Ansible 部署及容器重建后保持不变；Ansible 可报告连接缺失/错误但不自动覆盖 |

如果增量 tool parser 未证明安全，agent/tool turn 在晋级前必须使用非流式路径。需要大规模自研 parser 才能通过时触发 Stop。

## Performance and resource matrix

基线场景：TP1，1K 与 8K prompt，各生成 256 tokens，并发 1；另执行 >2K first-request 路径。

每轮记录：

- prompt processing rate、median decode rate、TTFT、E2E latency、time per output token；
- peak RSS、swap、guest free memory；
- 每卡 VRAM、utilization、power（如可用）；
- guest vNUMA、进程内存放置、`nvidia-smi topo -m`；
- ESXi `N%L`、`%RDY`、`%CSTP`；
- model load duration、错误与 restart count。

| Metric | Pass / promotion criterion |
|---|---|
| Decode usability | 单请求 median decode ≥ 8 tok/s；目标 ≥ 10 tok/s |
| Correctness | 固定 corpus 无损；不同候选的确定性 fixture 可解释地一致 |
| Resource safety | 无 OOM、无持续 swap，guest memory 与每卡 VRAM 有可见余量 |
| NUMA repeatability | 每轮有 locality 证据；无法解释的跨启动差异在晋级前解决 |
| TP2 | 与 TP1 同题正确、无稳定性回归，且吞吐或用户体验约提升 ≥ 10% |
| Optional concurrency | 并发 2 时 tail latency 与资源余量仍符合批准标准 |

不能把其他硬件的 16–20 tok/s 上游数据当作本机预期。

## Reliability, security, and recovery

| Gate | Pass criterion |
|---|---|
| Cold boot | VM/guest 冷启动后按预期到达 ready，GPU identity 稳定 |
| Clean restart | 显式 stop/start 无 orphan legacy process、端口冲突或双 restart owner |
| First request | 首个长 prefill 不因 lazy allocation 失败 |
| Soak | 一小时连续运行无输出破坏、OOM、持续 swap 或不可恢复健康退化 |
| Exposure | 未授权网络无法匿名访问 inference endpoint |
| Supply chain | 模型 revision、镜像 digest、runtime commit 与有效 entrypoint 已审计 |
| Secrets | runtime secret 由 Vault 间接提供，落盘文件为 root-owned `0600`，且不出现在 Compose、普通 inventory 或日志 |
| Logs | 容器与服务日志有界保留，晋级/恢复摘要和失败诊断可追溯 |
| Open WebUI backup | 非可重建状态可恢复 |
| Safe stop | DeepSeek 可被干净停止，Open WebUI 数据保持完整；没有 legacy backend 被自动启动 |
| Cold recovery | 文档和演练覆盖 Terraform/Ansible 重建、GPU 重新附加、Open WebUI 状态恢复、checkpoint rehydration 和固定候选重部署 |

## Promotion verdict

- 所有必需 gate 通过：可以请求 Phase 5 批准。
- 正确性/API 通过但 KTransformers 性能失败：允许一次顺序执行的 `ik_llama.cpp` Q4 CPU-MoE 比较。
- 任一候选出现静默错误、不可重复 GPU、长期 swap/OOM 或冷恢复失败：不得晋级。
- 两条候选均低于 8 tok/s：停止优化并记录服务不可接受。
