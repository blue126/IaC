# DeepSeek V4 Flash 本地推理优化 —— 项目交接文档（Handoff）

**最后更新/实机核验**：2026-08-18
**用途**：交给接手本项目的 AI/工程师。**只读本文档即可继续工作**，不需要原始对话上下文。
**权威顺序**：当前运行事实以已提交的 `deepseek-v4-mainline` Ansible role 和 guest 实机为准；本文件是操作入口；性能计划只提供背景和后续方向。`_bmad-output/implementation-artifacts/spec-switch-deepseek-v4-to-mainline-dspark.md` 是已完成的历史实施 spec，**不是当前配置来源**。
**关联文档**（细节均在，按需查阅）：
- `docs/designs/deepseek-v4-performance-optimization-plan.md`（全景优化计划，最详细）
- `docs/learningnotes/2026-08-14-deepseek-v4-dual-gpu-deployment.md`（部署与实验纪年）
- `_bmad-output/implementation-artifacts/spec-deepseek-v4-memory-prefill-experiments.md`（实验规范）
- `_bmad-output/planning-artifacts/research/technical-deepseek-v4-gguf-memory-and-prefill-optimization-research-2026-08-14.md`（研究基线）

---

## 0. 一句话现状

homelab 的 DeepSeek V4 Flash（GGUF，双 RTX 3090，CPU-MoE）已切换到 **官方 0731 模型 + DSpark + mainline llama.cpp**。在此之上采用了五项优化：一条 `--override-tensor` 规则把尾部三层路由专家放到 CUDA1（§3.6）、`numactl --interleave=all`、`kernel.numa_balancing=0`、`--threads 16`（§3.9）、DSpark `n_max=2`（§3.12）。mainline active、ik inactive、稳定 API `8081` 健康、容器 restart=0。

decode **1K 7.58 → 9.46 tok/s（+24.8%）、8K 7.31 → 8.92 tok/s（+22.1%）**，两档均稳定高于 8.0 门槛，也都明显超过 ik 基线（8.05 / 7.68）。

**收益来源与直觉相反**：`-ot` 张量放置只贡献 8K 的 +7.8%；大头是 **NUMA 内存放置修复**（§3.9）和 **DSpark `n_max`**（§3.12）——两者都不占显存、不动硬件。瓶颈**不是**内存带宽（实测机器 80 GB/s，推理只用 27%），而是 43 层串行链的每层固定开销（§3.11）。

---

## 1. 环境与访问（接手者必读，无对话上下文）

### 1.1 机器

| 机器 | 地址 | 登录 | 说明 |
|---|---|---|---|
| **llm-server**（guest，跑推理） | 192.168.1.247 | `ssh ubuntu@192.168.1.247`（默认 key `~/.ssh/id_ed25519`，免密 sudo） | Ubuntu，36 核，334GB RAM，双 RTX 3090（ESXi 直通） |
| **ESXi 宿主机** | 192.168.1.251 | 从仓库根目录运行 `ssh -i .ssh/id_rsa_esxi_t7910 root@192.168.1.251` | ESXi 8.0.3；**必须用工作区 `.ssh/` 下的 RSA key**（`~/.ssh/id_ed25519` 不被接受） |
| 本机（开发/管理） | — | — | macOS 路径通常为 `/Users/weierfu/Projects/IaC`，Dev Container 为 `/workspaces/IaC`；Ansible 从 `ansible/` 目录跑 |

### 1.2 当前服务形态

```
Open WebUI → host.docker.internal:8081（稳定 API，CIDR 白名单）→ openai-compat-proxy → 127.0.0.1:8082（mainline llama-server，loopback）
```
- systemd：`deepseek-v4-mainline.service`（active + enabled）；独立代理 `deepseek-v4-ik-compat.service`
- 当前模型：`/data/models/DeepSeek-V4-Flash-0731-GGUF/`（UD-Q3_K_M 四分片 + Q8_0 drafter）
- 当前 runtime：mainline llama.cpp `10bf611e`（`/opt/deepseek-v4-mainline/src/build/bin/llama-server`）
- ik `deepseek-v4-ik.service` 当前 inactive，完整保留；仅在用户明确要求时人工切回，部署失败不会自动切回。
- 这是 homelab 快速验证环境，不建立 candidate/promotion/soak 框架。mainline 使用独立 role、Compose project 和 systemd unit，但切换后直接接管现有 loopback backend `8082`。
- 不要为了 mainline 改造 `deepseek-v4-ik` role。mainline 启动或最小 smoke 失败时保留现场，直接检查错误并继续修复。

### 1.3 关键路径（guest 上）

| 路径 | 内容 |
|---|---|
| `/data/models/DeepSeek-V4-Flash-GGUF/` | 保留的 ik 模型（sokann，当前未运行） |
| `/data/models/DeepSeek-V4-Flash-0731-GGUF/` | **新模型**（unsloth UD-Q3_K_M 4 分片 + drafter，已 sha256 验证 ✅） |
| `/opt/deepseek-v4-ik/` | 保留的 ik runtime（src/build，当前未运行） |
| `/opt/deepseek-v4-mainline/` | **新 mainline runtime**（src/build/bin/llama-server，已编译 ✅） |
| `/var/lib/deepseek-v4-ik/evidence/` | 证据目录（不可覆盖，按 experiment-id 建子目录） |
| `/tmp/0731-sha256.log`、`/tmp/mainline-build.log` | 下载校验/编译日志 |

