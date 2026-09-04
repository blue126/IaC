# Brownfield Baseline / 现状基线

## Repository facts

- `.github/workflows/claude-code-review.yml` 已监听 PR `opened`、`synchronize`、`ready_for_review` 与 `reopened`；但官方 `/code-review --comment` plugin 发现 Claude 已评论后会主动跳过，不能保证每个新 HEAD 复审。Phase 2A 的独立 `ai-review-gate` 又造成第二次模型调用。
- `.github/workflows/claude.yml` 提供 comment-triggered Claude 能力，但人工 mention 不能满足无人值守收敛目标。
- Repository 当前没有通用 PR validation workflow、Makefile 或统一测试框架；`repo-validation` 必须新增，不能把 deploy/publish pipeline 冒充验证。
- `Jenkinsfile` 在 Terraform Apply 和 Ansible Deploy 前保留人工 `input`；`main` push 会触发 Jenkins，但不会仅因 GitHub auto-merge 自动执行外部写入。
- `docs/designs/cicd-architecture.md` 是 Jenkins 与部署阶段的现行设计依据，实现不得绕过其人工批准边界。
- `AGENTS.md` 禁止 agent 自动 commit、push、merge、删除资源或修改 GitHub settings；实施需为命名自动化主体增加窄例外，并继续要求每个外部写边界单独授权。

## Adoption boundary

- Public bootstrap runtime 已公开并固定使用经过 contract tests 的 commit `3c6e3ada5ebe3790b9bbecf44c594ffa03be716e`；升级必须通过新 PR 验证并改用新的 immutable SHA。
- 自动 reviewer 已改为单次 Claude Code Action structured review；评论由受限确定性步骤发布。现有 `@claude` workflow 保留人工交互；Fixer App、required checks、auto-merge 与 Ruleset enforcement 尚未配置。
- PR #33 已证明 Anthropic structured output、当前 SHA 绑定、确定性 gate 和同 SHA 评论 PATCH 在真实 PR 上通过。Dedicated Fixer App 已延后，不属于当前 rollout 的前置条件。
