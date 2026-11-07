# 现实核对审核：WILL-106 更新

> 这是 2026-11-07 对 WILL-106 更新的 reality 审核，以原生同模型子代理方式运行，不是跨模型审核。本文取代 2026-11-05 的 HAPI 版本。

- 日期：2026-11-07
- 对象：`architecture-employee-lifecycle.md` 中 AD-2 新增行、AD-25 至 AD-32、配置总览、Stack 行、新增 Deferred 行，以及 `docs/deployment/oci-hub-ip-change.md`
- 基线：公开仓库 `aad7d3d` 加工作区未提交改动；私有 `remotecc/wsctl` `fe3f25e`（2026-11-06）
- 视角：每条已落定的决策是否经过网页或现状核对，而不是凭训练数据断言；命名的技术是否还存在、是否合用

## 结论

**方向成立，但不能按现文进入实现。** 没有发现 critical。大部分技术判断都核实了：bpg 的 SDN 资源、nftables 的 concat set、`pve-cluster.service`、OCI 自定义备份策略和相关 Terraform 资源都真实存在且合用，版本数字也基本准确。

问题集中在现状代码和新决策的接缝处，共 7 个 high：

- IP 变更预案的第 4、6 步按现状代码不会生效，其中 `wsctl reissue` 还是静默失败。
- AD-29 要“补上全局锁”，但 provider 不支持，用外层包锁反而会让 provider 写入失败。
- AD-27 的 set 与现有 `apply`、`verify` 契约冲突：role 重跑会清空配对，第一次写入元素后 `verify` 就失败。
- AD-32 原地恢复后，`terraform/oci` 的 `source_details` 可能把恢复好的启动卷换回全新镜像，`prevent_destroy` 拦不住。这一条的 provider 路径已确认，API 回读行为未确认。

这些修复多数只需改几句规则或加一行配置，不需要推翻已采纳的决策。

## 范围与边界

- 已读：spine、memlog 尾部、预案；`scripts/oci-hub/{boundary,pve-sdn}.py`；`oci-hub`、`oci-hub-pve`、`oci-hub-spoke`、`oci-hub-mosh` role；相关 playbook；`terraform/{oci,remotecc}`、`terraform/modules/proxmox-vm`；`Jenkinsfile`；`docs/architecture/ci-only-execution-architecture.md`；私有 `wsctl` 的 `*.py` 和入口脚本，含 `services/oci-hub/{executor,ledger}.py`。
- 网页：bpg provider 的源码、文档与 CHANGELOG；Proxmox 的 `pve-network`、`pve-cluster`、`pve-manager` 源码和 pmxcfs wiki；nftables wiki 与 man page；Oracle 文档；oracle/oci provider v8.3.0 的文档和源码。来源见文末。
- 未做：没有使用 OCI、Bitwarden、SSH 或任何凭据；没有读 settings、roster、catalog 或其他数据文件；没有安装任何东西。
- 没有运行 `nft`（本机是 macOS），下文的 nft 结论来自文档和代码，不是实测。

## 发现总表