---

## 2. 当前状态总览

| 项 | 状态 |
|---|---|
| 0731 模型下载（138.97GB，5 文件） | ✅ 完成，**SHA-256 5/5 全部通过**（§3.3 清单） |
| mainline llama-server 编译 | ✅ 完成，git HEAD=`10bf611e`（=pin），容器内运行验证通过 |
| P1：PCIe 维护窗口 | ✅ 物理完成 + 复核：GPU0 Gen3×16 / **GPU1 Gen3×8（卡的问题，未解决）** |
| P2/P3：P2P / graph split | ❌ **永久阻塞**（P2P=NS，不同 root port），已从路线图移除 |
| R6：prompt-cache 保存阻塞 /health | ⚠️ checkpoint=8 缓解（72s→22–28s）但**未解决**（同步保存根本问题） |
| Stage 2：mainline + DSpark 切换 | ✅ 已部署；health/chat 与 1K/8K 快速基准完成（见 §3.5、§5） |
| P1：当前 PCIe 拓扑性能基准 | ✅ 已由 mainline `n_max=1/2` 的同 corpus 1K/8K 基准覆盖 |
| `--override-tensor` 精准放置 | ✅ 已探索并**采用**：blk.40–42 路由专家 → CUDA1，8K decode +7.8%（§3.6）；追加 blk.0 → CUDA0 已测并回退（§3.7） |
| 部署耗时 | ✅ 模型校验默认降为大小比对，一次参数重部署由约 15 分钟降到约 5 分钟（§5.2） |
| **NUMA 内存放置** | ✅ **本轮最大收益**：`numactl --interleave=all` + `numa_balancing=0` + `threads=16`（§3.9） |
| 显存占用拆解 | ✅ 已用 `-lv 5` 取得权威数字；KV 仅 3.7 GiB，DSpark 占 15.2 GiB（§3.10） |
| 瓶颈归因 | ✅ 实测机器带宽 80 GB/s、推理仅用 27%；**受限于每层延迟而非带宽**（§3.11） |
| DSpark `n_max` 调优 | ✅ `n_max=2` 最优（1K +5.8%、8K +4.0%）；3 转负（§3.12） |
| 当前推荐参数 | ✅ mainline + DSpark `n_max=2` + `-ot` 规则 + §3.9 三项。**不要**再试：更多线程、更快解码格式、补内存条、KV 量化（§3.11 均已证伪） |

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
- **运行要点**：二进制 rpath 是容器路径，且依赖 `libnccl.so.2`（宿主机没有）→ **必须在容器内运行**。当前 Compose 用 CDI 映射 `nvidia.com/gpu=0/1`，并设置 `LD_LIBRARY_PATH=/build`；构建验证脚本使用 `--gpus all`。构建脚本：`scripts/deepseek-v4-mainline-build.sh`。
- 可选优化：`-DGGML_NCCL=OFF` 重建可消除 NCCL 依赖（本机 layer split 用不到 NCCL）；多卡如需可调 `GGML_SCHED_MAX_SPLIT_INPUTS`（当前不用）。

### 3.5 mainline + DSpark 快速基准（2026-08-17）

同一 `benchmark-runner.py`、cold-prefill、每档 3 样本中位；已依次实测 DSpark `n_max=1` 和 `n_max=2`：

| 指标 | ik 基线 | `n_max=1` | `n_max=2` | `n_max=2` 对 `n_max=1` |
|---|---:|---:|---:|---:|
| 1K decode | 8.05 tok/s | 7.58 tok/s | 7.75 tok/s | +2.3% |
| 1K TTFT | ~22 s | 7.76 s | 7.68 s | -1.1% |
| 1K prefill | ~71 tok/s | 152.64 tok/s | 154.27 tok/s | +1.1% |
| 8K decode | 7.68 tok/s | 7.31 tok/s | 7.11 tok/s | -2.6% |
| 8K TTFT | ~85–113 s | 39.79 s | 40.12 s | +0.8% |
| 8K prefill | ~89 tok/s | 233.66 tok/s | 231.79 tok/s | -0.8% |

`n_max=2` 只在 1K decode 上有小幅收益，8K decode 反而回退，未显示整体优于 `n_max=1`，因此运行参数回调为 `n_max=1`。这里的“不回退”仅指不退回 ik runtime；实验参数可以按结果回调。结果文件：guest `/tmp/mainline-dspark-1k.json`、`/tmp/mainline-dspark-8k.json`、`/tmp/mainline-dspark-nmax2-1k.json`、`/tmp/mainline-dspark-nmax2-8k.json`。

---

### 3.6 `--override-tensor` 精准放置（2026-08-17，已采用）

**先决知识（全部来自 pinned binary 的源码与 GGUF header，不是猜测）**

