# Qwen3-32B & GLM-4.7-Flash 新模型部署方案

## 硬件环境

- **主机**: Dell T7910, Dual E5-2686 v4, 384GB DDR4 ECC
- **GPU**: 2× RTX 3090 (48GB VRAM total)
- **虚拟化**: VMware ESXi, GPU Passthrough
- **存储**: 需预留约 40GB 用于模型文件

---

## 模型概览

| | Qwen3-32B Abliterated | GLM-4.7-Flash Abliterated |
|---|---|---|
| **定位** | 日常主力（综合智力最高） | 极速备用（需要快速响应时） |
| **架构** | 32B Dense | 30B MoE (3B active) |
| **量化** | Q4_K_M ~20GB | Q4_K_M ~18GB |
| **预期速度** | 15-25 tok/s | 35-50 tok/s |
| **中文** | 极强 | 好 |
| **Censorship** | 极低 | 低 |

---

## 部署架构

单实例运行，默认加载 Qwen3-32B，两张 RTX 3090 通过 `--split-mode graph` 双卡推理。需要切换模型时通过 `switch-model.sh` 停止当前实例、启动目标模型。

**架构：systemd 模板单元 + wrapper 脚本**

- **模板单元** `llama-server@.service`：`%i` = 模型名（m25 / qwen3-32b / glm-4.7）
- **Wrapper 脚本** `launch-llama.sh`：读取模型配置，构建完整命令行
- **模型配置**：每个模型一个 `.env` 文件（参数）+ 可选 `.ot` 文件（tensor override 规则）

```
┌─────────────────────────────────────────────────────────┐
│                       ESXi Host                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Ubuntu VM (GPU Passthrough)             │  │
│  │                                                      │  │
│  │  llama-server@.service                               │  │
│  │  ├── @m25      ── launch-llama.sh m25      ── m25.env/.ot      │  │
│  │  ├── @qwen3-32b── launch-llama.sh qwen3-32b── qwen3-32b.env  │  │
│  │  └── @glm-4.7  ── launch-llama.sh glm-4.7  ── glm-4.7.env    │  │
│  │                    │                                  │  │
│  │            Port 8080 (同一时间只运行一个)               │  │
│  │                    │                                  │  │
│  │                    ▼                                  │  │
│  │  ┌──────────────────────────────────────┐            │  │
│  │  │        Open WebUI (Port 3000)         │            │  │
│  │  │   http://host:8080/v1                │            │  │
│  │  └──────────────────────────────────────┘            │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

- 同一时间只运行一个模型实例，48GB VRAM 全部可用
- KV cache 充裕，支持长上下文
- 切换模型需重启服务（冷启动 20-30 秒）
- 模板单元切换无需 `daemon-reload`，直接 `stop @old` + `start @new`

---

## 部署步骤

### 0. 前置条件

```bash
# 创建专用服务用户（如已通过 M2.5 Ansible role 部署过则已存在）
sudo useradd -r -s /bin/bash -m llm 2>/dev/null || echo "用户 llm 已存在"

# 模型目录（llm 用户需要读权限）
sudo mkdir -p /data/models
sudo chown llm:llm /data/models

# 安装目录
sudo mkdir -p /opt/llm-server/{bin,models}

# 验证 llm 用户可访问 GPU
sudo -u llm nvidia-smi
```

> 若在已部署 M2.5 的同一 VM 上操作，`llm` 用户和 `/data/models` 目录已由 Ansible role 创建，跳过此步。

### 1. 模型下载

```bash
# Qwen3-32B Abliterated (huihui-ai, imatrix 版优先)
sudo -u llm hf download huihui-ai/Qwen3-32B-Instruct-abliterated-GGUF \
  --include "*Q4_K_M*" --local-dir /data/models/qwen3-32b-abl

# GLM-4.7-Flash Abliterated (mradermacher imatrix 版)
sudo -u llm hf download mradermacher/Huihui-GLM-4.7-Flash-abliterated-i1-GGUF \
  --include "*Q4_K_M*" --local-dir /data/models/glm-4.7-flash-abl

