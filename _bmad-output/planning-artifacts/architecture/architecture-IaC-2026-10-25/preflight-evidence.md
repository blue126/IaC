# 只读核查与待验证项

日期：2026-10-25，Australia/Sydney。没有停机、备份、恢复、配置/state写入、配额修改、挂载或文件清理。

| 核查 | 结果 | 证据口径 |
|---|---|---|
| pve0/PVE | 9.0.3；storage9.0.13、qemu-server9.0.16、container6.0.9、ZFS2.3.3-pve1 | pveversion -v |
| rpool | ONLINE，READ/WRITE/CKSUM为0，最近scrub无错误 | zpool status -v；未据此排除历史故障或代替SMART |
| pve2 .52 | SSH仍超时 | 本机BatchMode/5秒连接；未猜测关机原因 |
| PBS .249 | inactive，No route to host | pve0 pvesm status |
| VM108 | running/onboot=1，实机名containerlab；客体hostname仍ubuntu-2604 | qm config/status与SSH |
| VM108工作负载 | 四个clab-evpn-vxlan测试容器运行 | sudo -n docker ps，仅列名称/状态 |
| CT111 | root8G、mp0 nvme-lvm:vm-111-disk-0 900G；非特权 | pct config |
| CT111未知引用 | unused0=nvme-lvm:900G，pvesm path解析失败 | 非真实已识别卷，不授权清理 |
| CT111大小 | df Used730980683776B；du apparent730989341115B但lost+found Permission denied | du非完整成功，不能据此签完整性通过 |
| Samba | TimeMachine=/srv/timemachine，fruit streams_xattr，800G报告限制 | testparm只读过滤 |
| 备份/快照 | 前序Windows快照已删除；最近作业禁用、旧恢复点为10月22日 | 本轮未做新备份/恢复，实施前重查 |

> 🧠 **From Hindsight memory (Key decisions and rationale)** — VM108 的当前用途必须核查，不能只依据旧部署文档安排关机。本轮已独立验证四个运行中的 containerlab 容器；此处记忆作为调查线索，实机输出作为现状证据。

## 已查明的迁移机制

pve0 /usr/share/perl5/PVE/Storage.pm 的storage_migrate计算volume_transfer_formats，无共同格式即报cannot migrate；LVMPlugin只接受raw+size，ZFSPoolPlugin只接受zfs，ZFS import复用export_formats。QemuMigrate对停止guest的本地盘采用offline；LXC/Migrate也调用storage_migrate。故原简单离线映射不成立，不是本轮实际执行失败。

pve0 /usr/share/perl5/PVE/AbstractConfig.pm的destroy_config仅unlink调用节点的guest配置；不执行磁盘删除。lock_config使用原生配置锁并cfs_update。qm/pct destroy CLI则会销毁磁盘并删除相关权限/firewall，不能混用。**对内部API函数体的只读核验不是交接演练完成**；仍需隔离验证全局VMID、daemon缓存、任务锁、firewall/ACL与恢复行为。

pve1 PVE/API2/LXC.pm在restore中跳过unused设置；不因此删除源unknown引用。官方pct restore advanced模式在显式rootfs/mp时忽略备份中所有原挂载设置，因此必须把rootfs和每个mp逐个补全，不能只传rootfs。

## 执行前必须补齐

- pve2版本、CPU/32GiB启动余量、VMID108、vmbr0及pve2-ssd容量；PBS空间、访问与恢复凭据只在私有运行时使用。
- CT111宿主离线完整清单、lost+found实际情况、ID映射、ACL/xattr与文件摘要可比性；当前权限错误不可忽略。
- 同ID退注册/恢复/回退的隔离演练，原生锁与source/target任务互斥，以及恢复后firewall/ACL校验。
- 原备份范围含111 mp0、全部VM磁盘/EFI/TPM；本地ISO、bind/device mounts、guest外部数据单独盘点。
- 精确卷清单与返回源的容量账本，特别是thin metadata/data空间；恢复演练与业务验收的时间。

