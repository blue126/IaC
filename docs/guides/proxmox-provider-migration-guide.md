# Proxmox Terraform Provider 迁移实战指南

> 从 telmate/proxmox 迁移到 bpg/proxmox 的完整记录

## 1. 迁移前的问题

在使用 `telmate/proxmox` provider 管理 Proxmox 基础设施的过程中，我们遇到了多个持续性问题：

### 1.1 Tags Drift（永久性 Plan 漂移）

这是触发迁移的最直接原因。telmate provider 在处理 VM/LXC tags 时存在 bug：API 返回的 tags 值带有空格分隔符 `" "`，但 provider 发送时用分号 `";"`，导致**每次 `terraform plan` 都会显示 tags 变更**，即使实际没有任何改动。这意味着我们永远无法达到一个 clean plan。

### 1.2 Destroy/Recreate 过于激进

telmate provider 对很多属性标记了 ForceNew，小改动（如调整 Cloud-Init 配置）容易触发 VM 销毁重建，而不是 in-place 更新。这在生产环境中是不可接受的。

### 1.3 维护状态停滞

telmate/proxmox 已进入仅维护模式，新功能开发基本停止。Proxmox 8.x 的新特性（如 SDN、PCI/USB 直通增强）缺乏支持。

### 1.4 Cloud-Init 偶发 Bug

Cloud-Init 磁盘的顺序处理偶尔出错，导致初始化失败需要手动干预。

## 2. 为什么选择 bpg/proxmox

| 特性 | bpg/proxmox | telmate/proxmox |
|------|-------------|-----------------|
| 维护状态 | 活跃开发 | 仅维护 |
| Proxmox 8.x | 完整优化 | 基本支持 |
| Tags Drift | 无 | 严重 |
| In-place 更新 | 智能（少触发重建） | 容易重建 |
| Cloud-Init | 稳定 | 偶有 bug |
| SDN/PCI 直通 | 支持 | 无/困难 |
| 文档质量 | 详细 | 一般 |

## 3. 迁移方案设计

### 3.1 迁移范围

涉及 2 个模块和 8 个资源：

| 模块 | 资源类型 | 资源 |
|------|---------|------|
| `proxmox-vm` | VM (3) | immich (101), rustdesk (102), netbox (104) |
| `proxmox-lxc` | LXC (5) | anki (100), homepage (103), caddy (105), n8n (106), jenkins (107) |

### 3.2 核心策略：零停机迁移

选择 **state 迁移 + import** 方式而非销毁重建，确保：
- 所有 VM/LXC 保持运行
- 不丢失任何数据
- IP 地址和网络配置不变
- Ansible inventory 兼容性不受影响

### 3.3 迁移步骤概览

1. 备份 Terraform state
2. 重写 provider、module 代码
3. Code review（对抗性审查）
4. 从 state 中移除旧 telmate 资源
5. 以 bpg 格式 import 现有资源
6. 解决 drift，达到 clean plan
7. Apply 并验证

## 4. 实施过程

### 4.1 代码重写

#### Provider 配置

```hcl
# 旧：telmate
provider "proxmox" {
  pm_api_url          = var.pm_api_url
  pm_api_token_id     = var.pm_api_token_id
  pm_api_token_secret = var.pm_api_token_secret
  pm_tls_insecure     = true
}

# 新：bpg
provider "proxmox" {
  endpoint  = var.pm_api_url
  api_token = "${var.pm_api_token_id}=${var.pm_api_token_secret}"
  insecure  = true
  ssh {
    agent = true
  }
}
```

#### VM 模块核心变更

资源类型从 `proxmox_vm_qemu` 改为 `proxmox_virtual_environment_vm`，主要差异：

- **克隆**：telmate 用模板名称字符串，bpg 用 VM ID。我们通过 `data.proxmox_virtual_environment_vms` 动态查找模板 ID 实现
- **嵌套结构**：`cores` → `cpu { cores }`, `memory` → `memory { dedicated }` 等
- **Cloud-Init**：`ipconfig0` 字符串 → 结构化的 `initialization { ip_config { ipv4 {} } }`
- **EFI 磁盘**：需要显式声明 `efi_disk {}` 块（使用 dynamic block 按 bios 类型条件创建）
- **SSH Keys**：从多行 heredoc 字符串改为 `list(string)` 类型

