# pve0 内存与 ARC 分阶段实施手册

本手册落实 [内存设计](../architecture/pve0-memory-design.md)，供未来获得生产变更授权后使用。以下生产命令均为手册示例，未执行。安装、采购、部署、Terraform state 写入、apply、重启须分别获得授权。

## 基础设施与责任入口

目标仅为 pve0。2026-11-05 物理可见 RAM 62.64 GiB、ARC 有效上限 3348103168 bytes（约 3.118 GiB），不是 8 GiB。VM/LXC 上限合计分别 56/17 GiB；完整 guest 清单和快照见设计文档。mainpool/rpool 均为 ZFS。

| 事项 | 管理入口与执行者责任 |
|---|---|
| terraform/proxmox 内 VM 的规格/balloon | 在对应服务文件改参数，走 PR；合并后由 Jenkins 生成 plan，操作者在 Apply 审批点确认。不在本地 apply，不直接 qm set |
| VM 116 remotecc-ops | 属于 terraform/remotecc，由 `wsctl` 驱动，不走 Jenkins；不在本方案试点范围 |
| 114/115 等无 Terraform 声明的 guest | 用户先确认管理所有者、恢复责任与权威配置；本方案不改动 |
| 宿主 ARC | Ansible 操作者先新增获批的宿主内存角色和 Deploy + Verify play，定向 pve0；当前仓库没有该入口，本文不假定存在 |
| 服务验证 | 各服务所有者比较功能、任务积压、错误率、延迟和负载周期；宿主健康不能代替应用健康 |
| 维护重启 | 用户批准窗口后由 PVE 操作者执行，涉及 quorum、备份与业务可用性协调 |

Ansible 在当前 checkout 的 `.venv` 中运行（`./scripts/setup-dev-env.sh` 后 `source .venv/bin/activate`）；不使用或修改宿主 `~/.local/bin/ansible`。pve0 在 inventory 的 `proxmox_cluster` 组里。动态 inventory 无主机匹配或解析失败时，从仓库根运行 `./scripts/refresh-terraform-state.sh`，再核对 inventory；不要绕过 inventory 直接部署。

## 1. 建立带时间戳的基线

生产变更前至少连续 7 天，且必须覆盖一次完整照片处理、一次完整备份和日常任务周期；未覆盖就延长，而不是到第七天自动放行。建议宿主和候选 guest 每 60 秒采样，密集试点前后每 10 秒采样 30 分钟。保留 UTC 时间、节点/VMID、版本、阶段、正在运行的任务及变更记录到获批的运维证据目录，不把凭据或完整 Terraform state 放入 Git。

以下为在 pve0 的只读采样示例；由获批的采样设施定期调用，不需先安装新工具。`vmstat` 若不可用就记录缺项，不自动安装。

```bash
# Read-only examples on pve0; capture stdout with timestamps in approved evidence storage.
date -u +%FT%TZ
hostname
pveversion -v
cat /proc/meminfo
cat /proc/pressure/memory
cat /proc/vmstat
cat /proc/spl/kstat/zfs/arcstats
cat /sys/module/zfs/parameters/zfs_arc_max
cat /sys/module/zfs/parameters/zfs_arc_min
cat /etc/modprobe.d/zfs.conf
pvesh get /cluster/resources --type vm --output-format json
zpool status -P
```

在各 guest 内按同一时钟采集 `free -m`、`/proc/meminfo`、`/proc/pressure/memory`、`/proc/vmstat` 和 balloon 驱动路径，检查内核日志中的 OOM/oom-kill。记录 QEMU RSS/API memhost、guest used/available、宿主 available 的各自口径；不要将它们合并为同一个“已用”。用 `/proc/vmstat` 的 pswpin/pswpout 差值计算换页趋势，首个累计值不表示当前正在换页。ARC 记录 size、c、c_min、c_max、hits/misses 的增量及 I/O 延迟；命中率高不等于业务获益。

记录照片上传/缩略图/转码/ML、NetBox 同步、MCP 并发、RustDesk 远控、PDM 查询、OpenBao 请求和备份时长及积压。既有指标缺失时先补只读观测，不能把一次空闲状态当作已通过高峰。

## 2. 对账代码、state、现场

先读取 Proxmox 配置与 pending、锁、当前运行态，再核对对应 Terraform 地址、provider、node、storage、磁盘身份、内存与 balloon。2026-11-05 已比对 HCP state 与现场的内存字段，pve0 上已声明的 guest 全部一致。如遇 backup 锁，先查备份任务状态与锁所有者，不能自行解锁。

