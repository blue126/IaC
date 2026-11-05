# pve0 内存与 ARC 设计

本文回答一个问题：pve0 的 ZFS ARC 能否从约 3.1 GiB 扩到 8、12 或 16 GiB，要先做什么。文中候选值都没有批准为生产配置。实施步骤见 [实施手册](../guides/pve0-memory-rollout.md)。

**结论（2026-11-05 快照）**：现在不能直接扩 ARC。按当前快照推算，ARC 涨满 8 GiB 后宿主只剩约 7.8 GiB，已低于 8 GiB 的准入线；12 GiB 低于 4 GiB 的停止线；16 GiB 为负数。应先采样，再试点 balloon，然后才讨论 8 GiB。

## 证据与解释边界

本文的数字来自两次手工只读采样：2026-10-26 和 2026-11-05 08:34 UTC。快照只说明当时的状态，不代表峰值，也不保证下一次启动、照片处理或备份时仍相同。没有连续日志；原始输出只在会话工具记录里，后续必须生成带时间戳的重复采样证据。

GiB = 2^30 bytes；配置中的 1024 MiB = 1 GiB。API 的 `mem`/`memhost`、guest 内 `used`、QEMU RSS 和宿主 `MemAvailable` 口径不同，不能直接相加或相减推出应用工作集。

| 项目 | 2026-10-26 | 2026-11-05 | 口径 |
|---|---|---|---|
| MemTotal | 65679612 KiB = 62.64 GiB | 同左 | 宿主物理可见内存 |
| MemAvailable | 17114268 KiB = 16.32 GiB | 13356948 KiB = 12.74 GiB | 单次可用估计 |
| ARC size | 约 3.07 GiB | 3324262368 bytes = 3.10 GiB | 实际占用，已贴近上限 |
| ARC c_max | 3348103168 bytes = 3.118 GiB | 同左 | 有效上限 |
| ARC c_min | 2101747584 bytes = 1.957 GiB | 同左 | 有效下限；参数 zfs_arc_min=0 表示默认选择，不是零下限 |
| 持久化 ARC | options zfs zfs_arc_max=3348103168 | 同左 | /etc/modprobe.d/zfs.conf，文件日期 2025-11-24 |
| 宿主 swap | 0 | 0 | 宿主没有 swap |
| memory PSI | avg10/60/300 均为 0 | 同左 | 单次压力快照 |
| PVE | 9.0.3 | 9.0.3，内核 6.14.8-2-pve | `pveversion` |

pve0 已运行 26 天，本次启动晚于 `zfs.conf` 的修改日期，且 c_max 等于该值。这与“持久化配置在重启后生效”一致，但没有直接观察过启动过程。

两次快照之间 MemAvailable 少了约 3.6 GiB。同期变化有 n8n 从 LXC 改为 VM 106、新增 VM 116 remotecc-ops（当前 memhost 分别约 2.85、2.92 GiB）。这是时间上的对应，不是已证明的因果。

| pve0 VMID / 名称 | 配置上限 GiB | `balloon` 配置 | memhost GiB | Terraform 归属 |
|---|---:|---|---:|---|
| 101 Immich | 8 | 等于上限 | 7.48 | terraform/proxmox/immich.tf |
| 102 RustDesk | 4 | 等于上限 | 2.50 | terraform/proxmox/rustdesk.tf |
| 104 NetBox | 4 | 等于上限 | 3.42 | terraform/proxmox/netbox.tf |
| 106 n8n | 4 | 未设置 | 2.85 | terraform/proxmox/n8n.tf |
| 109 MCP Gateway | 4 | 等于上限 | 3.53 | terraform/proxmox/mcp-gateway.tf |
| 112 OpenBao bao | 4 | 等于上限 | 0.63 | terraform/proxmox/openbao-testbed.tf |
| 113 OpenBao control | 4 | 等于上限 | 0.52 | terraform/proxmox/openbao-testbed.tf |
| 114 Home Assistant | 4 | 0，关闭 | 3.70 | 无 Terraform 声明 |
| 115 FunASR | 12 | 0，关闭 | 8.88 | 无 Terraform 声明 |
| 116 remotecc-ops | 4 | 等于上限 | 2.92 | terraform/remotecc/remotecc-ops.tf |
| 117 PDM | 4 | 等于上限 | 1.05 | terraform/proxmox/pdm.tf |
| 合计 | 56 | | 37.48 | 8 + 9×4 + 12 |

