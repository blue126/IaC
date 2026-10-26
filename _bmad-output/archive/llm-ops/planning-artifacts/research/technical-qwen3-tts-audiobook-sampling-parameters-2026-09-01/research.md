---
title: 'Technical research: Qwen3-TTS audiobook timbre drift and restrained narration'
type: 'technical'
topic: 'Qwen3-TTS audiobook timbre drift, restrained prosody, sampling parameters and Web UI'
decision: 'Choose the next locally deployable controls that reduce perceived timbre drift and overly dramatic audiobook narration without making generation unusably slow'
source: 'native web research'
status: complete
preset: 'standard'
validation: 'normal'
verified_claims: 13
unverified_claims: 7
created: '2026-09-01'
updated: '2026-09-02'
---

# Qwen3-TTS 有声书音色漂移与克制旁白

**本研究服务的决策：** 选择下一项本地可部署的控制，在不显著牺牲生成速度的前提下，减少主观音色漂移和过度戏剧化的有声书韵律。

## 执行摘要

建议按 `preset → instruction → 请求块长 → 架构` 的顺序测试，而不是继续降低 `temperature/top_k`。Preset `speaker` 提供身份条件，`instruct` 独立控制风格、情绪和韵律；1.7B CustomVoice 支持 instruction，0.6B 官方路径忽略它。[1][2][9][12] 因此，最低成本的下一步是先比较 Serena、Uncle_Fu、Dylan，再让所有请求复用一条明确克制且包含否定项的 instruction。控制能力已有官方依据，实际听感排序仍须用户 A/B 确认。[1][10]

固定 seed 不能解决当前问题。vLLM-Omni v0.28.0 的默认 FULL CUDA Graph 不能保证逐请求 `tts_local_seed` 复现；切换 eager 可能明显降低生成速度，也不保证跨运行环境逐字节一致。[11][12][13][14][17] Seed 适合诊断，不会延续上一句的身份或语势。

当前 CustomVoice/OpenAI Speech API 也没有跨请求的声学、KV、codec 或韵律 continuation。[2][9][12][13] 将 2–4 句或一个自然段放入同一请求值得 A/B，因为它减少请求边界；但这仍是未在 Qwen 上证实的迁移假设。[15][16] 若 preset、instruction 和块长均不能将听感降到可接受范围，再评估 VoiceDesign → Base reusable clone prompt；这是模型和工作流升级，不是 CustomVoice 的一个参数。[1][2]

## 下一轮实验阶梯

测试以用户实际听感和等待体验为准。每轮使用同一类正文、同一播放设备，并且只改变一个变量。

1. **Voice A/B：** 保持当前 Talker/Subtalker `0.6/50`、文本和其他字段不变，只比较 Serena、Uncle_Fu、Dylan。Vivian 的官方描述是 bright/slightly edgy，Eric 是 lively/bright；应选择“连续听十分钟不疲劳”的 voice，而不是单句最惊艳者。[1][10] 控制面的依据置信度高，但具体听感排序尚未验证。
2. **Instruction A/B：** 在胜出的 voice 上，比较空 instruction 与固定克制 instruction。首轮长版可用：`平静、克制、自然地朗读，像成熟的有声书旁白。保持稳定音色、音高和语速，语调起伏小，句间停顿自然。不要角色表演，不要笑、哭腔、耳语、夸张重音或额外声音。` 若长版反而让声音显得做作，再测试短版：`沉稳、自然、均匀的有声书旁白。` Qwen 维护者确认明确否定项可抑制笑声等副作用；这两条中文文案本身仍是待听测条件。[10][12]
3. **重复稳定性：** 对胜出的 voice/instruction 连续生成同一段三次，记录身份跳变、夸张情绪、正文外声音和固定位置伪影。固定 seed 可作为诊断变量，但“输出完全相同”不等于“质量更好”，FULL graph 下也不能期待严格复现。[11][13][14]
4. **块长 A/B：** 仅当客户端能控制请求边界时，比较逐句与 2–4 句/自然段。判断标准是实际等待、超时率和连续听感，不做复杂机器基准。这一步可能减少句首重置和拼接点，也会扩大首包等待、超时和失败后的重生成范围。[15][16]
5. **架构决策：** 如果前四步仍不可接受，停止盲扫 top-k，比较回退 0.6B 与 VoiceDesign → Base clone。Clone 以固定声学参考强化身份，但实现成本更高，且不能沿用当前 CustomVoice instruction。[1][2]

本轮把 `0.6/50` 视为控制变量，不是最佳值。不要为了 seed 切 eager；若严格复现以后成为独立目标，先单独验证 PIECEWISE，再评估 eager 的实际实时因子（RTF）。[13][14] 后处理也放在最后：crossfade 可隐藏接缝，loudnorm 可统一响度，但二者都不能重建音色身份或改写句内韵律。[18]

