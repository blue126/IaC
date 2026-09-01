# v0.28.0 deployment and API compatibility digest

Accessed: 2026-09-01

## Findings

1. **The bundled Qwen3-TTS deployment is now an explicit two-stage streaming pipeline.**
   - Claim: `qwen3_tts.yaml` enables asynchronous chunking and connects Talker (stage 0) to Code2Wav (stage 1) through a shared-memory connector. Both stages default to `devices: "0"`; Talker and Code2Wav are graph-enabled by default, and Code2Wav uses incremental request-local state.
   - Source: https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/vllm_omni/deploy/qwen3_tts.yaml
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-08-31 tag
   - Confidence: high
   - Class: version/compatibility

2. **The legacy external stage-config interface cannot be carried forward unchanged.**
   - Claim: the v0.28.0 example passes a deploy config with `--deploy-config vllm_omni/deploy/qwen3_tts.yaml`, rather than the removed `--stage-configs-path` interface used by the rc1-era deployment.
   - Source: https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/examples/online_serving/text_to_speech/qwen3_tts/run_server.sh
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-08-31 tag
   - Confidence: high
   - Class: version/compatibility

3. **The executable name is inconsistent within the same tag and must be checked inside the selected image.**
   - Claim: the example shell script invokes `vllm-omni serve`, while the v0.28.0 user guide shows `vllm serve ... --omni`. This is a documentation/packaging ambiguity, not evidence that either spelling will work in every image.
   - Sources:
     - https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/examples/online_serving/text_to_speech/qwen3_tts/run_server.sh
     - https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/docs/user_guide/examples/online_serving/text_to_speech.md
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-08-31 tag
   - Confidence: high
   - Class: version/compatibility

4. **The existing shim's core OpenAI Speech contract remains compatible.**
   - Claim: the official client posts to `/v1/audio/speech` with `model`, `input`, `voice`, and `response_format`, plus optional Qwen-specific fields. Supported output choices include WAV and PCM. CustomVoice uses predefined names such as `vivian`, `ryan`, and `aiden`, so the shim still only needs to translate Speech Central's hard-coded OpenAI voice names to Qwen speaker names.
   - Source: https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/examples/online_serving/text_to_speech/qwen3_tts/openai_speech_client.py
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-08-31 tag
   - Confidence: high
   - Class: integration/version-compatibility

5. **The HTTP endpoint supports audio streaming, but this is separate from Speech Central compatibility.**
   - Claim: the user guide documents chunked PCM over `/v1/audio/speech` when `stream=true`, `stream_format="audio"`, `response_format="pcm"`, and `async_chunk` is enabled. It also documents a WebSocket endpoint at `/v1/audio/speech/stream` for incremental text input.
   - Source: https://raw.githubusercontent.com/vllm-project/vllm-omni/v0.28.0/docs/user_guide/examples/online_serving/text_to_speech.md
   - Publisher: vllm-project/vllm-omni
   - Published: 2026-08-31 tag
   - Confidence: high
   - Class: integration/version-compatibility

## Contradictions and caveats

- The bundled YAML comments say it was verified on one H100, so configuration compatibility does not establish RTX 3090 performance.
- The user guide and example script disagree on the executable name; the selected container image's `--help` output is the operational source of truth.
- The user guide's prose about stage-1 `max_num_seqs` does not match the tagged YAML. The first controlled test should use the tagged YAML as shipped and avoid speculative tuning.
- Both stages use GPU 0 in the official config. A two-GPU topology is possible only as a separate experiment and has no direct upstream evidence here for improving concurrency-1 RTF.

## Migration implication

- Pin v0.28.0 and model the role around `--deploy-config` and the bundled two-stage pipeline.
- Do not carry the rc1-era stage-config YAML or its wrapper/factory patch into the v0.28 branch.
- Keep the existing local shim and voice mapping; change only its upstream URL/model if the v0.28 endpoint passes a direct smoke request.
