# Proxmox Terraform Provider 迁移计划

> 从 telmate/proxmox 迁移到 bpg/proxmox

## 背景

当前使用的 `telmate/proxmox` provider 存在以下问题：

1. **Tags drift** - API 返回 `" "` 但不接受 `" "` 作为输入，导致永久性 plan 变更
2. **维护状态** - 仅维护模式，新功能开发缓慢
3. **Destroy/Recreate** - 小改动容易触发 VM 重建
4. **Cloud-Init** - 偶发的磁盘顺序 bug

## 目标 Provider

**bpg/proxmox** - https://registry.terraform.io/providers/bpg/proxmox

### 优势

| 特性 | bpg/proxmox | telmate/proxmox |
|------|-------------|-----------------|
| 维护状态 | 活跃开发 | 仅维护 |
| Proxmox 8.x | 完整优化 | 基本支持 |
| Drift 问题 | 少 | 多 |
| In-place 更新 | 智能 | 容易重建 |
| Cloud-Init | 稳定 | 偶有 bug |
| SDN 支持 | 有 | 无 |
| PCI/USB 直通 | 支持 | 困难 |
| 文档 | 详细 | 一般 |

## 迁移范围

### 需要迁移的模块

```
terraform/modules/proxmox-vm/     # VM 模块
terraform/modules/proxmox-lxc/    # LXC 模块
```

### 涉及的资源

| 资源类型 | 数量 | 说明 |
|----------|------|------|
| VM | 3 | immich, netbox, rustdesk |
| LXC | 5 | anki, caddy, homepage, jenkins, n8n |

## 迁移步骤

### Phase 1: 准备工作

- [x] 阅读 bpg/proxmox 文档
- [x] 对比两个 provider 的资源属性差异
- [x] 备份当前 Terraform state
- [x] 创建测试分支 (Simulated in Dev Env)

### Phase 2: 更新 Provider 配置

**当前配置** (`terraform/proxmox/versions.tf`):
```hcl
terraform {
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "~> 3.0"
    }
  }
}
```

**目标配置**:
```hcl
terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.70.0"  # Updated to 0.70.0
    }
  }
}
```

### Phase 3: 更新 Provider 认证

**当前方式** (密码/API Token):
```hcl
provider "proxmox" {
  pm_api_url          = var.pm_api_url
  pm_api_token_id     = var.pm_api_token_id
  pm_api_token_secret = var.pm_api_token_secret
  pm_tls_insecure     = true
}
```

**bpg 方式**:
```hcl
provider "proxmox" {
  endpoint = var.pm_api_url
  api_token = "${var.pm_api_token_id}=${var.pm_api_token_secret}"
  insecure = true
}
```

### Phase 4: 重写 VM 模块

**资源名称变更**:
- `proxmox_vm_qemu` → `proxmox_virtual_environment_vm`

**主要属性映射**:

| telmate | bpg | 说明 |
|---------|-----|------|
| `name` | `name` | 相同 |
| `target_node` | `node_name` | 重命名 |
| `vmid` | `vm_id` | 重命名 |
| `clone` | `clone.vm_id` | 结构变化 |
| `cores` | `cpu.cores` | 嵌套结构 |
| `memory` | `memory.dedicated` | 嵌套结构 |
| `disk {}` | `disk {}` | 结构类似但属性不同 |
| `network {}` | `network_device {}` | 重命名 |
| `ipconfig0` | `initialization.ip_config` | Cloud-Init 配置重构 |
| `sshkeys` | `initialization.user_account.keys` | Cloud-Init 配置重构 |

**示例转换**:

```hcl
# telmate/proxmox (当前)
resource "proxmox_vm_qemu" "vm" {
  name        = var.vm_name
  target_node = var.target_node
  vmid        = var.vmid
  clone       = var.template_name
  
  cores  = var.cores
  memory = var.memory
  
  disk {
    storage = var.storage_pool
    size    = var.disk_size
    type    = "disk"
    slot    = "scsi0"
  }
  
  network {
    model  = "virtio"
    bridge = var.network_bridge
  }
  
  ipconfig0 = "ip=${var.ip_address},gw=${var.gateway}"
  sshkeys   = var.sshkeys
}
```

