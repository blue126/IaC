# PBS 从 ESXi V2V 迁移到 PVE 的经验教训 (2026-08-11)

## 1. 背景

把 Proxmox Backup Server 从 T7910（ESXi 8.0.3）迁到 pve1（M920Q），以摆脱 T7910 手动开机窗口对备份频率的限制 —— 这是 2026-08-05 备份事故的直接成因之一。

方式：**PVE 原生 ESXi 导入（V2V）搬系统盘 + PBS sync 搬 datastore**。决策依据见备份架构整合规范 D15（取消两级副本）与 D16（datastore 落 zvol）。

**结果**：373.185 GiB / 113,895 chunks 全量迁移，verify 10/10 组 0 errors，pve0 端到端备份成功且增量复用 97%。

## 2. 核心概念定义

- **V2V（Virtual-to-Virtual）迁移**：把虚机从一个 hypervisor 搬到另一个。完整导入会搬虚拟磁盘并映射部分虚机配置，但**不会移动硬件，也不会把 PCI 直通后端的磁盘内容转成虚拟磁盘**。
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

### 4.1 MAC 冲突 —— 同一二层域内两台同 MAC 的主机无法可靠共存

本次的完整 ESXi 导入**保留了源虚机的 MAC**（导入元数据里带 `net0` 的 MAC，我又在 `qm create` 里照抄了它）。这不是所有 V2V 方式的必然行为 —— **每次都要检查 `qm config` 确认**，不能假设保留或重新生成。新旧两台 PBS 同时开机（传输数据必须如此）时，交换机的 MAC 表在两个端口间反复翻转，二层直接乱掉。

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

> **教训**：V2V 后应尽早装 `qemu-guest-agent`。它走 virtio-serial **不依赖客户机网络**，是网络出问题时重要的带外通道之一 —— 但**不是唯一的**：PVE 的 noVNC 控制台、串口控制台、救援 ISO 同样不依赖客户机网络，而且不需要预先安装任何东西。

### 4.3 改 datastore 配置路径 ≠ 创建 datastore

把 `datastore.cfg` 里的 `path` 指向新盘后，sync 立刻失败：

```
TASK ERROR: unable to open chunk store at "/mnt/datastore/.chunks" - No such file or directory
```

PBS datastore 需要 `.chunks/` 下 65536 个子目录的完整结构。**只改 `datastore.cfg` 不会初始化它** —— 必须走 PBS 支持的 datastore 创建操作（CLI `proxmox-backup-manager datastore create`、Web UI 的 Add Datastore、或对应 API，三者等效）。手工建目录理论上可行，但容易漏掉 owner、mode、`.lock` 等约束，不应作为方法。

⚠️ **V2V 之后 `datastore.cfg` 里已经有同名 datastore**，直接 `create` 会因重名失败。必须先 `remove`（**务必不带 `--destroy-data`**）再 `create`。

### 4.4 重建 datastore 会连带删除关联配置

为初始化结构而 `datastore remove` + `create` 之后：

- **ACL 全部丢失** → pve0 报 `Cannot find datastore 'backup-storage', check permissions and existence!`
- **sync job 一并被删**
- **`datastore.cfg` 里的其他属性也回到默认** —— 本次 `gc-schedule daily` 就需要在 `create` 时重新指定

`datastore remove` 有 `--keep-job-configs`（默认 `false`）这个选项，正说明**关联作业是需要显式处理的对象**。

> **教训**：删除前应清点 `datastore.cfg`、`acl.cfg`、`sync.cfg`、`prune.cfg`、`verification.cfg`，创建后逐项对照恢复 —— 而不是像本次这样只恢复了两条 ACL 和一个 sync job。prune / verify 作业本次恰好没有配置，否则会静默丢失。

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

全部 10 个备份组的 owner 都成了 `root@pam`，而 pve0 用 `backup@pbs!automation` 备份。PBS 不允许跨所有者追加。

**owner 的来源要分清**（早先版本这里写错了）：