1. **`--cpu-moe` 只是一条正则规则**：`common/arg.cpp` 把 `\.ffn_(up|down|gate|gate_up)_(ch|)exps` → CPU push 进和 `-ot` **同一个** `tensor_buft_overrides` 向量。
2. **首个命中即生效**：`src/llama-model-loader.cpp` 对每个张量按向量顺序做 `std::regex_search`，命中即 `break`。所以 **`-ot` 必须排在 `--cpu-moe` 之前**，顺序 = 命令行顺序。
3. **buffer type 只接受三个值**：解析器用各 device 的默认 buft 建表，即 `CUDA0`、`CUDA1`、`CPU`（`#define GGML_CUDA_NAME "CUDA"`）。`CUDA_Host` 之类不在表内；写错会打印 Available buffer types 后**在加载模型前**退出。
4. **shared expert 方向无效**：`ffn_*_shexp` 和路由 `ffn_gate_inp` **不匹配** `--cpu-moe` 的正则（要求以 `exps` 结尾），本来就在 GPU 上。对它们加 `-ot ...=CUDA*` 是 no-op。本模型也没有 `_chexps` 张量。
5. **层→设备归属**（`src/llama-model.cpp` 默认按加载时空闲显存分割，两卡等量）：`n_layer=43`、`ngl=100` → **blk.0–21 属 CUDA0，blk.22–42 + output 属 CUDA1**。`-ot` 的目标设备必须与该层归属一致，否则每 token 多出跨卡搬运（无 P2P，要绕 host）。
6. **drafter 不继承主模型的 `-ot`**（`common_base_params_to_speculative` 只复制 `params_spec.tensor_buft_overrides`），单变量干净。但 drafter 在主模型**之后**加载且 `tensor_split` 未设，所以它按"此刻的空闲显存"分割——主模型多占 CUDA1 会把 drafter 的层推向 CUDA0（实测 GPU0 +3.3GiB）。做显存预算时必须算上这个二阶效应。

**真实张量名与尺寸**（用 stdlib-only 脚本读 GGUF header 取得，guest 无 numpy 且禁止装包）：

| 张量 | 量化 | 每层 | 说明 |
|---|---|---:|---|
| `blk.{0..42}.ffn_down_exps.weight` | MXFP4 | 1088 MiB | 路由专家，`--cpu-moe` 命中 |
| `blk.{0..42}.ffn_gate_exps.weight` | IQ3_XXS | 784 MiB | 同上（blk.26 为 MXFP4 1088 MiB） |
| `blk.{0..42}.ffn_up_exps.weight` | IQ3_XXS | 784 MiB | 同上（blk.26 同） |
| `blk.{0..42}.ffn_{down,gate,up}_shexp.weight` | Q8_0 | 各 8.5 MiB | **不**命中，已在 GPU |
| `blk.{0..42}.ffn_gate_inp.weight` | BF16 | 2 MiB | **不**命中，已在 GPU |

`expert_count=256`、`expert_used_count=6` → 每层每 token 实际只读 6/256 ≈ 62 MiB，全 43 层 ≈ 2.6 GiB/token。命中 `--cpu-moe` 的共 129 个张量、112.12 GiB。

**采用的规则**（单变量，其余参数不变）：

```
--override-tensor 'blk\.(40|41|42)\.ffn_(down|gate|up)_exps=CUDA1'
```

恰好命中 9 个张量、7968 MiB（占专家权重 6.94%）。选尾部三层是因为它们的 attn/norm/shexp 本就在 CUDA1，顺带消除了每层每 token 的 GPU→CPU→GPU 往返。

**结果**（同 `benchmark-runner.py`、同 `benchmark-corpus-v1.json`、cold-prefill、每档 3 样本）：

| 指标 | control（`n_max=1`） | `-ot` blk.40–42 | 变化 |
|---|---:|---:|---:|
| 1K decode | 7.577 tok/s | 7.541 tok/s | -0.5% |
| 1K TTFT | 7.76 s | 7.70 s | -0.8% |
| 1K prefill | 152.64 tok/s | 154.06 tok/s | +0.9% |
| **8K decode** | **7.305 tok/s** | **7.873 tok/s** | **+7.8%** |
| 8K TTFT | 39.79 s | 38.93 s | -2.2% |
| 8K prefill | 233.66 tok/s | 239.06 tok/s | +2.3% |

判定依据不只是中位数：8K 实验三样本 **7.695 / 7.873 / 7.957**，最小值都高于 control 三样本的最大值（7.525），两组完全不重叠；1K 两组重叠（实验 7.538/7.674/7.541 vs control 6.938/7.577/7.799），判无变化。8K decode 已超过 ik 基线 7.68。

健康性：RestartCount=0、OOMKilled=false、容器日志 0 条 CUDA/OOM 错误、DSpark 接受率 0.70–0.79、`--tags verify` 全过。峰值显存 GPU0 20058 MiB / GPU1 20464 MiB（各余约 4.1–4.5 GiB）。

结果文件：guest `/tmp/mainline-ot40-42-1k.json`、`/tmp/mainline-ot40-42-8k.json`。

**已知残余不确定性**：control 数据取自重启前的容器实例，因此"重启本身带来的运气"（NUMA/内存布局）未被单独排除。若要更强证据，可把 `deepseek_v4_mainline_tensor_overrides` 置空重新部署再测一轮 8K。GPU1 目前是 Gen3×8，结论只代表当前拓扑。

### 3.7 追加规则 blk.0 → CUDA0（2026-08-17，已测并**回退**）

在 §3.6 基础上追加第二条规则 `blk\.0\.ffn_(down|gate|up)_exps=CUDA0`（+2656 MiB，累计移出 10624 MiB / 9.25%）。**结论：回退**。

