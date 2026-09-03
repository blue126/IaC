# vLLM-Omni v0.28.0：Qwen3-TTS 音色漂移与夸张韵律控制

## 结论

v0.28.0 已把 OpenAI Speech 请求的 `voice`/`speaker`、`instructions`、`seed` 接到 Qwen3-TTS，但“字段被接受”不等于所有检查点都会执行该控制。`instructions` 会映射为模型的 `instruct`；实际指令控制仅由 1.7B CustomVoice 与 1.7B VoiceDesign 明确支持，0.6B CustomVoice 的官方推理代码会主动丢弃 `instruct`，Base 模型也未声明指令控制。[S1][S4]

`seed` 同时进入 Stage 0 Talker 的 `SamplingParams.seed` 和残差 MTP/Subtalker 的 `extra_args["tts_local_seed"]`。然而，v0.28.0 默认 CUDA 图模式含 FULL graph；标签源码和已合并 PR 都明确说明 FULL graph 使用单一捕获 RNG 流，不能保证逐请求 `tts_local_seed` 可复现。改为 Stage 0 eager 或纯 `PIECEWISE` 可保留逐行 generator，但原版 v0.28.0 仍没有“不同并发/批形状下 bit-exact”的完整保证。[S3][S4][S5][S6][S7]

对有声书，最可靠的当前策略是固定同一检查点、语言、voice/ICL reference、克制且完全相同的 instruction 与每请求 seed；Stage 0 禁用 FULL graph；若需要严格调度不变性，再把 Talker 调度和 Stage 1 真批处理压到 1。代价是吞吐/延迟：PR #4923 的组件测量显示 FULL graph 将 `talker_mtp` 每步从 39 ms 降至 9 ms，但没有给出 eager 对目标有声书负载的端到端代价。[S6]

适用性：上述代码结论固定到 vLLM-Omni `v0.28.0` 提交 `eb11446b…`、vLLM `v0.28.0` 提交 `2cf0a691…`。接线与默认值置信度高；“降低采样会改善夸张韵律”仅为待试听验证的实验假设；跨批 bit-exact 在原版标签上置信度低。

## Works now

### 1. 请求字段与精确接线

- `voice` 与 `speaker` 是同一字段的输入别名；Qwen3-TTS adapter 将名字转为小写并对照当前模型的 speaker 表。CustomVoice 未传 voice 时，服务端默认 `Vivian`。因此生产请求应显式写 voice，避免依赖隐式默认。[S4]
- `instructions` 在协议中存在，服务端逐请求写入 `tts_params["instruct"]`。这反驳“v0.28.0 Speech API 完全遗漏 instructions”的说法；真正限制在检查点能力：1.7B CustomVoice/VoiceDesign 支持，0.6B CustomVoice/Base 不支持或不使用。[S1][S4]
- 显式 `seed` 会深拷贝 Stage 0 参数，设置 `stage0.seed = request.seed`，并设置 `stage0.extra_args["tts_local_seed"] = request.seed`。标签测试还验证了 deploy-level seed 若存在，也会传播到 `tts_local_seed`；但捆绑的 v0.28.0 `qwen3_tts.yaml` 已不再提供默认 seed，所以必须由调用方逐请求传入。[S3][S4]
- `extra_params.temperature/top_p/top_k` 只直接改 Stage 0 Talker 的 `SamplingParams`。同一 dict 虽也写入 `extra_args`，残差 MTP 实现并不从这里取采样值，而是读取部署级 `subtalker_sampling_params`。[S4][S5]

### 2. v0.28.0 默认采样与并发形状

