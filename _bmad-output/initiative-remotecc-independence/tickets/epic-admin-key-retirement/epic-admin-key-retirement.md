---
type: epic
title: 退役员工 VM 上的管理员公钥
parent: initiative-remotecc-independence
covers: [R14]
sources: []
companions: []
after: []
refined: false
risk: high
---

# 退役员工 VM 上的管理员公钥

## Description

员工 VM 上不再留管理员 SSH 公钥，开户和维护自动化不经管理员 SSH。这是本 initiative 唯一的行为变更，排在最后，避免与 R2 的零差异基线混在一起。

## Outcome

员工 VM 整台归员工使用，信号是一次新开户和一次现有 VM 维护不经管理员 SSH 通过。

## Done when

- 交付给员工的 VM 上没有管理员 SSH 公钥。
- 一次新开户和一次现有 VM 维护不经管理员 SSH 都通过。
- 管理员仍能经 PVE CLI 或控制台维护。
- 生产交付：现有员工 VM 已完成退役，员工设备的 SSH 接入不受影响。

## Boundaries

- 不做：改变员工设备的 SSH 接入（D12）。
- Must not change: 除管理员访问方式外的 RemoteCC 产品功能。

## References

- parent — `_bmad-output/initiative-remotecc-independence/initiative-remotecc-independence.md`，Requirements
- shared decisions — `_bmad-output/initiative-remotecc-independence/shared-decisions.md`

## Notes

- Open question: PVE API 加 QEMU Guest Agent 能否承担全部任务，由架构 spike 验证；`community.proxmox`、`proxmoxer` 的安装需 will 授权。
- Waits on epic-executor-cutover because: 切换已完成且零差异已证明。
- Waits on epic-oci-hub-service because: Hub 防火墙代码要先在独立项目内，管理访问规则要在那里改。
- Waits on epic-public-iac-detach because: 描述管理员访问的文档和 Skill 要先迁入独立项目。
