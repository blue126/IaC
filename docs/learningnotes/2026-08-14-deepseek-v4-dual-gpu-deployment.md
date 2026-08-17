# 学习笔记：DeepSeek V4 Flash 双 GPU 部署、验证与 Open WebUI 集成

**日期**：2026-08-14
**标签**：#LLM #DeepSeek #GGUF #llama.cpp #OpenWebUI #Ansible #GPU #ESXi #PCIe

本文记录今天将 DeepSeek V4 Flash GGUF 候选运行时接入现有 homelab 的全过程。重点不是把一次部署包装成“成功案例”，而是说明哪些判断有实测证据、哪些只是待继续验证的假设，以及为什么最终架构会比一开始看起来多出一些保护措施。部署边界的 Ansible 变更已提交为 `a3d766b`；文末所述后续性能实验仍是未提交工作区改动。本文所述 live 状态已通过 guest 上的 `systemctl cat`、`ss` 和 API 合同复核，不应仅凭工作区文件推断线上状态。

---

## 1. 当前实际运行形态

当前生产路径是：

```text
Open WebUI
  -> host.docker.internal:8081/v1
  -> OpenAI compatibility proxy
  -> 127.0.0.1:8082/v1
  -> DeepSeek V4 Flash GGUF / llama-server candidate
```

- 候选容器内部监听 `0.0.0.0:8082`，但宿主机发布被限制为 `127.0.0.1:8082`，因此 LAN 不可直接访问。
- `8081` 是给 Open WebUI 的稳定 API 地址；它由一个很小的本地兼容代理拥有。
- 兼容代理可按 CIDR 白名单发布到 LAN；当前允许本机、Open WebUI 使用的 Docker bridge（`172.17.0.0/16`、`172.18.0.0/16`）与 `192.168.1.0/24`。无鉴权 API 不应发布到未受控网段。
- 两张 RTX 3090 由 `--split-mode layer` 使用：不同 GPU 持有不同层，并在层边界传递 activation；**当前不是张量并行（TP2）**。
- GGUF 文件约 145.6 GiB，远大于两张卡合计 48GB 显存。`--cpu-moe` 已启用，MoE 专家驻留/计算于 CPU 侧；GPU 承担非专家部分、attention 与 KV cache。因此这是 CPU–GPU 混合推理，不是“模型完整驻留显存”的运行形态。
- 模型权重与 runtime build 目录均以只读方式挂载；Docker 使用有界的 local logging，避免日志无限增长。
- systemd unit 拥有 Compose project 的启停；候选容器为 `restart: "no"`，该 unit 也没有 `Restart=`。候选期刻意不自动重启，避免崩溃循环掩盖 OOM 等问题；故障后必须人工恢复。
- 该 unit 使用 `--force-recreate`，且 runtime 使用 `--no-mmap`；一次 service restart 会重建容器并重新读取约 145.6 GiB 权重，冷启动应按十分钟量级规划。

## 2. 为什么没有沿用旧 LLM 服务

旧 `llm-server` role 的职责非常宽：会准备磁盘、安装 NVIDIA 软件、编译旧引擎、下载旧模型、选择 boot model、启动旧 systemd unit，并拉起 Open WebUI。它适合历史上的 MiniMax/Qwen/GLM 生命周期，却不适合作为一次受控的 DeepSeek 试验入口。

因此今天采用独立的 `deepseek-v4` / `deepseek-v4-ik` role、独立 Compose project、端口和 systemd unit。这样做的收益是：

- 新旧运行时不会覆盖彼此的二进制、环境文件或服务 unit。
- 旧模型从 desired state 和 guest 生命周期中明确退役，而不是只从 inventory 中删除名称。
- 每次变更都可以只部署 DeepSeek 的相关标签和 owner，不会顺带下载模型、重编译引擎或重建 Open WebUI。

**教训**：把“配置一个模型”和“维护整台 LLM 主机”放在同一个 role，会使很小的配置操作变成高风险的基础设施操作。

## 3. 双 GPU：当前 layer split 与历史 TP 实验必须分开

### 3.1 当前 GGUF runtime：layer split + CPU-MoE

当前 Compose 以 `--split-mode layer` 和 `CUDA_VISIBLE_DEVICES=0,1` 使用两张卡。这是层切分（接近 pipeline/layer split）：不同卡保存不同层，前向过程仅在层边界传递 activation。它不使用 NCCL/all-reduce，也不等同于 vLLM/SGLang 语境中的 Tensor Parallelism。

该部署无条件启用 `--cpu-moe`。因此 prefill/decode 的首要瓶颈应优先假设为 CPU 侧专家计算与内存带宽，其次才检查 host↔device 传输；layer split 的跨卡流量远小于张量并行在每个 attention/FFN block 内所需的 all-reduce。

两张 3090 也不会成为统一的 48GB 显存池；更关键的是，即使能够池化，48GB 仍远不足以容纳约 145.6 GiB 的模型文件。这正是 CPU-MoE 路径存在的原因。

### 3.2 历史 KTransformers TP 实验：只作遗留记录

早先 `deepseek-v4`（KTransformers）role 曾定义下列 profile：

| Profile | GPU | TP |
|---|---|---|
| `tp1` | `0` | `1` |
| `tp2` | `0,1` | `2` |

它属于本次 cutover 已停用的旧 role，不能拿来描述当前 GGUF runtime。真正的张量并行是在层内切分权重矩阵，并在 attention/FFN block 结束后作 all-reduce；层间传 activation 则是 layer/pipeline split 的特征。

