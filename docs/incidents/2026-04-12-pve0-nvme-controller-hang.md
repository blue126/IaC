# 事故报告：NVMe 控制器挂死导致 mainpool 降级（2026-04-12 与 2026-08-11 两次）

> **事故编号**: INC-2026-04-12
> **报告日期**: 2026-08-04（一至五节）；2026-08-12（第六节及 5.1 状态更新）
> **状态**: 已缓解，永久处置进行中 — 走保修更换
> **严重级别**: 高 — 镜像冗余失效 114 天无人察觉；期间无在运备份链路，4 月之后无任何新的恢复点
> **时区**: 本报告所有无后缀时间均为 **AEST (UTC+10)**；带 `Z` 后缀者为 UTC（PBS 快照 ID 使用 UTC）
> **主机**: pve0 · PVE 内核 6.14.8-2-pve · ZFS 2.3.3-pve1
> **同步来源**: 本文档与 Notion 上的同名页面保持同步（Homelab → Device and Service → Proxmox(PVE0)）

---

> [!WARNING]
> **一句话总结**：mainpool 镜像中的一块 Samsung 990 PRO 2TB（S7HENU0YA65028L）于 2026-04-12 因 NVMe 控制器挂死被内核禁用，池降级运行 **114 天无人察觉**，直至 2026-08-04 例行操作中被发现。经冷启动后设备完全恢复，SMART 全项健康，已重新同步。**故障域集中于该设备或其专属的 PCIe / 供电路径；现有证据不足以在设备固件、控制器硬件、插槽供电之间进一步区分。**
>
> **追记：2026-08-11 03:00，同一块盘以相同的核心故障签名再次挂死（详见第六节）。** 四个月内第二次，内核 controller reset 与 PCIe remove/rescan 均无法恢复，而同固件的对照盘至今零错误——**4.3 节所立的更换判据已经成立，决定走保修更换**。本次未观察到持久数据损坏，且因备份链路已在两次故障之间修复，不再处于四月那种"既无冗余、也无在运备份"的处境。

---

## 一、故障是如何发现的

发现过程完全是**偶然**——这正是本次事件最值得警惕的地方。

1. 当日工作目标是在 PVE0 上新建一台 Windows VM（VMID 110）用于运行 7x24 Claude Desktop。
2. 创建 VM 时误将虚拟磁盘放在了 `local-zfs`，用户核对硬件配置后指出应使用 `vmdata` 存储池。
3. 执行 `qm disk move` 迁移磁盘前，例行检查目标存储的容量与健康状况，运行 `pvesm status` 与 `zpool list`，发现：

```
NAME       SIZE  ALLOC   FREE  CKPOINT  EXPANDSZ   FRAG    CAP  DEDUP    HEALTH  ALTROOT
mainpool  1.81T   376G  1.45T        -         -    16%    20%  1.00x  DEGRADED  -
rpool      928G  57.5G   870G        -         -     5%     6%  1.00x    ONLINE  -
```

`mainpool` 状态为 **DEGRADED**——而 `vmdata` 存储正是建立在这个池上（`mainpool/vmdata`）。

> [!TIP]
> **关键教训**：如果当天没有因为存储位置错误而去检查 pool 状态，这个故障可能会继续潜伏下去。系统运行正常、Web UI 没有弹窗、没有任何告警邮件——降级状态对日常使用是完全无感的。

## 二、故障症状

### 2.1 ZFS 层面

```
  pool: mainpool
 state: DEGRADED
status: One or more devices have been removed.
	Sufficient replicas exist for the pool to continue functioning in a
	degraded state.
  scan: scrub repaired 0B in 00:07:23 with 0 errors on Sun Apr 12 00:31:24 2026
config:

	NAME                                              STATE     READ WRITE CKSUM
	mainpool                                          DEGRADED     0     0     0
	  mirror-0                                        DEGRADED     0     0     0
	    nvme-Samsung_SSD_990_PRO_2TB_S7HENU0YA65028L  REMOVED      0     0     0
	    nvme-Samsung_SSD_990_PRO_2TB_S7HENU0YA65040W  ONLINE       0     0     0

errors: No known data errors
```

注意 `scan:` 行——最后一次 scrub 完成于 **Apr 12 00:31**，0 错误。故障恰好发生在这次 scrub 完成后约 6 小时。

### 2.2 设备层面

设备节点仍然存在（因为系统未重启），但容量显示为 **0B**：

```
# lsblk -d -o NAME,SIZE,MODEL,SERIAL
nvme1n1   1.8T Samsung SSD 990 PRO 2TB       S7HENU0YA65040W
nvme0n1     0B Samsung SSD 990 PRO 2TB       S7HENU0YA65028L
```

（勘误：本报告初稿将此处及下文多处标为 `nvme list`。实际输出格式为 `lsblk`，且 pve0 上未安装 nvme-cli——`nvme` 命令不存在。）

SMART 完全无法读取：

```
# smartctl -a /dev/nvme0n1
Read NVMe Identify Controller failed: NVME_IOCTL_ADMIN_CMD: Input/output error
```

### 2.3 业务层面

**无任何可感知影响**。ZFS 镜像的另一块盘正常服务，所有 VM/LXC（immich、caddy、n8n、jenkins 等）运行如常，用户完全无感。这是冗余设计的价值，也正是风险所在——保护网破了却没人知道。

