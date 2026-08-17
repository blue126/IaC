# DeepSeek V4 Flash 本地推理优化 —— 项目交接文档（Handoff）

**日期**：2026-08-17
**用途**：交给接手本项目的 AI/工程师。**只读本文档即可继续工作**，不需要原始对话上下文。
**关联文档**（细节均在，按需查阅）：
- `docs/designs/deepseek-v4-performance-optimization-plan.md`（全景优化计划，最详细）
- `docs/learningnotes/2026-08-14-deepseek-v4-dual-gpu-deployment.md`（部署与实验纪年）
- `_bmad-output/implementation-artifacts/spec-deepseek-v4-memory-prefill-experiments.md`（实验规范）
- `_bmad-output/planning-artifacts/research/technical-deepseek-v4-gguf-memory-and-prefill-optimization-research-2026-08-14.md`（研究基线）

---

## 0. 一句话现状

homelab 的 DeepSeek V4 Flash（GGUF，双 RTX 3090，CPU-MoE）**正确性达标但性能不达标**（decode ~8 tok/s，目标 ≥10；8K 冷 TTFT 85–113s）。已决定走 **B 路线：升级到官方 0731 模型 + DSpark 投机解码 + mainline llama.cpp**。Stage 1（模型下载 + runtime 编译 + 硬件核验）**已完成**；下一步是 **Stage 2（隔离搭建 + 契约 + 性能基准）**，见 §6。

---

## 1. 环境与访问（接手者必读，无对话上下文）

### 1.1 机器

| 机器 | 地址 | 登录 | 说明 |
|---|---|---|---|
| **llm-server**（guest，跑推理） | 192.168.1.247 | `ssh ubuntu@192.168.1.247`（默认 key `~/.ssh/id_ed25519`，免密 sudo） | Ubuntu，36 核，334GB RAM，双 RTX 3090（ESXi 直通） |
| **ESXi 宿主机** | 192.168.1.251 | `ssh -i /Users/weierfu/Projects/IaC/.ssh/id_rsa_esxi_t7910 root@192.168.1.251` | ESXi 8.0.3；**必须用工作区 `.ssh/` 下的 RSA key**（`~/.ssh/id_ed25519` 不被接受） |
| 本机（开发/管理） | — | — | 仓库在 `/Users/weierfu/Projects/IaC`；Ansible 从 `ansible/` 目录跑 |

### 1.2 生产服务形态（不要动）

```
Open WebUI → host.docker.internal:8081（稳定 API，CIDR 白名单）→ openai-compat-proxy → 127.0.0.1:8082（ik llama-server，loopback）
```
- systemd：`deepseek-v4-ik.service`（候选容器 `restart:no`）；代理 `deepseek-v4-ik-compat.service`（`PartOf=` 跟随候选）
- 生产模型：`/data/models/DeepSeek-V4-Flash-GGUF/`（sokann，145.6GiB，block_count=43，无投机 head）
- 生产 runtime：`ik_llama.cpp@981e5ea0`（`/opt/deepseek-v4-ik/src/build/bin/llama-server`）
- **任何实验都必须用独立 Compose project + 独立端口，生产不动；候选期间生产按 spec 互斥设计会短暂停止**

### 1.3 关键路径（guest 上）

| 路径 | 内容 |
|---|---|
| `/data/models/DeepSeek-V4-Flash-GGUF/` | 生产模型（sokann） |
| `/data/models/DeepSeek-V4-Flash-0731-GGUF/` | **新模型**（unsloth UD-Q3_K_M 4 分片 + drafter，已 sha256 验证 ✅） |
| `/opt/deepseek-v4-ik/` | 生产 ik runtime（src/build） |
| `/opt/deepseek-v4-mainline/` | **新 mainline runtime**（src/build/bin/llama-server，已编译 ✅） |
| `/var/lib/deepseek-v4-ik/evidence/` | 证据目录（不可覆盖，按 experiment-id 建子目录） |
| `/tmp/0731-sha256.log`、`/tmp/mainline-build.log` | 下载校验/编译日志 |

---

## 2. 当前状态总览

