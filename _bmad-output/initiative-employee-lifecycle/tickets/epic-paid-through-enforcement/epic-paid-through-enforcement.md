---
type: epic
title: "付费期限自动执行"
parent: initiative-employee-lifecycle
covers: [R4, R5, R6, R14]
sources: [_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: [epic-executor-platform]
refined: true
risk: high
---

# 付费期限自动执行

## Description

catalog 新增 `paid_through` 与不到期标记；执行器把整份快照推送到 OCI，OCI 上的 reconcile（`oci-hub-quota.timer`）增删 `expired` 原因；执行器每 5 分钟到期关机、续费开机；`wsctl renew` 按续费规则推进日期；上线时完成现有员工初始化。

## Outcome

未续费的员工在月底后自动失去访问，续费后自动恢复，管理员只需记一次续费。

## Requirements

- R1 (parent R5, AD-12): catalog 员工记录可带 `paid_through`（Sydney 月底 23:59:59，带偏移 ISO 8601）；执行器把全体有 `paid_through` 的员工以 `employee_id → paid_through` 整份快照（带单调递增 `generation`，不含邮箱）经 SSH 原子写到 OCI；OCI 拒绝 generation 不大于已接受值的快照。
- R2 (parent R5, AD-9, AD-11): OCI reconcile 对快照中 `now > paid_through` 的员工给 `oci-hub:user:<employee_id>` 加 `expired`，否则移除；只增删 `expired` 与 `quota_exhausted:*`，其他原因原样保留；快照缺失或损坏时沿用上次有效值；快照外的员工不处理。
- R3 (parent R6, AD-16): `wsctl enforce` 对 catalog 中已到期员工的 VM 正常关机（`qm shutdown --timeout 120`，超时强制停止，磁盘保留），并在 employee-data 记录由执行器关机；对已续费且有该记录的员工开机并删除记录；不碰 catalog 以外的 VM，也不开管理员手动关掉的 VM。Semaphore 每 5 分钟运行一次。
- R4 (parent R4, AD-8): `wsctl renew <邮箱> N` 无需确认：未过期在原到期月上加 N 个月，已过期从本月起加，结果为月底；只改 `paid_through` 并推快照。`wsctl provision` 开户时把 `paid_through` 设为当月月底并推快照。
- R5 (parent R14): catalog 员工可标 `no_expiry: true`，此类员工无 `paid_through`、不进快照、不被 enforce 处理；上线时 `pilot`、`control` 标为不到期，其余现有员工初始化为上线当月月底。

## Constraints

- (AD-1) renew、enforce 不创建或删除资源，无需确认；只在执行器上运行（Mac 返回 `WSCTL_WRITES_ON_EXECUTOR`）。
- (AD-2, AD-11) wg-portal 是接入状态权威；人工原因与配额原因不被改写。
- (AD-2) Terraform 不管电源状态。
- (AD-4) OCI reconcile 不调用执行器、Terraform、BWS 或 PVE。

## Done when

- 测试员工 `paid_through` 设为过去后，隧道在一个 timer 周期内断开、VM 5 分钟内关机；renew 后两者恢复。
- 人工停用原因与配额原因在整个过程中不被改写。
- 不到期员工不受影响；现有员工已初始化为上线当月月底。

## Boundaries

- 不做提醒、摘要、退役（epic 4），不做网站（epic 3），不做到期停用 HAPI（epic 6）。
- Touch point: OCI oci-hub 角色与 wg-portal 原因机制，只增加 `expired`。

## References

- parent — _bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md, section Requirements (R4, R5, R6, R14)
- architecture — _bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md, AD-8, AD-9, AD-11, AD-12, AD-16

## Notes

- Waits on epic-executor-platform because: 关机/开机定时任务运行在执行器 VM 的 Semaphore 上。
- Decision: 2026-11-01 不到期用 catalog `no_expiry: true` 表示，不写 `paid_through`、不进快照（AD-9 快照外不处理）。
- Decision: 2026-11-01 续费开机只开执行器因到期关掉的 VM（employee-data 记录），不开管理员手动关掉的 VM；细化 AD-16 字面"已续费的员工开机"。
- Decision: 2026-11-01 关机先 `qm shutdown --timeout 120`，超时强制停止。
- Decision: 2026-11-01 AD-16 中到期停用 HAPI 归 epic 6，本 epic 不做。
- Decision: 2026-11-01 拆为 5 个 story；tracer bullet 为 #1（catalog → 快照 → OCI reconcile → Portal `expired`）；#2 enforce 为最不确定项排第二；初始化（#4）放最后，此前快照只含测试员工，不影响他人；保留收尾 Refactor sweep（#5）。