#### LXC 模块核心变更

资源类型从 `proxmox_lxc` 改为 `proxmox_virtual_environment_container`，结构变化类似 VM 模块。

### 4.2 Code Review（10 项发现）

代码重写后进行了一次对抗性审查，发现并修复了 10 个问题：

| # | 问题 | 严重性 | 说明 |
|---|------|--------|------|
| F1 | cicustom 解析遗漏 | 高 | 未剥离 `user=` 前缀 |
| F2 | tags 空字符串 split bug | 中 | `split(";", "")` 返回 `[""]` 而非 `[]` |
| F3 | 模板查找无保护 | 高 | 模板不存在时会 crash |
| F4 | 迁移脚本 import 格式错误 | 高 | `node/qemu/vmid` 应为 `node/vmid` |
| F5 | 孤立变量未清理 | 低 | telmate 遗留变量 |
| F6 | pve-cluster.tf 硬编码密码 | 高 | SSH 密码明文写在代码中 |
| F7 | LXC outputs 引用错误 | 中 | bpg 不支持旧的输出路径 |
| F8 | 串口控制台缺失 | 中 | 需要 `serial_device` + `vga { type = "serial0" }` |
| F9 | CPU type 硬编码 | 低 | 提取为变量 |
| F10 | SSH keys 类型不匹配 | 高 | bpg 需要 `list(string)` 而非 heredoc 字符串 |

### 4.3 安全加固

迁移中顺带完成的安全改进：

- `pve-cluster.tf` 中硬编码的 SSH 密码（`Admin123...`）替换为 Vault 变量引用
- `terraform.tfvars` 中的 API token 和 SSH key 移除，改由 `secrets.auto.tfvars`（gitignored）管理
- `scripts/get-secrets.sh` 更新，新增 `proxmox_ssh_password` 提取

### 4.4 State 迁移

#### 困难：schema 不兼容

`terraform state rm` 无法直接移除 telmate 资源——因为 provider 已切换到 bpg，旧 schema 无法解析。

**解决方案**：直接用 Python 操作 state JSON 文件，绕过 provider schema 校验。

```bash
# 1. 导出 state
terraform state pull > state.json

# 2. Python 脚本移除旧资源
python3 remove_telmate_resources.py

# 3. 推送清理后的 state
terraform state push state.json

# 4. Import 所有资源（格式：node/vmid）
terraform import 'module.anki.proxmox_virtual_environment_container.lxc' 'pve0/100'
terraform import 'module.immich.proxmox_virtual_environment_vm.vm' 'pve0/101'
# ... 其余 6 个资源
```

#### 迁移脚本的坑

原先准备的 `migrate_to_bpg.sh` 脚本使用了错误的 import 格式（`node/qemu/vmid`），实际 bpg provider 的格式是 `node/vmid`。这在 Code Review 中被发现并修正。

### 4.5 SSH Keys 类型重构

telmate 使用多行 heredoc 字符串传递 SSH keys：

```hcl
sshkeys = <<EOF
ssh-ed25519 AAAA...
ssh-rsa AAAA...
EOF
```

bpg 需要 `list(string)` 格式：

```hcl
sshkeys = ["ssh-ed25519 AAAA...", "ssh-rsa AAAA..."]
```

**影响链**：这个类型变更需要贯穿整个变量传递链——从 `scripts/get-secrets.sh`（Ansible Vault → tfvars 生成）到 root module `variables.tf`，到 VM/LXC module 的 `variables.tf` 和 `main.tf`。

`get-secrets.sh` 中使用 Jinja2 模板将多行 YAML 字符串转换为 Terraform list：

```jinja2
sshkeys = [{% set keys = vault_sshkeys.strip().splitlines() | select | list %}{% for key in keys %}"{{ key.strip() }}"{% if not loop.last %}, {% endif %}{% endfor %}]
```

## 5. 迁移后问题修复

迁移后遇到了多个需要逐一排查和修复的问题。详细的症状、诊断步骤和解决方案记录在 [Terraform 故障排查文档](../troubleshooting/terraform-issues.md) 中（问题 9-13），以下是概要。