| # | 严重度 | 位置 | 问题 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | high | 预案第 6 步、影响范围“设备包”行 | `wsctl reissue` 重发旧字节，新 IP 不会进入设备包，且不报错 | 已确认 |
| 2 | high | 预案“`endpoint` 改一处”、第 4 步 | PVE 放行地址来自线上 `boundary.json`，不来自 `pool.endpoint`，重新 apply 是空操作 | 已确认 |
| 3 | high | AD-29 | provider 没有全局锁能力，外层持锁会让 provider 写入失败 | 已确认 |
| 4 | high | AD-27、AD-30、AD-31 | `apply` 用 `delete table` 重建，role 重跑清空 set，与“可随时重跑”矛盾 | 已确认 |
| 5 | high | AD-27 | `verify` 的回执摘要包含 set 元素，第一次写入后 executor 和服务全部拒绝运行 | 已确认（代码）；`nft -j` 输出未实测 |
| 6 | high | AD-32、`terraform/oci/compute.tf` | 原地恢复后 `source_details` 漂移可能触发启动卷被换回镜像 | 待确认：provider 路径已确认，API 回读未确认 |
| 7 | high | 预案第 5 步 | 没有可执行入口，现有路径都不覆盖已有 VM 批量重跑 | 已确认 |
| 8 | medium | AD-26、AD-29 | AD-26 先落地时 `pve-sdn.py` 没有输入，两条决策有未声明的先后依赖 | 已确认 |
| 9 | medium | AD-26 | 默认读到的是未应用配置，应读 running 配置 | 已确认 |
| 10 | medium | AD-26、AD-28 | “MAC 等于 VMID 算出的值”只来自分配器代码，未对现网核对，不符时全局拒绝加载 | 未确认 |
| 11 | medium | AD-27 | iptables FORWARD 无法使用 nft set，“规则固定”依赖这层改成静态规则 | 已确认 |
| 12 | medium | AD-32、配置总览 | 整机恢复只处理“备份后新增”，没处理“备份后退役或改址”；对应命令不存在 | 已确认（代码） |
| 13 | medium | AD-32、配置总览 | Hub 与 Anki、unified-proxy、BookOrbit 同机，恢复会回滚它们，且受 CI spine AD-14 约束 | 已确认 |
| 14 | medium | AD-32 | Jenkins 备用方案的“现有 OCI 权限”未落实到任何流水线，手动备份也不会过期 | 部分确认 |
| 15 | low | AD-32 | “保留 4 份”在 OCI 是按时长，瞬时可能 5 份，五份免费额度没有余量 | 已确认 |
| 16 | low | AD-29 | 升级影响面比 Binds 列的大；要钉在 v1.0 以下；API token 权限未知 | 部分确认 |
| 17 | low | 预案 | DNS 清单漏 `bookorbit.willfan.me`；SSH 严格校验要更新 known_hosts；首段把推断写成事实 | 已确认 |
| 18 | low | AD-26、AD-30 | 改名涉及硬编码的安装路径和 hook 文件，role 与 release 无法同时生效 | 已确认 |
| 19 | low | 配置总览、AD-2 | 从零重建缺 `--new-hub`；静态参数清单漏 `pve_address`、`hook_directory` | 已确认 |
| 20 | low | Stack | Semaphore 落后一个补丁版本；其余见下 | 已确认 |

## 发现详情

### 1. `wsctl reissue` 不会更新设备包里的 IP（high）

预案第 6 步和影响范围表都把 `wsctl reissue` 当作更新 `wireguard_endpoint` 的手段。代码不是这样：

- `wsctl:13` 的用法写明 `resend the existing device bundle with a new link`。
- `oci-hub-admin.py:239-247` 的 `reissue_request` 读取磁盘上已有的 `device-bundle.zip`，后续注释是“Every check, upload and mail decision uses the bytes captured above”。
- `wireguard_endpoint` 只在开户时写入 manifest（`hub-terminal.py:674`）。
- `verification_subject`（`oci-hub-admin.py:115` 起）校验地址、公钥、网关和主机 pin，**不校验 endpoint**，所以不会报错。
- 重新生成也走不通：`hub-bundle.py:67` 在字节不同时抛 `HUB_DELIVERY_CONFLICT`。`wsctl` 动作列表里没有重建现有设备包的命令。

后果：员工收到的包仍指向旧 IP，管理员看到的是发送成功。预案“需要提前准备”里的“批量重发”解决不了这个问题。

**建议：** 改写第 6 步，并在“需要提前准备”里加一项“按新 endpoint 重建现有设备包”，要求 story 把它做成命令，且 `verification_subject` 校验 endpoint。若想让后续变更更便宜，可评估把 endpoint 改成域名，但现在 `hub-bws-store.py:171` 和 `oci-hub-spoke/tasks/vpn.yml:10` 都强制要求 IP。

### 2. PVE 的放行地址不来自 `pool.endpoint`（high）

预案写“`endpoint` 现在是 settings 的 `pool.endpoint`，改一处”，第 4 步写“在 PVE 上重新 apply 防火墙”。

`boundary.py:192-193` 用的是策略文件里的 `c["endpoint"]`。`hub-terminal.py:207` 的 `policy_candidate` 从线上策略深拷贝，从不把 `pool.endpoint` 写进去。`pool.endpoint` 只进入 spoke 配置（`hub-terminal.py:623`）、凭据准备（`:637`）和 manifest（`:674`）。

