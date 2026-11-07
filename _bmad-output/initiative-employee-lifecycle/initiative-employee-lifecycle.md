---
type: initiative
title: 员工工作区生命周期串联（开户-管理-维护）
parent: none
sources: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md, docs/deployment/oci-hub-ip-change.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md, docs/deployment/oci-hub-ip-change.md]
after: []
risk: high
---

# 员工工作区生命周期串联（开户-管理-维护）

## Description

把员工工作区从申请、开户、按月续费、到期提醒与断开、到退役串成一条由唯一执行器驱动的生命周期。员工在 `cc.willfan.me` 申请并下载设备包；收费在线下完成，系统只记录付到哪天；执行器与 Semaphore 常驻 pve0 上的专用 VM，提醒、断开、关机自动完成，开户、退役由管理员在 Semaphore 中批准，续费无需批准。2026-11 的架构更新进一步收拢配置来源：静态配置归 IaC，VM 记录归 D1，防火墙从主机对象派生，OCI Hub 有定期备份并能原地恢复。设计依据是已定稿的架构主干。

## Outcome

管理员不再依赖 Mac 在线和手工记账：一名员工从申请到退役的全过程可在 Semaphore 中完成，未续费的员工在月底自动失去访问；OCI Hub 丢失后能从备份恢复，它的配置不再只存在于线上文件。

## Requirements

