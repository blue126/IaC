---
type: epic
title: 独立项目自给
parent: initiative-remotecc-independence
covers: [R2, R3, R6, R7, R8]
sources: []
companions: []
after: []
refined: false
risk: medium
---

# 独立项目自给

## Description

私有 `remotecc` 仓库带齐 RemoteCC 的 Terraform、Ansible、测试、工具链和凭据路径，并到达执行器但尚未生效；在没有 IaC checkout 的环境里校验都通过。这是平台基线 epic，后面的 epic 都在它之上工作。开工时以 lifecycle epic 8–12 完成后的代码为准，重做范围和调用方核查。

## Outcome

运维者不碰员工流程就能证明独立项目可用，信号是没有 IaC checkout 时校验和 plan 通过。

## Done when

- S1、S2、S3、S8a、S8c、S9、S10 的单元已进入私有仓库，`host-firewall` 规则并入改名后的 `remotecc-ops` 角色，`admin-ssh-keys` 随项目带走（R14 前不退役）。
- 没有 IaC checkout 时，RemoteCC root 的校验和 plan、除 `deploy-oci-hub.yml` 外的部署入口的语法检查和 dry run 都通过。
- 凭据不经 secrets bridge 取得，等效校验覆盖不低于切换前（除 ingress 夹具）。
- S2、S3、S8、S9、S10 的非 RemoteCC 调用方核查有记录，覆盖模板和动态 include。
- 切换前 plan 基线已记录。
- 生产交付：独立项目已到达执行器，现有 `wsctl` 员工流程不变。

## Boundaries

- 不做：执行器切换（epic-executor-cutover）。
- 不做：Hub 服务和 ingress 夹具（epic-oci-hub-service）。
- 不做：删除公开 IaC 的文件（epic-public-iac-detach）。
- Touch point: `terraform/modules/proxmox-vm`、`common`、`tailscale`、`ubuntu-vm`、`cloud-init-ubuntu.yml`、`pve_vms`、`tailscale`、`all/common` 变量：只消费。
- Must not change: 现有 `wsctl` 员工流程。

## References

- parent — `_bmad-output/initiative-remotecc-independence/initiative-remotecc-independence.md`，Requirements
- shared decisions — `_bmad-output/initiative-remotecc-independence/shared-decisions.md`

## Notes

- Open question: R2 的切换前基线在 lifecycle epic 8–12 完成后取得，取得前要重核 L1–L7。
- Waits on `initiative-employee-lifecycle` epic 8–12 because: D19，Terraform 变更不混入 R2 基线，Hub 配置先变成 role 可重跑。