历史 TP2 实验中，GPU1 释放、健康检查连接被拒绝曾发生；它不是当前 layer-split runtime 的已知结论。旧 profile 是否存在自动回退实现仍需单独核查，不能表述为“已经自动恢复 TP1”。

### 3.3 当前双卡的验证目标

双卡是否比单卡有收益仍未由对照基准证明。当前应采集两卡显存/利用率、CPU RSS/swap、TTFT、prefill 吞吐、decode 吞吐、错误和重启计数；不能仅因两张卡在 `nvidia-smi` 中出现就认定收益成立。PCIe/P2P topology 仍值得记录，但对当前 layer split 的排障优先级低于 CPU 侧专家计算与内存带宽。

### 3.4 可回归的当前参数基线

| 参数 | 当前值 | 排障含义 |
|---|---|---|
| `--split-mode` | `layer` | 层切分，不是 TP |
| `--cpu-moe` | 启用 | 专家侧 CPU/内存带宽是首要嫌疑 |
| `--n-gpu-layers` | `100` | 非专家部分尽量 offload |
| `--ctx-size` | `131072` | 当前 128K KV cache 上限；16K 仅为历史观测基线 |
| `--threads` | `32` | 应与 VM 实际 CPU 拓扑核对 |
| Flash Attention / KV | `on` / `f16,f16` | KV 精度与显存占用固定 |
| `--no-mmap` | 启用 | 冷启动需要完整读取模型 |
| 模板 / reasoning | `--jinja` / `--reasoning-format deepseek` | Native function calling 与 reasoning 分离依赖项 |
| GPU 可见性 | `0,1` 和两个 CDI device | 当前没有自动退回单卡机制 |
| `GGML_CUDA_NO_PINNED` | 未设置 | 当前实验允许 pinned host memory；启动时约分配 138 GiB pinned RAM，须以资源余量和实测吞吐共同裁决 |
| `--batch-size` / `--ubatch-size` | `4096` / `2048` | 当前收敛值；`ubatch=1024/1536` 仅是历史中间态 |
| `ipc` / capability | `host` / `SYS_NICE` | 分别影响共享内存与调度优先级 |

## 4. 性能观察：首轮慢并不等于整个会话慢

以下是 Open WebUI 统计面板的**单次历史观测**，当时配置为双卡 layer split + CPU-MoE、`ctx=16384`；它仅用于说明首轮与缓存轮的量级差异，不是可横向比较的性能基准。后续已批准将运行时目标提升为 `ctx=131072`，两者不可混为同一性能基线。

- 新对话首条请求约 742 prompt tokens，prompt eval 约 13 秒，约 57 prompt tokens/s；之后还会有模型本身约 3 秒的 reasoning/generation。
- 同一对话的下一条请求约 750 prompt tokens，但缓存命中约 737 tokens，只需处理约 13 个新增 token；prompt 阶段约 1.1 秒，生成约 10 tokens/s。

两点结论：

1. 首条消息的 prompt 更长（系统提示词、工具描述），且 KV cache 前缀完全未命中，需要全量 prefill；常驻服务已经加载模型，不能把“模型加载”归因于每个新对话首条请求。
2. UI 显示的 `prompt_per_second` 在只处理十几个新增 token 时不宜单独横向比较；应同时看 `cached_tokens`、`prompt_n`、TTFT 和端到端时间。

`prompt eval` 时间/吞吐与 TTFT 不是同一指标：TTFT 还包含排队、tokenize 和首个 token 解码。实用优化顺序仍是先减少不需要的工具和能力描述，再检查缓存命中，最后才考虑 context、并发或 offload；后几项会改变内存与稳定性边界。

2026-08-14 的 16K 空闲采样中，GPU0/1 分别占用约 5.2/6.2 GiB（合计约 11.4 GiB，常驻显存而非瞬时利用率）。这低于一张 24 GiB 3090 的容量：第二张卡在当前层切分下尚无“单卡显存放不下”的直接证据，不能把“两卡均有显存占用”误读为吞吐收益；仍须以同一 corpus 的单变量基准裁决。

随后已受控切换到 128K。runtime 日志确认 `n_ctx=131072`、KV cache 为 5,504 MiB；空闲时 GPU0/1 分别约 8.0/8.8 GiB，主机可用 RAM 约 186 GiB、无 swap。稳定 `8081` API 返回 `max_model_len/context_window=131072`，19 项兼容契约通过。这证明启动与 API 边界正常，**不等同于**128K 满负载长文的性能或正确性基准。

### 4.1 已落盘的受控性能证据

以下数据来自 guest 的 `/var/lib/deepseek-v4-ik/evidence/` 或 runtime timing 日志。它们都是单并发、CPU-MoE、双 GPU layer split 的观测；没有单卡对照，故不能用于证明双卡增益。

