# 迁移布局与实施约束

本文件为Spec的布局与边界摘要；PBS恢复能力和pve2接收资源条件已由用户确认，跳过重复复核；pve2 SSH及TCP22/8006已可达。本次用户确认优先于adopted文件中这两项旧待核验表述，其他演练不豁免。完整步骤和命令采用[runbook.md](../../planning-artifacts/architecture/architecture-IaC-2026-10-25/runbook.md)，容量论证采用[solution-design.md](../../planning-artifacts/architecture/architecture-IaC-2026-10-25/solution-design.md)，回退采用[validation-and-rollback.md](../../planning-artifacts/architecture/architecture-IaC-2026-10-25/validation-and-rollback.md)。这三个文件及架构脊柱均为原技能维护的adopted companions，本次未改写。

## 目标与串行顺序

| 顺序 | 来宾 | 内存GiB | 主盘GiB | 目标/验收后状态 |
|---|---|---:|---:|---|
| 1 | VM108 containerlab | 32 | 100 | pve2-ssd/vmbr0，接收能力用户确认；验证后关机/onboot0 |
| 2 | VM116 Windows11 | 16 | 100＋EFI/TPM | pve0/vmdata，提前验证后关机/onboot0 |
| 3 | VM112 OpenBao bao | 4 | 20 | pve0/vmdata，运行 |
| 4 | VM113 OpenBao control | 4 | 20 | pve0/vmdata，运行 |
| 5 | VM117 PDM | 4 | 40 | pve0/vmdata，运行 |
| 6 | VM114 Home Assistant | 4 | 64 | pve0/vmdata，运行 |
| 7 | VM115 FunASR | 12 | 40 | pve0/vmdata，运行 |
| 8 | CT118 Hindsight | 8 | 24 | pve0/vmdata，运行 |
| 9 | CT111 fileserver | 0.5 | 根8＋数据新800 | pve0根vmdata、mp0 local-zfs，运行 |

pve0来宾保留原vmbr1及VMID/IP/MAC，OVS/Linux bridge同名不证明VLAN/MTU/firewall相同。每台完整完成停写、T0、交接、恢复、校验和管理同步才继续，不一次关闭全部业务。

## 切换与身份

全部来宾冷备份恢复；取消旧Spec的直接离线LVM→ZFS映射。停应用写入并优雅停guest、关闭onboot，制作创建即protected的T0并verify；源仍注册时以宿主离线视图采全量清单，卸载后按演练过的内部API仅退注册，保存私有配置/原盘。确认同集群ID空闲才恢复同ID停止目标；不force、不destroy、不live-restore。

目标离线内容/元数据及全部磁盘/挂载通过后，全网卡栅栏下首启验证；真实tap/veth/生产探测须证明隔离，不只看link_down字段。首启即转移权威，未知首启也按T1。VM108源也在目标首启前退注册并留置ID；旧孤立卷不得rescan/复用ID。管理对齐且唯一写入者确认后才解除栅栏开放入口。

CT111文件级恢复到新800GiB子卷，不缩源900GiB ext4；显式全部rootfs/mp、保持非特权及相同ID映射。两Mac停备份、SMB及全部写者停止；源权限错误补审，目标挂载和Samba验证后才开放。CT118源先compose stop并停CT，目标隔离验证时用原compose start，不up拉取/重建；依赖不可达不能通过放开生产客户端绕过。

## 容量与内存

| 项目 | 准入/停止规则 |
|---|---|
| vmdata | 主盘316GiB，含预留/EFI/TPM/Cloud-Init等采用新增336GiB预算，另留128GiB；available约672.46GiB，不计VM108源释放 |
| CT111数据 | quota/refquota/reservation均800GiB，含快照总占用上限；Samba报告760GiB，40GiB差额用于元数据与写入余量，非每Mac独享 |
| rpool系统 | 初分配前800GiB＋64GiB＋本次元数据/其他增长；后核实实际系统dataset available≥64GiB，不重复加已预留800GiB；64GiB是操作线，不是CT111预留提供的系统硬保证 |
| PBS | 全部待迁逻辑盘约1316GiB；T0/T1两轮约2632GiB另计既有保留/元数据，不计去重；不放本地681GiB tar/suspend副本 |
| 内存 | 常开配置69GiB受控超配，不承诺满配；启动前MemAvailable≥该guest配置＋8GiB且ARC已知，Windows优先验后关机；pve2含PBS/其他负载 |

