---
id: 6
type: story
title: "退役时清除 Hub 里的员工会话数据"
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

# 退役时清除 Hub 里的员工会话数据

## Description

员工在 HAPI 网页上的会话和消息存在 VM500 共享 Hub 的 `hapi.db` 里。退役时路由、令牌和 Access 都会清掉，但没有清这部分数据的步骤，所以内容会一直留着，与 R19 不符。这些内容可能含员工的代码和提示词。先确认 Hub 能否按 namespace 删除，再接入 `wsctl retire`。

## Requirements

Verify: 退役测试员工后，`hapi.db` 里没有它的 namespace 下的会话和消息，其他员工的数据不变；身份绑定记录随之清除，不等下次登录；删除失败时 `retire` 报告失败，同一 SHA 重跑能补上。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R19)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-10、AD-20

## Notes

- Decision: 2026-11-07 用户在 WILL-112 决定退役时清除。
- Hub 能否按 namespace 删除还没查。Hub 二进制不能改时，回来和用户定方案。
- 实施和上线要另行授权。