| 时间 / 配置 | 固定输入 | 预填充 | 生成 | 验证结论 |
|---|---:|---:|---:|---|
| 历史 `ctx=16K`，Open WebUI 新对话 | 742 prompt tokens | 约 57 tok/s | 约 10 tok/s | UI 单次观察，只说明冷缓存与缓存命中的差异 |
| `--threads 32` 的历史 JSON 基准 | 1,156 / 9,220 prompt tokens，分别 3 次 | 未单列 | median 8.82 / 8.96 tok/s | `benchmark-threads32-1k.json`、`benchmark-threads32-8k.json` 均通过 `>=8` 门槛；该证据未记录完整运行时环境，不可充当本次 pinned/batch 的严格前后对照 |
| 历史中间态：128K、pinned host memory、batch 4096 / ubatch 1024 | 9,237 prompt tokens，compatibility contract 长上下文项 | **87.88 tok/s**（105.12 s） | 7.25 tok/s（60 tokens） | 2026-08-14 实测；19/19 contract 项通过；容器完成后 RSS 约 149.9 GiB / 334.6 GiB |
| 历史中间态：同上，`--cold-prefill` 1K 固定语料、3 次 | 1,165–1,166 prompt tokens | **70.59 tok/s** 中位量级（68.70–70.60） | **8.29 tok/s** 中位数 | 直接命中 `127.0.0.1:8082`，每次从首 token 失配 cache；JSON verdict 通过 |
| 历史中间态：同上，`--cold-prefill` 8K 固定语料、3 次 | 9,230–9,231 prompt tokens | **89.12 tok/s** 中位数（89.07–89.68） | **8.31 tok/s** 中位数 | 直接命中 `127.0.0.1:8082`，每次从首 token 失配 cache；TTFT 中位数 113.29 s，JSON verdict 通过 |

当前最强的预填充证据是 cold-prefill 8K 三次样本：中位 89.12 tok/s，离散范围仅 0.61 tok/s；其 8K TTFT 中位数为 113.29 s，端到端中位数 143.68 s。它与 contract 的 9,237-token、87.88 tok/s 单次结果相互印证。仍不能把这组数据解释为“batch 4096 或 pinned host memory 各自带来了多少提升”：两项在同一轮同时改变，且没有同语料的旧配置对照。

一次额外发现是：通过稳定 API `8081` 的 compatibility proxy 运行原始 streaming runner 时，首个可见 SSE 内容被延后到接近响应完成，导致 runner 将 decode 错算为约 15 万 tok/s。根因是代理仅把零 reasoning-budget 请求识别为 SSE，普通 SSE 被整段读取后才写回。该结果已明确作废，不纳入上表。修复为：普通 SSE 逐行立即 relay；仅 `thinking_budget_tokens: 0` 的请求保留思维前缀兼容变换。部署后通过 `8081` 重新跑 1K cold streaming smoke：TTFT 22.39 s、decode 8.08 tok/s、verdict 通过，和直接 `8082` 路径的量级一致。用户和 LAN 仍应继续使用受 CIDR 白名单保护的 `8081`；`8082` 只用于主机本地性能观测。这说明兼容边界的正确性契约与性能观测契约应分别验证。

## 5. Open WebUI：能力开关、工具与模型能力是三件事

今天最容易混淆的是以下三层：

1. **Capabilities / Default Features**：决定 Open WebUI 是否提供某种 UI 能力或默认启用它。
2. **Builtin Tools**：把 Time & Calculation、Web Search 等工具提供给当前聊天。勾选它并不保证模型会以正确 JSON 发出工具调用。
3. **Function Calling 模式**：决定 WebUI 如何与模型后端协商工具调用格式。

历史 Qwen/GLM 配置的有效经验是：保留确实要用的工具，关闭不使用的默认 Web Search、Image Generation、Code Interpreter 等，减少首条请求里工具 schema 和系统提示词的体积。对于 DeepSeek，`Time & Calculation` 可以保留；今天确认把模型的 **Advanced Params → Function Calling** 设为 **Native** 后，模型能够正确请求时间工具。

因此，日期正确性的首选路径是：

```text
用户问日期 -> 模型发起 native tool call -> Open WebUI 执行 Time & Calculation -> 将工具结果回传模型
```

架构决策是不应把当前日期硬塞进每次模型 prompt。当模型实际调用工具时，工具结果可审计、可随时区变化；而提示词注入既增加 token，也会把“模型知道日期”伪装成“模型调用了工具”。本次已从兼容代理、生产合同和部署参数中移除该注入。

## 6. 为什么仍有 OpenAI compatibility proxy

这个代理不是浏览器前端；它是后端和 Open WebUI 之间的一小段 API 适配。它的长期职责应仅限于隔离后端 OpenAI/SSE parser 缺陷。

已复现的后端问题是：在明确请求 `thinking_budget_tokens: 0` 时，某些响应仍可能把思维痕迹以不完整的 `<think>…</think>` 形式混入 `content`，并可能跨 SSE chunk 分裂。Open WebUI 因此会错误显示、解析或等待。

代理的处理以请求 JSON 中存在数值 `thinking_budget_tokens: 0` 为前提；该参数来自 Open WebUI 该模型的 Advanced Params，仓库不会下发它。2026-08-14 对 live SQLite `model.params` 的只读检查显示，当前 `Deepseek V4 Flash` Profile 和基础模型 Profile 都只保存了 `function_calling`，**没有** `thinking_budget_tokens`；因此当前真实 UI 流量会被代理纯透传。工具调用、结束事件和非零预算请求也保持透传。若日后显式设置零预算，SSE 只剥离**显式** `<think>` 前缀；前缀解析完成后，该 choice 进入直通状态，后续 content chunk 不再缓冲，因此保留正常流式输出。未闭合的显式思维标签会 fail-open 原样透传：宁可漏出痕迹，也不吞掉正文。

