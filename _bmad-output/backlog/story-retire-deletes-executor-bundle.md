---
id: 8
type: story
title: "退役后执行器上没有该员工的设备包"
parent: none
covers: []
sources: []
companions: []
after: []
assignee: ""
refined: false
hitl: true
risk: medium
---

# 退役后执行器上没有该员工的设备包

## Description

执行器上含私钥的 `device-bundle.zip` 退役后还在。`wsctl retire` 要一起删除它，同一邮箱退役后能重新开户。部署到执行器是人工步骤。

## Requirements

Verify: 退役测试员工后，执行器上找不到它的设备包；用同一邮箱重新开户，不报 `HUB_DELIVERY_CONFLICT`。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R9)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-10、AD-17

## Notes

- Decision: 2026-11-07 用户决定让 `wsctl retire` 删除执行器上的设备包。
- `HUB_DELIVERY_CONFLICT` 是读代码推断的，没有实跑，实施时先复现。
- 实施和上线要另行授权。
