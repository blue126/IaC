# architecture-consistency

输入版本：本次architecture阶段固定快照；请求模型 claude-opus-5-5。CLI返回码 0。

# Reviewer Gate 报告：architecture-consistency（Validate，只读）

**审查对象**：`project/_bmad-output/planning-artifacts/architecture/architecture-IaC-2026-10-25/ARCHITECTURE-SPINE.md`
**同级配套文件**：`solution-design.md`、`runbook.md`、`validation-and-rollback.md`、`preflight-evidence.md`
**驱动规格**：`specs/spec-proxmox-consolidation/{SPEC,brownfield,migration-plan,acceptance}.md`，以及 `AGENTS.md`、`docs/architecture/proxmox-qdevice-architecture.md`
**公开源码交叉核对**：`source/terraform/proxmox/{fileserver,ubuntu-2604,pdm,pbs,versions}.tf`、`source/terraform/modules/proxmox-lxc/main.tf`、`source/ansible/playbooks/configure-fileserver-timemachine.yml`

## 执行边界与缺失项

- **`lint_spine.py` 没有运行**：本次只能只读，不能执行代码。下文"机械检查"一节是我人工逐项核对的结果，不等于 lint 通过。
- **HTML 报告没有生成，也没有写入 `reviews/` 文件**：CLI 只读。完整 markdown 报告就是本回复，由宿主保存。
- **没有派发子代理，也没有运行其他 lens**：本报告只覆盖 architecture-consistency 这一个角色，不代表整个 gate 的结论。
- **没有缺失输入，也没有权限失败**：所有授权文件都读到了；没有读取兄弟角色的输入或报告。

---

## 门禁判定

**结论：不通过，需要修订后才能进入实施准入。** Spine 的单写者、冷备份边界和 T0/T1 分流骨架是对的，大多数危险路径在配套文件里已经关闭。但对抗构造找到了 5 组 High 级漏洞：两个单元都逐字遵守全部 AD，构建结果仍然互不兼容。分别是：

1. VM108 的双谱系；
2. 共享 thin pool 上的回退容量被重复认领；
3. T0/T1 恢复点没有生命周期所有者；
4. CT111 容量语义有四个所有者；
5. 内存峰值这个维度完全没有 AD 约束。

Spine 目前保持 `status: draft` 是正确的。

---

## 机械检查（人工代替 lint）

| 项 | 结果 |
|---|---|
| 占位符 | 没有 |
| AD ID 重复 | 没有（AD-1…AD-12） |
| Binds/Prevents/Rule 是否齐全 | 12 条都齐全 |
| Stack 版本是否钉住 | 已列出的项都有版本。缺 pve1 的包版本和 `libpve-guest-common-perl`，见 M4 |
| 状态标签 | 只有 AD-1/3/8/10 带 `[ADOPTED]`/`[ASSUMPTION]`，其余没有标签（Low） |
| Capability 映射 | CAP-1…6 都有映射。但 **AD-11（回退）的 Binds 不含 CAP-2、CAP-3**，与 H1 有关 |

---

## Critical

没有。所有生产写入都被 AD-12 和红线拦住；本轮不会因为文档本身造成数据损失。

---

## High

### H1：VM108 有两份可写谱系，"同一时刻只运行一份"挡不住轮流运行

- **依据**：
  - AD-1 Rule："独立pve2的源/目标副本只能有一份联网运行"
  - AD-8："源保留但关机/onboot=0"
  - AD-6：源盘无限期保留，直到另行授权
  - AD-11 Binds：CAP-1/4/6，**不含 CAP-2**
  - `validation-and-rollback.md` R0 第 5 步：VM108 只要求"目标必须停止/onboot0并隔离，源才可重新启动"