合并前在能访问 PVE API 的环境跑一次完整的 `terraform plan`，不保存 plan 文件，审查 pending 和漂移原因，不用 target 隐藏其他变更。输出可能含敏感信息，保存于私有证据目录。

Jenkins 的 Apply 会执行整个 root 的 plan，不是只执行本次改动。目前这个 plan 里已有一笔无关内容：`module.jenkins_agent` 和 `ansible_host.jenkins_agent` 待创建（LXC 110，2 GiB），还有 `pnetlab_ip`、`ws_executor_ip` 两个输出待删除。先决定这些内容的去留，再提 balloon 改动，否则批准 Apply 时会把 LXC 110 一起创建。

出现替换、删除、磁盘/node/storage 回退、身份不符、意外变更或锁时停止写入，先修正归属和声明。禁止用旧代码覆盖迁移后的现场。HCP state 是敏感证据；不要提交 state、saved plan 或 auto.tfvars。

## 3. 单台 balloon 试点与推广

先保持现有 ARC 上限。建议以 RustDesk 为首个候选，但必须先确认服务所有者与恢复窗口。`terraform/proxmox/rustdesk.tf` 内模块调用的候选差异为：

```hcl
# Candidate only; production apply requires separate authorization.
memory         = 4096
balloon_memory = 1024
```

后续按设计表的可回收上限排序：Immich、n8n、MCP Gateway、NetBox，都在各自服务文件配置。n8n 要把现有的 `balloon_memory = 0` 改成候选值；它的 balloon 设备现场本来就开着，见设计文档。OpenBao 和 PDM 的 memhost 已不高于候选最小值，现在收缩没有收益，暂不试点；它们是根级资源，以后要改时写 `memory` 块的 `floating`。HA/FunASR 保持原固定内存，不参与试点。不要改变全局 balloon target 或 shares 来强迫回收。

先 fmt/validate、审阅完整 plan，合并后在 Jenkins 的 Apply 审批点确认；每次 Apply 都要单独获得授权。核验配置、pending、guest 驱动、运行时 balloon 实际值、宿主和服务指标；若需要重启才能生效，另行安排，不能仅依据配置已写入通过。逐台至少观察 48 小时并覆盖该服务代表性负载；任何未覆盖的周期继续等待。

设了最小值后，宿主 MemAvailable 低于约 12.5 GiB（memused 80%）时自动 balloon 就会收缩 guest，而当前快照已经贴近这条线。所以试点从生效起就可能真实收缩，不是只有扩 ARC 后才发生。

通过条件：无新增 OOM、无新持续 guest 换页/PSI，服务错误与任务积压无恶化，关键操作 P95 延迟相对同负载基线不增加超过建议 20%，宿主保持下节余量标准。若 P95 不可测，先定义可复现业务操作与允许时长。停止条件沿用下节，且出现 guest MemAvailable 持续低于其 RAM 的 10% 达 5 分钟即暂停并恢复上一配置。所有阈值是建议，实施前由服务所有者确认，不能宣称厂商保证。

试点通过后逐台推广，每台保留相同观察要求，最后再完成至少 7 天覆盖三类周期的汇总。候选最小值合计与上限之差不算保证释放量；没有观察到实质回收时，不因此扩大 ARC。

## 4. ARC 从当前值到 8，再到 12 GiB

每阶段分别授权：当前 3348103168 → 8589934592（8 GiB）→ 12884901888（12 GiB）。若容量不够，停在已通过的较低值；当前约 3.1 GiB 同样是有效回退点。16 GiB（17179869184）不是本方案的目标：按设计文档的预算，候选回收全部兑现也达不到准入线。除非宿主内存或负载发生变化并重新做预算，否则不要进入这一档。

每次开始前用设计文档公式逐样本复算满 ARC 时余量，最差预测至少 8 GiB，且上一阶段服务和压力验证通过。2026-11-05 快照推算 8 GiB 满缓存约剩 7.84 GiB，12 GiB 约剩 3.84 GiB，16 GiB 为负，因此目前三档都不满足准入条件。只有采样中实际观察到的回收才能改变这个结论，候选 balloon 的理论释放量不计入物理预算。

