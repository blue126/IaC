# Digest: official UI and generation defaults

## Findings

- claim: The official Qwen3-TTS package includes a local Gradio demo launched with `qwen-tts-demo <model> --ip 0.0.0.0 --port 8000`; Qwen also links hosted Hugging Face and ModelScope demos.
  source: https://github.com/QwenLM/Qwen3-TTS/blob/main/README.md
  publisher: QwenLM
  pub_date: 2026-01-25
  accessed: 2026-09-01
  confidence: high
  class: version-compatibility

- claim: The official Python wrapper's hard defaults for both talker and subtalker are sampling enabled, `temperature=0.9`, `top_k=50`, and `top_p=1.0`; its API documentation recommends sampling for most use cases.
  source: https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/inference/qwen3_tts_model.py
  publisher: QwenLM
  pub_date: 2026-01-23
  accessed: 2026-09-01
  confidence: high
  class: version-compatibility

- claim: vLLM-Omni v0.28.0 documents optional Qwen3-TTS Gradio demos, but these are separate client/demo processes rather than an interface automatically served by the speech endpoint.
  source: https://github.com/vllm-project/vllm-omni/blob/v0.28.0/docs/user_guide/examples/online_serving/text_to_speech.md
  publisher: vLLM Project
  pub_date: 2026-08-19
  accessed: 2026-09-01
  confidence: high
  class: version-compatibility

- claim: vLLM-Omni v0.28.0 independently uses `temperature=0.9` and `top_k=50` for both the Qwen3-TTS talker and subtalker in its bundled deploy configuration.
  source: https://github.com/vllm-project/vllm-omni/blob/v0.28.0/vllm_omni/deploy/qwen3_tts.yaml
  publisher: vLLM Project
  pub_date: 2026-08-28
  accessed: 2026-09-01
  confidence: high
  class: version-compatibility

## Leads worth chasing

- The vLLM-Omni Gradio demo exposes voice, language, instructions, audio format, streaming and speed, but the checked implementation does not expose `temperature` or `top_k` sliders.

## Looked for but did not find

- No official Qwen or vLLM document found an audiobook-specific `temperature`/`top_k` preset.