- **单元 A**（CAP-2 日常使用）：验收后，操作者按需启动 pve2 上的 VM108 做实验，产生新数据，再关机。AD-1（只有一份在跑）和 AD-8（用后关机、onboot=0）都满足。
- **单元 B**（CAP-6 回退，或几周后排障）：pve2 出问题时，按 R0 第 5 步确认目标已停止并隔离，然后启动 pve0 上的源 VM108。AD-1 仍然满足。
- **冲突**：同一个 IP/MAC/VMID 108 出现两条分叉的数据谱系。R0 只检查"目标是否在运行"，不检查"目标自 T0 起是否被启动过、是否写过数据"。AD-11 的分流条件是"开写"，而 VM108 是按需使用的机器，从来没有一个正式的"开写"时刻；`runbook.md` §4 还允许"以生产IP联网验证"。同集群来宾不会这样，因为源配置已被 AD-3 退注册、只留在私有归档里，有一道很强的启动屏障。VM108 的源在 pve0 上保持完整注册，启动屏障只是一个 onboot=0。
- **修复（收紧 AD-1 和 AD-11）**：
  - AD-1 增加"**权威谱系唯一**"：以私有清单记录的"目标首次启动时间"作为权威转移点。转移后，源副本必须施加可审计的启动屏障，例如全部 netX `link_down=1` 加 `migrated-source` tag，或者也按 AD-3 退下源注册。
  - AD-11 增加：从源启动只允许在"目标自 T0 起零启动记录"时走 R0；否则一律先 T1。AD-11 的 Binds 补上 CAP-2、CAP-3。
- **处置**：discuss（选择哪种启动屏障需要用户决定）。

### H2：多个来宾的回退容量重复认领同一个 thin pool

- **依据**：
  - AD-11："回退账本不够时停在目标保全状态"
  - `validation-and-rollback.md` 第 89 行：A/B/C 分支"在首次向目标开放写入前选定并签入变更单"，按 guest 选
  - R1 映射表：VM112/113/115 和 CT111 的 mp0 都回到 `nvme-lvm`；VM114/116/117、CT118、CT111 的 rootfs 都回到 `local-lvm`
- **单元 A**：VM112 在开写前刷新 `nvme-lvm` 的 data/metadata 余量，选 A 分支（源空间够放一份 T1），签入变更单。
- **单元 B**：VM115 稍后用同一份空闲空间做同样的计算，也选 A。CT111 也计入同一个 pool。
- **冲突**：每个单元单独看都满足 AD-5 和 AD-11，但总和超额。一旦需要多来宾同时回退，比如 pve0 整机故障，按 A 分支顺序恢复会把 thin pool 的 data 或 metadata 写满。LVM-thin 写满后，同一 pool 中**被 AD-6 保留的原盘**也会出 I/O 错误；metadata 写满还可能需要修复 pool 元数据。这样 T0 原盘回退路径本身也被损坏。AD-5 只定义了正向 vmdata/rpool 准入，没有回退侧的累计账本。
- **修复（新增 AD-13"回退容量按池累计认领"）**：
  - 按 `node/pool` 维护单一累计账本：每个已开写来宾的 A 分支认领额都累加；data 和 metadata 分别设安全阈值。
  - 认领有效的前提是"已认领总和 ≤ 可写空间 − 阈值"；超出的来宾自动降为 C 分支。
  - 恢复顺序与认领顺序一致；按 pool 显式登记"pve0 整机故障时的整体回退可行性"。
- **处置**：autofix 候选（规则清楚），Validate 模式下只报告。

### H3：T0/T1 恢复点没有生命周期所有者，新的 PBS 作业可能把它们 prune 掉

- **依据**：
  - AD-6 和 AD-11 都要求"保留T0/T1"
  - B 分支要求"T0/T1均可读"
  - `runbook.md` §1："不得在此时运行prune/GC"
  - `runbook.md` §7："PBS新作业覆盖pve0迁入guest……不在迁移中prune"
  - Consistency Conventions 的身份四元组是 `endpoint/node/VMID/volume`，**不含 PBS 的 datastore/namespace/备份组/owner**