| 指标 | blk.40–42（保留） | 追加 blk.0（回退） |
|---|---:|---:|
| 8K decode 中位（冷样本） | 7.873 | 7.771 |
| 8K decode 冷样本跨度 | **0.26** | **1.46** |
| 1K decode | 7.541 | 7.699 |
| 8K TTFT | 38.93 s | 37.91 s |
| 8K prefill | 239.06 | 245.30 |
| GPU0 峰值余量 | 4518 MiB | **1866 MiB** |

8K 冷样本（6 个）：6.697 / 7.416 / 7.606 / 7.936 / 8.126 / 8.156。即使剔除 6.697 这个离群值也没有超过 blk.40–42，而离散度是它的 5 倍。

回退理由：decode（尤其 8K）是本轮主指标；1866 MiB 余量配 `--fit off`，未来任何加载期变化（更长 context、不同 batch）都会直接 OOM。1K decode、TTFT 和 prefill 确实各有 2–3% 的一致改善，如果后续把优化目标改成 prefill/TTFT，可以重新考虑这条规则——但要先解决 GPU0 余量问题。

**二阶效应的实测修正**：§3.6 第 6 条预期"往 CUDA0 加载荷会把 drafter 推回 CUDA1"，实测并非如此——GPU0 +2502 MiB、GPU1 −140 MiB，drafter 基本没动。drafter 的重分布不是对称的，做显存预算时**必须实测，不能按上一次的比例外推**。

### 3.8 基准方法陷阱：`--cold-prefill` 的 nonce 是确定性的

`benchmark-runner.py` 的 nonce 是 `sha256(f"{case_id}:{sample_index}:{seed}")`，**只保证单次运行内各样本互不命中**。跨运行用同样的 case/seed/样本数重跑，prompt 完全相同 → 全部命中 prompt cache，TTFT 从 38 s 掉到 0.8 s、prefill 从 239 掉到 9 tok/s，decode 也偏高，数据不可与冷启动结果比较。

判别方法：8K 样本 TTFT <10 s 即为缓存命中。想在**同一容器实例**内取得新的冷样本，用更大的 `--repeat-samples`（新下标产生新 nonce）再只取新下标的样本，或重启服务清空缓存。

§3.6 和 §3.7 的跨配置对比都是重新部署后在空缓存上跑的（TTFT 38–40 s），结论不受此影响。

### 3.9 NUMA 内存放置 + 线程数（2026-08-17，本轮最大收益）

**起因**：把显存占用拆解清楚后（§3.10）发现，decode 每 token 从主存读约 2.5 GiB 专家权重、实测 7.87 tok/s → 有效带宽仅约 **20 GB/s**，而宿主是双路 E5-2686 v4、四通道 DDR4，理论值 100+ GB/s。差了 5 倍。

**根因**：`/proc/<pid>/numa_maps` 显示 105 GiB 常驻内存 **74% 落在 node1、26% 在 node0**。`--no-mmap` 下模型由 `cudaHostAlloc` 分配页锁定内存，页归属遵循 first-touch，于是绝大部分落在加载线程所在的节点。结果是 node1 的内存控制器扛下四分之三流量，node0 的大半闲置——双路机器被压到接近单路带宽。

**注意**：guest 的 NUMA **拓扑本身是正确的**（2 节点，node0=CPU 0-17、node1=CPU 18-35，距离 10/20），尽管 ESXi 上 VM 配的是 cores-per-socket=1 / sockets=36。ESXi 6.5+ 的 vNUMA 自动计算，与 cores-per-socket 无关，**不需要改成 2×18**。问题在放置，不在拓扑。

**三项修复与实测**（同 corpus、cold-prefill、每档 3 样本中位）：

| 配置 | 1K decode | 8K decode |
|---|---:|---:|
| `-ot` blk.40–42（§3.6 终点），threads=32 | 7.541 | 7.873 |
| + `numactl --interleave=all` | 8.303 | 8.635 |
| + `kernel.numa_balancing=0` | 8.710 | 8.269 |
| **+ `--threads 16`（当前默认）** | **8.941** | **8.577** |
| 相对 §3.6 终点 | **+18.6%** | **+8.9%** |
| 相对最初 control | **+18.0%** | **+17.4%** |

要点：

1. `numactl --interleave=all` 把落点从 74/26 改善到 **60/40**，没有到 50/50——`cudaHostAlloc` 的一部分内存由 CUDA 驱动按 GPU 亲和性就近放置，不完全受 mempolicy 管辖。**剩余空间仍可挖**。
2. `--numa distribute` **确实**会绑定计算线程（17 个到 node0、18 个到 node1），早前"没有绑定"的观察是空闲时采样、线程池未起来所致。
3. **线程数与内存格局耦合**：NUMA 修复前 threads=16 是 1K 赢 8K 输；修复后两档都赢。decode 是带宽受限而非计算受限，线程越多在失衡的内存子系统上争抢越严重——历史上"36 比 32 差"由此得到统一解释。计划文档曾把 `threads=32` 列为"已收敛、不再折腾"，**该结论作废**（它当初只和 36 比过，从未向下扫描）。
4. `numa_balancing=0` 单独看在 8K 上是负的（8.635 → 8.269），但叠加 threads=16 后 8K 回到 8.577。**未测组合**：`interleave` + threads=16 但不关 numa_balancing，其 8K 可能更高。

