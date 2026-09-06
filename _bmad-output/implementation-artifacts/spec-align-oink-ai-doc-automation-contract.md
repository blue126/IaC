---
title: 'Align OINK AI documentation automation contract / 对齐 OINK AI 文档自动化契约'
type: 'refactor'
created: '2026-09-05'
status: 'done'
review_loop_iteration: 1
baseline_commit: 'e5dd546e965e6878b5edffe093699c81ff1e0dce'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** OINK 契约仍把 Notion 去凭据化列为阻塞项，把六条已知 claim 的一致性检查混同于通用漂移检测，并残留“四条 claim”、退役 llm-server 和失效锚点。CI 名称也容易让人误以为真实 AI 检测与修复已经自动运行。

**Approach:** 对齐 canonical contract、done artifacts、CI 标签和回归测试：记录 Notion credential GUI 的 accepted risk；将静态 detector 定位为 consistency/regression/acceptance gate；如实定义离线 fixtures；并写明 AI discovery → deterministic gate → minimal patch → validation → Draft PR 路线。本次不接通模型或 publisher。

## Boundaries & Constraints

**Always:** Notion credential sync 是独立 inventory/deployment 路径，accepted scope 包含人工运行和现有 Jenkins post-deploy stage；文档 AI/CI、OINK/Pages、manifest/report 不得调用或消费它、其输出、`.env`、Vault、tfvars/state 或凭据。测试独立锁定 NetBox 两条与 Qwen3-TTS 四条 claim。`verified` 仅表示 Markdown 与 checked-in defaults 同类型同值，不证明生产现实。AI 负责发现/写作，普通代码负责 scope、证据、staleness 和验收。

**Ask First:** 真实 AI、应用 patch、schedule、secret、write permission、publisher、runtime collector、commit/push/Draft PR、公开 report 或扩大 registry。

**Never:** 改变 Notion credential behavior；读取真实秘密或生产系统；部署、apply、自动 merge；将 fixture 指标称为模型准确率，或将 pairwise consistency 称为现实 correctness。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Accepted risk | 私人 Notion GUI + 人工/Jenkins post-deploy sync | 记录理由、既有执行路径、隔离与复审触发器；不再阻塞 OINK/AI | 文档自动化接触该路径即违反硬边界 |
| Claim baseline | 当前六个 ID | 独立常量锁定顺序与 `verified` | 删除、重排、替换或非 verified 均失败 |
| Capability wording | 离线检查及手动 live Codex | 区分 contract tests、真实 AI 与未实现 apply/PR | 不声称 CI 已测模型质量或自动修复 |

</frozen-after-approval>

## Code Map

- `_bmad-output/specs/spec-oink-doc-accuracy-integration/` -- 更新 `SPEC.md`、`security-boundary.md`、`claim-registry.md`；新增 `automation-roadmap.md` companion。
- `_bmad-output/implementation-artifacts/spec-oink-doc-accuracy-integration-phase-1.md:15-117` -- 修正 8 处四条/llm-server 漂移及 source anchors。
- `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md:13-76` -- 手动 live Codex、offline replay、只产 proposal 的现状依据。
- `tools/check-doc-claims.py:289-457` -- 六条权威 claim；`registry_value` 仅辅助脱敏，不是第三事实源。
- `tests/doc-claims/doc-claims-test.py:87-156` -- 用独立 expected-ID tuple 取代 `>= 4` 和同源自比较。
- `tests/doc-gardening/doc-gardening-test.py:227-811`, `tools/doc-gardening/evaluate.py:29-101` -- controller contract 与 11 个 golden accept/reject fixtures。
- `.github/workflows/doc-accuracy.yml:22-32`, `scripts/ci/validate-documentation.sh:22-29` -- 只改步骤名称/注释，不加模型或写权限。

## Tasks & Acceptance

**Execution:**
- [x] `_bmad-output/specs/spec-oink-doc-accuracy-integration/` -- 对齐 risk、consistency 语义、suite 术语和自动化路线。
- [x] `_bmad-output/implementation-artifacts/{spec-oink-doc-accuracy-integration-phase-1.md,spec-doc-gardening-phase-2.md}` -- 修复历史事实、路径和锚点，保留 done 边界。
- [x] `tests/doc-claims/doc-claims-test.py` -- 独立锁定六个 ID、顺序与 verified 结果。
- [x] `.github/workflows/doc-accuracy.yml`, `scripts/ci/validate-documentation.sh` -- 如实命名四个离线验证步骤。

**Acceptance Criteria:**
- Given 私人 Notion 设计，when 阅读 contract，then 它是有条件 accepted risk、不再阻塞 OINK/AI，且自动化仍禁止接触凭据路径。
- Given 当前 `CLAIMS`，when 删除、重排或替换任一 ID，then fixture test 失败；保持 registry 时六条全部 verified。
- Given workflow 与 companions，when 判断能力，then 可区分离线测试、手动 live AI、未实现 apply/Draft PR 与后置 runtime evidence。
- Given 最终 diff，when 运行 repository-only validation，then 全部通过且无外部写或真实 AI。

