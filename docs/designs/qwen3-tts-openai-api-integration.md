# Qwen3-TTS OpenAI API 部署方案

**日期**：2026-09-01（2026-09-03 迁移至新主机）
**状态**：已部署验证
**目标主机**：`llm-workstation`（`192.168.1.191`）

> **迁移说明**：本方案最初部署在 ESXi 上的 `llm-server`（`192.168.1.247`），
> 该主机已退役，其 VM 已销毁。实现由 `ansible/roles/qwen3-tts` 承载，运行在
> 裸机 `llm-workstation` 上。shim 与 profile bootstrap 两个文件在迁移中未改动；
> role 层面去掉了 Qwen3.6 共存与 DeepSeek 互斥逻辑，新主机上没有这两个服务。
> 迁移期间该 role 曾短暂命名为 `qwen3-tts-workstation`，以便与 llm-server 上的
> 同名 role 并存；后者删除后已改回 `qwen3-tts`——服务不应以其所在主机命名。

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

四项均取自 `ansible/roles/qwen3-tts/defaults/main.yml`。

`files/vllm-deploy-config.yaml` 中的取值（`gpu_memory_utilization`、`max_num_seqs`、`kv_cache_memory_bytes`、`silence_ban_frames`）尚未纳入校验：claim 的 oracle 读取会跳过首字符为空白的行，而这些键位于 `stages:` 之下均为缩进行，因此根本不会被收集，判定停在 `oracle_key_missing`。每个 stage 各出现一次所导致的 `oracle_key_duplicate` 轮不到触发。本文中关于它们的描述目前只能靠人工核对。

## 3. 已发布 shim 与 13 音色 catalog

shim 使用服务仓库发布的不可变镜像，而不是 IaC bind-mount 的 Python 源码：`ghcr.io/blue126/qwen3-tts-service-shim@sha256:37cabe5713613ba719e47bc9c535d0443c58243fdd0e4404f560ba3b60b231a5`。该 release 对应服务仓库 commit `ea79dff642f7be5e12bccf88167b0b30373f82cd`；服务仓库负责 shim 行为、catalog schema 与 alias/profile 选择，IaC 只部署其纯 runtime catalog。

shim 将客户端模型 `tts-1` 改写为实际 Qwen Base 模型，并将 `POST /v1/audio/speech` 的 13 个 OpenAI/Speech Central alias 路由到各自的持久 Base profile。Speech Central 请求 vLLM-Omni 不支持的 `response_format=aac` 时，shim 改为请求 MP3；`stream=true` 时未指定格式则补充 PCM/audio。普通音频和 streaming PCM 均增量代理，不完整缓冲。

IaC 挂载的 `voice-catalog.json` 只有 `schema_version`、`default_alias` 与 `voices` 三个字段，不含 reference 音频、转写、selection metadata、来源 hash 或 pending 状态。shim 不挂载 profile、模型或 cache；只有 Base `server` 保留 profile volume。未知、空白、null 或非字符串 voice 回退到 `alloy`。已知 alias 的目标 profile 不存在时，shim 返回 `503 profile_unavailable`，绝不静默改用其他声音。

切换到 VoiceDesign 或 Base、注册/替换 profile 和任何音频操作都需要独立授权。本次 catalog cutover 只重建 shim：先在私有 Base endpoint 检查 13 个 profile 全部存在，再用 `docker compose up --no-deps --pull never --force-recreate shim` 切换。它不重启 Base `server`、不改变 VoiceDesign 或 Qwen3.8 状态，也不改模型、GPU、vLLM deploy config、profile 或 cache。失败时仅恢复旧 catalog/Compose 并重建 shim。正式生产结果必须在切换执行后单独记录。

### 候选配对试听

若当前 `audiobook_narrator_zh` 的 Base clone 与 VoiceDesign 参考声不像同一人，可在获得单独授权后运行 `--tags candidate-pairing`。该路径依次生成三种非真人中文旁白候选（只变化低沉共鸣、厚实质感或轻微自然沙哑），每一种都使用同一段准确参考转写注册独立的临时 Base profile，并用同一固定探针文本生成 clone WAV。

流程不会覆盖 `audiobook_narrator_zh`、不会修改 Speech Central 映射，也不会并行运行 VoiceDesign 与 Base。参考 WAV、临时 profile 和 clone WAV 留在 `/data/models/qwen3-tts/profiles`；成功生成的 WAV 会拉取到控制端 `qwen3-tts-candidate-pairing/` 试听。请逐组比较同名 `*-reference.wav` 与 `*-clone.wav` 的身份相似性，而非只比较 reference 本身。某一候选失败会保留其诊断结果并继续处理其余候选，流程结束时会恢复并检查现有 Base + shim 的 `/health`。

只有用户明确选定某个候选后，才可以另行授权将其提升为生产 profile、替换生产 reference WAV，或让 Speech Central 指向它；未选择时不得清理候选资产或改变生产配置。

shim 不实现 Worker 的 `url_override`、`model_override`、`/admin/clone`，客户端不能改变固定的 upstream 路由。

## 4. 仓库实现

相关文件：

```text
ansible/playbooks/deploy-qwen3-tts.yml
ansible/playbooks/cutover-qwen3-tts-shim.yml
ansible/roles/qwen3-tts/defaults/main.yml
ansible/roles/qwen3-tts/tasks/main.yml
ansible/roles/qwen3-tts/tasks/shim-cutover.yml
ansible/roles/qwen3-tts/tasks/shim-cutover-verify.yml
ansible/roles/qwen3-tts/tasks/verify.yml
ansible/roles/qwen3-tts/templates/docker-compose.yml.j2
ansible/roles/qwen3-tts/templates/qwen3-tts.service.j2
ansible/roles/qwen3-tts/files/voice-catalog.json
ansible/roles/qwen3-tts/files/qwen3-tts-profile-bootstrap.py
ansible/roles/qwen3-tts/files/vllm-deploy-config.yaml
scripts/test-qwen3-tts-profile-bootstrap.py
```

