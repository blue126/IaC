---
type: initiative
title: CI-only 执行架构落地
parent: none
sources:
  - _bmad-output/initiative-ci-only-execution/spec-ci-only-execution/SPEC.md
  - _bmad-output/initiative-ci-only-execution/decisions-2026-11-05.md
  - docs/planning/jenkins-peer-agent-recovery.md
  - docs/architecture/ci-only-execution-architecture.md
companions:
  - docs/architecture/ci-only-execution-architecture.md
  - docs/planning/jenkins-peer-agent-recovery.md
  - docs/guides/jenkins-agent-bootstrap.md
after: []
risk: high
---

# CI-only 执行架构落地

## Description

把 Proxmox、OCI 的 Terraform 和 Ansible 执行从工作站移到 Jenkins peer，让每次变更都能追溯到同一 Git SHA、精确范围和审批记录。范围按 2026-11-05 的决策收窄：GitHub 保持权威，RemoteCC 继续走 `wsctl`，ESXi 和 NetBox 不在本次内。决策优先于 SPEC 和架构文档，架构文档待更新。

## Outcome

运维者不再从工作站变更受管环境：合并一个同时涉及 Terraform 和 Ansible 的代表性变更后，Jenkins 无需本地命令即可完成全流程（SPEC Success signal）。

## Requirements

- R1 (SPEC CAP-8, recovery S1–S2): CT110 peer 以 `iac-plan`、`iac-deploy`、`iac-apps` 三个隔离身份运行，Verify 与隔离探测通过，Terraform 变更只有 CT110 及其 inventory。
- R2 (SPEC CAP-8, recovery S5): controller 维护失败时，独立 watchdog 可用实测备份恢复 Jenkins；没有有效证据时，controller 变更和归零都被拒绝。
- R3 (recovery S3): 只读 plan 不持有 mutation 凭据即可预测 Proxmox 变更，并明确报告盲区；partial 结果不能推出全 root 无变更。
- R4 (recovery S6–S7): 全部存续 job 都在 peer 上运行并有调度和清理证据，获批后 controller executor 归零，正常 plan、deploy、agent 重连和重复运行都通过。
- R5 (SPEC CAP-1, decisions 1): PR 只验证、不改受管环境；只有不可变 `main` SHA 在绑定计划获批后才进入变更阶段。
- R6 (SPEC CAP-2, decisions 2): Jenkins 对 `terraform/proxmox`（`iac-proxmox-lab`）和 `terraform/oci`（`iac-oci`）完成可审计的 plan 和 apply，没有本地 state 和并发 writer。
- R7 (SPEC CAP-3): 部署前独立批准刷新后的 inventory、主机、playbook、tags 和 limit，Verify 通过后流水线才算成功。
- R8 (SPEC CAP-4): Terraform import、state、destroy 和手动 playbook 都使用类型化参数、预览、审批、锁、审计和恢复证据，不存在任意命令入口。
- R9 (decisions 1, 取代 SPEC CAP-6): GitHub `main` 是 Jenkins 唯一的 IaC 代码来源，webhook 必须通过 GitHub 签名校验，且只能请求执行，不能选择代码或命令。
- R10 (decisions 2–3, architecture AD-1, AD-9): 移交完成后，受管环境变更只由 Jenkins 执行，例外只有 AD-9 记录的 bootstrap 或灾难恢复，以及 RemoteCC 的 `wsctl`；本地只读 plan 仍然允许，本地写操作不允许。

## Constraints

- 移交完成前，本地执行和合并前真实 dry run 照旧（decisions 3）。
- PR 流水线定义来自受保护的 `main`；PR 不得获得 mutation 凭据、部署 SSH 身份或 controller 文件系统（SPEC Constraints）。
- plan、deploy、apps 使用独立非 root 身份、service 和私有 workspace，没有共享可写路径（SPEC Constraints, recovery S2）。
- Terraform 和 Ansible 分别审批，绑定不可变 SHA、plan 或 inventory 摘要、审批人和 conflict-domain 锁；同一运维者可以完成两次审批，但必须是两条独立记录（SPEC Constraints, decisions 4）。
- 每个 Terraform root 只对应一个 HCP workspace；执行前验证 local execution mode 和 state lineage（SPEC Constraints）。
- Secret、原始 plan、tfvars、Vault 密码、OCI 私钥和 state backup 不进 Git、普通日志或持久 workspace（SPEC Constraints）。
- Controller 回滚只使用 quiesced、application-consistent 且通过 restore-and-boot 验证的兼容备份（SPEC Constraints）。
- 取得真实恢复证据、完成全部 job 映射前，controller 保持 bootstrap=2，旧入口不下线（recovery S5–S7）。
- CT110、真实密钥、controller 归零、提交和推送都要单独授权（decisions 授权边界）。

## Done when

- 代表性 Terraform 加 Ansible 变更经 Jenkins 完成计划、两阶段审批、apply、inventory 刷新、deploy 和 verify，全部追溯到同一 SHA。
- CT110 在生产运行，controller executor 为 0，恢复演练有真实证据。
- `terraform/proxmox` 和 `terraform/oci` 都由 Jenkins 完成过一次获批 apply。
- 维护操作只能经受限入口完成。
- `docs/architecture/ci-only-execution-architecture.md` 和 `AGENTS.md` 与上述现状一致。

## Boundaries

- 不做：Gitea 权威迁移和 GitHub 镜像、ESXi、RemoteCC 迁入 Jenkins、NetBox 事件（CAP-5）和 Terraform 接管（CAP-7）、跨节点 HA、HCP remote execution。
- 不把 apply、deploy、发布或其他外部写入当作 PR 验证。
- 私有应用代码归应用所有者，本 initiative 只交付接入契约。
- Must not change: RemoteCC 的 `wsctl` 和 `remotecc-ops` 执行路径。
- Tracer path: PR 验证 → 合并到 `main` → Jenkins peer 计划 → 审批 → apply → inventory 刷新 → 审批 → deploy 和 verify。

## References

- architecture — docs/architecture/ci-only-execution-architecture.md, AD-1 至 AD-12（待按 decisions 更新）
- plan — docs/planning/jenkins-peer-agent-recovery.md, S1–S8 与技术契约
- guide — docs/guides/jenkins-agent-bootstrap.md, 分阶段操作与凭据矩阵
- spec — _bmad-output/initiative-ci-only-execution/spec-ci-only-execution/SPEC.md, CAP-1 至 CAP-8
- decisions — _bmad-output/initiative-ci-only-execution/decisions-2026-11-05.md

## Notes

- Source conflict: SPEC CAP-1、CAP-2、CAP-6 和架构 AD-2、AD-3、AD-4、AD-8、AD-11、AD-12 与 decisions 冲突，以 decisions 为准，等架构更新。
- Decision: 2026-11-05 第一个 epic 是 peer 生产落地（S1–S8）。
- Decision: 2026-11-05 Gitea 继续运行，只退出 IaC 权威，n8n job 仍用它做只读 SCM。
- Decision: 2026-11-05 GitHub Actions 不持有基础设施凭据，webhook 只能请求执行，不能选择代码或命令。
- Decision: 2026-11-05 移交后允许本地只读 plan，不允许写。
- Decision: 2026-11-05 用户同意解除 Jenkins 流水线冻结；本地证据显示 `IaC-Homelab-Pipeline` 已在 2026-10-27 解冻，无需动作，线上现状待登录确认。
- Decision: 2026-11-05 给 `/github-webhook/` 加 HMAC secret 并由 Jenkins 校验，列入第一个 epic，排在最前面，因为公网入口当前可能已经在触发流水线。
