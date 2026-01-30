# Terraform 故障排查 (Terraform Troubleshooting)

本文档汇总了在使用 Terraform 与 Proxmox 交互时遇到的典型问题。

**来源**:
- `/mnt/docs/learningnotes/2025-11-30-terraform-proxmox-provider-crash.md`
- `/mnt/docs/learningnotes/2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md`

---

## 问题 1: Terraform Provider 崩溃 (Panic)

### 症状
执行 `terraform import` 或 `terraform plan` 时，进程崩溃：
```
panic: interface conversion: interface {} is nil, not string
```

### 诊断步骤
1. 检查 Provider 版本号：
   ```bash
   grep 'telmate/proxmox' .terraform/providers/registry.terraform.io/telmate/proxmox/*/*/terraform-provider-proxmox_*
   ```
2. 检查 Proxmox VE 版本：
   ```bash
   pveversion
   ```
3. 检查 VM 配置特征（快照、磁盘属性等）

### 原因分析
- **Provider 版本 `v3.0.2-rc05`** 存在回归 Bug (Regression)
- 当处理某些特定的 VM 配置时（如包含快照 `parent: baseline` 或特定磁盘属性），Provider 的解析逻辑出错，导致空指针引用
- 虽然删除快照可能缓解症状，但在 rc05 版本下无法彻底解决

### 解决方案
**升级/降级到最稳定的 Provider 版本：`v3.0.2-rc04`**

```hcl
# terraform block
terraform {
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.2-rc04"  # 推荐版本
    }
  }
}
```

**版本对比**:
| 版本 | 优点 | 缺点 |
|------|------|------|
| v3.0.2-rc05 | 最新 | 存在崩溃 Bug |
| v3.0.2-rc04 | 无崩溃，支持 PVE 8 | 略早期 |
| v2.9.14 | 稳定版本 | PVE 8 权限不兼容 |

---

## 问题 2: 权限错误 (Permission Denied)

### 症状
降级到稳定版后，出现权限错误：
```
permissions for user/token root@pam are not sufficient... missing: [VM.Monitor]
```

### 诊断步骤
1. 验证 Proxmox VE 版本：
   ```bash
   pveversion
   ```
2. 查看 Provider 是否使用密码认证或 API Token
3. 检查 API Token 的权限配置：
   ```bash
   pveum user token list
   ```

### 原因分析
- **Proxmox VE 8.0+** 对权限模型进行了改革
- 移除了 `VM.Monitor` 权限，拆分为 `Sys.Audit` 等细粒度权限
- 旧版 Provider (`v2.9.14`) 硬编码了对 `VM.Monitor` 的检查
- 即使是 root 用户使用密码认证，在 PVE 8+ 上也会失败

### 解决方案

#### 方案 A: 使用 API Token 认证（推荐）

1. 在 Proxmox 上生成 Token：
   ```bash
   pveum user token add root@pam terraform --privsep 0
   # 输出: root@pam!terraform 8f5a6b9c-1234-5678-90ab-cdef1234567890
   ```

2. **关键参数 `--privsep 0` 的含义**:
   - **`--privsep 0`** = 关闭权限分离，Token 完全继承用户权限
   - 对于 `root@pam` (Linux 系统级用户)，这是必须的
   - 如果开启权限分离（默认），Token 默认无任何权限，必须一条条手动添加 ACL，极不方便

3. Terraform 配置：
   ```hcl
   variable "pm_api_token_id" {
     type = string
   }
   
   variable "pm_api_token_secret" {
     type      = string
     sensitive = true
   }
   
   provider "proxmox" {
     pm_api_token_id     = var.pm_api_token_id
     pm_api_token_secret = var.pm_api_token_secret
     pm_api_url          = "https://192.168.1.50:8006/api2/json"
   }
   ```

4. 在 `terraform.tfvars` 中存储敏感信息（注意：务必添加到 `.gitignore`）：
   ```hcl
   pm_api_token_id     = "root@pam!terraform"
   pm_api_token_secret = "8f5a6b9c-1234-5678-90ab-cdef1234567890"
   ```

#### 方案 B: 升级 Provider 版本

