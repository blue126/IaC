# Rollout and Rollback / 上线与回滚

## Implementation sequence

1. **Pending:** Bootstrap 安装薄 caller 与 IaC adapter 配置骨架；未完成 adapter 时只运行 AI review，auto-merge 关闭。
2. **Observe:** Ready PR 的 `opened`、`ready_for_review`、`reopened`、`synchronize` 对当前 HEAD 只调用一次 Claude，确定性 renderer 发布评论，非 required `review-policy-gate` 校验同一 verdict；Draft `opened` 不调用模型。
3. **Validate:** 启用无生产凭据的 path-aware `repo-validation`，用 Terraform、Ansible、文档、脚本及治理敏感 fixture 验证。
4. **Repair:** 安装独立 Fixer App，先允许一次自动修复，证明普通 push 会触发新复审，再启用三轮与重复指纹保护。
5. **Protect:** 以 evaluate/shadow 方式验证 Ruleset 后，要求两个 gate、会话解决、无 direct/force push 和 squash merge。
6. **Merge:** 普通 IaC 路径启用 auto-merge；治理敏感路径保留人工确认；Jenkins Apply/Deploy 继续人工批准。
7. **Clean:** 启用远端 branch 删除、旧 run cancellation 与 bounded artifact retention；不实现本地 cleanup。

## Initial merge policy

| Scope | Review/fix | Merge |
|---|---|---|
| Terraform、Ansible、文档、普通脚本与配置 | 通过 adapter 与安全条件后自动 | 两个 gate 通过后自动 squash merge |
| 治理敏感路径 | 只读 review；禁止 AI fixer | 人工确认后由 GitHub 合并流程处理 |
| Fork、未知 bot、未获准 actor | 只运行不接触 secrets 的检查 | 不自动合并 |

## Failure behavior

- Adapter pending/invalid、validation outage、模型 timeout、schema 错误或 GitHub API 错误都使 gate failing/pending。
- 三轮修复、重复 finding、冲突或含糊结论停止自动写入并标记 human attention。
- 新 SHA 取消陈旧 work，重新开始 classify 与 validation。
- Jenkins 不接收自动批准；reject、timeout 或 abort 必须保持基础设施不变。

## Rollback

1. 关闭 fixer 与 auto-merge，保留只读 validation/review。
2. 将新 required checks 临时设为 evaluate/disabled，避免 gate outage 封锁全部 PR。
3. 撤销 Fixer App 安装或凭据；不依赖 PAT。
4. 恢复人工 merge，不改变 Jenkins 人工 input 或部署凭据。
5. 通过受保护 PR 回退 caller、adapter 与 `AGENTS.md`，不 force push 或重写历史。

## Enforcement evidence

- 无 finding PR 只为其当前 SHA 产生有效 pass。
- seeded finding 产生一次修复 commit、新 `synchronize` review 并最终通过。
- 重复 finding 在边界内停止，fork/untrusted PR 无法读取模型或写凭据。
- Terraform/Ansible 验证失败阻止合并且不访问生产系统。
- 治理敏感变更无法由 fixer 修改或自动合并。
- 合并触发 Jenkins 后，Apply 与 Deploy 都停在现有人工输入。
- GitHub 远端残留被清理，本地 worktree 不被 workflow 触碰。
