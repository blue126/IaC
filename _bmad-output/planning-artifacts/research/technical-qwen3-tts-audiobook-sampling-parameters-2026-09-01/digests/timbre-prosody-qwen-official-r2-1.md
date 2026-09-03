# Qwen3-TTS 1.7B CustomVoice：长篇中文有声书的音色与韵律控制

检索截止：2026-09-01。代码结论固定到 QwenLM/Qwen3-TTS 当时 `main` 的不可变提交 `022e286b98fbec7e1e916cb940cdf532cd9f488e`（`qwen-tts` 0.1.1）；该仓库无 release/tag。本文只把本轮取回的 QwenLM 官方仓库、源码和官方 issue/PR 当作证据。“已验证”表示来源直接支持，不表示本轮做了听感复测。

## 结论

1. **先分清两条控制链。** 在 1.7B CustomVoice 中，`speaker` 是九个预置 speaker ID 之一，底层将其映射为固定 speaker embedding；`instruct` 是另一路文本 prompt，用来调风格/情绪/韵律。前者是身份条件，后者不是新的身份锚点。[S1][S2][S3]
2. **中文旁白的保守基线。** 固定一个中文母语预置音色并显式传 `language="Chinese"`；普通话优先试听 Vivian、Serena、Uncle_Fu，Dylan 是北京口音、Eric 是成都/四川口音。官方建议使用 speaker 的母语；源码还会在 Dylan/Eric 配 `Chinese`/`Auto` 时改用其 dialect language ID。[S1][S3]
3. **抑制“演过头”主要靠 1.7B 的 `instruct` 和选声，不靠另一个身份参数。** 可把同一条克制指令用于所有分段，例如“平静、克制、自然朗读；语调起伏小；不要笑、哭腔、耳语、夸张重音或添加正文外声音”。这是基于维护者“`very happy` 会诱发笑声、可明确写 `without laughing`”的保守工程化扩展；它是待 A/B 验证的提示词，不是官方保证。维护者还明确称 Ryan 天生 expressive、non-broadcast，追求平直旁白时应避开或至少单独验收。[S4]
4. **0.6B 不能替代 1.7B 做文字韵律控制。** 两个 12Hz CustomVoice 都有相同九种预置音色和十种语言，但发布表只给 1.7B 标注 instruction control；当前源码会把 0.6B 的 `instruct` 强制置空。README 另一处却把 `instruct` 写成 1.7B/0.6B 都可选，形成文档矛盾；应以发布矩阵和实际源码为准。[S1][S2]
5. **采样旋钮确实公开，但没有官方证据证明某组值能锁住音色。** Talker 暴露 `do_sample/top_k/top_p/temperature/repetition_penalty`；Subtalker（12Hz tokenizer-v2 适用时）另有 `subtalker_dosample/subtalker_top_k/subtalker_top_p/subtalker_temperature`。文档只明确“temperature 越高越随机”、`repetition_penalty` 用于减少重复；因此关闭两级 sampling 或降低随机性只适合作为可复现实验基线，不能宣称会提高 speaker similarity。官方注释反而建议多数场景 `do_sample=True`。[S2][S3]
6. **不要把源码 fallback 当作 checkpoint 的实际默认值。** wrapper 的硬 fallback 是 Talker/Subtalker 各 `top_k=50, top_p=1.0, temperature=0.9, do_sample=True`，另有 `repetition_penalty=1.05, max_new_tokens=2048`；但 `_merge_generate_kwargs` 先采用模型随附 `generation_config.json`，仅缺项时才用这些值。`max_new_tokens` 只是 codec token 上限，不是音色控制。[S2]
7. **当前官方 `qwen-tts` API 没有显式 `seed`，也没有跨请求连续状态。** `generate_custom_voice` 的显式参数只有 text/speaker/language/instruct/non-streaming 加 generation kwargs；每次调用重新 tokenize，并把 speaker embedding 注入本次 prefill。没有 previous-audio、continuation、voice prompt、speaker-strength 或 request-state 参数；batch 也只是把独立样本 padding 后一起生成。[S2][S3] 因而“固定同一 speaker + 同一 instruct + 同一 sampling tuple + 同一切分规则”是控制变量，而不是连续性保证。
8. **关于固定 seed 的社区说法相互矛盾，且旧投诉没有被修复关闭。** #298 直接报告 1.7B CustomVoice 在同输入下音色/情感每次不同、调 temperature 无效（其后补充为 vLLM）；普通用户建议 vLLM 固定 seed，另有用户仍报告 voice changes，建议者也承认 seed 只作用于模型一部分、不能保证 byte-identical。该 issue 最终由 GitHub Actions 以 `not_planned` 关闭，无修复提交；当前官方 wrapper 仍无 `seed` 参数。[S5]
9. **分段/长文本边界仍是证据缺口。** 官方长语音表只报告 12Hz-1.7B-CustomVoice 的内容 WER（long-zh 2.356），不是跨段 speaker similarity 或韵律漂移；它不能证明长篇音色稳定。[S1] 当前 CustomVoice 默认 `non_streaming_mode=True`，而 `False` 只是模拟流式文本输入，并非真正流式输入/生成。[S2] 一个面向 1.7B-Base 克隆的未合并 PR 测得 simulated-streaming 的长段语速漂移并建议 non-streaming，但它不应外推成 CustomVoice 的已证实缺陷或修复。[S7]
10. **若固定角色身份比保留 CustomVoice instruction 更重要，官方另给跨模型方案。** 先用 VoiceDesign 生成短参考，再用 1.7B Base 建立可复用 `voice_clone_prompt`；README 称它适合 many lines 的 consistent character voice。代价是离开 CustomVoice：当前 12Hz Base 发布表没有 instruction control，VoiceDesign 的描述也不能直接作为 CustomVoice 的 speaker 条件。[S1]

