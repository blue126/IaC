---
type: epic
title: OCI Hub 服务从独立项目部署
parent: initiative-remotecc-independence
covers: [R3, R6, R7, R8]
sources: []
companions: []
after: []
refined: false
risk: medium
---

# OCI Hub 服务从独立项目部署

## Description

OCI Hub 服务的部署入口离开 IaC，主机和网络规则仍由 IaC 管理（S4、S5）。Hub 部署到另一台主机，不经执行器切换，所以单独成 epic。

## Outcome

运维者从独立项目部署 Hub，信号是 `deploy-oci-hub.yml` 的 verify 通过且同机工作负载不受影响。

## Done when

- `deploy-oci-hub.yml` 和 `oci-hub` role 在没有 IaC checkout 时通过语法检查和 dry run。
- `tests/oci-hub` 的 ingress 夹具不再依赖 IaC checkout，覆盖不低于切换前。
- S4 的非 RemoteCC 调用方核查有记录。
- Portal 密钥和配对令牌从 IaC Vault 迁到 BWS，Hub 部署不再读 IaC Vault（D18）。
- 生产交付：Hub 从独立项目部署并通过 verify，同机的 anki、bookorbit 不受影响。

## Boundaries

- 不做：`terraform/oci/oci-hub.tf` 和 ingress 变量文件留 IaC（S5）。
- Touch point: `caddy` role：只消费。
- Touch point: `ansible/inventory/oci/hosts.yml`、`host_vars/oracle-cloud-ubuntu2404.yml`：Hub 部署要用的主机清单和 `oci_hub_portal_external_url`。
- Must not change: 其他 OCI 工作负载。整机操作前运维者确认 Jenkins 一侧空闲（CI-only AD-14）。

## References

- parent — `_bmad-output/initiative-remotecc-independence/initiative-remotecc-independence.md`，Requirements
- shared decisions — `_bmad-output/initiative-remotecc-independence/shared-decisions.md`

## Notes

- Waits on epic-standalone-project because: 需要独立项目的工具链、凭据路径、校验载体和 `scripts/oci-hub/`。
- Waits on epic-executor-cutover because: 新主机部署要交替运行 Hub 部署和 `wsctl oci-hub-release`，两者须来自同一项目。