- **单元 A**（CAP-5 备份对齐）：在 pve0 上为 VM112…CT111 新建常规作业，按既有规范配置 `prune-backups`（例如 keep-last），对应 runbook §7 的"完成迁后新恢复点"。
- **单元 B**（CAP-6）：观察期 24–48h 内，依赖 `vm/112` 组里的 T0（pve0 故障且 T1 不可得的场景），以及 B 分支要求的"T0/T1均可读"。
- **冲突**：作业自带的 retention 会在它所在的备份组里执行 prune。T0 与常规备份同组，几次运行后 T0 就可能被清掉。"不在迁移中prune"约束的是手工操作，管不到作业配置。
- **同一根因的另一组**：pve0 集群和独立 pve2 都可能把备份写进同一 datastore 的同一 namespace 下的 `vm/108` 组。会出现 owner 校验冲突、互相 prune，或者"最新快照"属于另一台机器。`acceptance.md` 第 33 行要求检查冲突，但 spine 没有决定规则。
- **已处理部分**：`runbook.md` §0/§3 用**精确 volid** 记录 T0_VOL/T1_VOL，"选错快照"这条路径已关闭，不计为缺失。
- **修复（收紧 AD-6、Conventions）**：
  - T0/T1 在 verify 通过后立即标记 **protected**，取消保护和清理一样需要另行授权。
  - PBS 身份写入 Conventions：`datastore/namespace/type/ID/owner`。
  - pve2 使用独立 namespace，或在 namespace 不同时使用独立 datastore。
  - 新作业的 retention 在验收结束前不得覆盖 T0/T1 所在的组，或者 T0/T1 依赖 protected 标记。
- **处置**：autofix 候选。

### H4：CT111 的"容量"有四个所有者，而且互相矛盾

- **依据**：
  - AD-5："fileserver目标800GiB，live加snapshots总quota不超800GiB"
  - `runbook.md` §6：`zfs set quota=800G refquota=800G reservation=800G`
  - `preflight-evidence.md`：现场 Samba 报告上限是 800G
  - 源码 `source/ansible/playbooks/configure-fileserver-timemachine.yml` 第 11、98 行：`timemachine_size_quota: 1T` → `fruit:time machine max size`
  - 源码 `source/terraform/proxmox/fileserver.tf` 第 25–27 行：`volume = "nvme-lvm:vm-111-disk-0"`、`size = "900G"`
- **单元 A**（CAP-4）：按 AD-5 设置 ZFS 硬限额 800GiB（含快照），并保留 Samba 报告值 800G。
- **单元 B**（CAP-5 / AD-9"重绑定既有管理对象与依赖"）：对 fileserver 重跑或对齐仓库里的 Ansible playbook，把 Samba 报告上限写成 1T。
- **冲突一**：报告上限 1T 大于硬限额 800GiB。Time Machine 以为还有空间，不会自己裁剪旧备份，而是直接遇到 EDQUOT/ENOSPC，可能让 sparsebundle 处于写失败状态，危及 CAP-4 要求的"既有历史"。
- **冲突二**：即使两者都是 800G，也有问题。Samba 的 `800G` 按 1024³ 解释，等于硬限额。而硬 `quota` 还要计入快照、ZFS 元数据和 streams_xattr，所以 TM 达到报告上限之前就会先撞上硬限额。
- **冲突三**：PVE 根据配置里 mp0 的 `size` 管理 `refquota`，runbook 另外设置 `quota`/`reservation`，Terraform 还声明 900G。今后任何一方执行 `pct resize`、Terraform 对齐或 playbook 重跑，都会单方面改动其中一个值。
- **修复（收紧 AD-5，加一条所有权规则）**：
  - 写明唯一所有者和不等式：ZFS `quota`（硬限额，由 runbook/操作者拥有）> Samba `fruit:time machine max size`（由 Ansible 拥有，迁移前把 playbook 变量改成与硬限额一致的派生值，并留出快照和元数据余量，例如 ≤ 硬限额 − 余量）。
  - PVE 的 mp0 `size` 必须等于 `refquota`。Terraform 的 mount_point 要么与之同步，要么明确标为非受管。
  - 迁移期间禁止重跑这个 playbook，直到变量对齐。
