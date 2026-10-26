# VM116 Windows 只读调查记录

日期：2026-10-26，Australia/Sydney。调查现场约01:09–01:40 AEDT。用户明确表示VM116本应安装Windows；这一预期与当前磁盘证据冲突，不能把空盘认定为正确基线或通过迁移验收。

本次仅读取配置、设备映射、历史日志、存储元数据及PBS固定索引。未启动、迁移、恢复、安装、格式化、修复、挂载或修改VM116；未导入旧pool、扫描裸盘、导出100GiB磁盘、清理卷或安装工具。原VMDK/更早离线备份的位置正在等待用户回复。

## 当前配置与底层映射

源pve1（192.168.1.51）VM116为stopped、4核、16GiB、host CPU、OVMF、pc-q35-10.0。`qm pending 116`仅有current字段，`qm listsnapshot 116`仅有current，无现存快照或unused盘。启动顺序为`sata1;sata0`，Windows安装ISO优先。

| 接口 | 当前来源 | 参数/字节 |
|---|---|---|
| sata0 | local-lvm:vm-116-disk-1 | 100GiB，107374182400B |
| efidisk0 | local-lvm:vm-116-disk-0 | 4MiB；efitype=4m；pre-enrolled-keys=0 |
| tpmstate0 | local-lvm:vm-116-disk-2 | 4MiB；version=v2.0 |
| sata1 | local:iso/win11_iot_ltsc_2024.iso | 5144817664B |
| sata2 | local:iso/virtio-win.iso | 789645312B |
| net0 | vmxnet3、vmbr1 | MAC BC:24:11:92:81:B0 |

两ISO在pve0/pve1名称及字节数相同；未执行内容hash，不能据此声明内容相同。集群ID116只注册于pve1，pve0没有目标注册。

`pvesm path`返回OS盘`/dev/pve/vm-116-disk-1`，对应DM252:26。`dmsetup table`为`0 209715200 thin 252:8 12`，与LVM thin_id=12一致。LV UUID为`fZteHU-x0Ac-ceD2-pWdx-tbSM-Sgpy-e5FBfM`，创建时间2026-10-12 10:41:33+11。

`dmsetup status /dev/pve/vm-116-disk-1`返回`0 209715200 thin 0 -`：映射扇区为0，未读错设备层，亦非仅LVM百分比舍入。`blkid -p`未识别分区/文件系统。EFI映射1152个512B扇区（589824B），TPM映射128个512B扇区（65536B）。此证据说明当前活动OS薄盘无映射数据；没有启动guest验证或修复。

## 六份PBS备份主盘全零

通过PVE的既有PBS存储配置读取恢复点列表、最早及最新备份配置和文件元数据；随后通过现有严格hostkey SSH读取PBS（192.168.1.249）已挂载datastore内的固定索引。认证沿用现有通道，未打印凭据。

| 恢复点（UTC） | OS逻辑长度 | 固定索引字节 | 唯一chunk digest数 | 是否为4MiB全零摘要 |
|---|---:|---:|---:|---|
| 2026-10-11T23:42:05Z | 107374182400 | 823296 | 1 | 是 |
| 2026-10-14T13:19:56Z | 107374182400 | 823296 | 1 | 是 |
| 2026-10-18T02:41:15Z | 107374182400 | 823296 | 1 | 是 |
| 2026-10-21T13:17:27Z | 107374182400 | 823296 | 1 | 是 |
| 2026-10-22T01:56:47Z | 107374182400 | 823296 | 1 | 是 |
| 2026-10-24T13:17:08Z | 107374182400 | 823296 | 1 | 是 |

实际索引路径：`/mnt/datastore/tank/vm/116/<timestamp>/drive-sata0.img.fidx`。现装官方`proxmox-backup-debug inspect file <path> --output-format json`确认size为100GiB，chunk-digests仅有`bb9f8df61474d25e71fa00722318cd387396ca1736605e1248821cc0de3d3af8`。该值与`hashlib.sha256(bytes(4*1024*1024)).hexdigest()`相同；每个索引4096B头之后25600条32B摘要也全部相同。六份索引均记录100GiB零数据，不提供已安装Windows恢复候选。