## Spec Change Log

- 2026-09-05 — Review found the accepted-risk scope incorrectly described the synchronizer as manual-only while `Jenkinsfile` already runs it after Ansible deployment. Human confirmed the risk includes that existing Jenkins path. The contract and isolation test now distinguish the credential-bearing inventory/deployment path from documentation AI/OINK automation. KEEP: accepted risk remains narrow; no Jenkins behavior changes and no credential path enters documentation automation.

## Design Notes

Accepted risk 仅覆盖项目所有者有意将凭据存入私人 Notion workspace，并通过人工或当前 Jenkins post-deploy stage 同步的 SaaS/账户与执行风险；仓库多人化、数据库共享、增加其他无人值守触发或数据进入模型/公开制品时必须复审。OINK、AI worker 与 deterministic control plane 保持分层。

## Verification

**Commands:**
- `python3 tests/doc-claims/doc-claims-test.py` -- 六 ID 与 edge fixtures 通过。
- `python3 tests/doc-gardening/doc-gardening-test.py && python3 tools/doc-gardening/evaluate.py --fixtures tests/doc-gardening/fixtures` -- 离线 contract/golden cases 通过。
- `python3 -m py_compile tools/check-doc-claims.py tools/doc-gardening/*.py tests/doc-claims/doc-claims-test.py tests/doc-gardening/doc-gardening-test.py` -- 语法通过。
- `./scripts/ci/validate-documentation.sh false && git diff --check` -- repository-only validation 与 whitespace 通过。

**Final results (2026-09-05, baseline `e5dd546e965e6878b5edffe093699c81ff1e0dce`):**
- Repository-only validation passed: 23 known-claim/isolation tests, 20 controller contract tests, 11/11 recorded fixtures, and 6/6 current claim comparisons.
- Python compilation and `git diff --check` passed. Hugo was correctly not run because no OINK site input changed.
- No live AI, Notion/production call, patch apply, deployment, commit, push or PR operation ran.

## Suggested Review Order

**Canonical contract and risk boundary**

- Start with the current capability states and superseded Notion gate.
  [`SPEC.md:15`](../specs/spec-oink-doc-accuracy-integration/SPEC.md#L15)

- Confirm accepted scope includes direct and existing Jenkins execution only.
  [`security-boundary.md:3`](../specs/spec-oink-doc-accuracy-integration/security-boundary.md#L3)

- Verify documentation automation remains outside all credential-bearing paths.
  [`security-boundary.md:32`](../specs/spec-oink-doc-accuracy-integration/security-boundary.md#L32)

**AI automation route**

- Establish what is delivered, prototyped, planned, and deferred.
  [`automation-roadmap.md:15`](../specs/spec-oink-doc-accuracy-integration/automation-roadmap.md#L15)

- Follow the controller-owned path from discovery through human-reviewed Draft PR.
  [`automation-roadmap.md:45`](../specs/spec-oink-doc-accuracy-integration/automation-roadmap.md#L45)

- Review changed-file discovery and the separately gated snapshot-manifest requirement.
  [`automation-roadmap.md:62`](../specs/spec-oink-doc-accuracy-integration/automation-roadmap.md#L62)

- Review deterministic resolver, validation, trusted publisher, and authorization boundaries.
  [`automation-roadmap.md:75`](../specs/spec-oink-doc-accuracy-integration/automation-roadmap.md#L75)

**Known-claim regression and isolation tests**

- Confirm registry authority, six-ID projection, and consistency-only semantics.
  [`claim-registry.md:5`](../specs/spec-oink-doc-accuracy-integration/claim-registry.md#L5)

- Inspect the independent six-ID baseline before repository assertions.
  [`doc-claims-test.py:87`](../../tests/doc-claims/doc-claims-test.py#L87)

- Verify Jenkins is accepted while documentation automation stays isolated.
  [`doc-claims-test.py:358`](../../tests/doc-claims/doc-claims-test.py#L358)

**Historical alignment and CI labels**

- Review the Phase 1 six-claim erratum and corrected anchors.
  [`spec-oink-doc-accuracy-integration-phase-1.md:59`](spec-oink-doc-accuracy-integration-phase-1.md#L59)

- Confirm Phase 2 remains an offline/manual prototype without apply or publisher.
  [`spec-doc-gardening-phase-2.md:63`](spec-doc-gardening-phase-2.md#L63)

- End with the four accurately named read-only workflow steps.
  [`doc-accuracy.yml:22`](../../.github/workflows/doc-accuracy.yml#L22)
