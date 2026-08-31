---
id: SPEC-qwen3-tts-speech-central-shim
companions:
  - voice-mapping.md
  - brownfield.md
  - architecture-diagrams.md
sources:
  - ../../../docs/designs/qwen3-tts-openai-api-integration.md
  - ../../../ansible/playbooks/deploy-qwen3-tts.yml
  - ../../../terraform/esxi/llm-server.tf
  - ../../../ansible/inventory/host_vars/llm-server.yml
---

> **Canonical contract.** 本 SPEC 及 `companions` 中的文件共同定义需要构建、测试和验证的完整契约。`sources` 仅用于追溯，不是下游实现输入。

# Qwen3-TTS Speech Central 本地音色映射 Shim

## Why

Speech Central 将可选音色写死为 OpenAI voice alias，而现有 `groxaxo/Qwen3-TTS-Openai-Fastapi` 将这些 alias 映射到另一套默认 Qwen3 音色，无法让用户通过客户端槽位试听适合中文有声阅读的 CustomVoice 音色。需要在现有 `llm-server` 上增加本地 shim，在不修改 Speech Central、不依赖 Cloudflare Worker的前提下，把固定 alias 映射到本地 Qwen3-TTS 音色，并以真实阅读体验验证本地方案是否可用。

## Capabilities

- **CAP-1**
  - **intent:** Speech Central 可以使用其固定 OpenAI 音色名调用本地 Qwen3-TTS。
  - **success:** 客户端无需修改 alias 即可从 `192.168.1.247:8100/v1/audio/speech` 获得可播放的 Qwen3-TTS 音频。

- **CAP-2**
  - **intent:** 运维者可以独立配置 OpenAI alias 到 Qwen3 CustomVoice speaker 的映射。
  - **success:** Speech Central 支持的每个固定槽位都解析为已在后端启用的 speaker，修改映射不需要修改客户端。

- **CAP-3**
  - **intent:** shim 对普通和流式 OpenAI-compatible TTS 请求保持透明。
  - **success:** 除 `voice` 外的请求字段原样转发；上游状态码、Content-Type 和响应体原样返回；流式音频在 shim 中不被完整缓冲。

- **CAP-4**
  - **intent:** 现有 Ansible 工作流可以把 shim 和 Qwen3-TTS 后端作为同一本地服务部署和验证。
  - **success:** syntax check 通过，部署后 health、models、WAV、streaming PCM、Compose、systemd 和容器重启次数检查全部通过。

- **CAP-5**
  - **intent:** 用户可以在 Speech Central 中直接试听中文候选音色并判断本地方案是否可用。
  - **success:** 短文本和真实书籍片段可以连续播放，等待时间可接受，且用户认可至少一个候选音色。

- **CAP-6**
  - **intent:** 运维者可以停止 TTS 而不影响现有 Qwen3.6 服务，并继续维持 DeepSeek 互斥边界。
  - **success:** Qwen3.6 与 TTS 可按现有边界共存；启动 DeepSeek 前可停止整个 TTS Compose；停止后 Qwen3.6 继续可用。

## Constraints

- 运行链路必须完全位于可信家庭局域网：`Speech Central → 192.168.1.247:8100 本地 shim → Compose 内部 Qwen3-TTS:8880`；Cloudflare Worker、Tunnel 和公网入口不得进入 PoC 运行链路。
- 复用现有 Terraform 管理的 `llm-server`、inventory 身份和双 RTX 3090 直通配置；本功能不新增或修改 Terraform 资源。
- 保留 `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`、固定的 `groxaxo` 源码版本、`optimized` backend、GPU ordinal 1、单 worker、单并发、持久模型缓存和不开机自启的 PoC 边界。
- 宿主机 `192.168.1.247:8100` 只由 shim 发布；Qwen3-TTS 后端端口 8880 只在 Compose 网络中可达。
- shim 只能改写 `voice`；不得接受客户端提供的上游 URL、任意模型路由或其他可造成 SSRF/越权转发的覆盖字段。
- alias 匹配不区分大小写；支持的 Qwen speaker 名可以直接透传；其他未知值回退到 `alloy` 对应的 speaker。完整规则见 `voice-mapping.md`。
- Qwen3.6 必须处于 active，DeepSeek mainline 必须处于 inactive，部署才可继续；启动 DeepSeek 前必须停止 TTS。
- 不得保存明文凭据。PoC 后若增加 API key，必须使用 Ansible Vault 间接引用。
- 部署必须遵守仓库流程：先做安全本地验证；部署需要单独授权；部署后只运行相关 verify，不把 deploy/publish/apply 当作 PR 验证。

## Non-goals

- 不修改或部署现有 Cloudflare `tts-shim` Worker。
- 不为 PoC 增加公网访问、Cloudflare Tunnel 或生产级鉴权。
- 不执行正式 TTFA、RTF、方差、soak 或吞吐基准；性能以用户实际体验为主。
- 不在此阶段确定最终最佳音色；初始映射用于试听，后续可按用户选择调整。
- 不增加 Base voice clone、VoiceDesign、ASR、自动模型切换或 DeepSeek/TTS 自动生命周期。
- 不重构现有 LLM playbook，也不改变 8081/8082 Chat API。

## Success signal

用户在 Speech Central 中依次选择固定的 OpenAI 音色槽位，实际听到对应的本地 Qwen3 中文候选音色，并能连续朗读真实书籍片段；停止 TTS 后现有 Qwen3.6 服务仍正常工作。

## Assumptions

- PoC 继续限定在可信家庭局域网并暂不鉴权；Speech Central 即使要求填写 API key，也允许使用不参与服务器校验的占位值。
