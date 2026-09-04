# Brownfield Baseline / 现状基线

## Repository facts

- `.github/workflows/claude-code-review.yml` 已监听 PR `opened`、`synchronize`、`ready_for_review` 与 `reopened`；问题不是缺少新 SHA 事件，而是缺少可靠的机器 gate 和后续 fixer orchestration。
- `.github/workflows/claude.yml` 提供 comment-triggered Claude 能力，但人工 mention 不能满足无人值守收敛目标。
- Repository 当前没有通用 PR validation workflow、Makefile 或统一测试框架；`repo-validation` 必须新增，不能把 deploy/publish pipeline 冒充验证。
- `Jenkinsfile` 在 Terraform Apply 和 Ansible Deploy 前保留人工 `input`；`main` push 会触发 Jenkins，但不会仅因 GitHub auto-merge 自动执行外部写入。
- `docs/designs/cicd-architecture.md` 是 Jenkins 与部署阶段的现行设计依据，实现不得绕过其人工批准边界。
- `AGENTS.md` 禁止 agent 自动 commit、push、merge、删除资源或修改 GitHub settings；实施需为命名自动化主体增加窄例外，并继续要求每个外部写边界单独授权。

## Adoption boundary

- Public bootstrap runtime 尚未发布；IaC caller 必须 pin 首个经过 contract tests 的 public release SHA。
- 现有 Claude GitHub App 可继续担任 reviewer；Fixer App、required checks、auto-merge、Ruleset 与 repository secrets 尚未在本规范阶段配置。
- 本规范是设计产物，不证明 Anthropic structured output、Fixer App push recursion 或 reusable workflow provenance 已在真实 PR 上通过；这些属于 rollout evidence。
