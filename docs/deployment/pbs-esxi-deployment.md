# Proxmox Backup Server on ESXi 8.x - Deployment Guide

> **说明**：本指南覆盖在 ESXi 8.x 环境中通过 Infrastructure as Code 方式部署 Proxmox Backup Server，包含 LSI 3008 HBA 直通、ZFS 分层存储（special vdev）配置、Terraform 与 Ansible 集成的完整实施流程。

**文档版本**: 1.1  
**创建日期**: 2026-01-29  
**最后更新**: 2026-01-31  
**适用环境**: ESXi 8.x, vCenter Server, Terraform 1.14+, Ansible 2.16+

> **⚠️ 重要更新 (2026-01-31)**  
> `pbs_zfs` role 已合并到 `pbs` role 中。ZFS 相关 tasks 现位于 `ansible/roles/pbs/tasks/zfs-*.yml`。  
> 本文档中对 `roles/pbs_zfs/` 的引用仅作历史参考，实际文件路径已变更为 `roles/pbs/tasks/zfs-*.yml`。

---

## Table of Contents

- [1. Overview](#1-overview)
  - [1.1. Project Goals](#11-project-goals)
  - [1.2. Key Features](#12-key-features)
  - [1.3. Architecture Summary](#13-architecture-summary)
- [2. Architecture Design](#2-architecture-design)
  - [2.1. System Architecture](#21-system-architecture)
  - [2.2. Hardware Configuration](#22-hardware-configuration)
  - [2.3. Storage Architecture (ZFS Special vdev)](#23-storage-architecture-zfs-special-vdev)
  - [2.4. Network Topology](#24-network-topology)
  - [2.5. IaC Workflow](#25-iac-workflow)
- [3. Prerequisites](#3-prerequisites)
  - [3.1. Hardware Requirements](#31-hardware-requirements)
  - [3.2. Software Requirements](#32-software-requirements)
  - [3.3. Access Requirements](#33-access-requirements)
- [4. Infrastructure as Code Structure](#4-infrastructure-as-code-structure)
  - [4.1. Project File Organization](#41-project-file-organization)
  - [4.2. Terraform Architecture](#42-terraform-architecture)
  - [4.3. Ansible Roles Structure](#43-ansible-roles-structure)
  - [4.4. Inventory Source of Truth](#44-inventory-source-of-truth)
- [5. Implementation Phases Overview](#5-implementation-phases-overview)

---

## 1. Overview

### 1.1. Project Goals

本项目的目标是在 ESXi 8.x 虚拟化环境中部署一个高性能的 Proxmox Backup Server，用于混合环境（Proxmox VE + ESXi）的备份管理。通过 Infrastructure as Code 实现完全自动化、可重复、可审计的部署流程。

**核心目标**：
- ✅ **自动化部署**：Terraform 管理基础设施，Ansible 管理配置
- ✅ **高性能存储**：ZFS Mirror Pool（HDD，可选 NVMe special vdev 升级）
- ✅ **硬件直通**：LSI 3008 HBA 直通提供原生磁盘访问
- ✅ **可维护性**：完整的文档、验证机制、监控集成
- ✅ **资产管理**：与 Netbox IPAM/DCIM 集成

### 1.2. Key Features

**存储特性**：
- **ZFS Mirror Pool**: 2 × 8TB HDD（通过 LSI 3008 HBA 直通）
- **ZFS Special vdev**: 可选升级（当前未启用，需要 PCIe bifurcation 支持）
- **性能优化**: 针对 PBS 工作负载的 ZFS 参数调优
- **数据保护**: Mirror 冗余 + ZFS 校验和

**IaC 特性**：
- **Terraform 管理**: VM 创建、PCIe 直通、网络配置
- **Ansible 自动化**: ZFS 配置、PBS 安装、用户管理
- **动态 Inventory**: Terraform 作为 inventory source of truth
- **自动验证**: 部署后健康检查和性能测试

**集成特性**：
- **Netbox 集成**: 自动注册 VM、IP、服务记录
- **监控就绪**: 暴露 PBS metrics 端点
- **备份策略**: ZFS 快照自动化

### 1.3. Architecture Summary

```
ESXi Host (192.168.1.251)
  ↓
PBS VM (192.168.1.249)
  ├─ 8 vCPU, 16GB RAM (预留)
  ├─ 80GB System Disk (ESXi Datastore)
  ├─ PCIe Passthrough:
  │   └─ LSI 3008 HBA → 2 × 8TB HDD
  └─ ZFS Storage Pool:
      └─ Data vdev: mirror (HDD) - ~7.3TB usable
```

**部署流程**：
```
Terraform (Infrastructure)
  ↓
PBS ISO Installation (Manual)
  ↓
Ansible (Configuration)
  ↓
Verification (Automated)
```

---

## 2. Architecture Design

### 2.1. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  vCenter Server: 192.168.1.250                                  │
│  Datacenter: Roseville                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  ESXi Host: 192.168.1.251                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  PBS VM: 192.168.1.249                                    │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  Guest OS: Proxmox Backup Server                    │  │  │
│  │  │  • 8 vCPU                                           │  │  │
│  │  │  • 16GB RAM (Fully Reserved)                       │  │  │
│  │  │  • 80GB System Disk (ext4)                         │  │  │
│  │  │  • EFI Firmware, VMXNET3 Network                   │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │                                                             │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  PCIe Passthrough Devices                           │  │  │
│  │  │  ┌─────────────────────────────────────────────┐   │  │  │
│  │  │  │  LSI 3008 HBA (IT Mode)                     │   │  │  │
│  │  │  │  PCI ID: 0000:XX:XX.X (from discovery)      │   │  │  │
│  │  │  │  ├─ SATA Port 0 → 8TB HDD #1 (/dev/sdb)     │   │  │  │
│  │  │  │  └─ SATA Port 1 → 8TB HDD #2 (/dev/sdc)     │   │  │  │
│  │  │  └─────────────────────────────────────────────┘   │  │  │
│  │  │  ┌─────────────────────────────────────────────┐   │  │  │
│  │  │  │  NVMe #1 (via PCIe Adapter)                 │   │  │  │
│  │  │  │  PCI ID: 0000:YY:YY.Y                       │   │  │  │
│  │  │  │  256GB → /dev/nvme0n1                       │   │  │  │
│  │  │  └─────────────────────────────────────────────┘   │  │  │
│  │  │  ┌─────────────────────────────────────────────┐   │  │  │
│  │  │  │  NVMe #2 (via PCIe Adapter)                 │   │  │  │
│  │  │  │  PCI ID: 0000:ZZ:ZZ.Z                       │   │  │  │
│  │  │  │  256GB → /dev/nvme1n1                       │   │  │  │
│  │  │  └─────────────────────────────────────────────┘   │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │                                                             │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  ZFS Storage Pool: backup-pool                      │  │  │
│  │  │  ┌───────────────────────────────────────────────┐  │  │  │
│  │  │  │  Data vdev (mirror)                          │  │  │  │
│  │  │  │  • Device: /dev/sdb, /dev/sdc                │  │  │  │
│  │  │  │  • Raw: 16TB → Usable: ~8TB                  │  │  │  │
│  │  │  │  • Purpose: Backup data (blocks ≥ 128KB)     │  │  │  │
│  │  │  │  • Performance: ~200-300 MB/s seq write      │  │  │  │
│  │  │  └───────────────────────────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────────────────────────────┐  │  │  │
│  │  │  │  Special vdev (mirror)                       │  │  │  │
│  │  │  │  • Device: /dev/nvme0n1, /dev/nvme1n1        │  │  │  │
│  │  │  │  • Raw: 512GB → Usable: ~220GB               │  │  │  │
│  │  │  │  • Purpose: Metadata + blocks < 128KB        │  │  │  │
│  │  │  │  • Performance: ~3000 MB/s, 50k+ IOPS        │  │  │  │
│  │  │  └───────────────────────────────────────────────┘  │  │  │
│  │  │                                                      │  │  │
│  │  │  Dataset: backup-pool/datastore                     │  │  │
│  │  │  Mount: /mnt/backup-pool/datastore                  │  │  │
│  │  │  PBS Datastore: backup-storage                      │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2. Hardware Configuration

| Component | Specification | Purpose | Notes |
|-----------|---------------|---------|-------|
| **CPU** | 8 vCPU | PBS operations + ZFS metadata | 推荐 Intel Xeon 或等效 |
| **Memory** | 16GB (全部预留) | ZFS ARC (8GB) + PBS (4GB) + OS (4GB) | PCIe 直通必须预留内存 |
| **System Disk** | 80GB (VMDK, Thin) | PBS OS, logs, config | 位于 ESXi Datastore |
| **Firmware** | EFI | 现代化启动，支持 Secure Boot | 推荐用于新部署 |
| **Network** | VMXNET3 (1Gbps) | 备份数据传输 | 可升级到 10Gbps |
| **HBA Card** | LSI 3008 IT Mode | HDD 直通，JBOD 模式 | IT 固件必须，非 IR 模式 |
| **Data Disks** | 2 × 8TB HDD (SATA) | 主数据存储 | 通过 HBA 连接 |
| **Cache Disks** | 2 × 256GB NVMe | 元数据 + 小文件加速 | ❌ 暂不可用 - 需要 bifurcation 支持 |

**关键配置要求**：
- ✅ BIOS/UEFI 启用 VT-d/IOMMU
- ✅ LSI 3008 刷入 IT 模式固件（非 IR/RAID）
- ✅ NVMe 通过独立 PCIe 插槽或转接卡
- ✅ ESXi 启用 PCIe 直通（Passthrough Mode）

### 2.3. Storage Architecture

#### 2.3.1. ZFS Pool 结构（当前部署：HDD-Only）

```
backup-pool (总容量: ~7.3TB 可用)
│
└─ Data vdev: mirror-0
    ├─ /dev/sdb (8TB HDD #1)
    └─ /dev/sdc (8TB HDD #2)
    • 用途: 所有数据和元数据
    • 读写性能: ~250 MB/s 读, ~200 MB/s 写
    • IOPS: ~150-200 (4K随机)
    • 网络瓶颈: 1Gbps = 125 MB/s（实际限制）
```

**未来可选升级（需解决 bifurcation 问题）**：
```
backup-pool (升级配置: ~8TB 数据 + ~220GB 元数据)
│
├─ Data vdev: mirror-0
│   ├─ /dev/sdb (8TB HDD #1)
│   └─ /dev/sdc (8TB HDD #2)
│   • 用途: 存储 ≥ 128KB 的数据块
│
└─ Special vdev: mirror-1
    ├─ /dev/nvme0n1 (256GB NVMe #1)
    └─ /dev/nvme1n1 (256GB NVMe #2)
    • 用途: 所有元数据 + < 128KB 的小文件
    • 升级方法: zpool add backup-pool special mirror /dev/nvme0n1 /dev/nvme1n1
```

#### 2.3.2. ZFS 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `ashift` | 12 | 4KB 扇区对齐（4096 bytes） |
| `compression` | zstd | 高压缩比，适合备份数据 |
| `atime` | off | 关闭访问时间更新，提升性能 |
| `xattr` | sa | 扩展属性存储在 inode |
| `dnodesize` | auto | 自动选择 dnode 大小 |
| `special_small_blocks` | 128K | 小于 128KB 的块存到 special vdev |
| `recordsize` | 128K | PBS 典型块大小 |
| `primarycache` | metadata | 优先缓存元数据到 ARC |
| `redundant_metadata` | most | 元数据多副本（部分在 HDD） |

#### 2.3.3. 存储性能预期

| 工作负载 | 预期性能 | 实际瓶颈 |
|----------|---------|---------|
| PBS 备份写入（大文件） | 200-300 MB/s | HDD 顺序写速度 |
| PBS 索引查询 | < 50ms | NVMe 元数据访问 |
| PBS 去重计算 | 50k+ ops/s | NVMe IOPS |
| ZFS scrub | ~150 MB/s | HDD 随机读 |
| Snapshot 创建 | < 1s | 元数据操作（NVMe） |

**容量规划**：
- **256GB NVMe** 可支持约 **20-40TB** 的实际数据（元数据占比 0.5-1%）
- **PBS 去重** 会增加元数据量，建议监控 special vdev 使用率
- **如果 special vdev 满**，ZFS 自动溢出到 HDD（性能下降但不会丢数据）

### 2.4. Hardware Compatibility and Troubleshooting

#### 2.4.1. PCIe Passthrough Device Compatibility

**⚠️ CRITICAL: Not all PCIe devices work with ESXi passthrough**

During deployment, we discovered significant compatibility issues with certain NVMe devices:

| Device | Model | Status | Issue | Resolution |
|--------|-------|--------|-------|------------|
| LSI 3008 HBA | SAS3008 (IT Mode) | ✅ WORKING | None | Use as-is |
| Samsung SM963 NVMe | 256GB (×2) | ❌ FAILED | VM shutdown causes ESXi crash with FLR error | See workaround below |
| Intel Optane Memory | MEMPEK1W016GA 16GB (×2) | ❌ INCOMPATIBLE | Not a standard NVMe SSD, cannot be used standalone | Remove from configuration |

#### 2.4.2. Intel Optane Memory Incompatibility (CRITICAL)

**Device Identification**:
```bash
# Controller shows zero namespaces
nvme id-ctrl /dev/nvme0 | grep nn
# Output: nn  : 0
```

**Root Cause Analysis**:
- Intel Optane Memory (MEMPEK1W016GA) is **NOT** a standard NVMe SSD
- Designed exclusively for Intel RST (Rapid Storage Technology) caching in Windows/specific Intel chipsets
- Does not support NVMe namespace management commands (`oacs : 0x6` - bit 3 not set)
- Reports zero capacity (`tnvmcap : 0`, `unvmcap : 0`)
- Cannot create namespaces: `nvme create-ns` returns `Invalid Command Opcode`

**Impact**:
- No `/dev/nvme0n1` block devices will ever appear
- Controllers are detected (`/sys/class/nvme/nvme0` exists) but unusable
- Cannot be used for ZFS, even with firmware updates

**Resolution**:
```bash
# Remove Optane devices from VM configuration
# Edit VM .vmx file or use Terraform to remove PCI passthrough entries
# These devices are fundamentally incompatible with standalone use
```

#### 2.4.3. Samsung SM963 NVMe ESXi Crash Issue

**Symptom**:
```
ESXi PSOD (Purple Screen of Death) on VM shutdown
Error: VERIFY bora/devices/pcipassthru/pciPassthru.c:2254
```

**Root Cause**:
- Samsung SM963 fails Function Level Reset (FLR) during VM shutdown
- Device hangs during PCIe reset sequence
- ESXi crashes when attempting to reclaim the device

**Workaround** (✅ TESTED 2026-01-31 - WORKING):

使用 D3→D0 电源状态转换代替 FLR 重置。原理：D3（深度睡眠）→ D0（正常工作）的电源状态切换会触发硬件级重置，绕过 SM963 固件的 FLR 缺陷。

```bash
# On ESXi host, edit the VM .vmx file
ssh root@192.168.1.251
cd /vmfs/volumes/*/proxmox-backup-server/
vi proxmox-backup-server.vmx

# First, check which pciPassthru index corresponds to Samsung NVMe:
grep pciPassthru proxmox-backup-server.vmx
# Look for vendorId = "0x144d" (Samsung) to identify the correct index

# Add resetMethod for Samsung NVMe devices (adjust index as needed):
pciPassthru1.resetMethod = "d3d0"
pciPassthru2.resetMethod = "d3d0"
```

| Reset Method | 原理 | 适用场景 |
|--------------|------|----------|
| FLR (默认) | PCIe 功能级重置命令 | 需要设备固件支持 |
| **d3d0** | D3→D0 电源状态切换 | ✅ 推荐 - 绕过固件问题 |
| link | PCIe 链路级重置 | 备选方案 |

**注意事项**:
- 必须在 VM 关机状态下修改 .vmx 文件
- pciPassthru 索引从 0 开始，按设备添加顺序排列
- 只需给 Samsung NVMe 配置，HBA 等其他设备无需修改

#### 2.4.4. Architecture Options

**✅ RECOMMENDED: HDD + NVMe Special vdev**（FLR workaround 已验证可用）

```
backup-pool (Full Configuration with Special vdev)
│
├─ Data vdev: mirror-0
│   ├─ /dev/sdb (8TB HDD #1)
│   └─ /dev/sdc (8TB HDD #2)
│
└─ Special vdev: mirror-1 (metadata + small blocks)
    ├─ /dev/nvme0n1 (Samsung SM963 256GB #1)
    └─ /dev/nvme1n1 (Samsung SM963 256GB #2)
    • Metadata IOPS: 100,000+
    • Small block acceleration: <128K files on NVMe
```

**备选: HDD-Only Configuration**（如不使用 NVMe）

```
backup-pool (Simplified Configuration)
│
└─ Data vdev: mirror-0
    ├─ /dev/sdb (8TB HDD #1)
    └─ /dev/sdc (8TB HDD #2)
    • Usable Capacity: ~7.3TB
    • Sequential Performance: 200-300 MB/s
    • Random IOPS: 150-200
    • Network Bottleneck: 1Gbps = 125 MB/s (actual limit)
```

**Performance Comparison**:
| Workload | HDD-Only | HDD + NVMe Special |
|----------|----------|-------------------|
| Backup Write | ~120 MB/s | ~120 MB/s |
| Restore Read | ~120 MB/s | ~120 MB/s |
| Metadata Operations | 50-100ms | **<1ms** |
| ZFS Scrub | ~150 MB/s | ~150 MB/s |
| Web UI Responsiveness | Slow | **Fast** |

**Key Insight**: Special vdev 主要提升 **元数据操作性能**（目录浏览、快照管理、Web UI 响应），对大文件顺序读写影响不大。

### 2.5. Network Topology

```
┌─────────────────────────────────────────┐
│  Network: 192.168.1.0/24                │
│  Gateway: 192.168.1.1                   │
│  DNS: 192.168.1.1                       │
└─────────────────────────────────────────┘
              │
              ├─ 192.168.1.250 → vCenter Server
              ├─ 192.168.1.251 → ESXi Host
              ├─ 192.168.1.249 → PBS VM (New)
              ├─ 192.168.1.104 → Netbox
              └─ 192.168.1.50-52 → Proxmox VE Cluster
```

**PBS VM 网络配置**：
- **IP**: 192.168.1.249/24 (静态)
- **网关**: 192.168.1.1
- **DNS**: 192.168.1.1
- **主机名**: pbs.willfan.me
- **虚拟网卡**: VMXNET3 (VMware 准虚拟化)

**防火墙端口**：
- **TCP 8007**: PBS Web UI / API (HTTPS)
- **TCP 22**: SSH 管理
- **ICMP**: Ping 监控

### 2.5. IaC Workflow

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 1: Terraform (Infrastructure Provisioning)            │
├──────────────────────────────────────────────────────────────┤
│  terraform/esxi/pbs.tf                                       │
│    ├─ Create PBS VM (8vCPU, 16GB, 80GB)                     │
│    ├─ Configure PCIe Passthrough (HBA + NVMe)               │
│    ├─ Set Static IP (192.168.1.249)                         │
│    └─ Register to Ansible Inventory (ansible_host resource) │
│                                                              │
│  Output: VM Created, Devices Attached, IP Configured        │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  Phase 2: PBS ISO Installation (Manual)                     │
├──────────────────────────────────────────────────────────────┤
│  • Mount PBS ISO via vCenter                                │
│  • Boot from ISO, run installer                             │
│  • Configure: Hostname, IP, Root Password                   │
│  • Reboot, verify SSH connectivity                          │
│                                                              │
│  Output: PBS OS Installed, SSH Accessible                   │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  Phase 3: Ansible (Configuration Management)                │
├──────────────────────────────────────────────────────────────┤
│  ansible/inventory/terraform-esxi.yml                       │
│    └─ Read PBS from Terraform state (dynamic inventory)    │
│                                                              │
│  ansible/roles/pbs/                                         │
│    ├─ Install system packages (chrony, vim, etc)           │
│    ├─ Configure network (if needed)                        │
│    └─ Create PBS users and permissions                     │
│                                                              │
│  ansible/roles/pbs_zfs/                                     │
│    ├─ Verify devices (/dev/sdb, sdc, nvme0n1, nvme1n1)     │
│    ├─ Create ZFS pool (mirror + special vdev)              │
│    ├─ Optimize ZFS parameters                              │
│    └─ Create PBS datastore (via API)                       │
│                                                              │
│  ansible/playbooks/deploy-pbs.yml                           │
│    └─ Execute roles + automated verification                │
│                                                              │
│  Output: ZFS Configured, PBS Datastore Ready                │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  Phase 4: Netbox Integration (Asset Management)             │
├──────────────────────────────────────────────────────────────┤
│  terraform/netbox-integration/pbs-esxi.tf                   │
│    ├─ Create ESXi Cluster record                           │
│    ├─ Create PBS VM record                                 │
│    ├─ Create Network Interface                             │
│    ├─ Create IP Address (192.168.1.249)                    │
│    └─ Create Service records (PBS Web UI, API)             │
│                                                              │
│  Output: PBS Registered in Netbox                           │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  Phase 5: Verification (Automated Testing)                  │
├──────────────────────────────────────────────────────────────┤
│  ansible-playbook deploy-pbs.yml --tags verify              │
│    ├─ ZFS pool status (ONLINE check)                       │
│    ├─ PBS service status (systemd check)                   │
│    ├─ PBS API accessibility (curl test)                    │
│    ├─ Datastore configuration (API query)                  │
│    └─ Performance baseline (fio test)                      │
│                                                              │
│  Output: Health Report, Performance Metrics                 │
└──────────────────────────────────────────────────────────────┘
```

**关键设计原则**：
1. **Terraform as Source of Truth**: 基础设施状态存储在 Terraform state
2. **Dynamic Inventory**: Ansible 从 Terraform state 读取主机信息
3. **Idempotent**: 所有 Ansible tasks 可重复执行
4. **Verification First**: 每个阶段都有自动验证

---

## 3. Prerequisites

### 3.1. Hardware Requirements

#### 3.1.1. ESXi Host 要求

**最低配置**：
- ESXi 8.0 或更高版本
- CPU: Intel VT-d 或 AMD-Vi 支持（IOMMU）
- 内存: 至少 32GB（为 PBS VM 预留 16GB）
- 可用 PCIe 插槽: 至少 3 个
  - 1 × LSI 3008 HBA
  - 2 × NVMe (或 1 × 双口 PCIe 转接卡)

**BIOS/UEFI 设置**：
```
✅ Intel VT-d / AMD-Vi: Enabled
✅ IOMMU: Enabled
✅ SR-IOV: Enabled (可选)
✅ PCIe ACS (Access Control Services): Enabled
```

#### 3.1.2. Storage 设备要求

**LSI 3008 HBA**：
- ✅ 固件模式: **IT Mode** (非 IR/RAID 模式)
- ✅ 连接设备: 2 × 8TB SATA HDD（仅用于 PBS）
- ✅ 驱动: ESXi 8.x 原生支持
- ❌ 不要配置 RAID: HBA 应设置为 JBOD/直通模式

**验证 IT 模式**：
```bash
# 在 ESXi 上检查 HBA
esxcli hardware pci list | grep -i lsi
# 应显示: LSI Logic SAS3008 IT

# 在 PBS VM 内检查（部署后）
lspci | grep -i lsi
# 应显示: LSI Logic / Symbios Logic SAS3008 PCI-Express Fusion-MPT SAS-3
```

**NVMe 设备**：
- ✅ 容量: 2 × 256GB (或更大)
- ✅ 接口: PCIe 3.0 x4 或更高
- ✅ 连接: 通过 PCIe 转接卡或主板 M.2 插槽
- ⚠️ 确保 NVMe 在独立的 IOMMU 组（后续验证）

#### 3.1.3. Network 要求

- ✅ 静态 IP 可用: 192.168.1.249
- ✅ 网络带宽: 至少 1Gbps（推荐 10Gbps）
- ✅ VLAN: 根据环境配置（可选）

### 3.2. Software Requirements

#### 3.2.1. 本地开发环境

**必需软件**：
```bash
# Terraform
terraform --version
# 要求: >= 1.14.0

# Ansible
ansible --version
# 要求: >= 2.16.0

# Python
python3 --version
# 要求: >= 3.8

# Git
git --version
```

**Terraform Providers**：
```hcl
# terraform/esxi/versions.tf
required_providers {
  vsphere = {
    source  = "hashicorp/vsphere"
    version = "~> 2.6"
  }
  ansible = {
    source  = "ansible/ansible"
    version = "~> 1.3.0"
  }
}
```

**Ansible Collections**：
```bash
# 安装所需 collections
ansible-galaxy collection install community.general
ansible-galaxy collection install cloud.terraform
```

#### 3.2.2. vCenter Server

- ✅ vCenter Server 版本: 7.0 或 8.0
- ✅ ESXi Host 已添加到 vCenter
- ✅ Datacenter 和 Cluster 已配置
- ✅ Datastore 有足够空间（至少 100GB for VM + ISO）

#### 3.2.3. Proxmox Backup Server ISO

下载最新版本：
```bash
# 官方下载页面
https://www.proxmox.com/en/downloads/proxmox-backup-server

# 当前稳定版 (示例)
proxmox-backup-server_3.1-1.iso
```

### 3.3. Access Requirements

#### 3.3.1. Credentials Checklist

**vCenter / ESXi**：
- [ ] vCenter Server IP: `192.168.1.250`
- [ ] vCenter 用户名: `administrator@willfan.top`
- [ ] vCenter 密码: (存储在环境变量或 Terraform Cloud)
- [ ] ESXi Host IP: `192.168.1.251`
- [ ] Datacenter 名称: `Roseville`

**PBS VM**：
- [ ] Root 密码: (ISO 安装时设置，记录到 Ansible Vault)
- [ ] SSH 公钥: `~/.ssh/id_ed25519.pub` (用于 cloud-init，可选)

**Netbox**:
- [ ] Netbox URL: `http://192.168.1.104:8080`
- [ ] API Token: (存储在 Terraform 变量)

#### 3.3.2. SSH Key Setup

```bash
# 生成 SSH 密钥（如果没有）
ssh-keygen -t ed25519 -C "your_email@example.com"

# 复制公钥（稍后用于 PBS）
cat ~/.ssh/id_ed25519.pub
```

#### 3.3.3. Ansible Vault Setup

```bash
# 创建 vault 密码文件
echo "your-secure-vault-password" > ansible/.vault_pass
chmod 600 ansible/.vault_pass

# 将密码文件添加到 .gitignore（已包含）
```

---

## 4. Infrastructure as Code Structure

### 4.1. Project File Organization

本部署涉及以下目录和文件：

```
IaC/
├── terraform/
│   ├── esxi/                           # ESXi 基础设施
│   │   ├── main.tf                     # 已存在（空主文件）
│   │   ├── provider.tf                 # 已存在（vSphere provider）
│   │   ├── versions.tf                 # 🔄 需更新：添加 Ansible provider
│   │   ├── variables.tf                # 🔄 需更新：添加 PBS 变量
│   │   ├── terraform.tfvars            # 🔄 需更新：填写 PBS 配置
│   │   ├── pbs.tf                      # 🆕 PBS VM 定义 + PCIe 直通配置
│   │   ├── pbs-iso.tf                  # 🆕 ISO 管理（可选）
│   │   └── outputs.tf                  # 🆕 PBS 输出
│   │
│   ├── modules/
│   │   └── esxi-vm/                    # 🆕 通用 ESXi VM 模块
│   │       ├── main.tf
│   │       ├── variables.tf
│   │       └── outputs.tf
│   │
│   └── netbox-integration/
│       └── pbs-esxi.tf                 # 🆕 PBS Netbox 记录
│
├── ansible/
│   ├── inventory/
│   │   ├── terraform-esxi.yml          # 🆕 ESXi Terraform inventory
│   │   ├── groups.yml                  # 🔄 需更新：添加 esxi_vms 组
│   │   └── group_vars/
│   │       └── esxi_vms.yml            # 🆕 ESXi VMs 组变量
│   │
│   ├── roles/
│   │   ├── pbs/                        # 🆕 PBS 核心角色
│   │   │   ├── tasks/
│   │   │   │   ├── main.yml
│   │   │   │   ├── install.yml
│   │   │   │   ├── configure.yml
│   │   │   │   └── users.yml
│   │   │   ├── defaults/main.yml
│   │   │   ├── handlers/main.yml
│   │   │   ├── templates/
│   │   │   │   └── network-interfaces.j2
│   │   │   └── vars/
│   │   │       └── vault.yml           # 🔐 加密的密码
│   │   │
│   │   └── pbs_zfs/                    # 🆕 ZFS 配置角色
│   │       ├── tasks/
│   │       │   ├── main.yml
│   │       │   ├── verify-devices.yml
│   │       │   ├── create-pool.yml
│   │       │   ├── optimize.yml
│   │       │   └── datastore.yml
│   │       ├── defaults/main.yml
│   │       ├── handlers/main.yml
│   │       └── templates/
│   │           └── zfs-arc.conf.j2
│   │
│   └── playbooks/
│       └── deploy-pbs.yml              # 🆕 完整部署 playbook
│
├── scripts/
│   └── pbs/                            # 🆕 PBS 工具脚本
│       ├── discover-pci-devices.sh     # PCI 设备发现
│       ├── create-hba-passthrough.sh   # HBA 直通辅助
│       └── validate-deployment.sh      # 部署验证
│
└── docs/
    └── deployment/
        └── pbs-esxi-deployment.md      # 📄 本文档
```

**符号说明**：
- 🆕 新建文件
- 🔄 更新现有文件
- 🔐 需要加密/敏感
- ✅ 已存在，无需修改

### 4.2. Terraform Architecture

#### 4.2.1. Provider Configuration

**文件**: `terraform/esxi/versions.tf`

```hcl
terraform {
  required_version = ">= 1.0.0"
  
  # Terraform Cloud Backend（已配置）
  cloud {
    organization = "homelab-roseville"
    workspaces {
      name = "iac-esxi-lab"  # 新建 workspace
    }
  }
  
  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "~> 2.6"
    }
    
    # ✨ 新增 Ansible Provider
    ansible = {
      source  = "ansible/ansible"
      version = "~> 1.3.0"
    }
  }
}
```

**文件**: `terraform/esxi/provider.tf`

```hcl
provider "vsphere" {
  user                 = var.vsphere_user
  password             = var.vsphere_password
  vsphere_server       = var.vsphere_server
  allow_unverified_ssl = true
}

# Ansible Provider 无需额外配置
# 资源会自动写入 Terraform state
```

#### 4.2.2. Module Design

**文件**: `terraform/modules/esxi-vm/main.tf`

```hcl
# 通用 ESXi VM 模块
# 支持 PCIe 直通、内存预留、EFI 固件

resource "vsphere_virtual_machine" "vm" {
  name             = var.vm_name
  resource_pool_id = var.resource_pool_id
  datastore_id     = var.datastore_id
  num_cpus         = var.num_cpus
  memory           = var.memory
  
  # PCIe 直通必须预留内存
  memory_reservation = var.memory_reservation
  
  # EFI 固件
  firmware = var.firmware
  
  # 网络配置
  network_interface {
    network_id   = var.network_id
    adapter_type = var.network_adapter_type
  }
  
  # 系统磁盘
  disk {
    label            = "disk0"
    size             = var.system_disk_size
    thin_provisioned = true
  }
  
  # PCIe 直通设备
  dynamic "pci_device_id" {
    for_each = var.pci_device_ids
    content {
      device_id = pci_device_id.value
    }
  }
  
  # 客户机配置（如果使用 cloud-init）
  # ...
}
```

#### 4.2.3. PBS VM Resource

**文件**: `terraform/esxi/pbs.tf`

```hcl
# PBS VM 定义
module "pbs" {
  source = "../modules/esxi-vm"
  
  # 基础配置
  vm_name             = var.pbs_vm_name
  resource_pool_id    = data.vsphere_host.host.resource_pool_id
  datastore_id        = data.vsphere_datastore.datastore.id
  network_id          = data.vsphere_network.network.id
  
  # 硬件配置
  num_cpus            = var.pbs_num_cpus
  memory              = var.pbs_memory_mb
  memory_reservation  = var.pbs_memory_mb  # 预留全部（PCIe 直通要求）
  system_disk_size    = var.pbs_system_disk_gb
  firmware            = "efi"
  network_adapter_type = "vmxnet3"
  
  # PCIe 直通设备
  pci_device_ids = concat(
    [var.pbs_hba_pci_id],      # LSI 3008 HBA
    var.pbs_nvme_pci_ids       # 2 × NVMe
  )
}

# ✨ 注册到 Ansible Inventory
resource "ansible_host" "pbs" {
  name   = "pbs"
  groups = ["esxi_vms"]
  
  variables = {
    ansible_user       = "root"
    ansible_host       = var.pbs_ip_address
    ansible_ssh_private_key_file = "~/.ssh/id_ed25519"
    
    # PBS 特定变量（传递给 Ansible）
    pbs_datastore_path = "/mnt/backup-pool/datastore"
    pbs_zfs_pool       = "backup-pool"
  }
  
  depends_on = [module.pbs]
}

# 输出
output "pbs_vm_id" {
  value       = module.pbs.vm_id
  description = "PBS VM Managed Object ID"
}

output "pbs_ip" {
  value       = var.pbs_ip_address
  description = "PBS Management IP"
}
```

### 4.3. Ansible Roles Structure

#### 4.3.1. pbs Role (Core Configuration)

**目录结构**：
```
roles/pbs/
├── tasks/
│   ├── main.yml          # 主入口
│   ├── install.yml       # 包安装
│   ├── configure.yml     # 系统配置
│   └── users.yml         # PBS 用户管理
├── defaults/main.yml     # 默认变量
├── handlers/main.yml     # 处理器
├── templates/
│   └── network-interfaces.j2
└── vars/
    └── vault.yml         # 🔐 加密密码
```

**关键文件**: `roles/pbs/tasks/main.yml`

```yaml
---
- name: Include system package installation
  include_tasks: install.yml
  tags: [install, packages]

- name: Include PBS configuration
  include_tasks: configure.yml
  tags: [configure]

- name: Include PBS user management
  include_tasks: users.yml
  tags: [users]
```

**关键文件**: `roles/pbs/defaults/main.yml`

```yaml
---
# PBS Configuration
pbs_timezone: "Australia/Sydney"
pbs_port: 8007
pbs_datastore_name: "backup-storage"

# ZFS ARC Limits (内存 16GB)
pbs_zfs_arc_max_gb: 8
pbs_zfs_arc_min_gb: 2

# Network Configuration
pbs_reconfigure_network: false

# PBS Users (passwords in vault.yml)
pbs_backup_user_email: "fanweiblue@gmail.com"
```

#### 4.3.2. pbs_zfs Role (Storage Configuration)

**目录结构**：
```
roles/pbs_zfs/
├── tasks/
│   ├── main.yml              # 主流程
│   ├── verify-devices.yml    # 设备验证
│   ├── create-pool.yml       # 创建 ZFS pool
│   ├── optimize.yml          # 性能优化
│   └── datastore.yml         # PBS datastore
├── defaults/main.yml         # ZFS 参数
├── handlers/main.yml         # initramfs 更新
└── templates/
    └── zfs-arc.conf.j2       # ARC 配置
```

**关键文件**: `roles/pbs_zfs/defaults/main.yml`

```yaml
---
# ZFS Pool Configuration
pbs_zfs_pool_name: "backup-pool"
pbs_zfs_mount_point: "/mnt/backup-pool"

# Device Paths（from Terraform variables）
pbs_zfs_hdd_devices:
  - /dev/sdb
  - /dev/sdc
pbs_zfs_nvme_devices:
  - /dev/nvme0n1
  - /dev/nvme1n1

# ZFS Optimization Parameters
pbs_zfs_ashift: 12
pbs_zfs_compression: "zstd"
pbs_zfs_atime: "off"
pbs_zfs_special_small_blocks: "128K"
pbs_zfs_recordsize: "128K"
pbs_zfs_primarycache: "metadata"
pbs_zfs_redundant_metadata: "most"

# ARC Configuration
pbs_zfs_arc_max_gb: 8
pbs_zfs_arc_min_gb: 2
pbs_zfs_arc_max_bytes: "{{ (pbs_zfs_arc_max_gb * 1024 * 1024 * 1024) | int }}"

# PBS Datastore
pbs_datastore_name: "backup-storage"
pbs_datastore_path: "/mnt/backup-pool/datastore"
pbs_gc_schedule: "daily"
```

### 4.4. Inventory Source of Truth

**架构原则**：Terraform 是 infrastructure 的唯一真实来源（Source of Truth），Ansible inventory 通过动态插件从 Terraform state 读取。

#### 4.4.1. Terraform → Ansible 集成

**Proxmox 环境（已有参考）**：
```yaml
# ansible/inventory/terraform.yml
plugin: cloud.terraform.terraform_provider
project_path: /workspaces/IaC/terraform/proxmox
state_file: /workspaces/IaC/terraform/proxmox/terraform.tfstate
```

**ESXi 环境（新建）**：
```yaml
# ansible/inventory/terraform-esxi.yml
plugin: cloud.terraform.terraform_provider
project_path: /workspaces/IaC/terraform/esxi
state_file: /workspaces/IaC/terraform/esxi/terraform.tfstate
```

**关键点**：
- ✅ `state_file` 路径根据 Terraform backend 配置（本地或 Terraform Cloud）
- ✅ Ansible 自动发现所有 `ansible_host` 资源
- ✅ 无需手动维护 `hosts.yml` 文件
- ❌ 不要在 `ansible/inventory/esxi_vms/hosts.yml` 中硬编码主机

#### 4.4.2. Inventory Groups

**文件**: `ansible/inventory/groups.yml`（更新）

```yaml
---
all:
  children:
    proxmox_cluster:
    esxi_hosts:
    esxi_vms:         # ← 新增组
    oci:
    
    tailscale:
      children:
        proxmox_cluster:
        oci:
        pve_lxc:
        pve_vms:
        esxi_vms:     # ← 加入 Tailscale 组（如果需要）
    
    pve_lxc:
    pve_vms:
```

**文件**: `ansible/inventory/group_vars/esxi_vms.yml`（新建）

```yaml
---
# ESXi VMs 组变量
ansible_python_interpreter: /usr/bin/python3
ansible_ssh_common_args: '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
ansible_connection: ssh

# 默认用户（可被 host 变量覆盖）
ansible_user: root
```

#### 4.4.3. 验证 Inventory

```bash
# 查看所有主机（包括从 Terraform 读取的）
ansible-inventory --list

# 查看 esxi_vms 组
ansible-inventory --graph esxi_vms

# 输出示例：
# esxi_vms:
#   |--pbs

# 查看 PBS 主机详情
ansible-inventory --host pbs --yaml

# 输出示例：
# ansible_host: 192.168.1.249
# ansible_ssh_private_key_file: ~/.ssh/id_ed25519
# ansible_user: root
# pbs_datastore_path: /mnt/backup-pool/datastore
# pbs_zfs_pool: backup-pool

# 测试连接
ansible pbs -m ping
```

---

## 5. Implementation Phases Overview

部署分为 6 个阶段，总耗时约 **10-14 小时**（首次部署，包括学习和调试）。

| 阶段 | 任务 | 预计时间 | 输出 |
|------|------|---------|------|
| **Phase 0** | 硬件发现和准备 | 1-2h | PCI IDs, 变量文件, Vault 配置 |
| **Phase 1** | Terraform 基础设施 | 2-3h | VM 已创建，设备已直通 |
| **Phase 2** | PBS ISO 安装 | 1-2h | PBS OS 已安装，SSH 可访问 |
| **Phase 3** | Ansible 配置 | 2-3h | ZFS 已配置，PBS Datastore 就绪 |
| **Phase 4** | Netbox 集成 | 1h | PBS 已注册到资产管理 |
| **Phase 5** | 验证和测试 | 1-2h | 健康检查通过，性能基准 |

**建议实施节奏**：
- **第 1 天**: Phase 0-1（硬件发现 + Terraform 部署）
- **第 2 天**: Phase 2-3（PBS 安装 + Ansible 配置）
- **第 3 天**: Phase 4-5（Netbox 集成 + 验证测试）

**前置检查清单**：
- [ ] ESXi IOMMU 已启用（BIOS 设置）
- [ ] LSI 3008 已刷 IT 固件
- [ ] NVMe 通过 PCIe 转接卡安装
- [ ] vCenter 可访问，凭据正确
- [ ] 本地 Terraform、Ansible 已安装
- [ ] Ansible Vault 密码文件已创建
- [ ] PBS ISO 已下载（或准备自动下载脚本）

---

## 6. Phase 0: Discovery and Preparation

### 6.1. Hardware Device Discovery

在开始 Terraform 部署前，必须获取 PCIe 设备的准确 ID。

#### 6.1.1. 创建发现脚本

**文件**: `scripts/pbs/discover-pci-devices.sh`

```bash
#!/bin/bash
# PBS PCIe Device Discovery Script
# Purpose: Discover LSI HBA and NVMe PCI IDs on ESXi host

echo "=== PBS Hardware Discovery ==="
echo ""

echo "1. LSI 3008 HBA Card:"
esxcli hardware pci list | grep -A 10 "LSI.*3008"

echo ""
echo "2. NVMe Devices:"
esxcli hardware pci list | grep -A 10 "NVMe\|Non-Volatile"

echo ""
echo "3. All PCIe Devices (condensed):"
esxcli hardware pci list | grep -E "Address:|Device Name:"

echo ""
echo "4. Connected SATA Disks (via HBA):"
esxcli storage core device list | grep -E "Display Name:|Size:"

echo ""
echo "=== Instructions ==="
echo "Copy the PCI IDs (format: 0000:XX:XX.X) to terraform/esxi/terraform.tfvars"
```

#### 6.1.2. 执行发现脚本

```bash
# 1. 将脚本复制到 ESXi
scp scripts/pbs/discover-pci-devices.sh root@192.168.1.251:/tmp/

# 2. SSH 到 ESXi 并执行
ssh root@192.168.1.251
chmod +x /tmp/discover-pci-devices.sh
/tmp/discover-pci-devices.sh > /tmp/pbs-hardware-info.txt
cat /tmp/pbs-hardware-info.txt
```

**预期输出示例**：
```
1. LSI 3008 HBA Card:
   Address: 0000:03:00.0
   Device Name: LSI Logic / Symbios Logic SAS3008 PCI-Express Fusion-MPT SAS-3
   
2. NVMe Devices:
   Address: 0000:01:00.0
   Device Name: Samsung Electronics Co Ltd NVMe SSD Controller
   
   Address: 0000:02:00.0  
   Device Name: Samsung Electronics Co Ltd NVMe SSD Controller
```

**记录以下信息**：
- LSI HBA PCI ID: `0000:03:00.0`
- NVMe 1 PCI ID: `0000:01:00.0`
- NVMe 2 PCI ID: `0000:02:00.0`

### 6.2. 配置文件准备

#### 6.2.1. Terraform 变量

**文件**: `terraform/esxi/terraform.tfvars`（追加）

```hcl
# ==========================================
# PBS Configuration
# ==========================================

# VM Basic Settings
pbs_vm_name = "proxmox-backup-server"
pbs_vmid = 200
pbs_ip_address = "192.168.1.249"

# Hardware Resources
pbs_num_cpus = 8
pbs_memory_mb = 16384
pbs_system_disk_gb = 80

# PCIe Passthrough Devices (从 Phase 0.1 获取)
pbs_hba_pci_id = "0000:03:00.0"  # ← 替换为实际 ID
pbs_nvme_pci_ids = [
  "0000:01:00.0",  # ← 替换为实际 ID
  "0000:02:00.0"   # ← 替换为实际 ID
]
```

#### 6.2.2. Ansible Vault

```bash
cd ansible/

# 创建加密的密码文件
ansible-vault create roles/pbs/vars/vault.yml

# 内容（输入后保存）：
---
pbs_root_password: "YourSecureRootPassword"
pbs_backup_user_password: "BackupUserPassword"
```

### 6.3. 验证先决条件

```bash
# 1. 检查 IOMMU
ssh root@192.168.1.251 "esxcli system settings kernel list | grep iommu"
# 应显示: iovDisableIR = TRUE

# 2. 检查 HBA IT 模式
ssh root@192.168.1.251 "esxcli hardware pci list | grep -i lsi"
# 确认显示 "SAS3008 IT"

# 3. 测试 vCenter 连接
cd terraform/esxi/
terraform init
terraform validate
```

---

## 7. Phase 1: Terraform Infrastructure

### 7.1. 更新 Terraform Versions

**文件**: `terraform/esxi/versions.tf`（完整内容）

```hcl
terraform {
  required_version = ">= 1.0.0"
  
  cloud {
    organization = "homelab-roseville"
    workspaces {
      name = "iac-esxi-lab"
    }
  }
  
  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "~> 2.6"
    }
    ansible = {
      source  = "ansible/ansible"
      version = "~> 1.3.0"
    }
  }
}
```

### 7.2. 创建 ESXi VM 模块

**文件**: `terraform/modules/esxi-vm/main.tf`

```hcl
terraform {
  required_providers {
    vsphere = {
      source = "hashicorp/vsphere"
    }
  }
}

resource "vsphere_virtual_machine" "vm" {
  name             = var.vm_name
  resource_pool_id = var.resource_pool_id
  datastore_id     = var.datastore_id
  
  num_cpus = var.num_cpus
  memory   = var.memory
  memory_reservation = var.memory_reservation
  
  firmware = var.firmware
  guest_id = var.guest_id
  
  network_interface {
    network_id   = var.network_id
    adapter_type = var.network_adapter_type
  }
  
  disk {
    label = "disk0"
    size  = var.system_disk_size
    thin_provisioned = true
  }
  
  # PCIe 直通设备
  dynamic "pci_device_id" {
    for_each = var.pci_device_ids
    content {
      device_id = pci_device_id.value
    }
  }
  
  cdrom {
    client_device = true
  }
  
  wait_for_guest_net_timeout = 0
}

output "vm_id" {
  value = vsphere_virtual_machine.vm.id
}

output "vm_name" {
  value = vsphere_virtual_machine.vm.name
}
```

**文件**: `terraform/modules/esxi-vm/variables.tf`

```hcl
variable "vm_name" {
  type = string
}

variable "resource_pool_id" {
  type = string
}

variable "datastore_id" {
  type = string
}

variable "network_id" {
  type = string
}

variable "num_cpus" {
  type    = number
  default = 2
}

variable "memory" {
  type    = number
  default = 4096
}

variable "memory_reservation" {
  type    = number
  default = 0
}

variable "system_disk_size" {
  type    = number
  default = 40
}

variable "firmware" {
  type    = string
  default = "efi"
}

variable "guest_id" {
  type    = string
  default = "debian11_64Guest"
}

variable "network_adapter_type" {
  type    = string
  default = "vmxnet3"
}

variable "pci_device_ids" {
  type    = list(string)
  default = []
}
```

### 7.3. PBS VM 定义

**文件**: `terraform/esxi/pbs.tf`

```hcl
module "pbs" {
  source = "../modules/esxi-vm"
  
  vm_name          = var.pbs_vm_name
  resource_pool_id = data.vsphere_host.host.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id
  network_id       = data.vsphere_network.network.id
  
  num_cpus           = var.pbs_num_cpus
  memory             = var.pbs_memory_mb
  memory_reservation = var.pbs_memory_mb
  system_disk_size   = var.pbs_system_disk_gb
  
  firmware             = "efi"
  guest_id             = "debian11_64Guest"
  network_adapter_type = "vmxnet3"
  
  pci_device_ids = concat(
    [var.pbs_hba_pci_id],
    var.pbs_nvme_pci_ids
  )
}

resource "ansible_host" "pbs" {
  name   = "pbs"
  groups = ["esxi_vms"]
  
  variables = {
    ansible_user                 = "root"
    ansible_host                 = var.pbs_ip_address
    ansible_ssh_private_key_file = "~/.ssh/id_ed25519"
    pbs_datastore_path           = "/mnt/backup-pool/datastore"
    pbs_zfs_pool                 = "backup-pool"
  }
  
  depends_on = [module.pbs]
}

output "pbs_vm_id" {
  value = module.pbs.vm_id
}

output "pbs_ip" {
  value = var.pbs_ip_address
}
```

### 7.4. 扩展变量定义

**文件**: `terraform/esxi/variables.tf`（追加）

```hcl
# PBS VM Configuration
variable "pbs_vm_name" {
  type    = string
  default = "proxmox-backup-server"
}

variable "pbs_vmid" {
  type    = number
  default = 200
}

variable "pbs_ip_address" {
  type = string
}

variable "pbs_num_cpus" {
  type    = number
  default = 8
}

variable "pbs_memory_mb" {
  type    = number
  default = 16384
}

variable "pbs_system_disk_gb" {
  type    = number
  default = 80
}

variable "pbs_hba_pci_id" {
  type        = string
  description = "LSI 3008 HBA PCI ID (e.g., 0000:03:00.0)"
}

variable "pbs_nvme_pci_ids" {
  type        = list(string)
  description = "NVMe PCI IDs (e.g., ['0000:01:00.0', '0000:02:00.0'])"
}
```

### 7.5. 执行 Terraform

```bash
cd terraform/esxi/

# 1. 初始化（首次或添加新 provider）
terraform init -upgrade

# 2. 验证配置
terraform validate

# 3. 预览变更
terraform plan

# 检查输出：
# - 将创建 vsphere_virtual_machine.vm (module.pbs)
# - 将创建 ansible_host.pbs
# - PCI devices: 3 个（1 HBA + 2 NVMe）

# 4. 应用
terraform apply

# 5. 验证输出
terraform output pbs_vm_id
terraform output pbs_ip
```

### 7.6. 启用 PCIe 直通（ESXi 端）

Terraform 会附加 PCI 设备，但首次使用需要在 ESXi 端启用直通模式：

```bash
# SSH 到 ESXi
ssh root@192.168.1.251

# 启用 HBA 直通
esxcli hardware pci pcipassthru set -d=0000:03:00.0 -e=true -a

# 启用 NVMe 直通
esxcli hardware pci pcipassthru set -d=0000:01:00.0 -e=true -a
esxcli hardware pci pcipassthru set -d=0000:02:00.0 -e=true -a

# 重启 ESXi（必须）
reboot
```

**重启后验证**：

```bash
# 检查直通状态
esxcli hardware pci pcipassthru list | grep -E "0000:03:00.0|0000:01:00.0|0000:02:00.0"

# 应显示: Enabled = true
```

---

## 8. Phase 2: PBS ISO Installation

### 8.1. 挂载 PBS ISO

**通过 vCenter Web UI**：

1. 上传 PBS ISO 到 ESXi Datastore
   - 导航到: Storage → Datastore → Upload
   - 上传: `proxmox-backup-server_3.1-1.iso`

2. 配置 VM CD/DVD
   - 右键 PBS VM → Edit Settings
   - CD/DVD Drive → Datastore ISO File
   - 选择: `proxmox-backup-server_3.1-1.iso`
   - ✅ Connect at power on

3. 启动 VM
   - Power On
   - 打开 Web Console

### 8.2. PBS 安装流程

**启动后选择**：
- Install Proxmox Backup Server (Graphical)

**安装配置**：

| 选项 | 值 |
|------|-----|
| **Target Disk** | /dev/sda (80GB) |
| **Filesystem** | ext4 |
| **Country** | China (或你的位置) |
| **Timezone** | Australia/Sydney |
| **Keyboard Layout** | us |
| **Admin Password** | (设置强密码，记录到 Ansible Vault) |
| **Confirm Password** | (重复) |
| **Email** | admin@example.com |
| **Hostname (FQDN)** | pbs.willfan.me |
| **IP Address** | 192.168.1.249/24 |
| **Gateway** | 192.168.1.1 |
| **DNS Server** | 192.168.1.1 |

**完成安装**：
- 点击 Install
- 等待约 5-10 分钟
- Reboot
- 卸载 ISO（Edit Settings → CD/DVD → Client Device）

### 8.3. 初始验证

```bash
# 1. SSH 连接测试
ssh root@192.168.1.249

# 2. 检查系统信息
uname -a
cat /etc/os-release

# 3. 验证直通设备
lsblk
# 应看到:
# sda    80G  (系统盘)
# sdb    8T   (HDD #1)
# sdc    8T   (HDD #2)
# nvme0n1  256G
# nvme1n1  256G

lspci | grep -i "lsi\|nvme"
# 应看到:
# 03:00.0 Serial Attached SCSI controller: LSI Logic SAS3008
# 01:00.0 Non-Volatile memory controller: Samsung ...
# 02:00.0 Non-Volatile memory controller: Samsung ...

# 4. 网络测试
ip addr show
ping -c 3 192.168.1.1
ping -c 3 8.8.8.8

# 5. 检查 PBS 服务
systemctl status proxmox-backup

# 6. 访问 Web UI（从浏览器）
# https://192.168.1.249:8007
```

---

## 9. Phase 3: Ansible Configuration

### 9.1. 创建 Ansible Inventory

**文件**: `ansible/inventory/terraform-esxi.yml`

```yaml
plugin: cloud.terraform.terraform_provider
project_path: /workspaces/IaC/terraform/esxi
state_file: /workspaces/IaC/terraform/esxi/terraform.tfstate
```

**更新**: `ansible/inventory/groups.yml`

```yaml
all:
  children:
    proxmox_cluster:
    esxi_hosts:
    esxi_vms:
    oci:
    tailscale:
      children:
        proxmox_cluster:
        oci:
        pve_lxc:
        pve_vms:
        esxi_vms:
    pve_lxc:
    pve_vms:
```

**创建**: `ansible/inventory/group_vars/esxi_vms.yml`

```yaml
---
ansible_python_interpreter: /usr/bin/python3
ansible_ssh_common_args: '-o StrictHostKeyChecking=no'
```

**验证 Inventory**：

```bash
cd ansible/

ansible-inventory --list
ansible-inventory --host pbs
ansible pbs -m ping
```

### 9.2. 创建 pbs Role

**文件**: `ansible/roles/pbs/tasks/main.yml`

```yaml
---
- include_tasks: install.yml
  tags: [install]

- include_tasks: configure.yml
  tags: [configure]

- include_tasks: users.yml
  tags: [users]
```

**文件**: `ansible/roles/pbs/tasks/install.yml`

```yaml
---
- name: Update apt cache
  apt:
    update_cache: yes
    cache_valid_time: 3600

- name: Install ZFS utilities
  apt:
    name:
      - zfsutils-linux
      - zfs-dkms
    state: present

- name: Install system utilities
  apt:
    name:
      - vim
      - htop
      - iotop
      - fio
      - chrony
      - curl
    state: present

- name: Ensure chrony is running
  systemd:
    name: chrony
    state: started
    enabled: yes
```

**文件**: `ansible/roles/pbs/tasks/configure.yml`

```yaml
---
- name: Set timezone
  timezone:
    name: "{{ pbs_timezone | default('Australia/Sydney') }}"

- name: Configure ZFS ARC limits
  lineinfile:
    path: /etc/modprobe.d/zfs.conf
    line: "options zfs zfs_arc_max={{ pbs_zfs_arc_max_bytes }}"
    create: yes
  register: zfs_arc_config

- name: Update initramfs if ZFS config changed
  command: update-initramfs -u
  when: zfs_arc_config.changed
```

**文件**: `ansible/roles/pbs/tasks/users.yml`

```yaml
---
- name: Wait for PBS API
  wait_for:
    port: 8007
    timeout: 60

- name: Create PBS backup user
  uri:
    url: "https://{{ ansible_host }}:8007/api2/json/access/users"
    method: POST
    user: root@pam
    password: "{{ pbs_root_password }}"
    force_basic_auth: yes
    validate_certs: no
    body_format: json
    body:
      userid: "backup@pbs"
      password: "{{ pbs_backup_user_password }}"
      email: "fanweiblue@gmail.com"
    status_code: [200, 201]
  failed_when: false
```

**文件**: `ansible/roles/pbs/defaults/main.yml`

```yaml
---
pbs_timezone: "Australia/Sydney"
pbs_port: 8007
pbs_zfs_arc_max_gb: 8
pbs_zfs_arc_max_bytes: "{{ (pbs_zfs_arc_max_gb * 1024 * 1024 * 1024) | int }}"
```

### 9.3. 创建 pbs_zfs Role

**文件**: `ansible/roles/pbs_zfs/tasks/main.yml`

```yaml
---
- include_tasks: verify-devices.yml
  tags: [verify]

- include_tasks: create-pool.yml
  tags: [pool]

- include_tasks: optimize.yml
  tags: [optimize]

- include_tasks: datastore.yml
  tags: [datastore]
```

**文件**: `ansible/roles/pbs_zfs/tasks/verify-devices.yml`

```yaml
---
- name: Check HDD devices
  stat:
    path: "/dev/{{ item }}"
  loop:
    - sdb
    - sdc
  register: hdd_check

- name: Assert HDDs exist
  assert:
    that: hdd_check.results | selectattr('stat.exists') | list | length == 2
    fail_msg: "HDD devices not found"

- name: Check NVMe devices
  stat:
    path: "/dev/{{ item }}"
  loop:
    - nvme0n1
    - nvme1n1
  register: nvme_check

- name: Assert NVMes exist
  assert:
    that: nvme_check.results | selectattr('stat.exists') | list | length == 2
    fail_msg: "NVMe devices not found"
```

**文件**: `ansible/roles/pbs_zfs/tasks/create-pool.yml`

```yaml
---
- name: Check if pool exists
  command: zpool list backup-pool
  register: pool_check
  failed_when: false
  changed_when: false

- name: Create ZFS pool with HDD mirror
  command: >
    zpool create
    -o ashift=12
    -O compression=lz4
    -O atime=off
    -O xattr=sa
    -O dnodesize=auto
    -m /mnt/backup-pool
    backup-pool
    mirror /dev/sdb /dev/sdc
  when: pool_check.rc != 0

- name: Add NVMe special vdev
  command: >
    zpool add backup-pool
    special
    mirror /dev/nvme0n1 /dev/nvme1n1
  when: pool_check.rc != 0
```

**文件**: `ansible/roles/pbs_zfs/tasks/optimize.yml`

```yaml
---
- name: Set special_small_blocks
  command: zfs set special_small_blocks=128K backup-pool

- name: Set recordsize
  command: zfs set recordsize=128K backup-pool

- name: Enable zstd compression
  command: zfs set compression=zstd backup-pool

- name: Optimize cache
  command: zfs set primarycache=metadata backup-pool

- name: Set redundant metadata
  command: zfs set redundant_metadata=most backup-pool
```

**文件**: `ansible/roles/pbs_zfs/tasks/datastore.yml`

```yaml
---
- name: Create ZFS dataset
  command: zfs create backup-pool/datastore
  args:
    creates: /mnt/backup-pool/datastore

- name: Set permissions
  file:
    path: /mnt/backup-pool/datastore
    owner: backup
    group: backup
    mode: '0770'
    state: directory

- name: Create PBS datastore
  uri:
    url: "https://{{ ansible_host }}:8007/api2/json/admin/datastore"
    method: POST
    user: root@pam
    password: "{{ pbs_root_password }}"
    force_basic_auth: yes
    validate_certs: no
    body_format: json
    body:
      name: "backup-storage"
      path: "/mnt/backup-pool/datastore"
      "gc-schedule": "daily"
    status_code: [200, 201]
  failed_when: false
```

### 9.4. 部署 Playbook

**文件**: `ansible/playbooks/deploy-pbs.yml`

```yaml
---
- name: Deploy Proxmox Backup Server
  hosts: pbs
  become: yes
  vars_files:
    - ../roles/pbs/vars/vault.yml
  
  roles:
    - role: pbs
      tags: [pbs]
    - role: pbs_zfs
      tags: [zfs]

- name: Verify Deployment
  hosts: pbs
  become: yes
  tags: [verify]
  vars_files:
    - ../roles/pbs/vars/vault.yml
  
  tasks:
    - name: Check ZFS pool
      command: zpool status backup-pool
      register: zpool_status
      failed_when: "'ONLINE' not in zpool_status.stdout"

    - name: Check PBS service
      systemd:
        name: proxmox-backup
      register: pbs_service

    - name: Test PBS API
      uri:
        url: "https://{{ ansible_host }}:8007/api2/json/admin/datastore"
        user: root@pam
        password: "{{ pbs_root_password }}"
        force_basic_auth: yes
        validate_certs: no
      register: api_test

    - name: Display summary
      debug:
        msg:
          - "✅ PBS Deployment Complete"
          - "Web UI: https://{{ ansible_host }}:8007"
          - "ZFS Pool: ONLINE"
          - "Datastore: backup-storage"
```

### 9.5. 执行部署

```bash
cd ansible/

# 完整部署
ansible-playbook playbooks/deploy-pbs.yml --ask-vault-pass

# 仅验证
ansible-playbook playbooks/deploy-pbs.yml --tags verify --ask-vault-pass
```

---

## 10. Phase 4: Netbox Integration

**文件**: `terraform/netbox-integration/pbs-esxi.tf`

```hcl
resource "netbox_site" "roseville" {
  name = "Roseville"
  slug = "roseville"
}

resource "netbox_cluster_type" "vmware" {
  name = "VMware ESXi"
  slug = "vmware-esxi"
}

resource "netbox_cluster" "esxi" {
  name            = "ESXi-Roseville"
  cluster_type_id = netbox_cluster_type.vmware.id
  site_id         = netbox_site.roseville.id
}

resource "netbox_virtual_machine" "pbs" {
  name       = "proxmox-backup-server"
  cluster_id = netbox_cluster.esxi.id
  vcpus      = 8
  memory     = 16384
  disk       = 80
  comments   = "PBS with ZFS (2×8TB HDD + 2×256GB NVMe special vdev)"
  tags       = ["backup", "zfs", "esxi"]
}

resource "netbox_interface" "pbs_eth0" {
  name               = "eth0"
  virtual_machine_id = netbox_virtual_machine.pbs.id
  type               = "virtual"
}

resource "netbox_ip_address" "pbs_ip" {
  ip_address   = "192.168.1.249/24"
  status       = "active"
  interface_id = netbox_interface.pbs_eth0.id
  dns_name     = "pbs.willfan.me"
}

resource "netbox_service" "pbs_web" {
  name               = "PBS Web UI"
  virtual_machine_id = netbox_virtual_machine.pbs.id
  protocol           = "tcp"
  ports              = [8007]
}
```

**执行**：

```bash
cd terraform/netbox-integration/
terraform apply
```

---

## 11. Phase 5: Verification and Performance Testing

### 11.1. 自动验证

已包含在 `deploy-pbs.yml` 的 verify 标签中。

### 11.2. 手动验证清单

```bash
# ZFS 健康
zpool status backup-pool
zpool list -v backup-pool
zfs list

# PBS 服务
systemctl status proxmox-backup
journalctl -u proxmox-backup -n 50

# 网络
curl -k https://192.168.1.249:8007
```

### 11.3. 性能测试

```bash
# 顺序写入
fio --name=seq --rw=write --bs=1M --size=10G --directory=/mnt/backup-pool/datastore --ioengine=libaio --direct=1

# 随机混合
fio --name=rand --rw=randrw --bs=128k --size=5G --numjobs=4 --directory=/mnt/backup-pool/datastore --ioengine=libaio --direct=1

# ZFS I/O 监控
zpool iostat -v backup-pool 2

# ARC 统计
arc_summary
```

---

## 12. Troubleshooting

### 12.1. PCIe 直通失败

**症状**: VM 无法启动，错误 "Failed to power on"

**解决**:
```bash
# 检查直通状态
esxcli hardware pci pcipassthru list

# 检查 IOMMU 组
esxcli hardware pci list | grep -A 5 "0000:03:00.0"

# 确保内存预留
# terraform: memory_reservation = memory
```

### 12.2. ZFS 设备未找到

**症状**: `/dev/sdb` 不存在

**解决**:
```bash
# 检查设备
lsblk
ls -l /dev/disk/by-id/

# 如果是 /dev/disk/by-id/scsi-xxx
# 修改 ansible role 使用 by-id 路径
```

### 12.3. PBS API 不可访问

**症状**: Ansible API 调用失败

**解决**:
```bash
# 检查 PBS 服务
systemctl status proxmox-backup
journalctl -xe

# 检查防火墙
ss -tlnp | grep 8007

# 手动测试
curl -k https://localhost:8007
```

---

## 13. Appendix

### 13.1. Quick Command Reference

```bash
# Terraform
terraform init
terraform plan
terraform apply
terraform destroy

# Ansible
ansible-inventory --list
ansible pbs -m ping
ansible-playbook playbooks/deploy-pbs.yml

# ZFS
zpool status
zfs list
zpool iostat -v 2

# PBS
systemctl status proxmox-backup
proxmox-backup-manager datastore list
```

### 13.2. File Index

- Terraform: `terraform/esxi/*.tf`
- Ansible Roles: `ansible/roles/pbs*/`
- Playbooks: `ansible/playbooks/deploy-pbs.yml`
- Scripts: `scripts/pbs/*.sh`

### 13.3. Related Documentation

- Netbox Deployment: `docs/deployment/netbox-deployment.md`
- Ansible Verification: `docs/learningnotes/2025-11-30-ansible-deployment-verification.md`
- Proxmox Terraform: `docs/learningnotes/2025-11-28-terraform-proxmox.md`

---

**文档结束**