| 项 | 状态 |
|---|---|
| 0731 模型下载（138.97GB，5 文件） | ✅ 完成，**SHA-256 5/5 全部通过**（§4.3 清单） |
| mainline llama-server 编译 | ✅ 完成，git HEAD=`10bf611e`（=pin），容器内运行验证通过 |
| P1：PCIe 维护窗口 | ✅ 物理完成 + 复核：GPU0 Gen3×16 / **GPU1 Gen3×8（卡的问题，未解决）** |
| P2/P3：P2P / graph split | ❌ **永久阻塞**（P2P=NS，不同 root port），已从路线图移除 |
| R6：prompt-cache 保存阻塞 /health | ⚠️ checkpoint=8 缓解（72s→22–28s）但**未解决**（同步保存根本问题） |
| Stage 2：DSpark 隔离搭建 | ⬜ 待做（见 §6） |

---

## 3. 已核实的硬事实

### 3.1 性能基线（ik runtime，同 corpus）

| 指标 | 值 |
|---|---:|
| 1K decode | 8.05 tok/s |
| 8K decode | 7.68 tok/s（<8 门槛） |
| 1K cold TTFT | ~22 s |
| 8K cold TTFT | ~85–113 s |
| API 契约 | 19/19 ✅；128K recall 通过 ✅ |

已收敛的 ik 参数（不要再折腾）：`threads=32`、`numa=distribute`、`threads-batch=36`、`batch=4096`、`ubatch=2048`、pinned memory=on、`cache-ram=8GiB`、全 CPU-MoE、`split-mode=layer`、`ctx=131072`。

### 3.2 硬件状态（已复核）

- **PCIe**：GPU0（ESXi 03:00.0）= **Gen3 ×16** ✅；GPU1（04:00.0）= **Gen3 ×8** ⚠️。空闲时 nvidia-smi 显示 Gen1 是 **ASPM 省电**，负载时两卡均 Gen3（已验证）。
- **GPU1 ×8 根因**：槽能力 ×16（根端口 LnkCap ×16），但链路只训练到 ×8；GPU1 在换槽前后两张不同槽里都是 ×8 → **问题在卡（金手指接触或 lane 损伤），不是槽**。修复：关机重新插拔/清洁金手指 → 交换测试（卡装进 GPU0 的槽验证）→ 仍 ×8 即卡 lane 损伤，接受或换卡。**不阻塞 DSpark**（decode 是 CPU 带宽主导）。
- **P2P**：ESXi 参数已开但 `cuDeviceCanAccessPeer()` 双向 0、`nvidia-smi topo -p2p r/w` 均 NS、两卡不同 root port → **graph split 永久不可行**，不要投入。

### 3.3 模型文件清单（已验证）

目录：guest `/data/models/DeepSeek-V4-Flash-0731-GGUF/`，来自 `unsloth/DeepSeek-V4-Flash-0731-GGUF`：

| 文件 | 大小 | SHA-256（已核对 ✅） |
|---|---:|---|
| `UD-Q3_K_M/...-00001-of-00004.gguf` | 0.01 GB | `36e02d6d87c9fbfe0dd4e8fd0d03cef2aa2c509248802a9d1772159112db3734` |
| `UD-Q3_K_M/...-00002-of-00004.gguf` | 49.22 GB | `b210930a3dc8ad13b55f6a0eb79b58abb0752ac446cb53aebcdc744c6834a7ad` |
| `UD-Q3_K_M/...-00003-of-00004.gguf` | 49.53 GB | `ac71bc6fd30c0af3eb702cea5bc94be570b9fed4857d63bf7180ec668683612c` |
| `UD-Q3_K_M/...-00004-of-00004.gguf` | 29.32 GB | `28b764750db8c4539df530292cd5950c6d161d81b20673b736ff4f8ca4ffa7ae` |
| `dspark-DeepSeek-V4-Flash-0731-Q8_0.gguf` | 10.90 GB | `2c7ac54b0b64a99df1f139a9f1371a00198265e1d6a614b77597d20a655a4249` |

模型特性：`deepseek4` 架构，0731 官方正式版（agentic 大幅优于 Preview：DeepSWE 7.3→54.4 等），**只带 DSpark、无 NextN MTP head**。

### 3.4 mainline runtime（已编译）

