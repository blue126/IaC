# PBS 从 ESXi V2V 迁移到 PVE 的经验教训 (2026-08-11)

## 1. 背景

把 Proxmox Backup Server 从 T7910（ESXi 8.0.3）迁到 pve1（M920Q），以摆脱 T7910 手动开机窗口对备份频率的限制 —— 这是 2026-08-05 备份事故的直接成因之一。

方式：**PVE 原生 ESXi 导入（V2V）搬系统盘 + PBS sync 搬 datastore**。决策依据见备份架构整合规范 D15（取消两级副本）与 D16（datastore 落 zvol）。

**结果**：373.185 GiB / 113,895 chunks 全量迁移，verify 10/10 组 0 errors，pve0 端到端备份成功且增量复用 97%。

## 2. 核心概念定义

- **V2V（Virtual-to-Virtual）迁移**：把虚机从一个 hypervisor 搬到另一个。搬的是**虚拟磁盘**——宿主机上的物理盘、直通设备一律搬不走。
- **PVE ESXi 导入**：PVE 8.2+ 内置能力。配置 `esxi` 类型存储指向 ESXi 主机后，`qm create --scsi0 <storage>:0,import-from=<volid>` 即可直接拉取并转换 vmdk。源虚机需关机。
- **PBS chunk**：PBS 的内容寻址存储单元，平均约 3.35 MiB，散列存放于 `.chunks/` 下 **65536 个子目录**。这个结构决定了 PBS 的 I/O 特征是**元数据密集的随机读写**，而非顺序吞吐。
- **PBS sync job**：datastore 之间的原生同步机制，逐 chunk 拉取并校验。相比 `rsync` 的优势是无需在源端安装额外软件，且理解 PBS 的数据结构。
- **备份组 owner**：PBS 为每个备份组（如 `ct/103`）记录一个所有者 auth-id，存于 `<datastore>/<type>/<id>/owner`。**非所有者无法向该组追加快照**。

## 3. 最重要的一条：V2V 搬不走 datastore

旧 PBS 的 datastore 在 `backup-pool` 上，而该池建在**通过 HBA 直通给客机的物理盘**（2× HGST 8TB + 2× NVMe special vdev）。这些盘在 T7910 机箱里，规范 D6 已定「不迁移 HBA、不搬运磁盘」。

所以迁移**必然是两段式**：

| | 内容 | 手段 |
|---|---|---|
| 第一段 | 系统盘（配置、用户、token、ACL、作业定义都在里面） | V2V 导入 |
| 第二段 | datastore 数据 | PBS sync / rsync |

> **教训**：V2V 完成后虚机能开机、服务能起来，很容易误以为"迁移成功"。实际此时 **datastore 指向一个不存在的路径，PBS 完全不可用**。汇报进度时必须说清楚处在哪一段。

## 4. 踩过的坑

### 4.1 MAC 冲突 —— 两台同 MAC 的虚机不能共存

V2V 会**保留源虚机的 MAC**。新旧两台 PBS 同时开机（传输数据必须如此）时，交换机的 MAC 表在两个端口间反复翻转，二层直接乱掉。

症状很有迷惑性：**新 PBS 能 ping 通网关、pve0、pve1，唯独够不到旧 PBS**（ARP 显示 `FAILED`）。因为一台主机无法与"和自己同 MAC"的主机通信。同时容器侧对两台的 TCP 探测呈现**间歇性成功**。

### 4.2 改 MAC 又打断了接口命名

改 MAC 后虚机彻底失联。原因：客户机里的接口名 `nic0` **是按 MAC 绑定的**，MAC 一变规则失配，接口被重命名，而 `/etc/network/interfaces` 里写的是 `auto nic0`。

雪上加霜的是**该虚机没装 qemu-guest-agent**（源是 VMware 虚机，装的是 VMware Tools），无法通过 agent 查看内部状态。

**解决**：先改回原 MAC 恢复访问，在客户机里加一条**按驱动匹配、不依赖 MAC** 的命名规则，再改 MAC：

```
# /etc/systemd/network/10-nic0.link
[Match]
Driver=virtio_net

[Link]
Name=nic0
```

> **教训**：V2V 后应尽早装 `qemu-guest-agent`。它走 virtio-serial**不依赖网络**，是网络配置出问题时唯一的远程观测手段。

### 4.3 改 datastore 配置路径 ≠ 创建 datastore

把 `datastore.cfg` 里的 `path` 指向新盘后，sync 立刻失败：

```
TASK ERROR: unable to open chunk store at "/mnt/datastore/.chunks" - No such file or directory
```

PBS datastore 需要 `.chunks/` 下 65536 个子目录的完整结构，**只有 `proxmox-backup-manager datastore create` 会创建它**。

### 4.4 重建 datastore 会连带删除 ACL 和 sync job

为初始化结构而 `datastore remove` + `create` 之后：

- **ACL 全部丢失** → pve0 报 `Cannot find datastore 'backup-storage', check permissions and existence!`（措辞误导，实际是权限问题不是"不存在"）
- **sync job 一并被删** → 需重建

**迁移前备份的 `/etc/proxmox-backup/` 在此刻救了场** —— `acl.cfg` 里完整记录着原始两条：

```
acl:1:/datastore/backup-storage:backup@pbs:DatastoreBackup
acl:1:/datastore/backup-storage:backup@pbs!automation:DatastoreAdmin
```

> **教训**：规范 §2.4 记录的"PBS 未备份自身配置"是**真实且会兑现的风险**。这次把配置备份列为迁移第一步是正确的。

