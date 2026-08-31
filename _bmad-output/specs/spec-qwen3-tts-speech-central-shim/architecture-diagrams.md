# 架构图

## PoC 运行链路

```mermaid
flowchart LR
    SC[Speech Central\n固定 OpenAI voice alias]
    SHIM[Local TTS shim\n192.168.1.247:8100]
    API[groxaxo Qwen3-TTS API\nCompose internal :8880]
    MODEL[Qwen3-TTS 1.7B CustomVoice\nRTX 3090 GPU 1]

    SC -->|POST /v1/audio/speech| SHIM
    SHIM -->|rewrite voice only| API
    API --> MODEL
    MODEL -->|audio bytes or PCM stream| API
    API -->|transparent response| SHIM
    SHIM -->|playable audio| SC
```

Cloudflare Worker不在此链路中。shim 和 API 由同一个 Compose project 与 `qwen3-tts.service` 管理；只有 shim 端口发布到可信家庭局域网。

## LLM 运行时边界

```mermaid
stateDiagram-v2
    [*] --> QwenWithTTS
    QwenWithTTS: Qwen3.6 active\nQwen3-TTS shim + backend available
    QwenWithTTS --> DeepSeekOnly: stop qwen3-tts\nstart DeepSeek
    DeepSeekOnly: DeepSeek active\nQwen3-TTS unavailable
    DeepSeekOnly --> QwenWithTTS: stop DeepSeek\nstart Qwen3.6 and qwen3-tts
```

部署和启动检查必须拒绝 `Qwen3.6 inactive` 或 `DeepSeek active` 的状态，避免争抢 GPU 资源。
