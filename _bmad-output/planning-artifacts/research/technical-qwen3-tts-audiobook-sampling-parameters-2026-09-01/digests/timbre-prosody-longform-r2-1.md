# 长篇有声书中的音色与韵律稳定性：Qwen3-TTS CustomVoice 证据摘要

- 研究问题：哪些长篇 TTS 技术能减少句块间的说话人/音色漂移，并让旁白保持克制；其中哪些能映射到 OpenAI 兼容的无状态 speech API 后端。
- 检索截止/访问日：2026-09-01。
- 证据口径：只把本轮检索到的论文、官方实现和可复现运维报告作为证据。跨模型迁移、具体 instruction 文案和 Qwen3-TTS 上尚未测过的参数方向均明确标为假设。
- 置信度：高＝Qwen 官方实现或操作定义直接支持；中＝论文/官方实现支持原模型，但迁移需实验；低＝用户报告、未合并 PR 或未经 Qwen 验证的推断。

## 结论先行

1. **最能映射到无状态 CustomVoice 的低成本方案**是：每次请求合成一个自然段（而非逐句请求），固定 `speaker`、显式 `language`、完全相同的 `instruct`，并保持 `non_streaming_mode=True`。Qwen 官方接口直接支持这些输入；但“自然段一定比逐句更少音色漂移”尚无 Qwen 对照实验，只是由跨句上下文论文支持的优先假设。[S1][S3]
2. **CustomVoice 没有跨请求的声学 prompt、上一句音频或 KV/prosody state 参数**。因此，真正的跨句声学状态续接不能由标准无状态请求实现；可行替代是把数句放在同一次请求中。Qwen 的可复用 `voice_clone_prompt` 属于 **Base/VoiceClone**，不是 CustomVoice。[S1]
3. **可重复采样需要同时管住主 talker 和 subtalker**。官方包装器的硬回退默认值为两路均采样、`top_k=50`、`top_p=1.0`、`temperature=0.9`，主路另有 `repetition_penalty=1.05`；checkpoint 配置可覆盖这些值。只固定一处 seed 或只调主路温度不足以证明确定性。[S1][S2][S6]
4. **“克制旁白”可以用 1.7B CustomVoice 的 instruction 做，但具体文案效果未被论文验证**；0.6B CustomVoice 在官方代码中会禁用 instruction。声音选择应先遵循母语：英文可先试描述为“clear midrange”的 Aiden，再与“strong rhythmic drive”的 Ryan 对照；中文可先试 low/mellow 的 Uncle_Fu 或 warm/gentle 的 Serena。[S1]
5. **后处理只能处理接缝和响度，不能修复已经生成的音色、语速或表演强度**。短交叉淡化可掩盖拼接突变，`loudnorm` 可统一 IL/LRA/true peak；二者都不重写说话人表征或韵律轨迹。[S7]

## 关键证据与迁移边界

### S1. Qwen3-TTS 技术报告与官方实现（2026）