同步 JSON 另有一项受控兼容：当前 runtime 实测会省略开标签、仅输出内部文本加 `</think>`。为实现零预算不泄漏思维内容，代理会清理该 closing tag 之前的前缀，并写入不含 prompt/body 的 `suppressed_bare_thought_prefix` journal 事件。代价是：零预算下若正常正文恰好含字面量 `</think>`，该标记前的正文也会被清理；这不是无声行为但仍是格式歧义，应避免把这类文本作为零预算输出，直到 runtime 原生修复。

代理采用单进程 `ThreadingHTTPServer`，systemd 设 `MemoryMax=512M`、`TasksMax=32`；当前单用户足够，但 SSE 长连接并发能力有限。代理向下游每个响应发送 `Connection: close`，上游亦是一请求一连接，双向均不复用 keep-alive，高频短请求会有额外握手开销。它以 `DynamicUser`、空 capability 集、`PrivateDevices`、`ProtectSystem=strict` 等方式最小化权限，且日志只记 method/path，不记录 prompt body。

协议边界：chunked 请求体返回 501；请求体超过 8 MiB 返回 413；代理强制上游 `Accept-Encoding: identity`，零思考预算请求若上游仍返回非 identity 编码则返回 502。

### 6.1 已识别的职责边界

下列内容**不属于**代理职责：

- 注入“今天日期”的 system prompt；Native Function Calling 已经提供正确路径。
- 代替 Open WebUI 执行 Time & Calculation 或其他工具。
- 修改模型能力、工具选择或用户提示词。

当底层 runtime 原生稳定地满足上述 OpenAI/SSE 行为时，这个代理和对应兼容性回归用例都可以删除。

### 6.2 已移除的越界实现

代理此前曾在所有 `/v1/chat/completions` 请求上无条件注入 `Trusted current date` system message，并且生产合同将 `trusted-current-date` 作为必须通过的断言。这只能验证代理注入，不能验证模型通过 Native Function Calling 调用 Time & Calculation 的能力。

本次已删除 `inject_trusted_date_context()` 及调用、unit/defaults 中的 timezone 参数、日期注入自测与 `trusted-current-date` 合同。策略和渲染测试反向断言 unit 不得再携带 `--timezone`。日期能力仍由 Open WebUI 的 Native Function Calling 路径提供；已有单次 UI 手工确认，但尚无可重放的 UI 证据。

## 7. 何谓“API 契约”，为什么仍需要测试

所谓契约不是额外产品功能，而是自动化检查：若 Open WebUI 调用 `/v1`，后端必须给出它能够消费的响应。当前覆盖的关键场景包括：

- `/v1/models`、普通同步 chat 和 SSE chat；
- reasoning 与最终 `content` 的分离；
- 单工具、并行工具与工具结果 continuation；
- `thinking_budget_tokens: 0` 的前缀泄漏；
- 固定的中文、数学、代码、事实和长上下文正确性样例；
- 畸形工具调用和 SSE 的安全失败。

本次已在稳定入口 `8081` 运行不含日期注入的前台路径合同，19 项通过；guest 证据路径为 `/var/lib/deepseek-v4-ik/evidence/compatibility-contract.json`。它覆盖 API/SSE/reasoning/工具格式，但不把日期作为后端 API 能力断言。时间工具属于 Open WebUI 执行层，应以 UI 实测确认 Native Function Calling 是否真的调用该工具。

## 8. 安全与可运维性要点

- 镜像与模型 revision 必须 pin；浮动 tag（如 `main`、`latest`）会破坏可复现性。
- 模型与 runtime build 目录均只读挂载；当前候选容器不挂载可写数据或缓存卷，日志经 Docker local driver 有界落盘（20 MiB × 2）。
- 推理 API 默认 loopback/private gateway；若业务需要 LAN API，代理必须显式使用 source CIDR 白名单。这不是用户级鉴权，获准网段内的设备仍可调用模型。
- Open WebUI 的 SQLite 数据库是运行时配置权威。数据库已存在时，应先备份并验证连接，不能用环境变量反复覆盖它。
- 旧服务的退役要同时处理运行中的 unit、可重启脚本、环境文件和制品；仅从 Ansible 字典删除模型并不等于 guest 上的旧服务消失。
- 候选运行时当前刻意没有自动重启策略；若改为生产自愈策略，应显式选择单一 owner，并用 OOM/restart-churn 证据验证。
- 退役制品前先搜索反向依赖。此前 `candidate.yml` 在 `remove_legacy` 后仍依赖已删除的 `/opt/deepseek-v4/harness` 与 `deepseek-v4.service`；现已改为把 harness 安装到当前 runtime 的隔离目录，并停启 `deepseek-v4-ik.service`。受控 candidate 已实际运行多轮：每轮使用独立 Compose project 和不可覆盖的 evidence 目录，结束后恢复并核对原 owner/proxy；主 API 在候选切换期间会按互斥设计短暂停止。

## 9. 以后排障的建议顺序

1. 先明确是 UI、Open WebUI tool execution、兼容代理、还是模型 runtime 的问题。`8081` 连接拒绝时先检查 candidate unit，因为 `PartOf=` 会随 candidate 停止代理；`8081` 返回 502 时则说明代理还活着，应检查后端容器。
2. 直接从稳定 `/v1` 入口验证 `/v1/models`、同步 chat、SSE 和工具调用，再观察 UI。
3. 记录首轮和缓存命中后的性能，避免只用一条“感觉慢”的消息得出结论。
4. 对当前 layer split + CPU-MoE，优先采集 CPU 利用率/内存带宽、RSS/swap、两卡显存/利用率、TTFT、prefill/decode 与 restart count；PCIe/P2P topology 是补充证据，不是首要假设。
5. 任何涉及 GPU passthrough、驱动/CUDA、模型量化、GPU experts、context 或并发的改变，都先建立可回归的单变量基线。