所以在 AD-25、AD-26 落地前，第 4 步用旧地址重新渲染，等于没有改。VM 发往新 IP 的 UDP 51825 走到 `iifname "<vnet>" drop`，spoke 不会重连。预案前半写的是“现在”的情况，这条今天就会踩到。

**建议：** 预案分“AD-25 落地前”和“落地后”两种写法。落地前要明确修改 PVE 上 `/etc/oci-hub/boundary.json` 的 `endpoint` 再 apply，并把“改一处”改成“两处”。

### 3. AD-29 的“补上全局锁”按现文做不到（high）

AD-29 要求实现 story “补上 `pve-sdn.py` 的全局锁和‘拒绝无关 pending 变更’保护”。核对结果：

- provider 没有对应能力。`proxmox/cluster/sdn/applier/applier.go` 的 `ApplyConfig` 发送 `DoRequest(ctx, http.MethodPut, c.ExpandPath(""), nil, resBody)`，请求体为空。zones、vnets、subnets、applier 的客户端代码里搜不到 `lock`、`allow-pending`，CHANGELOG 也没有相关条目。
- 不能用外层持锁解决。PVE 的 `lock_sdn_config` 在 `/etc/pve/sdn/.lock` 存在、调用方没有带正确令牌时直接 `die "invalid lock token provided!"`，而 VNet 的 create、update、delete 都走这个检查。也就是 `wsctl` 一旦持锁，provider 的写入全部失败。
- 没有锁时，`PUT /cluster/sdn` 不检查 pending，`has_pending_changes` 只在获取锁的接口里调用。`commit_config` 又是用 `compile_running_cfg()` 整份写入，不能只提交部分对象，所以 applier 会把别人留下的 pending 一起应用上线。这正是 `allow-pending=0` 要防的情况。
- `proxmox_sdn_applier` 在 v0.120.0 文档里标为 **EXPERIMENTAL**，spine 没有提到。

**建议：** 把 AD-29 这句改成可实现的表述：Terraform 运行前做一次预检，获取锁（`allow-pending=0`）后立即释放，有 pending 就拒绝；串行依赖 `wsctl` 运行锁；接受 PVE 页面并发修改这个残余风险，或者给 provider 提 lock-token 支持。把 applier 是实验性资源写进风险说明。

### 4. role 重跑会清空配对（high）

AD-27 说 `firewall.py` “只加载规则和空 set”，set 只在 `register`、`retire`、`readdress` 时更新，开机时全量同步。AD-31 说“role 可随时重跑”。

现有 `apply`（`boundary.py:426-428`）的做法是先 `delete table inet oci_hub` 再整表加载，`oci-hub` role 每次都跑 `apply`（`tasks/main.yml:64`）。set 是表内对象，删表后元素全部丢失。这之后没有任何机制重新填充，全部设备与 VM 的流量被 `iifname { "wg-users", "wg-workspaces" } drop` 丢弃，直到下次重启。

此外“开机时从账本全量同步”目前没有入口：`executor.py:576` 的子命令只有 `init`、`action`、`sample`、`query`、`expiry`，也没有对应的 unit。

**建议：** 两件事一起定。

- `firewall.py` 不删表：同一事务里 `add table`、`add set`、`flush chain` 后重建规则，这样元素保留。man page 没写 `add set` 遇到已有 set 时的行为，story 要实测。
- 把 set 同步放进 `sample`。`oci-hub-quota.timer` 已是每 5 秒、开机 5 秒后触发，这样开机同步、崩溃后补写和 role 重跑后的自愈都由它承担，不用加新 unit，也不违反“公开代码不调用私有代码”。全量同步是幂等的，所以 `actions` 表里 `prepared` 状态重放时不会漏写。

### 5. `verify` 会因 set 元素而失败（high）

`boundary.py:358` 的 `live()` 取 `nft -j list table`，`canonical()`（`:218`）只去掉 `handle`、`packets`、`bytes`、`metainfo`，然后与 `apply` 时写的回执比较。set 元素变化后摘要就不一致。

`verify` 的调用方几乎覆盖全部 Hub 操作：`executor.py:586`（**每条命令加锁后第一步**）、`:548`（`routing_ready`）、Portal 和 quota 的 `ExecStartPre`。所以第一次 `add element` 之后，quota timer 失败，executor 拒绝一切命令，包括下一次写 set。AD-27 没有提到这一点。

