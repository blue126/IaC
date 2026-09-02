---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 6
research_type: 'technical'
research_topic: 'Hermes Agent 与 OpenClaw 的本地后端模型选型'
research_goals: '在双 RTX 3090、48 GB 显存与既有 DeepSeek V4 Flash 实测约束下，比较 Qwen3.6-27B、Qwen3.8-27B、Qwen3-Coder-Next 80B、Hermes 4.3 36B 与 DeepSeek V4 Flash，给出框架适配、工具调用可靠性、GGUF 供应链、量化档位及可执行验收方案。'
user_name: 'Will'
date: '2026-08-18'
web_research_enabled: true
source_verification: true
---

# Research Report: Hermes Agent 与 OpenClaw 的本地后端模型选型

**Date:** 2026-08-18
**Author:** Will
**Research Type:** technical

---

## Research Overview

本研究聚焦两个框架的实际协议与运行要求，不以单一编码榜分数代替 agent 可靠性。关键结论将优先由官方仓库、官方模型卡、官方榜单或论文支持，并明确区分厂商自报与独立验证。

---

## Technical Research Scope Confirmation

**Research Topic:** Hermes Agent 与 OpenClaw 的本地后端模型选型
**Research Goals:** 在给定双 RTX 3090 拓扑和已实测 DeepSeek V4 Flash 性能下，选择可落地的本地模型，并建立工具调用、长程任务、量化与供应链验收门禁。

**Technical Research Scope:**

- Architecture Analysis - 两个 agent 框架的模型接口、工具协议、上下文与多模态路径
- Implementation Approaches - 单一后端、分框架后端及慢模型升级路径
- Technology Stack - llama.cpp、GGUF、chat template 与推理参数
- Integration Patterns - OpenAI-compatible API、结构化输出、并行工具调用与 prompt caching
- Performance Considerations - 双 3090 放置、量化档位、TTFT/decode 与任务成功率

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-08-18（用户已通过六项明确问题和输出要求授权开展该范围研究）

---

## Research Synthesis

### Executive Summary

当前最稳妥的共同生产基线是 **Qwen3.6-27B-MTP，标准 Q5_K_M，文本模式**；不需要先给 Hermes Agent 与 OpenClaw 各配一个模型。原因不是它在单一编码榜最高，而是已经有精确到框架的第三方结果：PawBench 同一模型在 OpenClaw 为 72.9、Hermes 为 68.2，直接说明 harness 会改变结果，也同时证明两套框架都可用。Qwen3.8-27B 的厂商自报编码/agent 数字明显更强，但权重与 GGUF 太新，缺少同等强度的 Hermes/OpenClaw 独立复现，适合作为立即测试的 challenger，而不是未经本机门禁直接替换。

Hermes 4.3 36B 不应因“同源”优先。Nous 官方明确警告 Hermes 4 系列面向聊天/推理，不适合 Hermes Agent 所需的高频工具循环。Qwen3-Coder-Next 80B/3B active 只建议作为代码专用实验：它占用几乎全部显存、只能 non-thinking，且当前厂商 agentic coding 分数没有构成对 Qwen3.6/3.8 的确定优势。

DeepSeek V4 Flash 保留为高风险任务的升级档，而非默认常驻后端。它适用于跨仓库修改、迁移、安全和根因不明且一次错误代价高的任务；9 tok/s 与 8K 提示 38 秒 TTFT 会显著拖累高频工具循环。是否“慢但对”必须由本机的 verified completion 与 false-completion 指标证明，不能只靠厂商 SWE-bench 数字。

### Evidence Classification

| 证据 | 类型 | 可用于什么结论 |
|---|---|---|
| Qwen3.6 模型卡：SWE Verified 77.2、Terminal-Bench 2.0 59.3、Claw-Eval 72.4 | 厂商自报，且 SWE 使用内部 scaffold | 能力上限与候选筛选，不能直接预测本机两个框架 |
| Qwen3.8 模型卡：SWE-bench Pro 61.7、DeepSWE 42.2、LiveCodeBench v6 90.3 | 厂商自报；与 3.6 的版本、scaffold、采样未完全对齐 | 支持“值得挑战”，不支持“已确定胜出” |
| PawBench：Qwen3.6-27B / OpenClaw 72.9 / Hermes 68.2 | 第三方、精确 model × harness，150 任务 | 当前最直接的框架契合证据 |
| Claw-SWE-Bench：模型差 29.4pp、harness 差 27.4pp | 学术第三方 | 编码榜不能替代实际 harness A/B |
| MLCommons 选 Qwen3.6 Q4_K_M + BFCL v4 + agentic replay | 独立标准组织 | Q4_K_M 是合理的 edge 基线，不代表 Q4 与更高精度等价 |