**成本**：不占显存、不改任何推理参数、不动硬件。`numactl` 由固定 runtime image 自带；sysctl 写在 `/etc/sysctl.d/99-deepseek-v4-mainline.conf`，重启存活。

### 3.11 瓶颈归因：不是带宽，是每层延迟（2026-08-18）

在宿主机上用一个 stdlib/OpenMP 的小基准（`gcc -O3 -march=native -fopenmp`，源码见
`/tmp/membw.c`，未在宿主机安装任何软件包）实测内存读带宽：

| 策略 | 带宽 |
|---|---:|
| 双节点交错（推理实际使用） | **80.6 GB/s**（4 次重复 79.6–81.8） |
| 单节点本地（node0 CPU + node0 内存） | 46.4 GB/s |
| 纯远程跨 QPI | 29.7 GB/s |
| **推理实际达到** | **21.7 GB/s = 27%** |

顺序读与散布 4 MiB 分块读几乎同速（41 vs 45 GB/s 的那组早期数据），说明 MoE 的
gather 访问模式**不是**问题。带宽在 **8 线程即饱和**，与推理里 threads 8≈16≈32 吻合。

**注意一个曾经的误判**：第一次测得 42 GB/s 并据此得出"内存带宽是墙、应补内存条"的
结论，是**错的**——那次测量在模型刚加载完、系统未稳定时进行（15 分钟负载均值 5.55）。
重复 4 次后稳定在 80 GB/s。任何硬件采购建议都必须基于重复测量。

**时间账**（8.94 tok/s 时）：

```
每 token 112 ms ÷ 43 层 = 每层 2.6 ms
其中读 62 MiB 专家权重 @ 80 GB/s = 0.8 ms
剩余 1.8 ms（约 70%）= GPU↔CPU 往返 + 线程池同步
```

结论：decode **受限于 43 层串行链的每层固定开销**，既非带宽也非算力。这解释了：

- 线程越多越慢（每层 CPU 侧工作量小，协调成本超过收益）
- `-ot` 移走 3 层拿到 +7.8%（每层约 +2.3%，因为同时消除了字节**和**往返）
- 单流无法跑满带宽——需要约 3 个 token 的独立工作同时在飞才能填满

**由此作废的方向**：换解码更快的量化格式（非算力受限）、加线程（8 线程已饱和）、
补内存条/换 DDR4-2400（天花板未被触及）。**更小的量化档**收益也从"线性 +33%"
修正为约 **+8%**（字节只占每层时间的 30%），质量代价不值。

### 3.12 DSpark `n_max` 调优（2026-08-18）

§3.11 的归因直接指向投机解码：**验证 k 个 token 时权重只读一次**，几乎不增加那
1.8 ms 固定开销，正好把闲置的 3.7 倍带宽换成速度。

`mean len` 的上限是 `n_max + 1`，所以只有 `n_max` 能突破天花板；`p_min`/`n_min`
只能在天花板下调整接受率。实测：

| `n_max` | 1K decode | 8K decode | mean len | 单 token 接受率 |
|---|---:|---:|---:|---:|
| 1（旧默认） | 8.941 | 8.577 | 1.83 | 0.78 |
| **2（当前）** | **9.459** | **8.916** | **2.3** | 0.65 |
| 3 | 8.149 | 8.748 | 2.6 | 0.53 |

`n_max=2` 相对 1：**1K +5.8%、8K +4.0%**，两档样本均不重叠。`n_max=3` 转负——
`mean len` 仍在涨，但草稿模型要多跑一次自己的 3 层前向，而第三个草稿 token 近半
被拒，成本超过收益。

**重要**：`n_max=2` 在 §3.5 曾被测为"略差"并回调，那是 NUMA 还坏着、每层时间构成
完全不同的时候。修好 NUMA 后固定开销占比上升，投机解码的性价比随之提高。
**参数的最优值依赖于其它参数所处的状态，环境变了要重测。**

### 3.10 显存占用拆解（2026-08-17）

用 `-lv 5` 跑一次加载取得权威数字（该开关是 `deepseek_v4_mainline_log_verbosity`，默认关闭，**不要常开**，它对每个请求都打 debug）。单位 MiB：

| 组成 | CUDA0 | CUDA1 |
|---|---:|---:|
| 主模型权重 | 3311 | 11566 |
| **drafter 权重** | **10209** | 178 |
| 主模型 KV cache | 1838 | 1989 |
| 主模型 compute buffer | 2813 | 1329 |
| drafter compute buffer | 1096 | 3633 |
| CUDA context / 分配器开销 | ~600 | ~1600 |
| nvidia-smi 实测 | 19886 | 20310 |

另有 107262 MiB 专家权重在 `CUDA_Host`（页锁定主存，**不是普通 CPU 内存**——loader 对 CPU override 会从 CPU buft 列表挑 extra 类型）。

由此确立的三件事：

