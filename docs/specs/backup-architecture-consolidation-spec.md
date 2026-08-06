# 备份架构整合 — 实施规范

> **版本**: 1.1
> **日期**: 2026-08-06
> **状态**: 草案（待审核）
> **取代文档**: [pbs-iscsi-veeam-spec.md](./pbs-iscsi-veeam-spec.md)、[pbs-iscsi-veeam-guide.md](../deployment/pbs-iscsi-veeam-guide.md)、[veeam-backup-deployment-guide.md](../deployment/veeam-backup-deployment-guide.md)
>
> **v1.1 变更**：M920Q 内存确定为 16GB（不扩容）；NVMe 确定保留单块 1TB，**取消 special vdev 方案**；Windows/AD 虚机确定迁往 M920Q 且长期驻留；PBS **第一阶段暂留 ESXi**，视实测内存再定；修正 datastore 容量口径。
>
> **v1.2 变更（2026-08-06，pve1 实机落地）**：文件共享定案为 TurnKey Fileserver LXC（见 D14）；：`tank` 镜像池已创建（by-id 锚定）；`zfs_arc_max` 定为 **2 GiB**（非 4 GiB）；虚机存储池实为既有的 **`mainpool`**（非 `nvme`）；适配器芯片确认为 **ASM1064**；NVMe 为 DRAM-less，**暂缓 L2ARC**；新增 6.1.1 节说明 PVE 存储层与 `nodes` 限定；清理孤儿存储 `samsung256gpool`、补建 `mainpool/vmdata`；**推翻"T7910 无铜口"的判断**（实有 I217-LM 与 I210），WOL 方案重新可行。

## 1. 背景与目标

### 1.1 为什么有这份文档

现有备份架构（PBS 通过 HBA 直通独占物理盘 → ZVol → iSCSI → Windows VM → ReFS → Veeam）在运维上存在多个结构性问题。重新评估时发现，**当初的 spec 只记录了「怎么做」，没有记录「为什么这么选、放弃了什么」**，导致本次评估不得不从零重建全部推理链条。

因此本文档除了定义目标架构，还**完整记录关键决策及其理由**（见第 3 节），供未来重新评估时使用。

### 1.2 现有架构的问题

| 问题 | 说明 |
|------|------|
| ZFS 住在客机里 | 宿主机看不到自己的数据盘；SMART 必须进 PBS 才能查 |
| 存储跨网络分层 | `ZFS → ZVol → iSCSI(vSwitch) → ReFS`，双层文件系统 |
| ZFS 能力失效 | `veeam-vol` 压缩比 **1.00x**（对比文件数据集 1.02x / 1.30x）；快照只能得到 ReFS 卷的崩溃一致镜像，无法做文件级恢复 |
| 无空间护栏 | `veeam-vol` 为 2T sparse 且 `refreservation=none`，`datastore` 为 `quota=none`，二者可互相挤爆（原 spec 第 6 节标注了此风险但从未实施缓解） |
| iSCSI 无认证 | `gen-acls / no-auth`，portal 监听 `0.0.0.0:3260`，内网任意设备可挂载并写入备份仓库 |
| 备份频率受限 | T7910 为冷备机（每周六 WOL 唤醒），导致 Mac Time Machine 与 Proxmox 备份均被压缩到每周一次 |
| 单点风险 | 若把 ESXi 虚机备份也放在 T7910，备份与备份源将处于同一块主板上 |
| 依赖 Windows 授权 | 为运行 Veeam VBR 维护一台 Windows Server 2025 虚机（72G） |

### 1.3 目标

1. ZFS 由宿主机原生持有，消除 HBA 直通给客机的结构
2. 主备份目标常开，解除备份频率对冷备机开机窗口的依赖
3. 备份系统离开 ESXi，ESXi 仅作为备份**来源**
4. 建立两级副本（3-2-1）
5. 全部配置纳入 Ansible/Terraform 管理

---

## 2. 现状实测数据

> 以下数据于 2026-08-05 从运行中的系统实测获得，作为决策依据与迁移基线。

### 2.1 ESXi 宿主机

- **型号**: Dell Precision Tower 7910，ESXi 8.0.3 build-24022510
- **vCenter**: 192.168.1.250 / **ESXi**: 192.168.1.251

**存储控制器：**

| PCI 地址 | 设备 | 直通状态 | 承载 |
|---|---|---|---|
| `0000:01:00.0` | LSI SAS3008 12G（零售版，子系统 `1000:30e0`） | 已启用/生效 | **全部 4 块机械盘** |
| `0000:02:00.0` | LSI SAS2308_2 6G（`vmhba1`） | 可直通，未启用 | ESXi 引导卷 + 2 个 VMFS datastore |
| `0000:00:1f.2` | Wellsburg AHCI（`vmhba6`） | **`passthruCapable=False`** | Intel 800G SSD |
| `0000:08:00.0`、`0000:0b:00.0` | Samsung SM963 NVMe ×2 | 已启用/生效 | ZFS special vdev |

`vmhba1` 上的 LUN：

```
T0:L0  LSI Logical Volume   79GB   ← ESXi 引导 + OSDATA/scratch
T1:L0  Samsung SSD 870    1000GB   ← datastore SamsungSSDEVO8701T-1
T2:L0  Samsung SSD 870    1000GB   ← datastore SamsungSSDEVO8701T-2（PBS 与 windows-server 虚机所在）
```

> `ScratchConfig.CurrentScratchLocation` 指向 `/vmfs/volumes/695aced7-…`，该 UUID 不属于任何已挂载 datastore，即安装器在引导设备上创建的 OSDATA 分区。**因此 SAS2308 不可直通。**

### 2.2 物理磁盘

| 设备 | 型号 | 容量 | 接口 | 转速 | by-id | 用途 |
|---|---|---|---|---|---|---|
| sdd | HITACHI HUH72808CLAR8000 | 8TB | **SAS** (SPL-4) | 7200 | `wwn-0x5000cca2610d9c1c` | backup-pool mirror-0 |
| sde | HITACHI HUH72808CLAR8000 | 8TB | **SAS** (SPL-4) | 7200 | `wwn-0x5000cca261372330` | backup-pool mirror-0 |
| sdb | WDC WD60EFPX-68JH4N1 | 6TB | SATA | 5400 | `ata-…_WD-WC3K20AE5KA9` | **空闲** |
| sdc | WDC WD60EFPX-68JH4N1 | 6TB | SATA | 5400 | `ata-…_WD-WC3K20AE5KA2` | **空闲** |
| nvme0n1 / nvme1n1 | Samsung MZVPW256HEGL (SM963) | 238G ×2 | NVMe | SSD | `nvme-SAMSUNG_…_S34ENY0J112117` / `…231801` | special vdev mirror-1 |

- HGST 为 **4Kn 原生**（逻辑/物理扇区均 4096），SMART 均为 OK，grown defect list = 0
- WD 为 **WD Red Plus，CMR**（非 SMR），仅残留磁盘末尾的备份 GPT 头，`zpool import` 无可导入池
- WD 两块盘约于 2026 年 3 月加入，其接入导致 HGST 盘符从 sdb/sdc 顺延至 sdd/sde，使得 `pbs_zfs_hdd_devices` 的默认值指向了错误的磁盘（已于本次修复，改为 by-id 锚定）

### 2.3 backup-pool 现状

```
backup-pool          7.50T   已用 313G (4%)   ONLINE   fragmentation 0%
  mirror-0           sdd + sde
  special mirror-1   nvme0n1 + nvme1n1        已用 48.5G (20.4%)
```

参数：`ashift=12`、`compression=zstd`、`atime=off`、`recordsize=128K`、`xattr=on`、`dnodesize=auto`、`special_small_blocks=128K`

> **注意**：`special_small_blocks` 等于 `recordsize`，意味着几乎所有数据块都会优先落到 NVMe special vdev，直到写满才溢出到 HDD。这是否为有意设计需确认；若只想放元数据与小文件，通常设为 32K/64K。

| 数据集 | 用途 | USED | LUSED | 压缩比 |
|---|---|---|---|---|
| `backup-pool/datastore` | PBS 备份库 | 81.0G | 82.2G | 1.02x |
| `backup-pool/timemachine` | Mac Time Machine | 48.3G | 63.1G | **1.30x** |
| `backup-pool/veeam-vol` | ZVol 2T sparse → iSCSI → ReFS | 184G | 185G | **1.00x** |

**待迁移数据总量：约 130G**（datastore 81G + timemachine 48G；`veeam-vol` 不迁移）