**建议：** 摘要排除 set 元素。nft man page 的 `-t/--terse` 是“Omit contents of sets from output”，可以用，但要在 story 里实测它和 `-j` 同时使用的效果；不行就在 `canonical()` 里去掉 `elem`。同时另设一项检查，确认 set 与账本一致。

### 6. 原地恢复后 Terraform 可能把启动卷换回镜像（high，待确认）

`terraform/oci/compute.tf` 写的是 `source_type = "image"`，`ignore_changes`（`:30`）不含 `source_details`。oracle/oci v8.3.0 的源码显示：

- `source_details.source_id` 不是 `ForceNew`，文档标为 Updatable。
- 读取时，如果 API 返回 `InstanceSourceViaBootVolumeDetails`，state 写成 `bootVolume` 和新卷 OCID（`InstanceSourceDetailsToMap`）。
- 更新时，`source_id` 有差异就发 `UpdateInstanceSourceViaImageDetails`，这就是一次启动卷替换。

所以如果替换后 API 报告的来源变成新卷，下一次任意 `terraform apply` 会计划一个**原地更新**，把恢复好的 Hub 换成全新镜像。这不是 destroy，AD-32 的 `prevent_destroy` 拦不住。CI spine 的 AD-1 规定 `terraform/oci` 在交接后归 Jenkins，这个 apply 可能由一次无关的合并触发。

未确认的是替换后 `sourceDetails` 实际返回什么，Oracle 文档没写，要在演练里看。

**建议：** AD-32 增加一句，并在 story 里同时落地：`lifecycle.ignore_changes` 加上 `source_details`。恢复演练要包含“替换后跑一次 `terraform plan`，确认无变更”。另外 `oci_core_volume_backup_policy_assignment.asset_id` 应引用实例的 `boot_volume_id`。替换后这个 ID 会变，策略要等下一次 apply 才转到新卷，在此之前恢复出来的卷没有备份，这一步要写进恢复步骤。

### 7. 预案第 5 步没有可执行入口（high）

“对所有员工 VM 重跑 `oci-hub-spoke` 配置”目前没有对应命令：

- `wsctl` 动作列表里没有针对已有 VM 的入口，`hapi-install` 只跑 HAPI。
- `deploy-oci-hub-workspace.yml` 按部署合同只限新 VM。
- `deploy-oci-hub-terminal.yml --tags terminal_configure` 能走到 spoke（经 `oci-hub-mosh`），但需要 `hub-terminal.py` 现场组装的每员工变量和从 BWS 物化的运行时 Vault（`oci_hub_spoke_private_key`）。AGENTS.md 也禁止只用全局 Vault 跑员工 play。

另外已到期员工的 VM 是关机的，跑不到。

**建议：** 与发现 1 合并为一项“全量切换 endpoint”的 story，列入“需要提前准备”，并写清关机 VM 的处理。

### 8. AD-26 与 AD-29 有未声明的先后依赖（medium）

AD-26 说不设员工层文件、`wsctl` 不传数据。AD-29 说完成前 `oci-hub-pve` 仍是 SDN 唯一写者。但 `pve-sdn.py:89` 的输入就是策略文件，`:97` 遍历 `c['workspaces']`，`--prune` 也靠它判断（`:68`）；role 第 9 行还断言 `workspaces` 非空。

AD-26 若先落地，新 VNet 无从创建，`--prune` 对空列表还会把全部无 VM 使用的 VNet 判为过期。

**建议：** 明确 AD-29 先于 AD-26 的 PVE 部分，或写明过渡期 `wsctl` 仍向 `pve-sdn.py` 传工作区清单。

### 9. AD-26 要读 running 配置（medium）

`pve-network` 的 `GET /cluster/sdn/vnets` 不带参数时返回的是 `Vnets::config()`，不是运行配置；要 `running=1` 才取 `.running-config`。按默认方式读，已建未应用的 VNet 会生成规则，`verify --routing` 找不到接口；待删除的 VNet 会丢规则而接口还在。

