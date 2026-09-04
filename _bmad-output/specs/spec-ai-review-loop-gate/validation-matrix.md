# Validation Matrix / 验证矩阵

## Adapter contract

- Bootstrap 不要求空目录预先存在验证脚本；Phase 1 由 IaC workflow 直接调用 `scripts/ci/`，Phase 2 接入 public runtime 时才由 configure/sync 安装稳定 adapter 入口。
- Public runtime 只调用固定 adapter 协议，不包含 Terraform、Ansible 或 Jenkins 实现。
- Gate 使用默认分支受信版本的 adapter 验证 PR checkout，当前 PR 不能通过修改 adapter 给自身放行。
- Adapter 缺失、无法执行、输出不完整或当前 SHA 不匹配均使 `repo-validation` 失败。

## Required checks

| Changed scope | Required deterministic validation | Explicit exclusion |
|---|---|---|
| Any PR | Changed-file classification、secret scan、adapter/gate provenance 与治理策略检查 | 不运行 deploy 或 release job |
| `terraform/**` | `terraform fmt -check -recursive`；受影响 root 的 `terraform init -backend=false` 与 `terraform validate` | 不执行依赖生产 provider、state 或 secret 的 plan/apply |
| `ansible/**` | YAML parse、锁定版本的 `ansible-lint`、受影响 playbook 的 CI-safe `--syntax-check` | 不读取 Vault、SSH、动态 HCP state，不连接 live host，不 deploy |
| `scripts/**`、测试与工具 | 仓库定义的目标测试、shell syntax 与适用 lint | 不发明 always-success placeholder |
| `docs/**` | Documentation Accuracy 与 Pages build/smoke | PR 中不发布 Pages |
| 治理敏感路径 | Workflow/Jenkins policy validation，并产生 `human_required` | 不让修改后的 privileged workflow 携带写凭据执行 |

## Aggregation

- Ruleset 只要求稳定的 `repo-validation` 聚合 check，矩阵扩展不改变 check 名称。
- 子检查返回 `passed`、`failed` 或带原因的 `not_applicable`；预期 job 缺失即失败。
- 工具与 collection 从仓库锁定 manifest 安装到临时 runner；不得使用生产 Vault、state 或部署凭据。
- 诊断 artifact 不含 secret，并设置有限保留期。

## Acceptance examples

- 仅修改文档时，IaC job 为带原因的 `not_applicable`，实际文档检查结果决定 aggregation。
- Terraform validation 失败时，`repo-validation` 在不读取 HCP state 或生产凭据的情况下失败。
- Ansible syntax 或 lint 失败时，AI review pass 不能使 PR merge-ready。
- PR 修改自身 adapter 或 `Jenkinsfile` 时，即使普通测试通过也进入 `human_required`。
