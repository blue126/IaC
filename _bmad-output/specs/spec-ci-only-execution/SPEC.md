---
id: SPEC-ci-only-execution
companions:
  - ../../../docs/designs/2026-08-30-ci-only-execution-architecture.md
  - ../../../docs/learningnotes/2026-08-30-jenkins-agent-control-plane.md
sources: []
---

> **Canonical contract.** 本 SPEC 与 `companions:` 中的文件共同构成后续构建、测试和验收契约。本文件由 2026-09-05 重建的 memlog 派生；原始 memlog 已随旧 worktree 丢失。

# Terraform 与 Ansible CI-Only Execution

## Why

消除工作站直接执行 Terraform 与 Ansible 带来的凭据漂移、遗漏审批、状态分叉和不可审计变更。开发者只提交和审阅代码，Gitea 与 Jenkins 提供唯一、可重复、可恢复的基础设施执行路径，同时保留 GitHub 镜像和受限 NetBox 事件自动化。

## Capabilities

- **CAP-1 — 代码变更通道**
  - **intent:** 运维者可以通过 Gitea PR 验证变更，并从受保护的 `main` 发起受控部署。
  - **success:** PR 不能修改受管环境；只有不可变 `main` SHA 在绑定计划并获批后才能进入变更阶段。

- **CAP-2 — Terraform 全根模块执行**
  - **intent:** 运维者可以在 Jenkins 中规划和应用仓库的全部 Terraform 根模块。
  - **success:** Proxmox、ESXi、OCI 与 NetBox integration 分别通过指定 HCP workspace 完成可审计 plan/apply，不存在本地 state 或并发 writer。

- **CAP-3 — Ansible 部署与验证**
  - **intent:** 运维者可以针对精确变更范围部署对应 Playbook 并验证服务健康。
  - **success:** 部署前独立批准刷新后的 inventory、主机、playbook、tags 与 limit；Verify contract 通过后流水线才成功。

- **CAP-4 — 维护操作**
  - **intent:** 运维者可以远程执行 Terraform import/state/destroy 和手动 Playbook。
  - **success:** 每种操作使用类型化参数、预览、审批、锁、审计和恢复证据，不存在任意命令入口。

- **CAP-5 — NetBox 事件执行**
  - **intent:** 合法 NetBox 事件可以请求允许的基础设施自动化。
  - **success:** 事件可认证、防重放、只使用不可变 Gitea `main`，遵守版本化策略和事务锁，并保留完整审计证据。

- **CAP-6 — Git 权威与镜像**
  - **intent:** 开发者以 Gitea 为唯一代码协作入口，同时保持 GitHub 单向镜像与 Pages。
  - **success:** Jenkins 只从 Gitea checkout 并接受内网代码 Webhook；GitHub 不反向同步、不持有基础设施凭据且镜像漂移可检测。

- **CAP-7 — NetBox Terraform 接管**
  - **intent:** 运维者可以在不覆盖较新线上数据的前提下，将明确的 NetBox 对象子集纳入 Terraform。
  - **success:** 备份恢复测试、所有权清单和 import 完成，plan 无未解释漂移，可逆 canary 通过后才启用 apply。

- **CAP-8 — CI 控制平面可复现与恢复**
  - **intent:** 运维者可以独立重建、升级和恢复 Gitea、Jenkins controller、Jenkins agent 及执行依赖。
  - **success:** 三者运行于 peer LXC；plan/deploy 身份隔离，配置与版本由代码管理，bootstrap、备份、切换、回滚和健康门槛可验证。

## Constraints

- 除首次 bootstrap 或已声明灾难恢复外，面向受管环境的 Terraform/Ansible 命令只能由 Jenkins 执行。
- PR 流水线定义来自受保护的 `main`；PR 不得获得 mutation credential、部署 SSH 身份或 controller 文件系统。
- `iac-plan` 与 `iac-deploy` 使用独立非 root 身份、service 和私有 workspace，无共享可写路径。
- Terraform 与 Ansible 分别审批，并绑定不可变 SHA、plan/inventory 摘要、授权审批人与稳定 conflict-domain 锁。
- 每个 Terraform root 只拥有一个指定 HCP workspace；执行前验证 local execution mode 与 state lineage。
- Secret、原始 plan、tfvars、Vault 密码、OCI 私钥和 state backup 禁止进入 Git、普通日志或持久 workspace。
- CAP-7 完成前，`terraform/netbox-integration` 禁止 apply。
- Controller 回滚只使用 quiesced、application-consistent 且通过 restore-and-boot 验证的兼容备份。
- Gitea 切换必须执行 write freeze、single-writer fencing、身份材料迁移及最新数据方向的 rollback。
- GitHub 不得触发基础设施作业或持有基础设施凭据。
- 所有实现遵守 companion 中的 AD-1 至 AD-12。

## Non-goals

- 不在本阶段实现跨 Proxmox 节点 HA。
- 不迁移到 HCP remote/agent execution；HCP 仅保存远程 state。
- 不扩大 Terraform 管理的 NetBox 对象范围。
- 不把 apply、deploy、发布或其他外部写入当作 PR 验证。

## Success signal

合并一个同时涉及 Terraform 与 Ansible 的代表性变更后，Jenkins 无需本地命令即可完成检查、真实计划、两阶段审批、apply、inventory 刷新、deploy 和 verify；全部步骤可追溯至同一 Git SHA、精确目标、凭据范围和审批记录。维护、NetBox 事件与恢复也只能通过各自受限入口完成。

## Open Questions

- 同一名获授权 homelab 运维者是否可以依次完成 Terraform 与 Ansible 两次审批，还是必须使用不同身份？