## 三、分析

### 3.1 内核日志时间线

```
Jan 27 12:11:23  nvme nvme0: pci function 0000:02:00.0
Jan 27 12:11:27  nvme nvme0: using unchecked data buffer
                 ↑ 系统启动，设备正常工作

Apr 12 06:23:38  nvme nvme0: I/O tag 588 (524c) opcode 0x1 (I/O Cmd) QID 1 timeout, aborting req_op:WRITE(1) size:40960
Apr 12 06:23:38  nvme nvme0: I/O tag 102 (5066) opcode 0x1 (I/O Cmd) QID 2 timeout, aborting req_op:WRITE(1) size:4096
Apr 12 06:23:38  nvme nvme0: I/O tag 985 (63d9) opcode 0x1 (I/O Cmd) QID 3 timeout, aborting req_op:WRITE(1) size:4096
Apr 12 06:23:40  nvme nvme0: I/O tag 103 (1067) opcode 0x1 (I/O Cmd) QID 2 timeout, aborting req_op:WRITE(1) size:28672
Apr 12 06:23:40  nvme nvme0: I/O tag 465 (71d1) opcode 0x1 (I/O Cmd) QID 4 timeout, aborting req_op:WRITE(1) size:94208
Apr 12 06:24:07  nvme nvme0: I/O tag 956 (23bc) opcode 0x1 (I/O Cmd) QID 6 timeout, aborting req_op:WRITE(1) size:12288
                 ↑ 多个队列的写操作同时超时——控制器已停止响应 I/O

Apr 12 06:24:08  nvme nvme0: I/O tag 588 (524c) opcode 0x1 (I/O Cmd) QID 1 timeout, reset controller
                 ↑ 内核尝试重置控制器

Apr 12 06:25:31  nvme nvme0: Device not ready; aborting reset, CSTS=0x1
Apr 12 06:25:31  nvme nvme0: Abort status: 0x371   (×6)
Apr 12 06:25:51  nvme nvme0: Device not ready; aborting reset, CSTS=0x1
Apr 12 06:25:51  nvme nvme0: Disabling device after reset failure: -19
                 ↑ 重置失败两次，内核放弃并禁用设备（-19 = ENODEV）
```

同期 ZFS 记录了大量 I/O 错误（`error=5` 即 EIO）：

```
Apr 12 06:25:51 pve0 kernel: zio pool=mainpool vdev=/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_2TB_S7HENU0YA65028L-part1 error=5 type=2 offset=1907005353984 size=12288 flags=3145856
（重复数十条）
```

### 3.2 为什么要追究 CSTS=0x1

内核已经尽责地尝试了自愈——发现 I/O 超时后主动发起了控制器重置。但重置失败了，失败时报出的唯一硬信息就是 `CSTS=0x1`。

这个值指向的处置路径差别很大：

- **PCIe 链路/接触问题** → 重插拔或换插槽即可，盘本身没问题
- **控制器自身挂死** → 软件手段全无效，只能断电；需评估是否走 RMA
- **存储介质损坏**（NAND 磨损） → 盘已到寿命，必须更换

`CSTS` 寄存器能告诉我们控制器卡在了握手的哪一步，所以值得展开看。

**但需先声明它的局限**：`CSTS=0x1` 只说明当时 RDY 仍为 1。它无法区分固件 bug、控制器硬件故障、盘上供电、插槽/主板供电瞬变，以及驱动/电源管理交互——这些都会表现为同一个值。下文的推论应在这个前提下阅读。

#### CSTS 寄存器结构

`CSTS` 是 NVMe 规范定义的**控制器状态寄存器**（寄存器偏移 `0x1C`）。关键位：

| 位 | 名称 | 含义 |
|---|---|---|
| bit 0 | RDY (Ready) | 控制器就绪，可接收命令 |
| bit 1 | CFS (Controller Fatal Status) | 控制器发生致命错误 |
| bit 2-3 | SHST | 关机状态 |
| bit 4 | NSSRO | 子系统重置已发生 |

`CSTS=0x1` = **RDY 位为 1，其余为 0**。结合 NVMe 控制器重置的握手协议：

1. 主机将 `CC.EN` **清零**，请求控制器关闭
2. 控制器完成内部清理后，必须将 `CSTS.RDY` **也清零**，以此回应"我已停止"
3. 主机再将 `CC.EN` 置 1，控制器初始化完成后将 `CSTS.RDY` 置 1

本次故障卡在**第 2 步**：内核请求关闭并等待至其 ready timeout，而控制器的 RDY 位**始终维持在 1 不肯清零**。（具体时长分析见 3.3——注意首轮完整 reset 流程并非 20 秒。）

> [!NOTE]
> 类比：一台死机的电脑，屏幕还亮着显示"运行中"（RDY=1），但键鼠全无响应，长按电源键也没反应——只能拔电源。
>
> 对比：若为 `CSTS=0x2`（CFS 置位），则是控制器主动报告致命错误。本例中 RDY 卡死且错误日志为空——这与固件逻辑失控一致，但同样可能出于控制器硬件或供电异常（见上文局限声明）。

### 3.3 排除性诊断：PCIe 热重新枚举

