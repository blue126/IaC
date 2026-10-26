# architecture-rubric

输入版本：本次architecture阶段固定快照；请求模型 claude-opus-5-5。CLI返回码 0。

# 架构 Rubric 评审报告：Proxmox 整合迁移

- **角色：** architecture-rubric（Reviewer Gate 中的 rubric walker，Validate 意图：只报告，不修改 spine）
- **主目标：** `_bmad-output/planning-artifacts/architecture/architecture-IaC-2026-10-25/ARCHITECTURE-SPINE.md`
- **同时评审：** 4 个 companion（`solution-design.md`、`runbook.md`、`validation-and-rollback.md`、`preflight-evidence.md`）；驱动规格 `specs/spec-proxmox-consolidation/`（`SPEC.md`、`brownfield.md`、`migration-plan.md`、`acceptance.md`）；`AGENTS.md`；`docs/architecture/proxmox-qdevice-architecture.md`；brownfield 代码 `source/terraform/proxmox/{ubuntu-2604,fileserver,pdm,pbs,provider,versions}.tf`、`source/terraform/modules/proxmox-cloud-image-vm/{main,variables}.tf`、`source/terraform/modules/proxmox-lxc/main.tf`
- **建议的落盘路径：** `{doc_workspace}/reviews/review-architecture-rubric.md`。我只有只读权限，没有写这个文件，由主机负责保存。

---

## 0. 执行边界与缺失项

| 项 | 状态 |
|---|---|
| `uv run {skill-root}/scripts/lint_spine.py` 确定性检查 | **没有执行。** 本次只读，不允许运行代码，`skill-root` 也不在授权范围内。我改为人工做了机械检查：AD-1…AD-12 编号唯一；每条都有 Binds/Prevents/Rule；没有占位符；Stack 都写了具体版本。人工检查**不能代替** lint 的结果。 |
| `{workflow.finalize_reviewers}`、其他 lens 及 HTML 汇总 | 不属于本角色。我没有读其他审阅者的输入或报告，也没有生成 HTML。 |
| 权限失败 | 无。所有读取都在授权目录内完成。 |
| 输入缺失 | 无。spine、4 个 companion、SPEC 及其 companion、项目规则、QDevice 文档和相关 brownfield 代码都已读到。 |

---

## 1. 结论

**Spine 的主路线是对的：冷备份恢复、保留源盘、单一写入者，加上 T0/T1 回退。但还有 4 个高优先级的决策缺口，修订前不能进入实施准入。** 这 4 个缺口是：内存准入、Time Machine 配额余量、PBS 与 pve2 处于同一故障域、IaC 重绑定机制。没有发现 Critical。各项"未执行的演练/前置条件"都已经被红线正确拦住，下面单独列出，不算作缺陷，也不算作已通过。

---

## 2. 已正确处理、不算缺陷的部分

下面这些我核对过，处理得当：

- **vmdata 峰值：** 准入不计入 VM108 释放的空间。672.46 − 336 ≈ 336.46 GiB，大于 128 GiB 余量。336 的拆分（VM 284 + CT 32 + 预留和舍入）和 `migration-plan.md` 的磁盘表对得上。SPEC 里"释放 108 后约 450GiB"被明确作废（`solution-design.md` 字节容量账本一节）。
- **rpool 账本：** 800 + 64 < 878.02，只剩约 14 GiB 弹性，文档已写明。64 GiB 是运营停止线，不是硬预留，这个语义区分清楚。没有本地 tar 暂存，也不同时放两份 681 GiB（runbook §2、§6）。
- **CT111 恢复：** 显式映射全部 rootfs 和 mp，依据是 `preflight-evidence.md` 引用的 pct advanced restore 行为。不缩源盘 ext4，不使用 force。
- **unused0 无效记录、lost+found 权限错误：** 不清理，不当成"空目录"，转到宿主离线核实（AD-6；`validation-and-rollback.md` 完整性证据一节）。
- **完整性口径：** 覆盖全路径、SHA256、UID/GID、mode、ACL/xattr、硬链接组和稀疏文件，并明确要求源和目标的 ID 映射一致（AD-7、附录 B，包括 ACL 原始值的限制说明）。
- **单一身份：** 不用 destroy；全局 VMID 检查用 `get_vmlist` 而不是单节点 `qm list`；禁止按 VMID 扫描删除，也禁止 `destroy-unreferenced-disks`（AD-3、AD-6，回退收尾一节）。
- **T1 回退：** 按 A/B/C 三个分支在开放写入前选定。B 分支只针对确切 volid，需要单独授权，并写明不可逆边界。CT111 不默认走 A 分支（R1 精确恢复映射一节）。
- **QDevice：** 保留 pve1 成员身份和见证；关机前验证 pve0 能拿到见证票，不降票（AD-10，与 QDevice 文档的"不要同时维护 N100"一致）。
- **VM108：** 运行中的 containerlab 负载已经实测（preflight），在 AD-8 中处理。
- **窗口：** SPEC 的 1–3h 被 6–12h 取代，并要求用演练吞吐重算。