## 9.1 受控性能收敛实验（2026-08-14）

以下比较使用同一模型、`128K` context、`batch-size=4096`、单并发、固定 1K/8K
语料、每档三次 cold-prefill 样本；除表中列出的变量外，其余运行时参数不变。性能
runner 对每个长度要求 decode 中位数至少 `8 tok/s`，因此 `fail` 只表示严格性能门未
达标，不表示 API 或正确性失败。

| 单变量 / 配置 | 1K decode 中位数 | 1K TTFT 中位数 | 8K decode 中位数 | 8K TTFT 中位数 | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| `--threads 36` | 6.78 tok/s | 23.48 s | 6.58 tok/s | 88.15 s | 明显回退，不采用 |
| `--threads 32` | **8.05 tok/s** | **21.99 s** | 7.68 tok/s | **85.44 s** | 优于 36，采用 |
| 关闭 pinned host memory（其余同 threads 32） | 7.72 tok/s | 24.31 s | 8.07 tok/s | 102.77 s | 8K TTFT 明显回退，恢复 pinned memory |

在先前的同一实验序列中，`NUMA=distribute` 相对 `none` 的 TTFT 略优；
`threads-batch=36` 优于 `0`；`ubatch=2048` 相比 `1536` 将 8K cold TTFT 降至约
85 秒，尽管 decode 有轻微波动，故选择 2048。上下文实验中，256K 能启动、长提示词
正确性通过，但 1K TTFT 升至约 36 秒；512K 在普通请求阶段即触发 CUDA OOM，不能作为
稳定配置。因此本机当前的实测最优组合为：

```text
context=131072, threads=32, numa=distribute, threads-batch=36,
batch-size=4096, ubatch-size=2048, pinned host memory=enabled
```

最终运行态已重新读取容器参数确认，稳定代理 `8081` 的 19/19 API 契约通过；两张 GPU
加载后分别约 10.14 GiB，后端健康且 slot 空闲。对应证据在 guest 的
`/var/lib/deepseek-v4-ik/evidence/`：`benchmark-threads32-clean.json`、
`benchmark-threads36-cold.json`、`benchmark-no-pinned-clean.json` 与
`compatibility-contract-threads32-proxy-clean.json`。

## 9.2 RAM cache、GPU expert 与 graph 收敛实验（2026-08-15）

本轮固定上一节的运行时、模型、128K context、双 GPU、batch/ubatch、线程、NUMA、
精度和网络边界，只改变一个主变量。每个候选先经稳定 `8081` 入口通过 19 项 API
契约，再运行性能/资源采样，最后恢复并核对生产 owner。证据分别保存在
`/var/lib/deepseek-v4-ik/evidence/<experiment-id>/`，不会覆盖前一轮，也不保存 prompt、
响应正文、凭据或 header。

### Host RAM cache

cache 结论以固定 A cold → A continuation → B cold → return A 序列的三组样本为主；
cold 1K/8K 数据用于检查回退，不把 cache 分支的 decode 阈值当成推广条件。

| `--cache-ram` | A continuation TTFT | Return-A TTFT | 1K / 8K cold PP | 1K / 8K cold TG | 最低可用 RAM | 结论 |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8 GiB | 5.56 s | 19.93 s | 77.49 / 122.59 tok/s | 7.92 / 7.56 tok/s | 165.9 GiB | 最小合格 control，保留 |
| 16 GiB | 6.00 s | 22.19 s | 77.03 / 121.57 tok/s | 7.72 / 7.59 tok/s | 157.7 GiB | Return-A 比 8 GiB 慢 11.4%，拒绝 |
| 32 GiB | 5.31 s | 18.36 s | 78.27 / 122.67 tok/s | 7.88 / 7.37 tok/s | 142.4 GiB | Return-A 快 7.9%，未达约 10%；探索性，不推广 |

因此“还有空闲 RAM”不代表扩大 cache 必然更快。对当前固定 A/B workload，32 GiB
确实有轻微收益，但未达到预先声明的推广线；额外 24 GiB 并不是主机容量上的阻断项。
如果目标改为“有稳定的 5% 收益就使用闲置 RAM”，应先修改决策规则并做干净重测，
而不是把本轮探索数据直接推广。最终仍采用 8 GiB。
需注意 `cache32-20260815-r1` 的旧 manifest 把已拒绝的 cache16 声明为 control，故该
轮只能作为探索性横向数据，不能被后续候选继承。实际稳定服务在实验前后均为 8 GiB，
且 32 GiB 相对 8 GiB 仍未达到推广线，因此不改变拒绝结论。自动化现在要求 16 GiB
必须先相对同一 8 GiB control 形成完整的拒绝证据，才允许 8→32 横向比较；任何新
control 仍必须有类型化 `qualification.json` 且 `accepted=true`。

### 单层 expert 迁移

第一步将 `--cpu-moe` 改为 `--n-cpu-moe 42`，即只把一层 expert 从 CPU 路径迁往
GPU。19 项契约全部通过，无 swap、OOM 或 restart；GPU0/1 峰值显存分别为
15,702/12,616 MiB，最低空闲分别为 8,874/11,960 MiB。1K decode 从 7.92 提升到
8.19 tok/s（约 3.4%），8K 从 7.56 提升到 7.74 tok/s（约 2.4%），但 8K 仍未达到
8 tok/s 门槛，TTFT 也没有改善。按“首个失败或收益不显著即停止”的规则，没有继续
测试 `n-cpu-moe=41`，生产仍保留全部 CPU-MoE。

