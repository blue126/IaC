# 验收与停止条件

本次已核对pve2 SSH及22/8006可达；PBS恢复能力和pve2接收资源条件按用户明确确认关闭复核项，证据不标作助理实测。其余下列检查均是未来实施要求，未因文档定稿或Spec更新而通过；完整操作采用[validation-and-rollback.md](../../planning-artifacts/architecture/architecture-IaC-2026-10-25/validation-and-rollback.md)及[runbook.md](../../planning-artifacts/architecture/architecture-IaC-2026-10-25/runbook.md)。每项私有记录Australia/Sydney时间、对象、阶段、退出码/任务ID、证据位置和数据截止点；不公开凭据、配置全文或state。

## 能力验收

| 能力 | 实施通过条件 | 证据 |
|---|---|---|
| CAP-1 | pve2接收资源/PBS恢复能力以用户确认满足，助理跳过复核；pve2连接检查通过；同ID交接、网络断链及Linux元数据演练仍须通过，每次实际T0备份任务/范围/保护及错误核对 | 用户确认记录、pve2 SSH与端口结果、未豁免演练及当次恢复点记录 |
| CAP-2 | pve2的VM108 OS/SSH/containerlab和实验持久数据正常；验证后关机/onboot0，IaC不启动；pve0旧源已退注册、原盘与配置保留且ID留置 | 原/目标配置及卷映射、首启时间、权威谱系、实验功能、目标state/provider身份 |
| CAP-3 | VM112–117、CT111/118位于pve0，Windows验后关机，其他常开；磁盘/EFI/TPM/ISO及桥/ACL无遗漏，原pve0业务无退化 | 逐业务功能、源/目标清单、运行状态与基线对照 |
| CAP-4 | 全量文件和元数据清单通过，两Mac各识别旧历史、完成增量及代表性文件恢复；报告760GiB、硬限额800GiB、40GiB差额及系统余量核验 | 内容SHA256/路径/类型/UID/GID/mode/ACL/xattr/链接、客户端结果、字节容量及有效Samba配置 |
| CAP-5 | 3项既有IaC资源精确重新绑定、伴生依赖正确，完整/定向plan无意外动作且PBS VM100零动作；Ansible/NetBox/备份归属一致，迁后恢复点可读且verify | 私有state/哈希、endpoint/node/VMID/volume映射、脱敏计划、备份范围及namespace/owner |
| CAP-6 | 累计回退A/B/C签入变更单，容量/metadata和可达性成立；每台至少30分钟、整体24–48小时真实并发通过，无迁移导致持续压力/OOM/异常 | node/pool累计账本、内存/PSI/CPU排队/盘错误/响应、数据截止点及回退业务复验 |

## 服务检查

| 对象 | 验证 |
|---|---|
| VM112/113 | 原OpenBao测试入口、控制功能与数据；不使用生产凭据作仓库验证 |
| VM114 | HA集成及一项已知安全自动化，不误触发物理设备 |
| VM115 | 原入口真实语音识别，耗时与迁前基线对照 |
| VM116 | OS/网络/磁盘/EFI/TPM及ISO内容，验证后关机 |
| VM117 | PDM入口及原已管理节点 |
| CT118 | 持久记忆、原API查询及客户端；源compose stop，目标原compose start，不拉取/重建 |
| CT111 | 真实/srv/timemachine挂载、SMB身份/权限、两Mac历史/增量/恢复，不意外新建备份身份 |
| 原pve0服务 | 原入口与关键功能定向复验，不扩为部署/升级 |

不能以HTTP200、running、du或抽样文件代替上述验收。CT111/118在源仍注册的停止视图采集，目标同类离线视图、相同ID映射比对；rootfs与每个数据集独立清单，ACL内部ID不得靠字段归一化掩盖。任何lost+found权限问题、读取失败、未解释差异或未知ACL转换都阻断；需证明空目录才可登记同一排除，不能忽略错误。

## 准入、失败和恢复

- vmdata预算336GiB＋128GiB余量且不依赖旧VM108释放；CT111 quota/refquota/reservation800GiB、Samba760GiB；系统实际dataset可写余量≥64GiB。全池消费者、快照/预留/元数据/临时恢复及SMART/历史错误入账，不以pool FREE或ONLINE替代。
- 启动前MemAvailable≥guest配置＋8GiB，ARC有效上限已知；压力停止与恢复按runbook附录G，Windows提前验后关机。采样/值守缺失、OOM、存储错误或持续业务退化时暂停验收；不通过临时停掉业务来宣布容量已合格。
- 内部API仅退注册、原盘未变、ACL/firewall/缓存/锁与全局ID检查必须演练。测试资源创建/回收另批，AD-3失败或版本/哈希变化时停止修订，不destroy替代。真实断链须有guest、tap/veth及生产服务负向探测。
- 首次目标启动即默认T1；无法确认是否启动也按T1。T1失败保全停止，不能回旧盘；例外R0须书面无业务新数据证明及明确接受验证副作用损失。
- 累计回退不能多次认领同一free。thin data安全线候选为nvme-lvm max(32GiB,池5%)、local-lvm max(16GiB,池5%)，metadata至少20%空闲，实施前确认；未知写入峰值不得认领A。B精确卷释放须新授权及T0/T1可读、目标盘保留，释放后R0失效；C不承诺即时回源。
- PBS恢复点创建即protected，任何retention不得解除，源盘最终清理还须有迁后数据盘备份verify。pve2失效可能VM108及PBS同不可读，按实际可读点记录数据截止点；较新数据不保证恢复，无可读点保全等待，不承诺双机故障或RPO0。
- state写窗口、生产服务停止、备份/恢复/保护、管理更新和基础设施写入须对应授权。本次旧源副本按用户确认可在既定迁移验收通过且迁后备份verify后清理，不额外保留，执行核对精确原卷清单，清理后R0原盘回退失效；不扩大到失败残留/未知卷或PBS保护解除，不按VMID扫描删除。pve1继续在线；未来关机另议，若仲裁失败立即恢复，不降票。

## 本轮交付判定

本轮通过的是六项能力编号保留、三项已确认策略吸收、架构AD映射和配套文件引用的一致性与保真自检；未新增stories或延期条目。独立架构评审记录保留原输入版本，不把此次Spec派生称为新增独立评审或生产验收。所有适用现场能力验收通过后才可宣布迁移完成。
