# Qwen3-TTS OpenAI API 部署方案

**日期**：2026-09-01（2026-09-03 迁移至新主机）
**状态**：已部署验证
**目标主机**：`llm-workstation`（`192.168.1.191`）

> **迁移说明**：本方案最初部署在 ESXi 上的 `llm-server`（`192.168.1.247`），
> 该主机已退役。实现现由 `ansible/roles/qwen3-tts-workstation` 承载，运行在
> 裸机 `llm-workstation` 上。shim 与 profile bootstrap 两个文件在迁移中未改动；
> role 层面去掉了 Qwen3.6 共存与 DeepSeek 互斥逻辑，新主机上没有这两个服务。
> 旧 role `ansible/roles/qwen3-tts` 会随 llm-server 退役一并删除。

## 1. 目标与边界

在 `llm-workstation` 上部署 Qwen3-TTS 和一个轻量本地 shim，使 Speech Central 能使用其硬编码的 OpenAI voice 名称访问 Qwen3-TTS 原生音色。Open WebUI 也可以继续使用同一个 OpenAI-compatible API 地址。

- TTS 固定在 GPU ordinal `1`，与分摊到两张卡的 Qwen3.8 共用该卡；
- 不改变现有 `8081` Chat API；
- 不做 ASR、声音克隆管理、公网访问或自动模型切换；
- 以 Speech Central 的实际连续朗读体验为主要成功信号，不做复杂性能实验。

```text
Speech Central / Open WebUI
          |
          v
192.168.1.191:8100  local shim
          |
          v
Compose network only  server:8880  Qwen3-TTS backend
```

Cloudflare Worker `tts-shim` 只作为 OpenAI voice alias 映射行为的参考，不进入本地运行链路。

## 2. 选型

