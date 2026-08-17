# DeepSeek V4 Flash 本地推理优化 —— 项目交接文档（Handoff）

**最后更新/实机核验**：2026-08-17
**用途**：交给接手本项目的 AI/工程师。**只读本文档即可继续工作**，不需要原始对话上下文。
**权威顺序**：当前运行事实以已提交的 `deepseek-v4-mainline` Ansible role 和 guest 实机为准；本文件是操作入口；性能计划只提供背景和后续方向。`_bmad-output/implementation-artifacts/spec-switch-deepseek-v4-to-mainline-dspark.md` 是已完成的历史实施 spec，**不是当前配置来源**。
**关联文档**（细节均在，按需查阅）：
- `docs/designs/deepseek-v4-performance-optimization-plan.md`（全景优化计划，最详细）
- `docs/learningnotes/2026-08-14-deepseek-v4-dual-gpu-deployment.md`（部署与实验纪年）
- `_bmad-output/implementation-artifacts/spec-deepseek-v4-memory-prefill-experiments.md`（实验规范）
- `_bmad-output/planning-artifacts/research/technical-deepseek-v4-gguf-memory-and-prefill-optimization-research-2026-08-14.md`（研究基线）

---

## 0. 一句话现状

homelab 的 DeepSeek V4 Flash（GGUF，双 RTX 3090，CPU-MoE）已切换到 **官方 0731 模型 + DSpark + mainline llama.cpp**，当前固定 `n_max=1`，并已采用一条 `--override-tensor` 规则把尾部三层的路由专家放到 CUDA1（§3.6）。mainline active、ik inactive、稳定 API `8081` 健康、容器 restart=0。8K decode 由 7.31 提升到 **7.87 tok/s（+7.8%）**，已超过 ik 基线 7.68；1K 持平。

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
| `--override-tensor` 精准放置 | ✅ 已探索并**采用**：blk.40–42 路由专家 → CUDA1，8K decode +7.8%（§3.6） |
| 当前推荐参数 | ✅ mainline + DSpark，`n_max=1` + 上述 `-ot` 规则；不要再重复 `n_max` 1/2 对比 |

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

1. 在停止 ik 前校验 mainline git HEAD、binary SHA-256、固定 runtime image，以及四个基座分片和 drafter 的 SHA-256；任一不符立即失败，ik 保持运行。
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
| **下一步** | 把 `-ot` 扩展到 CUDA0 侧：追加 `blk\.(0\|1)\.ffn_(down\|gate\|up)_exps=CUDA0`（blk.0–21 归 CUDA0）。注意 §3.6 第 6 条的二阶效应——主模型多占 CUDA0 会把 drafter 推回 CUDA1，必须先重测峰值显存再定层数 | 与当前 blk.40–42 配置对照，同 1K/8K 三样本；无 OOM/restart；峰值余量 ≥2 GiB |
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
8. 模型/runtime pin 变更必须先验 SHA-256 或 git HEAD。

---

## 8. 遗留问题 / 低优先级项

- [ ] GPU1 ×8（卡 lane 问题，维护窗口处理，不阻塞 DSpark）
- [ ] R6 prompt-cache 同步保存阻塞（checkpoint=8 缓解未根治；候选：cache 策略跳过超大单条 / 保存异步化；新 runtime 上先复现）
- [ ] GPU1 从 ×8 修复到 ×16 后，对 prefill/`override-tensor` 的增量收益未知
- [ ] mainline 可选重建 `-DGGML_NCCL=OFF`（消除 NCCL 依赖）
- [ ] HF 下载限速：guest 上设 `HF_TOKEN`（只读）可提速
- [x] ~~`override-tensor` CLI 语法、真实张量名、buffer type 精确值和首个单变量候选~~ → 全部核实并采用，见 §3.6
- [ ] `-ot` 只用掉 CUDA1 的余量；CUDA0 侧（blk.0–21）尚未试，两卡合计理论上还能再挪约 2–3 层（见 §6）
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