### 试听工具

Qwen 官方提供在线 demo 和本地 `qwen-tts-demo` Gradio 服务；vLLM-Omni v0.28.0 也提供标准及 FastRTC Gradio demo。[1][3] 这些 UI 需要单独启动，生产 Speech endpoint 的根路径不会自动成为试听页面。

## 决策原理：身份、韵律与确定性是不同控制轴

Qwen3-TTS 先将 `instruct` 形成的风格条件加入 prompt，再将 preset speaker ID 映射为固定 speaker embedding；二者是独立路径。[2][9] 因而用户听到的“像换了音色”可能同时包含真正的 speaker identity 偏移，以及音高、节奏、气声、笑声、耳语或情绪强度变化造成的**主观音色偏移**。vLLM issue #6361 的固定 seed 对比中，音频时长和声学表现发生变化，而 speaker similarity 仍高；这支持至少部分问题属于韵律变化，而非身份翻转。[14]

这也解释了为何继续降低随机性可能没有明显改善：sampling 只影响选择分布，不会把上一请求的语势带入下一请求，也不会改变 preset 的风格先验。Qwen 维护者指出，强情绪 instruction 可能诱发笑声，某些 voice 天生 expressive/non-broadcast；缓解方向是加入明确否定项或更换 speaker。[10]

- **1.7B 的能力也是变量。** 它支持 instruction，并更强调语义驱动的 tone、rhythm 和 emotion；0.6B 不支持 instruction。公开证据不能证明 1.7B 更容易漂移，但 1.7B 提供了把表演收回来的正式控制面。[1][2]
- **严格确定性与实时性能是不同目标。** Eager 有利于逐请求 RNG 控制，但 FULL graph 将 `talker_mtp` 的上游组件耗时从约 39 ms/step 降至 9 ms/step；没有证据支持为减少主观漂移而放弃这部分性能。[13][14]
- **无状态 endpoint 不能保证彻底消除跨句漂移。** 可先减少输入和风格差异；需要更强身份锚定时，应升级到 clone/reference 架构，而不是期待某个 temperature 值承担状态连续性。[1][2][12]

## 当前 vLLM-Omni v0.28.0 的控制边界

| 控制 | 当前支持 | 对本问题的作用与限制 |
| --- | --- | --- |
| `voice` / `speaker` | 支持 | 固定身份条件；preset 自带不同风格先验，优先用于降低戏剧化。[1][9][12] |
| `instructions` | 1.7B CustomVoice 支持；0.6B 忽略 | 映射为 Qwen `instruct`，直接控制风格、情绪和韵律；不是第二个身份锚点。[1][2][12] |
| 显式 `language="Chinese"` | 支持 | 避免 Auto/方言条件变化；Dylan/Eric 分别带北京/成都方言路径。[1][9] |
| Talker `temperature/top_p/top_k` | 请求级 `extra_params` 可覆盖 | 控制主 codec 序列随机性；没有“有声书最佳值”或锁音色证据。[2][12] |
| Subtalker sampling | 仅 deploy 级 | 必须单独改 `subtalker_sampling_params`；请求级同名 extra 参数不会覆盖它。[12][13] |
| `seed` | 接口支持 | FULL CUDA Graph 下 residual MTP 不按逐请求 seed 严格复现；只适合作为诊断变量。[12][13] |
| speaker cache | 支持 | 复用 speaker/reference artifact，不保存上一句 codec/KV/prosody state。[12][13] |
| previous audio / continuation handle | 不支持 | 无法让独立 Speech 请求真正继承上一句语势。[2][9][12] |
| `voice_clone_prompt` | 仅 Base | 可强化可复用声学身份；不是 CustomVoice 参数，也没有当前 Base instruction control。[1][2] |

## 采样参数证据

Qwen 官方 wrapper 的硬默认值为 `do_sample=true`、`temperature=0.9`、`top_k=50`、`top_p=1.0`、`repetition_penalty=1.05`；Talker 与 Subtalker 使用相同的温度和 top-k，文档建议大多数场景保留 sampling。[2]

vLLM-Omni v0.28.0 的 Qwen3-TTS deploy config 独立重复了 Talker 与 Subtalker 的 `0.9/50`。[4] 但官方材料没有给出有声书专用值。

低采样范围也不能保证音色稳定。一个中文多角色/旁白案例在 `temperature=0.1`、`top_k=10`、`top_p=0.5` 下仍报告预设音色随段落明显变化；这是未控制的单用户试听，置信度低。[5] 另一个 1.7B 微调 Base 实验把 talker 设为 `temperature=0/top_k=1`，并把 subtalker 强制 greedy，短独立语句开头仍有约 1–2 秒音色错误。该模型类型不同于当前 CustomVoice，证据不能直接外推，但足以否定“参数足够低就一定稳定”。[6]

