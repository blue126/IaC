# Implementation Phases / 分步实施

本文件是 `SPEC.md` 的实施 companion，不是平行 spec。每个阶段必须独立可审查、可回滚；后续阶段不得在前置 evidence 缺失时提前启用 enforcement。

## Phase 1 — Repository validation shadow

### Scope

只新增无生产凭据的 `repo-validation` shadow CI。保留现有 Claude workflows、Jenkins、Ruleset、repository secrets、merge settings 和远端清理设置不变。

### Files and actions

1. `tests/ci/repo-validation-test.sh`
   - 先建立分类、工具缺失、失败传播、`not_applicable`、敏感路径及无 secret 行为的 shell fixtures。
   - 测试 module 变更会选择所有 Terraform roots，而不是只验证 module 目录。
2. `scripts/ci/classify-pr.sh`
   - 接收显式 base SHA 与 head SHA，使用三点 diff 计算 changed files。
   - 输出 Terraform roots、Ansible/docs/shell applicability 与 governance-sensitive boolean；不使用 `HEAD~1`。
3. `scripts/ci/validate-terraform.sh`
   - 运行全仓 `terraform fmt -check -recursive`。
   - 对分类器选择的 `terraform/proxmox`、`terraform/esxi`、`terraform/oci`、`terraform/netbox-integration` 执行 `init -backend=false -input=false` 和 `validate`。
   - `terraform/modules/**` 变化选择全部四个 consumer roots；不执行 plan/apply。
4. `scripts/ci/validate-ansible.sh`
   - 使用 repository `requirements.txt` 的兼容边界和 `ansible/requirements.yml` 安装 CI dependencies。
   - 新增并使用 `tests/ci/fixtures/inventory.yml` 作为 CI-only inventory，运行 `ansible-lint` 与 playbook `--syntax-check`，避免 Vault、Terraform state、SSH 与 live hosts。
5. `scripts/ci/validate-documentation.sh`
   - 复用现有 Documentation Accuracy suites；仅在 site inputs 变化时运行 Hugo production build 与 smoke checks。
   - 验证现有 Python、Go 与 Hugo 版本合同，但不上传或部署 Pages。
6. `scripts/ci/validate-repository.sh`
   - 运行适用的 shell syntax、现有 documentation-accuracy suites 与 project policy tests。
   - docs/site inputs 变化时使用现有版本执行 Hugo production build 与 smoke checks，但不上传或部署 Pages。
   - 子检查失败必须传播非零状态；不存在适用检查时输出带原因的 `not_applicable`，不得伪造成功。
7. `.github/workflows/repo-validation.yml`
   - 在 `pull_request` 的 opened、synchronize、ready_for_review、reopened 上运行。
   - `permissions: contents: read`，以 PR number 设置 concurrency 并 `cancel-in-progress: true`。
   - 设置 Terraform `1.14.9`、Python `3.13`、Go `1.25.0` 与 Hugo `0.165.0`，checkout 完整 base/head history，并把事件中的 base/head SHA 直接传给 `scripts/ci/validate-repository.sh`。
   - 第三方 Actions 在提交前解析并固定为完整 commit SHA；checkout credentials 不持久化；workflow 不持有 secrets 或 write permission。
   - 发布稳定 job/check 名 `repo-validation`；Phase 1 不加入 Ruleset required checks。
8. `docs/designs/cicd-architecture.md`
   - 增加 GitHub PR CI 与 Jenkins post-merge CD 的职责分界、无凭据约束和 shadow 状态。

### Acceptance criteria

- **AC-P1-1:** Given 一个只修改文档的 PR，when 分类与 validation chain 运行，then Terraform/Ansible 为有理由的 `not_applicable`，真实文档测试决定 `repo-validation` 结果。
- **AC-P1-2:** Given 任一 Terraform root 的无效 HCL，when shadow CI 运行，then validation 在不读取 HCP state 或 credentials 时失败。
- **AC-P1-3:** Given `terraform/modules/**` 变化，when 分类完成，then 四个 Terraform consumer roots 都被选择验证。
- **AC-P1-4:** Given Ansible syntax/lint 错误，when CI-only inventory 验证运行，then job 失败且不读取 Vault、不连接 live host。
- **AC-P1-5:** Given PR 修改 workflow、Jenkinsfile、validation scripts、secret bridge 或部署审批策略，when 分类运行，then 结果明确标记 governance-sensitive；Phase 1 仍只报告，不自动写入或合并。
- **AC-P1-6:** Given runner 缺少必需工具或任一子检查失败，when validation chain 聚合结果，then `repo-validation` 非零失败，不降级为 warning 或 always-success。
- **AC-P1-7:** Given fork PR，when shadow workflow 运行，then它只获得 read-only GitHub token，且没有任何 repository secret 被映射。
- **AC-P1-8:** Given 现有 Jenkins pipeline，when Phase 1 合入，then Jenkinsfile、两个 `input` gate 和 main-push CD 行为均无变化。

### Phase evidence

