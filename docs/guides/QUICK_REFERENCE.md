# Terraform + Proxmox 快速参考卡片

## 最常用的 10 个操作

```bash
# 1. 初始化项目
terraform init

# 2. 验证配置
terraform validate && terraform fmt -recursive

# 3. 查看计划（最重要！执行前必看）
terraform plan

# 4. 保存计划（方便 review）
terraform plan -out=tfplan

# 5. 应用配置
terraform apply tfplan

# 6. 自动应用（脚本用）
terraform apply -auto-approve

# 7. 刷新状态
terraform refresh

# 8. 查看输出
terraform output

# 9. 销毁资源
terraform destroy -auto-approve

# 10. 查看资源状态
terraform state list
terraform state show 'proxmox_vm_qemu.web'
```

## 最常见的 5 个问题与快速解决

| 问题 | 症状 | 快速解决 |
|------|------|---------|
| **磁盘缩容** | VM 无法启动，显示 unused_disk | 确保 disk_size >= 模板大小 |
| **Output 不显示** | terraform output 为空 | 在 Root Module 中重新定义 output |
| **VM 反复重建** | plan 显示 will be destroyed | 检查 vmid 是否与 state 一致 |
| **QGA 无法运行** | Terraform 超时卡住 | 在模板中预装 qemu-guest-agent |
| **Cloud-Init 未运行** | SSH Key 未注入 | 检查 cicustom 与其他参数的冲突 |

## 模块化项目结构模板

```
terraform/
├── modules/
│   └── proxmox-vm/
│       ├── main.tf          ← 定义资源
│       ├── variables.tf      ← 输入参数
│       ├── outputs.tf        ← 输出值（关键！）
│       └── versions.tf       ← Provider 版本
├── proxmox/                  ← Root Module
│   ├── main.tf              ← 实例化模块（并再次定义 outputs）
│   ├── variables.tf         ← 环境级参数
│   ├── outputs.tf           ← 汇总输出（必须显式定义）
│   ├── provider.tf          ← Provider 认证
│   └── terraform.tfvars     ← 参数值（.gitignore）
└── .terraform.lock.hcl      ← 版本锁（提交 Git）
```

## 关键参数配置速查

### 最小化 VM 配置
```hcl
resource "proxmox_vm_qemu" "vm" {
  name = "vm-name"           # VM 名称
  vmid = 100                 # VM ID（唯一）
  target_node = "pve0"       # 目标节点
  clone = "ubuntu-template"  # 模板名称

  cores = 4
  memory = 8192              # MB

  disk {
    slot = 0
    size = "50G"             # >= 模板大小！
    type = "disk"
    storage = "local-zfs"    # 存储池名称
  }

  ipconfig0 = "ip=dhcp"      # 网络配置
  ciuser = "ubuntu"
  sshkeys = file("~/.ssh/id_rsa.pub")
  agent = 1                  # 启用 QGA
  boot = "order=scsi0;ide2;net0"  # 启动顺序

  lifecycle {
    ignore_changes = [unused_disk, efidisk]  # 忽略漂移
  }
}

output "vm_ip" {
  value = proxmox_vm_qemu.vm.default_ipv4_address
}
```

### UEFI + Q35 配置
```hcl
resource "proxmox_vm_qemu" "vm" {
  # ... 基本配置 ...

  bios = "ovmf"              # UEFI 固件

  efidisk {                  # EFI 磁盘必须指定
    efitype = "4m"
    storage = "local-zfs"
  }

  cloudinit_cdrom_storage = "local-zfs"  # Cloud-Init 盘位置
}
```

### SSH 密钥管理配置
```hcl
# Terraform：只维护一个不变的 Bootstrap Key
variable "bootstrap_ssh_key" {
  default = file("~/.ssh/terraform_rsa.pub")
}

# Ansible：日常维护完整 Key 列表
# roles/users/defaults/main.yml
authorized_users:
  - name: alice
    key: "ssh-rsa AAAA...alice"
  - name: bob
    key: "ssh-rsa BBBB...bob"
```

## 状态管理速查

### 导入现有 VM
```bash
# 1. 在代码中定义资源框架
resource "proxmox_vm_qemu" "samba" { }

# 2. 导入现有 VM
terraform import proxmox_vm_qemu.samba pve0/qemu/102

# 3. 检查导入的属性
terraform state show proxmox_vm_qemu.samba

# 4. 复制属性到代码中，再执行 plan
terraform plan
```

### 处理配置漂移
```bash
# 检查漂移
terraform plan

# 如果有非预期变更
# 方案 1: 修改代码匹配实际状态
terraform apply

# 方案 2: 忽略特定字段
# lifecycle { ignore_changes = [tags, format] }

# 方案 3: 刷新状态后重新规划
terraform refresh
terraform plan
```

## 调试与诊断

### 启用详细日志
```bash
# 一次性调试
TF_LOG=DEBUG terraform plan

# 持久化日志
TF_LOG=DEBUG TF_LOG_PATH=terraform.log terraform apply

# 查看日志
tail -f terraform.log
```

### 查看资源详情
```bash
# 列表查看
terraform state list

# 详细查看
terraform state show 'proxmox_vm_qemu.web'

# JSON 格式
terraform state show -json 'proxmox_vm_qemu.web' | jq
```

### 强制刷新（谨慎）
```bash
# 刷新状态（重新查询 Proxmox API）
terraform refresh

# 强制覆盖（危险！）
terraform apply -refresh-only
```

## Proxmox SSH 操作速查

### 查询 VM 信息
```bash
# SSH 进入 Proxmox
ssh root@pve

# 列出所有 VM
qm list

# 查看具体 VM 配置
qm config 100 | less

# 查看磁盘大小
qm config 100 | grep -i disk
```

### 磁盘操作
```bash
# 扩展磁盘（VM 需离线）
qm resize 100 scsi0 +50G

# 查询存储池
pvesm status -content images

# 列出存储中的镜像
pvesm list local-zfs | head
```

### Cloud-Init Snippet 管理
```bash
# 列出所有 Snippet
ls -la /var/lib/vz/snippets/

# 创建新 Snippet
cat > /var/lib/vz/snippets/cloud-init.yaml << 'EOF'
#cloud-config
hostname: webserver
...