> **两个容量口径务必分清，否则会严重低估规划需求：**
>
> | 口径 | 含义 | 示例 |
> |---|---|---|
> | **落盘量**（`zfs list` USED） | 去重压缩后实际占用的磁盘 | 整个 datastore **81G** |
> | **逻辑量**（`pvesm list` Size） | 备份内容的原始大小 | 仅 immich 一台就是 **322G** |
>
> 上表的 81G 是落盘量。被备份对象的逻辑总量约 **490G**（见 2.6），PBS 的去重与压缩把它压到了 81G。**做容量规划时必须用逻辑量加保留份数估算，不能用 81G。**

### 2.4 PBS 虚机

- 8 vCPU / 16GB（`memory_reservation` 与之相等，因 PCIe 直通要求）
- 系统盘 80G，root 为 ext4 on LVM（61.6G），`arc_max` 8G
- 备份对象：pve0 上 VMID 100-106，每日 02:00，保留 7日/4周/6月
- **未启用 `proxmox-backup-client` 主机备份**（datastore 下无 `host/` 目录）
- **PBS 未备份自身配置**

### 2.5 pve0 上的备份对象（实测置备量）

| VMID | 名称 | 类型 | 置备 | 在备份作业中 |
|---|---|---|---|---|
| 100 | anki-sync-server | LXC | 8G | ✓ |
| **101** | **immich** | VM | **300G** | ✓ |
| 102 | rustdesk | VM | 50G | ✓ |
| 103 | homepage | LXC | 4G | ✓ |
| 104 | netbox | VM | 20G | ✓ |
| **105** | **caddy** | LXC | 100G（实占 73G） | ✓ |
| 106 | n8n | LXC | 8G | ✓ |
| 107 | jenkins | LXC | 16G | ✓（2026-08-06 新增） |
| 108 | **veeam-worker** | VM | 100G | ✗ 见 9.1 未决项 7 |
| 109 | claude-agent | LXC | 10G | ✓（2026-08-06 新增） |
| 110 | claude-desktop | VM | 64G | ✓（2026-08-06 新增） |
| 9000 | ubuntu-24.04-template | VM | 20G | ✗ 模板，可重建 |

在册对象逻辑总量约 **580G**。以 immich 这类以照片为主、增量极小的负载配 7日/4周/6月 保留估算，PBS 去重后落盘量预计在 **700G–1TB** 量级。M920Q 的 6TB 有充足余量。

### 2.6 ESXi 虚机清单

共 13 台，实占 1586G / 置备 5708G。按可重建性分类：

| 类别 | 虚机 | 实占 |
|---|---|---|
| **仅为管理 ESXi 存在** | vCenter Server 8 | 665G |
| **本仓库 IaC 可重建** | llm-server | 231G |
| **厂商 OVA 可重下** | DNAC / CML2.9 / Cisco ISE / Cat9800 WLC / EVE-NG ×2 | 432G |
| **仅为跑 Veeam 存在** | windows-server | 72G |
| 实验桌面 | Windows11 | 107G |
| 有状态 / 模板 | laas-local-controller / ubuntu2404 / proxmox-backup-server | 30G |

> **结论**：真正不可重建的数据集中在 Proxmox 侧（immich 照片、netbox、n8n），ESXi 侧绝大部分可重建。

---

## 3. 关键决策记录

> 本节是本文档的核心。每条决策记录**选择、理由、以及被否决的方案**，避免未来重复考古。

### D1 — 保留 PBS，不用 Veeam 统一

**选择**：PBS 继续负责 Proxmox VM/LXC 备份。

**理由**：
1. **Veeam CE 上限 10 个 workload 不够分**：7 台 Proxmox + 值得备份的 ESXi 虚机（约 3 台）+ Windows 物理机 Agent = 11，已超限。由 PBS 接管 Proxmox 后，Veeam 仅消耗约 4 个额度。
2. **PBS 对 PVE 有 Veeam 无法提供的能力**：脏位图永久增量、跨虚机块级去重（7 台虚机仅占 81G）、PVE UI 内直接恢复。

**资料冲突（需复核）**：Veeam 官方免费产品页现将 Proxmox VE 列入 CE 支持范围（上限 10 workload），而 helpcenter 的授权文档称 Proxmox 插件需要 Veeam Universal License 且每虚机消耗一个 instance。推测为 v12 → v13 的变化。**无论结论如何，上述两条理由均成立。**

### D2 — 原 iSCSI/ZVol 分层是被迫的，不是设计失误

**结论**：**Veeam 的 Fast Clone 仅支持 ReFS（block cloning）与 XFS（reflink），不支持 ZFS。**

OpenZFS 2.2 已提供 `block_cloning`（本池该 feature 为 `enabled`），但 Veeam 至今仅表示"评估中"，未落地支持。

**推论**：只要同时要求 ZFS 与 Fast Clone，就必然是「ZFS 提供块设备 → 上层再套 ReFS/XFS」。要消除该分层，只能放弃 ZFS 或放弃 Fast Clone。原架构的丑陋源于 **PBS 独占物理盘导致 Windows 拿不到裸盘**，而非 Veeam 本身。

### D3 — 排除 Linux 版 Veeam

**选择**：Veeam 继续运行在 Windows 上。

**理由**：
1. **Veeam Software Appliance（v13 的 Linux 形态）没有 Community Edition**。Veeam MVP 在官方社区明确确认："the Veeam Software Appliance isn't available as Community Edition."。无授权安装后**只能恢复，不能创建备份**。
2. **该 appliance 刻意反自动化**：基于 Rocky Linux 9.2，按 DISA STIG 加固；SSH 默认关闭、SELinux strict、获取 root shell 需 Security Officer 审批且限时 8 小时、管理账号强制 2FA。**无法用 Ansible 纳管**，IaC 契合度低于 Windows（仓库已装 `ansible.windows` 集合）。

> 例外：若取得 Veeam NFR 授权（vExpert / Veeam Legend / VCP 等），授权问题可解，但自动化问题依旧。

### D4 — M920Q 使用 Proxmox VE，排除 TrueNAS

**选择**：M920Q 安装 Proxmox VE。

**排除 TrueNAS 的理由**：TrueNAS 的 IaC 生态是**非官方且分裂的**——Terraform 至少有 5 个互相竞争的社区 provider（`deevus`、`baladithyab`、`dariusbakunas`、`PjSalty`、`xonvanetta`），无一来自 iXsystems 官方，各自覆盖范围不同；其中最活跃的 `deevus`（2026-01，v0.6.0，作者自称 early release）恰好**不支持 SMB/NFS 共享与用户管理**。Ansible 的 `arensb.truenas` 集合对 SCALE 支持薄弱。即便使用 provider，TrueNAS 的系统配置与更新仍在 IaC 之外，形成混合真相来源。

**补充**：TrueNAS 提供的运维便利（SMART 报表、告警、scrub 调度、共享 GUI）在 Debian/PVE 上可低成本替代——`smartd`、`zed`（ZFS Event Daemon）、`zfs-scrub@.timer`、Cockpit + 45Drives 共享插件。**关键差别在于这些工具操作标准配置文件，Ansible 仍是唯一 SSOT。**

### D5 — 副本端使用 Debian 虚机，而非 TrueNAS

**选择**：T7910 上以普通 Debian 虚机接收复制，直通 SAS3008。

**理由**：该角色仅需「每周接收 `zfs send`，保存数据」，不需要 GUI、共享管理或 app 生态。TrueNAS 在此角色上的全部价值均用不到，只保留了 D4 中的缺点。Debian 虚机的配置面小到近乎为零（一个池、一个接收数据集、一个 SSH key），且完全 Ansible 可管。

### D6 — 不迁移 HBA，不搬运磁盘

**选择**：物理磁盘全部留在原位，仅迁移数据。

**三个阻碍**（任一即足以否决）：
1. **M920Q 的 PCIe riser 限长 110mm**，而 LSI 零售版 SAS3008（MD2 低剖面）长约 167.65mm，超出约 57mm。
2. **HGST 是 SAS 盘**，无法接入 M.2 转 SATA 适配器，必须有 SAS HBA。
3. **`backup-pool` 含 special vdev（2× Samsung SM963 U.2 NVMe）**，ZFS 导入需全部 vdev 在场，无法只搬 HDD；而 M920Q 仅有 1 个 M.2 槽、0 个 U.2 位。

**另**：即便长度允许，SAS3008 要求约 200 LFM 强制风道，1L 被动散热机箱极可能过热。