- **处置**：discuss（余量取值需要用户决定），并 autofix 不等式规则。

### H5：内存和峰值资源这个维度没有任何 AD

- **依据**：
  - SPEC Constraints："迁后常开配置内存约 69 GiB，含 Windows 为 85 GiB"
  - CAP-3："pve0 原有业务无迁移引起的退化"
  - `brownfield.md`：pve0 实际约 62.6GiB，无 swap
  - Spine 的 AD-5 只覆盖存储
  - 配套文件里只有 `runbook.md` §7"不承诺满配"和 `acceptance.md` 的观察要求
- **单元 A**（CAP-3 / VM116）：按验收表"短暂开机验证"Windows（16GiB）。
- **单元 B**（CAP-3/CAP-4）：此时 FunASR 正在做验收所需的真实识别（12GiB），CT111 也在做全量 SHA256 清单（大量读，ZFS ARC 增长）。
- **冲突**：每个单元都守全部 AD，但 pve0 无 swap，叠加起来会超出物理内存。OOM killer 杀掉任一 QEMU 进程，对那个来宾而言相当于直接断电。如果被杀的是 OpenBao、Hindsight 的数据库，或者正在接收 TM 写入的 CT111，就直接触及数据完整性。ZFS ARC 上限是否已设置也没有核实。
- **修复（新增 AD-14"内存峰值准入"）**：
  - 每个阶段登记"运行中来宾配置内存 + ARC 上限 + 宿主保留 ≤ 物理内存 − 余量"。
  - VM116 验证和全量清单遍历都不得与其他高内存验收并发；ARC 上限是准入项。
  - 观察期出现 OOM 即停（`acceptance.md` 已有这一条，属于已处理部分）。
- **处置**：autofix 候选（新增 AD），具体阈值交给用户确认。

---

## Medium

### M1：源清单的采集时点和视图不在 AD-4/AD-7 中，配套文件之间也不一致

- AD-4 的顺序（停来宾 → T0 → 交接 → …）**没有"源完整清单"这一步**。
- `runbook.md` §3 第 60 行写的是在源静止数据上生成清单，但当时 CT 尚未关机，读起来是来宾内视图。附录 B 第 249 行则要求"在已批准的离线挂载视图运行；源须在退注册前采集"，即宿主视图加 `pct mount`。
- **对抗构造**：单元 A 在来宾内视图采集源清单（ID 映射 `[[0,0,…]]`）；单元 B 在宿主离线视图采集目标清单（例如 `[[0,100000,65536]]`）。uid/gid 字段可以归一化，但 POSIX ACL 的原始 xattr 不会转换（附录 B 第 329 行），于是 cmp 失败，结果是一直阻塞（fail-closed，不算不安全）。
- **更危险的构造**：一个单元逐字按 AD-4，把源清单推迟到交接之后。这时已经无法 `pct mount 111`，只能手工挂载源 LV，而 ext4 rw 挂载或日志回放会改写 R0 要用的原盘。
- **已处理部分**：附录 B 已经要求"退注册前采集"。
- **修复**：AD-4 在"T0 验证"和"源注册交接"之间插入"源完整清单（宿主离线视图）"。AD-7 规定两侧使用**同一视图类型**和同一份映射 JSON。禁止在退注册后挂载源卷（确有需要时必须 `ro,noload`）。同时统一 runbook §3 与附录 B 的写法。

### M2：AD-9 只定了门禁，没定重绑定方法，不同单元会选出互相冲突的方法

- **源码事实**：`proxmox-lxc/main.tf` 第 81–92 行的 `ignore_changes` 只包含 description 和 user_account；`fileserver.tf` 声明的是 `nvme-lvm` 卷和 900G；`ubuntu-2604.tf` 绑定 `cloud_image` provider 和 `target_node = "pve0"`，伴生资源是 download_file 和 ansible_host。
- **对抗构造**：单元 A 为了让 CT111 的计划不出现 replace，在**共享模块** `proxmox-lxc` 里加 `ignore_changes = [mount_point, operating_system]`，结果把所有使用该模块的其他 LXC 的漂移也一起隐藏了。单元 B 对同一资源做 `state rm` 后改为手工 ownership。两种做法都满足"定向计划无意外创建/销毁/替换/启动"，但仓库的最终状态互相冲突，而且单元 A 的改动影响了范围外的单元。
- **修复**：AD-9 增加方法的优先序，例如：先尝试 import 或 `moved` 加定向计划；不行就把该资源退出 state，改为登记手工 ownership；**禁止为了迁移修改共享模块的 lifecycle**。VM108 跨 provider 的绑定也按同一顺序处理。