一个有声书项目把 `temperature=0.9`、`top_p=1.0` 调为 `temperature=0.6`、`top_p=0.85`，并保留 `top_k=50`。作者明确写明只验证了参数链路，没有完成端到端试听，因此这组数值不能视为最佳实践。[7]

## 长文本与请求边界证据

短语/长句对比实验发现：即使使用 greedy，同一个短语独立生成时可能起声不稳，放入更长句子后却正常。这说明扩大文本上下文值得测试，但该实验来自微调 Base 模型，置信度中等。[6]

另一个旁白工程认为，分别合成约 3 秒的场景会反复造成句首音高重置和句末下降轮廓，因此提出先把连续句子作为 multi-sentence span 合成，再将生成结果切分为小段。但作者明确承认，这一因果解释只是推断，尚未经过测量，并把盲听对比列为实施前验证。因此，此来源只能支持“值得测试”，不能证明该方案有效。[8]

固定 seed 与跨请求随机性的关系更直接。一个有声书项目将“每次调用都从 OS 熵重新初始化随机数”的方式改为“为整本书固定并持久化一个 seed”，但同样没有完成端到端试听。[7] `temperature` 和 `top_k` 本身不会把上一段叙事状态带入新的 HTTP 请求。

TACA 在专门训练的 context encoder 中利用跨句上下文改善原模型的连贯韵律；FireRedTTS-2 通过 text–speech interleaved sequence 在一次 dialogue 调用中保留多句状态。[15][16] 这些来源验证“上下文有用”的一般机制，但不验证把 Qwen 的几个句子简单拼在一起就能获得同样收益。

因此，2–4 句/自然段 A/B 是值得测试的迁移假设，不是结论。收益可能是减少每句重新起声与拼接点；代价是非流式响应的首包等待、客户端超时、失败后重生成范围和长段落语速漂移风险。CustomVoice 应继续保持默认 `non_streaming_mode=True`；Base 模拟流式路径的语速漂移数据不能外推为 CustomVoice 的效果量。[2]

## 决策门槛

- **保留 preset：** 只有在当前书籍和播放设备上连续听读仍克制、耐听，才将某个 voice 定为胜者；官方描述不能替代试听。
- **保留 instruction：** 只有固定文案相对空 instruction 稳定改善听感，才注入所有请求；长版与短版需分别做单变量对比。
- **进入块长测试：** Speech Central 必须允许控制每次送入 TTS 的文本跨度。若边界不可控，服务端无法在不延迟当前响应的情况下等待未来句子并自动合并。
- **研究 PIECEWISE：** 仅当严格 seed 复现成为独立目标时，再测当前 RTX 3090/v0.28.0 上的可重复性与实际 RTF；现有上游资料没有 CUDA E2E 数据。
- **升级 clone：** 只有 preset、instruction 和可行的块长测试仍不能接受时，才验证 VoiceDesign→Base clone；官方没有它与 CustomVoice 的头对头漂移指标。

## 来源附录

