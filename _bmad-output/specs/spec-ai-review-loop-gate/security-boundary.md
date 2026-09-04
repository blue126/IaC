# Security and Permission Boundary / 安全与权限边界

## Automation identities

| Identity | Allowed | Forbidden |
|---|---|---|
| Validation workflow | 读取 PR 与代码；发布自身 check 和有限 artifact | secrets、branch write、deploy/apply、外部系统 |
| Claude reviewer | 读取可信 PR；发布评论和结构化 verdict | commit、merge、删除 branch、部署凭据 |
| Dedicated Fixer App | 在 trust、path 和 SHA 检查后普通 push 当前 PR head；回复 bot thread | `main`、force push、fork、治理敏感文件、settings、部署凭据 |
| GitHub auto-merge | Ruleset 满足后 squash merge 普通路径 PR | bypass、陈旧 SHA、治理敏感 PR |
| Remote cleanup | 删除已合并远端 head branch；取消旧 run；配置 artifact retention | 删除 open/unmerged branch 或审计记录 |
| Jenkins operator gate | 人工批准已审查的 plan 或命名 deploy | GitHub/AI 身份自动批准 |

## Trust checks before repair

- Base/head repository 均为 `blue126/IaC`，base branch 为 `main`。
- PR open、non-draft，actor 与 author 属于 owner/allowlist，且没有停止自动化的 label。
- Head branch 使用批准的任务前缀，触发 artifact 与当前完整 HEAD SHA 一致。
- Diff 不包含治理敏感路径；`allowed_bots: '*'` 禁止使用。
- 模型步骤不持有 GitHub write token；只有验证成功后的最小 push 步骤获得短期 Fixer App token。

## Governance-sensitive paths

- `.github/workflows/**`
- `Jenkinsfile` 与改变 Jenkins 人工审批语义的 helper
- validation adapter、gate、bootstrap managed configuration
- secret bridge、credential handling 与 deploy approval policy

这些路径仍可获得只读 AI review 和确定性检查，但禁止自动修复与自动合并。

## Ruleset

- Require pull request，阻止 direct push、force push 和 branch deletion。
- Require 当前 SHA 的 `repo-validation` 与 `ai-review-gate`，并要求 review conversation resolved。
- 普通路径允许 squash auto-merge；治理敏感路径由独立 check/label 维持人工确认。
- 合并后自动删除远端 head branch。

## Authorized policy exception

`AGENTS.md` 的全局禁令继续生效，只对命名 Fixer App、GitHub auto-merge 和远端 cleanup automation 增加精确例外。例外不授权交互式 agent merge、force push、写 `main`、批准部署或清理本地 worktree。