在冷启动之前，先做成本最低的无损尝试——PCIe 层移除并重新扫描。该盘已被内核禁用、其上无任何 I/O，对在线业务无影响。

```bash
# echo 1 > /sys/bus/pci/devices/0000:02:00.0/remove
# echo 1 > /sys/bus/pci/rescan
```

重新枚举时的内核行为：

```
Aug 04 17:59:57 pve0 kernel: nvme nvme0: pci function 0000:02:00.0
Aug 04 18:00:17 pve0 kernel: nvme nvme0: Device not ready; aborting reset, CSTS=0x1
```

两行相差恰好 **20 秒**，与 4 月两次 `Device not ready` 之间的间隔一致（注意：4 月从 `reset controller` 到**首次** `Device not ready` 是 83 秒）。

- PCI 配置空间再次可读、驱动重新 probe 后 NVMe 初始化仍失败 → **降低**了设备节点残留、单次 probe 异常等主机侧解释的可能性（但不构成排除）
- 症状与 4 月一致 → 说明该故障状态在**不断电的前提下持续存在**，而非瞬时抖动

但这一实验**没有**排除插槽供电：`remove`/`rescan` 只重置总线层的枚举关系，**并不切断设备供电**。若问题出在该插槽的供电或链路完整性上，本实验同样会得到相同结果。

> [!CAUTION]
> **一个自始至终未被解耦的混杂变量**：028L 从未离开过 `0000:02:00.0` 这个插槽。两次故障都发生在「这块盘 + 这个插槽」的组合上，而对照盘 040W 始终在 `03:00.0`。因此现有证据无法区分故障属于**设备**还是**插槽/供电路径**。
>
> 这具有现实后果：若根因在插槽侧，保修换回来的新盘插上去会重现同样故障。廉价的验证方法是**将两块盘对调插槽**，观察故障跟着盘走还是留在插槽。

故障范围因此只能收敛到**该设备或其专属 PCIe/供电路径**。下一步选择完整掉电复位——**本次已尝试的在线恢复手段（内核 controller reset、PCIe remove/rescan）均无效**。需说明的是，掉电并非理论上唯一的复位途径：PCIe 功能级复位（FLR）、上游桥的 secondary bus reset 等在线手段本例并未尝试。

### 3.4 健康数据佐证

| 指标 | 040W（幸存，故障期间） | 028L（恢复后） |
|---|---|---|
| SMART 总体 | PASSED | PASSED |
| Critical Warning | 0x00 | 0x00 |
| Percentage Used（磨损） | 1% | **0%** |
| Available Spare | 100% | 100% |
| Media and Data Integrity Errors | 0 | **0** |
| Error Information Log Entries | 0 | **0** |
| Power On Hours | 5,635 | 2,887 |
| 固件版本 | 5B2QJXD7 | 5B2QJXD7 |

推论：

- **通电小时差值 = 2,748 小时 ≈ 114.5 天**，与 4 月 12 日至 8 月 4 日的间隔一致。**但这只是弱旁证**：它成立的前提是两盘在故障前累计通电时长近似相同，而这个前提**没有基线记录可以验证**——若两盘入池前已有不同累计时长，差值就不能等同于离线时间。
- 对照盘未复发，说明故障并非当前环境下可稳定复现于所有 5B2QJXD7 设备，但**不足以排除低概率、状态相关或个体触发的固件缺陷**。另："同批次"仅由序列号相近推断，无生产批次证据；"同工况"也不严格成立（两盘插槽不同、通电时长相差近一倍）。
- SMART 无介质错误也不能排除控制器**硬件**故障——挂死期间甚至根本读不到 SMART。

（本表两列数据采集于不同时点：040W 为 2026-08-04 故障期间，028L 为当日恢复后。至 2026-08-12 040W 已走到 5,768 小时。）

> [!NOTE]
> Samsung 990 PRO 曾有一批广为人知的固件问题，表现为 `Percentage Used` 异常飙升。本例症状完全不同（磨损为 0），不属于该已知问题。

## 四、解决办法

### 4.1 处置顺序

遵循"先保数据、再动硬件"的原则：

```bash
qm set 110 --onboot 0                                        # 降低风险面
zfs snapshot -r mainpool/vmdata@pre-coldboot-20260804        # 建立回滚点（27 个数据集全覆盖）
qm agent <id> ping                                           # 确认可优雅关机
shutdown -h now                                              # 冷启动
```

> [!CAUTION]
> **为什么必须冷启动而非 `reboot`**：软重启和 PCIe remove/rescan 都不会切断设备供电。拔电源等 30 秒是为了让主板残余电容彻底放电。

### 4.2 结果

冷启动后设备完全恢复，**无任何 CSTS 报错**。ZFS 自动完成 resilver：

```
  scan: resilvered 55.0G in 00:01:19 with 0 errors on Tue Aug  4 18:13:45 2026
	    nvme-Samsung_SSD_990_PRO_2TB_S7HENU0YA65028L  ONLINE       0     0     4
	    nvme-Samsung_SSD_990_PRO_2TB_S7HENU0YA65040W  ONLINE       0     0     0
errors: No known data errors
```

### 4.3 遗留的 4 个 CKSUM 错误

恢复的盘上出现 4 个校验和错误——ZFS 从该盘读到了与校验和不符的数据，但因镜像存在已自动修复。推测为 4 月故障瞬间写入中断遗留的陈旧数据。

