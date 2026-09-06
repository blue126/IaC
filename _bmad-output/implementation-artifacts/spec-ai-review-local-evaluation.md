---
title: 'AI Review Local Evaluation'
type: 'refactor'
created: '2026-09-05'
baseline_commit: '3184bc10cec2d569b18877899ad43106c471037c'
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

**Problem:** `review-policy-gate` 目前 checkout 并执行 `blue126/agent-project-bootstrap` 的 external governance runtime，同时要求 Claude 回显 repository、PR number 与 SHA。评估规则属于本仓库 owner 的治理责任，而 GitHub event 已是这些身份事实的权威来源；当前设计造成不必要的跨仓库依赖与模型回显失败面。

**Approach:** 移除 review gate 与其 contract tests 对外部 runtime 的所有引用。Claude 只输出 `status` 与 `findings`；本仓库 workflow 用参数化 `jq` 验证完整 verdict 语义，并以确定性 shell 分支返回既有 pass / needs_fix / human_required gate 结果。同步更新当前设计与 canonical spec，历史 memlog 保持不变。

## Boundaries & Constraints

**Always:** 保持单次、只读、SHA-pinned Claude Action；保留 same-repository fork fail-closed、non-Draft 条件、per-PR cancellation、gate 的 `always()`、gate 不 checkout PR head、`pull-requests: write` 仅用于当前 HEAD 的 sanitized comment renderer，以及 shadow 状态。合法 verdict 的顶层字段仅为 `status` 与 `findings`；保留 finding 的类型、长度、相对路径、唯一 fingerprint 与 status/finding 语义约束。

**Ask First:** 修改 GitHub Ruleset、branch protection、required checks、auto-merge、branch deletion、Actions secrets/default permissions、模型或 Action pin、PR trigger、Jenkins、Terraform、Ansible、Vault、部署，或重新引入外部 evaluator/runtime。

**Never:** 不从 Claude verdict 读取或验证 repository、PR number、SHA；不使用 `agent-project-bootstrap`、`.governance-runtime`、`validate-review-verdict.sh` 或 `evaluate-ai-review-gate.sh`；不把自然语言评论、reaction 或模型 conclusion 当作 gate verdict；不放宽 malformed、redacted、上游失败、非法路径、重复 fingerprint 或语义矛盾 verdict 的 fail-closed 行为。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|---------------------------|----------------|
| Valid pass | `status=pass` with no blocking finding | Validate, render/update current-HEAD comment, gate exits 0 | N/A |
| Fix required | `status=needs_fix` with an actionable blocking finding | Validate and render current-HEAD comment, then gate exits 10 | Blocks gate without branch write |
| Human decision | `status=human_required` | Validate and render current-HEAD comment, then gate exits 11 | Blocks gate without branch write |
| Invalid verdict | Missing/extra field, invalid finding, duplicate fingerprint, illegal path, or inconsistent status | Validation fails before renderer/evaluator | No PR comment API call |
| Bad upstream | Claude job/conclusion fails or verdict is empty/redacted | Gate fails before verdict validation | No PR comment API call |

</frozen-after-approval>

## Code Map

- `.github/workflows/claude-review.yml` -- single-call review, bounded JSON export, deterministic gate, renderer, and shadow summary; replace only runtime checkout/validator/evaluator portions.
- `.github/workflows/repo-validation.yml` -- CI contract entry; stop checking out the removed runtime and invoke the local gate test with no argument.
- `tests/ci/review-policy-gate-test.sh` -- extracts workflow steps and executes fixtures; migrate assertions and fixtures from external scripts to workflow-local jq evaluation.
- `tests/ci/repo-validation-test.sh` -- static repository-validation workflow contract; remove the obsolete runtime setup expectation.
- `_bmad-output/specs/spec-ai-review-loop-gate/SPEC.md` -- canonical contract currently requires a public reusable workflow/runtime; revise current-state claims only.
- `_bmad-output/specs/spec-ai-review-loop-gate/implementation-phases.md` -- Phase 2B implementation record; revise evaluator and identity-binding wording without rewriting historical PR evidence.
- `_bmad-output/specs/spec-ai-review-loop-gate/validation-matrix.md` -- replace public runtime/adapter assumptions with local deterministic evaluation ownership.
- `docs/designs/cicd-architecture.md` -- current CI architecture; document repository-local jq validation and event-owned identity facts.

## Tasks & Acceptance

**Execution:**
- [x] `.github/workflows/claude-review.yml` -- reduce Claude schema/prompt to `status` and `findings`; remove runtime checkout; implement complete local `jq` verdict validation and existing exit semantics while preserving validation-before-rendering order.
- [x] `.github/workflows/repo-validation.yml` -- remove runtime checkout and run the local review-policy contract test without a runtime argument.
- [x] `tests/ci/review-policy-gate-test.sh` and `tests/ci/repo-validation-test.sh` -- execute workflow-extracted local jq steps for every matrix row and assert workflows contain no removed runtime references.
- [x] `_bmad-output/specs/spec-ai-review-loop-gate/SPEC.md`, `implementation-phases.md`, `validation-matrix.md`, and `docs/designs/cicd-architecture.md` -- align current architecture claims with repository-owned evaluation while preserving historical evidence and leaving `.memlog.md` unchanged.

**Acceptance Criteria:**
- Given a ready same-repository PR, when Claude returns a valid `pass` verdict containing only `status` and `findings`, then `review-policy-gate` validates it locally, renders one sanitized current-HEAD comment, and succeeds without any external runtime checkout.
- Given a valid `needs_fix` or `human_required` verdict, when the gate evaluates it, then it renders the current-HEAD comment and exits respectively 10 or 11 without any branch, merge, or settings write.
- Given an invalid verdict or bad upstream state, when the gate runs, then it fails before invoking the renderer and does not make a PR comment API call.
- Given repository validation CI, when its contract suite runs, then no executable workflow step or test invocation checks out or invokes `agent-project-bootstrap`, `.governance-runtime`, or its evaluator scripts; static negative assertions may name them only to prove absence.
- Given the current design/spec documents, when read after the change, then they describe repository-owned jq evaluation and GitHub-event identity ownership; historical memlog facts remain intact.

## Verification

**Commands:**
- `TMPDIR="$TMPDIR" bash tests/ci/review-policy-gate-test.sh` -- expected: all local evaluator, renderer, fail-closed, and no-runtime fixtures pass.
- `TMPDIR="$TMPDIR" bash tests/ci/repo-validation-test.sh` -- expected: repository-validation workflow contract passes without runtime setup.
- `git diff --check` -- expected: no whitespace errors.

## Suggested Review Order

**Verdict boundary**

- Confirm GitHub event values guide the review without entering model output.
  [`claude-review.yml:48`](../../.github/workflows/claude-review.yml#L48)

- Review the local fail-closed schema and gate exit semantics before rendering.
  [`claude-review.yml:100`](../../.github/workflows/claude-review.yml#L100)

**Contract evidence**

- Review local fixtures for valid, malformed, inconsistent, and failed-upstream verdicts.
  [`review-policy-gate-test.sh:77`](../../tests/ci/review-policy-gate-test.sh#L77)

- Confirm CI no longer materializes an external governance runtime.
  [`repo-validation.yml:52`](../../.github/workflows/repo-validation.yml#L52)

**Canonical record**

- Review Phase 2B documentation for repository-owned evaluation ownership.
  [`SPEC.md:15`](../specs/spec-ai-review-loop-gate/SPEC.md#L15)