- R1 (AD-13): 员工可在 `cc.willfan.me` 用手机浏览器查看工作区规格并提交申请（邮箱、姓名、手机号）；提交经 Turnstile 校验并按 IP 限频；提交成功的申请出现在 `wsctl request` 的结果中。
- R2 (AD-6, AD-1): 管理员可从一条已拉取的申请开户：新 VM 共 3 次批准（建 VM、配置、上传设备包并发开通邮件）；开户后该员工的 `paid_through` 为当月月底（Sydney），并收到开通邮件。
- R3 (AD-17, Decision 2026-11-07): 员工登录网站后在“我的工作区”下载设备包，不限次数；邮件不带设备包和下载链接；设备包与 VM 同寿命，保存到员工退役或被同设备的新包替换；不再使用 Temp.sh。
- R4 (AD-8): 管理员可用一条无需确认的命令为员工续 N 个月：未过期则在原到期月上加 N 个月，已过期则从本月起加，结果为月底。
- R5 (AD-9, AD-11): `paid_through` 过后，该员工的隧道接入在一个 OCI timer 周期内断开，续费后在同样时限内恢复；人工停用原因与配额原因保持不变。
- R6 (AD-16): `paid_through` 过后 5 分钟内该员工 VM 关机，续费后 5 分钟内开机，磁盘保留；不影响 catalog 以外的 VM。
- R7 (AD-14): 每天自动给 `paid_through` 为本月底且未续费的员工发提醒邮件，同一员工同一 `paid_through` 只发一次。
- R8 (AD-14): 管理员每天收到摘要邮件，列出新申请、可退役员工（`now > paid_through + 3 天`）和孤儿资源（有 VM 无 catalog 记录，或反之）。
- R9 (AD-10): 管理员可一次确认批量退役全部可退役员工；执行前逐个复查 `paid_through`，有人已续费时整批拒绝（`RETIRE_REPLAN_REQUIRED`），重新计划后不含此人；退役后 Portal、Terraform、BWS、网站设备包、catalog 中均无该员工，不备份。
- R10 (AD-17, AD-1, Decision 2026-11-07): 管理员可为员工重发设备包：重新上传原包并发通知邮件，不换密钥，邮件不带下载链接。
- R11 (AD-3, AD-14): `wsctl status` 显示每个员工的推导状态（正常/已停用/已到期/可退役）、到期日、孤儿资源与待提醒人数；在 wg-portal 页面手工停用后，状态立即反映。
- R12 (AD-15): 执行器与 Semaphore 运行在 pve0 上的专用 VM；管理员从浏览器经 Semaphore 完成 R2、R4、R9、R10、R11 的操作；Mac 关机时 R6、R7、R8 照常执行。
- R13 (AD-1): `wsctl` 是唯一入口，不再需要 `--profile`；`onboard.sh` 已于 2026-11-04 删除。
- R14 (Decision 2026-10-31): catalog 中可用 `no_expiry` 将员工标记为不到期，被标记者不受 R5–R9 的提醒、断开、关机、退役影响；到期功能上线时，其余现有员工的 `paid_through` 初始化为当月月底。
- R15 (AD-18): 员工可在微信小程序经微信登录查看规格、提交申请，并查看自己的状态与到期日；提交按 openid 限频；小程序不出现收费字样。
- R16 (AD-19): 两个入口的申请出现在同一份 `wsctl request` 结果中；同一邮箱跨入口只算一条；处理结果只回写来源入口；任一入口不可用时，另一入口与开户照常。
- R17 (AD-14): 管理员每日摘要显示 uniCloud 免费空间到期日，不足 7 天时提醒续期。
- R20 (AD-21): 网站同样提供员工自助查看：员工经邮箱验证码登录后查看自己的状态与到期日；网站与小程序的文案、视觉风格保持一致（规格说明、申请须知、状态与到期日的表述同一套）。
- R21 (Decision 2026-11-02, Decision 2026-11-04): 员工用一条命令 `mosh <员工ID>-vm` 登录自己的工作区（设备包把别名与端口写入员工本机配置）；SSH 别名相同，登录用户保持 `employee`；VM 系统 hostname 与 PVE VM 名都保持 `oci-hub-<员工ID>`。
- R18 (AD-20): 开户默认同时启用 WireGuard 与 HAPI。WireGuard 可在 wg-portal 单独停用，不影响 HAPI；HAPI 没有单独开关，员工在册且未到期即可使用。
- R19 (AD-16, AD-20): `paid_through` 过后 5 分钟内该员工的 HAPI 被停用，续费后恢复；退役后 VM500 与 Cloudflare Access 中没有该员工的 HAPI 记录。
- R22 (AD-25, AD-31): 管理员只凭 IaC 与 Vault 就能重跑 `oci-hub`、`oci-hub-pve` role，结果与线上一致；静态网络参数只在一份不含插值的变量文件里，settings 不再保存，`wsctl` 只读。
- R23 (AD-28): VM 记录存于 D1，开户时先于 Terraform 写入，退役时先于 Terraform 删除；var-file 每次运行时生成，roster 文件退役；读取失败时不生成 var-file；切换前后完整 plan 没有意外差异。
- R24 (AD-29): 员工 VM 的 VNet 和子网与 VM 由同一份 Terraform 输入创建和删除，`pve-sdn.py` 退役；导入现有对象后 plan 没有差异。
- R25 (AD-26): PVE 防火墙从本机 SDN 和 VM 配置派生，不存在员工层文件；对象不符合 VMID 算法的 VM 被拒绝启动；切换前新渲染结果与线上规则一致。
- R26 (AD-27, AD-13): OCI Hub 的设备与工作区配对来自 D1，是 nft set 的元素；开户、退役、改址后立即生效；set 未填入时设备与 VM 不通，读取失败时现有元素不变。
- R27 (AD-26, AD-27, AD-30): `firewall.py`（原 `boundary.py`）只由 `oci-hub`、`oci-hub-pve` role 下发，`wireguardusrmgr.py`（原 `executor.py`）改名同时完成；开户与退役流程不再复制代码，`configure-oci-hub-mosh-boundary.yml` 退役。
- R28 (AD-32): OCI Hub 启动卷按 Terraform 自定义策略每周备份、保留 4 周，手动备份一并计入 5 份免费额度；策略分配失败时改由定时任务调 OCI API，不放在执行器上；Hub 实例不能被 Terraform 误删。
- R29 (AD-32): 管理员可在同一实例上替换启动卷恢复 OCI Hub；恢复期间 WireGuard 入站保持隔离，按 D1 双向对账全部通过后才解除；恢复报告列出回退的数据；演练证明替换后公网 IP 不变。
- R30 (AD-32, oci-hub-ip-change): 公网 IP 变化时，管理员可按新 `endpoint` 批量重建设备包并批量重跑员工 VM 的 `oci-hub-spoke`。

## Constraints

- (AD-1) 跨系统写入只经 `wsctl`；创建或删除资源须计划 → 确认 → 以同一 SHA 执行，fail-closed；OCI timer 只做本机写入（Portal 原因、配额账本、配对 set）。
- (AD-2, AD-11) wg-portal 是接入状态的唯一权威；执行器只增删自己的原因，不覆盖人工操作。
- (AD-2, AD-28) VM 存在与规格归 D1 的 VM 记录，落地前仍是 roster；Terraform 按运行时生成的 var-file 落地，不管电源状态。
- (AD-4, AD-15) 执行器 VM 无公网入站；申请网站与 OCI 不调用家中任何服务；OCI Hub 只可用只读令牌读取网站配对接口。
- (AD-8) 计费边界一律按 `Australia/Sydney`，到期为月底 23:59:59，无宽限期；收款在线下进行，系统不记录收款。
- (AD-12) `paid_through` 以整份快照（带递增 generation）推送到 OCI，快照不含邮箱与凭据。
- (AD-10) 退役永不自动执行；VM 记录的条件删除是提交点；退役运行完成并核验后，VMID、网卡槽位、overlay 与设备地址才回到池中。
- (AGENTS.md) 运行数据在 `employee-data`，私有代码在 `remotecc/`，不进公开仓库；员工私钥在 BWS `remotecc`。
- (AD-25) 不随员工变化的 infra 和 OS 配置进 IaC，随员工变化的数据不进 Git；值进公开仓库前逐项判断，不宜公开的放 Vault。
- (AD-30) 跑 role 前必须确认执行器 `/srv/iac` 是最新的；`iac.git` 部署钩子持 `wsctl` 运行锁，运行中不换代码，计划摘要包含 IaC commit。
- (AD-31) 密钥迁入 Vault 属凭据改动，需单独授权。