| Ref | Claim/finding | Publisher | Pub date | Accessed | Confidence |
| --- | --- | --- | --- | --- | --- |
| [1] | 官方本地/在线 Web UI | [QwenLM — Qwen3-TTS README](https://github.com/QwenLM/Qwen3-TTS/blob/main/README.md) | 2026-01-25 | 2026-09-01 | high |
| [2] | 官方生成默认值及 sampling 建议 | [QwenLM — qwen3_tts_model.py](https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/inference/qwen3_tts_model.py) | 2026-01-23 | 2026-09-01 | high |
| [3] | vLLM-Omni Qwen3-TTS Gradio demo 形态 | [vLLM Project — TTS serving guide v0.28.0](https://github.com/vllm-project/vllm-omni/blob/v0.28.0/docs/user_guide/examples/online_serving/text_to_speech.md) | 2026-08-19 | 2026-09-01 | high |
| [4] | vLLM-Omni Talker/Subtalker 默认值 | [vLLM Project — qwen3_tts.yaml v0.28.0](https://github.com/vllm-project/vllm-omni/blob/v0.28.0/vllm_omni/deploy/qwen3_tts.yaml) | 2026-08-28 | 2026-09-01 | high |
| [5] | `0.1/10` 下仍有音色变化的用户报告 | [QwenLM GitHub community — issue #61 comment](https://github.com/QwenLM/Qwen3-TTS/issues/61#issuecomment-3845997240) | 2026-02-04 | 2026-09-01 | low, unverified |
| [6] | Greedy 仍有短语起声不稳定，长句较稳定 | [QwenLM GitHub community — issue #343](https://github.com/QwenLM/Qwen3-TTS/issues/343) | 2026-07-10 | 2026-09-01 | medium, unverified |
| [7] | 有声书项目提出 `0.6/top_p=0.85` 与持久 seed，但未听测 | [runandread-audiobook — PR #5](https://github.com/sergenes/runandread-audiobook/pull/5) | 2026-08-15 | 2026-09-01 | low, unverified |
| [8] | 短场景独立合成的韵律重置假说与 multi-sentence span 方案 | [rediacc — issue #526](https://github.com/rediacc/console/issues/526) | 2026-07-19 | 2026-09-01 | low, unverified |
| [9] | `speaker` embedding 与 `instruct` 的独立条件路径、双层采样和请求内构造 | [QwenLM — modeling_qwen3_tts.py pinned commit](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/core/models/modeling_qwen3_tts.py) | 2026-03-17 | 2026-09-02 | high |
| [10] | 强情绪 instruction 会诱发笑声、某些 speaker 天生 expressive，建议否定 instruction 或换声 | [QwenLM — issue #16 maintainer replies](https://github.com/QwenLM/Qwen3-TTS/issues/16) | 2026-01-23 | 2026-09-02 | high for supported mitigation direction; outcome unverified |
| [11] | 相同 CustomVoice 输入仍变化，固定 seed 的社区结果冲突 | [QwenLM — issue #298](https://github.com/QwenLM/Qwen3-TTS/issues/298) | 2026-04-17 | 2026-09-02 | low, unverified |
| [12] | OpenAI `instructions`/`seed` 接线、请求 schema、无 continuation 字段 | [vLLM-Omni v0.28.0 — Speech protocol and serving](https://github.com/vllm-project/vllm-omni/blob/v0.28.0/vllm_omni/entrypoints/openai/serving_speech.py) | 2026-08-31 | 2026-09-02 | high |
| [13] | FULL CUDA Graph 的 seed 限制、Subtalker deploy 控制、MTP 39→9 ms/step | [vLLM-Omni — PR #4923](https://github.com/vllm-project/vllm-omni/pull/4923) | 2026-07-10 | 2026-09-02 | high for implementation; component performance only |
| [14] | 固定 seed 在 sequential/co-batch 间仍不同，修复尚未进入 v0.28.0 upstream | [vLLM-Omni — issue #6361](https://github.com/vllm-project/vllm-omni/issues/6361) | 2026-08-19 | 2026-09-02 | medium |
| [15] | 训练得到的跨句 context encoder 改善原模型连贯韵律 | [TACA-TTS — INTERSPEECH 2024](https://github.com/dukGuo/TACA-TTS/tree/8d538c85ba877580109d8f7dcdb6d0d1534df80a) | 2024-09 | 2026-09-01 | medium for original model; Qwen transfer unverified |
| [16] | 真正长上下文由同一 dialogue sequence 与模型级设计维持 | [FireRedTTS-2 official implementation](https://github.com/FireRedTeam/FireRedTTS2/tree/404f3f61d25bb4804859b588a6a734bf8468090c) | 2025-09 | 2026-09-01 | medium for original model; low direct transfer |
| [17] | 固定 RNG 不保证跨版本/平台相同，确定性算法通常更慢 | [PyTorch — Reproducibility](https://github.com/pytorch/pytorch/blob/3226a599c9646f691e0c230334ba271f5266180f/docs/source/notes/randomness.md) | fixed commit | 2026-09-01 | high |
| [18] | `acrossfade` 与 `loudnorm` 的操作能力边界 | [FFmpeg filter documentation](https://github.com/FFmpeg/FFmpeg/blob/9ee7e00bfa9be83d72c572c017030d1b8e5212e4/doc/filters.texi) | fixed commit | 2026-09-01 | high |

### 维护：证据时效

- Qwen 1.7B/0.6B instruction capability：工具按版本兼容性窗口标记为已到期（2026-04-17）；本轮已于 2026-09-02 对当前 upstream `main` 固定提交重新核验，但应在下次 Qwen release 时再次检查。
- 段落请求改善 Qwen 连贯性的迁移假设：已到期（2026-09-01）且仍未验证；需要 Qwen 直接 A/B，而不是继续引用其他模型。
- Web UI/服务兼容性：2026-09-19 复查。
- vLLM-Omni v0.28.0 instructions、seed、Subtalker 接线与默认采样：2026-09-30 复查。
- preset 听感先验：2027-03-17 复查；低采样现场经验：2027-07-10 复查。
- speaker/instruct 分路与 clone 架构：2028-03-17 复查；无跨请求 continuation：2028-08-31 复查。

由 `recon_kit.py staleness` 计算的最早复查日期为 **2026-04-17**；其中两个 stale 项已在正文明确标注重新核验或仍未验证。