| 位置 | v0.28.0 捆绑默认 | 含义 |
|---|---|---|
| Stage 0 Talker | `temperature=0.9`, `top_k=50`, `top_p` 省略后为 vLLM 默认 `1.0`, `repetition_penalty=1.05`, `min_tokens=2`, `max_tokens=4096` | 生成主 codec/codebook-0 序列，也是最直接影响停顿、时长与高层韵律的采样层。 |
| residual MTP/Subtalker | `do_sample=true`, `temperature=0.9`, `top_k=50`, `top_p=1.0` | 固定生成其余 `Q-1` 个残差 codebook；是独立于 Talker 的第二套采样旋钮。 |
| Stage 1 Code2Wav | `temperature=0`, `top_p=1`, `top_k=-1`, `repetition_penalty=1` | 波形解码路径，不是另一个可调韵律 sampler。 |
| 默认 scheduler | Stage 0/1 均 `max_num_seqs=64`；Stage 1 `decode_batch_max_size=4`，图 bucket 默认只含 batch 1 | 允许请求共同调度；实际批形状会随负载变化。 |
| high-concurrency profile | Stage 0 `64`、Stage 1 `10`；`decode_cudagraph_batch_sizes=[1]`, `decode_batch_max_size=1`, Stage 1 eager | 已把 Stage 1 真后端批形状固定为 1，但 Stage 0 仍可共同批处理。 |

这些值与 Qwen 官方推理 hard defaults（Talker 与 Subtalker 均为 0.9/50/1.0）一致。[S1][S3]

### 3. 音色 conditioning 与缓存

- Base voice clone 有两条路径：`x_vector_only_mode=true` 只用 speaker embedding；`false` 使用 ref audio code + ref text 的 ICL。Qwen 官方明确警告 x-vector-only 可能降低克隆质量；需要跨段角色一致性时，应优先使用同一 ref audio + 精确 ref text 的 ICL，而不是只传 embedding。[S1]
- vLLM-Omni 的上传 voice 若保存了 `ref_text`，会自动走 ICL；没有 `ref_text` 时自动走 x-vector-only。预计算 profile 也按 `xvec`/`icl` 区分。[S4][S5]
- speaker cache 是进程内 LRU，key 含 `(model_type, lowercased voice name, created_at)`，Qwen 又按 xvec/icl 分 namespace；重传同名 voice 的时间戳会阻止复用旧 artifact。它缓存的是 `ref_spk_embedding`/`ref_code`，可稳定和加速 conditioning，但不缓存上一段生成的 Talker/Code2Wav 状态。[S5]

## Requires config change

### 1. 保留逐请求 seed

复制捆绑 `qwen3_tts.yaml` 后修改 Stage 0，二选一：

```yaml
stages:
  - stage_id: 0
    enforce_eager: true
```

或保留 piecewise 图但排除 FULL：

```yaml
stages:
  - stage_id: 0
    enforce_eager: false
    compilation_config:
      cudagraph_mode: PIECEWISE
```

依据是 Talker 只有在 `cudagraph_mode.has_full_cudagraphs()` 时关闭 per-row generators；纯 PIECEWISE 不触发该分支。PIECEWISE 在 CUDA 上的逐请求 seed 结论来自代码路径，标签内只有 NPU deploy 示例，没有 CUDA 端到端回归，因此置信度中等。[S3][S5]

### 2. 分别收紧 Talker 与 Subtalker

- 每请求实验：用 `extra_params` 调低 Stage 0 的 `temperature`，并按需缩小 `top_p`/`top_k`。
- residual MTP 必须改 deploy 的 `subtalker_sampling_params`；它是服务级全局值，并在 FULL graph 下烘焙进图，不能靠当前 Speech 请求逐段覆盖。[S4][S5][S6]
- 没有上游证据给出“有声书最佳”数值。降低 temperature 的已验证含义仅是减少随机性；它能否减少夸张韵律且不损伤自然度，必须以同文本/同 voice/同 seed 的盲听与韵律指标 A/B 验证。[S1][S3]

### 3. 需要 bit-exact 时限制批形状

- Stage 1 设 `decode_cudagraph_batch_sizes: [1]`、`decode_batch_max_size: 1`；高并发 profile 已这样配置。[S3]
- 最保守方案再把 Stage 0 `max_num_seqs: 1`，使 Talker 不发生单请求与共同批处理的形状切换。该设置逻辑上消除了 co-batch 变量，但上游没有在原版 v0.28.0 上发布对应 bit-exact E2E 测试，故是未验证的保守部署建议。[S7]
- eager 的已量化代价只有组件证据：FULL graph 的 `talker_mtp` 39→9 ms/step。不能把这个 4.3× 组件差直接当作整条 TTS 请求的降速比例。[S6]

