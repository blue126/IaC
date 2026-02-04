# Veeam Backup & Replication 部署指南

> **版本**: 1.0  
> **日期**: 2026-02-03  
> **状态**: 已完成  
> **适用场景**: T7910 冷备份服务器，混合环境备份 (ESXi VM + Windows/Mac 物理机)

## 1. 架构概述

### 1.1 备份架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    T7910 (ESXi Host)                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐         ┌─────────────────────────────┐   │
│  │    PBS VM       │         │    Windows Server VM        │   │
│  │                 │  iSCSI  │                             │   │
│  │  ZFS Pool ──────┼────────►│  ReFS Volume (E:)           │   │
│  │  (backup-pool)  │         │       │                     │   │
│  │                 │         │       ▼                     │   │
│  │  - veeam-vol    │         │  Veeam VBR                  │   │
│  │    (2TB ZVol)   │         │  Community Edition          │   │
│  │                 │         │                             │   │
│  │  - timemachine  │         └─────────────────────────────┘   │
│  │    (1TB dataset)│                     │                     │
│  └────────┬────────┘                     │                     │
│           │ SMB                          │ Backup              │
└───────────┼──────────────────────────────┼─────────────────────┘
            │                              │
            ▼                              ▼
      ┌──────────┐               ┌──────────────────┐
      │   Mac    │               │  ESXi VMs        │
      │ (Time    │               │  Windows PC      │
      │ Machine) │               │                  │
      └──────────┘               └──────────────────┘
```

### 1.2 组件说明

| 组件 | 作用 | 存储位置 |
|------|------|----------|
| PBS iSCSI Target | 提供块存储给 Windows | ZFS ZVol (backup-pool/veeam-vol) |
| Windows Server | 运行 Veeam VBR | ESXi VM |
| Veeam VBR | 备份管理软件 | Windows Server |
| ReFS Volume | Veeam 备份仓库 | iSCSI 磁盘 (E:) |

## 2. 前置条件

### 2.1 硬件要求

| 资源 | PBS VM | Windows Server VM |
|------|--------|-------------------|
| vCPU | 4+ | 4 |
| 内存 | 8GB+ (ZFS ARC) | 16GB |
| 系统盘 | 32GB | 80GB |
| 数据盘 | ZFS Pool (直通 HBA) | iSCSI (2TB) |

### 2.2 软件要求

- ESXi 8.x
- Windows Server 2022 Datacenter/Standard
- Veeam Backup & Replication 13 Community Edition
- VMware Tools (Windows VM)

## 3. 部署步骤

### 3.1 PBS 端：iSCSI Target 配置

使用 Ansible 自动化部署：

```bash
# 部署 PBS iSCSI Target
ansible-playbook playbooks/deploy-pbs-iscsi.yml

# 验证部署
ansible-playbook playbooks/deploy-pbs-iscsi.yml --tags verify
```

**手动验证命令 (在 PBS 上执行):**

```bash
# 检查 ZVol
zfs list backup-pool/veeam-vol

# 检查 iSCSI Target
targetcli ls /iscsi

# 检查端口
ss -tlnp | grep 3260
```

**配置参数:**

| 参数 | 值 |
|------|-----|
| ZVol 名称 | backup-pool/veeam-vol |
| ZVol 大小 | 2TB |
| ZVol blocksize | 64K |
| 压缩算法 | lz4 |
| IQN | iqn.2026-02.lan.pbs:veeam |
| Portal | 0.0.0.0:3260 |
| 认证模式 | Demo (无认证) |

### 3.2 Windows Server VM 创建

**Terraform 配置:**

```bash
cd terraform/esxi
terraform plan
terraform apply
```

**关键配置 (terraform.tfvars):**

```hcl
windows_vm_name        = "windows-server"
windows_ip_address     = "192.168.1.248"
windows_num_cpus       = 4
windows_memory_mb      = 16384
windows_system_disk_gb = 80
```

### 3.3 Windows Server 安装

1. **从 ISO 安装 Windows Server 2022**
   - 在 ESXi Web UI 挂载 ISO
   - 启动 VM，完成安装向导
   - 设置 Administrator 密码

2. **配置静态 IP**
   ```powershell
   New-NetIPAddress -InterfaceAlias "Ethernet0" -IPAddress 192.168.1.248 -PrefixLength 24 -DefaultGateway 192.168.1.1
   Set-DnsClientServerAddress -InterfaceAlias "Ethernet0" -ServerAddresses 192.168.1.1
   ```

3. **安装 VMware Tools**
   - ESXi Web UI → 右键 VM → Guest OS → Install VMware Tools
   - Windows 内运行 CD 驱动器中的 setup64.exe
   - 重启

4. **启用 WinRM (用于 Ansible 管理)**
   ```powershell
   Enable-PSRemoting -Force
   Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $true
   Set-Item WSMan:\localhost\Service\Auth\Basic -Value $true
   ```

### 3.4 Windows 端：iSCSI + ReFS 配置

使用 Ansible 自动化：

```bash
# 配置 iSCSI 连接和 ReFS 格式化
ansible-playbook playbooks/deploy-windows-iscsi.yml

