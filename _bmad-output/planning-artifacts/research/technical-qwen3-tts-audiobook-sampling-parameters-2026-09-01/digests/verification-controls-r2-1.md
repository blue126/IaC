# Qwen3-TTS / vLLM-Omni 控制面核验（R2.1）

核验日期：2026-09-02。方法：重新取回摘要所列固定提交、测试、PR 与 issue；未把项目上下文或训练记忆作为证据，也未做音频听测。状态词仅取 `verified / disputed / unverified / overturned`。

| 主张 | 状态 | 核验结论 |
|---|---|---|
| A | **verified** | Qwen 发布矩阵只给 1.7B CustomVoice 标注 instruction control；固定源码又明确将 0.6B 的 `instruct` 置空。vLLM-Omni v0.28.0 的 Speech schema 接受 `instructions`，构造请求时写为 `tts_params["instruct"]`。 |
| B | **verified** | 固定源码先追加 `instruct_ids`，再把 `speaker` ID 映射为固定 embedding，证明风格指令与 preset 身份是分开的条件。官方描述中 Serena 为 warm/gentle、Uncle_Fu 为 low/mellow、Dylan 为 clear/natural；Vivian 为 bright/edgy、Eric 为 lively/bright，故前三者是更合理的“克制旁白候选”先验。该排序不是效果验证。 |
| C | **verified** | 请求 `seed` 同时写入 Stage-0 `SamplingParams.seed`（Talker）和 `extra_args["tts_local_seed"]`（残差 MTP）。FULL CUDA Graph 分支禁用逐行 generator，并由已合并 PR 明示逐请求 seed 不可复现；eager 保留逐行 generator。纯 `PIECEWISE` 因 `has_full_cudagraphs()` 为假而避开该分支，但没有 CUDA 端到端回归，仍只能算代码路径推论。 |
| D | **verified** | Speech `extra_params.temperature/top_p/top_k` 只改 `sampling_params_list[0]`，即 Stage-0 Talker；MTP 调用实际从部署级 `model_config.subtalker_sampling_params` 读取四项采样值。把同名值放进 `extra_args` 不会使当前 MTP 路径读取它们。 |

## 证据、独立性与限定

### A

- Qwen 自身的[能力矩阵](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#L73-L79)与[官方 wrapper](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L730-L801)互相校验；后者消除了 README 其他位置把 `instruct` 泛写为可选参数所造成的歧义。
- 由另一组织维护的 vLLM-Omni [Speech 协议](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/entrypoints/openai/protocol/audio.py#L57-L178)及[参数构造代码](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/entrypoints/openai/serving_speech.py#L2469-L2586)独立确认适配器映射；这是跨项目的实现级交叉检查，但不是黑盒语音效果测试。

### B

- [Qwen 模型源码](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/core/models/modeling_qwen3_tts.py#L2075-L2105)直接显示 instruction embedding 与 speaker embedding 的分路；[官方 preset 表](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#L187-L199)支持上述语义排序。
- 独立用户的[现场问题](https://github.com/QwenLM/Qwen3-TTS/issues/16)及维护者[回复](https://github.com/QwenLM/Qwen3-TTS/issues/16#issuecomment-3797746019)另行表明 speaker 本身可带有 expressive/non-broadcast 倾向、换 speaker 是有效实验维度；但它没有比较 Serena/Uncle_Fu/Dylan。因此“候选更合理”已验证，“一定更克制或更稳定”仍未验证，不能由本项推出。

### C

- [请求接线](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/entrypoints/openai/serving_speech.py#L2997-L3138)、[标签测试](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/tests/entrypoints/openai_api/test_serving_speech.py#L4646-L4665)、[Talker 分支](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L315-L351)和[runner 的逐请求 generator](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/worker/gpu_model_runner.py#L1848-L1963)共同支持传播与执行语义。[已合并 PR #4923](https://github.com/vllm-project/vllm-omni/pull/4923)明确列出 FULL 与 eager 的行为差异。
- 外部报告者在 [issue #6361](https://github.com/vllm-project/vllm-omni/issues/6361) 用固定 seed + eager 复现了 sequential/co-batch 差异，独立支持“eager 不等于端到端确定性”的限定；它测试的是 0.27.0rc1/后续分支，不直接验证 v0.28.0 FULL 的根因。
- vLLM 的[`CUDAGraphMode`](https://github.com/vllm-project/vllm/blob/2cf0a6915ce544dc493a0990f2ea38d81601128a/vllm/config/compilation.py#L53-L87)证明纯 PIECEWISE 不满足 full 条件；但摘要已正确标注缺少 CUDA E2E。故不得把“避开此分支”写成“已经证明可复现”。

### D

- [Speech 服务实现](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/entrypoints/openai/serving_speech.py#L2997-L3138)只直接改第一个 stage 的 `SamplingParams`；[runner](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/worker/gpu_model_runner.py#L1848-L1963)与[Talker/MTP](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L1271-L1297)则从部署配置取 Subtalker 参数；[随附配置](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/deploy/qwen3_tts.yaml#L61-L138)提供该全局字典。
- PR #4923 另称全局 `subtalker_sampling_params` 会烘焙进 FULL 图，作为实现作者的交叉说明；它与代码同属 vLLM-Omni，组织独立性有限。未找到该版本的外部黑盒验证，但版本固定的代码路径不存在歧义。

## 总体边界

四项主张均按其谨慎措辞成立；没有主张被 disputed 或 overturned。这里验证的是能力与接线路径，不验证某个 preset、instruction 或采样组合能消除长篇音色/韵律漂移，也不提供跨并发形状的 bit-exact 保证。