使用 Provider `v3.0.2-rc04` 或更高版本，它已经适配了 PVE 8 的权限变更。

---

## 问题 3: 虚拟机无法启动 / 进入 UEFI Shell

### 症状
- 新创建的 VM 启动后进入 UEFI Shell 或黑屏
- Cloud-Init 无法运行
- Terraform 报错：`Error: 500 QEMU guest agent is not running`

### 诊断步骤
1. 检查 VM 磁盘大小：
   ```bash
   qm config <vmid> | grep scsi
   ```
2. 检查是否存在 `unused` 磁盘：
   ```bash
   qm config <vmid> | grep unused
   ```
3. 查看 VM 启动日志：
   ```bash
   journalctl -xe
   ```
4. 检查 Cloud-Init 和 QEMU Agent 状态：
   ```bash
   systemctl status qemu-guest-agent
   ```

### 原因分析 - 磁盘缩容陷阱

**场景**: 从模板克隆，模板磁盘 20G，Terraform 配置请求 8G

**Terraform 的错误行为**:
1. 发现请求大小 (8G) < 现有大小 (20G)
2. **不是报错**，而是认为你需要一个"新盘"
3. 执行 "Detach & Create" 逻辑：
   - 卸载 (Detach) 原 20G 系统盘，标记为 `unused0`
   - 创建 (Create) 新的空 8G 磁盘
4. VM 启动从新盘启动，但新盘是空的，没有操作系统
5. 结果：UEFI Shell / 黑屏 / Cloud-Init 无法运行

### 解决方案

#### 立即修复 (Fix Now)

1. 在 Proxmox WebUI 中：
   - 找到 VM，进入硬件标签
   - 确认 `scsi0` 是那个空的 8G 磁盘
   - 分离 `unused0` (原系统盘)
   - **手动调整 `scsi0` 大小到 20G**：
     ```bash
     qm resize <vmid> scsi0 +12G
     ```
   - 或者直接将原系统盘重新挂到 `scsi0`，删除空盘

2. 重新启动 VM，验证 Cloud-Init 和 QEMU Agent 运行

#### 长期预防 (Prevent Future Issues)

**在生成 Terraform 变量的脚本中加入校验**:

```python
# fetch_planned_vms.py (伪代码)
def calculate_disk_size(netbox_vm, template_vm):
    netbox_size_gb = netbox_vm.disk / 1024  # API返回MB，需转换
    template_size_gb = query_proxmox_template_size(template_vm.template_id)
    
    # 防御性检查：磁盘只能扩容，不能缩容
    final_size = max(netbox_size_gb, template_size_gb)
    
    if final_size < template_size_gb:
        raise ValueError(
            f"Cannot shrink disk: requested {final_size}G but template is {template_size_gb}G"
        )
    
    return final_size
```

**Terraform 配置中的防守**:

```hcl
resource "proxmox_vm_qemu" "vm" {
  # ...
  
  disk {
    size    = var.disk_size  # 必须 >= 模板大小
    storage = "local-zfs"
    type    = "scsi"
  }
  
  lifecycle {
    # 忽略 Proxmox 产生的残留磁盘
    ignore_changes = [unused_disk, efidisk]
  }
}
```

---

## 问题 4: Cloud-Init 与 QEMU Guest Agent 依赖链

### 症状
- VM 启动了，但 Terraform 报错：`QEMU guest agent is not running`
- 网络配置未生效
- Terraform 无法完成资源配置

### 原因分析

这是一个**连锁反应**：

```
磁盘错误 (上一个问题)
    ↓
操作系统丢失
    ↓
Cloud-Init 无法运行
    ↓
qemu-guest-agent 无法安装/启动 (我们的模板依赖 Cloud-Init 来动态安装)
    ↓
Terraform 无法配置网络和检测 VM 状态
    ↓
Terraform 超时失败
```

### 诊断步骤
1. SSH 连接到 VM，检查 Cloud-Init 日志：
   ```bash
   cat /var/log/cloud-init/cloud-init.log
   cat /var/log/cloud-init/cloud-init-final.log
   ```