---

## 3. 未执行的演练/前置条件（不计为通过，也不判为缺陷）

以下条件都被 runbook 红线拦住，处理方式正确，但**都还没完成**：

1. pve2 不可达：版本、CPU、32 GiB 余量、VMID108、vmbr0、pve2-ssd 都没核实。
2. PBS 不可达：容量（约 2632 GiB 无去重预算）、namespace/owner、verify 和 file-restore 能力都没核实。
3. AD-3 同 ID 退注册→恢复→回退的合成 guest 演练，以及单独批准，都没做。AD-3 自己标注为 [ASSUMPTION]。
4. 正式备份的试恢复没做；CT111 只能做"块校验 + 代表性提取"，不是全量 DR 演练（runbook §2 已写明边界）。
5. CT111 宿主离线完整清单没做：lost+found 实情、lxc.idmap、ACL/xattr 可比性。
6. 附录 A、B、C 三个工具都只是文档草稿，没审阅也没演练。
7. 回源容量账本（thin data/metadata）没算，A/B/C 分支没选定。
8. 吞吐没实测，窗口没定。
9. 私有证据还在临时目录，没转存到持久位置。
10. 外部评审没完成，状态保持 draft（AD-12）。

---

## 4. 发现（按严重度）

### HIGH-1：内存准入整个维度缺失，临时启动可能让 pve0 上的生产 guest 被 OOM

- **依据：** AD-5 只管存储。`brownfield.md` 记录 pve0 物理内存约 62.6 GiB、无 swap，迁后常开 guest 配置 69 GiB，加 Windows 为 85 GiB。runbook §7 只说"不承诺满配"。验收中 VM116 要"短暂开机验证"，顺序排在第 7，此时 112–118 都已在运行。CT118 和 VM115 是内存大户。ZFS ARC 在 pve0 上管两个池，上限未知。
- **为什么是缺口：** 没有任何 AD 或停止线规定"启动前要有多少可用内存"。OOM killer 可能杀掉 OpenBao、HA 或 fileserver 的进程，或者整台 QEMU，这会伤到已经切换完成的"唯一写入者"，是数据完整性风险。这属于 altitude 应该管的运营维度，spine 一字未提。
- **修复（autofix/discuss）：** 新增一条 AD（或扩展 AD-5）："任何启动（含隔离验证）前，`MemAvailable` ≥ 该 guest 配置内存 + 固定余量（例如 8 GiB）；ARC 上限需记录和核实；PSI 或 OOM 出现即停止。VM116 要么在其他常开 guest 恢复之前验证，要么暂停非关键 guest 后再验证。"把 pve0 的 ARC 上限、实际占用基线和 pve2 的余量（见 HIGH-3）都写进准入证据。

### HIGH-2：ZFS 硬配额 800G 和 Samba 的 Time Machine 上限 800G 相等，没留余量，Time Machine 可能遇到 ENOSPC 而不是正常修剪

- **依据：** AD-5 写"live 加 snapshots 总 quota 不超 800GiB"；runbook §6 执行 `zfs set quota=800G refquota=800G`。preflight 和 brownfield 记录 Samba `fruit:time machine max size=800G`，这是报告值，不是硬限制。源端是 900 GiB ext4 配 800G 报告上限，实际有约 100 GiB 缓冲；目标端缓冲变成 0。
- **为什么会出问题：**
  - Samba 按 sparsebundle 的 band 大小汇报用量；ZFS 的 quota 还算上元数据、xattr（`streams_xattr`）和快照。
  - 迁后 PBS 作业对 ZFS 上的 CT 如果用 snapshot 模式，快照在备份期间累积的旧块也计入 `quota`。
  - 结果是 macOS 还在等 Samba 报告"满"再修剪旧备份，ZFS 已经先拒绝写入。中途 ENOSPC 可能损坏 sparsebundle，CAP-4 要保护的正是这些历史。