**替代方案**：待迁移数据仅约 130G，`zfs send` 经万兆约 12 分钟（瓶颈为 WD 镜像约 180MB/s 写入）。**搬数据不搬盘。**

### D7 — Windows 物理机使用 Veeam Agent，不接入 PBS

**选择**：物理 Windows 继续使用 Veeam Agent for Windows（当前已在使用），仅变更备份目标路径。

**理由**：**PBS 没有官方 Windows 客户端。**现有途径均不适用于系统级备份：
- WSL + `proxmox-backup-client`：仅限指定路径，无 VSS，无裸机恢复
- 共享 Windows 盘经 Linux 中转：仅文件级，无系统状态
- PBS Plus：项目自述 **"Pre-1.0. Expect breaking changes on every release"**，定位文件级备份，未确认 VSS 与裸机恢复

备份系统不应依赖 alpha 级软件。

### D8 — PBS 以 LXC + bind mount 部署，而非虚机

**选择**：PBS 运行为 LXC，bind mount 一个 ZFS 数据集作为 datastore。

**理由**：若 PBS 为虚机，其 datastore 落在 zvol 上，形成 `ZFS → zvol → ext4 → chunk store` 分层；LXC + bind mount 使 chunk store 直接写入 ZFS 数据集，零分层并可获得压缩收益（当前 datastore 为 1.02x）。

**代价**：Proxmox 官方未背书 PBS-in-LXC（社区做法成熟）。若审核认为需要官方支持路径，可改为虚机方案，代价是恢复上述分层。

### D9 — Veeam 仓库使用 zvol，接受该妥协

**选择**：Windows/Veeam 虚机的仓库为 M920Q ZFS 池上的一个 zvol，格式化为 ReFS。

**理由**：由 D2，Fast Clone 要求 ReFS/XFS，必然分层。但相较原架构，**iSCSI 跨 vSwitch 这一跳被消除**，改为本地 virtio——而 PVE 上每个虚机磁盘本就是 zvol，属标准形态。

**已知代价**：该 zvol 上 ZFS 压缩基本无效（实测 1.00x），快照无文件级恢复价值，容量需预先规划。

**强制要求**：必须配置 `refreservation` 与 `quota`，避免重蹈原 spec 标注风险却未实施的覆辙。

### D10 — M920Q 保留 1TB NVMe，且不做 special vdev

**背景**：M920Q 有两个 M.2 2280 槽，分别装 256GB 与 1TB NVMe。其中一个槽必须让位给 M.2-SATA 适配器（WD 磁盘的唯一接入方式）。两块盘均为 2280，故存在选择空间。

**选择**：保留 **1TB**，拆除 256GB。剩余的单块 NVMe 用作虚机/容器存储，**不用作 special vdev**。

**理由**：
1. **单块 NVMe 无法组 mirror，而无冗余的 special vdev 一旦损坏会导致整个备份池不可导入。** special vdev 存的是元数据而非缓存，没有冗余等同于把主备份目标押在单盘上，不可接受。因此 v1.0 中「SSD 切分区做 special vdev」的建议**作废**。
2. 容量：Windows Server 2025 + AD DS + Veeam VBR 实际需 120–150GB（现系统盘即 80GB），加 Fileserver LXC 与 PVE 自身开销；**ZFS 超过约 80% 占用后性能显著劣化**，256GB 装完即逼近红线，且无余量做 L2ARC。
3. 256GB 级别的 NVMe 多为较早期型号，不少无 DRAM 缓存，持续写入性能与 TBW 明显弱于 1TB 级别。

**代价与缓解**：单盘无冗余，盘损即丢虚机。**缓解手段是把这些虚机纳入 PBS 备份**——Windows 迁到 PVE 后即成为可被 PBS 原生备份的对象。此风险明确接受。

**补偿措施**：因失去 special vdev，`tank` 的元数据将全部落在 5400rpm 机械盘上，PBS 的 GC/verify 会变慢。可在 NVMe 上划 100–200GB 作**持久化 L2ARC**（ZFS 2.x 支持跨重启保留，且缓存丢失无害）来部分补偿。

### D11 — pve1 保留在集群内

**选择**：M920Q（即 pve1）继续作为 `HomePVECluster` 成员。

**已核实的集群现状**：

| 节点 | nodeid | quorum_votes | ring0_addr | ring1_addr |
|---|---|---|---|---|
| pve0 | 1 | **3** | 192.168.1.50 | 192.168.1.20 |
| pve1 | 2 | 1 | 192.168.1.51 | 192.168.1.21 |
| pve2 | 3 | 1 | 192.168.1.52 | 192.168.1.22 |

总票 5，pve0 独占 3 票即可满足法定人数。这是写入 `corosync.conf` 的持久设计，非临时 `pvecm expected`。

**权衡**：集群成员互信（共享 corosync 密钥、节点间 root SSH、共享 `/etc/pve`），pve0 被攻陷则 pve1 易被波及，而备份正是用于对抗此类场景。

**但退出集群收益有限**：备份本身就需要网络路径与凭据，无论是否同集群，都存在一条从生产端通往备份端的授权通路。退出仅去掉 root 互信，却要付出失去统一管理与失去 pve1 那一票的代价（法定人数由 4/5 退回 3/5）。

**真正的隔离由二级副本提供**：T7910 大部分时间断电，是事实上的气隙副本。

**加固方向**（替代退出集群）：复制改为副本端**拉取**、PBS 使用独立 token 与 ACL、维持 T7910 的冷机状态。

### D12 — PBS 阶段一暂留 ESXi，迁移与否由实测内存决定

**选择**：阶段一不迁移 PBS；阶段二依据 M920Q 的实际内存占用再判断。

**理由**：M920Q 内存固定 16GB 且不扩容。阶段一预算已用 14GB（见 5.1），PBS 需要 3–4GB，只能从 ARC 或 Windows 虚机挤出。在没有真实负载数据前做此决定属于臆测。

**代价**：阶段一 **Proxmox 虚机的备份仍受制于 T7910 手动开机**，这是本次事故的直接成因之一，阶段一并不解决。

### D13 — T7910 的 WOL：原判断已被推翻，方案重新可行

**已证实**：原设计文档中「每周六 00:00 由 pve0 cron 发 WOL 唤醒 T7910」**从未实现**（pve0 上无 crontab、无 systemd timer、无任何 WOL 工具）。

**已推翻的判断**：v1.1 曾据"T7910 仅有光口、光纤网卡多不支持 WOL"断定当前硬件无法实现 WOL。**该前提错误**——PCI 清单显示 T7910 有两个铜口：

```
0000:00:19.0  Intel I217-LM (板载千兆)
0000:05:00.0  Intel I210   (PCIe 千兆)
```

先前的说法应为"仅有光口**接线**"。接线后 WOL 很可能可行，端口设计（L2-only、不配 IP、专用 vSwitch）见事故报告 7.2 节。

**但这不改变架构结论。**即便 WOL 完全实现，原设计的唤醒频率是**每周六**，而备份作业是**每日 02:00**——一周仍有 6 天会失败。真正的缺陷是**备份计划与电源策略从未闭环**，而非缺少唤醒手段。因此「主备份目标必须常开」这一要求依然成立；WOL 只是在迁移完成前的过渡手段。

### D14 — 文件共享用 TurnKey Fileserver LXC，而非 Debian LXC + 现有 Ansible

**选择**：TurnKey Fileserver LXC。

**背景**：两方案对比如下。

| | TurnKey Fileserver | Debian LXC + 复用现有 playbook |
|---|---|---|
| Time Machine 配置 | **不含**，需完整手工移植 | **已有且经实战验证**（T7910 上 48.3G 备份、compressratio 1.30x） |
| 额外常驻服务 | Webmin、web shell、WebDAV CGI、TKLBAM | 仅 smbd + avahi |
| 内存占用 | 较高 | 较低（规范预算 0.5G） |
| 共享/用户管理 | **Webmin GUI** | 改 Ansible 再跑 playbook |

**理由**：**这台机器将来要作为通用文件服务器使用**——多个共享、多个用户、需要经常手工增删。在这种用法下 Webmin GUI 的便利是真实且持续的，足以抵消额外服务与内存的代价。

**若用途仅限单一 Time Machine 共享，则应选 Debian LXC**：TurnKey 省不掉 Time Machine 配置这个真正困难的部分（它不含 `vfs_fruit` 与 Avahi 通告），只省掉了 `apt install`；而现有 playbook 里的配置已经跑通。此时 Webmin 是唯一收益，且在 Ansible 拥有 `smb.conf` 的前提下只能作查看器用。

