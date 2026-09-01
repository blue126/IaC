---
title: 'Technical research: vLLM-Omni Qwen3-TTS performance maturity'
type: 'technical'
topic: 'vLLM-Omni Qwen3-TTS performance maturity'
decision: 'Whether a newer upstream implementation is worth deploying to improve RTX 3090 single-request RTF'
source: 'native run'
status: complete
preset: standard
validation: normal
claims_verified: 7
claims_unverified: 3
created: '2026-09-01'
updated: '2026-09-01'
---

# Technical research: vLLM-Omni Qwen3-TTS performance maturity

## Executive summary

**Decision: deploy a pinned vLLM-Omni v0.28.0 as a controlled single-RTX-3090 retest, but do not predict success before measuring it locally.** The recommendation is driven by a materially new Qwen3-TTS execution path and the only directly relevant upstream result found: after incremental Code2Wav decoding, the PR author reported an RTF of 0.222 for Qwen3-TTS 1.7B Base at concurrency 1 on one RTX 3090. That result is promising enough to justify a retest, but no independent reproduction exists, and the test does not use the same model or task variant as the current deployment. [1][5]

v0.28.0 is not a drop-in image bump for the rc1-era role. It replaces the legacy external stage-config path with a registered Talker → Code2Wav pipeline, `--deploy-config`, shared-memory chunk streaming, an outer Talker MTP CUDA Graph, and request-local incremental Code2Wav state. The first retest should start from this official path without automatically transplanting the old stage YAML, the vLLM wrapper's autochunk disable, or the factory patch; remove the two patches permanently only after confirming that their original defects do not recur. [1][2][6]

The upstream side remains compatible in principle with an OpenAI Speech shim: v0.28.0 exposes `/v1/audio/speech` with `model`, `input`, `voice`, and `response_format`. This makes a protocol redesign unlikely, but it does not prove that the local shim's complete request/response behavior is compatible; that remains a direct smoke-test item. [4]

The biggest caveat is evidence quality: the tagged deploy configuration says it was verified on one H100, while the 3090 result is unreplicated. The first deployment should therefore be a reversible, single-GPU feasibility test. Start with one direct API smoke request, and then evaluate the user's actual Speech Central listening experience. [2][5]

## 1. Execution path and maturity

v0.28.0, released on 2026-08-31 and based on vLLM 0.28, includes the Qwen3-TTS cached incremental decode work and the final code-predictor projection fusion. Its tag contains distinct Talker, code predictor, Code2Wav, connector, API adapter, deploy configuration, and Qwen3-TTS test surfaces. This is a substantive implementation generation beyond the v0.14.0rc1 path, not a small scheduler revision. [1][11]

The bundled configuration runs two stages connected by shared-memory chunk streaming:

- Talker generates codec representations and defaults to CUDA Graph execution.
- Code2Wav incrementally turns codec frames into audio and keeps request-local Transformer KV prefix, rolling suffix, convolution, and quantization state.
- Both stages default to GPU 0; the official baseline is therefore a single-GPU topology. [2][5]

The merged Talker optimization compiles the code predictor internally and captures the outer `talker_mtp` hot path with a FULL CUDA Graph. It also avoids per-step hidden-state device-to-host transfer. The author's profile reports a reduction from roughly 39 ms to 9 ms per MTP step, but that number is not independently portable to an RTX 3090. [6]

This makes “0.6B” alone a poor runtime predictor. TTS latency is not one transformer forward pass: it includes autoregressive Talker/MTP work, multi-codebook generation, a second Code2Wav stage, repeated chunk processing, audio synthesis, and orchestration/synchronization overhead. These costs are a plausible explanation for a small model fitting easily in VRAM yet running slowly, and v0.28 targets several of them. They are **not yet proven to be the dominant cause** of the current 0.6B CustomVoice rc1 result; only a local per-stage profile can establish that. [2][5][6]

Code2Wav's incremental KV state must not be described as general Talker PagedAttention or paged KV support. It is request-local decoder state that prevents earlier codec frames from being recomputed for every later chunk. The tagged Talker configuration explicitly disables prefix caching. [2][5]

## 2. Performance evidence

The most decision-relevant data comes from PR #5202. For a 32-prompt Seed-TTS benchmark of Qwen3-TTS 1.7B Base at concurrency 1 on one 24 GB RTX 3090, the author reports:

| Metric | Before incremental decode | After incremental decode |
| --- | ---: | ---: |
| RTF | 0.244 | 0.222 |
| TTFP | 142 ms | 143 ms |

The change improves reported audio throughput by 10.3% while leaving first-packet latency essentially unchanged. This is direct evidence that the new path can be faster than real time on the same GPU class, but it remains **unverified** because no independent 3090 reproduction was found. [5]

Other upstream numbers are useful for identifying mechanisms, not for forecasting performance on this machine:

