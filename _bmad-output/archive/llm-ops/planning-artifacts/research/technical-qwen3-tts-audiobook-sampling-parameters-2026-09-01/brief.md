# Research brief

- Decision: choose practical Qwen3-TTS sampling settings for stable audiobook narration and determine whether a usable Web UI exists.
- Type: technical research.
- Shape: straightforward.
- Scope: official Qwen3-TTS UI/demo, official/default `temperature` and `top_k`, long-form/audiobook evidence, and whether those parameters can address style drift across separate requests.
- Effort: one focused round, 5–8 sources, normal validation, no subagents.
- Source priority: official QwenLM/Qwen3-TTS repositories and documentation, model cards/configuration, vLLM-Omni documentation/source, then issue/discussion evidence with reproducible details.

## Deepening plan: timbre drift and restrained narration

- Decision: choose the next locally deployable intervention that materially reduces cross-sentence timbre drift and overly dramatic audiobook prosody without making generation unusably slow.
- Slice 1 — identity stability: trace CustomVoice speaker conditioning, Talker/Subtalker stochastic paths, request-boundary resets, and seed behavior under vLLM-Omni CUDA Graph execution.
- Slice 2 — prosody restraint: distinguish the effects of stage-specific sampling, `instructions`, punctuation/text normalization, voice choice, request span, and the 0.6B/1.7B model difference.
- Slice 3 — implementation fit: rank only interventions supported by the current OpenAI-compatible shim and vLLM-Omni v0.28.0; identify small shim/server changes separately from unsupported ideas.
- Evidence: fixed-version Qwen and vLLM-Omni source/docs/issues first; reproducible long-form TTS implementations and relevant papers second. Verify load-bearing compatibility/performance claims with two independent sources.
- Deliverable: an evidence-ranked option matrix covering expected effect on timbre, dramatic prosody, latency, implementation cost, and a minimal Speech Central listening A/B. No complex machine benchmark.
