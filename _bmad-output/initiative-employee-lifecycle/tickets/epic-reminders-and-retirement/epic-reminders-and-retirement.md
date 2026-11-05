---
type: epic
title: "提醒、摘要与批量退役"
parent: initiative-employee-lifecycle
covers: [R7, R8, R9, R11]
sources: [_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: [epic-paid-through-enforcement, epic-apply-site]
refined: true
risk: medium
---

# 提醒、摘要与批量退役

## Description

wsctl remind 每日由 Semaphore 运行，给未续费员工发提醒、给管理员发摘要（新申请、可退役、孤儿资源）；wsctl status 显示推导状态、孤儿资源与待提醒人数；wsctl retire 批量列出可退役员工，一次确认后逐个复查并删除。

## Requirements

- R1 (parent R11, AD-3, AD-14): `wsctl status` 为每名员工输出推导状态（正常 / 已停用 / 已到期 / 可退役 / 不到期）、到期日；输出孤儿资源（Terraform 清单或 PVE 有员工 VM 而 catalog 无员工，或反之）与待提醒人数。
- R2 (parent R7, AD-14): `wsctl remind` 给 `paid_through` 落在 7 天内（Sydney）且未续费、非不到期的员工发一封提醒邮件（执行器 Microsoft 邮件通道），同一员工同一 `paid_through` 只发一次；Semaphore 每天运行。
- R3 (parent R8, AD-14): 同一次 `wsctl remind` 每天给管理员 fanweiblue@gmail.com 发摘要：新申请、可退役员工、孤儿资源、3 天内到期；Semaphore 每天 08:00 Sydney 运行。
- R4 (parent R9, AD-10): `wsctl retire` 列出所有可退役员工（`now > paid_through + 3 天`，非不到期）及每人将删除的内容，一次确认（同一 SHA）后逐个执行：执行前复查 `paid_through`，已续费跳过；删除顺序 Portal 用户与设备 → Terraform VM → BWS 员工密钥 → 网站设备包 → catalog，最后推送快照；中断后按运行记录续跑；不备份。HAPI 部分由 epic 6 补充。

## Outcome

管理员不必盯着日历：提醒自动发出，多余资源每天出现在摘要里，退役一次确认完成。

## Done when

- 测试员工在到期月收到且只收到一封提醒；管理员摘要列出新申请、可退役员工与人为制造的孤儿 VM。
- retire 一次确认删除可退役测试员工的 Portal、Terraform、BWS、网站设备包、catalog 记录，已续费者被跳过。
- 不到期员工从不出现在提醒与可退役名单中。

## Boundaries

- 退役不自动执行，不备份。

## References

- parent — _bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md, section Requirements (R7, R8, R9, R11)
- architecture — _bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md, AD-3, AD-10, AD-14

## Notes

- Decision: 2026-11-01 提醒在到期前 7 天发；用执行器 Microsoft 邮件通道；摘要每天 08:00 Sydney 发 fanweiblue@gmail.com；R17（uniCloud 到期提醒）移到 epic 5；退役的 HAPI 部分留给 epic 6；退役实测用临时测试员工（会真实创建并销毁 pve2 上一台 VM）（用户同意）。
- Decision: 2026-11-01 拆为 5 个 story：status 推导 → remind → 摘要 → retire → sweep；tracer 为 #1。

- Waits on epic-paid-through-enforcement because: 提醒与可退役判断依赖 paid_through 与不到期标记。
- Waits on epic-apply-site because: 摘要列出网站新申请，退役要删除 R2 设备包。
