---
title: 'wsctl status 显示推导状态、到期日与孤儿资源'
type: 'feature'
ticket: '1'
created: '2026-11-01'
status: 'done'
baseline_revision: 'a1baac3f0be847f87ed7f5c6523955230bf6115c'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `wsctl status` 只列连接与原因，管理员看不出谁到期、谁可退役，也发现不了多余的 VM。

**Approach:** 在 `hub-status.view` 的结果中为每名员工加 `lifecycle`（`active` / `disabled` / `expired` / `retirable` / `no_expiry`）与 `paid_through`；新增顶层 `orphans`（Terraform 清单或 PVE 上的员工 VM 在 catalog 里没有，或 catalog 员工在清单里没有）与 `remind_pending`（7 天内到期、未续费、非不到期的人数）。状态只推导、不存储（AD-3）。

**Decision:** 2026-11-01 用户同意 epic 4 拆分；"可退役"= `now > paid_through + 3 天`；PVE 侧孤儿只看 pve2 上 `oci-hub-` 前缀名称的 VM。

## Boundaries & Constraints

**Always:** 状态优先级：`no_expiry`（catalog 标记）> `retirable` > `expired`（`now > paid_through`）> `disabled`（用户或任一设备有非 `expired` 的停用原因）> `active`；时间按 Sydney 计算比较（用 `hub-expiry` 现有的解析与时区工具）；catalog 员工在 Terraform 清单里缺失时不再整体报错（现有 `HUB_STATUS_CATALOG_VM_MISSING`），改为该员工 `lifecycle='orphan'` 并进 `orphans`（`kind='catalog_without_vm'`）；清单有而 catalog 无 → `kind='vm_without_catalog'`（含 employee_id、vmid）；PVE（`pvesh get /cluster/resources --type vm`）上名称形如 `oci-hub-*` 而清单与 catalog 都没有 → `kind='pve_vm_without_record'`；PVE 查询失败时 `orphans_error='PVE_QUERY_UNKNOWN'`，不中断；只读。

**Never:** 不写任何系统；不改提醒、退役（4.2–4.4）；不改 registry 视图文件格式以外的东西（`registry_view` 仍保存结果）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 正常 | pt 未到、无原因 | active | — |
| 人工停用 | Portal 原因 admin_disabled | disabled | — |
| 已到期 | now > pt，≤ 3 天 | expired | — |
| 可退役 | now > pt + 3 天 | retirable | — |
| 不到期 | no_expiry | no_expiry | — |
| 待提醒 | pt 在 7 天内、未到期 | 计入 remind_pending | — |
| 清单无员工 | catalog 有、清单无 | 员工 lifecycle=orphan；orphans 一条 | 不抛错 |
| 多余 VM | 清单有、catalog 无 | orphans 一条 vm_without_catalog | — |
| PVE 野 VM | PVE 有 oci-hub-x，两边都无 | orphans 一条 pve_vm_without_record | PVE 查询失败 → orphans_error |

</frozen-after-approval>

## Code Map

私有代码 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交）。不 commit、不 push。

- `hub-status.py` `view()` -- 现有循环与结果组装；`terminal.root_roster`、`terminal.catalog`、`terminal.bind_vm`、`terminal.ssh`（PVE 目标 `settings['oci_hub']['terminal']['pve_ssh_target']`）。
- `hub-expiry.py` -- `enforced(row)`、`SYDNEY`、paid_through 解析方式。
- 测试：新增 `test-hub-status.py`（打桩 admin.remote、terminal.ssh、h.terraform_snapshot 等，覆盖矩阵）；如有现有 status 测试一并更新。

## Tasks & Acceptance

**Execution:**
- [x] `hub-status.py`、`test-hub-status.py` -- 推导状态、孤儿、待提醒
- [x] 部署与实测（hitl，主会话）-- push；执行器 `wsctl status` 显示 6 人 active、2 人 no_expiry、orphans 为空

**Acceptance Criteria:**
- Given 当前执行器数据，when `wsctl status`，then 每人有 lifecycle 与 paid_through，pilot/control 为 no_expiry，orphans 为空。

## Implementation Notes

- `load` 提到模块级 `load(base,name)`，便于测试打桩；`view()` 额外加载 `hub-expiry`，用其 `enforced()` 判定是否到期、`SYDNEY` 计算 3 天宽限（宽限按 Sydney 日历日相加，再与 UTC 现在比较，跨夏令时仍为 3 天）。
- `disabled` 判定忽略 `expired` 与 `not_registered`（后者是视图自己的占位值，不是 Portal 原因），只看用户与设备原因，不看 workspace 原因（按计划）。
- `orphan` 优先于其余状态；orphan 行只有 `employee_id`、`recipient`、`vmid`、`lifecycle`、`paid_through`，不查电源/会话。
- `paid_through` 输出推导值（`enforced` 时为 catalog 值，`no_expiry` 为 None）。无法解析或无时区的 paid_through 只把该员工标为 `lifecycle='invalid'`、`lifecycle_error='HUB_STATUS_PAID_THROUGH_INVALID'`，其余照常；orphan 优先于 invalid。
- `remind_pending`：非 orphan、非 invalid，`enforced` 且 `now <= paid_through <= now+7天`。
- 孤儿容忍与 PVE 查询只在 status 路径（`sessions=True`，即 `online`）；`registry`/`verify` 仍抛 `HUB_STATUS_CATALOG_VM_MISSING`，结果不含 `orphans` 键。PVE 只把查询/解析放在 try 里，失败时不加任何 pve 条目；缺 name/vmid 的条目显式跳过。
- PVE：`pvesh get /cluster/resources --type vm --output-format json`，只取 `node=='pve2'` 且名称以 `oci-hub-` 开头；名称后缀与 vmid 都不在清单/catalog 中才算野 VM。

- 2026-11-01 部署 cc414e6；执行器 `wsctl status`：control/pilot no_expiry（paid_through 空），其余 6 人 active、2026-11-30T23:59:59+11:00，全部 running；orphans []、无 orphans_error（PVE 查询正常）、remind_pending 0。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick) + 主会话: high 0 / medium 2 / low 3 / rejected 1
  - medium, patch（主会话）— 单个员工 paid_through 无效会让整个 status 失败：只把该员工标 invalid。
  - medium, patch — registry/verify 与 status 共用 view，孤儿容错让 registry/verify 失去原有硬失败：容错只用于 status。
  - low, patch — no_expiry 员工 paid_through 显示原始值：输出推导值。
  - low, patch — 孤儿被计入 remind_pending：排除。
  - low, patch — PVE 查询的 except 范围过大、可能留下半截列表：只包查询。
  - rejected — "AC 依赖 catalog 数据"：评审看的是 Mac 上的旧 catalog；执行器 catalog 已在 2.4 标好 pilot/control 为 no_expiry、6 人有 paid_through。

## Verification

**Commands:**
- `cd remotecc/employee-admin && for t in test-hub-status.py test-hub-expiry.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: OK

**Result (2026-11-01, review fixes):** test-hub-status 9 OK；初版 8 / 25 / 24 tests OK（test-wsctl 的两个 Secrets 用例需在 Claude 沙箱外运行，沙箱禁止 ssh-agent 绑定 unix socket）。部署与执行器实测未做（hitl）。