## 受支持与不受支持的控制

| 控制 | 归属 | 1.7B CustomVoice 状态 | 对本问题的谨慎用法 |
|---|---|---|---|
| `speaker` | 身份 | 官方支持，九选一 | 全书固定；中文普通话避开方言 preset，先验收母语中文声线。[S1][S3] |
| `language="Chinese"` | 语言条件 | 官方支持 | 已知语言时不要用 `Auto`；它不是风格或身份旋钮。[S1][S3] |
| `instruct` | 风格/韵律 | 仅 1.7B CustomVoice 支持 | 所有请求复用同一克制、带明确否定项的指令；效果需听测。[S2][S4] |
| Talker sampling | 随机性 | 官方支持 | 固定整组参数；greedy/低随机性只做诊断 A/B，不承诺音色更像。[S2][S3] |
| Subtalker sampling | 其余 codebook 随机性 | tokenizer-v2 时官方支持 | 若测确定性，应与 Talker 同时控制，不能只改主 temperature。[S2][S3] |
| `non_streaming_mode=True` | 文本喂入布局 | CustomVoice 官方默认 | 离线有声书保留默认；不是跨请求上下文。[S2][S7] |
| `repetition_penalty` / `max_new_tokens` | 重复/长度 | 官方支持 | 防重复、封顶输出；不是 timbre/prosody 强度旋钮。[S2] |
| 显式 `seed` | 随机种子 | **官方 wrapper 未暴露** | vLLM 的 seed 属后端能力，issue 经验冲突，不可当官方解法。[S5] |
| 数值 speed/pitch/energy/emotion、CFG、speaker strength | 韵律/身份强度 | **固定源码 API 未暴露** | 只能尝试文字 instruction 或外部后处理；后者不在本证据范围。[S2] |
| ref audio / `voice_clone_prompt` | 克隆身份 | **CustomVoice 不支持；Base 支持** | 需要更强身份锚定时采用官方 VoiceDesign→Base/Clone 替代流程。[S1][S2] |
| previous audio / continuation / 跨请求 KV state | 连续性 | **未暴露** | 不应假设相邻 HTTP 请求会继承音色或语势。[S2][S3] |
| 独立 `...-Instruct` checkpoint | 模型变体 | **当前发布矩阵不存在** | “instruct-capable”是 1.7B CustomVoice/VoiceDesign 的能力，不是第三个可下载变体。[S1] |

## 建议的验证顺序

保持 speaker、`language="Chinese"`、文本切分和同一条克制 `instruct` 不变，先对 20–50 个代表性段落跑默认 sampling；再只改变一项，比较双层 greedy 与默认 sampling。评价应至少包含跨请求 speaker-embedding 相似度、人工盲听身份一致性、F0/语速/能量分布和正文外声音率。由于官方没有给 speaker-consistency benchmark 或推荐低随机参数，本段是实验设计建议，不是已验证模型结论。[S1][S2][S3][S5]

## 一手来源

### [S1] QwenLM — `Qwen3-TTS` README