## Not supported

- **跨请求 prosody/context carryover 不支持。** Speech schema 没有 previous request、codec tail、KV state 或 continuation handle；每次 `create_speech` 都产生新的 `speech-<uuid>`，从该请求的 text/voice/ref/instruct 重建 prompt。Stage 1 的 decoder cache 也以 request id 为边界，只在同一请求的后续 chunk 中继续。[S4][S5]
- 因此，切段会丢失 Talker 的自回归状态、当前语速/能量轨迹和 Code2Wav decoder history。speaker cache 只能复用声纹/reference artifact，不能维持句间呼吸、语调落点或跨段节奏。固定 voice、ICL reference、instruction、sampling 与 seed 能减少输入差异，但不是上下文续接。[S4][S5]
- **原版 v0.28.0 不承诺跨 batch shape 的 bit-exact。** issue #6361 在 eager + 固定 seed 下复现 sequential 与 4-way co-batch 的音频/时长差异；报告的 speaker similarity 仍高，差异主要是 acoustic/prosody/duration，而非换了 speaker。它最初复现于 0.27.0rc1，标签源码仍没有后述 Stage 0 batch-invariant 修复。[S7]
- `VLLM_BATCH_INVARIANT=1` 不是原版标签的即插即用解法：issue 复现显示 speaker encoder 的 invariant mean 变为 FP32 后进入 BF16 Conv1d 会崩溃；v0.28.0 标签的 `hidden_states.mean(...)` 后仍没有 dtype cast。[S5][S7]

## Future upstream

- issue #6361 截至 2026-09-01 仍为 open。贡献者 fork commit `28c4e7258`（不在 v0.28.0、也未进入上游 main）让 residual predictor 遵守 eager，并使用 batch-invariant linear；在 L40S、vLLM 0.28.0、`VLLM_BATCH_INVARIANT=1`、`--enforce-eager`、Stage 1 `decode_batch_max_size=1` 下，报告 12/12 sequential-vs-concurrent 对比 byte-identical，完整模型 executor 测试 230 passed。它只能作为未来 cherry-pick/上游候选，不能当作 v0.28.0 现有能力。[S7]
- 同一验证还表明 Stage 1 真 batch 1 与 batch 4 从第一个 `Conv1d` 起就不 bit-exact；`cudnn.deterministic=true` 不能提供跨批形状不变性。未来即使 Stage 0 修复合入，严格复现仍应保留 `decode_batch_max_size=1`，直到卷积 batch invariance 有上游实现与测试。[S7]

## Primary sources

访问日期均为 **2026-09-01**。

