# 技术现实核验

日期：2026-10-25。对象为 ARCHITECTURE-SPINE.md 与 solution-design.md、runbook.md、validation-and-rollback.md、preflight-evidence.md。本层只做文档及公开官方机制核验；没有连接生产节点、执行迁移、修改原稿或调用外部模型。没有把其他必需评审计为通过。

## 结论

**备份恢复、文件级缩至800GiB、保留原盘及T0/T1分流的技术方向有公开机制支持；交付应保持 draft，尚不能作为已演练、可直接执行的操作手册。** 未发现必须改成原地ext4缩容或必须删除原盘的依据。AD-3已经正确标为假设，其成功条件仍未证实。

已标注的pve2/PBS不可达、原始容量需刷新、内部API未演练是现存准入条件，并非本核验发现它们已经通过。本文不重新声称实机版本、容量或可达性成立。

## 已有依据支持的机制

| 项目 | 核验结论及边界 |
|---|---|
| qmrestore | 官方参数具有 storage、unique、start 和 live-restore；start默认0。草稿使用unique=0保留MAC、禁止live-restore合理。它不会替代源/目标唯一运行者栅栏；原本地ISO仍须另外准备。[官方CLI](https://raw.githubusercontent.com/proxmox/pve-docs/master/generated/qmrestore.1-synopsis.adoc) |
| pct高级恢复 | 显式rootfs使恢复忽略归档原rootfs/mpX配置，逐项映射是正确要求；文件内容可以恢复到重新创建的更小目标，前提是数据与元数据实际装得下。草稿没有原地缩900GiB ext4。[官方恢复语义](https://raw.githubusercontent.com/proxmox/pve-docs/master/pct.adoc) |
| pct恢复参数 | 官方命令参考支持rootfs、mpX、unprivileged、onboot、start。尚须以现场6.0.9帮助及试恢复确认安装版本；指定unprivileged=1不能证明自定义ID映射一致。[官方CLI](https://raw.githubusercontent.com/proxmox/pve-docs/master/generated/pct.1-synopsis.adoc) |
| quota/refquota/reservation | quota含子级和快照；refquota限制活跃数据；reservation保护该数据集及子级的空间，父级按max(used,reservation)记账。800G不应在恢复后再额外加一次已用约681GiB。相同800G的quota与reservation机制相容，但需实测属性应用及余量。[OpenZFS 2.3.3属性](https://raw.githubusercontent.com/openzfs/zfs/zfs-2.3.3/man/man7/zfsprops.7) |
| 原生退注册 | 上游AbstractConfig的destroy_config仅unlink本节点配置；lock_config调用本地flock包装并刷新CFS。它既不销毁卷，也不提供跨节点全局事务锁。草稿已说明此限制。[官方源码](https://raw.githubusercontent.com/proxmox/pve-guest-common/master/src/PVE/AbstractConfig.pm) |
| 解析/停机检查 | QEMU的parse_vm_config(filename,raw,strict)与check_running(vmid,nocheck,node)，LXC的parse_pct_config(filename,raw,strict)和check_running(vmid)与草稿调用形式一致。这里只核对公开当前源码，不宣称其覆盖现场所有版本。[QEMU源码](https://raw.githubusercontent.com/proxmox/qemu-server/master/src/PVE/QemuServer.pm)、[LXC配置](https://raw.githubusercontent.com/proxmox/pve-container/master/src/PVE/LXC/Config.pm)、[LXC运行检查](https://raw.githubusercontent.com/proxmox/pve-container/master/src/PVE/LXC.pm) |
| 备份边界 | 冷备份＋恢复是正常能力；非rootfs挂载必须确认backup标志，bind/device不随常规容器备份保存内容。草稿已要求盘点这些例外。[官方备份](https://raw.githubusercontent.com/proxmox/pve-docs/master/vzdump.adoc) |

## 需要补齐的操作条件

### TR-1：T1回退仍不是预先具备容量的完整恢复路径

- **位置：** validation-and-rollback.md「R1」第2、4–6步；solution-design.md「回退峰值也要准入」。
- **触发：** fileserver已接收新备份而pve0故障或需要回迁；pve1原薄池仍保留旧卷，装不下第二份完整恢复。
- **后果：** 当前规则会安全停住，却不能兑现可预测的回退时长；可能需要临场批准释放源旧卷或增加存储。草稿已如实说明“空间不足停止”，应保留这个限制。
- **补齐：** 开放目标写入之前，列出每guest回退目标池、实际data/metadata余量、最新数据上限、旧卷保留/释放分支与精确恢复命令。CT111至少验证800GiB最大目标文件内容可在900GiB ext4卷上恢复，同时考虑ext4元数据/保留块和thin metadata；不能只由800<900推导成功。若不准备这些资源，明确用户接受的替代是保留目标修复而非保证回源。

### TR-2：完整性校验与网络隔离还依赖未交付的具体操作

- **位置：** validation-and-rollback.md:19；runbook.md第2、4–6节。
- **触发：** 操作者准备执行，却只有“已批准私有脚本”“隔离启动”“停止应用/数据库”的描述。
- **后果：** 全路径/ACL/xattr/硬链接校验及阻止服务后台写入仍由现场自由实现；不同实现可能漏文件或过早产生业务写入，无法可靠区分R0与R1。
- **补齐：** 在执行版交付清单生成器或已有工具的准确路径/版本/命令、空结果和权限错误的失败用例；给每guest提供已核实服务停止/恢复与隔离/解除步骤，保存原网络配置。若工具缺失，维持明确阻塞，不把本稿称为可直接运行的runbook。

### TR-3：原生API脚本只有函数级证据，尚缺安装版本及完整交接证据

- **位置：** runbook.md附录A；preflight-evidence.md「已查明的迁移机制」。
- **触发：** 从函数体“仅unlink”推导整套同ID交接、失败恢复与权限防火墙均安全。
- **后果：** 集群ID缓存、任务/HA竞争、恢复分配后残留卷、配置重写和ACL/firewall行为未由函数体保证；退注册后可能需要人工恢复。
- **补齐：** 保留现场软件包版本＋相关源码SHA256及最小摘录，演练QEMU/LXC各一例，覆盖退注册成功后restore失败、部分分配、原配置回退、断连/重入、并发创建拒绝、原卷仍在与firewall/ACL一致。公开master源码仅支持机制，不替代9.0.16/6.0.9现场演练。草稿已有阻塞声明，应继续保持AD-3为假设。

### TR-4：64GiB系统空间是准入底线，还不是硬性保留

- **位置：** ARCHITECTURE-SPINE.md AD-5；solution-design.md:48；runbook.md第6节。
- **触发：** CT111设置quota/reservation=800G后，其他rpool子集、系统快照或宿主写入继续增长。
- **后果：** CT111的800GiB上限不会替其他消费者设置增长上限；“预留64GiB给系统”容易被理解为ZFS已经保证的保留量。当前878.02−800≈78.02GiB仅为此刻账本，弹性约14GiB。
- **补齐：** 将64GiB明确写为整池可写余量的验收/运行下限，列出所有兄弟dataset、祖先quota/reservation及system增长预算，说明如何观察和达到下限时停止新增写入/处理。若需要ZFS硬保证，需另外设计并演练相应保留策略，不能由CT111 reservation本身推导。避免在恢复后用“当前available还须再≥864GiB”的错误口径双计已经消耗的数据。

### TR-5：版本和字节证据可追溯性不足

- **位置：** preflight-evidence.md版本表、容量表；Stack表。
- **触发：** 后续操作者按当前版本/容量执行，但只有摘要，没有时间戳、命令退出码及原始只读证据的私有引用。
- **后果：** 无法复核336GiB准入预算的zvol开销、祖先限制及存储节点content限制，也无法判断包升级后内部API是否改变。
- **补齐：** 在私有变更清单保存pveversion完整输出、ZFS池和dataset属性、vmdata块大小/稀疏策略、磁盘映射及输出哈希。本层没有重新连接实机，因此这些数字仅作为已有摘要，非本次验证结论。pve2-ssd仍是候选，不能先写成确定目标；本稿已正确标注未核实。

## 算术与临时空间复核

- 284GiB VM主盘＋32GiB CT根盘＝316GiB；采用336GiB预算给附属卷/开销预留20GiB。672.46−336＝336.46GiB，大于128GiB；不预支VM108释放是正确的。20GiB是否足够仍须由现场zvol/refreservation/块大小证据复核。
- 878.02−800＝78.02GiB，较64GiB底线多14.02GiB；不是宽裕容量。现有Used和带错误的du不是目标恢复精确占用。
- T0逻辑盘预算284＋32＋900＋100＝1316GiB，两轮2632GiB是保守起点；EFI/TPM、元数据、已有备份和保留余量另加。PBS去重不等于可跳过空间检查；当前PBS空闲未核实。
- 不在pve0系统盘生成681GiB临时tar、不同时存两份完整fileserver目标，是合理峰值限制。四遍数据扫描及PBS verify的时间也已计入草稿，6–12h仍应以演练吞吐替换。

## 本层完成条件

公开机制核验完成；没有运行生产命令或改动原稿。TR-1至TR-5属于执行版需要解决的条件，既有“未演练/未可达/未授权”门槛继续有效。本报告只代表技术现实核验，不代表架构rubric、一致性或编辑评审通过。

## 增量核对 — TR-1至TR-5补充

本节仅核对上述原问题的文档补充，保留首轮报告作为历史记录；未运行生产命令、原生API脚本body或外部模型。原文仍由主代理维护，本层仅追加本报告。

| 原项 | 增量核对结果 | 仍有效的边界 |
|---|---|---|
| TR-1 | validation-and-rollback新增逐guest T1恢复表，明确112/113/115回nvme-lvm、114/116/117回local-lvm、118根盘和111双盘映射、108返回vmdata；所有命令均不force。新增A/B/C选择在开放目标写入前签入变更单；CT111的B分支列出两个精确旧源volid，并明确释放后R0失效。原“无精确恢复命令/处置选择”文档缺口已补。 | 这不是已获授权或实际容量通过：B仍需精确对象授权，源实际thin data/metadata和900GiB ext4可写空间必须现场准入；A/B均不满足时只能接受C，不能承诺回源RTO。 |
| TR-2 | runbook附录B已给可审阅的Python清单工具及运行/退出码规则，涵盖路径编码、全量摘要、UID/GID、xattr、硬链接和错误；附录C已给保存原网络、逐netX断链及恢复工具，补充CT111 SMB和CT118 Compose停止/恢复步骤。原“完全未交付工具”缺口已补。 | 两工具仍为草稿。根据主代理告知的测试范围，本机内容分支的合成测试不构成真实Linux ACL/xattr验证：macOS缺os.listxattr且使用空stub，不能据此签署元数据完整性；PVE网络栅栏亦未由生产/隔离guest运行验证。源码已正确提示ACL内部ID、挂载视图与映射口径限制。 |
| TR-3 | preflight-evidence增加私有原始输出及已安装源码SHA256引用；文档继续将AD-3和附录A标为待演练。按主代理说明只做API存在检查和perl -c，没有调用body。原可追溯性子问题已有补充。 | 函数存在、语法通过均不证明交接/恢复/回退、全局ID缓存及ACL/firewall正确。TR-3的完整隔离演练门槛仍未完成，不能关闭为“技术已验证”。 |
| TR-4 | AD-5及solution-design明确64GiB是系统可写余量的运营准入/停止线，非CT111 reservation创建的硬预留；还要求列出兄弟dataset/祖先限制、观察增长并接近底线暂停Time Machine新写入。原语义歧义已消除。 | 仍要在维护前刷新字节账本并实际观察；任何硬保证需要额外设计，当前没有宣称已经具备。 |
| TR-5 | preflight-evidence已引用私有临时证据目录。本层只读核对manifest.json存在2条记录，均含node、command、started_utc、exit_code、stdout_sha256和stderr_sha256，退出码均为0；没有在报告重印私有输出。原“无原始证据引用”缺口已补。 | 本层未逐字复核其中stdout和所有包/卷值，也未重新连接节点；不能将此说成独立实机认证。临时目录不保证持久，原稿已经要求维护前迁入经批准的持久私有位置。 |

**增量结论：** 这些修改实质补齐了首轮指出的文档和可追溯性缺口；TR-1/2/3所对应的真实容量、Linux元数据/栅栏工具演练和内部API交接验证仍作为明确准入条件保留。方案继续为draft，不因本次补充而成为已通过演练的执行手册；必需PAL及其他评审不在本层核验结论内。
