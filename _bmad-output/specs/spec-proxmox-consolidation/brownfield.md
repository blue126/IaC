# 现场基线与证据边界

依据为2026-10-24至25日已记录核查及定稿架构，非持续监控；本次仅补查pve2可达性：SSH hostname和TCP22/8006成功，未读取资源配置或写入。字节、版本及证据限制详见已采用的[preflight-evidence.md](../../planning-artifacts/architecture/architecture-IaC-2026-10-25/preflight-evidence.md)，实施前刷新，不能把旧恢复点列表或仓库声明当现场可恢复证明。

## 主机与资源

| 对象 | 最近记录 | 设计含义 |
|---|---|---|
| pve0/pve1 | HomePVECluster，PVE9.0.3、内核6.14.8-2-pve；i5-8500T/i5-8500，均6核 | host CPU不同；采用冷恢复，非热迁移 |
| pve0 RAM | 约62.6GiB，无swap；迁前MemAvailable约34GiB | 与配置额度分开；迁后69GiB受控超配，Windows另16GiB不并发常开 |
| pve1 RAM | 32GB级，约1.6GiB swap已用 | 不能把迁前低占用当峰值保证 |
| vmdata | mainpool/vmdata，2×2TB Samsung990PRO镜像，available722047012864B≈672.46GiB；sparse=0 | 预算预留，不用池物理free替代dataset available |
| local-zfs | rpool/data，单块1TB WD Blue SA510 SATA SSD，与系统共享；available942772604928B≈878.02GiB | 无镜像；SMART及历史错误需解释，系统dataset余量单独核实 |
| pve2 | 独立节点；2026-10-25T10:20:35Z SSH hostname返回pve2，TCP22/8006可达 | 接收资源条件由用户确认，本轮仅查可达性，不重复资源核验 |
| PBS | 仓库为pve2 VM100，16GiB、HBA/SSD直通；早前曾不可达，本轮未探测 | 恢复能力按用户明确确认视为已验证，跳过复核；接受共享故障域 |
| 仲裁 | pve0/pve1各1票、QDevice1票，quorum2；N100 .53见证路径 | pve1后续关机依赖见证，保留成员，不降票 |

CPU历史3秒采样pve0/pve1为10.7%/10.0%；最近一周半小时均值12.2%/5.7%、P95 17.1%/17.0%、最大43.6%/83.3%。均值粗加约18%不代表8500T迁后性能，不能相加P95。迁前来宾实际使用合计约40GiB也不保证峰值；ARC先前约3.12GiB上限须重新读有效值。

## 来宾与管理差异

- VM108为containerlab，4vCPU/32GiB/100GiB、OVMF，源曾running/onboot1，四个clab-evpn-vxlan容器运行；保存拓扑和持久化状态后再停。IP .108、MAC BC:24:11:B3:C8:DE，源vmbr1，目标桥需核验。源zvol used109055836160B、usedbyrefreservation93271642112B，保留源盘不释放。
- CT111非特权，根8GiB，mp0真实卷nvme-lvm:vm-111-disk-0，900GiB ext4挂载/srv/timemachine、backup1；df Used730980683776B。du apparent730989341115B但lost+found权限失败，仅为下界，须宿主补审。
- CT111 unused0=nvme-lvm:900G已证实解析无效；保留不清理。其他未知unused不能一概判无效。Samba迁前报告800G，fruit/streams_xattr启用，Webmin/操作者拥有配置；一次性Ansible bootstrap默认1T不得重跑。
- CT118非特权，8GiB内存、24GiB根，nesting/keyctl；Compose /opt/hindsight/compose.yaml唯一服务hindsight，须完整持久数据及已运行服务恢复。
- VM116前序获准删除的toolhive-authz-acceptance-20261021及三个LVM快照卷已删除，不重复删除；仍须查新增快照。win11_iot_ltsc_2024.iso、virtio-win.iso在目标同名不证明内容一致；EFI/TPM/介质不遗漏。
- 备份周期作业最近disabled，旧10月22日恢复点不证明现可读或已试恢复。仅按新授权制作迁后恢复点；启用周期作业另批。

## 已验证机制与仍缺的证据

现装LVM导出raw+size、ZFSPool接收zfs，简单离线storage_migrate无共同流格式；并非本轮执行迁移失败。内部destroy_config仅退配置与qm/pct destroy删盘不同，但源码核验不是交接演练。高级CT恢复须显式全部rootfs/mp映射。真实Linux ACL/xattr、全量清单、网络断链、同ID缓存/锁/firewall恢复均待现场演练；macOS空xattr stub和Perl语法检查不能替代。

定向代码依据：terraform/proxmox/{ubuntu-2604,fileserver,pdm,pve-cluster,provider,pbs,pnetlab}.tf及相关模块、Ansible pve2 host vars。执行前与当前代码交叉核对；bpg/proxmox固定0.70.0，VM108/CT111/PDM保持既有Terraform ownership。版本/模块哈希及官方机制链接沿用已采用证据文件，不把latest文档当现装版本。