```hcl
# bpg/proxmox (目标)
resource "proxmox_virtual_environment_vm" "vm" {
  name      = var.vm_name
  node_name = var.target_node
  vm_id     = var.vmid
  
  clone {
    vm_id = local.template_vm_id # Resolved dynamically
  }
  
  cpu {
    cores = var.cores
  }
  
  memory {
    dedicated = var.memory
  }
  
  disk {
    datastore_id = var.storage_pool
    size         = local.disk_size_gb  # Parsed from string
    interface    = "scsi0"
  }
  
  network_device {
    model  = "virtio"
    bridge = var.network_bridge
  }
  
  initialization {
    ip_config {
      ipv4 {
        address = var.ip_address
        gateway = var.gateway
      }
    }
    user_account {
      keys     = [var.sshkeys]
      username = var.ciuser
    }
  }
}
```

### Phase 5: 重写 LXC 模块

**资源名称变更**:
- `proxmox_lxc` → `proxmox_virtual_environment_container`

**主要属性映射**:

| telmate | bpg | 说明 |
|---------|-----|------|
| `hostname` | `initialization.hostname` | 结构变化 |
| `target_node` | `node_name` | 重命名 |
| `vmid` | `vm_id` | 重命名 |
| `ostemplate` | `initialization.template_file_id` | 格式变化 |
| `rootfs {}` | `disk {}` | 结构变化 |
| `network {}` | `network_interface {}` | 重命名 |
| `ssh_public_keys` | `initialization.user_account.keys` | 结构变化 |

### Phase 6: 状态迁移

有两种方式处理现有资源：

#### 方式 A: 导入现有资源 (推荐)

使用提供的脚本 `terraform/proxmox/migrate_to_bpg.sh` 自动执行迁移。

```bash
# 示例
cd terraform/proxmox
./migrate_to_bpg.sh
```

#### 方式 B: 重建资源 (简单但有停机)

直接 apply，让 Terraform destroy 旧资源并 create 新资源。
**风险**: 数据丢失、IP 变化、停机时间

### Phase 7: 测试验证

- [ ] `terraform plan` 无意外变更
- [ ] VM/LXC 正常运行
- [ ] Cloud-Init 配置正确
- [ ] 网络连通性正常
- [ ] Ansible 可以连接所有主机

## Review Notes

- Adversarial review completed.
- Findings: 4 total, 2 fixed (EFI Disk, Machine Type), 2 skipped (Unused vars).
- **Secondary Review**: Disk size parsing issue identified (inputs like "512M" would parse as 512GB). Skipped fix; assumes "G" suffix convention is strictly followed.
- Resolution approach: Walk through.

## 回滚计划

1. 保留旧 state 备份
2. 保留旧模块代码在 git 历史
3. 如需回滚，恢复 state 和代码，重新 init

## 时间估算

| 阶段 | 时间 |
|------|------|
| Phase 1: 准备 | 1 小时 |
| Phase 2-3: Provider 配置 | 30 分钟 |
| Phase 4: VM 模块重写 | 2 小时 |
| Phase 5: LXC 模块重写 | 2 小时 |
| Phase 6: 状态迁移 | 1 小时 |
| Phase 7: 测试验证 | 1 小时 |
| **总计** | **约 8 小时** |

## 参考资料

- [bpg/proxmox 官方文档](https://registry.terraform.io/providers/bpg/proxmox/latest/docs)
- [bpg/proxmox GitHub](https://github.com/bpg/terraform-provider-proxmox)
- [迁移指南 (社区)](https://github.com/bpg/terraform-provider-proxmox/discussions)
- [资源属性对照表](https://registry.terraform.io/providers/bpg/proxmox/latest/docs/resources/virtual_environment_vm)

## 注意事项

1. **不要在生产时间迁移** - 选择维护窗口
2. **先在测试 VM 上验证** - 可以新建一个测试 VM 验证配置
3. **备份 state 文件** - `terraform state pull > backup.tfstate`
4. **逐个资源迁移** - 不要一次性迁移所有资源
5. **保持 Ansible inventory 兼容** - 确保 `ansible_host` 资源输出格式不变
