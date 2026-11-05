---
type: epic
title: "HAPI 接入并入 wsctl 生命周期"
parent: initiative-employee-lifecycle
covers: [R18, R19]
sources: []
companions: []
after: [epic-executor-platform, epic-paid-through-enforcement]
refined: false
risk: high
---

# HAPI 接入并入 wsctl 生命周期

## Description

把 `remotecc/hapi-admin` 的隔离、身份绑定与重试逻辑并入 wsctl：开户时同时启用 WireGuard 与 HAPI（Cloudflare Access 放行、VM500 上的 route/credential/agent、员工 VM 上的 Runner）；`wsctl access enable|disable --method wg|hapi` 分别启停；到期 5 分钟任务停用 HAPI、续费恢复；退役清除 HAPI 全部记录。HAPI 专用机器账号与 Sandbox 绑定在合并后撤销。

## Outcome

HAPI 成为员工生命周期的一部分，不再是需要单独开户和单独管理的第二套系统。

## Done when

- 新开户的测试员工同时能经 WireGuard 与 HAPI 网页进入自己的 VM。
- 停用其中一种接入，另一种仍可用。
- 测试员工到期后 5 分钟内 HAPI 不可用，续费后恢复。
- 退役后 VM500 与 Cloudflare Access 中没有该员工的记录；两个测试员工互相进不了对方的 namespace。

## Boundaries

- 不改 VM500 上 HAPI 服务本身的部署方式与共享 Hub 架构。
- Must not change: 管理员本人（VM502）现有 HAPI route 与会话历史。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R18, R19)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-2, AD-10, AD-15, AD-16, AD-20

## Notes

- Waits on epic-executor-platform because: HAPI 管理凭据并入执行器 VM。
- Waits on epic-paid-through-enforcement because: HAPI 停用挂在 5 分钟到期任务上。
- Open question: VM500 上 hapi-health 与现有 `hapi-admin` 的 Sandbox 绑定如何迁移、何时撤销，细化本 epic 时再定。
