# 事故报告：pve0 SA510 SATA 链路异常导致 rpool I/O 错误

> **事故编号**：INC-2026-10-02-RPOOL
> **发现日期**：2026-10-02
> **关闭日期**：2026-10-14
> **状态**：已缓解，观察期未复发，按用户要求提前结束临时监控
> **主机**：pve0，Intel Cannon Lake PCH SATA AHCI，内核 `6.14.8-2-pve`
> **时间**：10 月 2 日使用 AEST（UTC+10）；10 月 4 日起使用 AEDT（UTC+11）。本文明确标注关键时间。

## 结论

本次错误发生在 WD Blue SA510 系统盘的 SATA 通道。内核先记录链路状态变化与 ATA bus error，随后写入失败、ZFS 报错，再通过重置链路恢复。关闭 SATA 链路省电后，截至 2026-10-14 01:16 AEDT，没有发现新增 SATA、rpool I/O 或 NVMe 超时错误；两个池均 ONLINE，例行 scrub 也未发现错误。

这些结果支持 SATA 省电唤醒兼容性作为主要排查方向。未做 SSD、连接件或供电路径的交叉替换，仍不能唯一确定具体硬件或固件缺陷。保留关闭省电的配置，结束本次临时观察。

## 存储边界与症状

| 项目 | 实际配置 | 本次问题 |
|---|---|---|
| `rpool` | 单块 WD Blue SA510 M.2 2280 1000GB；serial `2444BR400267`；系统盘 `/dev/sda3` | 2026-10-02 检查时 WRITE=15，READ/CKSUM=0 |
| `mainpool` / VM 数据 | 双 Samsung 990 PRO 2TB 镜像；serial `S7HENU0YA65028L`、`S7HENU0YA65040W` | 本次检查均 ONLINE，错误计数为0 |

`rpool` 没有镜像冗余。监控期间未观察到 ZFS 已知永久数据错误；本次核查没有覆盖全部 VM 应用层的数据完整性。

此前 [990 PRO 控制器故障报告](./2026-04-12-pve0-nvme-controller-hang.md) 属于另一事故，不应混用其故障盘、池名与处置结论。

## 诊断证据

2026-09-24 至 27 日的典型错误顺序：

```text
ata1.00: exception Emask 0x10 ...
ata1.00: irq_stat 0x00000040, connection status changed
ata1: SError: { PHYRdyChg CommWake DevExch }
ata1.00: failed command: WRITE FPDMA QUEUED
ata1: hard resetting link
I/O error, dev sda ... (WRITE)
zio pool=rpool vdev=...2444BR400267-part3 error=5 type=2 ...
```

10 月 2 日对保留内核日志的统计发现，这不是仅持续几天的问题：

- 最早可见记录为 **2025-11-28 23:49 AEDT**。
- 同一 SA510 的通道累计 **576 次 ATA 链路异常**，对应 **1,098 条 rpool I/O 错误记录**，其中写入1,087条、读取11条。
- 9 月 21 日启动后的8次链路异常对应15条写入错误，与当时 `zpool status` 的 WRITE=15一致。
- 最后一次旧错误为 **2026-09-27 06:05:46 AEST**。

以上是2026-10-02当次日志读取的统计，不是磁盘固件的终身错误计数。错误在池重新导入或重启后可能重置，因此判断复发时同时检查跨启动日志。

SA510 当时 SMART 为 PASSED，重映射、不可纠正、命令超时及 CRC 属性均为0，但没有自检记录；SMART 通过不能否定内核已观察到的链路错误。固件版本为 `52046100`，已经包含厂商公告的关键修复版本，不能简单归因于未安装那次固件更新。

当时 SATA host 的策略为 `med_power_with_dipm`，盘报告 DIPM 已启用。控制器与磁盘的 `power/control=on` 禁用了运行时自动挂起，仍不等同于关闭 SATA 链路省电。

日志中的 `Unaligned write command` 也不能单独证明分区对齐错误：libata 可将 DRDY 状态映射为该提示；采样请求按4K对齐，`rpool` 的 `ashift=12`。本次没有因此重建池或调整分区。

## 处置与时间线