1. **KV cache 只有 3.7 GiB**，因为 43 层**全部是 SWA（窗口 128）**，不随 128K 上下文线性增长。"量化 KV / 降 ctx 腾显存"这个方向基本无效，最多省 1.8 GiB。
2. **DSpark 总成本约 15.2 GiB**（drafter 权重 10.4 + compute buffer 4.7），占在用显存的 38%，且权重几乎全压在 CUDA0 上。这解释了为什么 §3.7 往 CUDA0 加载荷时余量那么紧。
3. **但不要动 DSpark**：drafter 权重 94% 是专家（9792 MiB / 3 层）。若用 `--cpu-moe-draft` 挪到主存，释放 9.5 GiB 可多放 3 层主模型专家（每 token 少读 186 MiB），但 drafter 自己每 token 要读 6/256 × 9792 = **229 MiB**，**净增 43 MiB/token，反而更慢**。而 DSpark 当前接受率 0.70–0.79、mean len 1.83，收益远大于这点显存。此路分析上即可否决，无需实验。

### 3.13 `ngram-mod` 投机（2026-08-18，已测并**否决**）

`--spec-type ngram-mod,draft-dspark`（外加 `--spec-ngram-mod-n-match 24
--spec-ngram-mod-n-min 48 --spec-ngram-mod-n-max 64`）。设想是命中重复上下文时
提交 48–64 token 长块、未命中回落 DSpark，因此"最坏也就是持平"。

**实测是明确回退**：1K decode 9.459 → 8.069（−14.7%），8K 8.916 → 7.271
（−18.4%，三样本 7.139/7.271/7.519 与原组完全不重叠）。

结论：n-gram 查找与回落路径**不是零开销旁路**，未命中时要付真实代价。只有输出
大量引用输入的负载（代码改写、摘要、逐字引用）才可能回本，开放式对话不要开。
参数已保留在 role 里（`deepseek_v4_mainline_spec_types`，默认 `draft-dspark`），
注释记录了数字，避免重复试。

### 3.14 待办：MoE expert cache（未实施，Track B）

这是目前已知**唯一可能带来数十个百分点**的方向，机制正对 §3.11 的瓶颈：高频专家
常驻显存，`MUL_MAT_ID` 仍由 CPU 主持，CPU 算 miss 行的同时 CUDA 算 hit 行，形成
真正的 CPU/GPU 重叠，且不经同步 PCIe 传输（绕开 GPU1 只有 ×8 的限制）。

**来源与实测**（已核对原文，非二手转述）：
- 讨论：<https://github.com/ggml-org/llama.cpp/discussions/24528>
- Fork：`leloch/llama.cpp`，分支 `moe-cache-v2-pr`，29 个连续提交
- 报告数字：**DeepSeek-V4-Flash + 投机解码 +37%～+55%**；独立验证者在 3090 配置
  上 +21%～+39%；GLM-5.1 754B +25%
- 主线**没有**该功能（本仓库 pin 的源码全库 grep 无命中），原 PR #24524 已关闭

**运行参数**：`--moe-cache auto|on|off|N`（N = 每卡 MiB，各卡同额、不能分别指定），
等价环境变量 `LLAMA_ARG_MOE_CACHE`。与现有放置共存：`--cpu-moe` 的 CPU 专家成为
cache provider；`-ot` 已静态放到 CUDA1 的 blk.40–42 **不进** cache。显式 `on` 或
数值预算会关闭 weight repacking，因此 miss 路径可能变慢，需要用 `--repack` 单独
隔离该影响。当前余量下建议从 **2048 MiB/卡** 起步，不要直接上 4096。

**主要代价（必须先想清楚）**：该分支基线是上游 `15586e2d`，而本项目 pin 是
`10bf611e`；实测 `git merge-base --is-ancestor` 确认前者是后者祖先，两者之间有
**153 个上游提交**，其中至少 6 个直接涉及投机解码，包括
`spec: enable backend sampling for both dflash & dspark`（#26958）和
`spec : auto-detect mtp draft model type`（#27005）。切到该分支等于放弃这些
DSpark 相关修复——而 DSpark 正是 §3.12 拿到 +5.8% 的地方。

**因此不要"直接换 pin"**。正确做法是**保留现有二进制，另建第二套 llama-server 做
同机 A/B**，比较"旧基线 + expert cache"与"新基线 + 无 cache"，再决定是否值得
forward-port。

**正确性风险**（改动 28 文件 / +6814 行，风险不是数值误差而是生命周期）：
cache 失效协议漏路径会产生旧权重或 UAF；CUDA dispatch 失败时 CPU 必须重算所有被
跳过的 hit 行；session enter/leave 必须在所有错误路径成对执行。验证至少要覆盖：
分支自带 `ctest`、固定 seed greedy 的 logits/token 对比、perplexity 与长上下文
retrieval、DSpark verification batch、target/drafter 反复创建销毁、server
sleep/wake 与模型 reload、故意压显存验证 OOM/trim 回落 CPU。日志必须看到 cache
激活且 hits 非零、failures 为零——"分配了显存"不等于在工作。

**回退**：一级 `--moe-cache off --repack on`（同一二进制）；二级切回 `10bf611e`
原始二进制。cache 不改 GGUF 或 KV 格式，无数据迁移。

**此项需要用户明确批准**（runtime pin/构建变更），且建议单独立项，不要与参数调优
混在同一轮。

---

## 4. 已做的决定（不要推翻，除非有强证据）

