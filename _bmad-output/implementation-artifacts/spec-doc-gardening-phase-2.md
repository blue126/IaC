---
title: 'AI doc-gardening candidate analysis / AI 文档治理候选分析'
type: 'feature'
created: '2026-08-30'
status: 'in-review'
review_loop_iteration: 1
baseline_commit: '40852fa2d8abb7a2bef8b93305871c98def0865c'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Phase 1 只能确定性判定封闭 claim，无法从文档/diff 中提取新 claim、标记可能过期内容或生成可审查的最小编辑建议。

**Approach:** 构建 stdlib-only controller，将明确指定的单一文档、Git diff hunk 和脱敏 Phase 1 evidence 打包为封闭 manifest；在隔离临时目录用本机 `codex exec` 只读生成 schema-constrained candidate/edit-proposal artifact，再由 deterministic validator fail closed。

## Boundaries & Constraints

**Always:** 用户显式选择一份 `docs/deployment/` 或 `docs/designs/` Markdown；manifest 绑定 base/head、文件/hunk SHA 和 Phase 1 evidence ID；prompt/model/runtime/output hash 全记录；source span/quote/evidence ref 必须逐字回验；歧义、stale 或缺证据一律 `unknown|blocked`。

**Ask First:** 运行 live Codex 调用；安装 SDK/依赖；新增 OpenAI/GitHub secret、Actions workflow/environment/permission；应用补丁、创建 branch/PR；修改 canonical evidence gate。

**Never:** 读取 Vault/tfvars/Notion/production/runtime API；使用 `pull_request_target`、PR body/issue/comment/commit message 作 prompt；让模型扫描完整 checkout/网络；将 confidence 当授权；让 LLM 宣称 `verified|document_drift`；修改文档、开/merge PR 或接触 Phase 3 evidence。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Candidate | 单文档 manifest、有效 hunk/span/evidence refs | schema-valid candidate + optional exact FIND/REPLACE proposal | validator 复核全部 refs/hashes |
| Unknown | 缺失/重复 span、歧义或可能过期 | `unknown` + enum reason; `edit:null` | artifact 可审计，不 apply/publish |
| Hostile input | doc/diff 包含指令、secret sentinel 或伪 evidence ID | 指令视为 data；伪 ref/sentinel 被拒绝 | run blocked，无自由文本泄漏 |
| Stale/refusal | revision/SHA 变化、schema 错误、timeout/refusal | run record=`blocked|unknown` | 不重试扩权，不改 repo |

</frozen-after-approval>

## Code Map

- `tools/check-doc-claims.py:289-489` -- Phase 1 closed claims/report v1 producer；Phase 2 仅消费 CLI JSON，不 import parser internals。
- `tests/doc-claims/doc-claims-test.py:96-344` -- 22 项 fail-closed regression，Phase 2 验证前必须先通过。
- `.github/workflows/doc-accuracy.yml:3-34` -- 始终只读的 Phase 1 trust plane；不加 AI/secret/write permission。
- `_bmad-output/specs/spec-doc-gardening-agent/evidence-model.md:5-65` -- complete evidence loop 仍阻止 apply/publisher；Phase 2 只产候选 artifact。
- `_bmad-output/planning-artifacts/research/technical-oink-doc-accuracy-integration-2026-08-26/research.md:122-134` -- Phase 2 draft-only 与 Phase 3 runtime 边界。
- `AGENTS.md:106-114,126-130` -- 禁止自动 commit/merge、secret 和外部写入。

## Tasks & Acceptance

**Execution:**
- [x] `tools/doc-gardening/build-candidate.py`, `schemas/analysis-input-v1.json` -- 从 explicit document + base/head 构建脱敏、带 hunk ID/SHA/evidence ref 的封闭 manifest。
- [x] `tools/doc-gardening/schemas/{claim-candidates,edit-proposal,run-record}-v1.json`, `validate-contract.py` -- 固定 exact-key/type/enum 契约，回验 span/ref/revision/hash/path/single-document 边界。
- [x] `tools/doc-gardening/prompts/{analyze,propose}-v1.md`, `run-analysis.py` -- 用隔离 temp dir 调用 `codex exec --ephemeral --ignore-user-config --sandbox read-only --output-schema`；默认仅验证 recorded output，live 需确认。
- [x] `tools/doc-gardening/evaluate.py`, `tests/doc-gardening/doc-gardening-test.py`, `fixtures/` -- 覆盖 valid candidate、unknown、prompt injection、secret sentinel、伪 ref、stale SHA、multi-doc/out-of-scope、malformed/refusal 和 recorded replay eval。

**Acceptance Criteria:**
- Given an explicit allowed document and matching base/head, when candidate packaging runs, then output contains only allowlisted hunks/spans/evidence and stable hashes; unrelated files/environment never appear.
- Given recorded model outputs, when strict validation/eval runs offline, then valid single-document candidates pass and every hostile, stale, ambiguous, schema-extra or hallucinated-ref case fails closed without repo changes.
- Given a confirmed live run, when Codex executes, then its working root contains only manifest/prompt/schema, sandbox is read-only/ephemeral, and final artifact records prompt/model/runtime/output provenance.
- Given any Phase 2 outcome, when the run completes, then no document patch, branch, PR, secret, production call or GitHub permission change occurs.

## Spec Change Log

## Design Notes

- `codex exec` 0.149.1 已本地安装；不添加 SDK/package dependency。Official OpenAI Docs 支持 non-interactive、ephemeral、read-only sandbox 和 `--output-schema`.
- Controller 而非模型决定 gate。LLM 只能输出 `candidate_contradiction|possibly_stale|unknown`，不能签发事实或发布权限。
- GitHub-hosted Action/publisher 后置：当前无 Actions secrets/variables，default token 只读且未允许 Actions 创建 PR。

## Verification

**Commands:**
- `python3 tests/doc-gardening/doc-gardening-test.py` -- schema/manifest/validator/injection/stale/replay fixtures pass offline.
- `python3 tools/doc-gardening/evaluate.py --fixtures tests/doc-gardening/fixtures` -- golden metrics and zero false-proposal/security leakage gates pass.
- `python3 -m py_compile tools/doc-gardening/*.py tests/doc-gardening/doc-gardening-test.py` -- syntax passes without new packages.
- `python3 tests/doc-claims/doc-claims-test.py` -- Phase 1 regression remains 22/22.
- `git diff --check` -- no whitespace errors.
