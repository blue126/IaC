# MiniMax M2.5 LLM Server IaC 部署方案

## Context

将 `minimax-llama.md` 中的手动部署方案转化为符合本 repo 约定的 Terraform + Ansible 自动化部署。目标：一条 `terraform apply` 创建 VM，一条 `ansible-playbook` 完成从裸机到可用推理服务的全部配置。

用户选择：ik_llama.cpp 引擎 / 模型下载纳入自动化 / Open WebUI 同 role 部署。

---

## 1. Terraform — VM 定义

### 修改文件

**`terraform/esxi/variables.tf`** — 追加 LLM Server 变量块：

```hcl
# ==========================================
# LLM Server VM Configuration
# ==========================================
variable "llm_server_vm_name" {
  default = "llm-server"
}
variable "llm_server_ip_address" {
  type = string
}
variable "llm_server_num_cpus" {
  default = 48
}
variable "llm_server_memory_mb" {
  default = 286720  # 280 GB
}
variable "llm_server_system_disk_gb" {
  default = 500
}
variable "llm_server_mmio_size_gb" {
  description = "64-bit MMIO size in GB for GPU passthrough. Dual 3090: start with 64, increase to 128 if VM fails to boot"
  type        = number
  default     = 64
}
```

**`terraform/esxi/llm-server.tf`** — 新文件，仿照 `pbs.tf` 模式：

```hcl
module "llm_server" {
  source = "../modules/esxi-vm"

  vm_name          = var.llm_server_vm_name
  resource_pool_id = data.vsphere_host.host.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id
  network_id       = data.vsphere_network.network.id
  host_system_id   = data.vsphere_host.host.id

  num_cpus           = var.llm_server_num_cpus
  memory             = var.llm_server_memory_mb
  memory_reservation = var.llm_server_memory_mb  # Required for GPU Passthrough
  system_disk_size   = var.llm_server_system_disk_gb

  firmware = "efi"
  guest_id = "ubuntu64Guest"

  # GPU Passthrough managed via ESXi Web UI (same pattern as PBS HBA)
  pci_device_ids = []

  extra_config = {
    "pciPassthru.use64bitMMIO"    = "TRUE"
    "pciPassthru.64bitMMIOSizeGB" = tostring(var.llm_server_mmio_size_gb)
    "mem.hotadd"                  = "FALSE"
  }
}

resource "ansible_host" "llm_server" {
  name   = "llm-server"
  groups = ["esxi_vms"]
  variables = {
    ansible_user                 = "ubuntu"
    ansible_host                 = var.llm_server_ip_address
    ansible_ssh_private_key_file = "~/.ssh/id_ed25519"
  }
  depends_on = [module.llm_server]
}

output "llm_server_vm_id" {
  value       = module.llm_server.vm_id
  description = "LLM Server VM Managed Object ID"
}

output "llm_server_ip" {
  value       = var.llm_server_ip_address
  description = "LLM Server IP Address"
}
```

重点：GPU PCI 设备 ID 不由 Terraform 管理（同 PBS 的 HBA passthrough 模式），在 ESXi Web UI 手动 toggle 后 Terraform `lifecycle.ignore_changes` 会忽略差异。

---

## 2. Ansible Role — `llm-server`

### 文件结构

```
ansible/roles/llm-server/
├── defaults/main.yml          # All configurable values
├── tasks/
│   ├── main.yml               # Entry point (includes sub-task files)
│   ├── disk.yml               # Expand root partition to fill virtual disk
│   ├── nvidia.yml             # NVIDIA driver + CUDA Toolkit
│   ├── llama-cpp.yml          # Compile ik_llama.cpp
│   ├── model.yml              # Download GGUF model via hf CLI
│   ├── tuning.yml             # Performance tuning (THP, CPU governor)
│   ├── service.yml            # Systemd unit for llama-server
│   └── webui.yml              # Open WebUI via Docker Compose
├── templates/
│   ├── llama-server.service.j2
│   └── docker-compose.yml.j2
└── handlers/main.yml          # Restart handlers
```

### `defaults/main.yml` — 关键变量