模板 9000 停止，不计运行预算。

| pve0 LXC VMID / 名称 | 配置上限 GiB | 单次 API mem GiB | Terraform 归属 |
|---|---:|---:|---|
| 100 anki-sync-server | 2 | 0.55 | terraform/proxmox/anki.tf |
| 103 Homepage | 4 | 0.26 | terraform/proxmox/homepage.tf |
| 105 Caddy | 0.5 | 0.04 | terraform/proxmox/caddy.tf |
| 107 Jenkins | 2 | 1.29 | terraform/proxmox/jenkins.tf |
| 111 Fileserver | 0.5 | 0.11 | terraform/proxmox/fileserver.tf |
| 118 Hindsight | 8 | 3.24 | 无 Terraform 声明 |
| 合计上限 | 17 | 5.49 | 2 + 4 + 0.5 + 2 + 0.5 + 8 |

上表各 mem 值不是严格同一时刻，不能当成宿主总用量。全部 guest 运行中，本次无锁。

pve1 无 guest，集群当前只有 pve0 一个节点在线，靠 QDevice 保持法定票数。

主池 mainpool 是两块 Samsung 990 PRO 的 ZFS mirror，存储 ID `vmdata`；系统盘 rpool 也是 ZFS，存储 ID `local-zfs`。

本次把 `terraform/proxmox` 的 HCP state 与现场逐台比对：pve0 上所有已声明 guest 的内存上限、balloon 与 swap 都和现场一致。PDM 和 CT111 的 pve0 迁移已在 `main` 的源码和 state 中落地。

`terraform/proxmox/jenkins-agent.tf` 声明了 pve0 上的 LXC 110（2 GiB），但 state 和现场都没有它。这笔待创建资源一旦 apply，配置上限再加 2 GiB，上表和预算都要更新。

## 谁占内存，谁负责回收