## 外部机制依据

- [Proxmox备份与恢复](https://github.com/proxmox/pve-docs/blob/master/vzdump.adoc)：stop/suspend及额外挂载备份边界。
- [LXC advanced restore](https://github.com/proxmox/pve-docs/blob/master/pct.adoc#advanced-restore-mode)：恢复时逐挂载映射、目标大小可变。
- [pct命令参考](https://github.com/proxmox/pve-docs/blob/master/generated/pct.1-synopsis.adoc)、[qm命令参考](https://github.com/proxmox/pve-docs/blob/master/generated/qm.1-synopsis.adoc)：命令以本机9.0.x帮助为准。
- [OpenZFS属性](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html)：quota含子级/快照，refquota限定活跃引用；预留不是数据实际已用。
- [Samba fruit](https://www.samba.org/samba/docs/current/man-html/vfs_fruit.8.html)：报告容量不替代文件系统硬限制。


## 本轮私有原始证据

已补采pve0/pve1的版本、池/卷属性及相关已安装模块SHA256，原始stdout/stderr与命令/UTC时间/退出码/摘要保存在本任务私有临时目录：`/var/folders/sw/f6wx_nqd1p181b7cygj65gyc0000gn/T/iac-migration-evidence-1ylk03ft`，目录0700、文件0600。以其中manifest.json核对本次输出；临时目录不保证跨会话持久化，进入正式维护前须另行批准保存到持久私有证据位置。本轮仅SSH读取，并未运行文档里的挂载/备份/退注册或配额命令。

附录B/C已提供清单生成与网络栅栏草稿；这些补充不表示生产演练已通过。CT111源smbd.service实查active/enabled；CT118唯一Compose服务hindsight，/opt/hindsight/compose.yaml存在。


## 独立评审后的证据澄清

私有已采集pve0与pve1 stdout均为：libpve-guest-common-perl6.0.2、pve-cluster9.0.6、qemu-server9.0.16、pve-container6.0.9、libpve-storage-perl9.0.13；两节点AbstractConfig.pm SHA256均46c9e20f1e8b3c442a78d06523e2d9ea5cce938931c3611379c161e98b661d74。先前表只列pve0摘要，现补齐pve1；实际执行前重新采集并与演练版本/哈希比较。

configure-fileserver-timemachine.yml确有1T默认值，但文件头明确为one-time bootstrap且之后由Webmin拥有Samba配置，不在site.yml/日常自动化运行。本方案保留Webmin/操作者ownership并禁止重跑bootstrap，不采纳“Ansible是当前唯一Samba所有者”的推断。硬quota与报告值相等仍是真实余量问题，用户现已选择报告760GiB、硬限额800GiB，保留40GiB差额；这是待实施值，不是现网已修改证据。

pbs.tf当前声明PBS为pve2 VM100、内存16GiB及HBA/SSD直通；这支持按共享故障域规划，但不能由两个超时推断同一故障原因。pve2开机验收需将PBS与ARC、宿主及其他guest一并纳入内存/I/O准入。

网络栅栏演练还需验证真实效果：guest与宿主tap/veth的断链状态、生产网段的ARP/ping/实际服务负向探测，而非只检查link_down配置字段。现场pct help已证实netX支持link_down，但真实隔离效果尚未演练。

受保护快照/namespace参考[官方PBS客户端](https://pbs.proxmox.com/docs/proxmox-backup-client/man1.html)与[命名空间](https://pbs.proxmox.com/docs/storage.html)；adoption/import依据[固定bpg0.70.0 VM](https://raw.githubusercontent.com/bpg/terraform-provider-proxmox/v0.70.0/docs/resources/virtual_environment_vm.md)及[container](https://raw.githubusercontent.com/bpg/terraform-provider-proxmox/v0.70.0/docs/resources/virtual_environment_container.md)，不是套用latest provider文档。
