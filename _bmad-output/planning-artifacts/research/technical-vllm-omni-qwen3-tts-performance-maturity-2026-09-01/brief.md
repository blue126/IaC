# Research brief

## Decision

Determine whether a newer vLLM-Omni/Qwen3-TTS implementation materially improves the current v0.14.0rc1 execution path enough to justify another deployment test, especially for single-request RTF on RTX 3090.

## Questions

1. What Qwen3-TTS changes landed after v0.14.0rc1?
2. Were the missing KV cache, unsupported torch.compile, CUDA Graph capture failure, or generation-runner limitations fixed?
3. Is there credible single-request performance evidence on consumer Ampere GPUs?
4. Should this deployment upgrade and retest, patch the runner, or stop investing in vLLM?

## Method

- Type: technical
- Shape: explore
- Topology: straightforward
- Preset: standard, pruned to one focused researcher
- Budget: up to 8 primary sources per round, at most 2 rounds
- Validation: normal, with independent checks for recommendation-bearing performance and compatibility claims
- Preferred sources: official GitHub repositories, release notes, merged PRs, issue discussions, official documentation