Sources: [Qwen3.6 model card](https://huggingface.co/Qwen/Qwen3.6-27B), [PawBench](https://agentscope-ai.github.io/PawBench/en/), [Claw-SWE-Bench](https://arxiv.org/abs/2606.12344), [MLCommons edge agentic benchmark](https://mlcommons.org/2026/07/mlperf-inference-v61-edge-agentic/)

## Framework Integration Findings

### Hermes Agent

- 任意 OpenAI-compatible `/v1/chat/completions` 端点均可作为自托管后端。
- 主模型承担每个消息和每个工具循环；compression、vision、web extract、MCP routing 等辅助槽可单独配置。
- 实际上下文必须至少 64K；压缩模型上下文不能小于主模型，否则中间轮次可能在压缩失败后丢失。
- Nous 明确不推荐 Hermes 4 用作 Hermes Agent 主模型，因为其训练目标是聊天/推理而非 rapid-fire tool calling。
- 对有副作用或前后依赖的工具，默认关闭 parallel tool calls。Hermes issue #69119 的 A/B 中，强制 `parallel_tool_calls:false` 后，依赖批次从 10/10 错误变成 10/10 正确。

Sources: [Hermes custom/self-hosted providers](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md), [Hermes model slots](https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models), [Nous Portal Hermes 4 warning](https://hermes-agent.nousresearch.com/docs/integrations/nous-portal), [dependent tool-call issue](https://github.com/NousResearch/hermes-agent/issues/69119)

### OpenClaw

- llama.cpp 应按 custom OpenAI-compatible provider 配置，使用 `openai-completions`；只有后端明确完整支持时才切 `openai-responses`。
- 对本地模型打开 `agents.defaults.experimental.localModelLean`，缩小工具 schema 与隐藏上下文；工具 schema 本身会占上下文。
- 若工具调用以 JSON/XML 文本而不是结构化 `tool_calls` 返回，不要写正则代理“修复”，应修正 Jinja/template/parser。
- OpenClaw 自带 `pnpm qa:code-mode-models -- --model ...`，可记录工具调用、失败分类、计时和已验证副作用，适合作为首层本地门禁。
- custom/proxy route 不发送 OpenAI 专属 prompt-cache hints；这不等于禁用 llama.cpp 自身的 prefix/KV cache。

Sources: [OpenClaw local models](https://github.com/openclaw/openclaw/blob/main/docs/gateway/local-models.md), [OpenClaw agent/model matrix](https://github.com/openclaw/openclaw/blob/main/docs/cli/agent.md), [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

## Model Decision

### 1. Production Baseline: Qwen3.6-27B-MTP Q5_K_M

- Qwen3.6 本身就是带 vision encoder 的原生多模态模型；“3.8 是 VLM、3.6 是纯文本”这一前提不成立。
- 纯文本服务时不加载 mmproj；llama.cpp 将 projector 作为独立文件，因此不会支付视觉编码计算和显存成本。
- 优先标准 Q5_K_M；如果要求单卡且 128K 上下文 OOM，再退 Q4_K_M。两卡 Q6_K 是准确率 control，不是默认生产档。
- 先在无 MTP 下完成质量基线，再启用 `draft-mtp`。Qwen3.6 官方对 vLLM 推荐 2 个 speculative tokens；llama.cpp 主线已有 Qwen3.5/3.6 MTP graph，但收益对 build、GPU backend 和 `-np` 敏感。

Sources: [Qwen3.6 architecture, context, tool parser and MTP](https://huggingface.co/Qwen/Qwen3.6-27B), [llama.cpp Qwen MTP graph](https://github.com/ggml-org/llama.cpp/blob/master/src/models/qwen35.cpp), [llama.cpp speculative options](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md), [llama.cpp multimodal separation](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)

### 2. Immediate Challenger: Qwen3.8-27B Q5_K_M/Q6_K

- 厂商同表结果支持它可能显著强于 3.6，但截至 2026-08-18 缺少可复现的 Hermes/OpenClaw/BFCL 精确组合结果。
- 原生多模态不是纯文本劣化的充分理由：3.6 同样是多模态，且 projector 可不加载。真正风险是新模型的 chat template、tool parser、reasoning history 与第三方 GGUF 转换尚未充分磨合。
- 只有在本机 paired A/B 达到晋级阈值后替换 3.6；不建议先按框架拆成两个后端。

### 3. Deprioritized Candidates

- **Hermes 4.3 36B**：虽有 schema adherence、JSON repair 和工具格式训练，且 Nous 提供官方 GGUF，但官方 Hermes Agent 文档明确反对把 Hermes 4 用作主 agent。OpenClaw 可以解析其格式，但没有足够证据证明胜过 Qwen3.6。
- **Qwen3-Coder-Next**：80B total / 3B active、48 层、512 专家、10 active + 1 shared、仅 non-thinking；在无 P2P 双 3090 上占用大、通用 agent 覆盖窄。仅在 90% 以上任务为代码且本机评测取胜时采用。

Sources: [Hermes 4.3 model card](https://huggingface.co/NousResearch/Hermes-4.3-36B), [official Hermes 4.3 GGUF](https://huggingface.co/NousResearch/Hermes-4.3-36B-GGUF), [Qwen3-Coder-Next model card](https://huggingface.co/Qwen/Qwen3-Coder-Next)

## GGUF Supply Chain and Quantization

### Recommended Baseline Artifact

Known immutable Qwen3.6 MTP Q5_K_M artifact:

- Repository: `unsloth/Qwen3.6-27B-MTP-GGUF`
- Revision: `e61310b84ddc5e4b47b2422bf60f1a22342c36d0`
- File: `Qwen3.6-27B-Q5_K_M.gguf`
- Size: 19.8 GB
- SHA-256: `e85d114efc50b6df20b5707042f9092afed852a3c9958a478efec4bc79f148a7`

Source: [immutable Hugging Face file page](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF/blob/e61310b84ddc5e4b47b2422bf60f1a22342c36d0/Qwen3.6-27B-Q5_K_M.gguf)

Policy:

1. Pin model repository revision, GGUF SHA-256, mmproj SHA-256 if used, and llama.cpp commit separately.
2. Verify local `sha256sum -c` before atomically changing the service symlink.
3. Run `llama-model-loader --print-details`/server startup checks for architecture, tokenizer, embedded chat template, MTP layer and context metadata.
4. Third-party quantization is an independently built binary artifact, not equivalent to official weights. Reputable publisher lowers operational risk but does not prove semantic equivalence.
5. Qwen3.8 production supply chain should initially self-convert from a pinned official BF16 revision with a pinned llama.cpp converter and recorded imatrix corpus; otherwise pin the third-party repository revision plus each file SHA and treat it as a canary.

Standard Q5_K_M is preferred over Dynamic quantization for the baseline because 48 GB provides headroom and Q5 is simpler to compare across publishers. UD-Q5_K_XL is a challenger after the standard quant passes; the DeepSeek UD-Q3 fit rationale does not transfer to a 27B dense model. Avoid extreme KV quantization during evaluation: llama.cpp warns that Q4 KV can materially degrade tool calling.

Source: [llama.cpp function-calling and KV warning](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)

## Executable Validation Plan

### Server Baseline

Start with 128K, one slot, Jinja, text-only, F16/Q8 KV, and no MTP. If Q5 cannot fit one 3090 with buffers/KV, compare Q4 single-GPU with Q5/Q6 layer split across two GPUs; do not CPU-offload dense layers for the production candidate.

```bash
./llama-server \
  -m /models/qwen36/Qwen3.6-27B-Q5_K_M.gguf \
  -ngl all -c 131072 -np 1 -fa on --jinja \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --cache-prompt --host 127.0.0.1 --port 8080
```

Confirm `/props` exposes a tool-aware template, then send direct `/v1/chat/completions` probes. Only after the non-speculative quality run passes, add:

```bash
--spec-type draft-mtp --spec-draft-n-max 2 \
--spec-draft-type-k f16 --spec-draft-type-v f16
```

Sweep `n_max=1,2,3` and optionally `--spec-draft-p-min`; accept MTP only if verified outcomes are unchanged and time-to-correct-completion improves. Community reports are not a performance guarantee; current llama.cpp discussions show both gains and regressions across builds/backends.

### Artifact Download and Verification

```bash
hf download unsloth/Qwen3.6-27B-MTP-GGUF \
  Qwen3.6-27B-Q5_K_M.gguf \
  --revision e61310b84ddc5e4b47b2422bf60f1a22342c36d0 \
  --local-dir /models/qwen36

cd /models/qwen36
printf '%s  %s\n' \
  e85d114efc50b6df20b5707042f9092afed852a3c9958a478efec4bc79f148a7 \
  Qwen3.6-27B-Q5_K_M.gguf > SHA256SUMS
sha256sum -c SHA256SUMS
```

### Framework Configuration

Hermes main model:

```bash
hermes config set model.provider custom
hermes config set model.base_url http://127.0.0.1:8080/v1
hermes config set model.default qwen3.6-27b-mtp-q5
hermes config set model.context_length 131072
```

For OpenClaw, register the endpoint as `openai-completions`, declare `reasoning: true`, `input: ["text"]`, `contextWindow: 131072`, and enable lean mode:

```bash
openclaw config set agents.defaults.experimental.localModelLean true
```

Use `parallel_tool_calls:false` for any write, delete, message, deploy or other side-effecting tool set. Only enable parallel calls for independent read-only operations after an explicit test.

### Three-Layer Gate

1. **Protocol gate:** 100–200 tool probes covering one tool, no-tool, wrong/missing parameter, multiple independent tools, Unicode/path quoting and malformed tool output. Require zero unparsed calls and zero silent conversion of assistant text into tool execution.
2. **Environment gate:** 40–50 real tasks, each repeated three times in both Hermes and OpenClaw. Inject `ENOENT`, nonzero exit, timeout, stale result, malformed JSON and cross-source conflict. Check real git diff, tests and external state rather than final prose.
3. **Long-horizon gate:** repeat at 8K/32K/64K/128K effective context, including compression/resume. Inspect turns 1/10/25/50 for instruction drift and false claims.

Primary metrics: verified pass@1/pass^3, malformed calls per 100, wrong tool/arguments, no-tool false positive, recovery@1, false-completion rate, dead-loop rate, p50/p95 TTFT, and time-to-correct-completion. Promotion rule: zero false file/state claims; zero malformed calls in protocol gate; paired verified success improves at least 5pp, or stays within 2pp while time-to-correct-completion improves at least 30%; no regression on destructive/side-effect tasks.

Use BFCL v4 for schema/no-tool/multi-turn/parallel coverage, ToolBench-X for recoverable hazards, τ-bench for policy/user/tool interaction, AgentDojo for prompt-injection resistance, and actual framework runs for filesystem truthfulness. Old ToolBench is not a primary selection gate.

Sources: [BFCL v4](https://gorilla.cs.berkeley.edu/leaderboard.html), [ToolBench-X](https://arxiv.org/abs/2606.25819), [τ-bench](https://arxiv.org/abs/2406.12045), [AgentDojo](https://agentdojo.spylab.ai/)

## Final Recommendation

1. Deploy one shared Qwen3.6-27B-MTP Q5_K_M profile for Hermes Agent and OpenClaw; establish the non-MTP baseline first.
2. Immediately run Qwen3.8-27B Q5_K_M/Q6_K as a shadow challenger. Promote it for both frameworks only after the paired local gate; do not infer superiority from release date or unmatched vendor benchmarks.
3. Keep DeepSeek V4 Flash as a manually selected high-assurance profile for expensive-to-get-wrong tasks. Because models cannot coexist, switch by work session or queue, not per tool call.
4. Do not prioritize Hermes 4.3 for Hermes Agent despite shared branding; Nous' own documentation rules it out as the main rapid-tool-loop model.
5. Revisit separate per-framework models only if the same quant/runtime produces a persistent, statistically material harness interaction after template and configuration are controlled.