- URL：[固定提交 README](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md)；文件最近提交 2026-01-25（`1ab0dd7`）；访问 2026-09-01。
- 精确证据：L73–79 的发布矩阵只给 1.7B VoiceDesign/CustomVoice 标 instruction control；L146–150 说明公开调用参数；L167–199 列九种 speaker 与母语建议；L243–290 区分 clone prompt，并称 VoiceDesign→Base workflow 适合 “a consistent character voice across many lines”；L873–928 是 instruction 指标；L1026–1168 的 0.6B/1.7B 与 long-speech 表都是 WER/content consistency，而非 speaker consistency。
- 适用性：直接覆盖 12Hz-1.7B-CustomVoice、0.6B 对照、speaker/语言/模型变体和长文本评测边界。
- 置信度：高；但 README L150 与发布矩阵/源码对 0.6B `instruct` 的说法冲突，已按源码降级解释。

### [S2] QwenLM — `qwen_tts/inference/qwen3_tts_model.py`

- URL：[固定提交源码](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py)；文件最近提交 2026-01-23（`0c6a7cbb`）；访问 2026-09-01。
- 精确证据：L287–352 定义两级 sampling、checkpoint-default 优先级和硬 fallback；L730–778 是 CustomVoice 签名/参数文档；L788–839 校验 `custom_voice`、在 L799–800 将 0.6B `instruct=None`，随后分别传 `instruct_ids` 与 `speakers`；L753–755 明言 `False` 只模拟 streaming text input。
- 适用性：直接适用于官方 Python wrapper 的 1.7B CustomVoice；不代表 vLLM/DashScope 会暴露完全相同参数。
- 置信度：高。

### [S3] QwenLM — `qwen_tts/core/models/modeling_qwen3_tts.py`

- URL：[固定提交源码](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/core/models/modeling_qwen3_tts.py)；文件最近提交 2026-01-23（`ab0f7784`）；访问 2026-09-01。
- 精确证据：L1652–1680 把 `subtalker_*` 传给 code predictor；L2021–2058 分别构造 Talker/Subtalker generation kwargs；L2075–2105 先加入 instruction，再把 preset speaker ID 映射成 embedding；L2110–2122 处理 language/dialect；L2239–2292 展示 batch padding 和一次 `talker.generate`，没有跨调用状态输入。
- 适用性：直接解释 1.7B CustomVoice 的身份/风格分路、双层采样及请求边界。
- 置信度：高。

### [S4] QwenLM 官方 issue #16 — “The generated audio has unwanted laughter…”