- **修复（discuss，因为涉及保留历史长度）：** 二选一并写进 AD-5：
  - (a) Samba 上限 < ZFS quota，并留出固定余量，例如 Samba 降到约 760G；需要用户接受历史保留期会变短。
  - (b) 保持 Samba 800G，把 `quota`（不是 `refquota`）提高到 800 + 余量。但这会侵蚀 rpool 只有 14 GiB 的弹性，需要重新做准入。

  另外，迁后备份作业必须规定 CT111 的备份模式和快照余量，或者明确用 stop 模式。观察期加一项：Time Machine 修剪行为和 ENOSPC 日志检查。

### HIGH-3：PBS 实际是 pve2 上的 VM，spine 把它画成独立恢复点，没有建模共享故障域和资源争用

- **依据：** brownfield 代码 `source/terraform/proxmox/pbs.tf:1-21` 显示 PBS 是 `pve2/100`，内存 16 GiB，datastore 用直通的 HBA 和 SSD。spine 的 Structural Seed 把 PBS 和 P2 画成两个独立节点。preflight 里 "pve2 .52 SSH 超时"和 "PBS .249 No route" 很可能是同一个原因，但被当成两个问题。
- **影响：**
  1. **回退可行性：** 全部 T0/T1 都依赖 pve2 这一台宿主。T1 回退、"pve0 失效/无法取 T1"这类场景，实际就是"pve2 一出问题，所有 guest 同时失去恢复点"。
  2. **资源争用：** pve2 要同时承载 PBS（16 GiB）、VM108 验证启动（32 GiB）和 PBS 读写。preflight 只核"32GiB 启动余量"，没要求把 PBS 的占用和 ARC 计进去。
  3. **IaC 风险：** `pbs.tf:4-5` 的注释写明 bpg 0.70.0 改 agent、boot 等字段时可能重启正在运行的 VM。VM108 重绑定用的是 pve2 provider，误 apply 可能在迁移中途重启 PBS。
- **修复（autofix + discuss）：**
  - Structural Seed 和 Consistency Conventions 改成 `pve2 ⊃ PBS(VM100)`。
  - AD-11 或 Deferred 写明"T0/T1 与 VM108 目标同在 pve2 故障域；进入 CT111 阶段前 PBS datastore 健康必须通过（zpool/SMART/verify）"。
  - pve2 内存准入 = PBS + VM108 + ARC + 余量。
  - 需要用户决定是否接受"没有第二份离机恢复点"；如果不接受，要另找恢复目标。

### HIGH-4：AD-9 只有门禁，没有选定重绑定机制，而现有模块的结构默认会产生替换

- **依据：**
  - `ubuntu-2604.tf:21-45`：`target_node="pve0"`，`storage_pool` 用变量。模块 `proxmox-cloud-image-vm/main.tf:9-17` 的 `download_file` 绑定节点，`disk.file_id` 引用它（:75-81）。`variables.tf` 中 `started` 和 `on_boot` 默认 true，`network_mac_address` 默认 null。
  - `fileserver.tf:8-29`：`target_node="pve1"`、`rootfs_storage="local-lvm"`、`mount_points` 为 `nvme-lvm:vm-111-disk-0` / `900G`。LXC 模块的 `ignore_changes` 只有 `description` 和 `user_account`（`proxmox-lxc/main.tf:81-92`）。
  - `pdm.tf:11,23`：`pve1`、`local-lvm`。
- **为什么是缺口：** 改 node、datastore、file_id、mount_point 的 volume/size（900G→800G）时，bpg 很可能计划成 replace 或迁移，需要用 plan 实测确认。AD-9 规定"定向计划无意外创建/销毁/替换/启动"，这能拦住错误，但没告诉实施者**该用哪条路径**通过：
  - `removed{}` + `import{}`；
  - `state rm` + import；
  - `lifecycle.ignore_changes`（`disk[0].file_id`、`download_file`）；
  - 或者把 VM108 移出 Terraform ownership。

  这正是两个执行者会各走各路的分歧点。CT111 一旦被误判为可以 replace，就会丢数据。
- **修复（discuss→写进 AD-9）：** 固定一种机制，例如"对已迁 guest 使用 `removed{lifecycle{destroy=false}}` + `import{id="<node>/<vmid>"}`；模块增加对 `download_file` / `file_id` 的 ignore 或解耦；CT111 的 `mount_points` 写成目标真实 volid 和 800G；VM108 显式写 `started=false`、`on_boot=false`、`network_mac_address`。"同时把"in-place update 可能重启运行中 VM"（`pbs.tf:4-5`）列入 AD-9 禁止的意外结果，不只是"启动"。