- PR #4923 reports a reduction from about 39 ms to 9 ms per Talker MTP step and an aggregate concurrency-8 RTF improvement, but omits the hardware used for the aggregate benchmark. [6]
- An earlier PR reported a large A100 gain from graphing the full 16-step predictor loop, but it was not merged and is not v0.28 behavior. [7]
- The earlier `torch.compile` work reported improvements only at concurrency 4/8/16, not concurrency 1 or Ampere. [8]
- The V2 runner migration itself reported concurrency-1 wall time of 1.153 s versus 1.147 s, effectively no single-request benefit; this argues against treating runner/scheduler migration alone as the solution. [9]
- The production-readiness RFC defines an RTF below 1 as the target and includes related H200 and L4 figures, but neither figure independently confirms the RTX 3090 measurement. [10]

The evidence therefore supports **one upgrade/retest**, not a promise of RTF 0.222 and not a broad patching effort.

## 3. Integration and migration impact

### Speech Central shim compatibility

The official v0.28 client posts to `/v1/audio/speech` with the core OpenAI Speech fields. WAV and PCM remain supported, and CustomVoice accepts predefined Qwen speakers such as `vivian`, `ryan`, and `aiden`. If the local shim already handles this request/response subset, its OpenAI-name → Qwen-speaker mapping can likely remain unchanged; confirm this with one direct end-to-end request rather than assuming full compatibility from the upstream client alone. [4]

The server also documents chunked PCM over the HTTP speech endpoint and a WebSocket endpoint for incremental text. These are possible later optimizations; they are not prerequisites for validating the existing Speech Central flow, and client-side support should not be assumed. [12]

### Ansible migration

The v0.28 branch of the role should be modeled as a new execution path:

1. Pin the v0.28.0 image/package and use its registered Qwen3-TTS deploy configuration.
2. Replace the rc1-era legacy stage-args integration based on `--stage-configs-path` with `--deploy-config` and `--omni`.
3. Start the v0.28 path without the vLLM wrapper autochunk disable and factory patch; remove them permanently only after a smoke test confirms that the defects they addressed no longer recur.
4. Keep the local shim, authentication, voice mapping, and upstream model selection for the first smoke test; change only what the direct compatibility result requires.
5. Resolve the executable inside the chosen image with `--help`: the tagged example calls `vllm-omni serve`, while the tagged user guide shows `vllm serve ... --omni`. [1][2][3][12]

The tagged YAML and its user guide also disagree on some tuning prose, including stage-1 `max_num_seqs`. The first test should use the tagged YAML as shipped rather than mixing in tuning guidance. [2][12]

## 4. Cross-dimension insight

The combined evidence makes software execution maturity—not model capacity alone—a strong hypothesis for the surprising rc1 result. v0.28 specifically removes recomputation and synchronization from two repeated hot paths, and an upstream 3090 result is already below RTF 1. This does not prove the local bottleneck, but it makes a newer single-GPU baseline more informative than immediately adding a second 3090.

The official deploy configuration places both stages on GPU 0, and the only directly relevant 3090 benchmark also uses one GPU. A dual-GPU layout may later help throughput or stage isolation, but this research found no direct evidence that it improves concurrency-1 RTF enough to justify testing it before the single-GPU v0.28 baseline. [2][5]

## 5. Contrary evidence and limitations

- The RTX 3090 RTF 0.222 result comes from the implementation's PR author, has no independent reproduction, and uses 1.7B Base rather than the currently relevant 0.6B CustomVoice path. [5]
- The official deploy YAML says it was verified on one H100. Configuration correctness on an RTX 3090 remains a local test question. [2]
- The merged Talker optimization reports a large hot-loop gain, but the benchmark does not establish end-to-end Speech Central behavior or long-form continuity on this host. [6]
- Older dramatic A100 graph numbers refer to an unmerged design and must not be used as v0.28 expectations. [7]
- Upstream documentation inside the same tag is internally inconsistent about the executable name and some stage tuning. [3][12]

## 6. Recommendations

1. **Run one pinned v0.28.0 single-GPU test.** Confidence: medium. The implementation evidence is strong, while the portable 3090 performance claim is unverified.
2. **Use the official deploy config first.** Do not transplant the rc1 stage config or patches into the first retest; preserve the ability to restore a narrow patch if its original defect recurs. Confidence: medium. [1][2]
3. **Keep validation deliberately small.** After startup and one direct `/v1/audio/speech` smoke request, use the same representative Chinese passage in Speech Central and judge whether the playback buffer grows or drains over time. Record only TTFB, generated audio duration, wall time, RTF, and the user's continuity and quality assessment.
4. **Do not test dual GPU before the new single-GPU baseline.** The upstream baseline is single-GPU, and no direct concurrency-1 dual-GPU benefit was found. Confidence: medium. [2][5]
5. **Stop and profile before patching if v0.28 still misses real time.** Confirm whether Talker FULL graph and Code2Wav incremental decode are active. If both are active and the RTF remains far above 1, do not speculate about scheduler or dummy-EOS fixes unless a profile shows that either issue is the dominant bottleneck. Confidence: medium. [5][6][9]