**建议：** AD-26 写明读 running 配置（`--running 1` 或 `/etc/pve/sdn/.running-config`）。启动路径只读本机 VM 配置：`pve-sdn.py` 的 `bridges()` 走 `/nodes/<node>/...`，读其他节点时不适合放在开机阶段。读不到 `/etc/pve` 时要失败，不能当成“没有工作区”，单元上再加 `Requires=pve-cluster.service`。

### 10. VMID 规则未对现网核对（medium，未确认）

“子网、网关、MAC 必须等于 VMID 算出的值”的来源是 `hub-terminal.py:447` 的分配器，这是 2026-11-02 才定的方案。已开户的 VM 不一定都符合：

- 公开迁移记录里 VM504 至 507 的 VNet、/30、网关、overlay 与公式一致，但这些记录没写 MAC，而这几台是“保留原 VM、禁止重建”迁过来的。同一记录里的设备地址与公式不同，不过这份记录早于 2026-11-02 的方案，AD-26 也不检查设备地址。
- `hub-terminal.py:451` 的 `reserved` 路径也会保留旧值。

按本次边界我没有读 roster，所以 MAC 无法确认。AD-26 的处理是“拒绝加载”，一台不符就让整份规则加载失败。AD-28 又写 MAC “不存”，一旦有例外就没有地方记录。

**建议：** 把“对全部工作区只读核对 `qm config`”列为 AD-26 的前置条件。把“拒绝加载”收窄为拒绝该 VM，或确认全量符合后再保留全局拒绝。

### 11. iptables 层用不上 nft set（medium）

nft man page 写明 accept 只结束当前 base chain，“The packet advances to the next base chain”。这正是 `boundary.py:282` 要维护逐配对 iptables FORWARD 规则的原因。iptables 不能引用 nft 的命名 set，所以“Hub 规则固定”只有在 iptables 这层也固定时才成立。AD-27 把它留给 story，但没说结论。

**建议：** AD-27 明确改成按接口的静态规则（`-i wg-users -o wg-workspaces` 及反向）。这是安全的：`oci_hub` forward 链优先级 -200，未配对流量在到达 iptables 之前已被丢弃。代价是逐配对检查只剩 nft 一层，`verify_host_forward` 同步调整。

### 12. 恢复只处理了一个方向（medium）

配置总览第 5 步只说“补登记备份之后开户的员工”。恢复的账本和 Portal 还包含备份之后退役的员工，以及 `readdress` 之前的地址。`executor.py` 开机从账本同步时会把这些配对重新放进 set，对应的 peer 密钥也还在 Portal。AD-10 让地址回到池中，所以旧配对可能指向已分配给新员工的 VM。

另外第 5 步和从零重建第 4 步都没有现成命令：`wsctl` 动作列表没有“按 D1 对账并登记”，`register` 需要从 BWS 组装 Portal 对象。

**建议：** 第 5 步改为双向对账，并在 set 同步和 Portal 启用之前完成；写明这是新命令。

### 13. Hub 是共享主机（medium）

`terraform/oci/compute.tf` 只有一台实例，上面还跑 Anki、unified-proxy、BookOrbit，这些归 Jenkins 一侧。替换启动卷会把它们一起回滚到最多一周前，AD-32 和配置总览都没提。CI spine AD-14 还规定 “Whole-host operations on a shared host need the operator to confirm that the other side is idle”。

**建议：** AD-32 和恢复表补一行，写明影响和这条确认要求。

### 14. Jenkins 备用方案未落到实处（medium，部分确认）

`Jenkinsfile` 的 Terraform 阶段只有 `terraform/proxmox`，`terraform/oci` 只在清理时出现。仓库里没有任何使用 OCI CLI 的地方。CI spine AD-5 说 OCI API 私钥是 Jenkins 的 secret-file 凭据，所以设计上有凭据，但是否已实际配置、`terraform/oci` 是否已交接，我无法确认。

Oracle 文档写明 “Policy-based backups expire, manual backups do not expire”，所以备用任务还要自己删旧备份，否则超出 5 份。

**建议：** AD-32 的备用方案写明工具、清理职责和前提，不要只写“沿用现有权限”。

### 15. “保留 4 份”是按时长实现的（low）