**判读标准**：scrub 后 CKSUM 仍为 0 → 历史遗留，盘可继续使用；**再次出现新错误 → 盘不稳定，应更换**。

### 4.4 scrub 验证结果

全池校验于 19:01:30 启动（`zpool history` 显示 19:01:29 是 `zpool clear`，scrub 在下一秒），**用时 8 分 49 秒**：

```
  scan: scrub repaired 0B in 00:08:49 with 0 errors on Tue Aug  4 19:10:18 2026
	READ / WRITE / CKSUM 均为 0
errors: No known data errors
```

> [!IMPORTANT]
> 全量读取校验 653G 数据，**零修复、零错误**。这与"4.3 中那 4 个 CKSUM 为写入中断遗留"的推测一致，但并不构成证实——clean scrub 只能说明当时不存在持续可检测的校验错误。
>
> 整个故障周期中始终保持 `errors: No known data errors`，全池 scrub 也未发现错误——**未观察到持久数据损坏**。（这不覆盖应用层未落盘的写入或 guest 文件系统一致性。）
>
> **本小节的检测结果至今仍然成立**——2026-08-04 当时确实检测不到持续的校验错误。被 8-11 复发推翻的不是这个检测结果，而是由它得出的**"磁盘可继续服役"这一处置决策**。见 6.2。

## 五、后续改善

### 5.1 待办事项

- [x] **scrub 结果判读** — 已完成，8分49秒全池校验，零修复零错误，与"4 个 CKSUM 为历史遗留"的推测一致（该点时结论已被 8-11 复发废止）
- [x] **恢复 PBS 备份** — 已完成。PBS 于 2026-08-06 通过 V2V 从 ESXi 迁至 pve1（VM 113，IP 保持 192.168.1.249），datastore 落在 zvol 上，verify 零错误。2026-08-12 全量备份 10/10 成功。原文所说「最薄弱的一环」已闭环
- [x] **固件更新至 8B2QJXD7** — 已于 2026-08-12 完成，**仅 028L**；对照盘 040W 保持 5B2QJXD7 以维持对照价值。两盘固件不一致为有意为之。见 6.3 与 6.7
- [x] **修复 PVE / zed 事件通知的投递通道** — 已完成。2026-08-12 改用 PVE 原生通知 endpoint，绕过已证实不可靠的 postfix 直投路径：

  ```bash
  pvesh create /cluster/notifications/endpoints/smtp    --name gmail  --server smtp.gmail.com --port 587 --mode starttls ...
  pvesh create /cluster/notifications/endpoints/webhook --name bark   --method post --url https://api.day.app/<key> ...
  pvesh set    /cluster/notifications/matchers/default-matcher --target gmail --target bark
  ```

  Bark 走 HTTPS，不受 25 端口封锁影响；原 `mail-to-root` 已从路由中摘除。**覆盖范围与未验证项见 6.8。**

  配置过程中另发现 pve0 当时**完全没有 DNS**（`/etc/resolv.conf` 仅剩 `search` 行），根因是 Tailscale 关闭 DNS 接管时恢复"接管前备份"，而该备份早已丢失。已以 `pvesh set /nodes/pve0/dns --dns1 192.168.1.1` 修复，并在 Ansible 的 tailscale role 中加固（commit `ab14e7c`）。

- [x] **修复 PBS 的 prune 权限** — 新增项，已完成并验证。2026-08-12 的定时任务报 `missing Datastore.Modify|Datastore.Prune`：用户 `backup@pbs` 仅有 `DatastoreBackup`，而 PBS 中 token 的有效权限是「token ACL ∩ 所属用户 ACL」，因此 token 上的 `DatastoreAdmin` 被封顶。**备份本体全部成功，仅保留策略未执行。**

  ```bash
  proxmox-backup-manager acl update /datastore/backup-storage DatastorePowerUser --auth-id backup@pbs
  pvesm prune-backups pbs-backup --keep-daily 7 --keep-weekly 4 --keep-monthly 6   # rc=0，10 个组全部执行完毕
  ```

  实跑后日内重复快照已被清除，保留策略生效。**在现有记录中，能直接证明某次 prune 执行失败的只有那条权限报错**；它证明的是对应那一次执行失败，不能概括所有历史执行。

- [ ] **建立周期性健康轮询** — 新增项，**未执行，且这是本次事故最核心的整改项**。投递通道修好只解决了"消息发不出去"，没有解决"边沿触发导致一封漏接即无限静默"。需覆盖：pool health 现状、scrub freshness、backup freshness。**在此项完成之前，不应认为监控已闭环**——详见 6.8
- [ ] **验证盘/插槽解耦** — 新增项，未执行。见 3.3 的橙色提示

### 5.2 固件更新方案

升级前版本 `5B2QJXD7`，目标版本 `8B2QJXD7`（2025 年 12 月发布，官方说明为"改善读取操作稳定性"）。**028L 已于 2026-08-12 升级至 8B2QJXD7，040W 仍为 5B2QJXD7**。