1. **B 路线**：0731 + DSpark（放弃 Preview + NextN-MTP 路线 A）——agentic 质量提升是主要收益；官方 GPU-heavy 环境的 decode ~1.8× **未在本机 CPU-MoE 上兑现**。
2. **量化档**：`UD-Q3_K_M`（~128GB，4 分片）；**drafter**：`Q8_0`（10.9GB）。
3. **runtime**：mainline llama.cpp（pin `10bf611e`）。
4. 其它低成本杠杆（cache 16/32GiB、n-cpu-moe 42、checkpoint=8 等）已测，均未达 10% 推广线——按规则不推广，**不要重复测**。
5. `n_max=1/2` 已测，采用 `1`；禁止把”不退回 ik”误解成”实验参数不能回调”。
6. `-ot blk\.(40|41|42)\.ffn_(down|gate|up)_exps=CUDA1` 已测并**采用**（§3.6）。shared expert / 路由方向已证实是 no-op，不要再试。

---

## 5. Stage 2：快速切换到 mainline + DSpark（已完成）

本阶段只做快速部署与最小验证，不建立 candidate、watchdog、soak、A/B runner 或 promotion 框架。新入口是 `ansible/playbooks/deploy-deepseek-v4-mainline.yml`；它不会修改 ik role、兼容代理或 Open WebUI。

### 5.1 本地语法检查

```bash
cd ansible
ansible-playbook playbooks/deploy-deepseek-v4-mainline.yml --syntax-check
```

### 5.2 切换命令（2026-08-17 已执行成功）

```bash
cd ansible
ansible-playbook playbooks/deploy-deepseek-v4-mainline.yml
```

流程固定为：

1. 在停止 ik 前校验 mainline git HEAD、binary SHA-256、固定 runtime image，以及五个模型文件；任一不符立即失败，ik 保持运行。模型这一步默认只比对**文件大小**（`deepseek_v4_mainline_verify_model_checksums: false`）——138GB 全量哈希要约 7 分钟，会主导一次纯参数重部署，而大小检查同样能拦住文件缺失/截断。**模型文件本身变更或重新同步后，必须把该开关翻回 `true` 跑一次。**
2. 渲染独立 `deepseek-v4-mainline` Compose project 与 systemd unit。
3. 停止并禁用 `deepseek-v4-ik.service`，启动并启用 `deepseek-v4-mainline.service`，由 mainline 直接接管 `127.0.0.1:8082`。
4. 等待 backend `8082/health` 和稳定入口 `8081/health`，再通过 `8081` 发送一次 `temperature=0`、`seed=42`、要求只回复 `OK` 的固定 chat。
5. 启动或 smoke 失败时不自动恢复 ik；保留 mainline 配置与日志，检查错误并继续修复直到成功。

只做只读复核时：

```bash
cd ansible
ansible-playbook playbooks/deploy-deepseek-v4-mainline.yml --tags verify
```

### 5.3 已固定的运行要点

- 容器使用两张 GPU，binary 目录只读挂载到 `/build`，`LD_LIBRARY_PATH=/build`；
- 模型目录只读挂载；`--model` 只指向第一个分片，由 llama.cpp 自动加载其余分片；
- Q8_0 drafter 固定使用 `--spec-type draft-dspark --spec-draft-n-max 1 --fit off`；
- `deepseek_v4_mainline_tensor_overrides` 默认渲染出一条 `--override-tensor`，位置在 `--cpu-moe` **之前**（§3.6）；置空即回到全 CPU-MoE；
- 模型加载约 130GB，首次健康检查按最长 20 分钟等待；
- ik runtime 和模型保留、不删除，仅作为人工回退备份；部署流程不会自动退回 ik。

---

## 6. 接手后的下一步

| 优先级 | 内容 | 最小完成标准 |
|---|---|---|
| **下一步（大）** | **MoE expert cache（§3.14）** —— 唯一已知可能带来数十个百分点的方向，同配置实测 +37%～+55%。需单独立项、需批准构建变更 | 见 §3.14 的验证清单 |
| 下一步（小） | DSpark 的 `p_min`（当前 0.00）和 `n_min`（当前 0）尚未调过。`n_max=2` 下接受率 0.65，`p_min>0` 或可在低置信度时提前放弃、省掉白算的草稿前向 | 同 1K/8K 三样本对照 `n_max=2`；看 `mean len` 与 decode 是否同向 |
| 高价值但需批准 | 并发吞吐测量（服务器已有 4 个 slot）。§3.11 表明带宽闲置 3.7 倍，多路并发应能把总吞吐推到远高于单流；这不改善单条对话延迟，但决定这台机器能否同时服务多 agent | 2/4 路并发的总 tok/s |
| 长期 | 软件预取：让第 N 层计算时预读第 N+1 层专家权重，填满每层 1.8 ms 的空窗（§3.11）。llama.cpp 未实现，需改代码 | — |
| 低优先 | 继续挖 NUMA：落点仍是 60/40 而非 50/50（§3.9 要点 1）；线程数 8–24 细扫（8 与 16 已知打平） | — |
| **已封闭**（不要重试） | `-ot` 的 CUDA0 侧（§3.7 证伪）、shared expert/router（no-op）、`--cpu-moe-draft`（§3.10 否决）、KV 量化（KV 仅 3.7 GiB）、改 ESXi cores-per-socket（vNUMA 本就正确）、开 HT（steal=0 且不缺线程）、加线程（8 线程即饱和）、更快解码的量化格式（非算力受限）、补内存条/换 DDR4-2400（天花板未触及）、`n_max=3`（§3.12 转负）、`ngram-mod`（§3.13 大幅回退） | — |
| 可并行但需维护窗口 | GPU1 ×8：关机、清洁/重插、交换测试 | 达到 Gen3×16，或确认卡 lane 损伤并接受 ×8 |
| 低优先 | 在 mainline 上复现 R6 prompt-cache `/health` 阻塞 | 判断是否仍存在；不要直接沿用 ik 结论 |
| 按需 | 256K/384K 容量 profile | 峰值分配 + recall；不混入速度实验 |
| 长期 | SGLang-KT 重评估 | 3090 阻塞解除或硬件升级后再做 |