# 下载后确认实际文件名（HF 仓库命名因上传者而异）
ls /data/models/qwen3-32b-abl/*Q4_K_M*.gguf
ls /data/models/glm-4.7-flash-abl/*Q4_K_M*.gguf
```

> ⚠️ **下载后务必核对实际 GGUF 文件名**，将正确的文件名填入下方 `/opt/llm-server/models/` 配置文件的 `LLAMA_MODEL` 变量。HF 仓库命名因上传者而异（如 mradermacher 的格式为 `Huihui-GLM-4.7-Flash-abliterated.i1-Q4_K_M.gguf`），与本文档中的占位名可能不同。

### 2. ik_llama.cpp 编译

```bash
sudo git clone https://github.com/ikawrakow/ik_llama.cpp /opt/llm-server/ik_llama.cpp
cd /opt/llm-server/ik_llama.cpp
sudo git checkout f7923739  # Pin to known-good commit (同 Ansible role 及 M2.5 实测版本)
sudo cmake -B build -DGGML_CUDA=ON
sudo cmake --build build --config Release -j$(nproc)
```

### 3. Systemd Service

> ⚠️ **所有生命周期管理统一走 systemd**，不要手动 `&` 后台启动。混用会导致 stop 杀不掉进程、日志丢失、重启不可靠。

使用 systemd **模板单元** (`llama-server@.service`)。模板单元是 systemd 内置机制，一个 `.service` 文件可以派生多个实例 — `systemctl start llama-server@qwen3-32b` 会把 `%i` 替换为 `qwen3-32b`，传给 wrapper 脚本加载对应配置。切换模型无需 `daemon-reload`。

#### 3.1 目录结构

```
/opt/llm-server/
├── bin/launch-llama.sh       # wrapper 脚本，读取配置构建命令行
├── models/
│   ├── m25.env               # MiniMax-M2.5 参数
│   ├── m25.ot                # MiniMax-M2.5 tensor override 规则（仅 M2.5 需要）
│   ├── qwen3-32b.env          # Qwen3-32B 参数
│   └── glm-4.7.env            # GLM-4.7-Flash 参数
└── ik_llama.cpp/             # 引擎（步骤 2 编译）
```

#### 3.2 模型配置文件

**`/opt/llm-server/models/m25.env`**：

```bash
LLAMA_MODEL=/data/models/UD-Q5_K_XL/MiniMax-M2.5-UD-Q5_K_XL-00001-of-00005.gguf
LLAMA_ALIAS=MiniMax-M2.5
LLAMA_GPU_LAYERS=999
LLAMA_SPLIT_MODE=graph
LLAMA_CTX_SIZE=65536
LLAMA_THREADS=20
LLAMA_THREADS_BATCH=36
LLAMA_TENSOR_SPLIT=1,1
LLAMA_CACHE_TYPE_K=q8_0
LLAMA_CACHE_TYPE_V=q8_0
LLAMA_REASONING_FORMAT=auto
LLAMA_TEMP=0.8
LLAMA_TOP_P=0.95
LLAMA_TOP_K=40
```

**`/opt/llm-server/models/m25.ot`**（每行一条 `pattern=backend` 规则）：

```
blk\.(51|52|53|54|55|56)\.ffn_(up|down|gate)_exps\.weight=CUDA0
blk\.(57|58|59|60)\.ffn_(up|down|gate)_exps\.weight=CUDA1
\.ffn_(up|down|gate)_exps\.weight=CPU
```

**`/opt/llm-server/models/qwen3-32b.env`**：

```bash
# ↓ 文件名为占位符，部署时替换为 hf download 后的实际文件名
LLAMA_MODEL=/data/models/qwen3-32b-abl/qwen3-32b-q4_k_m.gguf
LLAMA_ALIAS=qwen3-32b
LLAMA_GPU_LAYERS=999
LLAMA_SPLIT_MODE=graph
LLAMA_CTX_SIZE=32768
LLAMA_THREADS=20         # 沿用 M2.5 值，部署后建议实测调优
LLAMA_THREADS_BATCH=36
LLAMA_TENSOR_SPLIT=1,1
LLAMA_CACHE_TYPE_K=q8_0
LLAMA_CACHE_TYPE_V=q8_0
LLAMA_REASONING_FORMAT=auto
LLAMA_TEMP=0.6
LLAMA_TOP_P=0.95
LLAMA_TOP_K=20
```

**`/opt/llm-server/models/glm-4.7.env`**：

```bash
# ↓ 文件名为占位符，部署时替换为 hf download 后的实际文件名
LLAMA_MODEL=/data/models/glm-4.7-flash-abl/glm-4.7-flash-q4_k_m.gguf
LLAMA_ALIAS=glm-4.7-flash
LLAMA_GPU_LAYERS=999
LLAMA_SPLIT_MODE=graph
LLAMA_CTX_SIZE=32768
LLAMA_THREADS=20         # 沿用 M2.5 值，部署后建议实测调优
LLAMA_THREADS_BATCH=36
LLAMA_TENSOR_SPLIT=1,1
LLAMA_CACHE_TYPE_K=q8_0
LLAMA_CACHE_TYPE_V=q8_0
LLAMA_TEMP=1.0
LLAMA_TOP_P=0.95
```

#### 3.3 Wrapper 脚本

**`/opt/llm-server/bin/launch-llama.sh`**：

```bash
#!/bin/bash
set -euo pipefail

MODEL_NAME="$1"
CONFIG_DIR="/opt/llm-server/models"
ENV_FILE="${CONFIG_DIR}/${MODEL_NAME}.env"
OT_FILE="${CONFIG_DIR}/${MODEL_NAME}.ot"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Model config not found: $ENV_FILE" >&2
    exit 1
fi

source "$ENV_FILE"

# 构建 -ot 参数（仅当 .ot 文件存在时）
OT_ARGS=()
if [[ -f "$OT_FILE" ]]; then
    while IFS= read -r line; do
        line=$(sed 's/^[[:space:]]*//' <<< "$line")
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        OT_ARGS+=(-ot "$line")
    done < "$OT_FILE"