1. **[S1] QwenLM**, “Qwen3-TTS inference defaults and model capability matrix,” pinned commit `022e286b`，2026-03-17。官方默认值、0.6B 忽略 instruct、ICL/x-vector 说明与模型能力表。<https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L287-L350>；<https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L730-L801>；<https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#L73-L79>；<https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#L241-L290>
2. **[S2] vLLM-Omni**, “v0.28.0 release,” tag commit `eb11446b`，发布于 2026-08-31。<https://github.com/vllm-project/vllm-omni/releases/tag/v0.28.0>
3. **[S3] vLLM / vLLM-Omni**, “v0.28 sampling, CUDA Graph and Qwen3-TTS deploy defaults,” 2026-08-31。<https://github.com/vllm-project/vllm/blob/2cf0a6915ce544dc493a0990f2ea38d81601128a/vllm/sampling_params.py#L252-L267>；<https://github.com/vllm-project/vllm/blob/2cf0a6915ce544dc493a0990f2ea38d81601128a/vllm/config/compilation.py#L607-L632>；<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/deploy/qwen3_tts.yaml#L61-L138>；<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/deploy/qwen3_tts_high_concurrency.yaml#L52-L110>
4. **[S4] vLLM-Omni**, “v0.28 Speech protocol, Qwen request building, seed propagation and tests,” tag `v0.28.0`，2026-08-31。<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/entrypoints/openai/protocol/audio.py#L57-L178>；<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/entrypoints/openai/serving_speech.py#L2469-L2586>；<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/entrypoints/openai/serving_speech.py#L2997-L3138>；<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/tests/entrypoints/openai_api/test_serving_speech.py#L4646-L4665>
5. **[S5] vLLM-Omni**, “v0.28 Talker/MTP RNG, Subtalker controls, request-local chunk state and speaker cache,” tag `v0.28.0`，2026-08-31。<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L315-L351>；<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L1271-L1297>；<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/worker/gpu_model_runner.py#L1848-L1963>；<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/utils/speaker_cache.py#L228-L305>；<https://github.com/vllm-project/vllm-omni/blob/eb11446b7f2e30ca582f8aff3afe12e9a2e66f6c/vllm_omni/model_executor/stage_input_processors/qwen3_tts.py#L300-L367>
6. **[S6] vLLM-Omni PR #4923**, “[Perf][Qwen3-TTS] Align talker MTP CUDA graph capture with Qwen3-Omni & Adapt to async output,” 创建于 2026-07-06、合入于 2026-07-10。PR 明列 FULL/eager 的 seed 行为与 `talker_mtp` 39→9 ms/step。<https://github.com/vllm-project/vllm-omni/pull/4923>
7. **[S7] vLLM-Omni issue #6361**, “[Bug]: Qwen3-TTS fixed-seed output changes between sequential and 4-way co-batch requests,” 创建于 2026-08-19；含 2026-09-01 L40S 验证与未上游 fork commit `28c4e7258`。<https://github.com/vllm-project/vllm-omni/issues/6361>；<https://github.com/vllm-project/vllm-omni/issues/6361#issuecomment-5494117054>；<https://github.com/akshatvishu/vllm-omni/commit/28c4e7258>

## Claim ledger

| Sentence | Class | Status | Refs |
|---|---|---|---|
| v0.28.0 Speech API 接受 `instructions`，并把它映射到 Qwen3-TTS `instruct`。 | implementation | verified | [S4] |
| 0.6B CustomVoice 会忽略 instruct；Base 未声明 instruction control。 | model capability | verified | [S1] |
| 请求 seed 同时设置 Talker seed 与 residual MTP `tts_local_seed`。 | implementation | verified | [S4][S5] |
| 捆绑 v0.28.0 deploy 没有默认 seed。 | configuration | verified | [S3] |
| FULL CUDA Graph 下逐请求 `tts_local_seed` 不可复现；eager 保留 per-row generator。 | limitation | verified | [S5][S6] |
| CUDA 纯 PIECEWISE 会避开 FULL wrapper 并保留 per-row generator。 | code-path inference | verified（无标签 E2E） | [S3][S5] |
| `extra_params` 只直接覆盖 Stage 0 Talker；Subtalker 采样必须改 deploy。 | implementation | verified | [S4][S5] |
| ICL 使用 ref code + ref text；x-vector-only 可能降低克隆质量。 | model behavior | verified | [S1] |
| speaker cache 不携带前一请求的生成/prosody state。 | architecture | verified | [S4][S5] |
| 跨 Speech 请求没有 context/codec/KV continuation。 | unsupported capability | verified | [S4][S5] |
| 在原版 v0.28.0 把 Stage 0/1 批大小限制为 1 可获得端到端 bit-exact。 | deployment hypothesis | unverified | [S7] |
| 降低 Talker 与 Subtalker temperature/top-p 会减少“过度戏剧化”而不损害自然度。 | quality hypothesis | unverified | [S1][S3] |
| fork commit `28c4e7258` 是未来候选，不是 v0.28.0 或 upstream main 的现有修复。 | upstream status | verified | [S7] |