**因此本决策的成立完全依赖「将来会有多个共享需要手工管理」这一前提。**若该前提不再成立，应重新评估。

---

## 4. 目标架构

分两个阶段。**阶段一不迁移 PBS**——先把 Windows/Veeam 和文件共享迁到 M920Q，实测内存占用后再决定 PBS 去留（见 D12）。

### 4.1 阶段一（本规范的实施目标）

```
┌───────────── M920Q / pve1（常开，Proxmox VE，10GbE）─────────────┐
│                                                                  │
│  Windows Server VM          TurnKey Fileserver (LXC)             │
│  ├─ AD DS（长期驻留）        └─ Samba + vfs_fruit                 │
│  └─ Veeam VBR CE               └─ tank/timemachine               │
│     └─ zvol → ReFS 仓库                                          │
│                                                                  │
│  存储：                                                           │
│   mainpool  928G  → 虚机/容器存储（1TB NVMe，已存在）              │
│   tank     5.45T  → ZFS mirror 2×WD 6TB（备份数据，已创建）        │
│   rpool     117G  → PVE 系统盘（仅 OS，不参与存储池）              │
└──────────────────────────────────────────────────────────────────┘
     ▲                  ▲                      ▲
     │ SMB              │ SMB (Agent)          │ vSphere API (NBD)
     │ (Time Machine)   │                      │
  MacBook          Windows 物理机           ESXi 虚机

┌───────────── T7910（手动开机，ESXi 8.0.3）──────────────────────┐
│  PBS 虚机（直通 SAS3008 + 2×NVMe special vdev）                  │
│   └─ backup-pool 7.5TB ← Proxmox VM/LXC、Linux 主机             │
│  其余为实验室虚机（vCenter / Cisco / EVE-NG / llm-server …）      │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 阶段二（条件满足后再评估）

若阶段一实测显示 M920Q 尚有 3–4GB 余量，则把 PBS 迁至 M920Q（LXC + bind mount），T7910 的 PBS 降级为 **sync 目标**。收益是 Proxmox 备份摆脱 T7910 的开机窗口（见 D12）。

### 4.3 角色划分（阶段一）

| 备份对象 | 机制 | 落点 | 频率 |
|---|---|---|---|
| Proxmox VM/LXC | PBS 原生 | **T7910** `backup-pool/datastore` | 受限于手动开机 |
| Mac | Time Machine over SMB | M920Q `tank/timemachine` | **每小时**（原每周） |
| Windows 物理机 | Veeam Agent for Windows 免费版 → SMB | M920Q | 按 Agent 计划 |
| ESXi 虚机 | Veeam VBR CE（NBD 传输） | M920Q zvol/ReFS | 每周 |
| Linux 主机 | `proxmox-backup-client`（**新增能力**） | T7910 `backup-pool/datastore` | 受限于手动开机 |

### 4.4 关键改善与遗留限制

**改善：**

1. **消除 iSCSI 层**：iSCSI target、跨 vSwitch 块存储、无认证 portal 全部移除
2. **Mac 与 Windows 物理机的备份目标常开** → Time Machine 恢复正常频率
3. **ESXi 虚机备份的副本不再落在 T7910 自身** → 消除「备份与源同主板」
4. Windows 虚机成为 PVE 虚机后，**PBS 可原生备份它**（此前作为 ESXi 虚机无人备份）

**遗留限制（阶段一未解决）：**

- **Proxmox 虚机的备份仍依赖 T7910 手动开机。**[D13](#d13--t7910-无法-wol暂无自动唤醒手段) 说明了为何无法用 WOL 自动化。这是阶段二要解决的问题。
- 阶段一**没有第二份副本**。两级副本依赖 PBS 迁移完成后再建立。

---

## 5. M920Q 硬件规范

| 部件 | 规格 | 备注 |
|---|---|---|
| 机型 | Lenovo ThinkCentre M920Q Tiny (1L)，集群节点 **pve1** | |
| 内存 | **16GB（固定，不扩容）** | 见 5.1 预算 |
| M.2 2280 槽 ① | **1TB NVMe** — 虚机/容器存储（+ 可选 L2ARC 分区） | 见 D10 |
| M.2 2280 槽 ② | M.2 转 SATA 适配器 → 2× WD 6TB | 原 256GB NVMe 拆除让位；芯片型号需确认，见 5.2 |
| PCIe riser | 万兆网卡 | **限长 110mm**（LSI SAS3008 长 167.65mm，装不下，见 D6） |
| 2.5" SATA 位 | **PVE 系统盘（仅 OS，不参与任何存储池）** | |
| 磁盘供电 | 外置一拖 N 适配器 | 见 9.2 风险 |

### 5.1 内存预算（16GB）

**阶段一**（PBS 留在 T7910）：

| 用途 | 分配 |
|---|---|
| PVE 宿主 | 1.5 GB |
| ZFS ARC (`zfs_arc_max`) | **2 GB**（已落地） |
| Windows VM（AD DS + Veeam VBR） | 8 GB |
| TurnKey Fileserver LXC | 0.5 GB |
| **合计** | **12 GB（余 4 GB）** |

> Veeam 官方要求约「4GB + 每并发作业 500MB」，叠加 Windows Server 2025 与 PostgreSQL，8GB 是可用下限。AD DS 本身很轻（1–2GB）。
>
> ARC 定为 2 GB 而非早期规划的 4 GB：阶段一的负载（Time Machine SMB、Veeam 仓库写入）均为大块顺序写，元数据缓存需求低。PVE 安装时的默认值为 1.5 GB（内存 10%），已调整。

**阶段二**若要迁入 PBS，需再挤出 3–4GB，只能从 ARC 或 Windows（降到 6GB）里出。**这是决定 PBS 能否迁移的硬约束**，须以阶段一实测数据判断（见 D12）。

### 5.2 M.2 转 SATA 适配器（已确认：ASM1064）

```
03:00.0  ASMedia ASM1064 Serial ATA Controller [1b21:1064] (rev 02)
LnkCap:  Speed 8GT/s, Width x1        ← PCIe 3.0 x1
LnkSta:  Speed 8GT/s, Width x1        ← 未降级
驱动:     ahci（标准内核驱动）
dmesg:   无 ata 错误 / 复位事件
```

**评估**：约 985 MB/s 可用带宽，两块 5400rpm 组镜像（顺序写约 180 MB/s 封顶）**远未触及上限**。

- ✅ **不是 ASM1166**，无需处理该型号已知的 ASPM 掉盘问题
- ✅ **不是端口倍增器方案**（JMB575 类在 ZFS 下错误处理不可靠）
- ⚠️ **扩展上限**：若将来把 4 个口插满做两组 mirror stripe（见 9.2），x1 的 985 MB/s 将接近瓶颈

磁盘挂载路径已确认经由该控制器：

```
sdb : 00:1b.4 → 0000:03:00.0 / ata7
sdc : 00:1b.4 → 0000:03:00.0 / ata8
sda : 00:17.0 / ata1                    ← 系统盘走 Intel PCH SATA
```

### 5.2.1 磁盘健康基线（2026-08-06）

| | sdb | sdc |
|---|---|---|
| 序列号 | WD-WC3K20AE5KA2 | WD-WC3K20AE5KA9 |
| SMART 总评 | PASSED | PASSED |
| 通电时长 | 24 小时 | 24 小时 |
| 启停次数 | 5 | 5 |
| Reallocated / Pending / Offline_Uncorrectable | 0 / 0 / 0 | 0 / 0 / 0 |
| **UDMA_CRC_Error_Count** | **0** | **0** |
| 温度 | 22°C | 22°C |

> `UDMA_CRC_Error_Count = 0` 是验证 SATA 线材与供电质量的关键指标，此处为零说明适配器接线与外置供电均正常。

### 5.2.2 NVMe 实况（影响 L2ARC 决策）

```
02:00.0  Phison PS5019-E19 PCIe4 NVMe Controller (DRAM-less)
设备:     MSI M450 1TB
```

**该盘无独立 DRAM 缓存**，依赖 HMB 借用主机内存，而本机仅 16 GB。在持续随机写入下性能衰减较明显。

**因此暂不实施 5.3 节的可选 L2ARC 分区**：L2ARC 会给这块盘增加持续随机写，恰是其弱项，且要与虚机争用 HMB。待 PBS 迁入后实测 GC/verify 表现再决定。

### 5.3 存储布局与容量规划

**三类存储各司其职，互不混用：**

| 载体 | 用途 | 冗余 |
|---|---|---|
| 2.5" SATA | PVE 系统盘，仅 OS | 无（重装即可，配置在 Ansible 里） |
| 1TB NVMe（`mainpool` 池，已存在） | 虚机/容器磁盘 + 可选 L2ARC 分区 | **无**——见下方说明 |
| 2× WD 6TB（`tank` 池） | 全部备份数据 | ZFS mirror |

**关于 NVMe 无冗余**：单块 NVMe 承载 Windows/AD 虚机与 Fileserver LXC，盘损即虚机丢失。**缓解手段是把它们纳入 PBS 备份**——Windows 迁到 PVE 后即成为可被 PBS 原生备份的虚机，这正是迁移带来的附加收益。此风险**明确接受**，不额外投入硬件。

**`tank` 池的数据集与配额**（可用 6TB，当前真实数据约 130G）：

| 数据集 | 类型 | 建议配额 |
|---|---|---|
| `tank/timemachine` | dataset（SMB） | `quota=500G`（沿用现有 playbook 设定） |
| `tank/veeam-vol` | **zvol** → ReFS | `volsize` 与 `refreservation` 待定 |
| `tank/pbs-datastore` | dataset（阶段二才创建） | `quota` 待定 |

**强制要求**：全部必须配置 quota / refreservation，任一不得无限增长——这正是原 spec 标注了风险却从未实施的那一条。**具体数值待第 9 节确认后填入。**

**可选：持久化 L2ARC**。M920Q 的 ARC 只有 4GB，而 `tank` 没有 special vdev（元数据全在机械盘上）。可在 NVMe 上划 100–200GB 分区作 `tank` 的 L2ARC：ZFS 2.x 支持跨重启持久化，**且 L2ARC 丢失无害**（纯缓存），正适合单盘无冗余的场景。注意 L2ARC 的索引头会占用 ARC 内存，需在实测中观察。

---

## 6. 组件规范

### 6.1 M920Q / pve1 — Proxmox VE

**实机状态（2026-08-06 实测）**：PVE `pve-manager/9.0.3`，内核 `6.14.8-2-pve`，已是 `HomePVECluster` 成员（nodeid 2，1 票），Quorate。

#### 存储布局（实测）

| 池 | 载体 | 容量 | 用途 | 状态 |
|---|---|---|---|---|
| `rpool` | SanDisk SD8SBAT 128G（`sda`，Intel PCH SATA） | 117G | PVE 系统盘 | 安装时已建 |
| `mainpool` | MSI M450 1TB NVMe（`nvme0n1`） | 928G | **虚机 / 容器存储** | **已存在**，几乎全空 |
| `tank` | 2× WDC WD60EFPX（`sdb`/`sdc`，ASM1064） | 5.45T | **备份数据** | 2026-08-06 创建 |

> **命名说明**：`tank` 为 ZFS 文档惯例示例名，属占位。与本环境既有习惯（T7910 上为 `backup-pool`）不一致，建议改名以求自解释与对称。池为空时改名成本为零：`zpool export tank && zpool import tank backup-pool`。
>
> **`mainpool` 已存在**，无需创建；本规范早期版本中的 `nvme` 池名与实际不符，已更正。

#### `tank` 创建参数（已落地）

```bash
zpool create -f -o ashift=12 \
  -O compression=zstd -O atime=off -O xattr=sa \
  -O dnodesize=auto -O recordsize=128K \
  tank mirror \
  /dev/disk/by-id/ata-WDC_WD60EFPX-68JH4N1_WD-WC3K20AE5KA2 \
  /dev/disk/by-id/ata-WDC_WD60EFPX-68JH4N1_WD-WC3K20AE5KA9