# 验证配置
ansible-playbook playbooks/deploy-windows-iscsi.yml --tags verify
```

**预期结果:**

```
=== iSCSI Session ===
Target: iqn.2026-02.lan.pbs:veeam
Connected: True
Persistent: True
=== ReFS Volume ===
Drive: E:
Size: 2047.94 GB
Free: 2035.99 GB
```

### 3.5 Veeam VBR 安装

1. **下载 Veeam VBR Community Edition**
   - 访问 https://www.veeam.com/virtual-machine-backup-solution-free.html
   - 下载 ISO 或 EXE 安装包

2. **安装前准备**
   - 关闭 IE Enhanced Security Configuration (Server Manager → Local Server)
   - 确保 C: 盘有足够空间 (建议 20GB+)

3. **安装 Veeam**
   - 运行安装程序
   - 选择 Veeam Backup & Replication
   - 使用默认设置 (PostgreSQL 数据库)
   - 等待安装完成 (可能需要 10-20 分钟)

4. **首次启动**
   - 启动 Veeam Backup & Replication Console
   - 连接到 `127.0.0.1:9392`
   - 使用 Windows 凭证 (Administrator)

### 3.6 Veeam 配置

#### 3.6.1 添加 Backup Repository

1. **Backup Infrastructure** → **Backup Repositories**
2. 右键 → **Add Backup Repository** → **Direct attached storage** → **Microsoft Windows**
3. 名称: `PBS-iSCSI-ReFS`
4. 路径: `E:\Backups`
5. 勾选 **Use per-VM backup files** (启用 Fast Clone)

#### 3.6.2 添加 ESXi 服务器

1. **Backup Infrastructure** → **Managed Servers** → **Add Server**
2. 选择 **VMware vSphere** → **vSphere**
3. 输入 ESXi IP: `192.168.1.251`
4. 输入 root 凭证

#### 3.6.3 创建备份作业

1. **Home** → **Backup Job** → **VMware vSphere**
2. 名称: `ESXi-VMs-Backup`
3. 添加要备份的 VM
4. 选择 Repository: `PBS-iSCSI-ReFS`
5. 设置计划或手动运行

## 4. 备份 Windows 物理机

### 4.1 准备工作

在目标 Windows PC 上创建本地管理员账户:

```powershell
# 创建 Veeam 专用账户
net user VeeamAdmin "YourPassword123!" /add
net localgroup Administrators VeeamAdmin /add
```

启用远程管理:

```powershell
# 允许远程管理员访问
New-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "LocalAccountTokenFilterPolicy" -Value 1 -PropertyType DWORD -Force

# 启用防火墙规则
Enable-NetFirewallRule -DisplayGroup "File and Printer Sharing"
Enable-NetFirewallRule -DisplayGroup "Windows Management Instrumentation (WMI)"
```

重启 PC。

### 4.2 在 Veeam 中添加

1. **Inventory** → **Physical Infrastructure**
2. 右键 → **Add Protection Group** → **Individual computers**
3. 输入 PC 的 IP 地址
4. 使用凭证: `电脑名\VeeamAdmin`

## 5. Mac 备份 (Time Machine)

Mac 使用 PBS 上的 Samba 共享进行 Time Machine 备份:

```bash
# 部署 Time Machine 服务
ansible-playbook playbooks/deploy-pbs-timemachine.yml
```

**Mac 端配置:**

1. 系统设置 → 通用 → Time Machine
2. 添加备份磁盘
3. 选择 `pbs TimeMachine.local` 或手动连接 `smb://192.168.1.249/TimeMachine`
4. 用户名: `timemachine`
5. 密码: `timemachine`

## 6. 故障排除

### 6.1 Veeam 服务无法启动

**症状:** VeeamBackupSvc 卡在 Starting 状态

**解决方案:**

```powershell
# 重启 PostgreSQL
Restart-Service -Name "postgresql-x64-17"

# 等待后启动 Veeam
Start-Sleep -Seconds 30
Start-Service -Name "VeeamBackupSvc"
```

### 6.2 VBR Console 无法连接

**症状:** SSL Connection error 或 Cannot connect to localhost

**解决方案:**

```powershell
# 删除 SSL 证书缓存
Stop-Service -Name "VeeamBackupSvc" -Force
Remove-Item -Path "C:\ProgramData\Veeam\Backup\SSL\*" -Force -Recurse
Start-Service -Name "VeeamBackupSvc"
```

### 6.3 iSCSI 磁盘不可见

**检查步骤:**

```powershell
# 检查 iSCSI 服务
Get-Service -Name MSiSCSI

# 检查连接
Get-IscsiTarget
Get-IscsiSession

# 重新连接
Connect-IscsiTarget -NodeAddress "iqn.2026-02.lan.pbs:veeam" -IsPersistent $true
```

### 6.4 Windows PC 备份失败 (Access Denied)

**解决方案:**

1. 创建本地管理员账户
2. 添加注册表项 `LocalAccountTokenFilterPolicy = 1`
3. 启用 WMI 防火墙规则
4. 重启 PC

## 7. 备份架构总览

| 平台 | 备份工具 | 存储位置 | 说明 |
|------|----------|----------|------|
| Proxmox VM/LXC | PBS | PBS ZFS Pool | 原生集成，推荐 |
| ESXi VM | Veeam | E:\ (ReFS) | Agent-less |
| Windows 物理机 | Veeam Agent | E:\ (ReFS) | 需装 Agent |
| Mac | Time Machine | PBS SMB | 原生支持 |

## 8. 相关文档

- [PBS iSCSI Veeam 架构方案](pbs-iscsi-veeam-guide.md)
- [PBS iSCSI 实施规范](../specs/pbs-iscsi-veeam-spec.md)