`schedules` 只有 `retention_seconds`，没有份数。每周一次保留 4 份应写成 `ONE_WEEK` 和 2419200 秒。Oracle 说定时备份可能延后“up to several hours”，过期清理时间未说明，所以交接时可能短暂有 5 份，正好用满免费额度。任何手动备份（不过期）都会超出。Pay As You Go 下超出是计费，不是失败。

**建议：** AD-32 写成“保留 28 天，常态 4 份，瞬时 5 份”，并说明手动备份要及时删。免费额度只在 home region，我未确认悉尼就是 home region。恢复时新建的 200 GB 卷加上原卷会超出 200 GB 免费存储，短暂计费。

### 16. provider 升级的影响面（low）

已核实 0.70 到 0.120 之间有 12 个版本带 breaking 说明，SDN 从 0.81.0 开始，与 memlog 一致。补充几点：

- `terraform/modules/proxmox-vm` 被 `terraform/proxmox`（6 处）和 `terraform/remotecc`（2 处）共用，模块不钉版本，升级一边时模块代码要同时兼容两个版本。AD-29 的 Binds 没列这些。
- `terraform/remotecc` 还管 VM500、模板和 `remotecc-ops`，升级计划会涉及它们。
- `hub-terminal.py` 的 `bind_vm` 硬编码 `proxmox_virtual_environment_vm.vm`。ADR-007 第 3 阶段说 v1.0 会移除这些旧名，所以目标版本要钉在 1.0 以下。新资源用 `proxmox_sdn_*`，`proxmox_virtual_environment_sdn_*` 已标记弃用。
- 0.100.0 的 breaking 项是 VM 电源状态集中处理。模块已 `ignore_changes` `started`，但 AD-2 规定电源不归 Terraform，plan 对比时要专门看这一项。
- `pve-sdn.py` 现在以 root 经 `pvesh` 运行，provider 用 API token，token 是否有 SDN 权限未知。如需调整，属于凭据改动。

### 17. 预案的小问题（low）

- DNS 清单漏了 `bookorbit.willfan.me`（`host_vars/oracle-cloud-ubuntu2404.yml:27`）。
- 执行器到 Hub 的 SSH 用 `StrictHostKeyChecking=yes`（`oci-hub-admin.py:25`、`hub-terminal.py:12`），只“核对是否写的 IP”不够，新 IP 需要更新 known_hosts。
- 首段写“替换启动卷不会丢 IP”，末段才说是推断，首段应一致。

### 18. 改名的落地顺序（low）

`/usr/local/lib/oci-hub-boundary.py` 硬编码在 `executor.py:548,586`、`oci-hub-release.py:23` 和多个 unit 里，`executor.py:618,631` 还读 `boundary-receipt.json`、`boundary.json`。`executor.py` 经 `oci-hub-release` 发布，`firewall.py` 经 role 下发，两者不能同时生效。hook 文件 `oci-hub-boundary.sh` 还写在每台 VM 的配置里。

**建议：** 保留安装路径，或留兼容符号链接，等两边都发布后再移除。

### 19. 配置总览和 AD-2 的细节（low）

- 从零重建第 3 步必须是 `wsctl oci-hub-release --new-hub`，否则 `oci-hub-release.py:79` 抛 `OCI_HUB_RELEASE_NEW_HUB_MISMATCH`。部署合同的顺序是先 `deploy-oci-hub.yml --skip-tags verify`。
- AD-2 的静态参数清单漏了 `pool.pve_address`、`pool.hook_directory`。`pool.device_ingress_mode` 要在迁移时移除，否则和 `terraform/oci` 的同名字段成了两份。
- AD-27 写 `readdress` 会更新 set。这个 Hub 动作存在，但现在 `wsctl` 里没有调用方。
- `boundary.py:172,178,446` 的 `v.get('disabled', True)` 默认值为真。如果 AD-26 决定去掉 `disabled`，这些代码会让 HAPI 放行不渲染、VM 无法启动。

### 20. Stack 行（low）

| 行 | spine | 核对结果 |
| --- | --- | --- |
| bpg/proxmox | 最新 0.120.0 | 正确，2026-11-02 发布 |
| oracle/oci | 8.3.0 | 与 `versions.tf` 一致，2026-02-25 发布；最新已是 9.12.1，无需升级，两个备份资源在 8.3.0 已有 |
| wg-portal | v2.3.1 | 仍是最新 |
| Semaphore | v2.19.17 为最新稳定版 | 已过时，最新 v2.19.18（2026-11-02） |
| ansible-core | 当前 2.20.10 | 上限内最新 2.20.11，上限有文档依据，保持 |
| Python | 与 Mac 3.14.7 一致 | 3.14 最新 3.14.10，未核对执行器实际版本 |

