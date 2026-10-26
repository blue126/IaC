# 跨请求音色/韵律连续性核验（R2.1）

核验日：2026-09-02。状态词沿用 `verified / disputed / unverified / overturned`。本轮只以固定提交的一手源码/官方文档及下列独立原模型材料为证据；未把项目上下文或训练记忆当作证据。

## A. CustomVoice 与 vLLM Speech 没有跨请求 continuation

**状态：`verified`（需限定“重建”的含义）。** Qwen `generate_custom_voice` 的显式输入只有本次 `text/speaker/language/instruct/non_streaming_mode` 与 generation kwargs；调用内重新 tokenize，并由本次 speaker/instruction 构造 prefill，没有 previous audio、KV、codec tail、prosody state 或 continuation handle。vLLM-Omni v0.28.0 的 Speech schema 同样没有这些字段，每次创建新的 `speech-<uuid>`，Code2Wav 上下文和 decoder cache 以该 request id 为边界。

独立交叉检查：Qwen 官方 wrapper 与底层 generation flow、vLLM 的协议/服务层与 Stage 1 传递层四处一致。vLLM 可以跨请求复用 speaker embedding/ref-code 等**条件素材**，但不会复用上一段的生成/KV/韵律状态；因此“重建条件”应理解为每请求重新组装 prompt，而不是所有条件素材都重新计算。

不接受的外推：固定 speaker、clone prompt、seed 或命中 speaker cache，不等于跨请求声学连续性。

来源：[Qwen CustomVoice API](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L730-L839)、[Qwen generation flow](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/core/models/modeling_qwen3_tts.py#L2075-L2292)、[vLLM Speech schema](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/entrypoints/openai/protocol/audio.py#L57-L178)、[vLLM request construction](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/entrypoints/openai/serving_speech.py#L2469-L2586)、[request-local Code2Wav state](https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/model_executor/stage_input_processors/qwen3_tts.py#L78-L367)。

## B. 一次发送 2–4 句/一个自然段

**状态：`unverified`。** 这是合理的 Qwen 迁移实验假设，不是已证实修复。Qwen 官方长语音结果只报告内容 WER，没有逐句请求与段落请求的 speaker similarity、音色漂移或韵律连续性对照，也没有证明“2–4 句”这个具体范围。

独立交叉检查：TACA 在其原模型中用**训练出的 context encoder**融合跨句信息并报告更连贯的韵律；FireRedTTS-2 用双 Transformer 和 text–speech interleaved sequence，在同一次 dialogue 调用中保留多句上下文。两者支持“跨句上下文可能有用”的一般机制，却都不是简单把句子拼入 Qwen CustomVoice。

不接受的外推：不能把 TACA/FireRedTTS-2 的收益、块长或效果量转移给 Qwen；只能把“逐句 vs 2–4 句/自然段”作为固定其他变量的 Qwen A/B。

来源：[Qwen long-speech WER](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#L1026-L1168)、[TACA 官方摘要/实现](https://github.com/dukGuo/TACA-TTS/tree/8d538c85ba877580109d8f7dcdb6d0d1534df80a)、[FireRedTTS-2 官方实现](https://github.com/FireRedTeam/FireRedTTS2/tree/404f3f61d25bb4804859b588a6a734bf8468090c)。

## C. VoiceDesign→Base reusable clone prompt

**状态：`verified`（工作流与接口边界）；“实测一定比 CustomVoice 更少漂移”为 `unverified`。** Qwen README 官方给出 VoiceDesign 生成参考音频、Base `create_voice_clone_prompt` 建立可复用 prompt、再跨多行调用 `generate_voice_clone` 的流程，并明确称适用于 many lines 的 consistent character voice。源码同时强制 `generate_voice_clone` 只用于 Base；CustomVoice 签名不接收 `voice_clone_prompt`。发布能力矩阵未给当前 12Hz Base 标注 instruction control，Base clone API 也没有 `instruct`。

独立交叉检查：README 的能力矩阵/工作流与两个互斥的官方 API 类型检查及函数签名一致。

不接受的外推：该流程不是 CustomVoice 的隐藏参数或无缝配置项；也没有官方头对头指标证明它必然优于 CustomVoice。采用它意味着换到 Base，并失去当前 Base 的文字 instruction control。

来源：[Qwen model matrix and VoiceDesign→Base workflow](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#L73-L79)、[workflow details](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#L241-L290)、[Base clone API](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L455-L629)、[CustomVoice API](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L730-L839)。

## D. crossfade/loudnorm 不能修复已生成的 identity/prosody drift

**状态：`verified`（按操作能力边界）。** FFmpeg `acrossfade` 只在相邻流边界的指定时长内重叠淡入淡出；`loudnorm` 只以 EBU R128 的 integrated loudness、loudness range 和 maximum true peak 为目标做线性或动态响度规范化。它们没有说话人表征、文本、F0/时长目标或生成状态，无法重建已经错误的身份、句内重音、语速或语调轨迹。

独立交叉检查：同一固定提交中两个滤镜的输入域与可调目标彼此独立地限定为“边界幅度混合”和“响度统计”；由操作定义即可排除身份/韵律再生成能力。

不接受的外推：crossfade 可以掩盖接缝，loudnorm 可以缩小响度差；这不等于修复音色漂移或恢复正确韵律。动态 loudnorm 可能改变能量包络，更不能据此宣称恢复了目标表演。

来源：[FFmpeg `acrossfade` and `loudnorm` filter definitions](https://github.com/FFmpeg/FFmpeg/blob/9ee7e00bfa9be83d72c572c017030d1b8e5212e4/doc/filters.texi)。