### Graph split 前置条件

`topology-p2p-20260815-r1` 识别到两张 RTX 3090，GPU 间路径为 `PHB`；
`nvidia-smi topo -p2p r/w` 的两个方向均为 `NS`，没有 NVLink。该次环境没有
`p2pBandwidthLatencyTest` 可执行文件，且初版 PCIe query 使用了错误字段，因此完整
preflight 状态为 `incomplete`；不过明确的 P2P `NS` 已足以使 graph 不满足批准的
“两卡 P2P 前置通过”条件。故本轮没有启动 graph 候选，也没有伪造 layer-versus-graph
性能数字。之后已把采集器改成正确的 `pcie.link.*` 字段，并要求带宽样例显式报告
`P2P=Enabled` 才能通过，默认 fail closed。

### 实验与最终资格护栏

二次代码审查后，实验入口不再只相信 inventory 中“期望的”版本和参数。每次停服前
会重新校验 156 GB GGUF SHA-256、源码 commit、`llama-server` 二进制 SHA-256、实际
生产容器 image digest、完整 argv 顺序、双 GPU 环境、非 privileged 状态和只读模型
挂载；已有 control 的 contract、benchmark、cache、资源、日志、watchdog、恢复结果与
typed qualification 也必须齐全。这样可阻止重复 flag、脏构建或不完整 evidence 被误当
成合格 control。

资源 sampler 现在把 32 GiB `MemAvailable`、每卡 2 GiB 空闲显存、零 swap、零新增
OOM 和零 restart 作为 fail-closed 下限。越界会写入不含 prompt/response 的 abort
evidence，由 managed-host watchdog 立即 teardown 候选；controller 超过 20 分钟不再
刷新 heartbeat 时也会恢复生产 owner、代理并轮询本地 `/health`。一小时 soak 除样本
总数外还限制相邻 health probe 的最大空洞和单次 completion 时长，避免“前面密集采样、
最后长时间失明”仍被判定为通过。

### R6 最终资格结果与 prompt-cache 阻塞

`final-baseline-20260815-r6` 重新校验了实际运行容器的 image、完整 argv、双 GPU
环境、非 privileged 状态、只读模型挂载，以及 GGUF、源码和二进制 SHA-256。pre-soak
与 post-soak 的公开 API 契约均为 19/19；128K fixture 实际观察到 126,992 prompt
tokens，marker 和 token 数均匹配。该阶段的 547 个资源样本记录到 GPU0/1 峰值显存
12,360/12,580 MiB、容器峰值约 175.7 GiB、主机最低可用内存约 150.9 GiB，且没有
swap、OOM 或 restart。

一小时 soak 完成了 119 次 health probe 和 12 次 completion；12 次 completion 都精确
返回 `OK`，最长一次为 84.02 秒。361 个资源样本中容器峰值约 208.7 GiB、主机最低
可用内存约 119.0 GiB，两项服务始终 active，仍没有 swap、OOM 或 restart。资格门仍
严格判定为失败，因为首个冷 completion 运行期间，第 30 秒的 `/health` 请求超时；相邻
health 的最大空洞为 60.0001 秒，超过 60 秒边界。之后 health 全部恢复，post-contract
仍为 19/19，只读 `verify` 也通过。因此这是“服务未崩溃，但控制请求在冷转换期间被
阻塞”的可用性缺陷，不能写成完整资格通过。

后端日志给出了直接归因：从 127K 对话切换到短请求时，pinned ik runtime 同步保存
127,048-token prompt cache，单条 state 为 34,116.6 MiB，保存耗时 72.15 秒。当前
`--cache-ram=8192` 并不会拒绝这个超大单条；pinned 源码的驱逐逻辑会“始终至少保留
一个 state”，所以它先执行整条复制，再移除其他旧条目。health 请求在同一后端任务
队列中等待，直到保存结束才统一返回 200。把上限提高到 32 GiB 仍不会消除这次约
34.1 GiB 的同步复制；它主要改变其他对话能否同时留在 cache。

因此本轮已完成的候选比较仍不改变运行配置：继续使用 8 GiB cache、全部 CPU-MoE、
layer split。准确结论是“这些候选未达到原定推广线”，而不是它们永远不值得继续研究：
若另行修订实验契约，`n-cpu-moe=41/40` 可验证多层收益是否累积；32 GiB 可用更多重复
样本验证项目切换收益。要修复本次最终资格阻塞，则需单独评审超大 prompt-cache policy
或修改 pinned runtime 使保存不阻塞控制请求，不能通过放宽 soak 阈值来伪造通过。

## 9.3 checkpoint=8 单次诊断（2026-08-15）

为避免立即重复三次 127K 和一小时 soak，本轮先运行了明确不可推广的单次诊断
`checkpoint8-diagnostic-20260815-r4`。候选固定 R6 的模型、runtime、128K context、
双 GPU、8 GiB RAM cache、CPU-MoE 和 layer split，只把 `--ctx-checkpoints` 从运行时
默认的 32 改为 8。19 项公开 API 契约全部通过；实验后精确恢复生产 owner、代理、
镜像和完整 argv，只读 `--tags verify` 通过。