```

- **by-id 锚定**：`zpool status` 直接显示 by-id 名称，从源头避免 T7910 那类盘符漂移
- `ashift=12`：磁盘为 512e（逻辑 512 / 物理 4096），须按物理扇区对齐
- **不设 special vdev**——单块 NVMe 无法组 mirror，而无冗余的 special vdev 一旦损坏**整个池全毁**（见 D10）
- **不设 `special_small_blocks`**——不沿用 T7910 的 128K（该值等于 `recordsize`，会把几乎所有数据块挤上 special vdev）
- `xattr=sa` 已显式设置；注意 OpenZFS 会将其回显为 `on`，以 `source=local` 判断是否生效

#### `zfs_arc_max` = 2 GiB

写入 `/etc/modprobe.d/zfs.conf` 并更新 initramfs。选 2 GiB 而非早期规划的 4 GiB，是因为**阶段一 PBS 不迁入**：pve1 只跑 Windows/AD 虚机与 Time Machine 共享，二者均为大块顺序写，对元数据缓存需求远低于 PBS 的 chunk-store GC/verify（海量小文件 stat）。

内存预算相应变为 **12 GiB / 16 GiB，余 4 GiB**（见 5.1）。

> **触发重新评估的条件**：若 PBS 迁入（D12），`tank` 无 special vdev、元数据全在 5400rpm 盘上，2 GiB ARC 将成为瓶颈，须重新分配。

#### 主机基线（待完成）

- `smartd`、`zed`（ZFS 事件告警）
- **`zfs-scrub` 定时器**——实测当前**一个都没启用**（`systemctl list-timers zfs-scrub*` 返回 0 条）。池永远不会被主动校验，位腐烂无法被发现。Debian 的 `zfsutils-linux` 自带 `zfs-scrub-monthly@.timer`，启用即可

### 6.1.1 PVE 存储层：为什么"池存在"不等于"PVE 能用"

这是两个独立的层次，容易混淆：

| 层次 | 含义 |
|---|---|
| **操作系统层** | `tank` 已创建并挂载于 `/tank`，shell 里可直接读写 |
| **PVE 存储层** | 除非在 `/etc/pve/storage.cfg` 中登记，**PVE 完全不知道它存在**——Web UI 建虚机时存储下拉框里不会出现它 |

**`nodes:` 限定为何是硬性要求**

`/etc/pve/storage.cfg` 由 pmxcfs 同步到**集群所有节点**。若登记 `tank` 时不加 `nodes pve1`，pve0 与 pve2 也会尝试激活一个它们本地并不存在的池，从而持续报错、状态恒为 `inactive`。

这不是假设——被清理掉的 `samsung256gpool`（对应已拆除的 256GB NVMe）正是这种残留：

```
zfspool: samsung256gpool
        pool samsung256gpool
        content rootdir,images
        mountpoint /samsung256gpool
        nodes pve1
```

**但"不加 `nodes` 限定"本身不是错误，而是另一种有意的用法。**存在两种正确模式：

| 模式 | 条件 | 效果 | 本环境实例 |
|---|---|---|---|
| **每节点同名池，不限定** | 每个节点上都真实存在同名池／数据集 | 存储 ID 可移植，**虚机可在节点间迁移** | `local-zfs`（各节点各有 `rpool`）、`vmdata` |
| **单节点独有，加限定** | 池只存在于某一节点 | 其他节点不会误报 `inactive` | `mainpool`（`nodes pve1`）、将来的 `tank` |

> 同名不要求同容量。实测 pve0 的 `mainpool` 为 1.81T、pve1 为 928G，存储 ID 在各节点分别解析到本地池，互不影响。

**错误模式则是第三种：不限定（或限定过宽）但目标并不存在**，表现为该节点上存储恒为 `inactive`。本次排查中发现两例：

| 存储 | 问题 | 处置 |
|---|---|---|
| `samsung256gpool` | 限定 `nodes pve1`，但对应 NVMe 已物理拆除 | ✅ 已删除定义 |
| `vmdata` | 限定 `nodes pve0,pve1`，但 pve1 上缺 `mainpool/vmdata` 数据集 | ✅ 已在 pve1 补建数据集，两节点均 `active` |

**`tank` 是否需要登记，取决于用途，并非全都需要：**

| 用途 | 是否需要登记 | 原因 |
|---|---|---|
| **Veeam 仓库 zvol**（作为 Windows 虚机磁盘） | **需要** | PVE 需在池上分配虚机磁盘 |
| Fileserver LXC bind mount `tank/timemachine` | 不需要 | bind mount 在容器配置中直接写宿主机路径，不经 PVE 存储层 |
| PBS datastore（阶段二） | 不需要 | PBS 自行管理 datastore |

因此现阶段唯一的登记理由是 Veeam 的 zvol，可推迟到建 Windows 虚机时再做。**登记时必须加 `--nodes pve1`**，因为 pve0 上不会有同名池：

```bash
pvesm add zfspool tank --pool tank --content rootdir,images --nodes pve1
```

### 6.2 PBS（阶段二才迁移）

阶段一 PBS 留在 T7910 不动。迁移时：

- 以 **LXC + bind mount** 部署，bind mount `tank/pbs-datastore`（见 D8）
- `zfs send` 迁移现有 datastore
- 保留现有备份作业定义与保留策略（7日/4周/6月）
- **新增**：`proxmox-backup-client` 覆盖 Linux 主机（现有 datastore 无 `host/` 目录，该能力完全未启用）
- **新增**：PBS 自身配置纳入备份

### 6.3 TurnKey Fileserver（LXC）— 已定案，见 D14

从 PVE 模板目录部署（`pveam available | grep turnkey`，Debian 12 底座，含 Samba、WebDAV CGI、Webmin:12321、web shell:12320）。

#### 必须手工移植的配置（TurnKey 不含）

**TurnKey Fileserver 只有 Samba，没有任何 Time Machine / AFP 支持。**以下配置需从 [`deploy-pbs-timemachine.yml`](../../ansible/playbooks/deploy-pbs-timemachine.yml) 完整移植——这是 Time Machine over SMB 真正困难的部分，务必逐行照搬，缺任何一行 macOS 都可能不识别该共享：

```ini
[global]
vfs objects = fruit streams_xattr
fruit:metadata = stream
fruit:model = MacSamba
fruit:posix_rename = yes
fruit:veto_appledouble = no
fruit:nfs_aces = no
fruit:wipe_intentionally_left_blank_rfork = yes
fruit:delete_empty_adfiles = yes
socket options = TCP_NODELAY IPTOS_LOWDELAY

