---
id: 4
type: story
title: "catalog 变化后 enforce 自动推送 paid_through 快照"
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

# catalog 变化后 enforce 自动推送 paid_through 快照

## Description

AD-12 写了 `enforce` 在 catalog generation 变化时推送快照，但代码没有，也没有票。现在控制台打标或改期到不了 OCI，要手动运行 `wsctl expiry`。修好后，下一次 `enforce` 就把变化送到 OCI。部署到执行器是人工步骤。

## Requirements

Verify: 在控制台改测试员工的 `paid_through` 或 `no_expiry`，不手动运行命令，下一次 `enforce` 后 OCI 快照的 generation 前进且内容一致；catalog 没变时不推送。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R5, R14)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-8、AD-12、AD-16

## Notes

- Decision: 2026-11-07 John 按 WILL-117 的 D4 开票，`story-no-expiry-clears-expired` 的 Verify 依赖它。
- 完成后请架构师删除 AD-8 里“落地前手动运行 `wsctl expiry`”的说明。
- 实施和上线要另行授权。