> [!NOTE]
> **版本谱系（2026-08-12 核实）**：990 PRO 的版本序列为 3B → 4B → 5B → 6B → 7B → 8B，其中 **7B 是一个正常发布且广泛存在的版本**。
>
> 据 smarthdd 实盘上报数据库（样本约 61 块），在野分布为：4B（49.2%）、7B（13.1%）、8B（13.1%）、5B（9.8%）、3B（8.2%）、0B2QJXG7（4.9%）、6B（1.6%）。**6B 仅对应 1 块盘**——这只能证明 6B 确实存在于实盘，**不足以证明它曾被正式发布后撤回**；低占比与"撤回"传闻相容，但仅是相容性旁证，样本量不支持更强结论。

**Linux 下没有 Samsung Magician 的官方等价物**——三星已停止为消费级 SSD 提供 Linux 工具。官方提供的可引导 ISO 在多数现代服务器上无法使用。

**可行方案：从 ISO 中提取 flash 工具，在现有 Linux 下直接运行。**

```bash
aria2c -x8 -s8 -k1M -c -o Samsung_SSD_990_PRO_8B2QJXD7.iso \
  "https://download.semiconductor.samsung.com/resources/software-resources/Samsung_SSD_990_PRO_8B2QJXD7.iso"

mount -o loop,ro /var/lib/vz/template/iso/Samsung_SSD_990_PRO_8B2QJXD7.iso /mnt/samsungiso
cd /root/fwupdate && gzip -dc /mnt/samsungiso/initrd | cpio -id --no-absolute-filenames
umount /mnt/samsungiso

# 提取结果：
#   /root/fwupdate/root/fumagician/fumagician       (2.9MB, 可执行)
#   /root/fwupdate/root/fumagician/8B2QJXD7.enc     (20MB, 加密固件)
#   /root/fwupdate/root/fumagician/fumagician.sh    ← 勿执行，见 6.7

cd /root/fwupdate/root/fumagician/ && ./fumagician
```

**上述步骤已于 2026-08-12 执行完毕。实际过程与预想有出入（缺 `unzip`、需额外一次控制器重新初始化、以及一个会刷错盘的交互陷阱）——以 6.7 为准。**

### 5.3 监控（本次事件的核心改进项）

**放大本次事故严重度的关键问题不是单盘故障本身，而是降级状态持续 114 天无人察觉。** 需要建立的监控应覆盖：

| 监控项 | 检测目标 | 说明 |
|---|---|---|
| ZFS pool 状态 | DEGRADED / FAULTED / 只读 | 本次故障的直接信号，最高优先级 |
| ZFS 错误计数 | READ / WRITE / CKSUM 非零 | 盘劣化的早期征兆 |
| scrub 执行与结果 | 是否按期执行、是否有修复 | Debian zfsutils cron：第一个周日 trim、第二个周日 scrub |
| SMART 健康度 | Percentage Used、Available Spare、介质错误 | 预测性指标 |
| NVMe 内核错误 | I/O timeout、controller reset、CSTS | 本次故障的最早信号（比 ZFS 降级早约 2 分钟） |
| 备份任务状态 | 最后成功时间、连续失败次数 | PBS 停机本应被立即发现 |
| 磁盘容量水位 | pool 使用率阈值 | 常规运维项 |

> [!TIP]
> **告警设计原则**：告警必须送达到用户实际会看到的地方。PVE 自带 zed，但若邮件未配置或无人查看，等同于无告警。

---

## 六、复发（2026-08-11）

2026-08-11 03:00，**同一块盘以相同的核心故障签名再次挂死**。本节记录复发经过，并修订本报告在四月做出的若干判断。

（"相同签名"指故障演进的阶段序列与错误码一致，**并非逐字相同**——两次的 Abort 计数为 6 与 8，tag、QID、请求尺寸也各不相同。）

### 6.1 两次故障的签名对照

| 阶段 | 2026-04-12 | 2026-08-11 |
|---|---|---|
| 首个 WRITE 超时 | 06:23:38 | 03:00:36 |
| 内核发起控制器重置 | 06:24:08 | 03:01:06 |
| 重置失败 CSTS=0x1 | 06:25:31 | 03:02:28 |
| 内核弃盘 -19 | 06:25:51 | 03:02:48 |
| Abort status 0x371 | ×6 | ×8 |

全部 15 个 boot 的内核日志里，`Disabling device after reset failure` **只出现过这两次**，且都是 `S7HENU0YA65028L`。对照盘 `S7HENU0YA65040W` 至今零错误。

若按 Linux 默认的 30 秒 `nvme_core.io_timeout` 推算，真正卡住的写请求下发于约 `03:00:06`（本机实际 `io_timeout` 参数未存档，此推算存在不确定性）。已核对的宿主机计划任务在该时刻均无活动：`cron.hourly` 在每小时 :17，`pve-daily-update` 于 02:56:35 结束，02:00 的备份任务在 02:01:02 就因存储不可达退出、未产生 I/O。`autotrim` 为 `off`。两次首先记录到超时的请求均为 **4–112 KiB** 的小块 WRITE。

**可以说的**：两次首先记录到的超时都是小块写；在已核对的宿主机计划任务中未发现同刻任务。

**不能说的**：本报告初稿曾写"不是负载尖峰触发的……无法通过降低负载规避"，**这超出了证据**。日志只显示首先超时的可见命令是 WRITE，不能证明故障源在写路径；请求尺寸小不等于总负载低；且缺少 guest 侧与块层的同期遥测（IOPS、带宽、队列深度、iowait、ARC/TXG），无法判断负载尖峰是否参与触发。"宿主机无计划任务"也不能排除 VM/LXC 内部的负载。