| 项目 | 选择 |
|---|---|
| 模型 | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` + 一次性 `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` bootstrap |
| API 服务 | `vllm/vllm-omni:v0.28.0` |
| pipeline | 官方 Talker → Code2Wav 两阶段 `--deploy-config` |
| backend | `vllm_omni` |
| 对外 API | `GET /health`、`GET /v1/models`、`POST /v1/audio/speech` |
| 模型别名 | `tts-1` |
| 对外地址 | `192.168.1.191:8100`，仅由 shim 发布 |
| 后端地址 | `server:8880`，仅 Compose 网络可达 |
| GPU | 宿主 ordinal `1`，容器内 device `0`，与 Qwen3.8 共享该卡 |
| 并发 | `3`（两个 stage 的 `max_num_seqs`） |

Base profile 保留两个客户端的固定 OpenAI voice 名称兼容性；VoiceDesign 仅作为一次性合成参考声 bootstrap，不是常驻 backend。

### 关键配置值

以下取值由 `tools/check-doc-claims.py` 对照仓库中的实际配置校验，改动其一而不改另一会使检查失败。

```yaml
qwen3_tts_vllm_image: "vllm/vllm-omni:v0.28.0"
qwen3_tts_gpu_ordinal: 1
qwen3_tts_port: 8100
qwen3_tts_min_free_vram_mib: 512
```

四项均取自 `ansible/roles/qwen3-tts-workstation/defaults/main.yml`。

`files/vllm-deploy-config.yaml` 中的取值（`gpu_memory_utilization`、`max_num_seqs`、`kv_cache_memory_bytes`、`silence_ban_frames`）尚未纳入校验：claim 的 oracle 读取只识别顶层键，而这些键位于 `stages:` 之下，且每个 stage 各出现一次会被判为歧义。本文中关于它们的描述目前只能靠人工核对。

## 3. 本地 shim

shim 以当前 Cloudflare Worker 的映射目的为基准，但使用 `python:3.12-slim` 和 Python 标准库在本地 Compose 中运行。它把客户端模型 `tts-1` 改写为实际 Qwen 模型，并转换 `POST /v1/audio/speech` JSON 的 `voice` 字段；其他 OpenAI-compatible 字段透明转发。Speech Central 请求 vLLM-Omni 不支持的 `response_format=aac` 时，shim 改为请求兼容性更好的 MP3，并将上游的 `audio/mpeg` 响应原样返回。`stream=true` 时若客户端没有提供格式，shim 补充 `response_format=pcm` 和 `stream_format=audio`。普通音频和 streaming PCM 响应均增量转发，不完整缓冲。

当前旁白 profile 使用受控的一次性流程：VoiceDesign 只生成非真人的中文参考 WAV，随后由 Base 的公开 `/v1/audio/voices` 接口以准确转写注册 `audiobook_narrator_zh`。参考 WAV 与持久化 profile 仅保存在 `/data/models/qwen3-tts/profiles`，不得提交、公开或写入日志。所有 Speech Central voice alias 都会被 shim 忽略并固定到该 profile；profile 缺失时 shim 返回 503，不会退回预设 speaker。

切换到 VoiceDesign 或 Base 都需要单独授权，并使用 `--tags bootstrap`。该流程先停止现有服务、仅启动临时 VoiceDesign 生成参考，再停止 VoiceDesign 后启动 Base 注册 profile，因此同一 GPU 不会并行运行两种模型。0.6B 仅在连续试听仍不可接受时作为最后回退选择，不是当前模型。

所有 alias 都固定到同一 Base ICL profile `audiobook_narrator_zh`；不再选择 CustomVoice preset，也不再区分男声或女声 alias。alias 仅为 Speech Central 的兼容输入，空值和未知值也使用同一个 profile。

| OpenAI voice | Base profile |
|---|---|
| all 13 supported aliases | `audiobook_narrator_zh` |

Base request 固定为 `task_type=Base`、`voice=audiobook_narrator_zh`、`language=Chinese`。客户端 `instructions` 会删除，而不是沿用 CustomVoice instruction；profile 不存在时 shim 返回明确 503，绝不静默改用 preset。

VoiceDesign 只在经单独授权的 `--tags bootstrap` 流程中生成描述为“成熟、沉稳、低起伏、自然的中文有声书旁白”的合成参考 WAV。它停止后才启动 Base，并通过公开 `/v1/audio/voices` 持久注册含准确转写的 ICL profile。Talker/Subtalker 采样仍为 `0.6/50`。

### 候选配对试听

若当前 `audiobook_narrator_zh` 的 Base clone 与 VoiceDesign 参考声不像同一人，可在获得单独授权后运行 `--tags candidate-pairing`。该路径依次生成三种非真人中文旁白候选（只变化低沉共鸣、厚实质感或轻微自然沙哑），每一种都使用同一段准确参考转写注册独立的临时 Base profile，并用同一固定探针文本生成 clone WAV。

流程不会覆盖 `audiobook_narrator_zh`、不会修改 Speech Central 映射，也不会并行运行 VoiceDesign 与 Base。参考 WAV、临时 profile 和 clone WAV 留在 `/data/models/qwen3-tts/profiles`；成功生成的 WAV 会拉取到控制端 `qwen3-tts-candidate-pairing/` 试听。请逐组比较同名 `*-reference.wav` 与 `*-clone.wav` 的身份相似性，而非只比较 reference 本身。某一候选失败会保留其诊断结果并继续处理其余候选，流程结束时会恢复并检查现有 Base + shim 的 `/health`。

只有用户明确选定某个候选后，才可以另行授权将其提升为生产 profile、替换生产 reference WAV，或让 Speech Central 指向它；未选择时不得清理候选资产或改变生产配置。

shim 不实现 Worker 的 `url_override`、`model_override`、`/admin/clone`，客户端不能改变固定的 upstream 路由。

## 4. 仓库实现

相关文件：

```text
ansible/playbooks/deploy-qwen3-tts-workstation.yml
ansible/roles/qwen3-tts-workstation/defaults/main.yml
ansible/roles/qwen3-tts-workstation/tasks/main.yml
ansible/roles/qwen3-tts-workstation/tasks/verify.yml
ansible/roles/qwen3-tts-workstation/templates/docker-compose.yml.j2
ansible/roles/qwen3-tts-workstation/templates/qwen3-tts.service.j2
ansible/roles/qwen3-tts-workstation/files/qwen3-tts-shim.py
ansible/roles/qwen3-tts-workstation/files/qwen3-tts-profile-bootstrap.py
ansible/roles/qwen3-tts-workstation/files/vllm-deploy-config.yaml
scripts/test-qwen3-tts-shim.py
```

playbook 采用薄编排模式：Deploy play 调用 `qwen3-tts-workstation` role，Verify play 只加载 role 的 `verify.yml`。role 管理以下内容：

- `server` 直接使用 pinned 官方 vLLM-Omni 镜像，不 checkout 上游源码、不做本地镜像构建，只通过 Compose `expose` 提供 `8880`；
- `shim` 使用独立的 `python:3.12-slim` 镜像，挂载仓库提供的 shim 文件，并发布 `192.168.1.191:8100`；
- Talker 保持 FULL/PIECEWISE CUDA Graph，Code2Wav 保持增量解码和 CUDA Graph；
- 官方 H100 配置的 `max_num_seqs=64` 会在 RTX 3090 的 Code2Wav CUDA Graph warmup 阶段 OOM，因此两个 stage 都限制在 `max_num_seqs: 3`，并把连接器的 `decode_cudagraph_batch_sizes` 固定为 `[1]` 以约束 Code2Wav 的图捕获规模；
- 两个 stage 的 `gpu_memory_utilization` 均为 `0.3`。0.6B CustomVoice 时期 Talker 用的是 `0.17`，换成 1.7B Base 后权重加开销实测已占 4.04 GiB，超过 `0.17 × 23.56 = 4.0 GiB` 的预算，因此必须上调。stage 1 是 Code2Wav 解码器，**没有 KV cache**，实测 3.24 GiB 全是权重与激活，它的 `0.3` 是够不到的天花板：启动时会记录 "Capping requested memory to available free memory"，无害；
- Talker 的 KV cache 用 `kv_cache_memory_bytes` 显式钉死，不再按启动时的空闲显存自行定大小。实测 2.92 GiB 装了 27,296 token，而 `max_num_seqs: 3` × `max_model_len: 4096` 只需 12,288 个，vLLM 自己也记录其 `0.3` 预算实际只要 2.66 GiB。取 2.00 GiB（18,696 token，4.56 倍余量），向与 Qwen3.8 共卡的 GPU1 归还约 0.9 GiB；
- shared-memory connector 的 `decode_batch_max_size` 固定为 `1`：三个请求可以同时在途，但 Code2Wav 仍逐个解码。上游的 `qwen3_tts_high_concurrency.yaml` 在 `max_num_seqs: 64` 下也用 `1`；
- Talker 的 `max_tokens` 由上游默认的 `512` 提高到 `2048`，把单次请求的音频上限从约 55 秒抬到约 3.5 分钟。`512` 会让整段发送的阅读客户端持续触发上限并重试，表现为服务很慢而不是失败；代价是退化的无 EOS 生成从约 14 秒后被拒绝变为约 57 秒。实测数据记在 `vllm-deploy-config.yaml` 该项的注释里；
- 两个容器均使用 `init: true`、`restart: "no"`；
- 独立 `qwen3-tts.service` 同时启动 `server` 和 `shim`，但不开机自启；
- Hugging Face 模型缓存持久化到 `/data/models/qwen3-tts`，vLLM 编译缓存持久化到 `/data/models/qwen3-tts/vllm-cache`。

部署边界固定为 1.7B Base、GPU ordinal 1、单 worker 和 `max_num_seqs: 3`。与 llm-server 上的旧 role 不同，本 role 不含 Qwen3.6 共存断言与停止逻辑，也不要求 DeepSeek mainline 为 inactive —— 新主机上这两个服务都不存在，同卡上只有按 layer 分摊的 Qwen3.8。首次 profile 缺失时，常规启动会失败并要求单独获授权的 `--tags bootstrap`，不会启动一个只能返回 503 的表面健康服务。

## 5. 验证

本地安全验证：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test-qwen3-tts-shim.py
cd ansible
ansible-playbook playbooks/deploy-qwen3-tts-workstation.yml --syntax-check
```

