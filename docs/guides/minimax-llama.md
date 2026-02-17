# MiniMax M2.5 本地部署方案 — ESXi + Dual RTX 3090

## 环境概述

| 项目 | 配置 |
|------|------|
| 宿主机 | Dell T7910 |
| CPU | 2× Intel Xeon E5-2686 v4 (18C/36T × 2 = 72 线程) |
| 内存 | 384 GB DDR4 ECC |
| GPU | 2× NVIDIA RTX 3090 (24 GB VRAM × 2) |
| 虚拟化 | VMware ESXi |
| 目标模型 | MiniMax-M2.5 230B MoE (10B active) |

## 架构选择

推荐方案：**单 VM + GPU Passthrough + CPU-MoE 混合推理**

将两张 3090 直通给一台 Ubuntu VM，注意力层跑 GPU，MoE 专家层卸载到 CPU。这是目前在 48GB 总 VRAM 下运行 230B MoE 模型的最佳实践。

### 推理引擎选型

MiniMax M2.5 官方推荐 [SGLang](https://huggingface.co/MiniMaxAI/MiniMax-M2/blob/main/docs/sglang_deploy_guide.md) 和 [vLLM](https://huggingface.co/MiniMaxAI/MiniMax-M2.5/blob/main/docs/vllm_deploy_guide.md) 作为 serving 引擎。但这两者都要求模型完全驻留在 GPU VRAM 中：

| 引擎 | 最低 GPU 配置 | 权重格式 | CPU offload MoE |
|------|-------------|---------|----------------|
| SGLang | 96GB × 4（384GB VRAM） | BF16（~460GB） | 不支持 |
| vLLM | 96GB × 4（384GB VRAM） | BF16（~460GB） | 不支持 |
| llama.cpp | 任意 GPU + 足够系统内存 | GGUF 量化（Q5 ~162GB） | **支持** |

本方案硬件为 2× RTX 3090（48GB VRAM 总计）+ 280GB 系统内存。SGLang/vLLM 所需 VRAM 是可用量的 8 倍以上，无法使用。

**llama.cpp（[ik_llama.cpp](https://github.com/ikawrakow/ik_llama.cpp) fork）是唯一可行方案**，原因：

1. **GGUF 量化**：将 460GB BF16 权重压缩到 ~162GB（Q5_K_XL），可放入系统内存
2. **CPU-MoE 混合推理**：注意力层 offload 到 GPU 加速，MoE expert 层留在 CPU，充分利用大内存
3. **ik_llama.cpp 优势**：比标准 llama.cpp 有更好的量化内核和 MoE 调度优化

> **如果未来升级到 4× A6000（48GB × 4 = 192GB VRAM）或更高配置**，建议切换到 SGLang/vLLM 以获得更好的吞吐量和 batch 处理能力。

---

## 第一部分：前置条件 & BIOS 设置

### 1.1 BIOS/UEFI 硬性要求

在 Dell T7910 的 BIOS 中确认以下选项全部开启，**缺一不可**：

- **Intel VT-d (Virtualization Technology for Directed I/O)**：GPU Passthrough 的基础。
- **Above 4G Decoding**：双 3090 各 24GB 显存，BAR 空间总和远超 4GB 寻址范围。不开此选项，VMX 中设置的 `pciPassthru.use64bitMMIO` 无法生效，VM 可能无法识别 GPU 或直接启动失败。
- **SR-IOV**（如有此选项）：开启不影响，关闭也不会阻塞消费级 GPU 的 Passthrough。

Dell T7910 BIOS 路径参考：System Setup → Processor Settings → VT-d，以及 Integrated Devices → Above 4G Decoding。

### 1.2 ESXi 主机端设置

SSH 登录 ESXi 后执行：

```bash
# 查看 GPU PCI 设备 ID
lspci | grep -i nvidia

# 记录两张 3090 的 PCI 地址，例如：
# 0000:04:00.0 3D controller: NVIDIA Corporation GA102 [GeForce RTX 3090]
# 0000:41:00.0 3D controller: NVIDIA Corporation GA102 [GeForce RTX 3090]
```

在 ESXi Web UI 中操作：

1. 进入 **Host → Manage → Hardware → PCI Devices**
2. 找到两张 RTX 3090，勾选 **Toggle Passthrough**
3. 重启 ESXi 主机使 Passthrough 生效

### 1.3 ESXi 高级参数（可选优化）

```
# 如果遇到 Passthrough 不稳定，尝试以下设置
esxcli system settings kernel set -s vmdirectpath -v TRUE
```

---

## 第二部分：虚拟机配置

### 2.1 VM 规格建议

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| OS | Ubuntu 22.04 / 24.04 LTS | llama.cpp 兼容性最好 |
| vCPU | 48-56 | 留部分给 ESXi 和其他 VM |
| 内存 | 256-300 GB | 模型 + OS + 余量 |
| 磁盘 | 300 GB+ (SSD/NVMe) | 存放模型文件 |
| NUMA | 开启 NUMA 亲和性 | 性能关键 |

### 2.2 VM 高级配置

编辑 VM 的 `.vmx` 配置，添加以下参数：

```
# GPU Passthrough 相关
pciPassthru0.present = "TRUE"
pciPassthru0.id = "0000:04:00.0"    # 第一张 3090 的 PCI 地址
pciPassthru1.present = "TRUE"
pciPassthru1.id = "0000:41:00.0"    # 第二张 3090 的 PCI 地址

# 内存预留（Passthrough 必需，值必须等于 VM 分配的内存 MB 数）
sched.mem.min = "<VM_MEMORY_MB>"     # 例：280GB → 286720，256GB → 262144
sched.mem.shares = "normal"
mem.hotadd = "FALSE"

# VM 固件类型（推荐 EFI）
firmware = "efi"

# 64-bit MMIO（双 3090 需要大 MMIO 空间）
pciPassthru.use64bitMMIO = "TRUE"
pciPassthru.64bitMMIOSizeGB = "64"    # 若 VM 启动失败或 GPU 识别异常，可上调到 128

# NUMA 优化
numa.autosize.once = "FALSE"
# 注意：不设置 numa.nodeAffinity。
# "0,1" 只表示"允许在两个节点上运行"，并非精细 pinning。
# 真正的 NUMA 优化在 VM 内部通过 numactl --interleave=all 实现（见第五部分）。
```

> **关于 sched.mem.min**：此值必须与 VM 实际分配的内存 MB 数精确一致。如果后续调整 VM 内存，必须同步更新此参数，否则 Passthrough VM 可能无法启动。
>
> **关于 EFI 固件**：双大显存卡 + 64-bit MMIO 场景下，EFI 固件比传统 BIOS 更稳定。如果 VM 已创建为 BIOS 模式，需要重建 VM 并选择 EFI。

### 2.3 内存全量预留 & Hot-Add 关闭（双保险）

GPU Passthrough 要求 VM 内存必须全量预留，否则可能直接无法开机。需要**同时**在 UI 和 VMX 两处设置：

1. **ESXi Web UI**：编辑 VM 设置 → Memory → 勾选 **"Reserve all guest memory (All locked)"**，同时确认 **"Memory Hot Plug"** 为关闭状态
2. **VMX 文件**：确认 `sched.mem.min` 值等于 VM 分配的内存 MB 数，`mem.hotadd = "FALSE"`（如上方配置所示）

UI 和 VMX 两处都设置才是最稳妥的做法。UI 操作可能被意外修改，VMX 是配置文件级别的兜底。

### 2.4 NUMA 分布策略

Dell T7910 双路 CPU，内存通常均匀分布在两个 NUMA 节点。确认 GPU 所在的 PCIe 槽位对应的 NUMA 节点，尽量将 VM 的内存和 vCPU 与 GPU 所在节点对齐：

```bash
# 在 ESXi 上查看 NUMA 拓扑
vsish -e get /hardware/numa/numaInfo
```

---

## 第三部分：VM 内部环境搭建

### 3.1 基础环境

```bash
# 系统更新
sudo apt update && sudo apt upgrade -y

# 安装依赖
sudo apt install -y build-essential cmake git wget curl \
    numactl htop nvtop python3-pip

# 安装 NVIDIA 驱动（方式一：自动检测推荐版本）
sudo apt install -y ubuntu-drivers-common
sudo ubuntu-drivers autoinstall
sudo reboot

# 如果 autoinstall 失败或版本不理想，手动指定（方式二）：
# sudo apt install -y nvidia-driver-550-server
# 如果仓库中没有 550，选择 535 或其他最新的 production 分支即可

# 验证 GPU
nvidia-smi
# 应看到两张 RTX 3090，各 24GB
```

> **关于 CUDA Toolkit**：llama.cpp 编译时需要 CUDA 头文件和 nvcc，因此仍建议安装完整 CUDA Toolkit。但如果只是运行预编译的 llama.cpp，驱动本身就够了。

### 3.2 安装 CUDA Toolkit（推荐 12.8+）

**重要：先装驱动，再装 Toolkit。** NVIDIA 官方 CUDA 安装器可能捆绑驱动依赖，安装过程中会尝试替换已安装的驱动版本。

`cuda-toolkit-12-8` 来自 NVIDIA CUDA APT 仓库，干净的 Ubuntu 系统上默认不包含该仓库。若 `apt install` 提示找不到包，请先按 [NVIDIA 官方安装页](https://developer.nvidia.com/cuda-downloads)（选择 Linux → x86_64 → Ubuntu → deb (network)）添加 repo 和 GPG key，再安装 toolkit 子包。

```bash
# 只安装 toolkit 子包，不装驱动
sudo apt install -y cuda-toolkit-12-8

# 锁住实际安装的驱动包，防止后续 apt upgrade 或 CUDA 依赖反向覆盖
# 先查看实际安装的驱动包名（autoinstall 不一定装的是 550-server）
dpkg -l | grep -E 'nvidia-driver-[0-9]+' | head
# 然后 hold 查到的实际包名，例如：
sudo apt-mark hold nvidia-driver-550

# 验证
nvcc --version
nvidia-smi  # 确认驱动版本没有变化
```

### 3.3 编译 llama.cpp（推荐 ik_llama.cpp）

ik_llama.cpp 的自定义量化和 MoE 优化比标准版更好：

```bash
git clone https://github.com/ikawrakow/ik_llama.cpp
cd ik_llama.cpp

cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CUDA=ON \
    -DGGML_CUDA_F16=ON

cmake --build build --config Release -j $(nproc)
```

如果更偏好标准版：

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp

cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CUDA=ON

cmake --build build --config Release -j $(nproc)
```

> **版本锁定（重要）**：ik_llama.cpp 对 MiniMax M2.5 的支持存在版本敏感性。经验证，**commit `f7923739`**（build 4081）可以正常工作。更新的版本（如 `528cadb0` GLM-5 support）会导致 MoE 推理产生完全不可用的垃圾输出（重复无意义 token）。建议 clone 后立即锁定版本：
>
> ```bash
> git clone https://github.com/ikawrakow/ik_llama.cpp
> cd ik_llama.cpp
> git checkout f7923739  # 已验证可用版本
> ```
>
> 升级前务必在测试环境验证推理输出质量。参考：[ubergarm/MiniMax-M2.5-GGUF#11](https://huggingface.co/ubergarm/MiniMax-M2.5-GGUF/discussions/11)

---

## 第四部分：模型下载与量化选择

### 4.1 量化版本推荐

| 量化 | 大小约 | 质量 | 推荐度 | 说明 |
|------|--------|------|--------|------|
| Q6_K | ~170 GB | 极高 | ★★★★★ | 384GB 内存轻松装下，质量接近 FP16 |
| UD-Q5_K_XL | ~162 GB | 很高 | ★★★★★ | Unsloth 动态量化，关键层保留更高精度 |
| Q5_K_M | ~145 GB | 很高 | ★★★★★ | 标准 Q5 量化，性价比优选 |
| Q4_K_M | ~120 GB | 高 | ★★★★ | 省内存，质量仍然不错 |
| IQ4_NL | ~110 GB | 较高 | ★★★★ | ik_llama.cpp 专属，同大小更好质量 |
| Q3_K_L | ~100 GB | 中等 | ★★★ | 如需更多 context 可选 |

**384GB 内存建议选 UD-Q5_K_XL 或 Q6_K**。UD (Unsloth Dynamic) 量化在关键层使用更高比特，边际层使用更低比特，同等模型大小下质量优于标准均匀量化。

> **注意**：Unsloth 仓库 (`unsloth/MiniMax-M2.5-GGUF`) 不一定包含所有量化变体。下载前建议先在 HuggingFace 仓库页面确认可用的文件列表。

### 4.2 下载模型

```bash
# 安装 hf
pip3 install huggingface_hub

# 推荐 Unsloth 的动态量化版本（UD-Q5_K_XL，5 个分片，~162GB）
hf download unsloth/MiniMax-M2.5-GGUF \
    --local-dir /data/models \
    --include "*UD-Q5_K_XL*"

# 或 ubergarm 的 ik_llama.cpp 优化版本
hf download ubergarm/MiniMax-M2.5-GGUF \
    --local-dir /data/models \
    --include "*IQ5_K*"
```

---

## 第五部分：运行配置

### 5.1 推荐启动命令（Server 模式）

```bash
# 保守配置（跑通验证用）：全 CPU-MoE + KV cache FP16
numactl --interleave=all \
./build/bin/llama-server \
    --model /data/models/UD-Q5_K_XL/MiniMax-M2.5-UD-Q5_K_XL-00001-of-00005.gguf \
    -ngl 999 \
    --cpu-moe \
    --split-mode layer \
    --tensor-split 1,1 \
    --jinja \
    --ctx-size 65536 \
    --cache-type-k f16 \
    --cache-type-v f16 \
    --host 0.0.0.0 \
    --port 8080 \
    --parallel 1 \
    --reasoning-format auto \
    --temp 0.8 \
    --top-p 0.95 \
    --top-k 40
```

```bash
# 调优后配置（推荐）：-ot 6+4 不对称 + graph 模式 + KV cache q8_0 + 线程优化
# 相比保守配置：短 prompt 生成 +78%，长 prompt 生成 +71%
numactl --interleave=all \
./build/bin/llama-server \
    --model /data/models/UD-Q5_K_XL/MiniMax-M2.5-UD-Q5_K_XL-00001-of-00005.gguf \
    -ngl 999 \
    -ot "blk\.(5[1-6])\.ffn_(up|down|gate)_exps\.weight=CUDA0" \
    -ot "blk\.(5[7-9]|60)\.ffn_(up|down|gate)_exps\.weight=CUDA1" \
    -ot "\.ffn_(up|down|gate)_exps\.weight=CPU" \
    --split-mode graph \
    --tensor-split 1,1 \
    --jinja \
    --ctx-size 65536 \
    --cache-type-k q8_0 \
    --cache-type-v q8_0 \
    --threads 20 \
    --threads-batch 36 \
    --host 0.0.0.0 \
    --port 8080 \
    --parallel 1 \
    --reasoning-format auto \
    --temp 0.8 \
    --top-p 0.95 \
    --top-k 40
```

参数说明：

- `-ngl 999`：所有非 MoE 层上 GPU
- `--cpu-moe`（保守）/ `-ot`（调优后）：MoE 专家层的放置策略。`--cpu-moe` 将全部 expert 卸载到 CPU，简单可靠；`-ot` 可以精确控制每层 expert 放在哪个设备上（见 5.2 和 5.4）。**注意**：MiniMax M2.5 的 expert 层只在 blk.0~blk.61，blk.62 是输出层无 expert
- `--split-mode graph`（ik_llama.cpp 特有）：启用张量并行，两张 GPU 同时计算。多轮 benchmark 证明 graph 模式在 short gen（日常交互）上有 6.6% 稳定优势（见 6.6 多轮稳定性分析）。如用标准 llama.cpp 请改为 `layer`
- `--tensor-split 1,1`：两张 3090 规格相同，按 1:1 均分。如果两张卡 VRAM 可用量不同（如一张接了显示器），可调整比例如 `0.8,1`
- `--ctx-size 65536`：64K context，384GB 内存可以支撑。首次验证时可先用 16384 确认链路正常，再拉到此值
- `--cache-type-k q8_0` / `--cache-type-v q8_0`：KV Cache 使用 Q8 量化，VRAM 占用约为 FP16 的一半，质量损失极小。如对长距离召回精度有极高要求，可改回 `f16`
- `--threads 20`：decode 线程数。默认使用全部物理核（本机 36），但实测 20 线程 generation 速度比默认高 16-18%——过多线程引入 NUMA 跨节点访问和同步开销。最优区间 20-24，优先选 20（调度开销更低）
- `--threads-batch 36`：prefill/batch 处理线程数。对 generation 无影响，但影响 prefill 速度。tb=24 会使 prefill 下降 ~18%，tb=32/36 接近。推荐与物理核数一半持平（36）
- `--parallel 1`：单并发槽位。llama-server 会为每个 slot 预分配独立的 KV Cache，在 64K context 下 parallel 2 意味着 KV Cache 占用直接翻倍，内存压力显著增加。单人使用建议从 1 开始（见 5.5 并发配置）
- `--jinja`：启用 Jinja 模板支持（M2.5 的 think 标签需要）
- `--model ... -00001-of-00005.gguf`：显式指向第一个分片文件，llama.cpp 自动加载后续分片
- `--reasoning-format auto`：自动处理 M2.5 的 `<think>` 推理标签，将思维链与最终回答分开
- `numactl --interleave=all`：内存在两个 NUMA 节点间交错分配

> **关于模型路径**：务必指向分片文件的第一个文件（如 `-00001-of-00005.gguf`），不要使用通配符 `*`。llama.cpp 会根据命名规则自动找到后续分片。通配符在 shell 展开后可能传入多个路径参数导致不可预期行为。
>
> **关于多 GPU 切分**：多 GPU 的默认切分行为可能随 llama.cpp 版本变化。为了可复现性，建议始终显式指定 `--split-mode` 和 `--tensor-split`。启动后务必检查 llama-server 的启动日志和 `nvidia-smi`，确认最终的层分配和 VRAM 占用符合预期。
>
> **关于 `--flash-attn` 和 `--fit on`**：ik_llama.cpp 已默认启用 Flash Attention，无需手动指定 `--flash-attn`。`--fit on` 在当前版本（2025 年初）不是有效参数，已从命令中移除。如未来版本重新引入，可视需要添加。

### 5.2 MoE 卸载进阶调优

`--cpu-moe` 是将所有专家层全量卸载到 CPU 的简单开关。跑通之后有两种方式做更精细的控制：

#### 方式一：`--n-cpu-moe N`（简单但多 GPU 下不均匀）

指定前 N 层的专家放在 CPU，剩余的留在 GPU：

```bash
# 63 层中 57 层专家放 CPU，6 层留 GPU
--n-cpu-moe 57
```

调参策略：从大值开始（如 58），逐步减小直到 VRAM 接近上限。留在 GPU 上的专家层越多，生成速度越快。

> **多 GPU 已知问题**：`--n-cpu-moe` 在多 GPU 环境下不会均匀分配 expert 层（[ggml-org/llama.cpp#15136](https://github.com/ggml-org/llama.cpp/issues/15136)），会将 GPU expert 全部堆积到一张卡上，导致一卡满载另一卡闲置。**多 GPU 环境推荐使用 `-ot`（方式二）。**

#### 方式二：`-ot`（Override Tensor，推荐多 GPU 使用）

使用正则表达式精确控制每个张量的放置设备。可以多次指定，按顺序匹配（先匹配先生效）：

```bash
# 层 56-58 expert → CUDA0，层 59-61 expert → CUDA1，其余 expert → CPU
# 注意：M2.5 的 expert 层只到 blk.61，blk.62 是输出层无 expert
-ot "blk\.(5[6-8])\.ffn_(up|down|gate)_exps\.weight=CUDA0" \
-ot "blk\.(59|6[01])\.ffn_(up|down|gate)_exps\.weight=CUDA1" \
-ot "\.ffn_(up|down|gate)_exps\.weight=CPU"
```

优势：
- 解决 `--n-cpu-moe` 的多 GPU 不均匀分配问题
- 可以精确控制每一层 expert 放在哪张 GPU 上
- 与 `--split-mode graph` 配合效果最好

调参策略：先用上述模板跑通，然后逐步增加分配给 GPU 的层数（每次加 1 层），同时注意两卡 VRAM 均匀。每层 expert 约占 2.4 GB VRAM。

> **重要**：MiniMax M2.5 共 63 层（blk.0 ~ blk.62），但 expert 张量（`ffn_*_exps`）只存在于 blk.0 ~ blk.61。blk.62 是输出层，不包含 expert。写正则时不要覆盖到 blk.62，否则实际生效的 GPU 层数会少于预期。

### 5.3 替代方案：纯 CLI 交互

```bash
numactl --interleave=all \
./build/bin/llama-cli \
    --model /data/models/UD-Q5_K_XL/MiniMax-M2.5-UD-Q5_K_XL-00001-of-00005.gguf \
    -ngl 999 \
    --cpu-moe \
    --split-mode layer \
    --tensor-split 1,1 \
    --jinja \
    --ctx-size 65536 \
    --cache-type-k f16 \
    --cache-type-v f16 \
    --temp 1.0 \
    --top-p 0.95 \
    --top-k 40 \
    -cnv
```

### 5.4 高级：自定义层分配（ik_llama.cpp）

如果想更精细控制哪些层放 GPU、哪些放 CPU：

```bash
# 注意力层放 GPU（高精度），专家层放 CPU（适度压缩）
# 使用 -ot 参数精确控制
numactl --interleave=all \
./build/bin/llama-server \
    --model ./model.gguf \
    -ngl 999 \
    -ot ".ffn_.*_exps.=CPU" \
    --jinja \
    --ctx-size 65536 \
    --host 0.0.0.0 \
    --port 8080
```

> **`-ot` vs `--n-cpu-moe`**：`-ot` 是 ik_llama.cpp 的正则匹配方式，灵活但容易写错；`--n-cpu-moe` 是标准 llama.cpp 的参数，更直观。建议优先用 `--n-cpu-moe`，只在需要"注意力层和专家层使用不同量化精度"时才动 `-ot`。

### 5.5 并发配置：`--parallel`

llama-server 会为每个并发 slot 预分配独立的 KV Cache。这意味着 `--parallel N` 在大 context 下的内存占用会近似按 N 倍增长：

| parallel | ctx-size | KV Cache 占用 (FP16 估算) |
|----------|----------|--------------------------|
| 1 | 65536 | ~15-25 GB |
| 2 | 65536 | ~30-50 GB |
| 1 | 131072 | ~30-50 GB |
| 2 | 131072 | ~60-100 GB |

**默认配置建议 `--parallel 1`**（本文档所有命令已更新为此值），64K context 下单 slot 的内存占用可控，单人交互体验最优。

如果需要多用户或多 tab 并发访问，可以在验证内存余量充足后提升：

```bash
# 并发版：建议先用较小 context 验证内存占用
numactl --interleave=all \
./build/bin/llama-server \
    --model /data/models/UD-Q5_K_XL/MiniMax-M2.5-UD-Q5_K_XL-00001-of-00005.gguf \
    -ngl 999 \
    --cpu-moe \
    --split-mode layer \
    --tensor-split 1,1 \
    --jinja \
    --ctx-size 32768 \
    --cache-type-k f16 \
    --cache-type-v f16 \
    --host 0.0.0.0 \
    --port 8080 \
    --parallel 2
```

> **并发 + 大 context 注意事项**：如果同时需要 parallel 2 和 64K+ context，请先用 `nvidia-smi` 和 `htop` 确认 VRAM 和系统内存是否扛得住双份 KV Cache。384GB 内存在 UD-Q5_K_XL + 64K + parallel 2 的组合下可能仍然够用，但余量会比较紧。如果内存吃紧，可以将 KV Cache 降级到 Q8（`--cache-type-k q8_0 --cache-type-v q8_0`）来腾出空间。

### 5.6 M2.5 推理模式（Think Mode）

MiniMax M2.5 支持"推理模式"（Think Mode），类似于 Claude 的 extended thinking。模型会在 `<think>...</think>` 标签内生成推理链（chain-of-thought），然后在标签外给出最终回答。

**服务端配置**：`--reasoning-format auto` 参数（已包含在本文档所有启动命令中）让 llama-server 自动检测和处理 `<think>` 标签：

- 推理链内容会被提取到 API 响应的 `reasoning_content` 字段
- 最终回答保留在 `content` 字段
- 客户端无需自行解析 `<think>` 标签

**API 响应格式示例**：

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "最终回答内容",
      "reasoning_content": "模型的推理过程（原 <think> 标签内的内容）"
    }
  }]
}
```

**客户端适配注意**：

| 客户端 | 支持情况 |
|--------|---------|
| Open WebUI | 原生支持 `reasoning_content` 字段，推理过程会以折叠面板显示 |
| OpenAI Python SDK | `message.reasoning_content` 字段可能存在，客户端应防御性读取（取决于 SDK 版本和 chat template） |
| 不支持的客户端 | 推理链可能直接包含在 `content` 中（带原始 `<think>` 标签），需手动解析或忽略 |

**关于推理模式的行为**：

- 模型自行决定是否启用推理链——简单问题可能直接回答，复杂问题会先思考再回答
- 推理链的 `<think>` tokens 会消耗生成预算、KV Cache 和 context window 容量（与普通输出 token 相同），服务端只是将其提取到单独字段，并不节省资源
- 如果不需要推理模式，可将 `--reasoning-format` 改为 `none`，但一般建议保持 `auto`

---

## 第六部分：性能预期与调优

### 6.1 预期性能

| 指标 | 预估值 (64K context) |
|------|--------|
| Prompt 处理速度 | 10-25 tokens/s |
| 生成速度 | 5-10 tokens/s |
| 首字延迟 (TTFT) | 3-10 秒（视 prompt 长度） |
| VRAM 占用 | ~25-35 GB（注意力层 + KV cache） |
| 系统内存占用 | 170-200 GB（Q5_K_M 模型 + KV cache FP16） |

瓶颈分析：生成速度主要受限于 CPU 内存带宽。DDR4 四通道双路理论带宽约 170 GB/s，但实际有效带宽会受 NUMA 拓扑和 VM 虚拟化开销影响。

### 6.2 Context Window 深度分析

#### 内存预算

以 VM 分配 280GB 内存、UD-Q5_K_XL 量化为例：

| 用途 | 占用 |
|------|------|
| 模型权重 (UD-Q5_K_XL) | ~162 GB |
| OS + llama.cpp + 运行时开销 | ~10 GB |
| **可用于 KV Cache** | **~108 GB** |

M2.5 采用 MoE 架构，MoE 的影响主要体现在专家权重的存放位置与 CPU 内存带宽瓶颈上。KV Cache 占用则取决于注意力层的结构参数（n_layers、n_heads、head_dim、GQA/MQA 的 kv_heads 数量）与 context 大小，随 ctx-size 近似线性增长，与 MoE 的"230B 总参数 / 10B 激活"无直接关系。

以下为经验估算区间，**实际占用以 llama-server 启动日志和 `nvidia-smi` / `htop` 实测为准**：

| Context Size | KV Cache 占用 (FP16) | 是否可行 |
|-------------|---------------------|----------|
| 16,384 (16K) | ~4-6 GB | 轻松 |
| 65,536 (64K) | ~15-25 GB | 推荐日常使用 |
| 131,072 (128K) | ~30-50 GB | 可行，仍有余量 |
| 196,608 (196K, 官方标称上限) | ~45-75 GB | 接近可用上限，需实测确认 |

> 以上数值为经验区间。KV Cache 实际占用取决于模型的 GQA group 数量、kv_heads、head_dim 等参数，不同量化方式也会影响。务必以实际运行时观测为准。196K 上限来自 MiniMax 部署指南生态的公开标注（vLLM MiniMax-M2 recipes 明确写 "maximum context length per individual sequence remains 196K"、Unsloth 运行指南 / GGUF 仓库 README 均标注 196K），以你实际运行的 GGUF 元数据与 llama-server 启动日志为准。

#### 推荐配置：64K 日常 / 128K 按需

**默认设置 `--ctx-size 65536`**（本文档所有命令已更新为此值）。64K 对于大多数编码辅助、文档分析、多轮对话场景足够。

如果需要处理更长的上下文（大型代码库、长文档分析），可以直接拉到 128K：

```bash
    --ctx-size 131072
```

甚至尝试接近官方标称上限 196K（来源：vLLM recipes / Unsloth 运行指南 / GGUF 仓库 README 的公开标注）：

```bash
    --ctx-size 196608
```

#### KV Cache 精度选择

| 参数 | 效果 | 建议 |
|------|------|------|
| `--cache-type-k f16 --cache-type-v f16` | KV Cache 使用 FP16，质量最好 | 内存充裕时的默认选择（本方案推荐） |
| `--cache-type-k q8_0 --cache-type-v q8_0` | KV Cache 量化到 Q8，占用减半 | 如需 196K context 但内存吃紧时使用 |
| `--cache-type-k q4_0 --cache-type-v q4_0` | KV Cache 量化到 Q4，占用减至 1/4 | 牺牲长距离召回精度，极限场景用 |

384GB 内存下建议直接用 FP16，不需要量化 KV Cache。只有在想同时跑 196K context + 高量化模型 + 其他 VM 抢内存时，才需要降到 Q8。

#### 与 Claude Opus 4.6 的体验差异

诚实地说，本地跑 M2.5 在长 context 体验上和 Claude API 有明显差距：

| 维度 | Claude Opus 4.6 API | 本地 M2.5 (64K-128K) |
|------|---------------------|---------------------|
| Context 上限 | 200K | 196K（官方标称），实际受内存和速度制约 |
| 长 prompt 处理速度 | 数秒内（集群算力） | 64K prompt 可能需要 30-60 秒 |
| 生成速度 | 稳定快速 | 5-10 t/s，长 context 下可能更低 |
| 长距离召回精度 | 很高 | 取决于量化精度和 KV Cache 设置 |

本地 M2.5 更适合的场景：不想发到云端的敏感代码和内部文档、离线环境、批量处理任务、以及希望不受 API 限额约束的长时间交互。对于需要频繁使用 200K context + compaction 的高强度交互式工作流，Claude API 仍然是更好的选择。

#### 首次验证流程

虽然日常使用建议 64K，首次部署时仍建议从低 context 开始逐步验证：

| 阶段 | Context Size | 目标 |
|------|-------------|------|
| 第一步 | 8192 | 确认模型加载、GPU/CPU 分配、推理流程全链路正常 |
| 第二步 | 16384 | 基本对话测试，确认输出格式和 think 标签正确 |
| 第三步 | 65536 | 日常使用配置，观察速度和内存占用 |
| 第四步 | 131072 | 长 context 场景，确认 VRAM 和系统内存不溢出 |

每次调整后跑几轮对话，用 `nvidia-smi` 确认 VRAM 峰值，用 `htop` 确认系统内存，用 llama-server 日志确认 tokens/s。

### 6.3 性能调优建议

```bash
# 1. VM 内关闭透明大页（可能引起延迟抖动）
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/enabled

# 2. 设置 CPU governor 为 performance
sudo cpupower frequency-set -g performance

# 3. 验证 NUMA 拓扑与 interleave 策略
numactl --hardware               # 查看 NUMA 节点与内存分布
numactl --show                   # 确认当前 NUMA policy（应显示 interleave）
# 启动 llama-server 后，验证进程的实际 NUMA 分布：
numastat -p $(pgrep llama-server)  # 查看进程在各节点的内存分配是否均匀

# 4. 监控运行状态
watch -n 1 nvidia-smi    # GPU 使用率和 VRAM 占用
htop                      # CPU 和内存（关注 llama-server 的 RSS）
nvtop                     # GPU 详细监控
```

### 6.4 部署验证测试

部署完成后，按以下步骤验证系统功能正常：

#### GPU 状态检查

```bash
# 确认两张 GPU 被正确识别
nvidia-smi
# 预期：两张 RTX 3090，各 24GB VRAM，驱动版本一致
# 如果只看到一张或零张，检查 ESXi Passthrough 和 MMIO 配置

# 检查 CUDA 工具链（可选，仅安装了 cuda-toolkit 时可用）
nvcc --version
```

#### 服务健康检查

```bash
# 检查 systemd 服务状态
sudo systemctl status llama-server

# 等待模型加载完成（首次启动需要数分钟加载 ~162GB 模型）
# 观察日志，直到出现 "server is listening" 字样
journalctl -u llama-server -f

# API 健康检查
curl -s http://localhost:8080/health | python3 -m json.tool
# 预期返回：{"status":"ok"}
```

#### 推理冒烟测试

```bash
# 基础推理测试：发送一个简单请求，确认模型能正常生成
curl -s http://localhost:8080/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "messages": [{"role": "user", "content": "Say hello in 3 languages."}],
        "max_tokens": 200,
        "temperature": 0.7
    }' | python3 -m json.tool

# 检查点：
# 1. HTTP 200 响应
# 2. choices[0].message.content 非空
# 3. usage.total_tokens > 0
# 4. 如果模型启用了 think mode，可能会有 reasoning_content 字段
```

#### 启动日志验证（CPU-MoE + 层分配）

```bash
# 检查 llama-server 启动日志，确认关键配置生效
journalctl -u llama-server --no-pager | head -100

# 应确认以下关键信息：
# 1. CPU-MoE 已启用：日志中应出现 cpu-moe 相关的层分配信息
# 2. 双 GPU 层分配：确认层被分配到两张 GPU（如 "GPU 0" / "GPU 1"）
# 3. tensor-split 生效：分配比例与 --tensor-split 1,1 一致
# 4. 模型加载完成：出现 "model loaded" 或类似字样

# 在推理过程中观察双 GPU 利用率（发送一个请求后运行）
watch -n 0.5 nvidia-smi
# 预期：推理时两张卡的 GPU Utilization 都应有活动，而非只有一张在工作
```

#### 资源占用验证

```bash
# GPU VRAM 占用（注意力层 + KV Cache）
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
# 预期：每张卡 12-18 GB（取决于层分配和 context 使用情况）

# 系统内存占用（模型权重 + KV Cache + 运行时）
ps aux | grep llama-server | grep -v grep | awk '{print $6/1024/1024 " GB"}'
# 或用 htop 查看 llama-server 进程的 RES 列

# NUMA 内存分布（确认 interleave 策略生效）
numastat -p $(pgrep llama-server)
# 预期：两个节点的内存分配大致均匀
```

#### Open WebUI 验证

```bash
# 检查 Docker 容器状态
docker ps | grep open-webui

# HTTP 可达性（检查状态码和响应内容）
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:3000 | tail -1
# 预期：HTTP Status: 200
```

### 6.5 性能基准测试方法

在验证功能正常后，使用以下方法建立性能基线，便于后续调优和版本升级时对比。

#### 测试工具

| 工具 | 用途 | 安装 |
|------|------|------|
| `curl` + `time` | 手动单次请求计时 | 系统自带 |
| llama-server `/health` | 服务健康状态（返回 `{"status":"ok"}` 或 503） | 内置 |
| `nvidia-smi dmon` | GPU 利用率和显存实时监控 | 驱动自带 |
| `numastat` | NUMA 内存分布 | `numactl` 包 |

#### 关键指标

| 指标 | 含义 | 获取方式 |
|------|------|---------|
| Prompt Processing (pp) | Prompt 处理速度 (tokens/s) | llama-server 日志 / API `timings` 字段 |
| Token Generation (tg) | 生成速度 (tokens/s) | llama-server 日志 / API `timings` 字段 |
| TTFT | 首 token 延迟 | `curl` 计时 / streaming 响应首字节时间 |
| VRAM Peak | GPU 显存峰值 | `nvidia-smi` |
| RSS | 系统内存占用 | `htop` / `ps` |

#### 标准测试命令

```bash
# 短 prompt 生成速度测试（测 token generation 速度）
time curl -s http://localhost:8080/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "messages": [{"role": "user", "content": "Write a short poem about the sea."}],
        "max_tokens": 500,
        "temperature": 0.7
    }' | python3 -c "
import sys, json
r = json.load(sys.stdin)
t = r.get('timings', {})
u = r.get('usage', {})
pt = u.get('prompt_tokens', 'N/A')
ct = u.get('completion_tokens', 'N/A')
print(f'Prompt tokens: {pt}')
print(f'Completion tokens: {ct}')
pp = t.get('prompt_per_second')
tg = t.get('predicted_per_second')
print(f'Prompt processing: {pp:.1f} tok/s' if pp else 'Prompt processing: N/A')
print(f'Generation: {tg:.1f} tok/s' if tg else 'Generation: N/A')
"

# 长 prompt 处理速度测试（测 prompt processing / prefill 速度）
# 生成一个 ~4K token 的 prompt
python3 -c "
import json, urllib.request
prompt = 'Summarize the following text:\n' + 'The quick brown fox jumps over the lazy dog. ' * 500
data = json.dumps({
    'messages': [{'role': 'user', 'content': prompt}],
    'max_tokens': 100,
    'temperature': 0.7
}).encode()
req = urllib.request.Request('http://localhost:8080/v1/chat/completions',
    data=data, headers={'Content-Type': 'application/json'})
r = json.loads(urllib.request.urlopen(req).read())
t = r.get('timings', {})
u = r.get('usage', {})
print(f'Prompt tokens: {u.get(\"prompt_tokens\", \"N/A\")}')
pp = t.get('prompt_per_second')
tg = t.get('predicted_per_second')
print(f'Prompt processing: {pp:.1f} tok/s' if pp else 'Prompt processing: N/A')
print(f'Generation: {tg:.1f} tok/s' if tg else 'Generation: N/A')
"
```

#### 测试记录模板

建议使用以下格式记录每次基准测试结果，便于纵向对比：

```
日期: YYYY-MM-DD
引擎版本: ik_llama.cpp commit <hash>
量化: UD-Q5_K_XL
启动参数: --ctx-size 65536 --parallel 1 --cache-type-k f16 --cache-type-v f16
          --split-mode layer --tensor-split 1,1 --cpu-moe --reasoning-format auto
GPU 配置: 2× RTX 3090
---
短 prompt 测试:
  - Prompt tokens: __
  - Completion tokens: __
  - Generation: __ tok/s
  - TTFT: __ s
长 prompt 测试 (~4K tokens):
  - Prompt tokens: __
  - Completion tokens: __
  - Prompt processing: __ tok/s
  - Generation: __ tok/s
资源占用:
  - GPU0 VRAM: __ / 24 GB
  - GPU1 VRAM: __ / 24 GB
  - System RAM (RSS): __ GB
  - NUMA balance: node0 __ GB / node1 __ GB
```

### 6.6 调优实测记录

经过 17 轮系统性单变量调优（11 轮 expert 层放置 + 6 轮 CPU 线程），short gen 从基线 4.7 提升到 8.38 tok/s（+78%），long gen 从 4.7 提升到 8.02 tok/s（+71%）。

**完整调优过程详见独立文档**：[minimax-m25-tuning-log.md](minimax-m25-tuning-log.md)

#### 推荐生产配置

```
-ot 6+4 不对称分配 + split-mode graph + KV cache q8_0
--threads 20 --threads-batch 36
CUDA0: blk.51-56 (6层 expert) → ~20,794 MiB (余 3.8 GB)
CUDA1: blk.57-60 (4层 expert) → ~17,412 MiB (余 7.2 GB)
Short gen: ~8.38 tok/s | Long gen: ~8.02 tok/s | Long prefill: ~100 tok/s
```

> 7+3 分配 S_gen 略高（7.21 → 线程优化后同样 ~8.4），但 CUDA0 仅余 1.3 GB，不推荐作为日常默认。

#### 调优总结

**Expert 层放置**（第一～十一轮）：

| 配置 | Short gen | Long gen | CUDA0 | CUDA1 | 备注 |
|------|-----------|----------|-------|-------|------|
| 基线 (cpu-moe, f16) | 4.7 | 4.7 | ~12 GB | ~12 GB | 全 expert CPU |
| +q8_0 +moe=58 | 6.0 | 6.4 | 5,848 | 17,334 | 5 层 expert GPU |
| +graph mode | 7.01 | 6.57 | 5,924 | 19,940 | 张量并行 |
| +ot 6+4 graph | 7.10* | 6.79* | 20,794 | 17,412 | 不对称基线 |
| +ot 7+3 graph | 7.21* | 6.79* | 23,246 | 14,498 | CUDA0余1.3GB |

**CPU 线程优化**（第十二～十七轮）：

| 配置 | Short gen | Long gen | L_pf | 备注 |
|------|-----------|----------|------|------|
| 无显式线程 | 7.21 | 6.79 | 99.1 | 默认全核 |
| threads=16, tb=36 | 8.17 | 7.82 | — | +13% / +15% |
| **threads=20, tb=36** | **8.38** | **8.02** | **100.2** | **+16% / +18%** |
| threads=24, tb=36 | 8.40 | 8.02 | 100.1 | 与 t=20 持平 |
| threads=28, tb=36 | 7.98 | 7.95 | 101.7 | S_gen 回落 |

\* 多轮均值（排除首次冷启动）。

#### 关键发现

1. **CPU 线程调参是最大增益点**：threads=20 比默认 S_gen +16%、L_gen +18%，增幅超过此前 expert 层优化总和
2. **Expert 集中分配**：主卡多 expert 减少跨卡通信，short gen 持续提升（3+3→7+3: 5.80→7.21）
3. **Graph 模式**：short gen +6.6% 稳定优势（多轮均值验证）
4. **threads-batch 影响 prefill 不影响 generation**：tb=24 prefill 低 18%，tb=32/36 接近
5. **Benchmark 方法论**：单次波动 ±0.5 tok/s，需多轮均值；prefill 仅冷启动有效（KV cache 污染）

---

## 第七部分：前端 & API 集成

### 7.1 Open WebUI（推荐）

llama-server 启动后暴露 OpenAI 兼容 API，可以直接接入 Open WebUI：

```bash
# 在同一 VM 或另一 VM 中用 Docker 部署
docker run -d \
    --name open-webui \
    -p 3000:8080 \
    -e OPENAI_API_BASE_URL=http://<llama-server-ip>:8080/v1 \
    -e OPENAI_API_KEY=not-needed \
    -v open-webui:/app/backend/data \
    ghcr.io/open-webui/open-webui:main
```

### 7.2 在其他工具中使用

llama-server 的 API 兼容 OpenAI 格式，可以配置到：

- **Continue (VS Code 插件)**：设置 API base 为 `http://<ip>:8080/v1`
- **Cursor / Cline**：作为自定义 OpenAI-compatible 端点
- **Claude Code**：暂不支持自定义端点，但可通过 LiteLLM 代理转发
- **Python/脚本调用**：直接用 `openai` 库，修改 `base_url`

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://<llama-server-ip>:8080/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="minimax-m2.5",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

---

## 第八部分：自动启动与管理

### 8.1 Systemd 服务

```bash
sudo tee /etc/systemd/system/llama-server.service << 'EOF'
[Unit]
Description=llama.cpp Server - MiniMax M2.5
After=network.target
# 如果系统安装了 nvidia-persistenced，取消下行注释以确保 GPU 就绪后再启动
# After=network.target nvidia-persistenced.service

[Service]
Type=simple
User=llm
WorkingDirectory=/home/llm/ik_llama.cpp
ExecStart=/usr/bin/numactl --interleave=all \
    /home/llm/ik_llama.cpp/build/bin/llama-server \
    --model /data/models/UD-Q5_K_XL/MiniMax-M2.5-UD-Q5_K_XL-00001-of-00005.gguf \
    -ngl 999 \
    --cpu-moe \
    --split-mode layer \
    --tensor-split 1,1 \
    --jinja \
    --ctx-size 65536 \
    --cache-type-k f16 \
    --cache-type-v f16 \
    --host 0.0.0.0 \
    --port 8080 \
    --parallel 1 \
    --reasoning-format auto \
    --temp 1.0 \
    --top-p 0.95 \
    --top-k 40
Restart=on-failure
RestartSec=30
StartLimitIntervalSec=300
StartLimitBurst=3
LimitNOFILE=65536
# 可选：锁定模型和 KV Cache 到内存，减少运行时页面换出导致的抖动
# 启用时取消下面两行注释，并在 ExecStart 中加上 --mlock --no-mmap
# LimitMEMLOCK=infinity

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable llama-server
sudo systemctl start llama-server

# 查看日志
journalctl -u llama-server -f
```

> **重启策略说明**：`RestartSec` 设为 30s，并加入 `StartLimitBurst=3` / `StartLimitIntervalSec=300`（5 分钟内最多重启 3 次）。消费级 GPU 在 ESXi Passthrough 下，频繁触发驱动重载/GPU 复位可能导致 GPU 进入不可恢复状态，最终需要重启 ESXi 宿主机。保守的重启策略可以避免连续崩溃把 GPU "打死"。如果 llama-server 确实崩了，先检查日志再手动重启更安全。
>
> **关于 `--mlock` / `--no-mmap`（可选）**：`--mlock` 将模型权重和 KV Cache 锁定在物理内存中，防止 OS 将其换出到 swap，减少推理时的延迟抖动。`--no-mmap` 则在加载时直接将模型读入内存而非 mmap，代价是启动时间更长、瞬时内存峰值更高。384GB 内存下启用两者是安全的，但会让启动过程需要等待更久（100-170GB 模型完整读入）。如果不追求极致稳定性，默认的 mmap 加载方式已经足够。

---

## 第九部分：注意事项与已知风险

### 9.1 消费级 GPU 的 Passthrough Reset 问题（重要）

这是消费级 GPU + ESXi Passthrough 最常见的痛点：VM 重启或 GPU 驱动 reset 后，GPU 在宿主机侧没有被正确复位（FLR/热复位路径不完整），导致再次进入 VM 后 GPU 不可用。此时唯一的恢复方式是重启 ESXi 宿主机。

应对策略：

- 尽量避免频繁重启 VM 或重载 GPU 驱动。模型切换时优先使用 llama-server 的 API 热加载（如支持），而非停服重启。
- Systemd 服务的重启策略已设为保守模式（见 8.1），避免连续崩溃加剧 GPU 状态损坏。
- 业务层（Open WebUI / 反向代理）加健康检查：llama-server 无响应时先从入口摘除流量，而非立即触发进程重启。
- 如果此问题频繁出现，认真考虑迁移到裸机 Ubuntu 或 Proxmox VE（见 9.7）。

### 9.2 BIOS 配置

确认 BIOS 中以下选项已开启（缺一不可）：VT-d / IOMMU 和 Above 4G Decoding。详见第一部分。

### 9.3 驱动兼容性

VM 内的 NVIDIA 驱动版本需要与 GPU 硬件匹配。RTX 3090 (GA102) 建议使用 535+ 驱动。

### 9.4 散热

两张 3090 在工作站机箱内散热需要注意。MoE 推理时 GPU 负载不会满载（注意力层计算量有限），但长时间运行建议监控温度。

### 9.5 内存分配

给 VM 分配 256-300 GB 后，ESXi 和其他 VM 仍有 84-128 GB 可用。确保 ESXi 本身有足够内存运行。

### 9.6 磁盘 I/O

模型加载时需要读取 100-170 GB 文件，SSD/NVMe 会显著加快启动速度。日常推理对磁盘无压力。

### 9.7 备选方案：裸机 / Proxmox VE

如果满足以下任一情况，建议考虑绕过 ESXi：

- GPU Reset 问题频繁出现，运维成本过高
- 需要更细粒度的 CPU pinning、hugepages、vfio 参数控制
- 对生成速度和尾延迟有较高要求（ESXi 的 NUMA 调度和虚拟化抽象层会引入额外开销）

Proxmox VE 的 GPU Passthrough 基于 vfio-pci，配置透明度更高。裸机 Ubuntu 则完全消除虚拟化开销，是性能上限最高的方案。

### 9.8 ESXi 侧进阶调优（可选）

如果在基本方案跑通后想进一步压榨性能或减少抖动，以下是可探索的方向（不展开详细配置，按需自行研究）：

- **VM CPU Reservation**：为 LLM VM 预留 CPU 资源，防止 ESXi 在其他 VM 抢资源时降频
- **VM Latency Sensitivity = High**：减少 ESXi 调度器的干预，降低尾延迟抖动
- **BIOS 电源策略 / C-state 关闭**：在 Dell T7910 BIOS 中将电源策略设为 Maximum Performance，关闭 CPU C-state，避免省电模式引入唤醒延迟

---

## 附录：Review 反馈处理记录

以下记录了四轮外部审阅意见的逐条处理结果和理由。

### 第一轮采纳的改进

| 反馈点 | 改动 | 理由 |
|--------|------|------|
| Above 4G Decoding | 新增第一部分 BIOS 前置条件，明确为硬性要求 | 双 3090 大 BAR Passthrough 必需，原方案遗漏 |
| 内存全量预留双保险 | 新增 2.3 节，UI 勾选 + VMX 参数双重设置 | Passthrough 硬性要求，单靠 VMX 参数不够稳妥 |
| 模型文件路径 | 所有命令改为显式指向第一个分片文件 | 通配符可能导致 shell 展开后传入多个路径，行为不可预期 |
| `--n-cpu-moe` 参数 | 新增 5.2 节详细说明渐进调参策略 | 比 `--cpu-moe` 更灵活，可在 VRAM 有余量时提速 |
| Context 渐进验证 | 新增首次验证流程：8K → 16K → 64K → 128K | 先确认链路正常再拉高 context，更务实 |
| GPU Reset 风险 | 新增 9.1 节详细说明问题现象和应对策略 | 消费级 GPU Passthrough 最常见的运维痛点，必须提前预警 |
| Systemd 重启策略 | RestartSec 改为 30s，加入 StartLimitBurst/Interval | 避免连续崩溃频繁触发 GPU 复位导致不可恢复 |

### 第二轮采纳的改进

| 反馈点 | 改动 | 理由 |
|--------|------|------|
| ctx-size 叙事矛盾 | 统一为：默认 64K，首次验证从 8K 起步；修正附录中的错误描述 | 第一轮附录里写"默认改为 16384"与正文 65536 冲突 |
| sched.mem.min 硬编码 | 改为参数化模板 `<VM_MEMORY_MB>`，加注释说明计算方式 | 写死 262144 会误导照抄的人，尤其 VM 内存不是 256GB 时 |
| KV Cache 解释错误 | 重写：明确 KV Cache 取决于注意力层结构参数，与 MoE 激活比例无直接关系；估算表降级为经验区间 | 原文"10B active → KV Cache 更省"推导不成立 |
| EFI 固件建议 | VMX 配置中新增 `firmware = "efi"`，并说明原因 | 双大显存卡 + 64-bit MMIO 场景下 EFI 更稳定 |
| mem.hotadd UI 侧双保险 | 2.3 节补充 UI 里也要确认 Memory Hot Plug 关闭 | 与内存预留同理，UI 和 VMX 双保险 |
| 驱动安装方式 | 改为 `ubuntu-drivers autoinstall` 优先，手动指定版本作为 fallback | 原写法在部分 Ubuntu 版本/源上可能找不到 550-server |
| NUMA 验证命令 | 6.3 节补充 `numactl --show`、`numastat -p` | 让 interleave 策略可审计，而不是盲信 |
| 196K 上限来源 | 标注为"官方 model card / HuggingFace 仓库标称" | 补充信息来源，避免被质疑为无根据 |

### 第三轮采纳的改进

| 反馈点 | 改动 | 理由 |
|--------|------|------|
| 多 GPU 切分策略缺失 | 所有命令新增 `--split-mode layer --tensor-split 1,1 --fit on` | 多 GPU 默认切分行为随版本变化，显式指定确保可复现 |
| `--parallel` 在大 context 下的内存影响 | 默认改为 `--parallel 1`，新增 5.5 节详细说明 KV Cache 按 slot 预分配的机制，另给并发版示例 | parallel 2 + 64K context 意味着双份 KV Cache，内存占用可能翻倍 |
| `--n-cpu-moe` 与多 GPU 交互 | 5.2 节补充多 GPU 下层序分配可能导致显存不均的提醒 | 帮助调参时避免"一卡满一卡空"的困惑 |
| CUDA Toolkit 反向覆盖驱动 | 3.2 节重写，强调"先装驱动再装 toolkit"，给出 `cuda-toolkit` 子包安装和 `apt-mark hold` 方案 | CUDA 安装器捆绑驱动依赖是常见踩坑点 |
| systemd 缺少 mlock 支持 | 8.1 节新增 `LimitMEMLOCK=infinity`（注释态）和 `--mlock --no-mmap` 可选说明 | 384GB 内存可以 mlock，减少运行时页面换出抖动 |
| 196K 来源不够具体 | 改为引用 vLLM recipes / Unsloth 运行指南 / GGUF 仓库 README 的公开标注 | 比"官方 model card"更具体可查证 |
| ESXi 侧 CPU reservation / Latency Sensitivity / C-state | 新增 9.8 节简要列出可探索方向 | 不展开但点到，方便后续深度调优 |

### 第四轮采纳的改进（定稿补丁）

| 反馈点 | 改动 | 理由 |
|--------|------|------|
| `apt-mark hold` 包名不匹配 | 改为先 `dpkg -l` 查实际驱动包名再 hold | `ubuntu-drivers autoinstall` 不一定装 `nvidia-driver-550-server`，硬编码包名会导致 hold 不生效 |
| `cuda-toolkit-12-8` 需要 NVIDIA APT 源 | 补充"若找不到包，先按 NVIDIA 官方安装页添加 repo"的前置说明 | 干净 Ubuntu 系统默认不含 CUDA 仓库，照抄者会卡在 "Unable to locate package" |
| `numa.nodeAffinity = "0,1"` 容易误导 | 移除该参数，改为注释说明其不等于精细 pinning，NUMA 优化在 VM 内通过 numactl 实现 | "0,1" 只表示允许在两个节点运行，容易被误解为对齐 GPU 所在节点的 pinning |
| `--fit on` 行为边界不明确 | 补充说明它可能自动下调未显式指定的配置项，需以启动日志和 nvidia-smi 确认最终落点 | 避免读者误以为"写了 64K 就一定 64K、层分配一定按预期" |
| `pciPassthru.64bitMMIOSizeGB` | 加注释：若 VM 启动失败可从 64 上调到 128 | 双 3090 + 不同主板/BIOS 组合下 MMIO 需求可能超过 64GB |
| systemd `After=nvidia-persistenced.service` | 改为注释态，不硬依赖 | 部分 Ubuntu/驱动组合不含该服务，硬依赖会产生无谓告警 |

### 四轮均未采纳的建议及理由

| 反馈点 | 决定 | 理由 |
|--------|------|------|
| `numactl --interleave=all` 改为本地优先 + 线程绑定 | **保留 interleave** | ESXi VM 内做精细 CPU pinning 受 hypervisor NUMA 调度器二次映射影响，实操困难。MoE 专家激活具有随机性，访存模式天然分散，interleave 能有效避免单节点带宽饱和。已补充验证命令使策略可审计 |
| 锁定 llama.cpp 到特定 commit | **不锁定** | M2.5 支持仍在快速迭代，过早锁定可能卡在已知 bug 上。建议跑通验证后记录 commit hash，确认稳定再锁定 |
| 裸机/Proxmox 替代方案详细展开 | **保持简述** | 9.7 节已列出迁移触发条件。完整的替代方案部署属于独立文档范畴 |
| `--flash-attn` / `--jinja` / `--reasoning-format` 兼容性警告 | **保留使用，不加警告** | 这三个参数是跑 M2.5 的标准配置，去掉反而导致输出异常。版本兼容性变化由"跟随最新版"策略自然覆盖 |