### MEDIUM-1：AD-3 的 destroy_config 行为是在 pve0 上读代码验证的，但 retire 实际在 pve1 上执行；Stack 没记 pve1 的包版本

- **依据：** preflight 只读核验的是 pve0 的 `AbstractConfig.pm`；runbook §5 的 retire 和 R0 的 restore 都在源 pve1 上运行。Stack 只列了 pve0 的 libpve-storage、qemu-server 和 pve-container 版本；`brownfield.md` 写着"包版本仍须复核"。
- **修复（autofix）：** Stack 补上 pve1 的 `qemu-server`、`pve-container`、`pve-cluster`、`libpve-guest-common` 版本和模块 SHA256（preflight 称已私有采集）。AD-3 的 Rule 加一句："演练与执行节点的包版本和所用模块哈希必须一致，否则视为未验证。"

### MEDIUM-2：spine 与驱动 SPEC 存在实质偏离，但没有把"先修订 SPEC"列为待办

- **依据：**
  - `migration-plan.md` 第 4、5 步隐含使用同集群 migrate；
  - "回退与保留"一节说"成功后源盘通常被移除"；
  - fileserver 窗口 1–3h；
  - 容量"约 450GiB"。

  spine 和 solution-design 用有据可查的理由推翻了这些内容，方向是正确的，但 SPEC 自己规定"候选方案若不受支持，先修改本规格再实施"。
- **修复（defer→open items）：** 在 Deferred 或 Open Questions 加一项："SPEC/migration-plan 须按冷备份恢复路线、保留源盘、6–12h 窗口和 336GiB 账本修订后才能实施准入。"

### MEDIUM-3：pve0 rpool 是单盘，且有历史写错误，迁后会成为 Time Machine 数据唯一的在线副本；spine 没把它列为耐久性准入条件

- **依据：** `brownfield.md` 写明 local-zfs 是单块 SA510、没有镜像；QDevice 文档提到"未修复 pve0 的 SATA/WRITE 错误""pve0 私有快照还处于已报告错误的 rpool 上"。runbook §1 已经要求 smartctl 并"不因 ONLINE 忽略"，这部分**已处理**；但 spine 本身没有相应规则，源盘清理之后也没有耐久性要求。
- **修复（autofix）：** AD-5 或 AD-6 增加两条：
  - "rpool 健康（SMART/历史错误解释）是 CT111 切换的准入项；"
  - "源 CT111 卷的清理授权以'迁后 PBS 作业已对 CT111 数据盘完成并 verify 至少一次'为前提。"

### MEDIUM-4：附录 C 网络栅栏只检查配置值，没检查实际断链；LXC 的 `link_down` 是否支持需要在演练中确认

- **依据：** `fence.py` 只断言配置里有 `link_down=1`。CT111 和 CT118 的首次隔离启动完全依赖这个栅栏，来防止目标和生产客户端（包括两台 Mac）建立连接。
- **修复（autofix 到演练清单）：** 演练要求做实际效果验证：在 guest 内看 `ip link` 状态为 down 或 no-carrier，宿主侧 tap/veth 状态一致，并在生产网段做一次 ARP/ping 负向测试。如果 pve-container 9.0.x 不支持 LXC 的 `link_down`，就改用其他隔离方式（例如临时改桥到无上联的隔离桥），并写入方案。

### LOW-1：VM 只做了功能验证，没做块级完整性比对

- **依据：** AD-7 的逐项比对只覆盖 CT111 和 CT118。VM 盘的完整性依赖 PBS verify 加功能验收。由于源盘保留且停机，可以低成本做源 LV 和目标 zvol 按源字节长度的 SHA256 比对（含 EFI、TPM 盘）。
- **修复：** 写进 `validation-and-rollback.md` 的 VM 部分，作为可选强证据；盘大于 100 GiB 时计入窗口。

### LOW-2：R1 回源恢复表中的 VM 命令缺少 onboot=0 归一化

- **依据：** `validation-and-rollback.md` R1 表里 VM 用 `qmrestore … --unique 0`。T1 来自已经开放写入的目标，配置里 onboot=1；CT 行显式写了 `--onboot 0`，VM 行没有。runbook 正向流程有 `qm set --onboot 0`。
- **修复：** 每个 VM 行后加 `qm set "$VMID" --onboot 0`，验收后再恢复成原来的常开策略。