[TimeMachine]
path = /srv/timemachine          # 容器内挂载点
valid users = timemachine
writable = yes
browseable = yes
fruit:time machine = yes
fruit:time machine max size = 500G
```

以及 Avahi 服务通告 `/etc/avahi/services/timemachine.service`（`_smb._tcp` + `_device-info._tcp` 带 `model=TimeCapsule8,119` + `_adisk._tcp` 带 `dk0=adVN=TimeMachine,adVF=0x82`），原文见上述 playbook。

#### 存储挂载

- 宿主机先建数据集：`zfs create -o quota=500G tank/timemachine`
- 容器配置 bind mount：`mp0: /tank/timemachine,mp=/srv/timemachine`
- **不需要注册 PVE 存储**——bind mount 不经 PVE 存储层（见 6.1.1）

#### 两个 LXC 特有的坑（未验证，实施时注意）

1. **Avahi 在非特权容器中可能无法启动**——需要 D-Bus 与网络多播。若失败，可改用特权容器，或调整 `lxc.apparmor.profile`。Avahi 不工作时 Mac 的「网络」里看不到该服务器，但仍可用 `smb://<ip>/TimeMachine` 手工连接。
2. **ZFS 数据集上的扩展属性**——`vfs_fruit` 依赖 xattr 存储 macOS 元数据。`tank` 已设 `xattr=sa`，容器内应能正常工作，但首次备份前建议验证。

#### 与现有 Ansible 的关系

现有 playbook 是内联任务的单体形式，与 [ansible-role-architecture.md](../designs/ansible-role-architecture.md) 的 role 约定不符（见 8.3）。**建议将 Samba/Avahi 配置抽成模板，由 Ansible 管理 TurnKey 容器内的 `/etc/samba/smb.conf`**，使 T7910 现有实例与 pve1 新实例共用同一份真相。

> **Webmin 与 Ansible 的边界**：Webmin 编辑的是标准 `smb.conf`，不像 TrueNAS 那样把配置吃进私有数据库，因此不构成 SSOT 冲突。但若 Ansible 拥有该文件，Webmin 中的改动会在下次 playbook 运行时被覆盖。**需明确约定**：要么 Webmin 只作查看、变更走 Ansible；要么将来共享增多后把 `smb.conf` 移出 Ansible 管理、改由 Webmin 负责。二者不可同时为真相来源。

### 6.4 Windows Server VM（AD DS + Veeam VBR CE）

- 由 ESXi V2V 迁移而来（PVE 8.2+ 自带 ESXi 导入向导）
- 系统盘放 `mainpool` 池；Veeam 仓库为 `tank/veeam-vol` zvol → 虚机内格式化 ReFS（64K 分配单元）
- 职责：
  - **AD DS 实验环境（长期驻留，这是保留该虚机的主要原因）**
  - ESXi 虚机备份（**新增能力**）
  - 接收 Windows 物理机 Veeam Agent 的备份（仅需改 Agent 的目标路径，Agent 为独立运行，不依赖 VBR）
- 迁移后成为 PVE 虚机，**纳入 PBS 备份**——此前作为 ESXi 虚机始终无人备份

**V2V 注意事项**：
- 迁移前卸载 VMware Tools
- 准备 VirtIO 驱动；稳妥做法为先以 SATA 控制器启动，再切换 VirtIO SCSI
- **Windows Server 2025 换硬件后可能需重新激活**
- **传输模式退化**：VBR 不再驻留 ESXi，无法使用 HotAdd，只能走 **NBD**（管理网络），大虚机备份明显变慢。万兆可缓解

### 6.5 T7910 — 副本端（阶段二）

阶段一保持现状（PBS 虚机 + `backup-pool`）。阶段二 PBS 迁走后：

- 以普通 **Debian 虚机**接收复制，直通 SAS3008（见 D5）
- 两块 HGST 建 ZFS mirror；两块 SM963 可继续作 special vdev 或释放
- 仅安装 `zfsutils-linux` + `sshd`
- 接收 `zfs send -i`；**复制方向建议为副本端主动拉取**，使主端不持有指向副本端的凭据（见 D11）
- 保留周期长于 M920Q
- **注意**：T7910 无法 WOL（见 D13），同步需配合手动开机

---

## 7. 迁移计划

> **安全线：阶段一第 7 步之前，T7910 上所有现有数据与服务原样不动。**任一步骤出问题均可回退。

### 7.1 阶段一

| # | 步骤 | 可回退 |
|---|---|---|
| 1 | ~~M920Q 拆除 256GB NVMe，装入 M.2-SATA 适配器；确认芯片型号~~ | ✅ **已完成**（ASM1064，见 5.2） |
| 2 | ~~装 PVE，两块 WD 建 ZFS mirror，NVMe 建虚机存储池~~ | ✅ **已完成**（`tank` 5.45T + 既有 `mainpool`；ARC 已调至 2G；`xattr=sa` 已显式设置） |
| 2a | ~~清理集群存储配置~~ | ✅ **已完成**（删除孤儿 `samsung256gpool`；补建 pve1 的 `mainpool/vmdata` 使 `vmdata` 在两节点均可用） |
| 2b | **启用 `zfs-scrub` 定时器**（当前一个都没有，池不会被主动校验） | ✓ |
| 2c | 配置 `smartd` 与 `zed` 告警 | ✓ |
| 3 | 部署 Fileserver LXC，移植 Samba + `vfs_fruit` 配置，Mac 切换并验证 Time Machine | ✓ |
| 4 | V2V 迁移 Windows VM 到 `mainpool` 池；建 `tank/veeam-vol` zvol，Veeam 重建仓库（现有 184G **建议直接起新链**，不迁移历史） | ✓ |
| 5 | Windows 物理机 Veeam Agent 目标改指 M920Q | ✓ |
| 6 | 把 Windows 虚机加入 PBS 备份作业 | ✓ |
| 7 | **验证：完整跑一轮各类备份并实测恢复** | ← **安全线** |
| 8 | 拆除 T7910 上的遗留：停 iSCSI target、删 `backup-pool/veeam-vol`（释放 184G）、删 ESXi 上的 `windows-server` 虚机 | ✗ |
| 9 | **记录 M920Q 的实际内存占用**，据此决定阶段二是否可行 | |

### 7.2 阶段二（条件满足才执行）

| # | 步骤 |
|---|---|
| 10 | M920Q 部署 PBS LXC + bind mount `tank/pbs-datastore` |
| 11 | `zfs send` 迁移 datastore 与 timemachine（约 130G，万兆约 12 分钟） |
| 12 | 备份作业目标切到 M920Q，验证 |
| 13 | T7910 销毁 `backup-pool`，起 Debian 虚机直通 SAS3008，建新池 |
| 14 | 配置每周增量复制（副本端拉取），配合手动开机 |
| 10 | 配置每周 `zfs send -i` 增量同步 | |

