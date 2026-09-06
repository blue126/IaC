# Validation Matrix / 验证矩阵

## Repository-owned review gate contract

- Phase 1 由 IaC workflow 直接调用 `scripts/ci/`；AI review 的 verdict 验证、renderer 与判定也由本仓库 workflow 持有，不使用 public runtime、adapter 或外部 evaluator。
- Claude 的有界 verdict 顶层只能包含 `status` 与 `findings`。模型不提供 repository、PR number 或 reviewed SHA；这些身份事实只从 GitHub event 取得。
- `review-policy-gate` 在 renderer 前以本地 `jq` 验证顶层字段、finding 类型和长度、相对路径、fingerprint 唯一性与 status/finding 语义。
- verdict 缺失、redacted、上游失败、字段多余或缺失、非法路径、重复 fingerprint、语义矛盾或本地 `jq` 失败，均 fail closed 且不得调用 PR comment API。

## Required checks

| Changed scope | Required deterministic validation | Explicit exclusion |
|---|---|---|
| Any PR | Changed-file classification、secret scan、repository-owned workflow/gate contract 与治理策略检查 | 不运行 deploy 或 release job |
| `terraform/**` | `terraform fmt -check -recursive`；受影响 root 的 `terraform init -backend=false` 与 `terraform validate` | 不执行依赖生产 provider、state 或 secret 的 plan/apply |
| `ansible/**` | YAML parse、锁定版本的 `ansible-lint`、受影响 playbook 的 CI-safe `--syntax-check` | 不读取 Vault、SSH、动态 HCP state，不连接 live host，不 deploy |
| `scripts/**`、测试与工具 | 仓库定义的目标测试、shell syntax 与适用 lint | 不发明 always-success placeholder |
| `docs/**` | Documentation Accuracy 与 Pages build/smoke | PR 中不发布 Pages |
| 治理敏感路径 | Workflow/Jenkins policy validation，并产生 `human_required` | 不让修改后的 privileged workflow 携带写凭据执行 |

## Aggregation

- Ruleset 只要求稳定的 `repo-validation` 聚合 check，矩阵扩展不改变 check 名称。
- 子检查返回 `passed`、`failed` 或带原因的 `not_applicable`；预期 job 缺失即失败。
- 工具与 collection 从仓库锁定 manifest 安装到临时 runner；不得使用生产 Vault、state 或部署凭据。
- `review-policy-gate` 只在一次 Claude 审查成功且其本地验证的 `status=pass` 时退出 0；`needs_fix` 和 `human_required` 分别以 10 和 11 阻断，不写 branch、merge 或设置。
- 诊断 artifact 不含 secret，并设置有限保留期。

## Acceptance examples

- 仅修改文档时，IaC job 为带原因的 `not_applicable`，实际文档检查结果决定 aggregation。
- Terraform validation 失败时，`repo-validation` 在不读取 HCP state 或生产凭据的情况下失败。
- Ansible syntax 或 lint 失败时，AI review pass 不能使 PR merge-ready。
- PR 修改 workflow、Jenkinsfile、validation scripts、secret bridge 或部署审批策略时，即使普通测试通过也进入 `human_required`。
- 模型返回额外身份字段、相对路径外的 finding、重复 fingerprint 或 status/finding 语义冲突时，gate 在 renderer 前失败且不写 PR comment。