- URL：[issue](https://github.com/QwenLM/Qwen3-TTS/issues/16)、[维护者回复 1](https://github.com/QwenLM/Qwen3-TTS/issues/16#issuecomment-3789482711)、[维护者回复 2](https://github.com/QwenLM/Qwen3-TTS/issues/16#issuecomment-3797746019)；创建 2026-01-23，关键回复 2026-01-23/26；访问 2026-09-01。
- 精确证据：Qwen 协作者称高表达力模型会因 `very happy` 加入 laughter，并建议写 `very happy but without laughing`；又称 “Ryan is inherently expressive, non-broadcast in style, and carries rich paralinguistic information in timbre”，并建议换 speaker 或用 Base 克隆目标风格后连续生成。
- 适用性：问题复现命令明确是 12Hz-1.7B-CustomVoice；直接适用于过度戏剧化/正文外声音。
- 置信度：高（行为解释与选声）；中（负面 instruction 只能“may”跟随，不是保证）。

### [S5] QwenLM 官方 issue #298 — 同输入如何得到相同输出

- URL：[issue](https://github.com/QwenLM/Qwen3-TTS/issues/298)、[固定 seed 建议](https://github.com/QwenLM/Qwen3-TTS/issues/298#issuecomment-4330199697)、[仍有变化](https://github.com/QwenLM/Qwen3-TTS/issues/298#issuecomment-4411718686)、[建议者的限制说明](https://github.com/QwenLM/Qwen3-TTS/issues/298#issuecomment-4413001186)；创建 2026-04-17，自动关闭 2026-08-03；访问 2026-09-01。
- 精确证据：正文称 1.7B CustomVoice “每次合成的音频都不同，音色 or 情感都有差异，调整 temperature 无效”，并补充使用 vLLM；社区回复一方建议固定 seed，另一方仍见 voice changes，建议者承认 seed 只应用于模型一部分、不能保证 byte-identical。
- 适用性：模型直接命中，但 backend 是 vLLM，回复均非 Qwen 维护者；只能作为实现经验，不能证明官方 wrapper 的因果。
- 置信度：中（存在此现场报告与关闭状态）；低（seed 缓解效果）。

### [S6] QwenLM 官方 issue #61 — 多人场景突然变成其它声音

- URL：[issue](https://github.com/QwenLM/Qwen3-TTS/issues/61)、[预置音色评论](https://github.com/QwenLM/Qwen3-TTS/issues/61#issuecomment-3845997240)；创建 2026-01-24，关键评论 2026-02-04，自动以 `not_planned` 关闭 2026-06-02；访问 2026-09-01。
- 精确证据：正文报告长对话中男女声/音色突变；评论者称即使降低到 `temperature=0.1, top_k=10, top_p=0.5`，官方 preset 在不同情绪文本下仍有“比较大”的音色变化。
- 适用性：与中文有声书、多角色和情绪跨段高度相关，但评论未精确声明版本/官方 wrapper，且无维护者复现。
- 置信度：低；只作为未解决风险信号，不作为参数结论。

### [S7] QwenLM 官方 PR #362 — “Default generate_voice_clone to non_streaming_mode=True…”

- URL：[PR](https://github.com/QwenLM/Qwen3-TTS/pull/362)；提交 2026-08-28；截至访问日 2026-09-01 为 open、未合并，作者非仓库成员。
- 精确证据：作者在 1.7B-Base audiobook clone 上报告 simulated-streaming、12.9 秒 reference 的段内语速漂移 `+16.7%`，non-streaming 为 `0.0%`，并明确说 CustomVoice/VoiceDesign 已默认 non-streaming。
- 适用性：只支持“保留 CustomVoice 当前默认布局”的风险判断；实验对象是 Base/clone，不能证明 CustomVoice 的音色或韵律漂移。
- 置信度：中（可审查的实现经验与当前 PR 状态）；低（外推到 1.7B CustomVoice）。

## Claim ledger

- **C1｜architecture-pattern｜已验证：** 1.7B CustomVoice 的 preset `speaker` 是身份 embedding，`instruct` 是独立文字风格条件，而非第二个 speaker anchor。[S2][S3]
- **C2｜version-compatibility｜已验证：** 12Hz 0.6B/1.7B CustomVoice 共享九个 preset 和十种语言，但当前 0.6B 源码禁用 `instruct`，且不存在独立发布的 `...-Instruct` 模型。[S1][S2]
- **C3｜implementation-experience｜已验证：** 对中文母语 preset 使用显式 Chinese 是官方建议；Dylan/Eric 会触发方言 language ID。[S1][S3]
- **C4｜version-compatibility｜已验证：** 官方 wrapper 暴露 Talker 与 Subtalker 两组 sampling 参数，并让 checkpoint generation config 优先于硬 fallback。[S2][S3]
- **C5｜implementation-experience｜未验证：** 双层 greedy 或较低随机性可能降低输出随机差异，但没有官方 speaker-similarity 证据证明它能减少音色漂移，且官方通常建议 sampling。[S2][S3][S5]
- **C6｜version-compatibility｜已验证：** 固定源码的 CustomVoice API 未显式支持 seed、数值 speed/pitch/energy/emotion、speaker strength、previous audio 或 continuation state。[S2][S3]
- **C7｜architecture-pattern｜已验证：** 每个 CustomVoice 调用重新构造条件；batch 是独立样本的共同执行，不提供跨请求身份/韵律连续性。[S2][S3]
- **C8｜implementation-experience｜已验证：** 维护者确认强情绪 instruction 可诱发笑声、Ryan 本身偏 expressive/non-broadcast，并建议更明确的否定 instruction 或换声。[S4]
- **C9｜implementation-experience｜未验证：** 固定一条克制的正/负面 instruction、避免 Ryan，可能减少过度戏剧化，但需要对具体中文旁白做 A/B 听测。[S4]
- **C10｜implementation-experience｜已验证：** #298/#61 的相关投诉没有关联修复提交，分别由自动化以 `not_planned` 关闭；“issue 已关闭”不能解释为问题已修复。[S5][S6]
- **C11｜implementation-experience｜未验证：** vLLM 固定 seed 可能改善某些运行的行为一致性，但社区证据冲突，且不是官方 `qwen-tts` 控制。[S5]
- **C12｜version-compatibility｜已验证：** 官方 0.6B/1.7B 和 long-speech 数字衡量内容 WER 或 instruction following，不衡量跨请求 timbre consistency，因此不能据此宣称 1.7B 比 0.6B 更不漂移。[S1]
- **C13｜architecture-pattern｜已验证：** VoiceDesign→Base reusable clone prompt 是官方给出的多行角色一致性替代路径，但它不再是 CustomVoice，也失去当前 12Hz Base 的 instruction control。[S1][S2]
- **C14｜implementation-experience｜未验证：** Base simulated-streaming 的长段语速漂移实验不应直接外推到默认 non-streaming 的 1.7B CustomVoice。[S2][S7]
