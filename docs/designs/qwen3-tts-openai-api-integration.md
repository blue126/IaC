# Qwen3-TTS OpenAI API 快速部署方案

**日期**：2026-09-01
**状态**：已部署验证
**目标主机**：`llm-server`（`192.168.1.247`）

## 1. 目标与边界

在现有 VM 中部署 Qwen3-TTS 和一个轻量本地 shim，使 Speech Central 能使用其硬编码的 OpenAI voice 名称访问 Qwen3-TTS 原生音色。Open WebUI 也可以继续使用同一个 OpenAI-compatible API 地址。

首期只做快速 PoC：

- Qwen3.6 与 TTS 并存；
- DeepSeek 运行前手工停止 TTS；
- 不改变现有 `8081/8082` Chat API；
- 不做 ASR、声音克隆管理、公网访问或自动模型切换；
- 以 Speech Central 的实际连续朗读体验为主要成功信号，不做复杂性能实验。

```text
Speech Central / Open WebUI
          |
          v
192.168.1.247:8100  local shim
          |
          v
Compose network only  server:8880  Qwen3-TTS backend
```

Cloudflare Worker `tts-shim` 只作为 OpenAI voice alias 映射行为的参考，不进入本地运行链路。

## 2. 首期选型

| 项目 | 选择 |
|---|---|
| 模型 | `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` |
| API 服务 | `vllm/vllm-omni:v0.28.0` |
| pipeline | 官方 Talker → Code2Wav 两阶段 `--deploy-config` |
| backend | `vllm_omni` |
| 对外 API | `GET /health`、`GET /v1/models`、`POST /v1/audio/speech` |
| 模型别名 | `tts-1` |
| 对外地址 | `192.168.1.247:8100`，仅由 shim 发布 |
| 后端地址 | `server:8880`，仅 Compose 网络可达 |
| GPU | 宿主 ordinal `1`，容器内 device `0` |
| 并发 | `1` |

CustomVoice 适合两个客户端使用固定 voice 名称。Base、VoiceDesign 留到 PoC 之后。

## 3. 本地 shim

shim 以当前 Cloudflare Worker 的映射目的为基准，但使用 `python:3.12-slim` 和 Python 标准库在本地 Compose 中运行。它把客户端模型 `tts-1` 改写为实际 Qwen 模型，并转换 `POST /v1/audio/speech` JSON 的 `voice` 字段；其他 OpenAI-compatible 字段透明转发。Speech Central 请求 vLLM-Omni 不支持的 `response_format=aac` 时，shim 改为请求兼容性更好的 MP3，并将上游的 `audio/mpeg` 响应原样返回。`stream=true` 时若客户端没有提供格式，shim 补充 `response_format=pcm` 和 `stream_format=audio`。普通音频和 streaming PCM 响应均增量转发，不完整缓冲。

初始映射如下：

| OpenAI voice | Qwen3 speaker |
|---|---|
| `alloy`, `onyx`, `cedar` | `Uncle_Fu` |
| `echo`, `ash`, `verse` | `Dylan` |
| `fable`, `ballad` | `Eric` |
| `coral`, `nova`, `shimmer` | `Vivian` |
| `marin`, `sage` | `Serena` |

匹配不区分大小写。已启用的原生 Qwen speaker 名可直接透传；voice 为空或未知时回退到 `alloy`，即 `Uncle_Fu`。

shim 不实现 Worker 的 `url_override`、`model_override`、`/admin/clone`，客户端不能改变固定的 upstream 路由。

## 4. 仓库实现

相关文件：

```text
ansible/playbooks/deploy-qwen3-tts.yml
ansible/roles/qwen3-tts/defaults/main.yml
ansible/roles/qwen3-tts/tasks/main.yml
ansible/roles/qwen3-tts/tasks/verify.yml
ansible/roles/qwen3-tts/templates/docker-compose.yml.j2
ansible/roles/qwen3-tts/templates/qwen3-tts.service.j2
ansible/roles/qwen3-tts/files/qwen3-tts-shim.py
ansible/roles/qwen3-tts/files/vllm-deploy-config.yaml
scripts/test-qwen3-tts-shim.py
```

playbook 沿用 `qwen36` 的薄编排模式：Deploy play 调用 `qwen3-tts` role，Verify play 只加载 role 的 `verify.yml`。role 管理以下内容：

- `server` 直接使用 pinned 官方 vLLM-Omni 镜像，不 checkout 上游源码、不做本地镜像构建，只通过 Compose `expose` 提供 `8880`；
- `shim` 使用独立的 `python:3.12-slim` 镜像，挂载仓库提供的 shim 文件，并发布 `192.168.1.247:8100`；
- Talker 保持 FULL/PIECEWISE CUDA Graph，Code2Wav 保持增量解码和 CUDA Graph；
- 官方 H100 配置的 `max_num_seqs=64` 会在 RTX 3090 的 Code2Wav CUDA Graph warmup 阶段 OOM，因此两个 stage 固定为单请求，Talker 与 Code2Wav 的 `gpu_memory_utilization` 分别调整为 `0.17` 和 `0.3`；
- shared-memory connector 的 `decode_batch_max_size` 固定为 `1`，符合 Speech Central 单请求 PoC；
- 两个容器均使用 `init: true`、`restart: "no"`；
- 独立 `qwen3-tts.service` 同时启动 `server` 和 `shim`，但不开机自启；
- Hugging Face 模型缓存持久化到 `/data/models/qwen3-tts`，vLLM 编译缓存持久化到 `/data/models/qwen3-tts/vllm-cache`。