```yaml
# System user (shell must be /bin/bash — required for become_user + async model download)
llm_server_user: llm

# Engine
llm_server_engine_repo: "https://github.com/ikawrakow/ik_llama.cpp"
llm_server_engine_version: "f7923739" # Pin to known-good commit for MiniMax M2.5 (see ubergarm/MiniMax-M2.5-GGUF#11)
llm_server_install_dir: /opt/llm-server

# NVIDIA driver (empty = ubuntu-drivers autoinstall; set to e.g. "nvidia-driver-550" to pin)
llm_server_nvidia_driver: ""

# CUDA Toolkit package name
llm_server_cuda_toolkit_package: "cuda-toolkit-12-8"

# Model
llm_server_model_repo: "unsloth/MiniMax-M2.5-GGUF"
llm_server_model_pattern: "*UD-Q5_K_XL*"
llm_server_model_dir: /data/models
llm_server_model_filename: "UD-Q5_K_XL/MiniMax-M2.5-UD-Q5_K_XL-00001-of-00005.gguf"
llm_server_model_shard_count: 5

# Inference parameters
llm_server_gpu_layers: 999
llm_server_cpu_moe: true
llm_server_split_mode: layer
llm_server_tensor_split: "1,1"
llm_server_ctx_size: 65536
llm_server_cache_type_k: f16
llm_server_cache_type_v: f16
llm_server_parallel: 1
llm_server_port: 8080
llm_server_host: "0.0.0.0"

# Open WebUI
llm_server_webui_image: "ghcr.io/open-webui/open-webui:main"
llm_server_webui_port: 3000
llm_server_webui_data_dir: /opt/open-webui
```

### Task 逻辑概览

**`disk.yml`** (VMware 模板克隆后分区扩容):
1. Install `cloud-guest-utils` (provides `growpart`)
2. Detect root device via `findmnt`, extract disk and partition number (compatible with `/dev/sdX` and `/dev/nvmeXnXpX`)
3. `growpart` to expand partition (idempotent: handles NOCHANGE gracefully)
4. `resize2fs` only if partition was actually changed

**`nvidia.yml`**:
1. Install `acl` + `ubuntu-drivers-common` + `build-essential cmake git wget curl numactl htop nvtop python3-pip`
   - `acl` is required for Ansible `become_user` on ext4 filesystems
2. Install NVIDIA driver:
   - If `llm_server_nvidia_driver` is empty → `ubuntu-drivers autoinstall` (with `creates: /usr/bin/nvidia-smi` guard)
   - If set (e.g. `nvidia-driver-550`) → `apt install` the specified package
3. Add NVIDIA CUDA APT repo (if not present)
4. Install `{{ llm_server_cuda_toolkit_package }}` (default: `cuda-toolkit-12-8`, with `creates: /usr/local/cuda/bin/nvcc` guard)
5. `apt-mark hold` the installed NVIDIA driver package (auto-detect actual package name via `dpkg -l`)
6. Handler: reboot if driver was newly installed

**`llama-cpp.yml`**:
1. Clone repo to `{{ llm_server_install_dir }}/ik_llama.cpp`
   - If `llm_server_engine_version` is set → checkout that commit/tag (`force: true`)
   - If empty → use latest (HEAD)
2. Build version tracking: 读取 `build/.ik-version` 标记文件，与当前 `git rev-parse HEAD` 对比
   - 标记缺失或版本不匹配 → 自动删除 `build/` 目录触发重建
3. cmake build with `DGGML_CUDA=ON DGGML_CUDA_F16=ON`
4. 构建完成后写入 `build/.ik-version` 记录当前 commit hash
5. Guard: `creates:` + 版本标记双重保护；版本变更时通知 `Restart llama-server` handler

**`model.yml`**:
1. `pip3 install huggingface_hub`
2. `/usr/local/bin/hf download` with `--include` pattern, run as `llm` user with explicit `PATH` and `HOME` environment
   - Note: `huggingface-cli` was renamed to `hf` in huggingface_hub >= 0.28
   - Uses `async: 7200` + `poll: 30` for large downloads (~162GB)
3. Guard: check if model first shard exists
4. Post-download assert: verify shard files in model subdirectory (searches `{{ model_filename | dirname }}` to avoid counting `.cache/` metadata files)

**`tuning.yml`**:
1. Disable THP: `echo never > /sys/kernel/mm/transparent_hugepage/enabled`
2. Persist THP disable via `tmpfiles.d`
3. Install `linux-tools-common` + kernel-specific `linux-tools` for cpupower
4. Set CPU governor to performance (`failed_when: false` — non-fatal in VMs where hypervisor manages frequency)
5. Persist via cron only if governor was actually set

**`service.yml`**:
1. Grant `llm` user access to model directory
2. Template `llama-server.service.j2` → `/etc/systemd/system/llama-server.service`
3. Enable + start service
4. Notify restart handler on template change

**`webui.yml`**:
1. Ensure Docker role dependency is met (via playbook role ordering)
2. Create data dir
3. Template `docker-compose.yml.j2` with llama-server API endpoint
4. `docker compose pull` + `docker compose up -d`
5. Notify restart handler on template change

