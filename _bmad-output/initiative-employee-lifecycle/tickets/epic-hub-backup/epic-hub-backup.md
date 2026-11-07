---
type: epic
title: "OCI Hub 启动卷有定期备份，实例不会被误删"
parent: initiative-employee-lifecycle
covers: [R28]
sources: [_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: []
refined: true
risk: medium
---

# OCI Hub 启动卷有定期备份，实例不会被误删

## Description

把 OCI Hub 的备份从一份手动备份变成 Terraform 管理的定期备份，同时防止实例被误删，并准备好恢复时要用的隔离开关。这部分不依赖其他 epic，先做。

## Outcome

管理员不用再手动备份：OCI Hub 每周自动有一份可用备份，Terraform 也删不掉这台实例。

## Requirements

- R1 (parent R28): OCI Hub 启动卷按 Terraform 自定义策略每周备份、保留 4 周，手动备份一并计入 5 份免费额度；策略分配失败时改由定时任务调 OCI API，不放在执行器上；Hub 实例不能被 Terraform 误删。

## Constraints

- (AD-15, AD-32) 执行器不增加 OCI 凭据。

## Done when

- OCI 控制台显示策略已绑定启动卷，且策略产生过一份备份。
- `terraform/oci` 的 plan 没有漂移，销毁实例的计划被拒绝。
- 隔离开关的 plan 只改 WireGuard 入站规则。

## Boundaries

- 不做恢复流程和演练，归 epic-hub-recovery。
- 不改公网 IP，保持临时 IP。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R28)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-15、AD-32

## Notes

- Decision: 2026-11-07 用户批准切分和 story 大纲。本 epic 的需求全部来自 initiative，不需要再补输入。
- Decision: 2026-11-07 tracer bullet 是 8.1：策略绑定是本 epic 风险最高的一步，控制台能选但还没实际分配过。