本轮长请求实际为 116,445 tokens，而不是目标 127,000，原因是初版 transition runner
用固定的 `target/12` 粗估 filler 数量。其 cold prefill 为 931.94 秒，约
124.95 tok/s。虽然该 token 数仍足以触发 checkpoint 保存路径，但它不满足 127K
正确性资格，因此 marker 回忆失败不能用于判断 128K 能力。runner 已改为先调用当前
pinned server 实测可用的只读 `/tokenize` 接口校准，再只发送一次真实长 completion；
旧 context runner 也一并移除了最多五次长 completion 校准，避免一次资格测试膨胀为
多轮 127K prefill。

性能机制的结果仍有价值：checkpoint=8 的 prompt-cache 保存耗时为 21.97 秒，短请求
交接总时长为 27.58 秒；对照 R6/checkpoint=32 的保存耗时 72.15 秒，保存阶段缩短约
69.5%。但保存期间仍有 1 次 `/health` 的 10 秒超时，短请求也没有严格只返回 `OK`，
故候选被拒绝。这一观察强烈支持 checkpoint 数量是同步 host-RAM state 深拷贝/序列化
时延的重要杠杆，但 R6 与本轮的 token 数和 runner 并不完全相同；只有修复校准后用
同一 runner 完成显式 32 对 8 的重复比较，才能建立严格的单变量因果结论。本轮更没有
证明 8 已达到正确性或可用性门槛。

1K/8K cold benchmark 与同 runner 的 8 GiB control 基本持平：1K PP/TG 分别变化
-1.34%/+0.10%，TTFT +3.75%；8K PP/TG 分别变化 -0.81%/-0.47%，TTFT +2.01%。
绝对 decode 中位数为 7.93/7.52 tok/s，仍低于既定 8 tok/s 门，因此 benchmark 状态
为 fail；这不是进程崩溃。资源采样记录零 swap、零 OOM、零 restart，每卡峰值显存约
12.5/12.7 GiB，主机最低仍有约 159 GiB `MemAvailable`。

本次还纠正了一个控制面误解：终端工具约 30 秒返回会话 ID 只是输出 yield，不会回收
Ansible controller 或终止远端 async job。真实中断风险来自控制进程/开发容器退出、
SSH 长期断开，或显式的 Ansible/runner/watchdog 超时；本轮 Ansible 会话跨多个 30 秒
窗口持续了约 36 分钟，并完成了候选 teardown 与生产恢复。

## 9.4 插槽调整、平台固定与校准后的 checkpoint=8 诊断（2026-08-17）

物理调整后，两张 RTX 3090 在来宾中的拓扑关系由跨系统路径变为 `PHB`，说明它们现在
位于同一 host bridge 下；但 `nvidia-smi topo -p2p p/n` 的 read/write 结果仍为 `NS`，
因此不能把同 root/bridge 等同于 GPU P2P 已可用，graph split 仍保持阻断。GPU0
`13:00.0` 协商宽度为 x16，GPU1 `1b:00.0` 仍为 x8；空闲时两卡速率显示 Gen1 是电源
管理降速，不代表负载下只能运行 Gen1。宿主 topology 证据保存在
`/var/lib/deepseek-v4-ik/evidence/slot2-slot4-20260817/topology-p2p.json`。

LLM VM 已固定并实际验收 `6.8.0-101-generic`、NVIDIA userspace/kernel module
`590.48.01`、两张精确型号的 RTX 3090、11 个精确 APT hold、窄范围 unattended-upgrades
blacklist 和固定 GRUB entry。单独的 `platform-verify` 重跑为 `changed=0`；这避免下次普通
自动更新再次改变已验证的 kernel/driver 组合。

校准后的单次诊断 `checkpoint8-diagnostic-20260817-r2` 通过了 19/19 公开 API 契约，
实际校准为 127,001 tokens、API 观察为 127,005 tokens。长请求耗时 677.80 秒；随后
短请求 handoff 为 30.98 秒，期间仍有一次 10.01 秒 `/health` 超时。对照旧的显式
checkpoint=32、同为 transition-v2 的 R6 三次中位数 84.06 秒，handoff 方向性缩短约
63.1%；127K recall 耗时相对 R6 中位数 1,047.51 秒缩短约 35.3%。但两次证据之间还
发生了 kernel 和 PCIe 插槽调整，因此这些百分比不是严格的单变量因果证明。

本轮 1K cold benchmark 的 PP/TTFT/TG 中位数为 78.22 tok/s、22.44 秒、
7.39 tok/s；8K 为 181.04 tok/s、63.50 秒、7.34 tok/s。相对旧 R6，1K 基本持平；
8K PP 提高约 48.1%、TTFT 缩短约 27.6%，但同样受平台变化干扰。TG 分别低约
2.3%/3.0%，没有明显 decode 收益。R6 benchmark 使用 0 tok/s 的证据阈值，而本轮使用
8 tok/s 晋级阈值，所以不能直接用两个 JSON 的 `pass/fail` 字段比较性能；本轮 fail
主要来自绝对 TG 门和 transition 正确性/health 门，而不是崩溃。

资源证据记录到两卡峰值显存 12,472/12,618 MiB、最低空闲 12,104/11,958 MiB，主机
最低 `MemAvailable` 约 159.6 GiB；全程 swap=0、OOM=0、container restart=0。实验结束后
生产 owner、代理、image、command 和完整容器边界均精确恢复，公开 `/health` 为 200。