标准库测试覆盖全部 13 个 alias 和未知 alias 的同一 Base 请求载荷、profile 缺失时的 speech/health 503、普通 WAV、chunked PCM、AAC 兼容、health/models 代理，以及无效 input 在到达 upstream 前被拒绝。

部署后的 `verify` play 检查：

- systemd active，Compose 的 `server` 与 `shim` 均运行；
- `/health` 和 `/v1/models` 可用；
- `alloy`、`marin` 和未知 alias 都以同一 Base profile 返回有效 WAV；
- Speech Central 的 `response_format=aac` 请求被兼容转换并返回有效 MP3；
- `stream=true` 返回有效的 chunked PCM 音频；
- 两个容器均为 healthy，且无异常 restart；
- GPU 1 在部署完成后仍留有至少 `qwen3_tts_min_free_vram_mib` 的空闲显存。

这些是快速冒烟检查，不替代用户试听。

### 单请求实测

服务预热后，使用以下 111 字中文文本分别请求 WAV 和流式 PCM：

> 清晨六点，窗外的鸟鸣把我从睡梦中唤醒。厨房里，咖啡机发出轻微的响声，空气中很快弥漫着温暖的香气。我打开今天要读的书，故事从一座临海的小城开始。主人公沿着石板路慢慢前行，潮水拍打堤岸，远处的钟声提醒他，一段新的旅程即将开始。

