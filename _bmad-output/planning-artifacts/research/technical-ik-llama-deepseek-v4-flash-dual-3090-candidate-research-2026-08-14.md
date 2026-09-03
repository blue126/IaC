---
stepsCompleted: [1, 2, 3, 4, 5, 6]
workflowType: 'research'
research_type: 'technical'
research_topic: '新版 ik_llama.cpp + GGUF 作为 DeepSeek V4 Flash 双 RTX 3090 独立候选'
research_goals: '判断是否值得在不影响现有 KTransformers TP2 服务的前提下建立可复现实验候选'
user_name: 'Will'
date: '2026-08-14'
web_research_enabled: true
source_verification: true
---

# ik_llama.cpp / GGUF 双 RTX 3090 候选调研

## 结论

不建议现在直接切换该候选，但受控性能实验已证明其值得保留。2026-08-14 已将现有系统盘原地扩展至 900GB，独立候选在 loopback、双 RTX 3090、TP layer split、CPU-MoE 下完成了制品、正确性与固定性能测试。

原因有三项：

1. 以 `--threads 32`（36 vCPU、两 NUMA 节点）运行时，固定三次中位 decode 为 1K `8.82 tok/s`、8K `8.96 tok/s`，均超过 8 tok/s 门槛；这是相对 16 线程（1K `6.57`、8K `7.00 tok/s`）约 34% 与 28% 的提升。
2. 当前 VM 的两张 3090 没有 P2P，且公开资料报告过非 P2P 双 3090 的 layer split 在较长上下文产生错误输出。现场 1K/8K 正确性通过，但仍需要更长 soak 才能解除这一风险。
3. API 契约中 17/18 项通过；同步的“exactly OK”失败，因为受控 `thinking_budget_tokens=0` 请求会把思考文本泄到 `content`，而非可安全分离到 `reasoning_content`。这阻止把候选接入 Open WebUI 或替换现役服务。

## 现场受控实验（2026-08-14）

固定制品为 `ik_llama.cpp` commit `981e5ea0d7579b4803c86afbb09a7cd7d7bf3bb8` 与 `sokann/DeepSeek-V4-Flash-GGUF` revision `8315f07e97f3e8b15b551da6a82ba944b2e55be9`。GGUF SHA-256 已验证为 `fd4108898e566869e333f11f8e9b40ab773d3431c5a94685aeff5794e2c5572f`。候选仅发布在 loopback `:8081`；主服务没有被接入或替换。

| 配置 | 1K decode median | 8K decode median | 结果 |
|---|---:|---:|---|
| CPU-MoE，16 threads，F16 K/V | 6.57 tok/s | 7.00 tok/s | 未达 8 tok/s 门槛 |
| CPU-MoE，32 threads，F16 K/V | 8.82 tok/s | 8.96 tok/s | 两项通过 |

8K 冷预填充由约 45.9 tok/s（16 threads）提高到约 73 tok/s（32 threads）。各三次运行的热缓存 TTFT 为约 0.55--0.86 秒；因此该值不代表首次长上下文请求的体验，首次 8K 预填充仍需约数分钟量级。

## 当前事实

| 项目 | 证据 | 影响 |
|---|---|---|
| 现役路径 | KTransformers/SGLang-KT、TP2、两张 3090、CPU-MoE | 必须保持运行，候选不得占用其端口、Compose project 或模型路径。 |
| GPU 拓扑 | GPU0↔GPU1 为 PHB，P2P 为 `NS` | 双卡不是共享 48GB；通信与 NUMA 成为性能和正确性风险。 |
| 实际磁盘 | 2026-08-14：Terraform `disk0` 从 600GB 原地扩至 900GB；guest ext4 已在线扩展，可用 468 GiB | 存储门通过；不需要删除现役 checkpoint。 |
| 候选尺寸 | `sokann` 近无损 GGUF 约 146 GiB；`teamblobfish` Q4_K_M-XL 约 163--175 GiB | 现在有足够的下载、工作和回滚余量。 |

## 上游状态

`ik_llama.cpp` 的 DeepSeek V4 PR #2165 已合入主分支。维护者的混合 CPU/GPU 命令使用 `--cpu-moe`、2×3090 和 64 线程；在 Threadripper Pro 3995WX 上约为 16--18 tok/s。该数字只说明软件路线可行，不是当前主机的预测值。

上游 llama.cpp 的 DeepSeek V4 `q8_0` K cache 已出现“服务健康但输出乱码”的图级正确性问题；在修复发布并经本候选固定 commit 验证前，实验必须指定 `--cache-type-k f16`。V 可单独评估，但首轮同时固定为 F16 更易诊断。

可公开获取的 V4-aware CUDA fork 同时明确：Ampere 走软件模拟 FP8、尚未 runtime 验证；多 GPU layer split 标为 WIP，验证主要在 Ada/A100。因此不采用它作为生产候选或默认下载源。

## 受控实验前提

只有同时满足下列条件才可进入下载/启动门：

1. 完成下载后仍保留至少 100 GiB 空闲空间；2026-08-14 的 900GB 根盘扩容已满足这一门槛，且没有删除现役 checkpoint。
2. 固定 `ik_llama.cpp` 的 commit、CUDA build 选项、GGUF repository revision、各 shard SHA-256、chat/reasoning/tool parser 与完整启动参数。
3. 新建独立目录、Compose project、systemd unit、端口和只读模型挂载；Open WebUI 不改连接，候选只在 loopback 测试。
4. 首轮明确 CPU-MoE、F16 K/V cache、16K context、并发 1、无 MTP；不得复用 KTransformers 的 CUDA graph 或 GPU-expert 参数。
5. 使用固定 corpus 先完成同步、SSE、reasoning、tool calls、畸形请求和 1K/8K 正确性；随后才跑重复性能测试与 soak。

## Go/No-Go 与预期

当前状态为 **性能 Go、生产接入 No-Go**。保留 32 threads 的独立候选可继续做长时稳定性与 parser 修复验证；不得修改 Open WebUI 连接或停止/替换现役 KTransformers 服务，直到同步 API 的 reasoning/content 分离与长时间非 P2P 正确性均被证明。

合理预期是：该路线可能利用 ik_llama.cpp 的 CPU-MoE 优化改善吞吐，但旧双路 E5 的内存带宽、非 P2P 双卡和 ESXi NUMA 都会显著压低相对 3995WX 的结果。任何“16--18 tok/s”都只可作为外部上限案例，不能作为验收承诺。

## Sources

- [ik_llama.cpp DeepSeek V4 PR #2165](https://github.com/ikawrakow/ik_llama.cpp/pull/2165)
- [ik_llama.cpp repository](https://github.com/ikawrakow/ik_llama.cpp)
- [DeepSeek V4 quantized-K cache correctness issue](https://github.com/ggml-org/llama.cpp/issues/25382)
- [Non-P2P dual-3090 layer-split correctness issue](https://github.com/ggml-org/llama.cpp/issues/20052)
- [sokann lossless-style DeepSeek V4 Flash GGUF](https://huggingface.co/sokann/DeepSeek-V4-Flash-GGUF)
- [teamblobfish Q4_K_M-XL GGUF and Ampere status](https://huggingface.co/teamblobfish/DeepSeek-V4-Flash-GGUF)
