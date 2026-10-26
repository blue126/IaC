# Digest: audiobook and cross-request consistency

## Findings

- claim: A Qwen3-TTS discussion participant reported audible preset-voice changes even after lowering generation to `temperature=0.1`, `top_k=10`, and `top_p=0.5`; this is a single uncontrolled user report, not an official recommendation.
  source: https://github.com/QwenLM/Qwen3-TTS/issues/61#issuecomment-3845997240
  publisher: QwenLM GitHub community
  pub_date: 2026-02-04
  accessed: 2026-09-01
  confidence: low
  class: implementation-experience

- claim: In a reproducible 1.7B fine-tune report, greedy decoding (`temperature=0`, `top_k=1` for talker and patched greedy subtalker) did not remove wrong-timbre/gender-flip behavior at the first 1–2 seconds of short standalone utterances; the same text was stable inside a longer sentence.
  source: https://github.com/QwenLM/Qwen3-TTS/issues/343
  publisher: QwenLM GitHub community
  pub_date: 2026-07-10
  accessed: 2026-09-01
  confidence: medium
  class: implementation-experience

- claim: An audiobook project changed from `temperature=0.9, top_p=1.0` plus per-call OS-entropy reseeding to `temperature=0.6, top_p=0.85` plus one persisted seed per run to improve inter-chunk pitch/energy consistency; its author explicitly said the wiring was checked but the change had not been listened to end-to-end.
  source: https://github.com/sergenes/runandread-audiobook/pull/5
  publisher: runandread-audiobook
  pub_date: 2026-08-15
  accessed: 2026-09-01
  confidence: low
  class: implementation-experience

- claim: A separate Qwen3-TTS narration investigation argues that independent short synthesis calls cause sentence-initial pitch resets and terminal contours, and proposes multi-sentence spans; the author explicitly labels the causal split as reasoned rather than measured and calls for a blind comparison before implementation.
  source: https://github.com/rediacc/console/issues/526
  publisher: rediacc
  pub_date: 2026-07-19
  accessed: 2026-09-01
  confidence: low
  class: architecture-pattern

## Leads worth chasing

- A fixed/persisted seed is more directly connected to run-to-run variance than lowering `top_k`, but the exact seed semantics in the current vLLM-Omni request path require a local implementation check before deployment.
- Grouping consecutive Speech Central text into longer requests would address the repeated onset/reset mechanism more directly, but it may require client-side buffering or a stateful shim and must be assessed against playback latency.

## Looked for but did not find

- No controlled study establishing an optimum Qwen3-TTS audiobook value for `temperature` or `top_k`.
- No credible audiobook-specific evidence that `top_k=30` is better than the official `top_k=50`.