部署边界固定为 0.6B CustomVoice、GPU ordinal 1、单 worker 和单并发。playbook 在更改前要求 Qwen3.6 为 active、DeepSeek mainline 为 inactive。

## 5. 本地验证与部署验证

本地安全验证：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test-qwen3-tts-shim.py
cd ansible
ansible-playbook playbooks/deploy-qwen3-tts.yml --syntax-check
```

标准库测试覆盖全部 13 个 alias、原生 speaker 透传、未知/空 voice 回退、普通 WAV、chunked PCM、health/models 代理，以及无效 input 在到达 upstream 前被拒绝。

部署后的 `verify` play 检查：

- systemd active，Compose 的 `server` 与 `shim` 均运行；
- `/health` 和 `/v1/models` 可用；
- 男声 alias `alloy` 与女声 alias `coral` 均返回有效 WAV；
- Speech Central 的 `response_format=aac` 请求被兼容转换并返回有效 MP3；
- `stream=true` 返回有效的 chunked PCM 音频；
- 两个容器均为 healthy，且无异常 restart。

这些是快速冒烟检查，不替代用户试听。

### 单请求实测

服务预热后，使用以下 111 字中文文本分别请求 WAV 和流式 PCM：

> 清晨六点，窗外的鸟鸣把我从睡梦中唤醒。厨房里，咖啡机发出轻微的响声，空气中很快弥漫着温暖的香气。我打开今天要读的书，故事从一座临海的小城开始。主人公沿着石板路慢慢前行，潮水拍打堤岸，远处的钟声提醒他，一段新的旅程即将开始。

| 模式 | 音频时长 | 首个音频字节 | 总耗时 | RTF |
|---|---:|---:|---:|---:|
| WAV | 27.120 秒 | 4.125 秒 | 4.171 秒 | `0.154` |
| streaming PCM | 30.320 秒 | 0.447 秒 | 4.539 秒 | `0.150` |

两次生成存在采样差异，因此音频时长不同。服务端对流式请求记录的首 chunk 为 70.97 ms；通过 LAN 和 shim 观测到的首个音频字节为 0.447 秒。流式总生成速度约为播放速度的 6.7 倍，已经明显满足 `RTF <= 1`，不需要为单请求场景扩展到双 RTX 3090。测试结束后 `server` 与 `shim` 均为 healthy，restart count 均为 0。

## 6. 客户端接入与成功标准

Speech Central：

```text
Settings -> Speech -> Voices -> OpenAI
Custom URL: http://192.168.1.247:8100/v1/audio/speech
Model:      tts-1
Voice:      alloy（也可选择客户端支持的其他 OpenAI voice）
```

Open WebUI：

```text
Admin Panel -> Audio
Engine:       OpenAI
API Base URL: http://192.168.1.247:8100/v1
Model:        tts-1
Voice:        alloy
Split:        punctuation
```

程序化验收已经证明普通与 streaming API 可返回有效音频、TTS 与 Qwen3.6 可并存、容器无异常重启，且单请求 RTF 明显低于 1。PoC 的最终用户验收是 Speech Central 能以合适音色连续朗读短文本、中英文和较长文章，并且播放缓冲不会持续耗尽。Open WebUI 接入不是本次快速部署的阻塞条件。

## 7. 生命周期与回滚

自动生命周期完成前：

```bash
# 切换到 DeepSeek 前
sudo systemctl stop qwen3-tts

# 切回 Qwen3.6 后
sudo systemctl start qwen3-tts
```

不得在 DeepSeek 运行时启动 TTS。

回滚时停止并禁用服务：

```bash
sudo systemctl stop qwen3-tts
sudo systemctl disable qwen3-tts
```

然后让 Speech Central 切回原语音提供商，并在 Open WebUI 中关闭 Audio engine。模型缓存默认保留；只有用户明确要求时才删除。

## 8. PoC 后再做

- 固定镜像 digest、模型 revision 和 checksum；
- API Key、Vault、LAN/Tailscale 访问控制；
- Open WebUI PersistentConfig 自动更新；
- Qwen/DeepSeek/TTS 自动生命周期；
- Speech Central 长文章试听和音色偏好调整；
- Base voice clone、VoiceDesign、ASR 或公网入口。

## 9. 参考

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- [vLLM-Omni v0.28.0](https://github.com/vllm-project/vllm-omni/releases/tag/v0.28.0)
- [vLLM-Omni Qwen3-TTS serving guide](https://github.com/vllm-project/vllm-omni/blob/v0.28.0/docs/user_guide/examples/online_serving/text_to_speech.md)
- [Speech Central 的 Qwen3-TTS 说明](https://speechcentral.net/2026/02/21/qwen3-tts-advanced-open-source-voices-for-speech-central/)
- [Open WebUI OpenAI TTS integration](https://github.com/open-webui/docs/blob/main/docs/features/chat-conversations/audio/text-to-speech/openai-tts-integration.md)