## 按核对项汇总

**bpg/proxmox**

- 已确认：`proxmox_sdn_zone_simple`（`nodes`、`ipam`）、`proxmox_sdn_vnet`（`zone`）、`proxmox_sdn_subnet`（`gateway`、`snat`）、`proxmox_sdn_applier` 均存在，也都支持 import，subnet 的导入 ID 格式与 `pve-sdn.py` 的命名相容。provider 的目标是 PVE 9.x，pve2 记录为 9.2.2。
- `snat=false` 在 provider 验收测试里能读回。但 `pve-sdn.py:48` 把缺失当作 0，说明 PVE 可能不返回该字段，而 provider 读到缺失时是 null，所以导入后要看一次 plan。不写 `snat` 也是不做 SNAT，可作为退路。
- 替代全局锁的方案：没有，见发现 3。

**nftables**

- 已确认：`type ipv4_addr . ipv4_addr` 的命名 set 和 `ip saddr . ip daddr @set` 是文档示例，内核 4.1 起支持；`nft -f` 一个文件是一次事务；`flush set` 和 `add element` 可放在同一文件。
- 四条规则都能改成固定形式：端口和 `ct state`、`ct direction` 仍写在规则里，不进 set。Mosh 范围是常量（`hub-terminal.py` 的 `MOSH_PORT_RANGE`，代码注释写“Hub 总是放行整段”），不需要进元素。
- 配对可以从账本推导：device 行的 `workspace` 指向 workspace 行，后者 `details.address` 就是 overlay，与 `pairs` 的取值相同。只需去掉 `/32`。`identities` 的写入点确实只有 `register`、`retire`、`readdress`。
- 未实测：反向规则用同一 set 交换键序（`ip daddr . ip saddr @pairs`）。类型上成立，但文档没有直接示例，story 用 `nft -c` 验证即可。

**Proxmox 启动顺序**

- 已确认：单元名就是 `pve-cluster.service`，`Type=forking`、`After=network.target`；与现有 `After=network-pre.target`、`Before=pve-guests.service` 没有依赖环。
- 代价：规则加载晚于 `network.target`，但 VM 此时还没启动，没有实际影响。
- 法定人数：`docs/architecture/backup-architecture-consolidation-spec.md` v1.14 记录 pve2 是独立节点，不存在 `corosync.conf`，所以这个问题对 pve2 基本不成立（该记录日期为 2026-09-21）。
- 若以后加入集群：pmxcfs wiki 写无法定人数时 “Read-only”，没有明说读取可用；`pve-network` 的读接口不检查法定人数，只有 `create` 检查。`pve-guests` 的 `startall` 本来就无限期等待法定人数，所以 VM 不会先于规则启动。

**OCI**

- 已确认：Oracle 的 Boot Volume Backups 页面明确提到 “boot volumes with custom backup policies”；两个 Terraform 资源在 8.3.0 已有；`asset_id` 接受卷的 OCID；一个卷只能有一个策略；五份备份是启动卷和块卷合计、限 home region；备份是崩溃一致性的，账本的 SQLite WAL 和 `synchronous=FULL` 可以接受。
- 已确认：Deferred 里“临时 IP 不能原地转成同地址的保留 IP”，与 Oracle 原文一致。
- 未确认：见下节。

**仓库事实**

- 已确认：`registered`、`enabled` 检查点名称准确（`hub-terminal.py:652,654`、`hub-onboard.py:528,534`）。Portal 的 4 个密钥与模板一致；`executor.json` 的字段与 `executor.py` 一致。
- 已确认：`workspace_sources`、`device_sources`、`device_ingress_mode` 在已跟踪的 `oci-hub-ingress.auto.tfvars.json` 中；`configure-oci-hub-mosh-boundary.yml`、`deploy-oci-hub-terminal.yml` 存在；部署合同第 12 行的“固定 bpg 0.70”存在。
- 已确认：预案的文件路径和变量名都存在。Hub IP 在公开仓库的配置里只出现在 inventory 和 Homepage 模板，私有 `*.py` 中没有。
- 已确认：`docs/deployment/oci-hub-ip-change.md` 存在，但尚未被其他文档引用，AD-32 除外。