---

## 8. 仓库变更清单

### 8.1 删除

| 路径 | 说明 |
|---|---|
| `ansible/roles/pbs-iscsi/` | 整个 role |
| `terraform/esxi/windows-server.tf` | Windows 虚机定义 |
| `terraform/esxi/variables.tf` 中 `windows_*` 变量 | |
| `vault_windows_admin_password` | 若 PVE 侧不再使用 |
| `docs/specs/pbs-iscsi-veeam-spec.md` 等 3 份 | 归档至 `docs/archive/` |

### 8.2 新增

**阶段一：**

- **pve1 纳管**：已在 `terraform/proxmox/pve-cluster.tf` 中定义（`192.168.1.51`，root + `ansible_ssh_pass`），无需新建 inventory 条目
- 新 role：PVE 宿主基线。**注意手工已落地的部分需回填进 role**，以免 Ansible 与实机漂移：
  - `tank` 池创建（by-id 锚定、`ashift=12`、`compression=zstd`、`atime=off`、`xattr=sa`、`dnodesize=auto`、不设 special vdev 与 `special_small_blocks`）
  - `zfs_arc_max=2G`（`/etc/modprobe.d/zfs.conf` + `update-initramfs`）
  - `smartd`、`zed`、**`zfs-scrub-monthly@tank.timer`**（当前未启用）
- 新 role：Fileserver LXC（Samba + `vfs_fruit` + Time Machine + avahi）
- **新增备份告警**：分层告警（作业结果 + 备份新鲜度 + dead-man + 通道自检），详见事故报告 7.3
- **新增备份覆盖面校验**：详见事故报告 7.4——失败告警**抓不到**从未纳入作业的对象

**阶段二：**

- 新 role：PBS LXC 部署与 datastore 配置
- 新 role：增量复制任务（两端，副本端拉取）
- 新 role / playbook：ESXi 侧 Debian 副本虚机

### 8.3 重构

- `ansible/playbooks/deploy-pbs-timemachine.yml`：当前为内联任务的单体 playbook，与 [ansible-role-architecture.md](../designs/ansible-role-architecture.md) 的 role 约定不一致，借此机会重构为 role 并在新机器上复用
- `ansible/roles/pbs/`：调整为面向新 PBS 实例

### 8.4 已完成（截至 2026-08-06）

- `ansible/roles/pbs/defaults/main.yml`：`pbs_zfs_hdd_devices` 与 `pbs_zfs_nvme_devices` 改为 `/dev/disk/by-id/` 锚定（原 `sdb/sdc` 指向错误磁盘）
- `ansible/roles/pbs-client/defaults/main.yml`：`pbs_backup_vmids` 补入 107/109/110，并注明为何排除 108 与 9000
- `terraform/esxi/pbs.tf`：修正 PCIe 直通注释中的三处错误（HBA 地址、NVMe 地址、磁盘名）
- `requirements.txt`：`ansible-core` 加上界 `<2.21` 并注明原因（2.21 移除 `get_bin_path()` 的 `required` 参数，导致 `cloud.terraform` 动态 inventory 失效）
- `CLAUDE.md`：新增 Environment 段——未经许可不得安装任何软件包

---

## 9. 风险与未决项

### 9.1 未决项（需在实施前确认）

| # | 事项 | 影响 |
|---|---|---|
| 1 | **vCenter（665G）是否纳入备份** | 决定 Veeam 仓库 zvol 尺寸与备份窗口。vCenter 仅为管理 ESXi 存在 |
| 2 | 各数据集的 quota / refreservation 具体数值 | 见 5.3。**`tank` 已创建但尚未配置任何配额** |
| 3 | Fileserver 用 TurnKey LXC 还是 Debian LXC + 现有 Ansible | 见 6.3 |
| 4 | `special_small_blocks=128K` 是否为有意设计 | 见 2.3；**仅影响 T7910 的现有池**——新建的 `tank` 不设 special vdev，`special_small_blocks` 为 0 |
| 5 | **VMID 108 `veeam-worker` 的来历与去留** | 该虚机不在本仓库任何 Terraform/Ansible 定义中，仓库内唯一痕迹是提交 `8d520e5` 的说明文字。形态疑似 Veeam Proxmox VE 插件自动部署的 worker。**需确认是否在用**，并决定是否纳管或清理 |
| 6 | **`llm-server` 在两处重复定义** | 导致 esxi 动态 inventory 源整体解析失败，`pbs` 与 `windows-server` **当前不存在于 Ansible inventory 中**。已定位为 [`esxi_vms.yml`](../../ansible/inventory/esxi/esxi_vms.yml) 静态定义 + [`llm-server.tf:56`](../../terraform/esxi/llm-server.tf) 的 `ansible_host`，删其一即可 |
| 7 | **T7910 的 WOL 可行性与 I217-LM 的 MAC 地址** | 先前"仅有光口"的判断已被推翻（PCI 清单含 I217-LM 与 I210）。接线后需记录 MAC 写入 Ansible 变量。设计见事故报告 7.2 |
| 8 | **pve1 的 eno1 是否接线** | 当前 `NO-CARRIER`，但 `192.168.1.21` 已配置且 corosync **ring1 显示 connected**——因同网段可达，ring1 实际走的仍是万兆口。**双环名义存在、物理单点**。接线即可真正分离，无需改配置 |

**已解决并移出本表：**

| 原事项 | 结论 |
|---|---|
| M.2 转 SATA 适配器芯片型号 | ✅ ASM1064，PCIe 3.0 x1，链路未降级，无错误（见 5.2） |
| ZFS 池命名 | ✅ 备份池定名 `tank`；虚机存储池实为既有的 `mainpool`（非早期规划的 `nvme`） |

### 9.2 风险

| 风险 | 缓解 |
|---|---|
| **1TB NVMe 单盘无冗余**，承载 Windows/AD 虚机与 Fileserver LXC | 将这些虚机纳入 PBS 备份；风险明确接受（见 D10） |
| **两块 WD 共用外置电源适配器**，为共同故障点；ZFS 镜像可挡单盘故障，挡不住整机/供电故障 | 阶段二的二级副本；建议将磁盘固定妥当，避免震动与误碰 |
| **阶段一没有第二份副本** | 尽快推进阶段二；在此之前保留 T7910 现有 `backup-pool` 不销毁 |
| **`tank` 无 special vdev**，元数据全在 5400rpm 机械盘上，PBS 的 GC/verify 会慢 | 可选持久化 L2ARC；接受较慢的维护窗口 |
| Time Machine 迁移基本等同重开历史（sparsebundle 跨服务器搬迁易出问题） | 新库验证通过后，旧 `backup-pool/timemachine` 保留只读一段时间再删 |
| Veeam 备份 ESXi 的传输模式退化为 NBD | 万兆缓解；若不备 vCenter 则影响很小 |
| PBS-in-LXC 非官方支持路径 | 可退回虚机方案，代价为恢复 zvol 分层（见 D8） |
| **静态 IP 与 DHCP 地址池冲突** | 2026-08-05 曾因 192.168.1.249 被另一设备占用导致备份中断。须核查路由器 DHCP 池是否覆盖静态 IP 段 |
| WD 镜像顺序写入约 180MB/s 封顶，万兆并非瓶颈 | 若不足，M.2 适配器尚有空口，可加盘做双 mirror stripe |
| **无备份成功/失败告警** | 备份连续六个月失败而无人察觉的直接原因。须在阶段一同步建立告警 |

---

## 10. 附：本次评估中被否决的方案

供未来复查，避免重复评估。

