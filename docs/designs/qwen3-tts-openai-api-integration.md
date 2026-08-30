# Qwen3-TTS OpenAI API 快速部署方案

**日期**：2026-08-29
**状态**：待实施
**目标主机**：`llm-server`

## 1. 目标与边界

在现有 VM 中部署独立 Qwen3-TTS 服务，使 Speech Central 和 Open WebUI 能通过 OpenAI-compatible TTS API 朗读文本。

首期只做快速 PoC：

- Qwen3.6 与 TTS 并存；
- DeepSeek 运行时手工停止 TTS；
- 不改变现有 `8081/8082` Chat API；
- 不重构 LLM playbook；
- 不做 ASR、声音克隆管理、公网访问或自动模型切换。

```text
Qwen3.6 运行时：TTS 可用
DeepSeek 运行时：TTS 不可用
```

## 2. 首期选型

| 项目 | 选择 |
|---|---|
| 模型 | `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` |
| API 服务 | `groxaxo/Qwen3-TTS-Openai-Fastapi` |
| backend | `optimized` |
| API | `POST /v1/audio/speech` |
| 模型别名 | `tts-1` |
| 默认 voice | `alloy`，映射到 Vivian |
| 宿主地址 | `192.168.1.247:8100` |
| 容器端口 | 默认 `8880`，实施时以选定上游版本为准 |
| 并发 | `1` |

CustomVoice 适合两个客户端使用固定 voice 名称。Base、VoiceDesign 留到 PoC 之后。

该 API 服务支持 `tts-1`、OpenAI voice alias、自动分块，以及标准端点上的 `stream=true`。优先使用上游明确版本的 GPU 镜像；若没有合适镜像，则从一个明确 Git commit 构建。完整 digest 和模型 checksum 在 PoC 成功后补齐。

备选为 `audio.cpp`。不使用每个请求重新加载模型的 `llama-tts` CLI wrapper。

```text
Qwen3.6 -> Open WebUI ----┐
                          ├-> Qwen3-TTS :8100 -> one RTX 3090
Speech Central -----------┘
```

## 3. 仓库改动

首期只新增一个 one-off playbook：

```text
ansible/playbooks/deploy-qwen3-tts.yml
```

模型、端口和 PoC 参数直接放在 playbook 的 `vars` 中：

```yaml
qwen3_tts_model_repository: Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
qwen3_tts_backend: optimized
qwen3_tts_gpu_ordinal: 1
qwen3_tts_bind_address: 192.168.1.247
qwen3_tts_port: 8100
qwen3_tts_container_port: 8880
qwen3_tts_max_concurrent: 1
qwen3_tts_warmup_on_start: true
qwen3_tts_autochunk: true
qwen3_tts_model_cache_dir: /data/models/qwen3-tts
```

需要临时换 GPU 时使用 `-e qwen3_tts_gpu_ordinal=N`，不再为 PoC 增加 host vars。

playbook 内联完成目录创建、Compose 文件、systemd unit、启动和只读 verify。Compose 只映射一张 `nvidia.com/gpu=N`，持久化模型缓存，使用 `init: true` 和 `restart: "no"`。独立 `qwen3-tts.service` 不设置 `Wants`、`PartOf` 或 `Conflicts`，也不开机自启。

## 4. 实施与验证

### 4.1 离线实现

1. 检查上游 Dockerfile、GPU 镜像、容器端口和必需环境变量。
2. 创建一个 one-off playbook，在其中内联 Compose、systemd owner 和 verify。
3. 运行：

```bash
cd ansible
ansible-playbook playbooks/deploy-qwen3-tts.yml --syntax-check
```

playbook 在启动容器前执行远端 `docker compose config --quiet`，因此不增加单独的本地 render 测试。

### 4.2 部署冒烟测试

部署前确认 Qwen 正在运行、DeepSeek 未运行、端口 8100 空闲，并用 `nvidia-smi` 选择空闲显存更多的一张 GPU。然后部署并验证：

```text
GET  /health
GET  /v1/models
POST /v1/audio/speech -> 可播放音频
POST /v1/audio/speech + stream=true -> 收到音频分块
```

同时确认没有 CUDA OOM、swap 或异常 restart。首期不做长时间 soak 和完整性能基准。

### 4.3 客户端接入

Speech Central：

```text
Settings -> Speech -> Voices -> OpenAI
Custom URL: http://192.168.1.247:8100
Model:      tts-1
Voice:      alloy
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

两个客户端首期都手工配置。测试短文本、中英文和一篇较长文章，观察播放是否连续。记录 Speech Central 实际发送的 `stream` 和 `response_format`，但不提前增加协议转换层。

## 5. 成功标准与运维

PoC 成功条件：

- 普通和 streaming API 均返回可播放音频；
- Speech Central 可以连续朗读；
- Open WebUI 能朗读 Qwen3.6 回答；
- TTS 与 Qwen3.6 并存时没有 OOM、swap 或异常重启；
- 停止 TTS 后 Qwen3.6 不受影响。

TTFA、RTF、逐卡显存和 Qwen 性能变化只记录，不作为首期硬门槛。若 OOM，先更换 GPU；仍失败则尝试 0.6B CustomVoice，最后才改为与 Qwen3.6 互斥。

自动生命周期完成前：

```bash
# 切换到 DeepSeek 前
sudo systemctl stop qwen3-tts

# 切回 Qwen3.6 后
sudo systemctl start qwen3-tts
```

不得在 DeepSeek 运行时启动 TTS。

回滚：

```bash
sudo systemctl stop qwen3-tts
sudo systemctl disable qwen3-tts
```

然后在 Open WebUI 中关闭 Audio engine，并让 Speech Central 切回原语音提供商。保留模型缓存，除非用户明确要求删除。

## 6. PoC 后再做

- 固定镜像 digest、模型 revision 和 checksum；
- API Key、Vault、LAN/Tailscale 访问控制；
- Open WebUI PersistentConfig 自动更新；
- Qwen/DeepSeek/TTS 自动生命周期；
- render/policy test、soak 和性能对照；
- Base voice clone、VoiceDesign、ASR 或公网入口。

## 7. 参考

- Qwen3-TTS：<https://github.com/QwenLM/Qwen3-TTS>
- API 服务：<https://github.com/groxaxo/Qwen3-TTS-Openai-Fastapi>
- Speech Central：<https://speechcentral.net/2026/02/21/qwen3-tts-advanced-open-source-voices-for-speech-central/>
- Open WebUI：<https://github.com/open-webui/docs/blob/main/docs/features/chat-conversations/audio/text-to-speech/openai-tts-integration.md>
- `audio.cpp`：<https://github.com/0xShug0/audio.cpp/blob/main/app/server/README.md>