## Done when

- 一名测试员工从网站申请、开户、下载设备包到登录 VM，全程只在 Semaphore 和邮件中完成。
- 把测试员工的 `paid_through` 设为过去时间后，5 分钟内隧道断开且 VM 关机；续费后两者恢复。
- 连续一天 Mac 关机期间，提醒邮件与管理员摘要照常送达。
- 对一名可退役测试员工执行退役后，`wsctl status` 不再列出该员工，也没有孤儿资源。
- 现有 oci-hub 工作区迁移后都能重新接入：`pilot`、`control` 标记为不到期，其余员工的 `paid_through` 为上线当月月底。
- 线上 `boundary.json` 和 roster 文件删除后，开户和退役各跑通一次，防火墙规则与切换前等价。
- OCI Hub 恢复演练通过：替换启动卷后公网 IP 不变，对账通过后才解除隔离。
- 用测试员工和测试 `endpoint` 跑一次全量切换，设备包和 VM 配置都指向新地址，不影响真实员工。

## Boundaries

- 不做在线收费、自动退役。
- 不做保留公网 IP、PVE 规则改 nft set、执行器 IaC 自动同步、OCI Hub 从零重建、执行器和 D1 的恢复（架构 Deferred）。
- 不改 Portal 原因机制本身，只增加 `expired` 原因的使用；`portal.yaml` 按 AD-31 改由 IaC 生成。
- Must not change: 现有员工的设备身份；迁移期间不重发设备包。
- Touch point: `terraform/proxmox` 与共享模块 `proxmox-vm` — provider 升级要核实；owner: epic-vm-records-and-sdn
- Touch point: 同机的 Anki、unified-proxy、BookOrbit — 恢复时一起回退，恢复前确认空闲；owner: epic-hub-recovery
- Tracer path: 网站申请 → `wsctl request` → `provision` → 下载 → `renew` → 到期断开与关机 → `retire`。

## References

- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`，Invariants & Rules（AD-1 至 AD-32，AD-7 已退役）、Structural Seed、配置总览、Deferred
- oci-hub-ip-change — `docs/deployment/oci-hub-ip-change.md`，公网 IP 变更预案
- architecture memlog — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/.memlog.md`，在线收费调研结论

## Notes