正确性结果暂不能作为 checkpoint 机制的最终判断：旧 transition runner 给短请求只有
`max_tokens=8`，reasoning 模型把预算耗在 `reasoning_content` 后没有最终 `content`；长
recall 也只给 64 tokens。本轮之后 runner 已改为显式
`thinking_budget_tokens=0` 且最多 256 tokens，本地 self-test、Python 编译、Ansible
syntax、policy 与完整 render 测试均通过，但尚未重新运行长诊断。因此当前可收敛的结论
是：checkpoint=8 显著缩短同步切换阻塞，但 31 秒 handoff 和一次 health 超时仍未达到
资格门，生产配置保持不变。

本轮还修复了一个实验生命周期竞态。原 sampler 在稳定容器 teardown 的瞬间遇到一次
`nvidia-smi` 不可用，误写 `gpu-collection-incomplete`，watchdog 随即恢复生产并与候选
争抢 8082。新顺序是在端口释放后先等精确 GPU 0/1 恢复，再启动 sampler、确认首个
JSON 样本，最后启动候选；清理时先等 sampler 真正退出再 teardown candidate。

## Q&A 摘要

**Q：两张 3090 为什么没有自动变成 48GB？**

A：显存物理上仍分属两张 GPU，当前 runtime 也不是 TP。更关键的是，48GB 即使能池化也不足以放下约 145.6 GiB 的模型，因此专家走 CPU-MoE 路径。

**Q：首条消息为何显著更慢？**

A：一般首轮要处理系统提示词、工具 schema 和冷缓存；后续轮次可命中 KV cache。
本次还实测到一个独立原因：从 127K 对话切换到新短请求时，host prompt cache 同步保存
约 34.1 GiB state，阻塞后端任务队列约 72 秒。两种延迟必须分别测量，不能都归为 prefill。

**Q：Time & Calculation 勾选后为什么模型之前仍会答错日期？**

A：勾选只是让 WebUI 提供工具。模型还必须以与后端兼容的方式发起 function call；本次设为 Native 后该路径正常。

**Q：compatibility proxy 是不是多余的前端层？**

A：不是前端层。它暂时隔离已实测的后端 API parser/SSE 格式缺陷；日期注入已移除，因此不会再修改模型语义或掩盖 Time 工具是否真实被调用。

## 10. 尚未验证 / 待办

- **R6 资格阻塞（2026-08-15）**：证据目录
  `/var/lib/deepseek-v4-ik/evidence/final-baseline-20260815-r6/` 已不可变保留。
  2026-08-17 的校准版 checkpoint=8 单次诊断已观察到 127,005 tokens、30.98 秒
  handoff 和一次 health 超时，方向有效但仍未推广。下一次长诊断应先使用已经修正的
  zero-thinking/256-token 正确性请求；若要建立严格因果，还需在当前 kernel/插槽条件下
  补一个同 runner 的显式 checkpoint=32 control。只有 8 仍不满足可用性且证据继续指向
  checkpoint 数量时才考虑 4。若不能兼顾保存时延和长对话恢复，再评审
  cache policy 跳过超大单条，或修改并重新钉住 ik runtime 使保存不阻塞 health/control
  请求。任何路线都必须重跑 128K→短请求转换、完整一小时 soak 和 post-contract；不能
  仅将 health timeout 或 60 秒空洞阈值调大后宣称通过。
- **PCIe 后续（2026-08-17）**：Slot2/Slot4 调整后两卡已为 `PHB`，GPU0 为 x16，
  GPU1 仍为 x8，P2P read/write 仍为 `NS`。下一次维护只需继续核查 GPU1 的插槽电气
  lane、riser/adapter、BIOS bifurcation 和 ESXi passthrough 路径；不要重复移动已经为
  x16 的 GPU0。补齐 CUDA `p2pBandwidthLatencyTest` 前，不启用 graph split。
- 早期采样曾记录双卡空闲常驻显存约 5.2/6.2 GiB；后续固定 128K
  基线的空闲采样约为 11.9/11.7 GiB。两者来自不同运行阶段，均不能代替峰值证据；
  最终应以资格验证的 `resources-context-summary.json` 与
  `resources-summary.json` 为准。维护窗口后仍需做 layer split 的单卡/双卡固定
  corpus 基准，不能假定第二张卡自动带来算力叠加。
- 为 Native Function Calling 的 Time & Calculation 路径留下可重放的 UI 集成验证证据。
- 记录后端在 `thinking_budget_tokens: 0` 下泄漏思维前缀的原始请求/响应片段，避免只依赖回归用例证明“曾经发生”；如要使兼容分支在 UI 流量中生效，需先在两个相关 Open WebUI Profile 的 Advanced Params 显式配置该字段。
- 为同步零预算的裸 `</think>` 兼容建立更明确的上游格式修复路径；当前仍可能清理含该字面量的正常正文。
- pinned host memory、batch 4096 / ubatch 2048 已完成固定语料的单变量比较；当前最佳组合见 §9.1。若改变 PCIe 链路、GPU 插槽、runtime、量化或并发，必须重新从该基线开始测量。
- PCIe/ESXi 维护后重跑修复版 topology 采集器，并补齐 CUDA
  `p2pBandwidthLatencyTest`；只有显式 `P2P=Enabled` 才重新开放 graph A/B。
- 候选实验现已使用 managed-host watchdog：controller heartbeat 超时、swap/OOM、
  restart 或资源余量越界会触发候选 teardown，并重试恢复生产 owner、代理和本地
  `/health`。仍需在今后的真实失败注入中定期复验该恢复路径。