内存停止线依runbook附录G：低于8GiB持续60秒或PSI some avg60≥10%持续60秒暂停准入/新增重任务；低于4GiB持续15秒或OOM进入保全；≥10GiB且PSI低于阈值15分钟后人工逐台恢复。维护窗口5秒采样，单台稳定观察至少30分钟，整体24–48小时。停止范围须写入批准的变更单；建议顺序为本节点未开放验证guest→OpenBao测试VM112/113→FunASR VM115→Hindsight CT118，逐项确认依赖后采纳；保留HA、fileserver与基础管理服务。此顺序仍为建议，未视为用户已批准。不临场降阈值、停未授权生产负载、改内存或增swap。上述是初始操作规则，不是防OOM测试证明。

Samba由Webmin/操作者更新，testparm及两Mac容量报告核验；PVE mp0 size=refquota，Terraform声明同值；不重跑1T bootstrap或单方面扩容。rpool SMART/历史错误、祖先配额、快照和系统增长入账，余量将越64GiB停止新增写入并处理容量。

## 管理、备份与回退

- iac-proxmox-lab整个state独占写维护窗口内，准备VM108/CT111/VM117直接adoption资源，按runbook附录E精确state rm/import，保存私有state/哈希，不跨endpoint猜绑定。保留ansible_host并核对outputs；两项创建镜像仅退state不删文件，不改共享模块、不重放初始化。
- 完整及定向计划均不得意外创建/销毁/替换/回迁/启动/重启，PBS VM100零动作；不以reboot=false或定向apply放行，不升级provider。Terraform/Ansible只在仓库Sandbox运行；生产凭据/state访问另行授权，不作为PR验证。
- T0/T1创建即protected并复核，记录server/datastore/namespace/type/ID/timestamp/owner及源/目标alias；VM108新备份专用namespace，旧T0仍用原namespace。CT111新获准备份固定stop；周期作业维持disabled，启用另批。备份verify不替代应用恢复。
- 首启前R0可恢复原盘/注册；首启后默认先保全最新T1，R0例外需书面无新业务数据证据及明确接受验证副作用丢弃。不能因目标关机就启旧源。
- node/pool统一累计认领全体来宾及试恢复、data/metadata和VM108回pve0双卷峰值：A有空间新增T1；B另批精确源旧卷释放后恢复；C保全可读盘/恢复点等待修复，不保证即时回源。源nvme-lvm约93%已用，CT111不能默认A；详细预算及返回原存储映射见validation文档。
- 用户接受PBS与VM108共pve2故障域。无可读T1时只能考虑最近可读已验证点，明确数据截止点与可能损失并取得相应决定；不保证双机故障回退/RPO0。

## 时间与交接

VM112/113按用户说明约一周后退役，本次仍迁移、不自动删除。退役后常开配置由69GiB降至约61GiB；实际驻留内存释放另看现场，不免除宿主/ARC预算或现有内存停止线。

撤回旧fileserver1–3小时及释放VM108后约450GiB余量的依据。fileserver需源摘要、备份、恢复、目标摘要四次全量遍历，加verify和两Mac验收，候选6–12小时按演练吞吐重算；其他来宾按实际已用/吞吐排时，不保留旧固定预算为承诺。

用户后续明确：迁移按既定验收标准通过后即可清理本次旧源副本，不另加保留期；清理前确认迁后数据盘备份verify、唯一活动副本及精确原卷清单，清理后原盘R0回退失效。该选择不包含PBS受保护恢复点、未知unused或无关卷；pve1继续在线，关机不作为本次迁移待决项。此项为用户对原方案保留时机的后续澄清，以本Spec记录为准，未改写架构原文。

本次已吸收架构定稿时列出的“驱动Spec对齐”内容，关闭该文档交接项；adopted文件保留原定稿文字与哈希。pve2接收能力/PBS恢复能力按用户确认关闭复核项，pve2可达性已通过；内部API与网络/Linux元数据演练、其他容量账本、维护窗口、停止/回退分支及写入授权未因此通过。源副本验收后可清理的条件已确认，具体执行仍须精确清单与适用授权；保护解除另批。观察24–48小时后pve1仍保持在线和成员/QDevice；未来若决定关机，另获授权并核对见证票与quorum，失败恢复pve1，不降票。