### 6.2 判据已触发

判据实际由两项共同触发：**其一，复发后恢复的盘上再次出现新的 CKSUM 计数（1 个）**——这正是 4.3 字面写下的条件；**其二，四个月内第二次控制器挂死，核心签名相同，内核 controller reset 与 PCIe remove/rescan 均无效，而同固件的对照盘至今零错误**。

**判据成立，决定走保修更换。**

需注意的是，"更换该设备"是在现有证据下的合理处置，但**并未证实根因在设备内部**——盘与插槽从未解耦（见 3.3）。若新盘到位后故障重现，应优先怀疑插槽/供电路径。

### 6.3 修订：固件更新与本故障的关系

本节初稿的论断是："8B2QJXD7 的说明是改善**读取**稳定性，而本故障是**写**路径超时，故不对症。"**这个推理不完整，现修订。**

**其一，8B 是 7B 的后继版本，而 7B 针对的正是"间歇性不识别 / 蓝屏"一类问题。** 本盘停在 5B，从未获得 7B 的修复。完整固件的后继版本**通常预期继承前版修复**——但需要说明的是，**Samsung 的公告并未明确保证这一点**，因此这是合理的工程推断，不是已证事实。

**其二，第三方报告过一种表型相近的失效。** 数据恢复服务商描述部分 990 PRO 会进入"固件 panic 状态、停止响应 NVMe 初始化命令"直至无法枚举——与本例的 `CSTS.RDY` 卡死、复位失败、`Disabling device` 表型相近。

**但这条只能承担背景说明的分量**：该描述的典型链路是"早期固件 → SMART 劣化 → 初始化失败"，而本盘磨损 0%、零介质错误，路径不符；且它并非 Samsung 对本故障签名的确认。**只能说存在相似表型，不能确认同源，更不能用它支持"8B 会解决本例"。**

**修订后的结论**：**不能再仅凭 8B 的"读取稳定性"说明判定其与本故障无关**——相关性存在，但**升级效果未知**。目标盘已在复发后升级，尚无足够的升级后观察期，**不能替代 RMA**。

#### 关于"免复位激活"的准确表述

同型号控制器报告 `Firmware Updates (0x16)`，bit 4 置位。其含义是：**控制器具备接受"立即激活"请求（Firmware Commit、Commit Action `011b`）的能力**——而非对任意固件镜像、任意厂商工具执行路径都无需复位的无条件保证。NVMe 规范明确允许设备对特定镜像返回"需要 Controller Level / NVM Subsystem / Conventional Reset"的状态。

本次实测：`fumagician` 输出 `Firmware Update Completed` 后，主机仍观察到旧版本；直至 PCIe remove/rescan 触发控制器重新初始化后才显示 `8B2QJXD7`。**因此应记为"需要一次控制器重新初始化后新版本才可观察/生效"**。仅凭现有日志无法判断是工具未使用立即激活动作、设备要求了复位，还是 Identify 信息在旧控制器实例中未刷新。

（另：本报告证据包中的 `0x16` 读数来自 **040W** 的 SMART 存档；028L 的存档采集于挂死态，只有 I/O error。对 028L 的该位读取发生在一条未存档的实时命令中。）

### 6.4 四月未记录的两个机制

**其一：池降级会让 scrub 自我关闭。** Debian 的 `/usr/lib/zfs-linux/scrub` 在枚举池时即按 ONLINE 过滤（脚本第 30 行）：

```sh
zpool list -H -o health,name | awk -F'\t' '$1 == "ONLINE" {print $2}'
```

非 ONLINE 的池被直接跳过。因此 2026 年 5-10、6-14、7-12 三次月度 scrub **全部静默未执行**；池于 8-04 恢复 ONLINE 后，8-09 的 scrub 立即自动运行。一跳一恢复互为印证。

**数据完整性校验在最需要它的时候自行停止，且这一停止本身也不告警。**

**其二：告警从未送达的真实机制。** 并非仅仅「邮件无人查看」：

```
/root/.forward        →  |/usr/libexec/proxmox-mail-forward  （转发至 Gmail）
/etc/postfix/main.cf  →  relayhost =                        （空，直投 MX）
日志                   →  connect to gmail-smtp-in.l.google.com[...]:25: Connection timed out
mailq                 →  16 封、94 KB 滞留
```

住宅宽带封锁 25 端口出站，邮件全部堆积在发件队列。四月的日志中有一封 `delay=359741`，即已滞留 4.1 天。`zed` 服务本身是 active 的，事件也确实产生了——但它是**边沿触发**：池状态不再变化后便不再有任何事件。**一封丢失的消息等于 114 天静默。**

### 6.5 恢复过程

处置顺序沿用 4.1，但因备份链路已修复而多了第一步：

1. **补齐备份** — 10 个 guest 全量备份至已迁移到 pve1 的 PBS，`Backup job finished successfully`
2. **建回滚点** — `zfs snapshot -r mainpool/vmdata@pre-coldboot-20260811`，27 个数据集全覆盖
3. **确认可优雅关机** — VM 101/102/104/110 的 guest agent 均响应
4. **冷启动** — `shutdown -h now` → 物理断电 30 秒 → 上电