2. 检查 QEMU Agent：
   ```bash
   systemctl status qemu-guest-agent
   which qemu-ga  # 可能不存在
   ```
3. 检查网络配置：
   ```bash
   ip addr
   route -n
   ```

### 解决方案
1. **首先解决磁盘问题**（见问题 3）
2. 确保模板包含 `qemu-guest-agent` 或通过 Cloud-Init `packages` 列表自动安装
3. 模板中 Cloud-Init 配置应包含：
   ```yaml
   #cloud-config
   packages:
     - qemu-guest-agent
   runcmd:
     - systemctl enable qemu-guest-agent
     - systemctl start qemu-guest-agent
   ```

---

## 问题 5: Docker Restart Policy 配置漂移

### 症状
- 重启 VM 后，某些 Docker 服务（如 Netbox）没有自动拉起
- 依赖服务（如数据库）缺失，导致主服务启动失败

### 原因分析
- `docker-compose.yml` 中缺失 `restart: unless-stopped` 或 `restart: always` 策略
- 虽然在 Ansible Role 中为某些服务加了 override，但**漏掉了依赖服务**
- 数据库 (Postgres) 没有启动 → Netbox 无法连接 → 服务失败
- **Ansible 代码修改后必须运行 Playbook 才能生效**，手动修改只是临时救火

### 解决方案

在 Ansible Role 的 `docker-compose.override.yml` 中，为所有关键服务添加重启策略：

```yaml
services:
  netbox:
    restart: unless-stopped
  netbox-worker:
    restart: unless-stopped
  netbox-housekeeping:
    restart: unless-stopped
  postgres:
    restart: unless-stopped  # 数据库必须优先启动
  redis:
    restart: unless-stopped  # 缓存也是关键依赖
```

**关键策略对比**:
| 策略 | 自动启动 | 手动停止后 | 适用场景 |
|------|---------|----------|--------|
| `always` | 是 | 重启后自动启动 | 关键服务 |
| `unless-stopped` | 是 | 重启后保持停止 | 可能需要手工管理的服务 |
| `on-failure` | 否 | 仅异常退出时重启 | 临时服务 |

---

## 问题 6: Terraform Lifecycle 与启动顺序

### 症状
- VM 经常出现启动顺序错误（试图从网络或光驱启动）
- Terraform 反复提示 `unused_disk` 或 `efidisk` 变更
- Plan 输出不稳定，显示大量"虚假"的变更

### 诊断步骤
1. 查看 VM 的引导顺序：
   ```bash
   qm config <vmid> | grep boot
   ```
2. 检查是否存在多余的磁盘属性：
   ```bash
   qm config <vmid> | grep -E 'unused|efidisk'
   ```

### 原因分析
- **引导顺序** - 如果没有显式指定，Proxmox 可能使用默认顺序，导致不稳定
- **残留磁盘** - 克隆或调整磁盘时，Proxmox 经常产生 `unused` 磁盘或 EFI 盘属性漂移
- **Provider 默认值** - Terraform 的默认假设与 Proxmox 实际配置不一致

### 解决方案

在 Terraform 配置中显式定义：

```hcl
resource "proxmox_vm_qemu" "vm" {
  # ...
  
  # 显式指定引导顺序：优先从系统盘启动
  boot = "order=scsi0;ide2;net0"
  
  # 忽略 Proxmox 产生的残留磁盘和 EFI 属性漂移
  lifecycle {
    ignore_changes = [unused_disk, efidisk]
  }
}
```

**启动顺序含义**:
- `scsi0` - SCSI 设备 0 (通常是系统盘)
- `ide2` - IDE 设备 2 (通常是光驱)
- `net0` - 网络启动 (PXE)

---

## 问题 7: Terraform ID 漂移与强制重建

### 症状
- 再次运行 `terraform plan` 时，已存在的 VM 显示 `forces replacement`（销毁重建）
- 错误信息显示 `vmid: 102 -> 0`（从实际 VMID 变成了默认值 0）

### 诊断步骤
1. 检查 Terraform State：
   ```bash
   terraform state show proxmox_vm_qemu.vm | grep vmid
   ```
2. 检查 Terraform 配置中的 `vmid` 定义：
   ```bash
   grep -r 'vmid' *.tf
   ```