- Pin：`ggml-org/llama.cpp@10bf611e533d81f739128304991c5e133c6aebd8`（2026-08-16 master，含 DSpark，≥ #25784/`596a579`）
- 二进制：`/opt/deepseek-v4-mainline/src/build/bin/llama-server`
- 构建：容器内（`approachingai/ktransformers@sha256:5e8f614b...`），`-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86`
- **运行要点**：二进制 rpath 是容器路径，且依赖 `libnccl.so.2`（宿主机没有）→ **必须在容器内运行**，并 `--gpus all`（挂驱动）+ `LD_LIBRARY_PATH` 指向二进制目录。构建脚本：`scripts/deepseek-v4-mainline-build.sh`。
- 可选优化：`-DGGML_NCCL=OFF` 重建可消除 NCCL 依赖（本机 layer split 用不到 NCCL）；多卡如需可调 `GGML_SCHED_MAX_SPLIT_INPUTS`（当前不用）。

---

## 4. 已做的决定（不要推翻，除非有强证据）

1. **B 路线**：0731 + DSpark（放弃 Preview + NextN-MTP 路线 A）——agentic 质量确定大幅提升，DSpark decode ~1.8×（GPU 上；本机 CPU-MoE 待测，`n_max` 从 1 起测兜底）。
2. **量化档**：`UD-Q3_K_M`（~128GB，4 分片）；**drafter**：`Q8_0`（10.9GB）。
3. **runtime**：mainline llama.cpp（pin `10bf611e`）。
4. 其它低成本杠杆（cache 16/32GiB、n-cpu-moe 42、checkpoint=8 等）已测，均未达 10% 推广线——按规则不推广，**不要重复测**。

---

## 5. 下一步：Stage 2（DSpark 落地）—— 具体操作

> 原则：隔离优先、正确性先于性能、一次一个变量、证据不可覆盖。

### 5.1 隔离 smoke test（最快验证能跑）

在 guest 上（生产不动）：

```bash
docker run --rm --gpus all -p 127.0.0.1:8083:8083 \
  -e LD_LIBRARY_PATH=/build \
  -v /opt/deepseek-v4-mainline/src/build/bin:/build \
  -v /data/models/DeepSeek-V4-Flash-0731-GGUF:/models:ro \
  -w /build \
  approachingai/ktransformers@sha256:5e8f614b5f80ca9d281719a81d65f7dd153d9755696053a7487cd6b90558d1d8 \
  ./llama-server --host 0.0.0.0 --port 8083 \
  --model /models/UD-Q3_K_M/DeepSeek-V4-Flash-0731-UD-Q3_K_M-00001-of-00004.gguf \
  --model-draft /models/dspark-DeepSeek-V4-Flash-0731-Q8_0.gguf \
  --spec-type draft-dspark --spec-draft-n-max 1 \
  --fit off --flash-attn on --jinja \
  --ctx-size 131072 --threads 32 --numa distribute \
  --threads-batch 36 --batch-size 4096 --ubatch-size 2048 \
  --cache-ram 8192 --n-gpu-layers 100 --split-mode layer --cpu-moe \
  --no-mmap --cache-type-k f16 --cache-type-v f16
```

要点：
- **多分片模型**：`--model` 指第一个分片即可，自动加载其余分片；
- `--fit off` 对 DSpark **必需**（PR 线程实测，否则失败）；
- `--spec-draft-n-max` 上限 clamp 到 5（V4 drafter 训练块大小），默认 3；**CPU-MoE 下从 1 起测**；
- smoke：`curl 127.0.0.1:8083/v1/models` → 一个同步 chat（小输出）→ 观察 GPU 利用/无 crash。

### 5.2 正式候选流程（复用仓库现有 runner）

1. 建 experiment-id 证据目录（`/var/lib/deepseek-v4-ik/evidence/<id>/`），manifest 记录命令/pin/control；
2. **19 项 API 契约**（复用 `ansible/roles/deepseek-v4/files/contract-runner.py` 或等价 runner，指向 8083）；
3. **DSpark 输出与关闭投机时逐 token 一致**（投机解码理论无损，须实测证明）；
4. **性能 A/B**：同 corpus（固定 1K/8K cold-prefill，三样本中位），n_max=1→2→3；
5. **门槛**：decode 中位 ≥10 tok/s（目标）、无 swap/OOM/restart、每卡峰值显存 ≥2GiB 余量；
6. **对照**：与 ik 基线（§3.1）比；若需严格归因，补「Q3_K_M 无 DSpark」对照（去掉 `--model-draft`/`--spec-type`）；
7. 达标后：完整 128K recall + **一小时 soak**（health 空洞 ≤60s）+ post-contract → 才可 promote。