- Decision: 2026-10-31 现有工作区的 `paid_through` 在到期功能上线时统一设为当月月底；`pilot`、`control` 标记为不到期（R14）。
- Decision: 2026-10-31 当前没有生产用户，迁移到执行器 VM 期间允许员工掉线；仍不得出现 Mac 与新执行器并发写，也不重发设备包。
- Decision: 2026-10-31 拆为 4 个 epic（执行器平台 → 付费期限 ∥ 申请网站 → 提醒与退役），按"一起交付、一起上线的能力"切分；用户原提的"wsctl 改名与交互确认"并入 epic 1，"renew 与快照"并入 epic 2。共享决定以架构主干 AD-1..AD-17 为准，不再单独跑架构。
- Decision: 2026-11-02 用户在设计稿评论中要求：登录命令简化为 `mosh <主机名>`；面向员工的 hostname 去掉 `oci-hub-` 前缀，VM 名保留。新增 R21，归 epic 5（5.10）。
- Decision: 2026-11-02 用户决定暂不上线微信小程序，R15、R16 中小程序部分、R17 延后；员工入口本期只有网站。
- Decision: 2026-11-02 用户要求员工自助查看状态不只在小程序，网站也提供；两边文案与风格一致。新增 R20，归 epic 5。
- Decision: 2026-10-31 网站与微信小程序两个入口并行；小程序个人主体备案，后端 uniCloud 支付宝云免费空间（每月手动续期）；新增 epic 5"小程序入口"，覆盖 R15、R16；R17 归 epic 4。架构主干新增 AD-18、AD-19。
- Decision: 2026-10-31 HAPI 与 WireGuard 是同一 VM 的两种接入，默认都开；到期主动停用 HAPI；HAPI 不设独立管理凭据，`remotecc/hapi-admin` 并入 wsctl。新增 epic 6"HAPI 接入并入 wsctl"，覆盖 R18、R19，依赖 epic 1 与 epic 2。架构主干新增 AD-20。
- Decision: 2026-11-05 用户取消单独的 HAPI 开关，R18 按此修订；紧急时直接关 VM。
- Decision: 2026-11-04 用户决定 VM 系统 hostname 保持 `oci-hub-<员工ID>`，不做 5.14；R21 按此修订，员工登录别名 `<员工ID>-vm` 不变。
- Decision: 2026-11-07 用户在 WILL-106 验收架构更新，AD-25 至 AD-32 进入本 initiative，新增 R22 至 R30；Boundaries 里“网站上的员工状态查询”按 R20 和 AD-21 删除。
- Decision: 2026-11-07 用户确认设备包只在“我的工作区”下载，不随邮件发送，有效期与 VM 相同；R2、R3、R10 按此修订，AD-17 由架构师补改。
- Decision: 2026-11-07 用户同意把 R14 的 `no_expiry`、R21 的登录别名和 AD-17 的新规则补进架构主干，由架构师执行。
- Decision: 2026-11-07 用户批准清理已知残留，见 `_bmad-output/backlog/story-oci-hub-residual-cleanup.md`；`configure-oci-hub-portal-public.yml` 早已删除，无需处理。
- Assumption: 暂缓的 RemoteCC IaC 迁移（`_bmad-output/backlog/story-remotecc-iac-files-moved-to-private-repo.md`）恢复前，epic 9 至 11 按文件留在公开仓库规划；恢复时这些 epic 的路径要重新核对。
- Decision: 2026-11-07 用户批准切分：新增 epic 8 至 12，共 27 个 story，按“一起交付、一起上线的能力”切分；依据 AD-25 至 AD-32，AD-32 的备份部分先行，恢复部分最后。
- Decision: 2026-11-07 用户确认把记录已完成的 5.11、5.13、5.17、5.19、5.20、5.21、5.23、5.24、5.26、5.27 和 epic 7 全部 story 标为 done，5.14 标为 dropped。
- Decision: 2026-11-07 用户决定修代码：已到期后打 `no_expiry` 的员工要自动清除 `expired`，见 `_bmad-output/backlog/story-no-expiry-clears-expired.md`；修好前 AD-8 的例外（打标前先续费）仍然有效。
- Open question: AD-16 要求续费开机，又不能把人工关闭的 VM 开回来，但没有事实能区分两种关机（WILL-117 两路跨模型审查都判 high）。用户 2026-11-07 表示还没考虑过手动关机的场景，暂不决定；现有行为不变，已切的 story 不依赖它。
- Decision: 2026-11-07 用户同意收紧 AD-27：相同 generation 的配对内容必须相同，由架构师在 WILL-117 写入主干。
- Decision: 2026-11-07 WILL-117 验收：主干 `3c632a0933f0feed`（PR #285）。两路跨模型审查第 2 轮仍不通过，送审版本 `94fab3a547b82c21` 与交付版本不一致，未再审；分诊在 `reviews/triage-will-117.md`。不再加审查轮次，余下问题由 `_bmad-output/backlog/story-spine-revision-before-vm-records.md` 承接，阻塞 10.3 和 12.2。
- Source conflict: R2 要一次确认，代码和文档是分步审批（R2-H4）。WILL-115 合并了上传和发信的批准，核对后在上面这张票定改 R2 还是改 AD-6。
- Decision: 2026-11-07 用户决定 `wsctl retire` 删除执行器上含私钥的 `device-bundle.zip`，见 `_bmad-output/backlog/story-retire-deletes-executor-bundle.md`。
- Decision: 2026-11-07 用户确认只有一套生产环境，测试靠测试员工隔离；由 `_bmad-output/backlog/story-spine-revision-before-vm-records.md` 写入主干。
- Decision: 2026-11-07 用户在 WILL-112 接受 R2、R9 的现状，文本按实现修订：开户 3 次批准；有人已续费时退役整批拒绝。
- Decision: 2026-11-07 `wsctl renew`、`wsctl retire` 的 Semaphore 模板（WILL-114，PR #280）和 `wsctl deliver` 一次批准（WILL-115，PR #284）已部署，这些路径线上还没运行过。
- Decision: 2026-11-07 用户确认 D1 是 single source of truth。5.27 没做的“Terraform 名单从 D1 生成”由 10.3 接手，不另开票。
- Decision: 2026-11-07 用户决定退役时清除 Hub 会话数据，并做一次完整生命周期测试，见 `_bmad-output/backlog/story-retire-clears-hub-sessions.md`、`story-lifecycle-e2e-acceptance.md`。实施要另行授权。