| 每阶段检查 | 建议通过条件 | 停止与动作 |
|---|---|---|
| 时长 | 每档至少 7 天且覆盖照片处理、备份、日常任务完整周期 | 缺周期则延长；ARC 未接近上限时不能声称满缓存已验收，继续用预算最差值约束 |
| 宿主余量 | 每分钟 MemAvailable 最低至少 8 GiB | 低于 8 GiB 持续 5 分钟停止升档；低于 4 GiB 任一采样立即启动回退 |
| 内存压力 | 无新增 OOM；PSI some avg60 不持续达到 1%，full avg60 不持续达到 0.1% | 任一压力阈值持续 5 分钟、任何 OOM 或服务故障立即回退 |
| 业务和 ZFS | 同负载 P95 延迟增长不超过 20%、无新增错误/积压、备份完成且时长可接受 | 服务失败、延迟退化或备份异常则回退；检查 I/O，不把 ARC 变大当成功 |

建议阈值需在窗口开始前记录并认可；不要观察结果后临时放宽。若业务没有可测收益，不需要为达到数字而扩大 ARC。

## 5. 实现运行时、持久化与重启验证

此步骤是未来 Ansible 实现要求，当前没有新增角色或 playbook。先做只读身份断言、模块版本与参数范围检查、配置冲突检查、基线参数与文件备份；拒绝意外节点和未解释的同名 options 行。角色应幂等管理一个确定的 ARC 配置来源，检查 `zfs_arc_min < zfs_arc_max`，分别核验模块参数和 arcstats，避免只追加多条 options。不要改造 PBS 角色来部署 pve0。

运行时写入示例仅用于说明未来角色行为，实施时由获批 Ansible 入口管理：

```bash
# WRITE EXAMPLE ONLY: stage 8 GiB after approval and prechecks.
printf '%s\n' 8589934592 > /sys/module/zfs/parameters/zfs_arc_max
# Read back both configured limit and ARC effective state.
cat /sys/module/zfs/parameters/zfs_arc_max
awk '$1 == "size" || $1 == "c_max" || $1 == "c_min" {print}' /proc/spl/kstat/zfs/arcstats
```

运行时参数为本次启动状态；持久化的候选行是 `options zfs zfs_arc_max=8589934592`（8 GiB 示例），不是另一个独立可随意升档的值。若运行时阶段失败，同步恢复持久化来源，避免未来重启意外升档。

root 为 ZFS，应由 handler 在配置确实变化后执行 `update-initramfs -u -k all`，验证退出状态与对应内核 initramfs 中的配置内容。该命令会写启动镜像，需本次宿主变更授权；失败则恢复文件并重新生成已知良好的镜像，停止重启。配置文本正确、handler 成功仍不证明下次启动生效。依据：[Proxmox ZFS ARC](https://github.com/proxmox/pve-docs/blob/master/local-zfs.adoc#limit-zfs-memory-usage)。

重启另行授权并协调服务后，Verify 重新读取 node identity、模块参数、arcstats c_max/c_min/size 和服务健康；再完成完整观察窗口。记录“运行时通过”“持久化已生成”“重启后通过”三个独立状态。

## 6. 异常回滚顺序

1. 停止继续升档/推广，记录触发指标，暂停可延后的照片或其他任务（停任务同样需既有授权）。恢复 ARC 到上一通过值；首档失败则为 3348103168 bytes。同步恢复持久化配置并验证 initramfs，防止未来重启重新升高。
2. 连续读取 ARC size/c_max、MemAvailable、PSI、OOM 与服务状态，确认实际回收且至少 8 GiB 建议余量。**下调上限不保证立即缩小 ARC**；若 size 未降，不制造内存压力，不立刻恢复所有 balloon。先控制负载，必要时按获批维护窗口处理。
3. 已有足够余量后逐台恢复原 guest 参数，Terraform 管理对象使用审查并另行授权的 plan/apply；原先 null/最小等于最大恢复为原值，n8n 恢复 `balloon_memory = 0`，HA/FunASR 原 balloon=0 保持其原策略。每台核验实际生效、pending 与业务，避免同时回升产生新峰值。
4. 检查业务恢复与备份完整性，保留失败阶段证据。需要重启或停机则等待明确窗口授权，不把应急回退理解为无条件重启许可。

## 未来验收

未来验收记录至少包括阶段起止时间、采样文件位置、负载事件、最低余量、压力/换页趋势、服务性能、配置/运行时/pending/重启状态、是否回退及执行者。未得到这些证据前，状态应为“候选”或“待观测”，不能标记生产扩容完成。