| 时间 | 动作与结果 |
|---|---|
| 2026-10-02 10:18:56 AEST | 将 SA510 实际所在 SATA host 切为 `max_performance`，确认 DIPM 已禁用；WRITE=15保留作基线 |
| 2026-10-02 | 备份 `/etc/kernel/cmdline`，追加 `ahci.mobile_lpm_policy=1`，执行 `proxmox-boot-tool refresh`；只读检查实际 ESP 的启动 options 已包含参数 |
| 2026-10-02 | 在 pve1 部署临时监督任务，经既有集群 SSH 读取 pve0；复用 PVE 原生 Bark/Gmail 通道，真实投递日志确认两目标成功 |
| 2026-10-02 | 按用户要求简化为 Shell，并改为每小时一次；删除旧 Python 监控和 Mac 定时任务 |
| 2026-10-02 16:31:48 AEST | pve0 重启，随后确认当前内核实际携带关闭省电参数 |
| 2026-10-09 | 设置10月16日12:00 AEDT的条件收尾；观察期出现异常或文件归属无法核实时保留监控 |
| 2026-10-10 15:56:33 AEDT | pve0 再次启动；10月14日核查当前内核参数与运行策略仍正确 |
| 2026-10-11 00:24:56 AEDT | rpool 例行 scrub 完成，处理/修复字节为0、错误为0 |
| 2026-10-11 00:35:04 AEDT | mainpool 例行 scrub 完成，处理/修复字节为0、错误为0 |
| 2026-10-14 01:16 AEDT | 最终核查：累计279次 Shell 监控成功采集，异常和失败均为0；整个变更后日志范围没有新增相关错误 |
| 2026-10-14 01:21:26 AEDT | 用户要求不等到16日；停用并移除临时监控及到期收尾逻辑，确认两个 unit 为 not-found/inactive、timer列表为空 |

279次包括手动验证，不全部是定时触发。本次没有人为制造磁盘故障；10月11日 scrub 为系统例行任务，结束核查只读取其结果。

## 最终状态与清理范围

截至2026-10-14 01:16 AEDT：

- SA510 serial和固件保持不变，SMART PASSED；属性5、184、187、188、199均为0，温度48°C。
- SATA策略为 `max_performance`，实际 `/proc/cmdline` 与持久配置都包含 `ahci.mobile_lpm_policy=1`。
- rpool、mainpool及所有vdev均ONLINE，READ/WRITE/CKSUM与已知数据错误均为0。
- 监控当前故障、待报告内容及观察期异常标记均为空；部署文件哈希与任务归属清单一致。

当前错误计数0包含重启后的重置因素；关闭依据还包括整个观察期的日志和监控结果，以及后续 scrub 结果。

已移除 pve1 的 `/usr/local/sbin/pve0-storage-watch.sh`、`pve0-storage-watch.service`、`pve0-storage-watch.timer` 及 `/var/lib/pve0-storage-watch/`。此前旧 Python 采集器和 Mac 自动化已移除。工作树内本次临时脚本、unit、规划记录已清理，只保留本事故文档。

保留 pve0 上的 SATA省电关闭参数、原配置备份 `/etc/kernel/cmdline.pve0-sata-lpm.bak`，以及系统原有 SMART、ZED 与例行 scrub 机制。没有回退本次缓解配置，也没有执行 `zpool clear`、更换磁盘或升级固件。

## 再次出现错误时

先保存 `zpool status -vP`、SA510 的 `smartctl -x` 和对应时间段的跨启动内核日志。核实省电策略和实际内核参数；若关闭省电仍复发，再检查实际存在的连接件与供电路径，并用已知正常的设备/路径交叉验证。仅清除计数无法解决原因。

## 证据与参考

本报告来自2026-10-02诊断记录与2026-10-14通过SSH读取的主机现场数据。关键读取入口：

```bash
zpool status -pP rpool mainpool
smartctl -a /dev/disk/by-id/ata-WD_Blue_SA510_M.2_2280_1000GB_2444BR400267
cat /proc/cmdline
journalctl _TRANSPORT=kernel --since='2026-10-02 00:18:56 UTC'
journalctl -u pve0-storage-watch.service --since='2026-10-02 01:55:00 UTC'
```

- [SanDisk：SA510关键固件更新说明](https://support-en.sandisk.com/app/answers/detailweb/a_id/50208/~/wd-blue-sa510-sata-ssd-critical-firmware-update)
- [Linux v6.14：libata SCSI错误映射](https://github.com/torvalds/linux/blob/v6.14/drivers/ata/libata-scsi.c#L804-L809)
- [Linux v6.14：SATA链路省电策略](https://github.com/torvalds/linux/blob/v6.14/drivers/ata/libata-sata.c#L843-L850)