最早和最新配置均指向10月12日新建实例；元数据包含OS、EFI、TPM文件。最早PVE备份任务及最新`/var/log/vzdump/qemu-116.log`均明确记录`100.00 GiB (99%) total zero data`。

局限：这是索引与既有备份日志证据，并非本轮完整chunk读取/verify或试恢复；没有宣称完成灾难恢复演练。不能恢复覆盖生产盘来试错。尝试通过客户端restore读取`client.log`失败，原因manifest不包含该blob；未把files列表出现文件名当作日志已读取。最初手工解码索引头偏移不正确，错误size已弃用，以上长度以官方inspect结果为准。

## 历史操作证据

时间均转换为Australia/Sydney；来源为PVE保留任务日志、`/etc/lvm/archive/*.vg`及现有备份日志。

| 本地时间 | 操作及已确认结果 |
|---|---|
| 2026-09-20 16:45:51+10 | ESXi Windows11 live-import失败，QEMU duplicate node-name；旧目标tank:vm-116-disk-0/1。 |
| 2026-09-20 16:55:43+10 | 另一项qmcreate:116完成，日志创建tank上的EFI和100GiB OS盘；成功不等于已验证Windows功能。 |
| 2026-09-21 10:36:53+10 | qmdestroy:116因tank不存在/无法导入而失败。 |
| 2026-10-12 10:40:28+11 | qmdestroy:116完成，任务日志purging VM116、TASK OK。 |
| 2026-10-12 10:41:33+11 | qmcreate:116新建local-lvm EFI、100GiB SATA和TPM；日志不是restore/import系统数据。 |
| 2026-10-12 10:42:05+11 | 最早现存PBS备份；日志已显示100GiB零数据。 |
| 2026-10-21 16:44:40+11 | 创建toolhive-authz-acceptance-20261021快照。 |
| 2026-10-25 00:17:08+11 | 最新PBS备份；日志仍显示100GiB零数据。 |
| 2026-10-25 00:28:57+11 | qmdelsnapshot完成，精确删除三条snap_ LV，未显示删除活动盘。 |

快照删除目标由任务日志及LVM archives互证：`pve/snap_vm-116-disk-{1,0,2}_toolhive-authz-acceptance-20261021`。相关archive为`pve_00130`至`pve_00135`；10月12日创建证据为`pve_00067`至`pve_00075`。这些是LVM配置元数据历史，不含可直接恢复Windows的文件内容。

关键UPID：

- 新建：`UPID:pve1:002FCB23:0A8A639C:6ACC1EAD:qmcreate:116:root@pam:`
- 前序销毁：`UPID:pve1:002FC965:0A8A4A68:6ACC1E6C:qmdestroy:116:root@pam:`
- 最早备份：`UPID:pve1:002FCC1D:0A8A7043:6ACC1ECD:vzdump:116:root@pam:`
- 快照删除：`UPID:pve1:003E5A7C:11042BE9:6ADCB299:qmdelsnapshot:116:root@pam:`

因零盘在快照删除之前已存在，当前证据不支持把Windows消失归因于最近快照清理；也没有证明哪个更早动作丢失过已安装系统。

## 原来源与排查范围

原ESXi导入日志中的路径为`/run/pve/import/esxi/esxi-import/mnt/ha-datacenter/SamsungSSDEVO8701T-2/Windows11/Windows11.vmdk`。这是当时的导入挂载路径，不是当前存在的文件证明。

主checkout本地历史`terraform/esxi/terraform.tfvars`只提取非密钥endpoint：vCenter192.168.1.250、ESXi192.168.1.251；与历史文档一致。两地址的HTTPS `/sdk/vimServiceVersions.xml`均5秒超时。当前仓库PNETLab又使用.250，不能据旧地址假定vCenter仍在线。未猜IP扫描、未初始化Terraform、未重建已退役workspace。