| 方案 | 否决理由 |
|---|---|
| WD 盘接主板 SATA 后直通给虚机 | AHCI 控制器 `passthruCapable=False`，ESXi 明确不支持直通 |
| WD 盘经 RDM 给 Windows/TrueNAS | TrueNAS/ZFS 官方劝阻虚拟磁盘与 RDM；本地盘 RDM 不受 VMware 支持；客机内失去 SMART |
| 加装第三张 HBA 直通 | 需确认 PCIe 空槽；且 T7910 现有 6 张插卡（2 HBA、ConnectX-4、I210、2 NVMe 适配器） |
| T7910 整机换 Proxmox VE | 结构上最正确（消除直通把戏、vCenter 665G 直接消失），但需逐台评估 Cisco 虚机的 KVM 兼容性（ISE/CML 支持 KVM，DNAC 基本绑设备，EVE-NG 需嵌套虚拟化）。**列为后续独立课题** |
| M920Q 装 TrueNAS | 见 D4 |
| M920Q 装 Windows + Veeam（裸机） | 可行且迁移成本最低，但丢失 ZFS 完整性保护与 IaC 契合；被 PVE 方案取代 |
| 备份服务直接跑在现有 PBS 虚机上 | 可行，但无法解决「常开」与「备份与源同主板」两个结构性问题 |
| **M920Q 上用 SSD 做 special vdev** | **v1.0 曾建议，现作废**：确认只剩单块 NVMe，无冗余的 special vdev 损坏即毁整池（见 D10） |
| M920Q 扩容至 32GB 内存 | 无预算，内存固定 16GB（见 5.1） |
| 迁移 SAS3008 HBA 至 M920Q | riser 限长 110mm，卡长 167.65mm；且 HGST 为 SAS 盘、池含 U.2 special vdev，无法整体搬迁（见 D6） |
| Windows/AD 虚机留在 ESXi | 已否决——用户决定迁往 M920Q 以获得常开与 PBS 原生备份 |
| Veeam 改用 SMB 共享仓库（放弃 Fast Clone） | 保留作为简化选项；合成全备退化为真实读写合并，空间与时间成本上升 |
| 用 ghettoVCB 替代 Veeam 备份 ESXi 虚机 | 保留作为简化选项；无 CBT 增量，每次全量复制（vCenter 665G 为主要负担） |

---

## 11. 参考

- [Veeam Fast Clone 支持的文件系统](https://helpcenter.veeam.com/docs/backup/vsphere/backup_repository_block_cloning.html)
- [Veeam Backup & Replication 授权说明](https://helpcenter.veeam.com/docs/vbr/userguide/licensing.html)
- [Veeam Plug-in for Proxmox VE 授权](https://helpcenter.veeam.com/docs/vbproxmoxve/userguide/licensing.html)
- [Veeam 免费版产品页](https://www.veeam.com/products/free/backup-recovery.html)
- [Veeam 社区：Software Appliance 无 CE 授权](https://community.veeam.com/discussion-boards-66/linux-sw-appliance-12068)
- [PBS Plus 项目](https://github.com/pbs-plus/pbs-plus)
- [TurnKey Fileserver](https://www.turnkeylinux.org/fileserver)
- [Broadcom KB：本地存储的 RDM 配置](https://knowledge.broadcom.com/external/article/344431/raw-device-mapping-for-local-storage.html)

---

## 12. 交接说明（2026-08-06）

> 面向接手本工作的人或工具。**请先读第 3 节的决策记录**——本文档设立该节的原因，正是上一份规范只记「怎么做」不记「为什么」，导致本次评估必须从零考古（见 1.1）。不要在未读决策记录的情况下推翻既有选择。

### 12.1 当前状态一句话总结

备份已恢复（10 个工作负载均有 2026-08-06 的恢复点），**但事故未关闭**——根因未消除，T7910 已再次关机，下一次 02:00 作业仍会失败。详见[事故报告](../incidents/2026-08-05-backup-outage.md) 1.1 节。

### 12.2 已落地的变更

**pve1（192.168.1.51）实机：**

| 项 | 状态 |
|---|---|
| `tank` ZFS 镜像池 | ✅ 5.45T，by-id 锚定，`ashift=12`/`zstd`/`atime=off`/`xattr=sa` |
| `zfs_arc_max` | ✅ 2 GiB（`/etc/modprobe.d/zfs.conf` + initramfs） |
| 孤儿存储 `samsung256gpool` | ✅ 已删除 |
| `mainpool/vmdata` | ✅ 已补建，`vmdata` 两节点均 active |
| `zfs-scrub` 定时器 | ❌ **未启用**——池目前不会被主动校验 |
| `smartd` / `zed` | ❌ 未配置 |

**仓库变更（未提交）：**

| 文件 | 变更 |
|---|---|
| `requirements.txt` | `ansible-core` 加上界 `<2.21` 并注明原因 |
| `ansible/roles/pbs/defaults/main.yml` | 磁盘改 by-id 锚定（原 `sdb/sdc` 指向错误磁盘） |
| `ansible/roles/pbs-client/defaults/main.yml` | 补入 VMID 107/109/110 |
| `terraform/esxi/pbs.tf` | 修正 PCIe 直通注释三处错误 |
| `CLAUDE.md` | 新增「未经许可不得安装软件包」 |
| `docs/specs/`、`docs/incidents/` | 本文档与事故报告 |

**pve0 线上作业**：备份作业 VMID 已由 100–106 改为 100–107,109,110。

### 12.3 下一步：阶段一第 3 步（Fileserver LXC）

按 7.1 节，2b/2c 未做，可与第 3 步并行。第 3 步的完整规格见 **6.3 节**，要点：

1. `zfs create -o quota=500G tank/timemachine`
2. 从 `pveam` 部署 TurnKey Fileserver LXC，bind mount `mp0: /tank/timemachine,mp=/srv/timemachine`
3. **完整移植 `vfs_fruit` 与 Avahi 配置**——TurnKey 不含，且这是唯一困难的部分，配置原文在 6.3 与 [`deploy-pbs-timemachine.yml`](../../ansible/playbooks/deploy-pbs-timemachine.yml)
4. Mac 切换后验证，**旧的 `backup-pool/timemachine` 保留只读一段时间**（Time Machine 跨服务器迁移基本等同重开历史）

### 12.4 环境与访问方式

| 主机 | 地址 | 认证 |
|---|---|---|
| pve0 / pve1 / pve2 | `.50` / `.51` / `.52` | **root + 密码**（`vault_proxmox_password`），非密钥。定义见 [`pve-cluster.tf`](../../terraform/proxmox/pve-cluster.tf) |
| PBS | `192.168.1.249` | SSH 密钥（`~/.ssh/id_ed25519`） |
| vCenter | `192.168.1.250` | `terraform/esxi/terraform.tfvars`（该文件 gitignored） |

**非交互密码 SSH 不要安装 `sshpass`**（CLAUDE.md 明令禁止）。用 OpenSSH 自带机制：

```bash
export SSH_ASKPASS=<脚本>          # 脚本内部执行 ansible-vault view 取值，密码不落盘
export SSH_ASKPASS_REQUIRE=force
setsid ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@192.168.1.51
```

**Ansible**：先 `cd /workspaces/IaC/ansible`。inventory 已恢复（15 台主机），但 **`pbs` 与 `windows-server` 仍缺失**——`llm-server` 在 [`esxi_vms.yml`](../../ansible/inventory/esxi/esxi_vms.yml) 与 [`llm-server.tf:56`](../../terraform/esxi/llm-server.tf) 重复定义，导致 esxi inventory 源解析失败。删其一即可（9.1 未决项 6）。

### 12.5 优先处理事项

**安全（最高优先）**：排查过程中多项凭据明文进入终端与会话记录，**尚未轮换**。清单与处置要求见事故报告第 9 节。

**其次**：事故报告 6.1 节的 P0 五项——它们是事故关闭的前置条件，其中「保证下一个备份窗口目标可用」最紧急，因为 T7910 现已关机。

### 12.6 需要人工提供的信息

| 事项 | 用途 |
|---|---|
| T7910 上 I217-LM 的 MAC 地址 | WOL 配置（设计见事故报告 7.2） |
| pve1 的 eno1 是否接线 | 当前 corosync ring1 虽显示 connected，但因同网段可达，实际仍走万兆口——**双环名义存在、物理单点** |
| vCenter（665G）是否纳入备份 | 决定 Veeam 仓库 zvol 尺寸 |
| `98:b6:e9:02:57:11` 是哪台设备 | IP 冲突根因确认 |

### 12.7 给接手者的三点提醒

1. **区分「已证实」与「推断」。**本次排查中曾数次基于单一样本给出过于肯定的结论，后被证伪（详见事故报告第 8 节经验教训 6–8）。事故报告已对每条结论标注证据强度，请沿用该习惯。
2. **容量数字有三种口径**，不可混用：`zfs list` 落盘量、`pvesm list` 逻辑量、`pvesm status` 池占用。本次曾因此把「300 GiB 置备盘」误读为「322 GB 照片库」。
3. **手工落地的变更必须回填进 Ansible role**（见 8.2），否则实机与代码漂移——这正是本次事故中多个问题的共同成因。