结果：

```
resilvered 10.7G in 00:00:15 with 0 errors on Wed Aug 12 09:38:46 2026
state: ONLINE
  nvme-Samsung_SSD_990_PRO_2TB_S7HENU0YA65028L  ONLINE  0  0  1
  nvme-Samsung_SSD_990_PRO_2TB_S7HENU0YA65040W  ONLINE  0  0  0
```

与四月同形：恢复盘上残留 1 个 CKSUM（四月为 4 个）。执行 `zpool clear` + 全池 scrub 验证：

```
scrub repaired 0B in 00:10:59 with 0 errors on Wed Aug 12 09:50:47 2026
READ / WRITE / CKSUM 均为 0
errors: No known data errors
```

**未观察到持久数据损坏，10 个 guest 全部自动恢复运行。**

### 6.6 附带发现：设备名换位

冷启动后内核枚举顺序改变：

```
之前:  nvme0 = 02:00.0 = 028L      nvme1 = 03:00.0 = 040W
之后:  nvme1 = 02:00.0 = 028L      nvme0 = 03:00.0 = 040W
```

PCI 地址未变，仅 `nvme` 编号漂移。**池以 `/dev/disk/by-id/` 锚定，未受影响**；但任何写死 `/dev/nvme0n1` 的脚本或文档此刻已指向另一块盘。

### 6.7 固件升级实施记录（2026-08-12）

实际顺序（与 5.2 预想不同，以本节为准）：

1. 预检：池 ONLINE、当日 scrub 零错误、当日备份 10/10
2. `zpool offline` 目标盘（池转 DEGRADED，单副本窗口开始）
3. 首次刷写**失败**：`sh: 1: unzip: not found` — fumagician 需调 `unzip -o` 解开固件包。**失败发生在解包阶段，未写入任何内容**
4. 安装 unzip 后重跑，输出 `Firmware Update Completed`
5. 此时 `smartctl` **仍报旧版本**；PCIe remove/rescan 触发控制器重新初始化后显示 `8B2QJXD7`，无 CSTS 报错
6. `zpool online` → `resilvered 32.0M in 00:00:00 with 0 errors`，池回到 ONLINE

> [!CAUTION]
> **两个必须避开的坑**
>
> **其一：绝不要执行 `fumagician.sh`。** 它是给 ISO 引导环境写的启动脚本，结尾是 `read -t 10` 后 `/sbin/reboot -f` — 十秒无输入就强制重启宿主机；且它写死的路径 `/root/fumagician/` 与实际解压位置不符。只能跑二进制 `./fumagician`。
>
> **其二：工具会枚举全部三星 SSD 并逐设备询问，而健康的对照盘排在第一个被问。** 且两个提示语义不同：`Do you want to continue the firmware update?` 是刷当前这块，`...on next device?` 是前进到下一块。本例正确应答序列为：**Drive 1 (040W) → N；next device → Y；Drive 2 (028L) → Y**。一个反射性的 Y 会刷掉镜像里健康的那一半。**必须按序列号确认，不能按 nvme 编号**（参见 6.6）。

正式刷写前先做了一次**空跑**（对所有提示答 N，零写入）来探清枚举顺序与提示序列。建议任何人在多盘环境下重复此操作时照做。

另：`fumagician` 输出 `Firmware Update Completed` 的同时，包装层可能返回非零退出码（本例 `exit=255`，来自 `ssh -tt` 拆链）。**不能凭退出码判定成败，最终固件版本才是确认依据。**

### 6.8 监控：已验证与未验证

告警链路已重建（见 5.1），但**不应将"通道测试成功"等同于"监控闭环"**。当前状态：

| 环节 | 状态 |
|---|---|
| 投递通道（root 邮件 → proxmox-mail-forward → gmail/bark） | ✅ 已验证 |
| zed → 投递通道 | ✅ 已由真实事件验证（resilver 完成告警送达） |
| 设备 REMOVED / FAULTED 的端到端告警 | ⚠️ **未验证**（已读代码确认过滤器含 REMOVED，且与 resilver 共用同一 `zed_notify` 出口） |
| 持续性 pool health 轮询兜底 | ❌ 未建立 |

实测发现：**`zpool offline` 不会触发告警**。`statechange-notify.sh` 仅对 `FAULTED / DEGRADED / REMOVED / UNAVAIL` 发通知，`OFFLINE` 不在名单里——这是**预期行为**（管理员主动操作无需告警），但也意味着该测试**没有覆盖真实故障路径**。8-11 真实掉盘时的事件为 `resource.fs.zfs.removed`，状态 REMOVED，在名单内。

仍未覆盖的三个缺口（均需周期性状态检查，而非事件驱动）：

1. **已处于降级状态的池不会重复告警** — zed 是边沿触发，一封漏接即无限静默。这正是 114 天的结构性成因，**尚未消除**
2. **scrub 未按期执行不会告警** — `scrub_finish-notify.sh` 只在 scrub **完成**时触发；池降级导致 cron 静默跳过时根本不存在"完成"（见 6.4）
3. **备份"未运行"不会告警**（"运行失败"会）

---

## 附录 A：修订说明

