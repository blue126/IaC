---
title: 'AI doc-gardening candidate analysis / AI 文档治理候选分析'
type: 'feature'
created: '2026-08-30'
status: 'done'
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

## Suggested Review Order

**单文档封闭边界 / Single-document containment**

- 入口：manifest 只承载一个文档，多传即拒，不再静默 last-wins。
  [`build-candidate.py:235`](../../tools/doc-gardening/build-candidate.py#L235)

- 允许路径的唯一判定处；测试现在钉住的是这里而非文件是否存在。
  [`contract.py:83`](../../tools/doc-gardening/contract.py#L83)

- hunk header 声称从第 0 行开始时不再反向切片取到文末内容。
  [`build-candidate.py:67`](../../tools/doc-gardening/build-candidate.py#L67)

**密钥脱敏 / Secret redaction**

- base 侧被删除的密钥行仍在 hunk text 里，这道检查是唯一拦截点。
  [`build-candidate.py:214`](../../tools/doc-gardening/build-candidate.py#L214)

**审计记录可信度 / Audit-record truthfulness**

- 进入 live 前先认领 provenance，失败的 live run 不再记成离线回放。
  [`run-analysis.py:229`](../../tools/doc-gardening/run-analysis.py#L229)

- 只要 manifest 已知就欠一条记录，不再因 prompt/schema 未加载而无记录。
  [`run-analysis.py:264`](../../tools/doc-gardening/run-analysis.py#L264)

- 模型输出泄密与输入污染在记录里分开。
  [`run-analysis.py:270`](../../tools/doc-gardening/run-analysis.py#L270)

- 空候选列表是干净的"没发现"，不再等同于"无法判定"。
  [`run-analysis.py:245`](../../tools/doc-gardening/run-analysis.py#L245)

**Fail-closed 一致性 / Fail-closed consistency**

- 非 UTF-8 文档走 blocked exit 2，不再抛 traceback 出 exit 1。
  [`validate-contract.py:167`](../../tools/doc-gardening/validate-contract.py#L167)

- fixture 文件缺失不再被算作一次正确拒绝。
  [`evaluate.py:49`](../../tools/doc-gardening/evaluate.py#L49)

**契约双写对齐 / Contract duplication pinned**

- 新增的 reason 同时进入验证器常量与模型可见 schema。
  [`contract.py:39`](../../tools/doc-gardening/contract.py#L39)

- schema 侧对应项。
  [`run-record-v1.json:43`](../../tools/doc-gardening/schemas/run-record-v1.json#L43)

**测试 / Tests**

- 断言拒绝的具体原因；两个 mutation 现在都会被抓到。
  [`doc-gardening-test.py:221`](../../tests/doc-gardening/doc-gardening-test.py#L221)

- 新增：密钥只存在于 base 侧时的拦截。
  [`doc-gardening-test.py:256`](../../tests/doc-gardening/doc-gardening-test.py#L256)

- schema 枚举与 contract.py 常量的等价性断言。
  [`doc-gardening-test.py:633`](../../tests/doc-gardening/doc-gardening-test.py#L633)

- fixture 跟随 main 的 claim 集改为 qwen3-tts；llm-server 已退役。
  [`doc-gardening-test.py:51`](../../tests/doc-gardening/doc-gardening-test.py#L51)

- 隔离宿主 git 配置，避免 commit.gpgsign 之类影响 fixture。
  [`doc-gardening-test.py:119`](../../tests/doc-gardening/doc-gardening-test.py#L119)