- 元数据：Hu Hangrui 等，*Qwen3-TTS Technical Report*，arXiv:2601.15621；官方仓库 commit `022e286`（2026-03-17）。[论文](https://arxiv.org/abs/2601.15621)；[官方实现](https://github.com/QwenLM/Qwen3-TTS/tree/022e286b98fbec7e1e916cb940cdf532cd9f488e)。
- 精确证据：
  - `generate_custom_voice(text, speaker, language, instruct, non_streaming_mode=True, **kwargs)` 的默认是非流式文本布局；文档明确说设为 `false` 只是模拟流式文本输入，并不启用真正流式输入/生成。
  - 1.7B CustomVoice 支持 instruction；0.6B 官方代码把 `instruct` 置空。硬回退采样参数为 `do_sample=True`、`top_k=50`、`top_p=1.0`、`temperature=0.9`、`repetition_penalty=1.05`，subtalker 另有同样的采样开关、top-k/top-p/temperature；模型的 `generation_config.json` 优先。
  - 官方建议使用每个 speaker 的母语以获得最佳质量。英文 speaker 描述中 Aiden 为清晰中频，Ryan 为强节奏驱动；中文 Uncle_Fu 为低沉醇厚，Serena 为温暖柔和。
  - 官方 long-zh/long-en 仅报告内容 WER：12Hz 1.7B CustomVoice 为 2.356/2.812；该表**没有**音色漂移、韵律连贯或“克制程度”指标。
  - 只有 Base/VoiceClone 接受 `ref_audio`/`ref_text` 或可复用 `voice_clone_prompt`；`x_vector_only_mode` 不需转写但官方警告克隆质量可能下降。官方还给出 VoiceDesign→生成参考音频→Base clone prompt 的复用流程，并称其适合跨多行保持角色声音。
- 对本题适用性：同请求的多句文本、固定 speaker/language/instruct、非流式布局和采样参数是**直接可映射**项；跨请求声学 prompt 不是 CustomVoice 能力。设计后克隆或 SFT 是换模型/后端路径，不是透明的 CustomVoice 参数调整。
- 置信度：接口与默认值高；“段落请求改善漂移”中低；官方长文本质量只能证明内容正确率，不能证明音色/韵律稳定。

### S2. Qwen 官方仓库中的长文本与确定性运维报告（2026）

- 元数据：[issue #239](https://github.com/QwenLM/Qwen3-TTS/issues/239)、[未合并 PR #362](https://github.com/QwenLM/Qwen3-TTS/pull/362)、[issue #298](https://github.com/QwenLM/Qwen3-TTS/issues/298)、[issue #343](https://github.com/QwenLM/Qwen3-TTS/issues/343)。它们不是同行评审结果。
- 精确证据：
  - #239 的 Base/VoiceClone 报告称超过 100 字后语速逐渐加快。后续贡献者固定 seed、文本和采样参数测得：模拟流式 + 12.9 秒参考音频首末三分之一发音率漂移 `+16.7%`；同一参考裁至 4 秒为 `-2.3%`；非流式为 `0.0%`。PR #362 因此提议把 VoiceClone 默认改为非流式，但截至访问日仍未合并。
  - 该 PR 还记录了负面尝试：改变参考/目标文本对齐会导致立即 EOS、655 秒大段静音，或慢速 feed 下的静音/爆发；作者判断当前权重下需要训练侧修复。其建议“流式参考 <5 秒、单次音频约 ≤30 秒”仅是运维经验。
  - #298 报告相同 CustomVoice 输入仍有音色/情感差异；用户反馈固定 seed 可让行为更接近，但若 seed 只作用模型一部分，输出仍非逐字节一致。这不是维护者确认。
  - #343 的单例 LoRA 报告：约 21 分钟单说话人数据微调后，长句稳定，但 greedy 下约 15% 短句/开头 1–2 秒出现错音色、性别翻转或耳语；同一文本错误可确定性复现。
- 对本题适用性：#239 的机制直接针对 **Base 克隆的模拟流式路径**，不能宣称 CustomVoice 也有同一缺陷；它反而确认 CustomVoice 已默认非流式。#298/#343 只足以说明“固定 seed/greedy/微调并非质量保证”，适合作为风险提示。
- 置信度：#239 的测量中（有方法、数值、代码路径，但未同行评审且 PR 未合并）；#298/#343 低。

### S3. TACA：文本与跨句上下文的有声书韵律建模（INTERSPEECH 2024）

- 元数据：Dake Guo、Xinfa Zhu、Liumeng Xue 等，*Text-aware and Context-aware Expressive Audiobook Speech Synthesis*，INTERSPEECH 2024；[作者演示与摘要](https://github.com/dukGuo/TACA-TTS/tree/8d538c85ba877580109d8f7dcdb6d0d1534df80a)。
- 精确证据：TACA 用语音风格监督的对比学习建立 text-aware style space，再用 context encoder 融合跨句信息与文本风格 embedding；同一机制分别接入 VITS 型和语言模型型 TTS。作者报告它改善连贯韵律、自然度和表现力。
- 对本题适用性：它支持“上一/下一句语义是韵律信息”的一般结论，但改进来自**训练好的 context encoder**，并不证明把相邻句简单拼进 Qwen 文本就能复现。且目标是“expressive audiobook”，可能与“克制旁白”相冲突；应把更大文本块当 A/B 假设，而不是结论。
- 置信度：原模型结论中高；迁移到 Qwen CustomVoice 低至中。

### S4. FireRedTTS-2：真正的跨句长上下文需要模型级设计（2025）

- 元数据：*FireRedTTS-2: Towards Long Conversational Speech Generation for Podcast and Chatbot*，arXiv:2509.02020；[官方代码 commit `404f3f6`](https://github.com/FireRedTeam/FireRedTTS2/tree/404f3f61d25bb4804859b588a6a734bf8468090c)。
- 精确证据：系统用 12.5 Hz tokenizer、双 Transformer 与 text–speech interleaved sequence，在**一次 dialogue 调用**中接收句子列表和每位说话人的 prompt wav/text；官方称支持 3 分钟、4 说话人，并以 sentence-by-sentence 生成在 L20 上做到约 140 ms 首包。官方实现示例把多句连续传入同一个 `generate_dialogue`。
- 对本题适用性：它说明“跨句韵律续接 + 低延迟”不是简单拼 WAV，而是模型/序列设计。无状态 Qwen CustomVoice 无法复制其跨句声学 state；能借鉴的仅是尽量在**一次请求**保留多个句子的文本上下文。它是需要换模型的备选，不是 Qwen 参数。
- 置信度：原系统能力中高；迁移到 Qwen 的直接性低。

### S5. VibeVoice：长上下文收益及 prompt/style leakage 的负面证据（ICLR 2026 Oral）

- 元数据：*VibeVoice: A Frontier Open-Source Text-to-Speech Model*，ICLR 2026 Oral；[Microsoft 官方仓库](https://github.com/microsoft/VibeVoice/tree/94da20d98b2fa7688e9cbfaf7692ddb4954f7600)；[TTS 文档](https://github.com/microsoft/VibeVoice/blob/94da20d98b2fa7688e9cbfaf7692ddb4954f7600/docs/vibevoice-tts.md)。
- 精确证据：模型以 7.5 Hz 连续 acoustic/semantic tokenizer、Qwen2.5 LLM 与 next-token diffusion 支持 64K context、官方声称单次约 90 分钟/4 说话人。官方故障提示同时给出负面证据：中文建议只用英文逗号和句号；语速过快时把文本拆成同 speaker 的多个 turn；参考音频含 BGM 会提高生成 BGM 概率，即使参考干净，`Welcome to`、`Hello`、`However` 等文本也可能触发 BGM；模型训练/推理不做 text normalization；跨语言迁移不稳定，可能靠重复采样才得到满意结果。
- 对本题适用性：长上下文和样式泄漏结论只对 VibeVoice 有直接证据。它说明参考音频会携带非说话人风格、标点/词语可触发表演模式，但不能据此声称 Qwen 必然如此。作为替代模型，它偏播客/对话和表现力，未必适合克制旁白；且原 1.5B TTS 代码因滥用已禁用，复现性受限。
- 置信度：VibeVoice 内部中高；向 Qwen 迁移低。

### S6. PyTorch 可重复性说明

- 元数据：[PyTorch 官方 Reproducibility 文档，commit `3226a59`](https://github.com/pytorch/pytorch/blob/3226a599c9646f691e0c230334ba271f5266180f/docs/source/notes/randomness.md)。
- 精确证据：`torch.manual_seed()` 可控制 CPU/CUDA RNG；同一环境并消除其他非确定源时可复现随机序列，但跨 PyTorch release、commit、平台及 CPU/GPU 不保证完全复现。确定性算法往往更慢。
- 对本题适用性：若 shim 暴露 seed，应固定所有 RNG、模型/库版本和设备，并同时控制 talker/subtalker；“同 seed＝跨机器相同 WAV”不成立。固定 seed 主要用于可靠 A/B 和可重生成，不等于音质更好。
- 置信度：高。

### S7. FFmpeg 后处理能力边界

- 元数据：[FFmpeg 官方 filter 文档，commit `9ee7e00`](https://github.com/FFmpeg/FFmpeg/blob/9ee7e00bfa9be83d72c572c017030d1b8e5212e4/doc/filters.texi)。
- 精确证据：`acrossfade` 只在第一段末尾与下一段开头按给定时长/曲线重叠淡化；`loudnorm` 只针对 EBU R128 的 integrated loudness、loudness range 与 maximum true peak 做动态或线性规范化。
- 对本题适用性：可用很短的 crossfade 隐藏边界幅度突变，并在最终成书时统一响度；按操作定义，它们不能恢复身份 embedding、改写句内重音或消除“戏剧化”表演。过长 crossfade 还会重叠词头/词尾，需试听。
- 置信度：高。

## 对无状态 Qwen CustomVoice 的方案排序

| 排名 | 技术 | 可映射性 | 预期收益与边界 |
|---:|---|---|---|
| 1 | 一次请求合成 2–4 句、以自然段为边界 | 直接 | 保留文本级跨句上下文、减少拼接点；Qwen 上减少漂移仍待验证。块越大，失败后重生范围越大；若 API 缓冲整段，首音频等待也可能增加（系统推断）。 |
| 2 | 固定 `speaker`、显式 `language`、逐请求完全相同的 `instruct` | 直接 | 消除可控输入差异；1.7B 才有 instruction，0.6B 无效。固定 instruction 不保证模型一定服从。 |
| 3 | 保持 CustomVoice 的 `non_streaming_mode=True` | 直接 | 避开已知 Base 模拟流式语速漂移机制；但不能把 Base 的 `0%` 数值当成 CustomVoice 的效果量。 |
| 4 | 固定 seed、checkpoint/运行时和两路采样参数 | 取决于 shim 是否暴露 | 便于重生成与 A/B；跨硬件/版本不保证逐样本一致，也不保证更自然。 |
| 5 | 母语 speaker + 简短克制 instruction | 直接（1.7B） | 机制与 voice 描述有官方依据；具体组合是待听测假设。建议首轮文案：`沉稳克制的有声书旁白，语速均匀，情绪起伏小，句间停顿自然。`；英文用同义英文。 |
| 6 | 文本规范化、保守标点 | 直接 | 先展开数字/缩写，避免成串感叹号、省略号和表演性舞台提示；只有 VibeVoice 有具体标点负证据，Qwen 效果未验证。 |
| 7 | 复用声学参考/设计后克隆 | **CustomVoice 不可直接** | 切到 Base 后可复用同一 `voice_clone_prompt`，理论上固定音色锚；会引入参考风格/环境泄漏风险，且改变服务模型与接口。 |
| 8 | 上下文 encoder、长上下文原生模型或 SFT | 不透明/高成本 | TACA、FireRedTTS-2、VibeVoice 表明模型级上下文有效；需要换权重、换模型或训练。SFT 不是自动修复，短句 onset 仍有反例。 |
| 9 | crossfade + loudnorm | 直接后处理 | 只修接缝与响度，不能修音色/韵律；放在生成参数稳定之后。 |

## Claim ledger

| 可引用句子 | 类别 | 状态 | 依据 |
|---|---|---|---|
| Qwen3-TTS 1.7B CustomVoice 支持 instruction，0.6B 官方路径禁用 instruction。 | 实现事实 | 已验证 | [S1] |
| CustomVoice 官方包装器默认 `non_streaming_mode=True`，且 `false` 只模拟流式文本输入。 | 实现事实 | 已验证 | [S1] |
| Qwen 的主 talker 与 subtalker 默认都含随机采样路径。 | 实现事实 | 已验证 | [S1] |
| Qwen 12Hz 1.7B CustomVoice 的长文本表只证明 WER，不证明音色或韵律稳定。 | 证据边界 | 已验证 | [S1] |
| Base 模拟流式 + 长参考音频出现 `+16.7%` 语速漂移，非流式对照为 `0.0%`。 | 运维测量 | 已验证为单一报告；未独立复现 | [S2] |
| 上述 Base 漂移数值可直接外推到 CustomVoice。 | 跨模型外推 | **未验证，不应采用** | [S1][S2] |
| 跨句上下文 encoder 能改善 TACA 原模型的连贯韵律与自然度。 | 论文结论 | 已验证于原模型 | [S3] |
| 把 Qwen 的逐句请求改为自然段请求一定会减少音色漂移。 | 迁移假设 | **未验证** | [S1][S3] |
| CustomVoice 可跨请求复用上一句的声学 prompt/state。 | 接口能力 | **不支持/未暴露** | [S1] |
| 固定 seed 可用于同环境 A/B，但不保证跨设备、版本逐字节一致。 | 运行时事实 | 已验证 | [S2][S6] |
| `沉稳克制…` 这一 instruction 会可靠减少戏剧化。 | prompt 假设 | **未验证** | [S1] |
| crossfade/loudnorm 能修复已生成的音色漂移。 | 后处理能力 | **错误/不支持** | [S7] |

## Speech Central 用户的低成本听测（从高到低）

1. **句块 A/B（最高优先）**：选同一段 2–4 句、约 45–75 秒的旁白；A 逐句生成后拼接，B 整段一次生成。固定 voice、language、instruction 和所有可见参数。只听五项：音色身份、句末是否加速、段内情绪起伏、句界停顿、错读；各记 1–5 分。
2. **instruction A/B**（仅 1.7B）：同一自然段比较空 instruction 与 `沉稳克制的有声书旁白，语速均匀，情绪起伏小，句间停顿自然。`；不要同时换 voice 或参数。若长文案产生做作感，再试更短的 `沉稳、自然、均匀的旁白。`。这些文案是实验条件，不是已验证配方。
3. **母语 voice A/B**：英文先 Aiden 对 Ryan；中文先 Uncle_Fu 对 Serena。用同一叙述段而非对白段，优先选择“听 10 分钟不疲劳”而非单句最惊艳者。
4. **重复生成稳定性**：用同一段连续生成 3 次；若后端有 seed，先固定 seed，再换一个 seed 生成 3 次。记录是否出现音色跳变、夸张情绪或相同位置的伪影；不要把“完全相同”当成“质量高”。
5. **采样小步扫描**（仅参数确实映射时）：保留 `do_sample=True`，把主/子 `temperature` 同步从 checkpoint 默认值降一小步（例如 0.9→0.7），其他参数不变；比较三次重复的稳定性和沉闷/吞字。不要先上 greedy，官方推荐多数场景采样，且有 deterministic 错音色反例。[S1][S2]
6. **文本规范化 A/B**：同一内容比较原文与“展开数字/缩写、只保留常规逗号句号”的版本；对白引号保留与否单独测试。若效果只在某些文本出现，不推广为全局规则。
7. **块长阶梯**：在胜出的设置上依次测试 1 句、2–4 句、约 30 秒、约 60 秒；选择“开始出现加速/漂移之前”的最长块，而不是预设固定字符数。
8. **最后才做后处理**：只对已经稳定的块测试极短 crossfade 和最终 loudnorm；若词尾/词头重叠或呼吸被切掉，缩短/取消 crossfade。不要用后处理掩盖模型侧漂移。