### M3：CT111 备份模式与"含快照的 quota"相互作用，没有决定

- AD-5 规定 quota 计入快照。`runbook.md` §7 的新 PBS 作业没有规定 CT111 用什么模式。PVE 作业默认 snapshot 模式，会在 ZFS 上创建快照。
- 备份期间 TM 写入的覆盖块会被快照保留并计入 quota；vzdump 失败遗留的快照会长期占用 quota，导致 TM 撞上 ENOSPC。
- T0/T1 用的是 stop 模式，不受影响（已处理）。
- **修复**：AD-5 增加"CT111 常规备份模式与快照余量"规则：要么用 stop 模式或固定窗口，要么把快照峰值纳入 H4 的余量，并把遗留 vzdump 快照列为监控和停止项。

### M4：AD-3 依赖的代码没有出现在 Stack 中，核验的节点也和执行节点不一致

- `destroy_config` 和 `lock_config` 位于 `PVE/AbstractConfig.pm`，属于 libpve-guest-common-perl。`preflight-evidence.md` 第 25 行只核验了 **pve0** 上的这个文件，但 retire 在 **pve1** 上执行。
- Stack 只列了 pve0 的 storage、qemu-server、container 版本，没有 pve1 的版本，也没有 guest-common 和 pve-cluster。
- **修复**：Stack 增加两节点的 `libpve-guest-common-perl`、`pve-cluster`、`qemu-server`、`pve-container` 版本，并把"两节点版本一致"作为 AD-3 演练有效的前提。

### M5：同一节点上的孤立源卷与新目标卷同 ID 共存（VM108 的 R1 返回 pve0）

- `validation-and-rollback.md` R1 表：在 pve0 上退下源 ID108 的注册后，执行 `qmrestore … 108 --storage vmdata`。被 AD-6 保留的原 `vm-108-disk-*` 会以孤立卷形式和新卷待在同一个 vmdata 上。
- 之后任何 `qm rescan`/`qm disk rescan` 都会把原盘作为 unusedN 挂到新的 108 上。再执行"移除 unused"一类操作，就会误删回退盘。AD-6 只禁止了按 VMID 批量删除，没有禁止 rescan 自动挂载。
- 这次 T1 恢复也没有计入 AD-5 的 vmdata 预算。余量估算能吸收，但账本上没有体现。
- **修复**：AD-6 增加"同一节点存在同 ID 的保留孤立卷时禁止 rescan"。VM108 的 R1 列入 vmdata 回退账本。

### M6：AD-11 的分流条件与配套文件不一致

- AD-11 以"开写前/开写后"分流。`solution-design.md` 第 73 行和 `validation-and-rollback.md` 以"业务新写入"分流，并明确说明隔离启动也可能产生新写入。
- 一个逐字遵守 AD-11 的单元，会把隔离验证期间的写入（例如 CT118 在隔离状态下 compose start）当作"未开写"，直接走 R0。配套文件则要求记录这些写入并判断是否走 T1。
- 大多数来宾的隔离写入只是验证产物，丢弃风险低；但 VM108 在生产 IP 下验证（见 H1）就不是这样。
- **修复**：AD-11 改为以"目标首次启动"为分界；之后的 R0 必须附带"无业务新写入"的书面判定。

### M7：驱动 SPEC 的配套文件与 spine 矛盾，两份回退依据并存