VM 有独立内核，guest 页缓存仍占宿主物理页。guest 认为可回收的缓存，不会自动成为宿主可用内存。balloon 要求驱动配合，收缩可能导致 guest 换页、延迟甚至 OOM；配置最小值并不承诺宿主立刻得到“最大减最小”的内存。最小等于最大仍可保留 balloon 统计；0 表示关闭设备。依据：[Proxmox VM memory](https://github.com/proxmox/pve-docs/blob/master/qm.adoc#memory)。

LXC 共用宿主内核，内存限制是 cgroup 上限，不是预留或实际用量。不要给 LXC 套用 VM balloon。ARC 是宿主 ZFS 缓存，也使用物理 RAM；它的上限不是预留量，压力下可回收但有时延。guest 页缓存、ARC 和应用工作集可能缓存相同数据，不能仅因缓存较多就认定内存泄漏。

仓库 [proxmox-vm 模块](../../terraform/modules/proxmox-vm/main.tf) 把 `memory` 映射到 dedicated、`balloon_memory` 映射到 floating；null 回退到 memory。PDM 和 OpenBao 是根级资源，直接在 `memory` 块里写 `floating`。无需修改模块接口。

VM 106 是例外：代码和 state 写的是 `balloon_memory = 0`，但现场配置没有 `balloon` 行，`qm showcmd 106` 带 virtio-balloon 设备，guest 也绑定了驱动。所以它的 balloon 实际是开着的，最小值等于上限，不像 114/115 那样关闭。provider 把“未设置”读成 0，plan 看不出这个差别。

Terraform 管 guest 规格；宿主 ARC 由未来获批的 Ansible 宿主配置管理，目前仓库没有这个入口。[PBS ARC 配置](../../ansible/roles/pbs/tasks/configure.yml) 是持久化参考，不能直接套到 pve0。

## 候选 VM 规格与定值

下表的最小/最大值均为 GiB，是试验起点，尚无完整周期的最低需求证明。保留最大值使 guest 有恢复空间，不把理论收缩空间算进保证预算。所有候选都需采集 guest MemAvailable、匿名内存/缓存、OOM 与服务延迟；按完整周期的最坏值加余量确定最小值，任何压力或业务退化都提高最小值或恢复固定内存。

“可回收上限”= max(0, memhost − 候选最小值)，只是当前快照下的理论值。

| VM | free -m total/used/available（MiB） | 候选最小/最大 GiB | 可回收上限 GiB | 理由及定值重点 |
|---|---|---|---:|---|
| 102 RustDesk | 3894 / 590 / 3304 | 1 / 4 | 1.50 | 首个试点；并发远控、中继传输与连接恢复压力决定下限 |
| 101 Immich | 7936 / 2556 / 5380 | 6 / 8 | 1.48 | 保留照片与 ML 峰值空间；完整处理批次结束且无积压后定值 |
| 106 n8n | 3896 / 1168 / 2727 | 2 / 4 | 0.85 | 本次新增；按工作流并发和大批量执行定值 |
| 109 MCP Gateway | 3896 / 1594 / 2301 | 3 / 4 | 0.53 | 多服务并发有峰值；以真实并发请求、冷启动和服务重连定值 |
| 104 NetBox | 3894 / 1493 / 2401 | 3 / 4 | 0.42 | 给数据库、worker 和缓存留量；覆盖同步、后台作业与备份 |
| 112 OpenBao bao | 3901 / 385 / 3515 | 1 / 4 | 0 | memhost 已低于最小值，现在收缩没有收益，暂不试点 |
| 113 OpenBao control | 3901 / 353 / 3548 | 1 / 4 | 0 | 同上 |
| 117 PDM | 3914 / 481 / 3432 | 2 / 4 | 0 | 同上；管理任务有突发，覆盖多端点刷新和备份窗口 |
| 合计 | | | 4.78 | 不是保证释放量 |

八台 guest 均绑定 virtio_balloon 驱动，memory PSI avg10/60/300 当时都为 0。驱动存在不等于压力下回收已验收。101/102/104/106/109 的采样用户是 ubuntu，112/113/117 是 debian。

VM 116 remotecc-ops 不进候选：它是员工生命周期的执行机，属于 `terraform/remotecc`，由 `wsctl` 驱动，不走 Jenkins。本次也没有读取它的 guest 用量。

现场 PVE 9.0.3 的 pvestatd 默认目标 80%，每轮最大调整 100 MiB；ProcFSTools 以 memtotal − MemAvailable 计算 memused。AutoBalloon 仅处理有效 balloon/balloon_min，shares=0 跳过。这是 2026-10-26 读取现场 `/usr/share/perl5/PVE/{Service/pvestatd,ProcFSTools,AutoBalloon}.pm` 的结果，PVE 版本至今未变。它不预测业务峰值；本方案不修改全局目标或 shares。

按这个算法，当前 memused 约 79.7%，已贴近 80% 目标，相当于 MemAvailable 约 12.5 GiB。设了最小值之后，只要 MemAvailable 跌破这条线，自动 balloon 就会开始工作。ARC 涨到 8 GiB 约为 87.5%，这时 balloon 是持续在收缩，而不是偶尔触发，所以 ARC 扩容和 balloon 的影响不能分开看。

Immich 官方目前要求最低 6 GB、推荐 8 GB；这里 6/8 GiB 为保守换算后的候选，不能证明当前任务峰值能在 6 GiB 内运行。先覆盖上传、缩略图、转码和机器学习任务。依据：[Immich requirements](https://docs.immich.app/install/requirements/)（2026-10-26 查阅）。

HA（Home Assistant）与 FunASR 保持现有固定内存：前者优先家庭自动化响应稳定，后者模型驻留和推理峰值受实时任务影响；本次无证据证明收缩不会影响服务。固定内存是当前策略，不等于本次验证了它们的容量。它们没有 Terraform 声明，如要改动，先确认管理所有者，不得用临时 `qm set` 绕过归属。

## 可复算的容量预算

宿主总 RAM 约 62.64 GiB；guest 上限 56 + 17 = 73 GiB，已经高于物理 RAM 约 10.4 GiB。这是配置超分，不是当时实际耗用。即使候选 VM 都收到最小值，也不能保证它们同时能收缩到位，因此不以最小值之和证明安全。

快照 MemAvailable 约 12.74 GiB，ARC size 约 3.10 GiB。仅固定其他负载，按 ARC 增量估计余量：`12.74 - (目标 ARC - 3.10)`。此计算只是敏感性分析，没有把可回收缓存重复计入。

| ARC 满缓存假设 | 比快照多占 RAM | 静态余量估计 | 决策 |
|---|---:|---:|---|
| 8 GiB | 4.90 GiB | 7.84 GiB | 低于 8 GiB 准入线，先完成 balloon 试点再评估 |
| 12 GiB | 8.90 GiB | 3.84 GiB | 低于 4 GiB 停止线，当前不可行 |
| 16 GiB | 12.90 GiB | −0.16 GiB | 当前不可行 |

这些都是空闲快照的结果，高峰只会更低。

建议至少保留 8 GiB 宿主余量作为准入目标，4 GiB 为停止线；这些是本方案建议策略，并非厂商保证。用同一时间轴采集的最低 MemAvailable 和 ARC size，按 `观测 available - max(0, 下一阶段上限 - 同时刻 ARC size)` 逐样本复算；全窗口最差预测余量仍须至少 8 GiB。还需核查 guest 最大回升、宿主非 ARC 增长和服务性能，不能只凭静态公式放行。

即使 4.78 GiB 的理论回收全部兑现，静态余量也只有：8 GiB 档约 12.6 GiB，12 GiB 档约 8.6 GiB，16 GiB 档约 4.6 GiB。所以按当前负载和候选值，16 GiB 不满足准入线，不作为本方案的目标。12 GiB 只有在回收几乎全部兑现时才勉强达标，而这一点不能指望。现实目标是 8 GiB。

当前生效 ARC 上限约 3.1 GiB，**8 GiB 也是待批准的首个扩容阶段**，不是已部署基线。若 8 GiB 未通过，应回到已记录的 3348103168 bytes；通过后才讨论 12 GiB。

ARC 每次扩容的窗口、停止线和回退见实施手册；允许最终保留 3.1、8 或 12 GiB。

## ARC 生效与官方来源

运行时 `/sys/module/zfs/parameters/zfs_arc_max`、ARC 统计 `c_max` 与 `size`、持久化文件及启动配置须分别核验。下调上限不保证立即缩小 ARC；不要制造内存压力强迫回收。必须先看到回收和余量，再恢复 guest 可用内存。依据：[OpenZFS zfs_arc_max](https://openzfs.github.io/openzfs-docs/Performance%20and%20Tuning/Module%20Parameters.html#zfs-arc-max)（2026-10-26 查阅；按现场模块版本核对，不能套用 master 默认值）。

ZFS 根文件系统持久化涉及 `/etc/modprobe.d/zfs.conf`、initramfs 和后续重启；运行时修改成功不能证明重启后生效。依据：[Proxmox ARC 配置](https://github.com/proxmox/pve-docs/blob/master/local-zfs.adoc#limit-zfs-memory-usage)（2026-10-26 查阅）。8/12/16 GiB 分别是 8589934592 / 12884901888 / 17179869184 bytes。