### 5.1 EFI Disk pre_enrolled_keys 不一致

rustdesk VM 的 `efi_disk.pre_enrolled_keys` 生产环境为 `false`，代码中为 `true`。在 PVE 上手动修正使其一致。

### 5.2 Machine Type 转换问题

telmate 使用 `"pc"` 作为 machine type，确认 bpg 直接接受 `"pc"`，移除不必要的转换逻辑。

### 5.3 Apply 超时与锁文件残留

Apply 时 rustdesk VM 从关机状态启动，provider 等待 QEMU Guest Agent 返回 IP（默认超时 15 分钟）。同时 PVE 节点上存在之前操作残留的空锁文件，阻塞了 API 调用。清理锁文件后问题解决。详见[问题 9、10](../troubleshooting/terraform-issues.md#问题-9-apply-超时--vm-启动后-provider-长时间等待)。

### 5.4 State 迁移 — 旧资源无法移除

Provider 切换后 `terraform state rm` 无法解析旧 schema。通过直接操作 state JSON 文件绕过。详见[问题 13](../troubleshooting/terraform-issues.md#问题-13-state-迁移后-terraform-state-rm-无法移除旧资源)。

### 5.5 ignore_changes 逐项审查

迁移后 VM 和 LXC 模块使用了多项 `ignore_changes` 来避免 state 不一致导致的重建。我们逐一审查了每个被 ignore 的属性，能移除的全部移除：

| ignore_changes 项 | 决策 | 方法 | 详情 |
|-------------------|------|------|------|
| VM `tags` | 移除 | 类型改为 `list(string)` | — |
| VM `clone` | 保留 | 写入 state 会影响 30+ 属性的 refresh | — |
| LXC `unprivileged` | 移除 | 修补 state（provider bug） | [问题 11](../troubleshooting/terraform-issues.md#问题-11-lxc-ignore_changes-中-unprivileged-的-provider-bug) |
| LXC `template_file_id` | 移除 | 修补 state（containerRead 保留现有值） | [问题 12](../troubleshooting/terraform-issues.md#问题-12-lxc-template_file_id-在-state-中为-null) |
| LXC `user_account` | 保留 | ForceNew + API 不返回 | — |

## 6. 经验总结

### 6.1 State 迁移是最大挑战

代码重写相对直接——两个 provider 的属性有明确的映射关系。真正困难的是 state 迁移：

- Provider 切换后旧 schema 无法解析，`terraform state rm` 失败
- Import 后 state 中缺失大量属性（API 不返回 create-only 参数）
- 需要手动修补 state JSON 来填充 provider bug 导致的缺失值
- 每个 `ignore_changes` 都需要验证根因：是 API 限制、provider bug，还是可以修复的

### 6.2 对抗性 Code Review 很有价值

10 个发现中有 4 个是高严重性——包括硬编码密码、import 格式错误、模板查找 crash。这些如果在 apply 时才发现，可能导致资源意外销毁或安全漏洞。

### 6.3 不要盲目接受 ignore_changes

迁移后第一版代码有 6 个 `ignore_changes` 项。通过逐项验证，我们将其减少到 2 个，且每个保留项都有明确的技术原因和注释说明。盲目 ignore 会隐藏真实问题——比如 `unprivileged` 的 provider bug，如果不深入调查就会一直留在 ignore 列表里。

### 6.4 Provider 源码是最终参考

文档不够详细时，直接阅读 provider Go 源码是最可靠的方式。例如：

- `containerRead` 中 `unprivileged` 的条件读取逻辑暴露了 provider bug
- `vmReadCustom` 中 `len(clone) > 0` 的 30 处条件分支解释了为什么不能随意注入 clone 到 state
- `template_file_id` 在 read 中从 state copy 回写的行为，证明了手动修补 state 的可行性

### 6.5 注意 Proxmox 锁文件残留

Terraform provider（无论是 telmate 还是 bpg）通过 Proxmox API 操作 VM 时，PVE 会在 `/var/lock/qemu-server/` 下创建锁文件。但 **provider 不负责清理锁文件，PVE 也没有自动回收空锁文件的机制**，导致操作完成后锁文件残留。

我们在迁移过程中发现 PVE 节点上存在多个残留锁文件：

```
-rw-r--r-- 1 root root 0 Jan 27 12:11 lock-101.conf
-rw-r--r-- 1 root root 0 Jan 27 12:11 lock-102.conf
-rw-r--r-- 1 root root 0 Jan 27 12:11 lock-104.conf
-rw-r--r-- 1 root root 0 Jan 27 12:11 lock--1.conf
-rw-r--r-- 1 root root 0 Jan 28 17:31 lock-9000.conf
```

全部是空文件（正常的 PVE 锁文件会写入操作类型如 `backup`、`migrate`）。通过 git log 追溯，Jan 27 对应的 commit 是 `chore: migrate terraform state to HCP Terraform`——当时执行 `terraform init -migrate-state` 触发了对所有资源的 refresh，telmate provider 通过 API 查询 VM 状态时 PVE 创建了锁文件但未清理。`lock--1.conf` 中的 `-1` 是 provider 使用的临时/默认 VM ID。

**影响**：残留锁文件会导致后续 `terraform apply` 报错 `can't lock file ... got timeout`。实际上我们在 apply rustdesk 变更时就遇到了这个问题——第二次 apply 因为 Jan 27 残留的 `lock-102.conf` 而失败。

**建议**：每次执行大规模 Terraform 操作后，检查并清理 PVE 节点上的残留锁文件：

```bash
ls -la /var/lock/qemu-server/lock-*.conf
# 确认文件内容为空后安全删除
rm /var/lock/qemu-server/lock-*.conf
```

### 6.6 安全债务要随迁移一起清理

迁移是审查安全实践的好时机。我们顺带发现并修复了硬编码密码、tfvars 中的明文 token 等问题，将所有敏感信息统一到 Ansible Vault 管理。

## 7. 迁移后状态

### 最终 Plan

```
Plan: 0 to add, 0 to change, 0 to destroy.
```

所有 8 个资源（3 VM + 5 LXC）成功迁移，零停机，无数据丢失。

### 代码改进

- Provider: telmate/proxmox 3.x → bpg/proxmox 0.70.0
- SSH keys: heredoc 字符串 → `list(string)` 全链路类型安全
- Tags: 分号分隔字符串 → `list(string)` 原生类型
- 安全: 所有敏感信息通过 Ansible Vault + get-secrets.sh 管理
- ignore_changes: 6 项 → 2 项（每项有注释说明原因）

### 文件变更清单

| 文件 | 变更类型 |
|------|---------|
| `terraform/proxmox/versions.tf` | Provider source 切换 |
| `terraform/proxmox/provider.tf` | 认证方式重写 |
| `terraform/proxmox/variables.tf` | sshkeys 类型改为 list(string) |
| `terraform/proxmox/pve-cluster.tf` | 硬编码密码改为 vault 变量 |
| `terraform/proxmox/terraform.tfvars` | 移除敏感值 |
| `terraform/modules/proxmox-vm/main.tf` | 资源重写 |
| `terraform/modules/proxmox-vm/variables.tf` | 新增 cpu_type/vga_type，tags 改类型 |
| `terraform/modules/proxmox-vm/outputs.tf` | 输出引用更新 |
| `terraform/modules/proxmox-lxc/main.tf` | 资源重写 |
| `terraform/modules/proxmox-lxc/variables.tf` | sshkeys 改类型 |
| `terraform/modules/proxmox-lxc/outputs.tf` | 输出引用更新 |
| `scripts/get-secrets.sh` | sshkeys 生成改为 list 格式 |

## 8. 参考资料

- [bpg/proxmox 官方文档](https://registry.terraform.io/providers/bpg/proxmox/latest/docs)
- [bpg/proxmox GitHub](https://github.com/bpg/terraform-provider-proxmox)
- [迁移技术方案](../improvement/implemented/proxmox-provider-migration.md)（本仓库）
- [bpg provider 源码 - container.go](https://github.com/bpg/terraform-provider-proxmox/blob/main/proxmoxtf/resource/container/container.go)
- [bpg provider 源码 - vm.go](https://github.com/bpg/terraform-provider-proxmox/blob/main/proxmoxtf/resource/vm/vm.go)