- `acceptance.md` 第 38 行写"回退遵循migration-plan.md"。`migration-plan.md` 第 48 行写"同集群迁移：成功后源盘通常被移除，回退依赖反向迁移或迁移前备份"；第 4、5 步写的是 migrate 路径；第 41 行给 fileserver 1–3h 窗口。Spine 的 AD-2/AD-6 和 `solution-design.md` 已经把这些推翻了。
- 一个单元按 SPEC 的验收链执行回退，另一个按 spine 执行，两者的方法和停机窗口都不同。
- **修复**：向 SPEC 提交变更请求，把 acceptance 的回退依据改为指向 `validation-and-rollback.md`，并修订 migration-plan 中的方法和窗口。Spine 的方向没有错，问题在于 SPEC 尚未对齐。

---

## Low

- **L1**：`solution-design.md` 第 48 行写"容量允许时reservation=800GiB"（有条件），`runbook.md` 第 158 行无条件设置，第 163 行写失败即停止。另外，不设 reservation 时，AD-5"接近底线暂停 TM"才有效果；设了 reservation 时，TM 的增长发生在预留空间内，暂停 TM 对 rpool 底线没有帮助。需要选定一个口径。
- **L2**：AD 的状态标签不一致（见机械检查）。
- **L3**：`AGENTS.md` 写的是 telmate provider，源码 `versions.tf` 是 `bpg/proxmox 0.70.0`。Spine 的 Stack 与代码一致（正确）。AGENTS 的过时描述不在本轮范围内，只作记录。
- **L4**：`runbook.md` §2 的小 VM 临时 ID 试恢复会占用 vmdata，没有列入 AD-5 预算。AD-5 的"恢复前/后刷新字节账本"能发现，但最好显式列出。

---

## 已处理的路径（不计为缺失）

- 禁止对已占用的 VMID 使用 force 恢复，禁止用 destroy 代替退注册：AD-3、`solution-design.md` 技术取舍表、附录 A。
- CT111 显式指定每个挂载点、未知 unused0 原样保留：`runbook.md` §6，`preflight-evidence.md` 第 27 行。
- 源 thin pool 回退空间不足时的 A/B/C 分支，以及 B 分支对精确 volid 的授权：`validation-and-rollback.md` 第 89–104 行（多来宾累计问题见 H2）。
- T0/T1 用精确 volid 选取：`runbook.md` §0/§3。
- 网络栅栏覆盖全部 netX，有直通设备时停止：附录 C。
- 冻结两节点相关自动化：AD-1；源/目标跨节点没有全局锁，只能单一操作者串行，并已明确说明：`runbook.md` 第 244 行。
- pve1 保留集群成员和见证、不降票：AD-10，与 QDevice 文档一致。
- 禁止在 rpool 上同时存放两份 fileserver 数据：`runbook.md` §2，`solution-design.md` 第 54 行。

---

## 尚未执行的演练和准入条件（与决策缺口分开列）

下列各项都是**已决定、已设门禁、但尚未满足**的条件，不是决策缺失。不能把它们当成已验证的结果：

1. AD-3 内部 API 的退注册/恢复/撤回演练：标记为 `[ASSUMPTION]`，未验证前禁止进入切换。门禁处理正确。缺的只是演练失败后的备选方案（Deferred 里只写了"修订方案"），可作为待定事项。
2. PBS 可达性、剩余空间（约 2632GiB 加元数据）和读取凭据：当前 No route to host。
3. pve2 的版本、CPU、32GiB 启动余量、VMID108、vmbr0、pve2-ssd 容量：SSH 超时。
4. CT111 lost+found 的宿主离线核验、ID 映射、ACL/xattr 可比性：当前有权限错误。
5. 附录 B/C 工具只是文档草稿，尚未审阅或演练。
6. 吞吐实测和窗口重算（6–12h 是估算）。
7. Spine 的 rubric/一致性评审和外部编辑评审：Deferred 中写明尚未执行、不计为通过。本报告只覆盖一致性这一角色。
8. 第 23 行 VM108 的"四个容器在运行"、pve0 的 ZFS 健康状态都是本轮只读观测结果，实施前需要刷新。

