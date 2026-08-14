# 学习笔记：DeepSeek V4 Flash 双 GPU 部署、验证与 Open WebUI 集成

**日期**：2026-08-14
**标签**：#LLM #DeepSeek #GGUF #llama.cpp #OpenWebUI #Ansible #GPU #ESXi #PCIe

本文记录今天将 DeepSeek V4 Flash GGUF 候选运行时接入现有 homelab 的全过程。重点不是把一次部署包装成“成功案例”，而是说明哪些判断有实测证据、哪些只是待继续验证的假设，以及为什么最终架构会比一开始看起来多出一些保护措施。本文对应的 Ansible 变更尚未提交；本文所述 live 状态已通过 guest 上的 `systemctl cat`、`ss` 和 API 合同复核，不应仅凭工作区文件推断线上状态。

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
| `GGML_CUDA_NO_PINNED` | `1` | 禁用 pinned host memory，直接影响 H2D；设置动机待核查，可能是稳定性与传输性能的折衷 |
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
- 退役制品前先搜索反向依赖。此前 `candidate.yml` 在 `remove_legacy` 后仍依赖已删除的 `/opt/deepseek-v4/harness` 与 `deepseek-v4.service`；现已改为把 harness 安装到当前 runtime 的隔离目录，并停启 `deepseek-v4-ik.service`。该改动已通过本地策略与语法校验；尚未实际运行 candidate，因为它会按互斥设计短暂停止主 API。

## 9. 以后排障的建议顺序

1. 先明确是 UI、Open WebUI tool execution、兼容代理、还是模型 runtime 的问题。`8081` 连接拒绝时先检查 candidate unit，因为 `PartOf=` 会随 candidate 停止代理；`8081` 返回 502 时则说明代理还活着，应检查后端容器。
2. 直接从稳定 `/v1` 入口验证 `/v1/models`、同步 chat、SSE 和工具调用，再观察 UI。
3. 记录首轮和缓存命中后的性能，避免只用一条“感觉慢”的消息得出结论。
4. 对当前 layer split + CPU-MoE，优先采集 CPU 利用率/内存带宽、RSS/swap、两卡显存/利用率、TTFT、prefill/decode 与 restart count；PCIe/P2P topology 是补充证据，不是首要假设。
5. 任何涉及 GPU passthrough、驱动/CUDA、模型量化、GPU experts、context 或并发的改变，都先建立可回归的单变量基线。

## Q&A 摘要

**Q：两张 3090 为什么没有自动变成 48GB？**

A：显存物理上仍分属两张 GPU，当前 runtime 也不是 TP。更关键的是，48GB 即使能池化也不足以放下约 145.6 GiB 的模型，因此专家走 CPU-MoE 路径。

**Q：首条消息为何显著更慢？**

A：首轮要处理系统提示词、工具 schema 和冷缓存；后续轮次可命中 KV cache。

**Q：Time & Calculation 勾选后为什么模型之前仍会答错日期？**

A：勾选只是让 WebUI 提供工具。模型还必须以与后端兼容的方式发起 function call；本次设为 Native 后该路径正常。

**Q：compatibility proxy 是不是多余的前端层？**

A：不是前端层。它暂时隔离已实测的后端 API parser/SSE 格式缺陷；日期注入已移除，因此不会再修改模型语义或掩盖 Time 工具是否真实被调用。

## 10. 尚未验证 / 待办

- 已记录当前双卡空闲常驻显存约 5.2/6.2 GiB，合计低于单卡 24 GiB；下一步应在维护窗口做 layer split 的单卡/双卡固定 corpus 基准。单流下两卡按层交替执行，不能假定第二张卡带来算力叠加。
- 为 Native Function Calling 的 Time & Calculation 路径留下可重放的 UI 集成验证证据。
- 记录后端在 `thinking_budget_tokens: 0` 下泄漏思维前缀的原始请求/响应片段，避免只依赖回归用例证明“曾经发生”；如要使兼容分支在 UI 流量中生效，需先在两个相关 Open WebUI Profile 的 Advanced Params 显式配置该字段。
- 为同步零预算的裸 `</think>` 兼容建立更明确的上游格式修复路径；当前仍可能清理含该字面量的正常正文。
- 确认 `GGML_CUDA_NO_PINNED=1` 的设置动机，并在安全的单变量实验中评估其对 H2D 的影响。
- 在维护窗口实际运行一次修复后的 candidate 流程，验证 harness、基准和主服务恢复的完整闭环。
- 若候选转生产，设计并验证明确的单一自动恢复 owner；当前故障恢复仍是人工操作。