### `llama-server.service.j2` — Systemd Unit

所有推理参数从变量注入，核心命令行：
```
ExecStart=/usr/bin/numactl --interleave=all \
    {{ llm_server_install_dir }}/ik_llama.cpp/build/bin/llama-server \
    --model {{ llm_server_model_dir }}/{{ llm_server_model_filename }} \
    -ngl {{ llm_server_gpu_layers }} \
    {% if llm_server_cpu_moe %}--cpu-moe{% endif %} \
    --split-mode {{ llm_server_split_mode }} \
    --tensor-split {{ llm_server_tensor_split }} \
    --jinja \
    --ctx-size {{ llm_server_ctx_size }} \
    ...
```

> **注意**：`--flash-attn` 和 `--fit on` 已从模板中移除。ik_llama.cpp 默认启用 Flash Attention；`--fit on` 不是当前版本的有效参数。

保守重启策略（同原文档）：`RestartSec=30`, `StartLimitBurst=3`, `StartLimitIntervalSec=300`

---

## 3. Ansible Playbook — `deploy-llm-server.yml`

```yaml
- name: Deploy LLM Server
  hosts: llm-server
  become: true
  pre_tasks:
    - name: Set hostname
      hostname:
        name: "{{ inventory_hostname }}"
  roles:
    - common
    - docker       # Required by Open WebUI
    - llm-server

- name: Verify LLM Server Deployment
  hosts: llm-server
  become: true
  tags: [verify]
  tasks:
    - # Check nvidia-smi (assert 2 GPUs detected)
    - # Check systemd llama-server status (assert active + running)
    - # Wait for llama-server port (8080), timeout 120s
    - # HTTP health check: GET /health (retry up to 20×15s = 5min for model loading)
    - # Inference smoke test: POST /v1/chat/completions (max_tokens=256, timeout=300s)
    - #   Assert response has content OR reasoning_content (M2.5 uses <think> mode)
    - # PCIe link verification via lspci (informational — VM shows virtual topology)
    - # Wait for Open WebUI port (3000)
    - # HTTP check: Open WebUI (accept 200/301/302)
    - # Display deployment summary (GPU count, VRAM, model loaded, tok/s, URLs)
```

---

## 4. Inventory 更新

- `ansible/inventory/groups.yml`: 无需修改（`esxi_vms` 已存在，Terraform 动态注册）
- 如有 host-specific overrides → `ansible/inventory/host_vars/llm-server.yml`

---

## 5. 不在 IaC 范围内的手动步骤

| 步骤 | 原因 |
|------|------|
| BIOS 设置（VT-d, Above 4G Decoding） | 物理操作 |
| ESXi PCI Passthrough Toggle + 重启 | 一次性 UI 操作 |
| Ubuntu OS 安装（或模板制作） | 前置条件 |
| `--n-cpu-moe` 精细调参 | 需要人工观察 nvidia-smi |
| 首次验证流程（8K→16K→64K 逐级） | 人工验收 |

这些保留在 `minimax-llama.md` 作为参考文档。

---

## 6. 文件清单

| 操作 | 文件路径 |
|------|---------|
| 修改 | `terraform/esxi/variables.tf` |
| 新建 | `terraform/esxi/llm-server.tf` |
| 新建 | `ansible/roles/llm-server/defaults/main.yml` |
| 新建 | `ansible/roles/llm-server/tasks/main.yml` |
| 新建 | `ansible/roles/llm-server/tasks/disk.yml` |
| 新建 | `ansible/roles/llm-server/tasks/nvidia.yml` |
| 新建 | `ansible/roles/llm-server/tasks/llama-cpp.yml` |
| 新建 | `ansible/roles/llm-server/tasks/model.yml` |
| 新建 | `ansible/roles/llm-server/tasks/tuning.yml` |
| 新建 | `ansible/roles/llm-server/tasks/service.yml` |
| 新建 | `ansible/roles/llm-server/tasks/webui.yml` |
| 新建 | `ansible/roles/llm-server/templates/llama-server.service.j2` |
| 新建 | `ansible/roles/llm-server/templates/docker-compose.yml.j2` |
| 新建 | `ansible/roles/llm-server/handlers/main.yml` |
| 新建 | `ansible/playbooks/deploy-llm-server.yml` |

---

## 7. 验证方式

