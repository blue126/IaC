---
title: 'AI Review Governance Ownership Readiness'
type: 'feature'
created: '2026-09-05'
baseline_commit: 'e5dd546e965e6878b5edffe093699c81ff1e0dce'
status: 'done'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-ai-review-loop-gate/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-ai-review-loop-gate/security-boundary.md'
  - '{project-root}/_bmad-output/specs/spec-ai-review-loop-gate/implementation-phases.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** AI PR Review Loop 的 Phase 2B 已提供当前 SHA 的 shadow validation 与 fail-closed review-policy gate，但仓库尚未声明治理敏感路径的 GitHub owner，也未把 ownership 规则与 GitHub Actions 目录纳入现有 governance-sensitive 分类。未来启用外部 enforcement 前，缺少最小的 repository-local ownership readiness 基线。

**Approach:** 新增以 `@blue126` 为 owner 的、仅覆盖治理敏感路径的 `.github/CODEOWNERS`；将 `.github/CODEOWNERS` 与 `.github/actions/**` 纳入现有分类器，并仅为新增分类行为扩展现有 fixture 测试。这是 GitHub readiness artifact，不等同于实际 merge enforcement。

## Boundaries & Constraints

**Always:** 保持 `repo-validation`、`claude-review`、`review-policy-gate` 的名称、触发器、权限和 shadow 行为不变；所有 ownership 与分类判断必须是 repository-local、确定性和只读的；`.github/CODEOWNERS` 只列出约定的治理敏感路径并使用 `@blue126`，不包含全仓 catch-all owner；继续保留 Jenkins 两个人工 `input` gate。

**Ask First:** 修改 GitHub Ruleset、branch protection、required checks、CODEOWNERS review enforcement、auto-merge、squash 设置、远端分支清理、artifact retention、GitHub team/身份权限、Actions secrets/default permissions，或任何 Jenkins、Terraform、Ansible、Vault 与部署行为。

**Never:** 不创建或调用 GitHub settings API，不新增 GitHub write 权限、标签/评论写入、merge 命令或外部配置工具；不把治理敏感 PR 的 `repo-validation` 变为失败；不修改 `.github/workflows/claude-review.yml`、`.github/workflows/repo-validation.yml`、`Jenkinsfile` 或生产基础设施；不实现 CODEOWNERS 解析器、owner 覆盖矩阵或替代位置的竞争性规则检查。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|---------------------------|----------------|
| Ownership rule change | PR diff changes `.github/CODEOWNERS` | Classifier emits `governance_sensitive=true`; existing validation remains shadow | Fixture test fails if the classification is absent |
| GitHub Action change | PR diff changes `.github/actions/**` | Classifier emits `governance_sensitive=true`; existing validation remains shadow | Fixture test fails if the classification is absent |
| Ordinary path | PR diff changes a non-governance Terraform or documentation file | Governance classification remains false | No owner-review or CI behavior is added |

</frozen-after-approval>

## Code Map

- `AGENTS.md` -- repository policy and external-write boundary; the Minimal-Scope Implementation rule requires this change to stay repository-local.
- `_bmad-output/specs/spec-ai-review-loop-gate/SPEC.md` -- canonical CAP-4 constraint: governance-sensitive paths must await human confirmation, while Phase 2B remains shadow.
- `_bmad-output/specs/spec-ai-review-loop-gate/security-boundary.md` -- source for the governance-sensitive path boundary and the separation between ownership data and external enforcement.
- `_bmad-output/specs/spec-ai-review-loop-gate/implementation-phases.md` -- Phase 3 requires CODEOWNERS but separately gates Ruleset and auto-merge behind explicit authorization.
- `scripts/ci/classify-pr.sh` -- classifies a base...head diff; extend its governance-path predicate for ownership rules and GitHub Actions only.
- `scripts/ci/validate-repository.sh` -- renders governance-sensitive changes as `human_required enforcement=shadow`; read-only behavior that must remain unchanged.
- `tests/ci/repo-validation-test.sh` -- existing fixture and static contract suite; extend it only with new classifier fixtures.
- `.github/CODEOWNERS` -- new, narrowly scoped ownership manifest for governance-sensitive paths only.

## Tasks & Acceptance

**Execution:**
- [x] `.github/CODEOWNERS` -- add a sole, narrowly scoped governance ownership manifest mapping GitHub automation, Jenkinsfiles, agent instructions, CI scripts/tests, secret bridges, the Vault source, and the ownership rule itself to `@blue126`; do not add a catch-all rule.
- [x] `scripts/ci/classify-pr.sh` -- classify `.github/CODEOWNERS` and `.github/actions/**` as governance-sensitive alongside the existing sensitive paths; preserve base/head diff and all other classifications.
- [x] `tests/ci/repo-validation-test.sh` -- add temporary-Git fixtures proving that changes to the ownership rule and GitHub Actions are governance-sensitive, while an ordinary path remains non-sensitive; retain the existing shadow-semantics assertion unchanged.

**Acceptance Criteria:**
- Given a checkout of the repository, when `.github/CODEOWNERS` is inspected, then it exists, maps only the agreed governance-sensitive paths to `@blue126`, and contains no all-repository catch-all rule.
- Given a PR diff that changes `.github/CODEOWNERS` or a path under `.github/actions/`, when `scripts/ci/classify-pr.sh` classifies the explicit base and head, then it emits `governance_sensitive=true`.
- Given a PR diff that changes an ordinary non-governance path, when the classifier runs, then it continues to emit `governance_sensitive=false`.
- Given a governance-sensitive change, when `scripts/ci/validate-repository.sh` runs, then it continues to report `human_required enforcement=shadow` and may complete successfully; no check becomes required or blocking in this scope.
- Given the completed change, when workflow contracts are inspected, then no GitHub settings API, Ruleset mutation, auto-merge, branch deletion, external write permission, Claude runtime permission change, Jenkins behavior change, Terraform/Ansible execution, or production secret access has been added.

## Verification

**Commands:**
- `TMPDIR="$TMPDIR" bash tests/ci/repo-validation-test.sh` -- expected: the classifier fixtures and existing repository-validation contract pass.
- `TMPDIR="$TMPDIR" bash tests/ci/review-policy-gate-test.sh` -- expected: the existing one-call review, current-SHA, renderer, and minimal-permission contract remains passing.
- `git diff --check` -- expected: no whitespace errors in the scoped change.

## Suggested Review Order

**Ownership policy**

- Review the scoped ownership boundary before considering enforcement.
  [`CODEOWNERS:1`](../../.github/CODEOWNERS#L1)

**Governance classification**

- Confirm ownership and GitHub Action changes enter the existing shadow path.
  [`classify-pr.sh:112`](../../scripts/ci/classify-pr.sh#L112)

**Regression evidence**

- Review fixtures for the two new sensitive paths and ordinary-path preservation.
  [`repo-validation-test.sh:102`](../../tests/ci/repo-validation-test.sh#L102)

**Repository instruction**

- Review the user-approved minimal-scope rule that constrained this delivery.
  [`AGENTS.md:171`](../../AGENTS.md#L171)
