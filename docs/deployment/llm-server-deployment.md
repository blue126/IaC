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
│   ├── nvidia.yml             # NVIDIA driver + CUDA Toolkit
│   ├── llama-cpp.yml          # Compile ik_llama.cpp
│   ├── model.yml              # Download GGUF model via huggingface-cli
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
# System user
llm_server_user: llm

# Engine
llm_server_engine_repo: "https://github.com/ikawrakow/ik_llama.cpp"
llm_server_engine_version: ""  # Empty = latest (recommended during early iteration); set to commit hash to pin
llm_server_install_dir: /opt/llm-server

# NVIDIA driver (empty = ubuntu-drivers autoinstall; set to e.g. "nvidia-driver-550" to pin)
llm_server_nvidia_driver: ""

# Model
llm_server_model_repo: "unsloth/MiniMax-2.5-GGUF"
llm_server_model_pattern: "*UD-Q5_K_M*"
llm_server_model_dir: /data/models

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

**`nvidia.yml`**:
1. Install `ubuntu-drivers-common` + `build-essential cmake git wget curl numactl htop nvtop python3-pip`
2. Install NVIDIA driver:
   - If `llm_server_nvidia_driver` is empty → `ubuntu-drivers autoinstall` (with `creates: /usr/bin/nvidia-smi` guard)
   - If set (e.g. `nvidia-driver-550`) → `apt install` the specified package
3. Add NVIDIA CUDA APT repo (if not present)
4. Install `cuda-toolkit-12-4` (with `creates: /usr/local/cuda/bin/nvcc` guard)
5. `apt-mark hold` the installed NVIDIA driver package (auto-detect actual package name via `dpkg -l`)
6. Handler: reboot if driver was newly installed

**`llama-cpp.yml`**:
1. Clone repo to `{{ llm_server_install_dir }}/ik_llama.cpp`
   - If `llm_server_engine_version` is set → checkout that commit/tag
   - If empty → use latest (HEAD)
2. cmake build with `DGGML_CUDA=ON DGGML_CUDA_F16=ON`
3. Guard: `creates: {{ llm_server_install_dir }}/ik_llama.cpp/build/bin/llama-server`

**`model.yml`**:
1. `pip3 install huggingface_hub`
2. `huggingface-cli download` with `--include` pattern (tool has built-in resume + SHA256 verification)
3. Guard: check if model directory already has `.gguf` files
4. Post-download assert: verify expected number of `.gguf` shard files exist

**`tuning.yml`**:
1. Disable THP: `echo never > /sys/kernel/mm/transparent_hugepage/enabled`
2. Install `linux-tools-common` for cpupower
3. Set CPU governor to performance
4. Sysctl/tmpfiles for persistence across reboot

**`service.yml`**:
1. Create system user `llm`
2. Template `llama-server.service.j2` → `/etc/systemd/system/llama-server.service`
3. Enable + start service
4. Notify restart handler on template change

**`webui.yml`**:
1. Ensure Docker role dependency is met (via playbook role ordering)
2. Create data dir
3. Template `docker-compose.yml.j2` with llama-server API endpoint
4. `docker compose up -d`

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
    --fit on --jinja --flash-attn \
    --ctx-size {{ llm_server_ctx_size }} \
    ...
```

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
    - # Check systemd llama-server status
    - # Wait for llama-server port (8080)
    - # HTTP health check: GET /health
    - # Inference smoke test: POST /v1/chat/completions with fixed prompt, assert 200 + non-empty content
    - # Wait for Open WebUI port (3000)
    - # HTTP check: Open WebUI
    - # Display deployment summary (GPU count, VRAM, model loaded, URLs)
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

## 8. Codex 审核修订记录

经 Codex (gpt-5.3-codex, reasoning=high) 审核后的采纳/不采纳决定：

### 采纳

| 编号 | 审核意见 | 修订 |
|------|---------|------|
| P0-2 | MMIO 64GB 对双 3090 可能不足 | 参数化 `llm_server_mmio_size_gb`（Terraform 变量，默认 64，可调 128） |
| P1-5 | `ubuntu-drivers autoinstall` 不可预测 | 加 `llm_server_nvidia_driver` 可选变量（空=autoinstall，设值=固定版本）；`apt-mark hold` 改为自动检测实际包名 |
| P2-6a | 缺少 Open WebUI 镜像 tag 参数 | 加 `llm_server_webui_image` 变量 |
| P2-6b | 缺少 llama.cpp 版本锁定选项 | 加 `llm_server_engine_version` 变量（空=latest，设值=commit hash） |
| P2-8 | 验证缺少推理 smoke test | Verify play 增加 `/v1/chat/completions` API 调用验证 |

### 不采纳

| 编号 | 审核意见 | 理由 |
|------|---------|------|
| P0-1 | GPU PCI 应纳入 Terraform 声明式管理 | vSphere provider v2.15.0 bug 会触发 VM 重建；与 repo 现有 PBS HBA passthrough 模式一致 |
| P1-3 | llama-cpp 构建应基于版本+参数变化触发 | 文档明确"不要过早锁定版本"；`creates:` guard 当前阶段够用，需更新时手动清 build |
| P1-4 | 模型下载缺完整性校验 | `huggingface-cli download` 内置 SHA256 校验和断点续传；增加了 shard 文件数量 assert 作为轻量补充 |
| P2-7 | 500GB 磁盘偏紧 | 计算：模型 145GB + 编译/Docker/OS ≈ 172GB，余量 328GB 充裕；磁盘大小已参数化可调 |