```bash
# Terraform
cd terraform/esxi && terraform validate && terraform fmt -check

# Ansible
cd ansible && ansible-playbook playbooks/deploy-llm-server.yml --syntax-check

# Dry run (需要目标 VM 可达)
ansible-playbook playbooks/deploy-llm-server.yml --check --diff

# Deploy
ansible-playbook playbooks/deploy-llm-server.yml

# Health check only
ansible-playbook playbooks/deploy-llm-server.yml --tags verify
```

---

## 8. 性能验证与基准测试

Ansible verify play（`--tags verify`）覆盖了自动化验证，但以下手动测试和基准方法用于人工验收和版本升级前后对比。详细命令和记录模板见 [`minimax-llama.md` 6.4-6.5 节](../guides/minimax-llama.md)。

### 自动化验证（Verify Play 覆盖范围）

| 检查项 | 方式 | 通过标准 |
|--------|------|---------|
| GPU 识别 | `nvidia-smi --query-gpu` | 2 张 RTX 3090 |
| 服务状态 | `systemd` fact | `ActiveState == active` |
| 端口就绪 | `wait_for` port 8080 | 120s 内可达 |
| 健康检查 | `GET /health` | 200 OK（重试 20×15s，覆盖模型加载时间） |
| 推理冒烟 | `POST /v1/chat/completions` | `content` 或 `reasoning_content` 非空 |
| Open WebUI | `GET :3000` | 200/301/302 |

### 手动验证补充项

以下项目不在自动化中，需要人工确认：

1. **启动日志检查**：`journalctl -u llama-server | head -100`
   - CPU-MoE 层分配是否生效（`ffn_*_exps.weight buffer type overriden to CPU`）
   - 双 GPU 层分配（CUDA0/CUDA1 buffer size）
   - KV Cache 分配（每卡 ~8GB）
2. **GPU 利用率实时观测**：推理时 `watch -n 0.5 nvidia-smi`，确认双卡都有活动
3. **NUMA 内存均匀性**：`numastat -p $(pgrep llama-server)`

### 性能基准测试

升级 ik_llama.cpp 版本或调整推理参数后，使用以下标准测试建立对比基线：

| 测试场景 | 关键指标 | 参考值 (f7923739, UD-Q5_K_XL, 2×3090) |
|----------|---------|---------------------------------------|
| 短 prompt 生成 | Token Generation | ~6.5 tok/s |
| 短 prompt prefill | Prompt Processing | ~16 tok/s |
| 长 prompt (~4K tokens) | Prompt Processing | 需实测 |
| GPU VRAM 峰值 | 每卡占用 | ~9.7 GB |

标准测试命令、长 prompt 生成脚本、测试记录模板见 [`minimax-llama.md` 6.5 节](../guides/minimax-llama.md)。

---

## 9. 部署实测修正记录

首次实际部署（2025-02）中发现并修正的问题：

| 问题 | 原因 | 修正 |
|------|------|------|
| HuggingFace 仓库名错误 | `unsloth/MiniMax-2.5-GGUF` 不存在，正确为 `unsloth/MiniMax-M2.5-GGUF`（带 "M"） | 更新 defaults 中的 `model_repo` |
| UD-Q5_K_M 量化变体不存在 | Unsloth 仓库无此变体，实际可用为 UD-Q5_K_XL（5 分片，~162GB） | 更新 `model_pattern`、`model_filename`、`model_shard_count` |
| `huggingface-cli` 命令不存在 | huggingface_hub >= 0.28 将 CLI 从 `huggingface-cli` 重命名为 `hf` | 改用 `/usr/local/bin/hf` |
| 模型下载作为 `llm` 用户失败 | 系统用户 shell 为 `/usr/sbin/nologin`，Ansible `become_user` + `async` 需要可用 shell | 改为 `/bin/bash`，添加显式 `PATH`/`HOME` 环境变量 |
| `become_user` 权限错误 | ext4 文件系统上 Ansible `become_user` 需要 POSIX ACL 支持 | 添加 `acl` 包到 nvidia.yml 依赖 |
| Shard 计数误判（10 vs 5） | `ansible.builtin.find` 搜索整个 model_dir 会匹配 `.cache/` 下的 `.gguf.metadata` 文件 | 改为搜索特定子目录 `{{ model_filename \| dirname }}` |
| `--fit on` 导致 llama-server 启动失败 | 当前 ik_llama.cpp 版本不支持此参数 | 从 service 模板中移除 |
| `--flash-attn` 冗余 | ik_llama.cpp 已默认启用 Flash Attention | 从 service 模板中移除 |
| Inference smoke test 误报空响应 | MiniMax-M2.5 使用 `<think>` 推理模式，`content` 为空但 `reasoning_content` 有内容 | 修改 assertion 同时检查两个字段；`max_tokens` 从 32 提升到 256 |
| CPU governor 设置失败 (rc=237) | ESXi VM 中 CPU 频率由 hypervisor 管理，guest 无法控制 | 改为 `failed_when: false`，添加 warning 提示 |
| VMware 模板克隆后磁盘未扩展 | 模板保留原始分区表，500GB 虚拟磁盘但根分区可能只有几十 GB | 新增 `disk.yml` 任务自动扩展 |
| CUDA Toolkit 版本 | 原计划 12-4，实际安装 12-8 | 参数化为 `llm_server_cuda_toolkit_package` |
| ik_llama.cpp 最新版产生垃圾输出 | commit `528cadb0`（GLM-5 support）后引入 MiniMax M2.5 MoE 推理回归，输出重复无意义 token（`\|Bild\|Bild\|`） | 固定 `llm_server_engine_version: "f7923739"`；新增 `build/.ik-version` 版本标记自动检测不匹配并触发重建 |