本报告经过两轮独立审核（2026-08-12），以下判断被修正。列出的目的不是留存改动痕迹，而是因为**这些错误本身构成教训**——它们都属于"证据支持 A，却写成了更强的 B"。

| 位置 | 初稿写法 | 问题 | 现表述 |
|---|---|---|---|
| 摘要 / 3.3 | "根因指向固件层死锁"、"锁死在盘上的控制器/固件层" | `CSTS=0x1` 无法区分固件、控制器硬件、供电；且盘与插槽从未解耦 | 收敛到"该设备或其专属 PCIe/供电路径" |
| 3.3 | "排除插槽接触、PCIe 链路" | remove/rescan 不切断供电，排不掉供电问题 | 明确声明未排除，并新增插槽对调的验证建议 |
| 3.4 | "排除批次性固件缺陷"、通电小时差"精确吻合" | 单块对照盘不能排除低概率缺陷；通电小时差缺少入池基线 | 降为"不足以排除"、"弱旁证" |
| 6.1 | "不是负载尖峰触发的，无法通过降低负载规避" | 缺少 guest 侧与块层遥测 | 改为"无法判断负载是否参与触发" |
| 6.3 | "8B 说明是改善读取，故不对症" | 只看单版本说明，未看 5B→8B 的累积增量（含 7B 的不识别修复） | 改为"不能判定不相关，但效果未知" |
| 5.2 | "6B 被撤回，应直接跳至 8B" | 漏掉 7B；且 6B 的"撤回"仅有 1 块盘的占比作为相容性旁证 | 补齐 7B，并标注样本量限制 |
| 5.1 | "建立监控告警 ✅" | 只修好了投递通道，周期性轮询未建 | 拆为"投递通道已修复 ✅"+"周期性轮询 ❌" |
| 5.1 | "1 月快照还在 = prune 从未生效" | `keep-monthly=6` 计的是"有备份的月份"，当前只有 2 个月，1 月本就该留 | 删除该推理，只保留权限报错这一直接证据 |
| 2.2 / 附录 | 标为 `nvme list` | 实为 `lsblk` 输出；pve0 未装 nvme-cli | 全部更正 |
| 4.4 | scrub"于 19:01:29 启动" | 那一秒是 `zpool clear`，scrub 在 19:01:30 | 更正 |
| 3.2 / 3.3 | "等待约 20 秒" | 20 秒是两次 `Device not ready` 之间及 rescan 探测的间隔；首轮 reset 到首个报错实为 83 秒 | 分开表述 |
| 5.3 | "PVE 默认每月第一个周日 scrub" | 实为第一个周日 trim、第二个周日 scrub | 更正 |
| 全文 | "全程零数据丢失" | ZFS 未报错 ≠ 应用层无损 | 改为"未观察到持久数据损坏" |

**共性教训**：本报告初稿的大部分错误不是观测错误，而是**从正确的观测跳到了过强的结论**——尤其在排除性推理上（"实验 X 未复现 Y，故排除 Y"）。排除性结论需要实验真正覆盖了被排除的机制，而 remove/rescan 不切断供电这一条，恰恰是四个月里没人注意到的漏洞。

## 附录 B：完整命令速查

```bash
# —— 诊断 ——
zpool status -v mainpool                    # pool 详细状态（含错误计数与 scan 记录）
pvesm status                                # PVE 存储层状态
lsblk -d -o NAME,SIZE,MODEL,SERIAL          # NVMe 设备与容量（0B 是重要信号）
                                            # 注：pve0 未装 nvme-cli，`nvme` 命令不可用
for d in /sys/class/nvme/nvme*; do          # 序列号 → PCI 地址 严格映射
  echo "$(basename $d) $(cat $d/serial) $(basename $(readlink -f $d/device))"; done
smartctl -a /dev/nvmeXn1                    # SMART 全量数据（X 先用上行核对）
journalctl -k --no-pager | grep -iE "nvme nvme[01]"  # 内核 NVMe 日志
journalctl -k --no-pager | grep "zio pool"           # ZFS I/O 错误
lspci | grep -i "non-volatile"              # PCIe 层设备枚举

# —— 无损恢复尝试（不切断供电，见 3.3）——
echo 1 > /sys/bus/pci/devices/0000:02:00.0/remove
echo 1 > /sys/bus/pci/rescan

# —— 数据保护 ——
zfs snapshot -r mainpool/vmdata@pre-coldboot-<date>
qm agent <vmid> ping

# —— 恢复后验证 ——
zpool clear mainpool
zpool scrub mainpool
zpool status mainpool | grep -A3 "scan:"

# —— 固件升级（详见 6.7，勿跑 fumagician.sh）——
zpool offline mainpool <by-id 名>
cd /root/fwupdate/root/fumagician/ && ./fumagician   # 逐设备确认，按序列号
echo 1 > /sys/bus/pci/devices/<addr>/remove && echo 1 > /sys/bus/pci/rescan
zpool online mainpool <by-id 名>

# —— PBS 保留策略 ——
pvesm prune-backups pbs-backup --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --dry-run
proxmox-backup-manager acl list             # 注：token 权限 = token ACL ∩ 用户 ACL

# —— 通知链路 ——
echo test | mail -s "path test" root        # 验证 root 邮件 → proxmox-mail-forward → gmail/bark
pvesh create /cluster/notifications/targets/<name>/test
```