## 未能确认

| 事项 | 现有证据 | 确认方式 |
| --- | --- | --- |
| 替换启动卷后临时 IP 保留 | Compute 页面只说实例停止、替换、恢复原状态，没提 IP；公网 IP 页面写明删除条件是私有 IP、VNIC 或实例；OKE 页面写 “keeps the same OCID and network address”。推断很强，但没有针对 Compute 的直接说明 | 恢复演练 |
| 替换后 `sourceDetails` 的返回值 | 无文档 | 恢复演练时看 `terraform plan` |
| 本租户支持备份策略 | 已知未确认，AD-32 有备用方案 | 控制台 |
| 现网 VM 的 MAC 是否符合公式 | 只有分配器代码 | 只读核对 `qm config` |
| 反向键序和 `-t -j` 的 nft 行为 | 文档未直接覆盖 | `nft -c` 和一次本地试验 |
| 无法定人数时读 `/etc/pve` | 文档未明说；对独立的 pve2 不适用 | 不需要，除非 pve2 入集群 |
| Jenkins 的 OCI 入口是否已配置 | CI spine 有设计，`Jenkinsfile` 无阶段 | 查 Jenkins 凭据和 `Jenkinsfile-peer` |
| PVE API token 的 SDN 权限 | 无 | 查 token 权限 |
| Sydney 是否 home region、过期备份何时清理 | 无 | 控制台；观察一个周期 |

## 来源

**bpg/proxmox**

- 发布：https://github.com/bpg/terraform-provider-proxmox/releases
- 资源文档：https://github.com/bpg/terraform-provider-proxmox/tree/main/docs/resources
- applier 源码：https://github.com/bpg/terraform-provider-proxmox/blob/main/proxmox/cluster/sdn/applier/applier.go
- CHANGELOG：https://github.com/bpg/terraform-provider-proxmox/blob/main/CHANGELOG.md
- ADR-007：https://github.com/bpg/terraform-provider-proxmox/blob/main/docs/adr/007-resource-type-name-migration.md

**Proxmox**

- SDN 锁与配置：https://github.com/proxmox/pve-network/blob/master/src/PVE/Network/SDN.pm
- SDN API：https://github.com/proxmox/pve-network/blob/master/src/PVE/API2/Network/SDN.pm
- VNet API：https://github.com/proxmox/pve-network/blob/master/src/PVE/API2/Network/SDN/Vnets.pm
- 单元文件：https://github.com/proxmox/pve-manager/blob/master/services/pve-guests.service 、https://github.com/proxmox/pve-cluster/blob/master/debian/pve-cluster.service
- startall：https://github.com/proxmox/pve-manager/blob/master/PVE/API2/Nodes.pm
- pmxcfs：https://pve.proxmox.com/wiki/Proxmox_Cluster_File_System_(pmxcfs)

**nftables**

- Concatenations：https://wiki.nftables.org/wiki-nftables/index.php/Concatenations
- 原子替换：https://wiki.nftables.org/wiki-nftables/index.php/Atomic_rule_replacement
- man page：https://www.netfilter.org/projects/nftables/manpage.html

**OCI**

- 替换启动卷：https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/replacingbootvolume.htm
- 公网 IP：https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingpublicIPs.htm
- 备份策略：https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/schedulingvolumebackups.htm
- 启动卷备份：https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/bootvolumebackups.htm
- 块卷备份：https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumebackups.htm
- 创建启动卷备份：https://docs.oracle.com/iaas/Content/Block/Tasks/backingupabootvolume.htm
- Always Free：https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- OKE 替换启动卷：https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/replace-boot-volume-worker-node-top.htm
- Provider 文档与源码（v8.3.0）：https://github.com/oracle/terraform-provider-oci/tree/v8.3.0

**版本**

- wg-portal：https://github.com/h44z/wg-portal/releases
- Semaphore：https://github.com/semaphoreui/semaphore/releases
- ansible-core：https://pypi.org/project/ansible-core/
- Python：https://endoflife.date/python