### LOW-3：reservation 的写法前后不一致

- solution-design 写"容量允许时 reservation=800GiB"，runbook §6 无条件设置。建议统一成：无条件设置，失败即停止（与 runbook 一致）。

### LOW-4：能力映射表小缺漏

- CAP-2（VM108）的回退（AD-11 中的 VM108 跨节点 T1）没列进 "Governed by"。建议改成 `AD-1,2,8,9,11`。

### LOW-5："Named tech verified-current" 有一项不完整

- bpg/proxmox 0.70.0 是仓库锁定版本，沿用 brownfield 是对的。但 `pbs.tf` 已经记录了它的已知缺陷（in-place 更新会重启 VM），Stack 或 AD-9 应引用这一条。
- PBS 和 pve2 的版本已列入 Deferred，这部分已处理。

---

## 5. 逐项对照 good-spine checklist

| 检查项 | 结论 |
|---|---|
| 是否固定了下层的真实分歧点 | 大部分固定了。缺 3 个：重绑定机制（HIGH-4）、内存准入（HIGH-1）、TM 配额余量（HIGH-2）。 |
| 每条 AD 的 Rule 是否可执行、能否防住所述分歧 | AD-1/2/4/6/7/8/10/11/12 可执行。AD-3 正确标为 ASSUMPTION 并加了门禁。AD-5 有余量盲点（HIGH-2）。AD-9 只有门禁、没有路径（HIGH-4）。 |
| Deferred 里有没有会导致分歧的项 | 没有危险项；4 项都是准入门禁或授权项。建议补上 SPEC 修订（MEDIUM-2）和 PBS 故障域（HIGH-3）。 |
| 技术是否核实为当前版本 | pve0 已核实；pve1 包版本缺失（MEDIUM-1）；pve2/PBS 已延期。 |
| 是否与 brownfield 一致 | 存储、配置和 QDevice 一致。PBS 拓扑与 `pbs.tf` 矛盾（HIGH-3）；与 IaC 模块结构的冲突没处理（HIGH-4）。 |
| 是否覆盖 SPEC 能力 | CAP-1…6 都映射到了。与 SPEC 在方法和窗口上的偏离需要回写 SPEC（MEDIUM-2）。 |
| 父 spine | 无（不适用）。 |
| 运营/环境维度 | 部署、回退、授权、密钥、时区都已处理。**内存和计算容量这一维度完全没写**（HIGH-1）。监控只在验收文件里，可以接受。 |

---

## 6. 汇总（按 Gate 要求的紧凑格式）

- **结论：** 主路线正确，未执行的前置条件都被正确拦住；但有 4 个 HIGH 决策缺口，修订前不能进入实施准入。没有 Critical。
- **最重要的 4 条：**
  1. **HIGH-1 内存准入缺失：** pve0 无 swap，配置内存 85 GiB > 物理 62.6 GiB。VM116 临时验证时可能 OOM 掉已切换完成的 guest。需要补启动前 `MemAvailable` 余量规则和 VM116 的验证顺序。
  2. **HIGH-2 TM 配额无余量：** ZFS quota 800G 等于 Samba 800G，快照也计入 quota，ENOSPC 会先于 Time Machine 的正常修剪发生，可能损坏 sparsebundle。需要在"Samba 上限 < quota"和"提高 quota 并重做准入"之间选一个。
  3. **HIGH-3 PBS 就在 pve2 上：** `pbs.tf` 显示 PBS 是 `pve2/100`，T0/T1 和 VM108 目标在同一故障域且争用资源，spine 图画错。需要修正拓扑，把 PBS 健康和 pve2 合计内存纳入准入。
  4. **HIGH-4 AD-9 没定重绑定机制：** 现有模块（`download_file`/`file_id`/`node_name`、fileserver 900G 的 mount_point）默认会产生 replace。需要固定 `removed`+`import` 或 `ignore_changes`，或者移出 Terraform ownership 中的一种。
- **其余 4 条 MEDIUM 和 5 条 LOW：** 见上文第 4 节，包括 AD-3 在 pve1 上的版本校验、SPEC 回写、rpool 耐久性、栅栏实际效果、VM 块级哈希、R1 中 VM 的 onboot、reservation 写法、CAP-2 映射、bpg 缺陷引用。
- **报告文件：** `{doc_workspace}/reviews/review-architecture-rubric.md`（由主机落盘；本次只读，没写入；lint 也没运行）。