---

## 好 spine 清单逐项核对

| 检查项 | 结果 |
|---|---|
| 下一层的真实分歧点是否都已固定 | **否**：H1–H5、M1–M3 |
| 每条 Rule 是否可执行，且确实能防住它声明的分歧 | 大部分可以。AD-1（轮流运行）、AD-5（只管存储且所有者不唯一）、AD-11（分流条件）不足 |
| Deferred 中是否有项会导致分歧 | 没有直接导致分歧的项。AD-3 演练失败后的备选方案应作为待定事项 |
| 命名的技术是否经过当前核实 | pve0 已核实；pve1 和 guest-common 未核实（M4） |
| 是否认可而非违背 brownfield 现状 | 与 Terraform 代码一致；与 Ansible 的 1T 变量冲突，且没有处理（H4） |
| 是否覆盖 SPEC 的能力 | 已映射；SPEC 配套文件需要反向对齐（M7） |
| 运营和环境维度 | 存储、网络、集群已覆盖；**内存和计算维度完全没有 AD**（H5） |

---

## 建议的 AD 修订文本（供作者采纳，本轮未修改 spine）

- **AD-1（收紧）**：…另外，每个身份在任何时刻只有一条权威谱系。目标首次启动后，源副本必须施加有记录的启动屏障（netX 加 `link_down=1` 加 tag，或退注册）。
- **AD-5（收紧）**：…CT111 容量的所有者：ZFS `quota`/`reservation` 由变更单拥有；PVE mp0 的 `size` 等于 `refquota`；Samba 报告上限由 Ansible 拥有，并且必须满足"硬限额 − 快照/元数据余量 ≥ 报告上限"。迁移期间禁止任何单方面改动这些值。
- **AD-6（收紧）**：…T0/T1 在 verify 通过后标记 protected；作业的 retention 不得覆盖它们；同一节点存在同 ID 的保留孤立卷时禁止 rescan。
- **AD-11（收紧，Binds 补上 CAP-2、CAP-3）**：以目标首次启动为分界；之后走 R0 必须附带"无业务新写入"的书面判定。
- **AD-13（新增）**：回退容量按 node/pool 累计认领，data 和 metadata 分别设阈值，超出部分降为 C 分支。
- **AD-14（新增）**：内存峰值准入。并发运行来宾的配置内存加 ARC 上限加宿主保留不得超过物理内存减余量；VM116 验证和全量清单遍历不得与其他高内存验收并发。
- **Conventions（新增一行）**：PBS 恢复点身份为 `datastore/namespace/type/ID/owner`，pve2 使用独立 namespace。

---

## 简要结论

- **判定**：不通过，需修订。骨架正确，但有 5 组 High 级对抗漏洞，必须先用新增或收紧的 AD 关闭；当前没有任何部署准入。
- **最重要的问题**：
  1. **H1**：VM108 的源副本保持完整注册且无限期保留，AD-1 只禁止同时运行，不禁止轮流运行，会产生两条分叉谱系；AD-11 也没有覆盖 CAP-2。
  2. **H2**：各来宾的 A 分支回退认领同一个 thin pool 的空闲空间，多来宾回退时可能写满 pool，连被保留的原盘一起出错。
  3. **H3**：T0/T1 不受新 PBS 作业 retention 的保护；pve0 和 pve2 的 `vm/108` 组身份不唯一。
  4. **H4**：CT111 的 ZFS 800G、Samba 报告 800G、Ansible 变量 1T、Terraform 900G 四方共管，而且报告上限 ≥ 硬限额，会让 TM 撞上 ENOSPC。
  5. **H5**：pve0 的内存峰值（69/85GiB 对 62.6GiB，无 swap）没有任何 AD 约束，OOM 会危及来宾数据完整性。
- **另有 7 个 Medium、4 个 Low**，均已写在上文完整报告中。
- **执行限制**：`lint_spine.py` 没有运行，HTML 和 `reviews/` 文件没有生成，原因都是只读权限；没有缺失输入，也没有权限失败。