---

## 10. Codex 审核修订记录

### 第一轮：方案设计审核（部署前）

经 Codex (gpt-5.3-codex, reasoning=high) 审核后的采纳/不采纳决定：

#### 采纳

| 编号 | 审核意见 | 修订 |
|------|---------|------|
| P0-2 | MMIO 64GB 对双 3090 可能不足 | 参数化 `llm_server_mmio_size_gb`（Terraform 变量，默认 64，可调 128） |
| P1-5 | `ubuntu-drivers autoinstall` 不可预测 | 加 `llm_server_nvidia_driver` 可选变量（空=autoinstall，设值=固定版本）；`apt-mark hold` 改为自动检测实际包名 |
| P2-6a | 缺少 Open WebUI 镜像 tag 参数 | 加 `llm_server_webui_image` 变量 |
| P2-6b | 缺少 llama.cpp 版本锁定选项 | 加 `llm_server_engine_version` 变量（空=latest，设值=commit hash） |
| P2-8 | 验证缺少推理 smoke test | Verify play 增加 `/v1/chat/completions` API 调用验证 |

#### 不采纳

| 编号 | 审核意见 | 理由 |
|------|---------|------|
| P0-1 | GPU PCI 应纳入 Terraform 声明式管理 | vSphere provider v2.15.0 bug 会触发 VM 重建；与 repo 现有 PBS HBA passthrough 模式一致 |
| P1-3 | llama-cpp 构建应基于版本+参数变化触发 | 初期不采纳。后因版本回归（垃圾输出问题）改为采纳：增加 `build/.ik-version` 版本标记，自动检测不匹配并触发重建 |
| P1-4 | 模型下载缺完整性校验 | `hf download` 内置 SHA256 校验和断点续传；增加了 shard 文件数量 assert 作为轻量补充 |
| P2-7 | 500GB 磁盘偏紧 | 计算：模型 162GB + 编译/Docker/OS ≈ 190GB，余量 310GB 充裕；磁盘大小已参数化可调 |

### 第二轮：部署后代码审核

经 Codex (gpt-5.3-codex, reasoning=high) 对部署后全量代码审核：

#### 采纳

| 编号 | 审核意见 | 修订 |
|------|---------|------|
| P0-2 | disk.yml 在 NVMe 设备上解析磁盘/分区号出错 | regex 改为 `p?[0-9]+$` 兼容 `/dev/nvme0n1p2` |
| P1-3 | verify play `success_msg` 直接访问 `usage.total_tokens` 缺 default | 添加 `default({})` 防御 |
| P2-1 | cpupower `changed_when: rc == 0` 噪声 | 改为 `changed_when: false` |
| P2-3 | 文档 CUDA 版本与默认值不一致 | 同步为 `cuda-toolkit-12-8` |

#### 不采纳

| 编号 | 审核意见 | 理由 |
|------|---------|------|
| P0-1 | postCreateCommand 并行执行有顺序依赖 | devcontainer 配置不在 llm-server 范围内 |
| P1-1 | resize2fs 硬编码对 XFS 不兼容 | Ubuntu 24.04 模板使用 ext4，过度工程 |
| P1-2 | llm 用户改 /bin/bash 扩大登录面 | become_user + async + hf CLI 必须要可用 shell |
| P1-4 | ~/.claude 挂载 + rm -rf 数据风险 | 有意为之的设计（host/container 共享 Claude memory） |
| P2-2 | PCIe verify 仅打印不断言 | VM passthrough 的 lspci 值是虚拟的，断言无意义 |