| 模式 | 音频时长 | 首个音频字节 | 总耗时 | RTF |
|---|---:|---:|---:|---:|
| WAV | 27.120 秒 | 4.125 秒 | 4.171 秒 | `0.154` |
| streaming PCM | 30.320 秒 | 0.447 秒 | 4.539 秒 | `0.150` |

两次生成存在采样差异，因此音频时长不同。服务端对流式请求记录的首 chunk 为 70.97 ms；通过 LAN 和 shim 观测到的首个音频字节为 0.447 秒。流式总生成速度约为播放速度的 6.7 倍，已经明显满足 `RTF <= 1`，不需要为单请求场景扩展到双 RTX 3090。测试结束后 `server` 与 `shim` 均为 healthy，restart count 均为 0。

## 6. 已知问题：句间静音

Speech Central 连续朗读时，句与句之间有轻微卡顿。原因不是客户端缓冲不足——对一次真实的 30 句会话做过缓冲余量分析，余量从 +4 秒单调增长到 +62 秒，全程没有出现饥饿，RTF 为 `0.26`，客户端确实在后台预取。

卡顿来自音频本身：每段 clip 头部约有 400 毫秒、尾部约有 350 毫秒的近似静音，RMS 为峰值的 `0.13%`–`0.68%`，而语音段为 `6%`–`23%`。两端相接即为每个接缝约 775 毫秒的死区。

`silence_ban_frames` 看起来像是对症的开关，但实测无效：它禁止的是编码真正数字静音的 12 个 codec token，而模型在 clip 头部实际输出的是上述低电平噪声，使用的是其他 token。每组 15 个样本对比，接缝中位数在 `0` 时为 775 毫秒、在 `10` 时为 806 毫秒，因此该值保持 `0`。

可行的修法是按能量阈值裁剪——语音比该噪声底高一个数量级，阈值分离很干净——但非 PCM 格式需要 shim 内具备解码能力（ffmpeg 或等价物），因此尚未实现。

## 7. 客户端接入与成功标准

Speech Central：

```text
Settings -> Speech -> Voices -> OpenAI
Custom URL: http://192.168.1.191:8100/v1/audio/speech
Model:      tts-1
Voice:      alloy（也可选择客户端支持的其他 OpenAI voice）
```

Open WebUI：

```text
Admin Panel -> Audio
Engine:       OpenAI
API Base URL: http://192.168.1.191:8100/v1
Model:        tts-1
Voice:        alloy
Split:        punctuation
```

程序化验收已经证明普通与 streaming API 可返回有效音频、TTS 与同卡上的 Qwen3.8 可并存、容器无异常重启，且单请求 RTF 明显低于 1。最终用户验收是 Speech Central 能以合适音色连续朗读短文本、中英文和较长文章，并且播放缓冲不会持续耗尽。Open WebUI 接入不是阻塞条件。

## 8. 生命周期与回滚

llm-server 上需要的手工模型切换在本主机不再适用：没有 DeepSeek，Qwen3.8 与 TTS 常驻并存，服务不开机自启，按需启停即可。

```bash
sudo systemctl start qwen3-tts
sudo systemctl stop qwen3-tts
```

回滚时停止并禁用服务：

```bash
sudo systemctl stop qwen3-tts
sudo systemctl disable qwen3-tts
```

然后让 Speech Central 切回原语音提供商，并在 Open WebUI 中关闭 Audio engine。模型缓存默认保留；只有用户明确要求时才删除。

## 9. 待办

- 固定镜像 digest、模型 revision 和 checksum；
- API Key、Vault、LAN/Tailscale 访问控制；
- Open WebUI PersistentConfig 自动更新（Open WebUI 已迁至网关，需指向本主机的 shim）；
- Speech Central 长文章试听和音色偏好调整；
- shim 内按能量阈值裁剪 clip 首尾静音，消除约 775 毫秒的句间接缝（见 §6）；
- 为每个 OpenAI voice 槽位分别建立 Base 参考 profile，使 `voice` 参数重新生效；
- ASR 或公网入口。

## 10. 参考

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- [vLLM-Omni v0.28.0](https://github.com/vllm-project/vllm-omni/releases/tag/v0.28.0)
- [vLLM-Omni Qwen3-TTS serving guide](https://github.com/vllm-project/vllm-omni/blob/v0.28.0/docs/user_guide/examples/online_serving/text_to_speech.md)
- [Speech Central 的 Qwen3-TTS 说明](https://speechcentral.net/2026/02/21/qwen3-tts-advanced-open-source-voices-for-speech-central/)
- [Open WebUI OpenAI TTS integration](https://github.com/open-webui/docs/blob/main/docs/features/chat-conversations/audio/text-to-speech/openai-tts-integration.md)
