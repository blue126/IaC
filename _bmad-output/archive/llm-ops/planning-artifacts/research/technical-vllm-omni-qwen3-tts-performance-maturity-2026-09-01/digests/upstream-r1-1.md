# Upstream Qwen3-TTS maturity — round 1 digest

Accessed: 2026-09-01

## Findings

1. **v0.28.0 is the current stable release and materially changes the Qwen3-TTS path.**
   - Claim: v0.28.0 was published 2026-08-31, rebases on vLLM 0.28, includes cached incremental Code2Wav decode (#5202) and the final code-predictor projection fusion (#5791). The old stage-configs-path interface was removed; deployment now uses the unified `vllm serve --omni` path and deploy config.
   - Source: https://github.com/vllm-project/vllm-omni/releases/tag/v0.28.0
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-08-31
   - Confidence: high
   - Class: version/compatibility

2. **Code2Wav gained request-local incremental decoder state, not demonstrated paged KV cache.**
   - Claim: #5202 caches the Transformer KV prefix, rolling suffix window, and convolution/quantization state so later chunks decode only new codec frames.
   - Source: https://github.com/vllm-project/vllm-omni/pull/5202
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-08-11
   - Confidence: high for implementation
   - Class: execution-path/version-compatibility

3. **Talker prefix caching is not a demonstrated optimization in the current path.**
   - Claim: #4923 changes Stage 0 `enable_prefix_caching` from true to false to avoid bookkeeping interference with the full-graph MTP path. This should not be conflated with Code2Wav incremental state or ordinary vLLM paged KV.
   - Source: https://github.com/vllm-project/vllm-omni/pull/4923
   - Publisher: vllm-project/vllm-omni
   - Published: merged 2026-07-10, updated 2026-08-26
   - Confidence: high for prefix-cache opt-out; medium for absence of paged KV support
   - Class: architecture/limitation

4. **The merged CUDA Graph strategy targets the MTP hot subgraph rather than one graph over the whole TTS pipeline.**
   - Claim: #4923 compiles the code predictor internally and wraps the full `talker_mtp` externally with `CUDAGraphWrapper`, reporting approximately 39 ms to 9 ms per step in the author's profile.
   - Source: https://github.com/vllm-project/vllm-omni/pull/4923
   - Publisher: vllm-project/vllm-omni
   - Published: merged 2026-07-10, updated 2026-08-26
   - Confidence: high for implementation; medium/unverified for portable performance
   - Class: execution-path/performance

5. **An earlier whole-loop CUDA Graph prototype was not merged.**
   - Claim: #1467 captured the full 16-step code predictor loop and reported A100 batch-1 isolated latency from 5.07 s to 1.43 s, but the PR was not merged and is not current behavior.
   - Source: https://github.com/vllm-project/vllm-omni/pull/1467
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-02-28
   - Confidence: high
   - Class: failed-or-superseded-implementation/performance

6. **torch.compile support has landed for the MTP path, but single-request portability is unverified.**
   - Claim: #1913 adds `torch.compile(mode="reduce-overhead", dynamic=False)`, fixed shapes, and batch buckets; its reported 9.9–22.7% RTF gains cover concurrency 4/8/16, not concurrency 1 or Ampere. #4923 later makes it the inner compilation layer under an outer MTP graph.
   - Source: https://github.com/vllm-project/vllm-omni/pull/1913
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-03-20
   - Confidence: high for implementation; medium/unverified for single-request performance
   - Class: execution-path/performance

7. **The V2 runner migration alone did not improve concurrency-1 latency.**
   - Claim: #2242 reports V2/V1 concurrency-1 wall time of 1.153/1.147 s. Code2Wav still uses a dummy EOS convention for the generic scheduler, and the PR lists no-op profile_run, synchronous sample-token D2H, and private CUDA-graph attributes as limitations.
   - Source: https://github.com/vllm-project/vllm-omni/pull/2242
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-03-31
   - Confidence: high
   - Class: version/compatibility/performance

8. **The only directly relevant RTX 3090 single-request result is promising but unverified.**
   - Claim: #5202 reports one RTX 3090 24 GB, Qwen3-TTS 1.7B Base, concurrency 1 result of RTF 0.244 to 0.222 and TTFP 142 to 143 ms, a 10.3% throughput improvement. It is a PR-author measurement with no independent reproduction found.
   - Source: https://github.com/vllm-project/vllm-omni/pull/5202
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-08-11
   - Confidence: medium, unverified
   - Class: performance/scale

9. **Upstream's production target is RTF below 1, but adjacent numbers do not independently verify the 3090 result.**
   - Claim: #938 sets RTF < 1 as a goal, cites H200 Code2Wav graph latency around 8.96 s to 6.60 s and an external L4 implementation around RTF 0.6.
   - Source: https://github.com/vllm-project/vllm-omni/issues/938
   - Publisher: vllm-project/vllm-omni
   - Updated: 2026-04-10
   - Confidence: medium, unverified
   - Class: performance/roadmap

## Contradictions and caveats

- The attention-grabbing 3.54x A100 result in #1467 is not merged and must not be treated as v0.28 behavior.
- The Qwen3-TTS README still says vLLM-Omni only supports offline inference, but that text dates to 2026-01-25 and conflicts with later upstream release work; it is stale for current serving capability.
- Projection fusion #4958 was reverted for CI failure and later re-landed as #5791 after loader fixes; only #5791/v0.28 represents the final state.
- Full cudagraph mode changes per-request MTP seed reproducibility according to #4923.

## Recommendation from this round

- Upgrade to pinned v0.28.0 for one controlled RTX 3090 concurrency-1 retest using its current deploy config.
- Do not patch first. Verify graph and incremental decode are active, then compare identical text, model, sampling, audio length, RTF, TTFP, and E2E.
- If v0.28 activates both improvements yet stays far from the target, stop patching scheduler/dummy-EOS without a profile proving they dominate.

## Missing evidence

- No independent reproduction of #5202 on an RTX 3090.
- No overall v0.28 RTX 3090 single-request benchmark found.
- No proof that the Talker uses paged KV cache.
- No proof that one CUDA Graph captures the whole Talker-to-Code2Wav pipeline.
- No evidence that the dummy-EOS scheduler shim has been removed.

Coverage was sufficient; the second pass found no independent consumer-GPU performance reproduction.
