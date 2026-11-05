---
type: initiative
title: 员工工作区生命周期串联（开户-管理-维护）
parent: none
sources: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: []
risk: high
---

# 员工工作区生命周期串联（开户-管理-维护）

## Description

把员工工作区从申请、开户、按月续费、到期提醒与断开、到退役串成一条由唯一执行器驱动的生命周期。员工在 `cc.willfan.me` 申请并下载设备包；收费在线下完成，系统只记录付到哪天；执行器与 Semaphore 常驻 pve0 上的专用 VM，提醒、断开、关机自动完成，开户、续费、退役由管理员在 Semaphore 中各确认一次。设计依据是已定稿的架构主干。

## Outcome

管理员不再依赖 Mac 在线和手工记账：一名员工从申请到退役的全过程可在 Semaphore 中完成，未续费的员工在月底自动失去访问。

## Requirements

- R1 (AD-13): 员工可在 `cc.willfan.me` 用手机浏览器查看工作区规格并提交申请（邮箱、姓名、手机号）；提交经 Turnstile 校验并按 IP 限频；提交成功的申请出现在 `wsctl request` 的结果中。
- R2 (AD-6, AD-1): 管理员可从一条已拉取的申请开户，只需一次确认；开户后该员工的 `paid_through` 为当月月底（Sydney），并收到设备包下载邮件。
- R3 (AD-17): 员工可经邮件中的链接下载设备包：24 小时内有效、最多 3 次、需点击按钮触发，下载满或过期后文件被删除；不再使用 Temp.sh。
- R4 (AD-8): 管理员可用一条无需确认的命令为员工续 N 个月：未过期则在原到期月上加 N 个月，已过期则从本月起加，结果为月底。
- R5 (AD-9, AD-11): `paid_through` 过后，该员工的隧道接入在一个 OCI timer 周期内断开，续费后在同样时限内恢复；人工停用原因与配额原因保持不变。
- R6 (AD-16): `paid_through` 过后 5 分钟内该员工 VM 关机，续费后 5 分钟内开机，磁盘保留；不影响 catalog 以外的 VM。
- R7 (AD-14): 每天自动给 `paid_through` 为本月底且未续费的员工发提醒邮件，同一员工同一 `paid_through` 只发一次。
- R8 (AD-14): 管理员每天收到摘要邮件，列出新申请、可退役员工（`now > paid_through + 3 天`）和孤儿资源（有 VM 无 catalog 记录，或反之）。
- R9 (AD-10): 管理员可一次确认批量退役全部可退役员工；执行前逐个复查 `paid_through`，已续费者跳过；退役后 Portal、Terraform、BWS、R2、catalog 中均无该员工，不备份。
- R10 (AD-17, AD-1): 管理员可为员工重发设备包，生成新的下载链接与邮件。
- R11 (AD-3, AD-14): `wsctl status` 显示每个员工的推导状态（正常/已停用/已到期/可退役）、到期日、孤儿资源与待提醒人数；在 wg-portal 页面手工停用后，状态立即反映。
- R12 (AD-15): 执行器与 Semaphore 运行在 pve0 上的专用 VM；管理员从浏览器经 Semaphore 完成 R2、R4、R9、R10、R11 的操作；Mac 关机时 R6、R7、R8 照常执行。
- R13 (AD-1): `wsctl` 取代 `onboard.sh` 成为唯一入口，不再需要 `--profile`；过渡期 `onboard.sh` 转发到 `wsctl`。
- R14 (Decision 2026-10-31): catalog 中可将员工标记为不到期，被标记者不受 R5–R9 的提醒、断开、关机、退役影响；到期功能上线时，其余现有员工的 `paid_through` 初始化为当月月底。
- R15 (AD-18): 员工可在微信小程序经微信登录查看规格、提交申请，并查看自己的状态与到期日；提交按 openid 限频；小程序不出现收费字样。
- R16 (AD-19): 两个入口的申请出现在同一份 `wsctl request` 结果中；同一邮箱跨入口只算一条；处理结果只回写来源入口；任一入口不可用时，另一入口与开户照常。
- R17 (AD-14): 管理员每日摘要显示 uniCloud 免费空间到期日，不足 7 天时提醒续期。
- R20: 网站同样提供员工自助查看：员工经邮箱验证码登录后查看自己的状态与到期日；网站与小程序的文案、视觉风格保持一致（规格说明、申请须知、状态与到期日的表述同一套）。
- R21: 员工用一条命令 `mosh <主机名>` 登录自己的工作区（设备包把别名与端口写入员工本机配置）；员工看到的 hostname 不带 `oci-hub-` 前缀，PVE 中的 VM 名仍为 `oci-hub-<员工ID>`。hostname 格式为 `<用户名>-vm`（如 `alice-vm`，不含规格，升降规格不改名；2026-11-02 管理员确定）；SSH 别名与 hostname 相同；登录用户保持 `employee`。
- R18 (AD-20): 开户默认同时启用 WireGuard 与 HAPI。WireGuard 可在 wg-portal 单独停用，不影响 HAPI；HAPI 没有单独开关，员工在册且未到期即可使用。
- R19 (AD-16, AD-20): `paid_through` 过后 5 分钟内该员工的 HAPI 被停用，续费后恢复；退役后 VM500 与 Cloudflare Access 中没有该员工的 HAPI 记录。

## Constraints

- (AD-1) 跨系统写入只经 `wsctl`；创建或删除资源须计划 → 确认 → 以同一 SHA 执行，fail-closed。
- (AD-2, AD-11) wg-portal 是接入状态的唯一权威；执行器只增删自己的原因，不覆盖人工操作。
- (AD-2) Terraform 管 VM 存在与规格，不管电源状态。
- (AD-4, AD-15) 执行器 VM 无公网入站；申请网站与 OCI 不调用家中任何服务。
- (AD-8) 计费边界一律按 `Australia/Sydney`，到期为月底 23:59:59，无宽限期；收款在线下进行，系统不记录收款。
- (AD-12) `paid_through` 以整份快照（带递增 generation）推送到 OCI，快照不含邮箱与凭据。
- (AD-10) 退役永不自动执行；VMID、网卡槽位、overlay 地址永不回收。
- (AGENTS.md) 运行数据在 `employee-data`，私有代码在 `remotecc/`，不进公开仓库；员工私钥在 BWS `EmployeeWorkspace-OCIHub`。

## Done when

- 一名测试员工从网站申请、开户、下载设备包到登录 VM，全程只在 Semaphore 和邮件中完成。
- 把测试员工的 `paid_through` 设为过去时间后，5 分钟内隧道断开且 VM 关机；续费后两者恢复。
- 连续一天 Mac 关机期间，提醒邮件与管理员摘要照常送达。
- 对一名可退役测试员工执行退役后，`wsctl status` 不再列出该员工，也没有孤儿资源。
- 现有 oci-hub 工作区迁移后都能重新接入：`pilot`、`control` 标记为不到期，其余员工的 `paid_through` 为上线当月月底。

## Boundaries

- 不做在线收费、网站上的员工状态查询、自动退役。
- 不改 wg-portal 的部署与 Portal 原因机制本身，只增加 `expired` 原因的使用。
- Must not change: 现有员工的设备身份；迁移期间不重发设备包。
- Tracer path: 网站申请 → `wsctl request` → `provision` → 下载 → `renew` → 到期断开与关机 → `retire`。

## References

- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`，Invariants & Rules（AD-1 至 AD-17）、Structural Seed、Deferred
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