playbook 采用薄编排模式：Deploy play 调用 `qwen3-tts` role，Verify play 只加载 role 的 `verify.yml`。role 管理以下内容：

- `server` 直接使用 pinned 官方 vLLM-Omni 镜像，不 checkout 上游源码、不做本地镜像构建，只通过 Compose `expose` 提供 `8880`；
- `shim` 使用已发布且按 digest 固定的非 root 服务镜像，仅读取 IaC 部署的纯 13-alias catalog，并发布 `192.168.1.191:8100`；
- Talker 保持 FULL/PIECEWISE CUDA Graph，Code2Wav 保持增量解码和 CUDA Graph；
- 官方 H100 配置的 `max_num_seqs=64` 会在 RTX 3090 的 Code2Wav CUDA Graph warmup 阶段 OOM，因此两个 stage 都限制在 `max_num_seqs: 3`，并把连接器的 `decode_cudagraph_batch_sizes` 固定为 `[1]` 以约束 Code2Wav 的图捕获规模；
- 两个 stage 的 `gpu_memory_utilization` 均为 `0.3`。0.6B CustomVoice 时期 Talker 用的是 `0.17`，换成 1.7B Base 后权重加开销实测已占 4.04 GiB，超过 `0.17 × 23.56 = 4.0 GiB` 的预算，因此必须上调。stage 1 是 Code2Wav 解码器，**没有 KV cache**，实测 3.24 GiB 全是权重与激活，它的 `0.3` 是够不到的天花板：启动时会记录 "Capping requested memory to available free memory"，无害；
- Talker 的 KV cache 用 `kv_cache_memory_bytes` 显式钉死，不再按启动时的空闲显存自行定大小。实测 2.92 GiB 装了 27,296 token，而 `max_num_seqs: 3` × `max_model_len: 4096` 只需 12,288 个，vLLM 自己也记录其 `0.3` 预算实际只要 2.66 GiB。取 2.00 GiB（18,696 token，4.56 倍余量），向与 Qwen3.8 共卡的 GPU1 归还约 0.9 GiB；
- shared-memory connector 的 `decode_batch_max_size` 固定为 `1`：三个请求可以同时在途，但 Code2Wav 仍逐个解码。上游的 `qwen3_tts_high_concurrency.yaml` 在 `max_num_seqs: 64` 下也用 `1`；
- Talker 的 `max_tokens` 由上游默认的 `512` 提高到 `2048`，把单次请求的音频上限从约 55 秒抬到约 3.5 分钟。`512` 会让整段发送的阅读客户端持续触发上限并重试，表现为服务很慢而不是失败；代价是退化的无 EOS 生成从约 14 秒后被拒绝变为约 57 秒。实测数据记在 `vllm-deploy-config.yaml` 该项的注释里；
- 两个容器均使用 `init: true`、`restart: "no"`；
- 独立 `qwen3-tts.service` 同时启动 `server` 和 `shim`，并开机自启。单元里声明 `After=qwen38.service`（仅排序，不加 `Requires`，Qwen3.8 失败时 TTS 仍应起来），使开机顺序与实测过的顺序一致；两者的显存都在启动时一次性定死，因此先后其实都能容纳；
- Hugging Face 模型缓存持久化到 `/data/models/qwen3-tts`，vLLM 编译缓存持久化到 `/data/models/qwen3-tts/vllm-cache`。

部署边界固定为 1.7B Base、GPU ordinal 1、单 worker 和 `max_num_seqs: 3`。与 llm-server 上的旧 role 不同，本 role 不含 Qwen3.6 共存断言与停止逻辑，也不要求 DeepSeek mainline 为 inactive —— 新主机上这两个服务都不存在，同卡上只有按 layer 分摊的 Qwen3.8。首次 profile 缺失时，常规启动会失败并要求单独获授权的 `--tags bootstrap`，不会启动一个只能返回 503 的表面健康服务。

## 5. 验证

本地安全验证：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test-qwen3-tts-profile-bootstrap.py
python3 tests/ci/qwen3-tts-shim-cutover-test.py
cd ansible
ansible-playbook playbooks/deploy-qwen3-tts.yml --syntax-check
ansible-playbook playbooks/cutover-qwen3-tts-shim.yml --syntax-check
```

静态 catalog contract test 验证不可变 image、纯 catalog schema/13 个精确映射、Compose 挂载边界以及 cutover task 的禁止操作。profile-bootstrap 标准库测试继续覆盖候选 profile 不能覆盖生产 profile 的约束。服务镜像自身的发布测试负责 alias 解析、fallback、readiness 与代理行为。

`cutover-qwen3-tts-shim.yml` 的真实主机预检在切换前读取 Base `/v1/audio/voices`，要求 catalog 中全部 13 个 profile 存在；切换后只检查 shim 的 `/health`、`/v1/models`、新 image identity、13 个 alias 的非持久 WAV smoke、shim restart count，以及 Base/VoiceDesign/Qwen3.8 状态未变。它不调用旧 `verify.yml` 的 Base restart-recovery 路径。旧 verify play 仍是单独的恢复演练，不是 shim cutover 的无扰动验收。

这些是程序化冒烟检查，不替代用户试听。

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

llm-server 上需要的手工模型切换在本主机不再适用：没有 DeepSeek，Qwen3.8 与 TTS 常驻并存，两者均开机自启，平时无需干预。

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