### 4.5 备份组 owner 不匹配导致新备份被拒

数据迁完、verify 通过、存储 active，pve0 备份仍失败：

```
Error: backup owner check failed (backup@pbs!automation != root@pam)
```

sync job 是用 `root@pam` 拉取的，所以**全部 10 个备份组的 owner 都成了 `root@pam`**；而 pve0 用 `backup@pbs!automation` 备份。PBS 不允许跨所有者追加。

修复需 `proxmox-backup-client change-owner`，且该命令**必须提供指纹与密码**，否则报 `certificate validation failed`：

```bash
export PBS_FINGERPRINT="$(proxmox-backup-manager cert info | grep -i 'Fingerprint (sha256)' | sed 's/.*: //')"
export PBS_PASSWORD='...'
export PBS_REPOSITORY='root@pam@localhost:backup-storage'
proxmox-backup-client change-owner "ct/103" 'backup@pbs!automation'
```

## 5. 性能实测：瓶颈不在网络

| 环节 | 速率 |
|---|---|
| 万兆链路实测 | 9.3 Gbit/s ≈ 1160 MB/s |
| `tank`（2× WD 6TB mirror）顺序写 | ~180 MB/s |
| **PBS sync 实际达成** | **62.45 MiB/s** |

连机械盘顺序能力的 **40%** 都没跑到。原因是 PBS 的 I/O 特征：113,895 个 chunk 要分散写入 65536 个目录，**寻道开销主导**；而 `tank` **没有 special vdev**，元数据与数据争抢同一组磁头。

判据：若瓶颈是网络，速率会接近 1 GB/s；若是顺序带宽，会稳定在 180 MB/s。实测 62 MiB/s **且全程平稳**，正是随机 I/O 受寻道限制的特征。

> 由此引出规范 **D17**（待评估）：万兆对该负载严重过剩，可换 2.5G 腾出 PCIe 槽位加 special vdev。但 special vdev **必须镜像且不可移除**，是单向决定；建议先试可逆的 L2ARC。

## 6. 排查方法上的教训

本次和同日的 [ESXi 链路抖动笔记](./2026-08-11-esxi-link-flapping-dampening.md) 一样，多次在**不完整信息上下判断**：

| 错误 | 教训 |
|---|---|
| `pgrep -f "qm create 113"` 匹配到**自己的命令行**，误报任务仍在运行（实际早已 `TASK OK`） | 用 `pgrep` 匹配含自身参数的字符串时必须排除自己，或改查任务日志 |
| 用 `zfs list` 的 `REFER` 判断导入进度，得出"卡住"的结论 | 进度应看权威来源——`/var/log/pve/tasks/` 下的任务日志有精确百分比 |
| 轮询脚本因工作目录被重置而全部空转，一度以为任务无进展 | 脚本失败与任务无进展是两件事，输出为空时先验证工具本身 |

## 7. 下次迁移的正确顺序

1. **备份 PBS 自身配置**（`/etc/proxmox-backup/` 打包并拉到异地）—— 唯一不可逆的风险点
2. 目标端建 zvol，设 `refreservation`，**关闭 ZFS 压缩**（PBS 已压缩，实测 compressratio 仅 1.01x）
3. V2V 导入系统盘；**同时改 MAC**（避免与源冲突）—— 但改 MAC 前先确认客户机的接口命名不依赖 MAC
4. 装 `qemu-guest-agent`
5. 目标盘格式化（XFS）、挂载、写 `fstab`
6. **`datastore create`**（不要只改配置路径）
7. 配 remote + sync job，拉取数据
8. **恢复 ACL**（对照第 1 步的备份）
9. **改备份组 owner** 为客户端实际使用的 auth-id
10. 全量 verify
11. 源端关机 → 目标端改回原 IP
12. 跑一次真实备份，确认能**增量复用**历史快照
13. 源端保留两周再销毁

## 8. Q&A 摘要

**Q：V2V 之后 PBS 服务起来了，是不是就迁移完了？**
A：不是。datastore 数据在物理盘上，不随虚机迁移。此时 PBS 服务在跑但 datastore 不可用。

**Q：怎么确认迁移的 chunk 不只是"存在"而是真正可用？**
A：两个证据。一是全量 `verify`（校验每个 chunk 的哈希）；二是跑一次真实备份，看日志里有没有 `Downloading previous manifest` 和 `reused X%` —— 能增量复用说明历史 chunk 被正确索引和引用。本次复用 97%。

**Q：为什么万兆网络下只有 62 MiB/s？**
A：瓶颈是元数据密集的随机 I/O，不是带宽。113,895 个 chunk 散列写入 65536 个目录，机械盘寻道主导，且 `tank` 无 special vdev。

**Q：`Cannot find datastore ... check permissions and existence` 是什么意思？**
A：措辞有误导性。datastore 通常存在，问题在**权限**——检查 ACL 是否覆盖了该客户端使用的 auth-id。

**Q：迁移后旧 PBS 能马上删吗？**
A：不能。它是唯一的回滚路径，尤其在已决定不做两级副本（D15）的前提下——删掉后新 PBS 的 datastore 就是全世界唯一一份。建议关机保留两周。

## 9. 遗留项

- **恢复能力仍只验证到文件级。** verify 通过、增量复用正常，但**从未实际还原过一台虚机**。规范 v1.9 记录的这条遗留项依然开着，且现在多了一层含义：迁移后的数据从未被真正用于恢复。
- 旧 PBS（ESXi Vmid 47）已关机待命，数据完好，建议保留两周。