已查位置：

- pve0完整mainpool/rpool filesystem、volume和snapshot名称；mainpool/vmdata及rpool/data没有116卷；相关local dump与Windows/VMDK候选文件未找到。
- pve1全部现存LVM及相关archives；nvme-lvm无116盘，local-lvm仅上述三盘；当前无ZFS池与/dev/zvol/tank。
- pve2完整mainpool filesystem、volume和snapshot名称，包括datastore之外层级；mainpool存储配置指向pool根，不存在被vmdata子树漏掉的116卷。local-lvm、mainpool、pve2-ssd与相关dump未发现116/VMDK。mainpool中VM101/102/103配置分别为WLC、ISE、laas控制器。
- 三节点当前by-id设备、pool create/import/rename历史；未执行pool导入、裸盘扫描或恢复旧LVM元数据。
- PBS已挂载tank全部dataset/volume元数据及vm/116恢复点；只有tank filesystem，无116 zvol。

pve2的两块Samsung870EVO1TB序列为S74ZNX0X630283Y、S74ZNX0X726133H，pool history记录2026-09-20 21:42:42新建mainpool镜像，而非tank改名导入。型号与旧ESXi两datastore相符，但旧ESXi记录未给对应序列，物理同一性不能完全证实。

历史pve1 tank的两WD6TB序列WC3K20AE5KA2、WC3K20AE5KA9现已在PBS找到，为tank mirror-2。PBS history明确2026-09-21 23:16:08执行zpool add将两盘加入PBS池，并非保留旧pve1 tank导入。该事实不证明可恢复旧zvol，也不授权扫描盘上旧数据。

## 证据命令、位置与操作局限

只读命令包括`qm config/status/pending/listsnapshot`、`pvesm path/list/extractconfig`、`dmsetup info/table/status`、`lvs`、`blkid -p`、`zfs list`、`zpool status/history`、`lsblk`及PVE任务API读取。原配置只筛选设备/启动等非凭据字段，root历史只提取116相关操作类型/卷名；没有保存或公开凭据及完整私有配置。

持久原始来源保留在节点既有`/var/log/pve/tasks/`、`/var/log/vzdump/qemu-116.log`、`/etc/lvm/archive/`以及PBS上述fidx路径；本轮命令脱敏结果见父会话工具记录。未将新的完整原始证据另存到私有执行目录，因此不声称该目录已有本轮采集包。批准的私有归档根仍为`/root/migration-proxmox-20261025/execution-20261026/`，若后续需归档原配置应由父任务沿既有权限处理。

一次PBS路径搜索未先排除.chunks，已精确终止本轮启动的find进程；随后仅在排除.chunks的元数据路径查询，没有扫描chunk内容。没有以中断搜索结果证明目录不存在。

## 恢复条件与当前判定

保持VM116停止及原盘/配置/现存恢复点；暂停其迁移。下一有效输入是原`Windows11.vmdk`、更早包含系统的离线备份，或能证明旧磁盘去向的资产记录。用户回复待回。找到候选后先按只读方式验证Windows分区/文件和来源，再由父任务确定恢复位置与容量；不得用安装ISO重新安装冒充恢复原Windows，也不得以现存全零PBS备份覆盖当前盘来试错。


## 父任务后续证据归档

2026-10-26约01:55 AEDT，父任务将本轮新鲜config/status/pending/snapshot、OS dm table/status及上述四项关键任务日志只读采集到pve1私有目录`/root/migration-proxmox-20261025/execution-20261026/vm116-readonly-evidence/`，目录0700、文件0600。完整配置仅留该root私有目录。`manifest.json`记录六项成功设备/配置读取及初次四项CLI参数失败；`task-api-manifest.json`记录随后通过pvesh读取的四项任务日志全部成功、命令/字节及SHA。原失败保留，没有把失败采集当有效日志。实际VM116及盘未修改。这是对前文“尚无新增私有采集包”的时间后续更新。
