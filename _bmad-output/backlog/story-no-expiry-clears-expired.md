---
id: 3
type: story
title: "打上 no_expiry 后 WireGuard 自动恢复"
parent: none
covers: []
sources: []
companions: []
after: [4]
assignee: ""
refined: false
hitl: true
risk: medium
---

# 打上 no_expiry 后 WireGuard 自动恢复

## Description

员工到期后才打 `no_expiry` 时，timer 不处理快照外的员工，`expired` 留在 Portal，WireGuard 一直断开，这和 R14 不一致。修好后打标的员工在一个 timer 周期内恢复访问，不需要先续费。部署到 OCI Hub 是人工步骤。

## Requirements

Verify: 让测试员工到期并断开，给它打 `no_expiry`，一个 timer 周期内 `expired` 被移除、WireGuard 恢复；人工停用和配额原因保持不变。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R14)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-8、AD-9、AD-11

## Notes

- Decision: 2026-11-07 用户决定修代码，不保留“打标前先续费”的例外。
- 完成后请架构师删除 AD-8 的这条例外，并在 `deferred-work.md` 追加 `retired:` 记录。
- 上线和本 story 的实施要另行授权。