### 5.3 注意事项（已知坑）

- **R6 阻塞问题在新 runtime 上必须复现验证**（mainline 是另一套 `server_prompt_cache`；127K→短请求切换 + 独立 /health 探针）；
- mainline 的 `--cache-ram`/`--ctx-checkpoints`/`--cpu-moe` 语义与 ik 大致一致但实现不同，**不要假定行为相同**；
- DSpark 在 CPU-MoE 上的净收益未知——若 n_max 调档后仍无增益，如实记录，不硬推广；
- 模型加载 ~130GB、冷启动按十分钟量级规划。

---

## 6. 后续路线图（Stage 3+，按序）

| 阶段 | 内容 | 证据门 |
|---|---|---|
| 3 | 1K/8K 基准重跑（PCIe ×16 后，P1 验收） | 同 corpus 对照无回退 |
| 4 | GPU1 ×8 卡问题（维护窗口：清洁/交换测试） | 两卡 Gen3 ×16 |
| 5 | prefill 优化：`--override-tensor` 精准放专家（shared/gate/up-down 优先） | 全契约 + 显存余量 + 收益归因 |
| 6 | 容量轨道：256K/384K profile | 峰值分配 + recall，不混入速度实验 |
| 7 | 长期：SGLang-KT 重评估（当前 3090 不可行） | 硬件升级或 issue #1999 修复后 |

---

## 7. 规则与护栏（必须遵守）

1. **不自动 commit**——完成工作后先问用户「Ready to commit?」；
2. **Ask First**（未经用户同意不做）：runtime/model pin 变更、删除任何东西、ESXi/BIOS/PCIe/电源变更、context >128K、并发；
3. **一次只改一个主变量**，显式 control；证据目录按 experiment-id 不可覆盖；
4. **正确性先于性能**（19 契约 + 128K recall）；无 swap/OOM/restart；每卡峰值 ≥2GiB；
5. **生产服务不动**；候选独立 Compose project + 独立端口；候选期生产互斥停止由现有 candidate 流程管理；
6. 文档/对话中文，代码注释英文，commit 用 Conventional Commits（英文）；
7. Ansible 工作目录 `ansible/`；inventory 由 Terraform state 生成，失效先跑 `scripts/refresh-terraform-state.sh`；
8. 模型/runtime pin 变更必须先验 SHA-256 或 git HEAD。

---

## 8. 遗留问题 / 低优先级项

- [ ] GPU1 ×8（卡 lane 问题，维护窗口处理，不阻塞 DSpark）
- [ ] R6 prompt-cache 同步保存阻塞（checkpoint=8 缓解未根治；候选：cache 策略跳过超大单条 / 保存异步化；新 runtime 上先复现）
- [ ] prefill TTFT 无固定目标（越快越好）；PCIe ×16 对 prefill 的实际收益待基准验证
- [ ] mainline 可选重建 `-DGGML_NCCL=OFF`（消除 NCCL 依赖）
- [ ] HF 下载限速：guest 上设 `HF_TOKEN`（只读）可提速
- [ ] 0731 最终资格认证（一小时 soak）在 Stage 2 达标后进行

---

## 9. 参考资料

- 全景计划：`docs/designs/deepseek-v4-performance-optimization-plan.md`
- 学习笔记：`docs/learningnotes/2026-08-14-deepseek-v4-dual-gpu-deployment.md`
- 实验规范：`_bmad-output/implementation-artifacts/spec-deepseek-v4-memory-prefill-experiments.md`
- 研究：`_bmad-output/planning-artifacts/research/technical-deepseek-v4-gguf-memory-and-prefill-optimization-research-2026-08-14.md`
- 构建脚本：`scripts/deepseek-v4-mainline-build.sh`
- DSpark/MTP 合并 PR：https://github.com/ggml-org/llama.cpp/pull/25784
- DSpark 实测文章：https://rohitraj.tech/ar/notes/deepseek-dspark-speculative-decoding-llamacpp-2026
- 模型源：https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF
- SGLang-KT 阻塞：issue #1999（3090）、#2118（DSpark 缺失）
- ESXi P2P 参数：https://knowledge.broadcom.com/external/article/312208/vsphere-vmdirectpath-io-and-dynamic-dire.html