## 7. Open questions

- Can the exact 0.6B CustomVoice model, representative Chinese text, and this host reproduce RTF below 1 on one RTX 3090? Only a local controlled retest can answer this.
- Which serving executable is present in the chosen v0.28.0 container image? Check image-local `vllm --help` and `vllm-omni --help` before templating the systemd/Compose command.
- Does Speech Central consume HTTP chunked PCM in a way that improves perceived continuity? Test only after the ordinary endpoint works; it is not required for the first feasibility decision.
- If the new single-GPU path remains slow, which stage dominates? Capture per-stage logs/profile before considering stage placement, dual GPU, or a narrow upstream patch.

## 8. Source appendix

| Ref | Claim/finding supported | Publisher | Published | Accessed | Confidence |
| --- | --- | --- | --- | --- | --- |
| [1] | v0.28.0 release contents, vLLM 0.28 base, removed legacy stage-config path | [vllm-project/vllm-omni](https://github.com/vllm-project/vllm-omni/releases/tag/v0.28.0) | 2026-08-31 | 2026-09-01 | high |
| [2] | Tagged Qwen3-TTS two-stage async deploy configuration and device defaults | [vllm-project/vllm-omni](https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/vllm_omni/deploy/qwen3_tts.yaml) | 2026-08-31 | 2026-09-01 | high |
| [3] | Tagged Qwen3-TTS server example and `vllm-omni serve` invocation | [vllm-project/vllm-omni](https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/examples/online_serving/text_to_speech/qwen3_tts/run_server.sh) | 2026-08-31 | 2026-09-01 | high |
| [4] | OpenAI-compatible request path, fields, formats, and CustomVoice speaker examples | [vllm-project/vllm-omni](https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/examples/online_serving/text_to_speech/qwen3_tts/openai_speech_client.py) | 2026-08-31 | 2026-09-01 | high |
| [5] | Incremental Code2Wav implementation and RTX 3090 concurrency-1 benchmark | [vllm-project/vllm-omni](https://github.com/vllm-project/vllm-omni/pull/5202) | 2026-08-11 | 2026-09-01 | medium, unverified performance |
| [6] | Talker MTP `torch.compile`, outer FULL CUDA Graph, and author's profile | [vllm-project/vllm-omni](https://github.com/vllm-project/vllm-omni/pull/4923) | 2026-07-10, updated 2026-08-26 | 2026-09-01 | high implementation; medium performance |
| [7] | Unmerged earlier full-loop CUDA Graph prototype | [vllm-project/vllm-omni](https://github.com/vllm-project/vllm-omni/pull/1467) | 2026-02-28 | 2026-09-01 | high |
| [8] | Earlier MTP `torch.compile` implementation and concurrency-only benchmark scope | [vllm-project/vllm-omni](https://github.com/vllm-project/vllm-omni/pull/1913) | 2026-03-20 | 2026-09-01 | high implementation; medium performance |
| [9] | V2 runner concurrency-1 comparison and listed scheduler/runner limitations | [vllm-project/vllm-omni](https://github.com/vllm-project/vllm-omni/pull/2242) | 2026-03-31 | 2026-09-01 | high |
| [10] | Production RTF target and adjacent H200/L4 figures | [vllm-project/vllm-omni](https://github.com/vllm-project/vllm-omni/issues/938) | updated 2026-04-10 | 2026-09-01 | medium, unverified |
| [11] | Tagged repository tree and Qwen3-TTS implementation/test surface | [GitHub/vllm-project](https://api.github.com/repos/vllm-project/vllm-omni/git/trees/v0.28.0?recursive=1) | 2026-08-31 | 2026-09-01 | high |
| [12] | Tagged online-serving guide, `vllm serve` spelling, HTTP/WebSocket streaming, and tuning prose | [vllm-project/vllm-omni](https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/docs/user_guide/examples/online_serving/text_to_speech.md) | 2026-08-31 | 2026-09-01 | high for documented interface; medium for inconsistent tuning prose |

## 9. Staleness map

| Claim class / item | Re-check date | State on 2026-09-01 |
| --- | --- | --- |
| Current v0.28 release, deploy layout, executable/API compatibility | 2026-09-30 | fresh |
| Talker outer graph implementation | 2026-09-26 | fresh |
| RTX 3090 single-request performance result | 2026-11-11 | fresh but unverified |
| Earlier `torch.compile` concurrency benchmark | 2026-04-20 | stale historical support |
| V2 runner concurrency-1 result | 2026-04-30 | stale historical support |
| Production-readiness roadmap figures | 2026-07-10 | stale historical support |
| Unmerged CUDA Graph prototype status | 2028-02-28 | historical, stable |

The mechanical staleness check reports the earliest re-check as 2026-04-20 because three historical supporting claims are already stale. The recommendation itself rests on fresh v0.28 sources; refresh the current execution-path claims by 2026-09-26 and version/API claims by 2026-09-30.