`-ot` 的语法、优先级、buffer type 和真实张量名已全部实证并落地，见 §3.6——**不需要再重新发现**。该 binary **没有 `--dry-run` 选项**；改规则前的低成本校验办法是：用 `scripts/gguf-tensor-names.py` 把候选正则跑一遍真实张量名，确认命中数和字节数，再算显存预算（别忘了 drafter 的二阶重分布）。GPU1 仍为 Gen3×8，因此结果只代表当前拓扑；若以后修复到 ×16，再复测胜出候选。

---

## 7. 规则与护栏（必须遵守）

1. **不自动 commit**——完成工作后先问用户「Ready to commit?」；
2. **Ask First**（未经用户同意不做）：实际连接 guest 执行部署、runtime/model pin 变更、改变 `n_max`、删除旧 ik runtime/模型或 service、ESXi/BIOS/PCIe/电源变更、context >128K、并发；
3. 当前是 homelab 快速验证：性能候选默认只做 health/chat + 同 corpus 1K/8K 三样本，不自行扩展成长 soak/完整 production qualification；
4. mainline 失败不自动切回 ik；保留现场并继续排错。实验参数可依据数据回调；
5. ik role、兼容代理和 Open WebUI 不为 mainline 做兼容性改造；
6. 文档/对话中文，代码注释英文，commit 用 Conventional Commits（英文）；
7. Ansible 工作目录 `ansible/`；inventory 由 Terraform state 生成，失效先跑 `scripts/refresh-terraform-state.sh`；
8. 模型/runtime pin 变更必须先验 SHA-256 或 git HEAD；日常参数迭代走默认的大小检查即可（§5.2 第 1 条）。

---

## 8. 遗留问题 / 低优先级项

- [ ] GPU1 ×8（卡 lane 问题，维护窗口处理，不阻塞 DSpark）
- [ ] R6 prompt-cache 同步保存阻塞（checkpoint=8 缓解未根治；候选：cache 策略跳过超大单条 / 保存异步化；新 runtime 上先复现）
- [ ] GPU1 从 ×8 修复到 ×16 后，对 prefill/`override-tensor` 的增量收益未知
- [ ] mainline 可选重建 `-DGGML_NCCL=OFF`（消除 NCCL 依赖）
- [ ] HF 下载限速：guest 上设 `HF_TOKEN`（只读）可提速
- [x] ~~`override-tensor` CLI 语法、真实张量名、buffer type 精确值和首个单变量候选~~ → 全部核实并采用，见 §3.6
- [ ] CUDA0 侧（§3.7）已试并回退；CUDA1 侧还剩 4252 MiB，够再挪一层（见 §6）
- [ ] §3.6 的 control 取自重启前实例，"重启运气"未单独排除；如需更强证据可置空变量重测一轮 8K

---

## 9. 参考资料

- 全景计划：`docs/designs/deepseek-v4-performance-optimization-plan.md`
- 当前部署入口：`ansible/playbooks/deploy-deepseek-v4-mainline.yml`
- 当前参数：`ansible/roles/deepseek-v4-mainline/defaults/main.yml` 与 `templates/docker-compose.yml.j2`
- 学习笔记：`docs/learningnotes/2026-08-14-deepseek-v4-dual-gpu-deployment.md`
- 实验规范：`_bmad-output/implementation-artifacts/spec-deepseek-v4-memory-prefill-experiments.md`
- 研究：`_bmad-output/planning-artifacts/research/technical-deepseek-v4-gguf-memory-and-prefill-optimization-research-2026-08-14.md`
- 构建脚本：`scripts/deepseek-v4-mainline-build.sh`
- GGUF 张量名检查（校验 `-ot` 正则用）：`scripts/gguf-tensor-names.py`
- DSpark/MTP 合并 PR：https://github.com/ggml-org/llama.cpp/pull/25784
- DSpark 实测文章：https://rohitraj.tech/ar/notes/deepseek-dspark-speculative-decoding-llamacpp-2026
- 模型源：https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF
- SGLang-KT 阻塞：issue #1999（3090）、#2118（DSpark 缺失）
- ESXi P2P 参数：https://knowledge.broadcom.com/external/article/312208/vsphere-vmdirectpath-io-and-dynamic-dire.html

> 接手提醒：不要以已完成的 `spec-switch-deepseek-v4-to-mainline-dspark.md` 继续实施；其中可能保留实验过程中的旧参数。先读本文件，再核对 role/defaults 与 guest 实机。