fi

# 可选采样参数（.env 中有值才传）
EXTRA_ARGS=()
[[ -n "${LLAMA_REASONING_FORMAT:-}" ]] && EXTRA_ARGS+=(--reasoning-format "$LLAMA_REASONING_FORMAT")
[[ -n "${LLAMA_TEMP:-}" ]] && EXTRA_ARGS+=(--temp "$LLAMA_TEMP")
[[ -n "${LLAMA_TOP_P:-}" ]] && EXTRA_ARGS+=(--top-p "$LLAMA_TOP_P")
[[ -n "${LLAMA_TOP_K:-}" ]] && EXTRA_ARGS+=(--top-k "$LLAMA_TOP_K")

exec /usr/bin/numactl --interleave=all \
    /opt/llm-server/ik_llama.cpp/build/bin/llama-server \
    --model "$LLAMA_MODEL" \
    --alias "$LLAMA_ALIAS" \
    -ngl "$LLAMA_GPU_LAYERS" \
    "${OT_ARGS[@]}" \
    --split-mode "$LLAMA_SPLIT_MODE" \
    --tensor-split "$LLAMA_TENSOR_SPLIT" \
    --jinja \
    --ctx-size "$LLAMA_CTX_SIZE" \
    --cache-type-k "$LLAMA_CACHE_TYPE_K" \
    --cache-type-v "$LLAMA_CACHE_TYPE_V" \
    --threads "$LLAMA_THREADS" \
    --threads-batch "$LLAMA_THREADS_BATCH" \
    "${EXTRA_ARGS[@]}" \
    --host 0.0.0.0 \
    --port 8080 \
    --parallel 1
```

```bash
sudo chmod +x /opt/llm-server/bin/launch-llama.sh
```

#### 3.4 模板单元

**`/etc/systemd/system/llama-server@.service`**：

```ini
[Unit]
Description=llama-server %i
After=network.target
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=simple
User=llm
ExecStart=/opt/llm-server/bin/launch-llama.sh %i
Restart=on-failure
RestartSec=30
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now llama-server@qwen3-32b
```

### 4. 模型切换脚本

```bash
#!/bin/bash
# switch-model.sh — 在 M2.5 / Qwen3-32B / GLM-4.7-Flash 之间切换
set -euo pipefail

VALID_MODELS="m25 qwen3-32b glm-4.7"
MODEL="${1:-}"

if [[ ! " $VALID_MODELS " =~ " $MODEL " ]]; then
    echo "Usage: switch-model.sh <m25|qwen3-32b|glm-4.7>"
    # 显示当前状态
    CURRENT=$(systemctl list-units 'llama-server@*' --state=active --no-legend --plain | awk '{print $1}')
    if [[ -n "$CURRENT" ]]; then
        echo "当前: $CURRENT"
    else
        echo "当前: 无运行实例"
    fi
    exit 1
fi

# 停止当前运行的实例
echo "→ 停止当前实例..."
sudo systemctl stop 'llama-server@*' 2>/dev/null || true

# 启动目标模型
echo "→ 启动 llama-server@${MODEL}..."
sudo systemctl start "llama-server@${MODEL}"

# 健康检查
echo "  等待 port 8080..."
timeout 120 bash -c "until curl -sf http://localhost:8080/health >/dev/null 2>&1; do sleep 2; done" \
    || { echo "✗ 健康检查超时"; exit 1; }
echo "✓ ${MODEL} 已启动"
```

### 5. Open WebUI

```bash
sudo mkdir -p /opt/open-webui/data

docker run -d --name open-webui \
  --restart unless-stopped \
  -p 3000:8080 \
  --add-host=host.docker.internal:host-gateway \
  -e OPENAI_API_BASE_URLS="http://host.docker.internal:8080/v1" \
  -e OPENAI_API_KEY=not-needed \
  -v /opt/open-webui/data:/app/backend/data \
  --log-driver json-file --log-opt max-size=50m --log-opt max-file=3 \
  ghcr.io/open-webui/open-webui:main