- `bash -n` 通过所有新增 shell files。
- `tests/ci/repo-validation-test.sh` 全部通过。
- 在 Docker Sandbox 中运行 Terraform、Ansible 和 documentation validation；host 不安装依赖。
- 代表性 PR 分别证明 docs-only、Terraform、Ansible、module 和 governance-sensitive 路径行为。
- Shadow 至少覆盖一次新 commit 的 cancellation/restart；结果未配置为 required。

## Phase 2A — Structured review shadow（完成）

- 固定 public bootstrap runtime 与 Claude Code Action 的完整 commit SHA。
- PR #29、#30 验证绑定当前 HEAD 的 structured verdict；PR #32 验证 Draft → Ready 与 `synchronize` 触发行为。
- 该过渡阶段保留评论 reviewer 与独立 structured reviewer，因此每个 HEAD 有两次 Claude 调用。

## Phase 2B — Single review and policy gate（当前）

### Scope

把两个自动 AI workflow 收敛为一个 `Claude Review` workflow：`claude-review` 每个 HEAD 只调用一次 Claude 并输出有界 structured verdict；确定性 renderer 从该 verdict 创建或更新当前 SHA 评论；`review-policy-gate` 作为独立 job 复用固定 bootstrap evaluator。继续保持 shadow，不修改 Ruleset、Fixer、auto-merge 或 Jenkins。

### Files and actions

1. `.github/workflows/claude-review.yml`
   - 合并并取代 `.github/workflows/claude-code-review.yml` 与 `.github/workflows/ai-review-gate.yml`。
   - 保留 opened、synchronize、ready_for_review、reopened、non-Draft 和 per-PR cancellation；明确拒绝 fork。
   - Claude job 只读 PR 内容且恰好调用一次 SHA-pinned Claude Action；schema 限制 finding 数量和字段长度。
   - job output 仅通过 environment 交给 renderer/gate；空、redacted 或上游失败一律 fail closed。
   - renderer 不解析自然语言评论，以 HEAD marker 幂等创建或更新摘要；模型无 GitHub write tool。
   - gate job 使用 `if: always()`，不持有模型凭据或 OIDC；它只获得 renderer 所需的 `pull-requests: write` 来发布 PR 评论，先校验上游结果和绑定当前 repo/PR/full HEAD SHA 的 verdict，再执行 policy 判定。
2. `tests/ci/review-policy-gate-test.sh`
   - 保留 evaluator 的 pass、needs_fix、human_required、stale SHA 和 malformed fixtures。
   - 断言单 workflow、单 Claude Action、两个稳定 job 名、job output、`needs`/`always()`、权限边界、immutable pins 和旧 workflow 已移除。
3. `docs/designs/cicd-architecture.md` 与 canonical spec companions
   - 将 Phase 2A 双调用记为历史 evidence，并记录 Phase 2B 单调用数据流、命名和 fallback 原因。

### Acceptance criteria

- **AC-P2B-1:** Given 一个 Ready PR HEAD，when `Claude Review` 运行，then workflow 中恰好一次 Claude Action 调用，同时得到人类可读评论和机器 verdict。
- **AC-P2B-2:** Given Draft PR，when opened，then该 review workflow 的所有 job 均 skipped；when 同一 HEAD 转 Ready，then首次执行；when push 新 HEAD，then旧 run 取消并重新审查。
- **AC-P2B-3:** Given Claude 失败、output 为空/畸形/陈旧或身份不匹配，when policy job运行，then `review-policy-gate` fail closed 而不是 skipped。
- **AC-P2B-4:** Given pass、needs_fix 或 human_required verdict，when renderer运行，then它只从该 JSON 幂等创建/更新当前 SHA 评论，不把评论文本作为 gate 输入。
- **AC-P2B-5:** Given governance-sensitive workflow 变更，when Phase 2B 合入，then它仍处于 shadow，Ruleset、auto-merge、Fixer 和 Jenkins 行为均不变。

## Phase 2C — One-round repair

- 安装独立 Fixer App，只允许一次自动修复，验证普通 push 会触发新的 `synchronize` validation/review。

## Phase 3 — Enforcement and merge

- 将自动修复扩展到最多三轮，并启用重复 fingerprint、冲突、含糊结论和 permission stop guards。
- 新增 CODEOWNERS 敏感路径 ownership；治理敏感变更继续要求人工确认。
- 经单独授权后，Ruleset 要求当前 SHA 的 `repo-validation`、`review-policy-gate` 和 resolved conversations，只允许 squash。
- 经单独授权后启用 auto-merge、merge 后远端 branch 删除、obsolete run cancellation 和 bounded artifact retention。

## Phase 4 — Jenkins hardening

- 作为独立治理敏感 PR 保留两个人工 `input`，把 Terraform/Vault credentials 缩小到实际需要的 stages。
- 让无凭据 validation 先于 credentialed plan/deploy setup；不改变 main push webhook 与人工 Apply/Deploy 语义。
- 以 policy test 防止后续 PR 静默删除人工审批边界。