### 原因分析
- `proxmox_vm_qemu` 资源中，`vmid` 是**强制属性**
- 如果 State 中的 VMID 与配置中的不同，Terraform 认为需要重建
- 常见原因：脚本生成的 VMID 与手动创建的 VMID 不一致

### 解决方案

采用 **"IP Last Octet = VMID"** 的约定。在生成 Terraform 变量的脚本中加入逻辑：

```python
def extract_vmid_from_ip(ip_address):
    """从IP最后一段提取VMID"""
    # 例: 192.168.1.102 -> VMID 102
    return int(ip_address.split('.')[-1])

# 使用
netbox_ip = "192.168.1.102"
vmid = extract_vmid_from_ip(netbox_ip)
# vmid = 102
```

**优势**:
1. **解决 Terraform ID 漂移** - VMID 与 IP 绑定，不会变化
2. **便于管理** - 看到 IP 就知道 VMID，便于故障排查
3. **可预测性** - 不需要额外的 ID 管理系统

---

## 问题 8: Terraform Drift - 外部修改导致配置漂移

### 症状
- 没有修改代码，`terraform plan` 仍然显示很多变更
- 常见的虚假变更：`tags: " " -> null`，`format: "raw" -> null`，描述字段变化等

### 诊断步骤
1. 运行 `terraform plan` 并查看输出中的"虚假"变更
2. 检查这些变更是否影响实际基础设施
3. 使用 `terraform state show` 对比 State 与实际资源

### 原因分析
- **Provider 默认值** - Proxmox Provider 返回的某些字段默认值与 Terraform 预期的 `null` 不一致
- **外部修改** - Ansible 或手工在 Proxmox WebUI 中修改了资源属性（如 Description）
- **配置不完整** - 配置文件中未显式定义这些字段

### 解决方案

#### 方案 A: 显式定义所有属性

```hcl
resource "proxmox_vm_qemu" "vm" {
  # ...
  
  # 显式定义，使其与实际状态一致
  format = "raw"
  tags   = ""
}
```

#### 方案 B: 使用 Lifecycle ignore_changes

对于不影响基础设施本身的元数据变更，忽略它们：

```hcl
resource "proxmox_vm_qemu" "vm" {
  # ...
  
  lifecycle {
    ignore_changes = [tags, description, notes]
  }
}
```

**何时使用忽略**:
- 用于记录或文档的字段（`description`, `notes`）
- 经常被外部工具修改的字段（`tags`）
- 不影响资源功能的元数据

**保持 Plan 干净的重要性**:

只有当 `terraform plan` 显示 "No changes" 时，我们才能确信：
- 基础设施处于收敛状态 (Converged)
- 代码与实际资源一致
- 下一次变更不会有意外的副作用

---

## 总结与最佳实践

### 记住这些要点

1. **Provider 版本很关键** - 选择 `v3.0.2-rc04` 以获得 PVE 8 兼容性和稳定性
2. **API Token 优于密码** - 使用 `--privsep 0` 为自动化账号完整权限
3. **磁盘只能扩容** - 脚本中必须检查：`final_size >= template_size`
4. **显式定义一切** - 磁盘大小、启动顺序、重启策略、VMID 生成规则
5. **Inventory 与 Configuration 分离** - Infrastructure as Code 需要明确的关切点分离
6. **监控 Plan 输出** - 没有虚假变更的 Plan 是好 Plan

### 快速参考

| 问题 | 快速修复 |
|------|---------|
| Provider 崩溃 | 升级到 v3.0.2-rc04 |
| 权限错误 | 使用 API Token + `--privsep 0` |
| VM 不启动 | 检查磁盘大小，确保 >= 模板大小 |
| Cloud-Init 失败 | 先修复磁盘，再检查模板配置 |
| 服务不自动启动 | 为所有服务添加 `restart: unless-stopped` |
| 启动顺序错误 | 添加 `boot = "order=scsi0;ide2;net0"` |
| ID 漂移 | 从 IP 地址最后一段提取 VMID |
| 虚假变更 | 显式定义字段或使用 `ignore_changes` |