```

> **生产注意**：
> - `-v /opt/open-webui/data:/app/backend/data`：持久化会话、配置、用户数据。无此卷容器重建会丢失一切。
> - `--restart unless-stopped`：宿主机重启后自动恢复。
> - 镜像 tag `:main` 会随上游漂移。验证稳定后建议 pin 到具体 digest 或日期 tag（如 `:2025.02`）。

> ⚠️ **Linux 必须加 `--add-host=host.docker.internal:host-gateway`**。
> `host.docker.internal` 在 macOS/Windows Docker Desktop 上开箱即用，但在 Linux 原生 Docker (20.10+) 上需要手动映射。
> 没有这行，容器内无法解析 `host.docker.internal`，Open WebUI 连不上宿主机的 llama-server。

> **模型切换后 Open WebUI 无需重启**：多个模型共用端口 `8080`，Open WebUI 会通过 `--alias` 自动识别当前加载的模型。切换模型后刷新页面即可看到新模型名。

> **Task model / model_ids 映射检查**：Open WebUI 的 Memory、Web Search 等内置功能依赖 "Task Model" 发起后台请求。如果 Task Model 指向不存在的 model_id，会触发 404 错误。部署后需在 **Admin → Settings → Interface → Task Model** 中设为空（跟随当前选中模型），避免切换模型后 Task Model 指向已卸载的模型。

### 6. OpenClaw 配置

- **Endpoint**: `http://<VM-IP>:8080/v1`
- **模型名**: 取决于当前加载的模型 — `qwen3-32b` 或 `glm-4.7-flash`
- 切换模型后需更新 OpenClaw 的模型名配置

---

## NUMA 配置

```bash
# 确认 NUMA 生效
numactl --show

# llama-server 始终通过 numactl --interleave=all 启动
# 确保双 socket 内存带宽都被利用
```

---

## 日常使用模式

| 场景 | 选择 | 切换方式 |
|---|---|---|
| 日常聊天、问答 | Qwen3-32B（默认） | 无需切换 |
| 快速查询、简单任务 | GLM-4.7-Flash | `switch-model.sh glm-4.7` |
| 极致编程质量 | MiniMax-M2.5 | `switch-model.sh m25` |
| OpenClaw agent | Qwen3-32B | 更聪明，推荐 |
| 敏感话题、无审查需求 | Qwen3-32B abl. | Abliterated 生态最成熟 |

---

## 后续可选扩展

- **增加 Qwen3-Coder-Next**: 编程需求增加时加入模型栈
- **Ansible Role**: 将部署自动化为可复用的 Ansible playbook
- **监控**: `nvidia-smi` 定时采集 + Grafana dashboard

---

## Codex 审核记录

### 第一轮审核

经 Codex (ChatGPT default model, reasoning=high) 审核，交叉参考 `llm-server-deployment.md` 和 `minimax-m25-tuning-log.md`。

#### 采纳

| 编号 | 严重度 | 发现 | 修订 |
|------|--------|------|------|
| 2 | P0 | 编译路径 `git clone` 相对目录与 service 引用的 `/opt/llm-server/ik_llama.cpp` 不一致 | 统一为 `sudo git clone ... /opt/llm-server/ik_llama.cpp`（与 Ansible role 一致） |
| 3 | P0 | Open WebUI 无持久化卷，容器重建丢失会话和配置 | 加 `-v /opt/open-webui/data:/app/backend/data` + `--restart unless-stopped` + 日志限制 |
| 4 | P1 | Service 无 `User=` 指令，以 root 运行 | 加 `User=llm`（同 M2.5 Ansible role 模式） |
| 5 | P1 | 缺少显式 `--cache-type-k/v` 和 `--parallel`，默认值变化导致静默退化 | 显式加 `--cache-type-k q8_0 --cache-type-v q8_0 --parallel 1` |
| 6 | P1 | Open WebUI 无 `--restart` 策略，镜像 tag `:main` 随上游漂移 | 加 `--restart unless-stopped`，文档注明验证后 pin tag |
| 7 | P2 | `--threads 20/36` 直接复用 M2.5 结论，Qwen/GLM 负载形态不同 | 参数说明中注明"部署后建议实测验证" |
| 8 | P2 | 应尽快 Ansible role 化，补 verify play | 列入"后续可选扩展" |

### 第二轮审核（修订后复查）

#### 采纳

| 编号 | 严重度 | 发现 | 修订 |
|------|--------|------|------|
| 1 | P1 | `User=llm` 已加但无创建步骤，非既有环境会 `status=217/USER` | 新增"步骤 0. 前置条件"：创建 `llm` 用户 + `/models` 目录权限 |

> 注：两轮审核中涉及双实例方案（方案 A）的发现（原第一轮 #4/#5、第二轮 #1/#2/#3/#5）已随方案 A 移除而不再适用，此处仅保留仍有效的条目。