| | 决定什么 |
|---|---|
| **sync job 的 `--owner`** | 目标端新建备份组的 owner。**未设置时默认 `root@pam`** ← 本次问题的真正来源 |
| remote 的 auth-id | 只决定在**源端**能读到哪些组，与目标 owner 无关 |

**所以正确做法是建 sync job 时直接指定 owner，根本不会有这个问题**：

```bash
proxmox-backup-manager sync-job create migrate-old \
  --store backup-storage --remote old-pbs --remote-store backup-storage \
  --owner 'backup@pbs!automation'     # ← 关键，省掉事后批量 change-owner
```

事后补救才需要 `proxmox-backup-client change-owner`。该命令需要**有效认证 + TLS 信任**，本次因证书不被系统 CA 信任而必须显式提供指纹：

```bash
export PBS_FINGERPRINT="$(proxmox-backup-manager cert info | grep -i 'Fingerprint (sha256)' | sed 's/.*: //')"
export PBS_REPOSITORY='root@pam@localhost:backup-storage'
proxmox-backup-client change-owner "ct/103" 'backup@pbs!automation'   # 交互输入密码
```

> 密码优先用交互输入或 `PBS_PASSWORD_FILE` / `PBS_PASSWORD_FD`，**不要用 `PBS_PASSWORD` 环境变量** —— 会残留在 shell 历史与进程环境里。证书受系统 CA 信任时则无需指纹。

## 5. 性能实测：瓶颈不在网络

| 环节 | 速率 |
|---|---|
| 万兆链路实测 | 9.3 Gbit/s ≈ 1160 MB/s |
| `tank`（2× WD 6TB mirror）顺序写 | ~180 MB/s |
| **PBS sync 实际达成** | **62.45 MiB/s** |

**可以确定的**：网络不是瓶颈 —— 62 MiB/s 距离万兆的 1160 MB/s 差了近 20 倍，且连机械盘顺序能力的 40% 都没到。

**未经证实的**：把它归因于"元数据随机 I/O + 无 special vdev"是**合理假设，但本次没有测量验证**。同样能解释 62 MiB/s 的还有：

- **PBS sync 的 `worker-threads` 默认为 1** —— 单线程串行拉取本身就可能是限制
- 源端也是机械盘，**读取侧**同样有寻道开销
- TLS 加解密、chunk 校验的 CPU 开销
- 目标端 zvol 的同步写行为

> **教训**：迁移时没有采集 `zpool iostat -v 1`、`iostat -x 1`、CPU 与 worker 利用率，所以只能排除网络，无法定位真凶。**下次应在传输期间抓这些数据** —— 否则事后只能推测。

**这也影响了后续决策的可靠性**：规范 **D17**（换 2.5G 网卡腾槽位加 special vdev）的动机来自这个未经验证的归因。在实测确认瓶颈之前，D17 属于**基于假设的提案**。

> ⚠️ **一个已被指出的错误**：早先版本建议"先试可逆的 L2ARC 再考虑 special vdev"。**这个建议是错的** —— L2ARC 是**读缓存**，对 sync 期间的 chunk 创建、目录元数据更新、数据写入毫无帮助，冷数据全量拉取更没有命中机会。要可逆地验证写入侧瓶颈，应该测 pool 的实际 I/O、提高 sync 并发、或临时同步一组数据到 SSD 做对照。

## 6. 下次迁移的正确顺序

> 早先版本的步骤表遗漏了**临时 IP** 与**切点屏障**两处，照抄会踩坑。以下为修订版。

**准备**

1. **备份 PBS 自身配置** —— `/etc/proxmox-backup/` 打包并拉到异地。这是**第一个必须建立的回滚保障**（但它救不了 datastore 数据，见下方风险清单）
2. 清点源端配置：`datastore.cfg`、`acl.cfg`、`sync.cfg`、`prune.cfg`、`verification.cfg`
3. 目标端建 zvol，设 `refreservation`。本环境实测 compressratio 仅 1.01x（PBS 已自行压缩）故关闭 ZFS 压缩 —— **这是本地调优结论，不是通用步骤**

**导入（源端保持关机）**

