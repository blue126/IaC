# Proxmox Backup Server + Veeam 混合备份架构方案 (iSCSI)

> **版本**: 1.0  
> **日期**: 2026-02-03  
> **状态**: 草案  
> **适用场景**: 冷备份服务器 (T7910), 混合环境 (PVE + ESXi + Windows/Mac)

## 1. 方案背景与目标

当前 T7910 作为冷备份服务器，运行 ESXi 8.x，并直通 HBA 卡给 PBS (Proxmox Backup Server) 虚拟机管理 ZFS 存储池。

为了实现**全平台统一备份**（不仅针对 Proxmox VM，还包括 Windows/Mac 物理机及 ESXi VM），计划引入 **Veeam Backup & Replication (VBR)** 运行在 Windows Server 上。

本方案旨在解决核心冲突：**如何在 PBS 独占直通硬盘的情况下，让 Windows Server 高效利用底层存储空间？**

## 2. 架构设计：iSCSI over ZFS

采用 **iSCSI 块存储共享** 方案。PBS 继续独占物理硬件，但在 ZFS 上划分独立的块设备 (ZVol)，通过 iSCSI 协议共享给 Windows Server。

### 架构拓扑

```mermaid
graph TD
    subgraph "T7910 (ESXi Host)"
        HBA[LSI 3008 HBA]
        
        subgraph "PBS VM (Debian)"
            ZFS_Pool[ZFS Pool (backup-storage)]
            PBS_App[PBS Service]
            iSCSI_Svc[LIO iSCSI Target]
            
            ZFS_Pool --Dataset--> PBS_App
            ZFS_Pool --ZVol--> iSCSI_Svc
        end
        
        subgraph "Windows Server VM"
            Veeam[Veeam VBR]
            iSCSI_Init[iSCSI Initiator]
            NTFS_ReFS[ReFS Volume]
        end
        
        HBA ==PCIe直通==> PBS_VM
        iSCSI_Svc ==虚拟网络 (vSwitch)==> iSCSI_Init
        iSCSI_Init --> NTFS_ReFS
        NTFS_ReFS --> Veeam
    end
```

### 核心优势

1.  **Veeam 最佳实践**: Windows 将 iSCSI 目标识别为“本地磁盘”，可将其格式化为 **ReFS (Resilient File System)**。Veeam 在 ReFS 上支持 **Block Cloning (Fast Clone)** 技术，能极快地合并增量备份（Synthetic Full），且节省大量空间。
2.  **存储统一管理**: ZFS 为底层提供 RAID 保护、压缩和数据完整性校验（Bit Rot Protection）。
3.  **零硬件变动**: 无需重新规划直通卡或物理连线。
4.  **网络高性能**: 利用 ESXi 内部虚拟交换机 (vSwitch)，PBS 与 Windows 间的 iSCSI 流量通过内存总线传输（VMXNET3 虚拟网卡），速度极快（可达 10Gbps+），不受物理千兆网口限制。

## 3. 实施规划

### 3.1 PBS 端配置 (Ansible 自动化)

我们需要编写一个新的 Ansible Role (`pbs-iscsi`) 来执行以下任务：

1.  **安装依赖**: `targetcli-fb` (Linux LIO iSCSI 管理工具)。
2.  **创建 ZVol**:
    *   名称: `backup-storage/veeam-vol`
    *   大小: 按需分配 (例如 2TB)
    *   属性: `volblocksize=64k` (推荐配合 iSCSI), `compression=lz4`, `sparse=on` (精简置备)
3.  **配置 iSCSI Target**:
    *   Backstore: 映射上述 ZVol。
    *   IQN (iSCSI Qualified Name): 例如 `iqn.2026-02.lan.pbs:veeam`。
    *   Portal: 监听 PBS IP (0.0.0.0:3260)。
    *   LUN: 映射 Backstore 到 LUN 0。
    *   ACL: 限制仅允许 Windows Server 的 IQN 连接 (可选，内网环境也可开放 demo 模式)。

### 3.2 Windows 端配置 (手动/脚本)

1.  **部署 VM**: 安装 Windows Server 2019/2022 Standard。
2.  **连接 iSCSI**:
    *   打开 "iSCSI Initiator"。
    *   Target: 输入 PBS IP (`192.168.1.249`)。
    *   Connect -> Done。
3.  **磁盘初始化**:
    *   "Disk Management" -> 联机 -> 初始化 (GPT)。
    *   新建卷 -> 格式化为 **ReFS** (分配单元大小建议 64K 以匹配 ReFS 最佳实践)。
4.  **部署 Veeam**:
    *   安装 Veeam VBR Community Edition。
    *   Add Repository -> Direct Attached Storage -> Microsoft Windows -> 选择 ReFS 卷。
    *   **关键设置**: 确保勾选 "Align backup file data blocks" (通常默认) 以启用 Fast Clone。

## 4. 自动化冷备调度 (Veeam 驱动)

由于引入了 Windows，原本的自动化逻辑（WOL -> 备份 -> 关机）可以转移到 Windows 内部，利用 PowerShell 实现更灵活的控制：

**新流程**:

1.  **每周六 00:00**: `pve0` (Cron) 发送 WOL 唤醒 T7910。
2.  **T7910 启动**: ESXi 自动启动 PBS VM 和 Windows VM。
3.  **Windows 启动**:
    *   Veeam 调度器检测到 missed schedule，自动开始运行备份作业。
    *   作业内容：
        *   Backup ESXi VMs (通过 vCenter/ESXi API)。
        *   Backup Agents (物理机/Mac 等)。
4.  **备份后动作 (Post-Job Script)**:
    *   Veeam 作业配置 "Run the following script after this job"。
    *   脚本内容 (PowerShell):
        1.  检查其他作业是否还在运行。
        2.  调用 SSH (plink.exe) 命令关闭 PBS VM。
        3.  调用 ESXi API (PowerCLI) 关闭宿主机 T7910。

## 5. 资源分配建议 (T7910)

| VM | vCPU | RAM | Disk | 用途 |
| :--- | :--- | :--- | :--- | :--- |
| **PBS** | 4 | 8GB+ | 32GB (OS) + 直通 | ZFS 管理, PVE 备份, iSCSI Target |
| **Windows** | 4 | 8GB | 60GB (OS) | Veeam Server, 调度中心 |

*注：ZFS 需要内存做 ARC 缓存，但作为冷备机，性能要求不是第一位的，8-12GB 给 PBS 足够。Windows Server 运行 Veeam SQL 数据库需要一定内存，8GB 起步。*

## 6. 风险与注意事项

1.  **ZVol 空间规划**: ZVol 占用的空间是从 ZFS 池中划走的。如果 PBS (PVE 备份) 数据增长过快，可能导致存储池填满。建议设置 ZFS Quota 或保留一定的 Free Space。
2.  **启动依赖**: Windows VM 必须在 PBS VM **完全启动并加载 ZFS** 之后才能成功连接 iSCSI 盘。
    *   *解决方案*: 在 ESXi 中设置启动延迟，PBS 设为第一顺位，Windows 设为延迟 120秒启动。
3.  **ReFS 兼容性**: ReFS 对硬件错误比较敏感，底层的 ZFS 已经提供了强大的保护，这其实是双重保险。

## 7. 下一步行动

1.  确认 ZFS 存储池剩余空间。
2.  编写 `ansible/roles/pbs-iscsi`。
3.  准备 Windows Server 镜像和 License。
