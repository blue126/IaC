# Validation pass — release and performance PRs

Accessed: 2026-09-01

## Verified claims

1. **v0.28.0 is a stable release and explicitly includes Qwen3-TTS performance work.**
   - The official release was published 2026-08-31, rebases on vLLM 0.28.0, names cached incremental Qwen3-TTS decoding (#5202) and fused code-predictor projections (#5791), and removes the legacy stage-config loading path in favor of registered pipelines/deploy configurations through `vllm serve --omni`.
   - Source: https://github.com/vllm-project/vllm-omni/releases/tag/v0.28.0
   - Confidence: high
   - Class: version/compatibility

2. **#5202 is merged and contains a directly relevant RTX 3090 concurrency-1 benchmark.**
   - The PR benchmark states one RTX 3090 24 GB, Qwen3-TTS 1.7B Base, 32 Seed-TTS prompts, graph batch size 1, baseline RTF 0.244 versus cached RTF 0.222, and TTFP 142 versus 143 ms.
   - It also documents request-local incremental state for Transformer KV prefix, rolling suffix, convolution, and quantization, plus 34 incremental-decode tests and 22 Code2Wav tests passing.
   - Source: https://github.com/vllm-project/vllm-omni/pull/5202
   - Merged: 2026-08-11
   - Confidence: high for implementation and what the author measured; medium/unverified for independent performance reproducibility
   - Class: execution-path/performance

3. **#4923 is merged and replaces nested graph capture with outer FULL talker-MTP capture.**
   - The PR says GPU code predictor uses torch.compile only, the runner wraps `talker_mtp` in one FULL `CUDAGraphWrapper`, async output removes per-step hidden-state D2H, and its single-request profile changes `talker_mtp` from 39 ms to 9 ms per step.
   - Its benchmark reports aggregate RTF 0.54 to 0.19 at concurrency 8, but hardware fields are blank, so this number is not portable performance evidence for RTX 3090.
   - Source: https://github.com/vllm-project/vllm-omni/pull/4923
   - Merged: 2026-07-10
   - Confidence: high for implementation; medium/unverified for performance portability
   - Class: execution-path/performance

4. **v0.28 contains a materially different Qwen3-TTS implementation and test surface.**
   - The tag tree contains separate Talker, Code2Wav, code predictor, segmented graph wrapper, OpenAI TTS adapter, registered pipeline, online examples, incremental-decode tests, CUDA-graph tests, and deploy configs.
   - Source: https://api.github.com/repos/vllm-project/vllm-omni/git/trees/v0.28.0?recursive=1
   - Publisher: GitHub/vllm-project
   - Confidence: high
   - Class: version/compatibility

## Verification outcome

- Recommendation-bearing version/compatibility claims are verified by both the release record and merged PR/tag contents.
- The RTX 3090 RTF claim remains **unverified** because no independent publisher or reproduction was found. It is nevertheless directly relevant enough to justify one controlled local test, not to predict success.
- Release wording about scheduler-managed paged KV applies to diffusion/HunyuanImage3, not Qwen3-TTS. Qwen3-TTS #5202 implements request-local incremental Code2Wav state; the two claims must remain separate.