4. V2V 导入系统盘。⚠️ **系统盘带着源端的静态 IP**，光改 MAC 不解决 IP 冲突
5. **目标端首次启动前先断开虚拟网卡**（`qm set <id> --net0 ...,link_down=1`），或确保源端仍关机
6. 经 **PVE 控制台**（noVNC）进入目标：装 `qemu-guest-agent`、配**临时 IP**、把接口命名改成不依赖 MAC
7. 关机 → 改 MAC → 启动 → 确认目标端网络正常

**数据传输**

8. 目标盘格式化、挂载、写 `fstab`（按 UUID）
9. `datastore remove`（**不带 `--destroy-data`**）→ `datastore create`，**并重新指定 `--gc-schedule` 等属性**
10. **恢复 ACL**（对照第 1 步备份）—— 必须在 sync 之前，否则第 11 步指定 owner 会失败
11. 建 remote + sync job，**`--owner` 直接设为最终客户端的 auth-id**（省掉事后批量 `change-owner`）
12. 启动源端 → 首轮全量 sync
    - 建议同时采集 `zpool iostat -v 1` / `iostat -x 1` / CPU 与 worker 利用率，以便定位瓶颈
    - `--remove-vanished` 保持关闭，避免迁移期间传播误删

**切换**

13. **建立切点屏障**：暂停 PVE 侧备份作业与源端的 prune/GC → 等在途任务结束 → **再跑一次增量 sync** → 比对两端的组数、快照数与最新时间
14. 全量 verify
15. 源端关机 → 目标端改回原 IP
16. 跑一次真实备份，确认日志里有 `Downloading previous manifest` 与 `reused X%`

**源端销毁的门槛（不是时间）**

17. 以下**全部满足**才可销毁源端，两周只是最短观察期：
    - 完成**一台代表性 VM/CT 的实际恢复并启动验证**
    - 完成一次计划内备份 + 一次后续增量
    - 迁移后 datastore 全量 verify 通过
    - 两端组/快照清单一致
    - 期间源端应**禁用 autostart 并断开虚拟网卡**，防止误启动造成 IP 冲突

> ⚠️ **不可逆操作清单**（不止配置备份那一处）：格式化错误的块设备、`datastore remove --destroy-data true`、提前销毁源端、误加**单盘** special vdev、在唯一副本上误运行 prune/GC。每一处动手前都应确认目标并有停止条件。

## 7. Q&A 摘要

**Q：V2V 之后 PBS 服务起来了，是不是就迁移完了？**
A：不是。datastore 数据在物理盘上，不随虚机迁移。此时 PBS 服务在跑但 datastore 不可用。

**Q：怎么确认迁移的 chunk 不只是"存在"而是真正可用？**
A：两个证据。一是全量 `verify`（校验每个 chunk 的哈希）；二是跑一次真实备份，看日志里有没有 `Downloading previous manifest` 和 `reused X%` —— 能增量复用说明历史 chunk 被正确索引和引用。本次复用 97%。

**Q：为什么万兆网络下只有 62 MiB/s？**
A：瓶颈是元数据密集的随机 I/O，不是带宽。113,895 个 chunk 散列写入 65536 个目录，机械盘寻道主导，且 `tank` 无 special vdev。

**Q：`Cannot find datastore ... check permissions and existence` 是什么意思？**
A：这条消息**同时覆盖两类原因** —— datastore 名称/状态不可用，以及 auth-id 缺少权限。本次是后者（ACL 丢失），但排查时两者都要查，不能直接跳到权限。

**Q：迁移后旧 PBS 能马上删吗？**
A：不能。它是唯一的回滚路径，尤其在已决定不做两级副本（D15）的前提下——删掉后新 PBS 的 datastore 就是全世界唯一一份。建议关机保留两周。

## 8. 遗留项

- **恢复能力仍只验证到文件级。** verify 通过、增量复用正常，但**从未实际还原过一台虚机**。规范 v1.9 记录的这条遗留项依然开着，且现在多了一层含义：迁移后的数据从未被真正用于恢复。
- 旧 PBS（ESXi Vmid 47）已关机待命，数据完好。**销毁门槛见第 6 节第 17 步 —— 时间不是条件**；在整机恢复验证完成前不应销毁。
