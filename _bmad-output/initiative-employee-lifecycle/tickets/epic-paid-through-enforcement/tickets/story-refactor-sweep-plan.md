---
title: 'Refactor sweep'
type: 'refactor'
ticket: '5'
created: '2026-11-01'
status: 'done'
baseline_revision: 'cf4e6bde97f2f8a7b8bec8859f9351b90d13a3a6'
route: 'oneshot'
route_source: 'auto'
risk: 'low'
review: 'none'
review_source: 'auto'
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 2.4 评审发现 OCI 快照与执行器 enforce 各自判断"谁会到期"，两处不一致导致不到期员工残留 pt 时仍被关机。

**Approach:** 把判定收为 `hub-expiry.enforced(row)`，快照与 enforce 共用；不改行为。

</frozen-after-approval>

## Implementation Notes

本 epic 推迟项（快照外员工残留 expired、renew 使在途开户失效）均为行为变更，按 sweep 规则不在此处理，已在 deferred-work.md。提交 fe6c395，6 套测试全部 OK，部署后 enforce 无动作、expiry generation 16（6 人）。
