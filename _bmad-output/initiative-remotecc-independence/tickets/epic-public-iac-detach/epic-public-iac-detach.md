---
type: epic
title: 公开 IaC 移除 RemoteCC
parent: initiative-remotecc-independence
covers: [R8, R9, R10]
sources: []
companions: []
after: []
refined: false
risk: medium
---

# 公开 IaC 移除 RemoteCC

## Description

切换完成后，公开 IaC 删除已划走的文件和 RemoteCC 分支，运维和架构文档、两个 Skill 迁入独立项目，IaC 只留一页接口说明（S12、S13）。

## Outcome

IaC 不再为 RemoteCC 保留专属路径，信号是 PR 校验通过且其余 root 的 plan 不变。

## Done when

- 删除前对全部移出单元完成最终调用方复核，覆盖模板和动态 include。
- 公开 IaC 不含已划走的文件，CI 分类、Terraform 校验列表、state 刷新和 secrets bridge 中没有 RemoteCC 分支。
- `AGENTS.md`、布局和部署文档及相关 Skill 都指向新的唯一入口，CI-only 架构 Deferred 一节已更新。
- 生产交付：删除已合入 `main`，PR 校验通过，其余 root 的 plan 没有变化。

## Boundaries

- 不做：重写公开 Git 历史（S15）。
- 不做：改 `initiative-employee-lifecycle` 的记录（S14）。
- Touch point: `.github/workflows/`、`scripts/ci/`、`tests/ci/`、`scripts/get-secrets.sh`、`scripts/refresh-terraform-state.sh`、`ansible/inventory/groups.yml`、`.gitignore`、`.gitattributes`、`.worktreeinclude`：移除 RemoteCC 分支和路径规则。
- Touch point: `Jenkinsfile:381`：只删 `terraform/remotecc/secrets.auto.tfvars` 这一路径。
- Must not change: IaC 其余 root 和 CI-only 的 Jenkins 路径；`scripts/jenkins/proxmox-projection.py` 的旧员工字段保留。

## References

- parent — `_bmad-output/initiative-remotecc-independence/initiative-remotecc-independence.md`，Requirements
- shared decisions — `_bmad-output/initiative-remotecc-independence/shared-decisions.md`

## Notes

- Waits on epic-executor-cutover because: 执行器不再读取 IaC 代码根后才能删除。
- Waits on epic-oci-hub-service because: Hub 部署入口要先离开 IaC。
