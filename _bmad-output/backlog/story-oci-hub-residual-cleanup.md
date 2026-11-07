---
id: 2
type: story
title: "OCI Hub 已知残留已清除"
parent: none
covers: []
sources: []
companions: []
after: []
assignee: ""
refined: false
hitl: false
risk: low
---

# OCI Hub 已知残留已清除

## Description

删除 2026-11-07 核对确认不再使用的残留：Mosh 边界一次性 playbook 及其专用测试，设备包交付代码里的 temp.sh 分支和已删除的 `existing` 流程分支，OCI Hub 上的旧备份文件。

## Requirements

Verify: 公开和私有仓库搜索不到这些残留的引用，相关测试通过；线上待删目标已先只读确认、删除后不存在，Portal 和配额服务照常。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Notes
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-30

## Notes

- Decision: 2026-11-07 用户批准清理。这不含推送、PR、部署到执行器。
- 待删：`ansible/playbooks/configure-oci-hub-mosh-boundary.yml`；`tests/oci-hub/test-mosh-boundary-play.py` 里依赖它的测试；`remotecc/wsctl/hub-onboard.py` 代码哈希里的这项；`remotecc/wsctl/deliver-temp.py` 的 temp.sh 和 `existing` 分支及相应测试；OCI Hub 的 `/opt/oci-hub/backup-readdress-20261103` 和 `portal.yaml` 的 `~` 备份。
- 代码哈希变化会让未执行的开户计划失效，部署前确认没有进行中的运行。
