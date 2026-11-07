---
id: 5
type: story
title: "架构主干补齐 WILL-117 留下的待决项"
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

# 架构主干补齐 WILL-117 留下的待决项

## Description

用 `bmad-architecture` 的 Update 处理 WILL-117 审查留下的三项设计问题和一批文字残留。设计问题要用户决定，所以是人工参与的 story，由架构师执行。

## Requirements

Verify: 下面每项都有用户确认的决定并写入主干，`lint_spine` 零发现；Reviewer Gate 的结果如实记录。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Notes
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/reviews/triage-will-117.md`, 待决 D1、D5

## Notes

- 开工前处理，阻塞 10.3：开户中的资源是否在到期范围内（AD-16、AD-28）。
- 开工前处理，阻塞 12.2：AD-32 的隔离要覆盖哪些入口。
- 要定改 R2 还是改 AD-6：R2 要一次确认，代码是分步审批。WILL-115 合并了上传和发信的批准，先核对它的结果。
- 同轮处理 D5 的文字残留：AD-6、AD-7 的“下载邮件”，主干其余 R2 说法，AD-13 的管理接口清单。
