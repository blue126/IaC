# OINK AI Documentation Automation Roadmap

## Contract role

本 companion 说明现有交付物是什么、离线测试实际证明什么，以及从当前手动 AI prototype 到自动 Draft PR 的阶段边界。它不授权模型调用、GitHub 写入、生产访问或公开报告。

现有文档不整体作废：

- [SPEC.md](SPEC.md) 与本目录 companions 是当前 canonical contract；
- `spec-oink-doc-accuracy-integration-phase-1.md` 保留 `done`，作为带 change log 的滚动交付记录，反映 known-claim consistency gate 的当前已交付范围，而非不可变的原始快照；
- `spec-doc-gardening-phase-2.md` 保留 `done`，同样作为滚动交付记录，反映单文档 manifest、手动 live Codex、recorded replay 与 proposal validation 的当前已交付范围；
- `spec-doc-gardening-agent/SPEC.md` 继续提供更广义的 evidence gate、人工升级和不自动 merge 原则；其中 production observation/runtime evidence 属于本路线 Phase 3，不代表当前已实现；
- 本路线扩展而非替换上述成果；若历史 artifact 与当前能力描述冲突，以 canonical contract 与可执行代码/测试为准，并修正历史事实说明。

## Current capability / 当前能力

| Component | State | What exists | What does not exist |
|---|---|---|---|
| OINK/Hugo site | Delivered | Repository Markdown rendering and GitHub Pages workflow | Accuracy report is not publicly rendered |
| Phase 1 consistency gate | Delivered | Six explicit Markdown/defaults comparisons, stable report, read-only PR check | Open-ended claim discovery, production truth or semantic repair |
| Phase 2 AI controller prototype | Delivered | Single-document manifest, strict candidate/proposal schemas, recorded replay, explicitly confirmed local `codex exec` | Patch application or PR publication |
| Phase 2A Shadow candidate discovery | Delivered | Deterministic changed-document selection, v2 manifests, trusted base-object validation, bounded read-only Claude matrix, numeric Summary and 14-day JSON evidence | Model-quality proof, unchanged-document inference, edits, comments or policy enforcement |
| Automated repair loop | Not implemented | Contract and reusable validator primitives plus non-writing Shadow evidence | Isolated apply, write identity and Draft PR publisher |
| Runtime evidence | Deferred | Policy and observation design | Credentialed collectors and production reconciliation |

The current live implementation in `tools/doc-gardening/run-analysis.py` uses a locally installed Codex CLI only when both `--live` and `--confirm-live` are supplied. Its default model is an implementation detail, not a correctness authority. Existing CI never takes this path.

## Validation suite glossary

### Known-claim regression suite

`tests/doc-claims/doc-claims-test.py` tests the deterministic Markdown/defaults consistency checker: exact typed equality, contradiction/indeterminate states, locator/parser failures, provenance, secret-safe report behavior, atomic writes, CLI exits and the read-only workflow contract. It independently pins the six current claim IDs. It does **not** discover claims, call AI, validate production or prove that two matching values are objectively correct.

### Doc-gardening controller/contract suite

`tests/doc-gardening/doc-gardening-test.py` builds synthetic Git repositories and tests manifest packaging, single-document/path scope, source spans, hashes, evidence references, secret/stale rejection, strict model-output validation, proposal binding and recorded-output replay. Its live-mode test proves only that an unconfirmed call is blocked; the suite does not execute a model or assess model judgment.

### Phase 2A Shadow candidate-discovery suite

`tests/doc-gardening/candidate-discovery-test.py` 使用 synthetic Git repositories 与 fake structured output 覆盖 changed-path stable selection、A/M/D/R disposition、5-document/20-candidate limits、base-only trusted-object revalidation、无 Phase 1 evidence 时的 `unknown/missing_evidence`、secret/stale/action failure、bootstrap 与 workflow least-privilege contract。它不调用 Claude，也不证明模型能正确发现 stale claims。

### Recorded golden accept/reject fixtures

`tools/doc-gardening/evaluate.py` evaluates 11 prerecorded valid and hostile artifacts against the validator. `false_proposals` and `security_leakage` are fixture contract mismatches, not real-world model precision, recall or leakage measurements. Passing means the validator accepted/rejected the recorded cases as specified.

### Repository consistency run

`tools/check-doc-claims.py` evaluates the current six known claims and writes the local/CI report. This is the final deterministic regression for those six pairs, not a whole-document audit.

## Target architecture

```text
PR change or approved schedule
  -> deterministic document selection
  -> one secret-safe manifest per document/revision
  -> AI candidate discovery
  -> deterministic source/evidence/staleness gate
  -> AI minimal edit proposal
  -> deterministic proposal binding and isolated apply
  -> known-claim regression + document/OINK validation
  -> least-privilege publisher creates one Draft PR
  -> human review and merge
```

AI owns semantic discovery and prose generation. The controller owns document allowlists, evidence selection, state transitions, retries, revision binding, patch scope, validation and publish eligibility. The publisher receives only an already validated single-document patch and non-sensitive audit summary; it never receives model, Notion or production credentials.

## Phase 2A — Automated candidate discovery

**Goal:** automatically find likely stale claims without modifying the repository.

1. The initial deterministic trigger selects only changed Markdown files under `docs/deployment/` and `docs/designs/`; deleted/renamed files are recorded as no-analysis audit outcomes rather than silently omitted. “Impacted but unchanged” inference is deferred until a versioned dependency-selection contract exists.
2. Changed-file runs reuse the existing base/head diff manifest. A separately approved periodic full scan must first add a versioned snapshot-manifest mode that deterministically enumerates every allowed document and creates current-revision spans without requiring a diff; the current builder cannot represent unchanged documents.
3. Every model-visible document, diff hunk and repository evidence item is untrusted data, never an operator instruction. PR bodies, issues/comments and commit messages are excluded from prompts.
4. The AI returns only schema-valid `candidate_contradiction`, `possibly_stale` or `unknown` entries bound to exact spans and evidence references.
5. The validator rejects stale hashes, invented quotes/references, secret-bearing content, out-of-scope paths and multi-document outputs.
6. Valid candidates are audit artifacts only. `unknown` and evidence conflicts remain no-change results.
7. Credentialed jobs check out only the PR merge base, use trusted base code to reconstruct head Git-object provenance, and never execute PR-head code; the bootstrap PR records `runtime_not_bootstrapped` and makes zero model calls.
8. Claude Opus 5 receives one inline manifest with all tools disallowed and at most two turns. The first denied tool attempt is safe; only `structured_output` enters the final report, and prompts and execution logs are not uploaded as evidence artifacts.

**Delivered Shadow evidence:** `.github/workflows/doc-candidate-discovery.yml` 自动运行只读候选发现，但结果仅为不阻塞 PR 的 evidence；它有固定 5-document/20-candidate limits、每文档 5 分钟 timeout、串行调用与 14 天 JSON retention。离线 synthetic/hostile fixtures 只验证 controller 和安全合同。模型质量、precision/recall、false-negative budget 与 labeled real-document corpus 仍未建立，因此不得据此进入 Phase 2B、应用 patch、发表评论或设置 required check。

## Phase 2B — Deterministic gate, minimal patch and Draft PR

**Goal:** turn only provable document drift into a reviewable one-document Draft PR.

1. The controller re-reads the candidate's exact revision and independently reconstructs its evidence. AI classification alone never authorizes an edit.
2. Only a candidate supported by an approved, versioned deterministic oracle resolver may enter proposal mode. Phase 1's six pairs are the only current resolvers; a registry-external candidate remains `unknown` until a parser, source schema, uniqueness rule and approval are added. Ambiguous truth, production drift and missing evidence also stop.
3. AI produces one exact FIND/REPLACE proposal per run, bound to the selected candidate, span and evidence IDs. Multiple or overlapping proposals are not combined.
4. The controller applies the proposal in an isolated automation worktree and rejects edits outside the selected document or intended span.
5. It reruns all six known claims, controller/contract tests, recorded fixtures and `scripts/ci/validate-documentation.sh`; when site inputs change it runs that command with Hugo validation enabled. The target contradiction must be resolved and no existing claim may regress.
6. A separate trusted publisher reconstructs and revalidates the patch against the pinned revision rather than trusting an artifact from an untrusted PR run. Only after every gate passes may it create an automation branch and **Draft PR** containing provenance and validation results. It cannot merge.

**Exit evidence:** end-to-end fixtures cover clean no-op, valid drift repair, stale input, hallucinated evidence, secret detection, validation regression, overlapping proposals, duplicate-run idempotency and publisher failure. The publisher implementation SPEC must define its idempotency key and partial-failure recovery. Model credentials, schedules, apply, commit, push and Draft PR are distinct authorization boundaries; automation stops before each external write unless the project owner has separately approved a durable policy for that exact boundary.

## Phase 3 — Runtime evidence

Runtime evidence remains deferred until a separately approved Phase 3 implementation SPEC defines measurable entry criteria, evidence freshness/retention, collector identity and rotation, replay/staleness handling, and required operating-history evidence. Narrow controller-owned collectors may then verify facts unavailable from checkout, using dedicated read-only identities and redacted, versioned evidence envelopes. Model workers never receive collector credentials or raw Terraform state.

Production disagreement with valid IaC is `production_drift`, not authorization to rewrite documentation. Unreachable, unauthorized, stale or ambiguous evidence remains unresolved and cannot produce a patch. The observation/retry policy in `spec-doc-gardening-agent/` governs this phase and must be revalidated before implementation.

## Optional OINK report presentation

OINK may later render a reviewed, non-sensitive summary of scan revision, known-claim states and unresolved candidate counts. This is a separate publication decision. A report may be shown only when its source revision matches the site source revision; a missing, stale or mismatched report must be omitted or fail the approved build policy, never presented as current. Build time is not evidence freshness, and no model prompt, raw diff, Notion data, runtime payload or credential-derived field may enter Pages or `llms.txt`.

## Invariants across all phases

- One model task, one proposal and one repair PR operate on one document at one pinned revision; proposals are never combined.
- All model-visible repository text is untrusted data; only fixed controller prompts carry operator instructions.
- AI can nominate and write; it cannot declare `verified`, authorize publishing or merge.
- Known-claim regression is preserved after every accepted patch but does not replace semantic evals.
- No evidence means no edit; `unknown` is a successful safe outcome, not a failure to bypass.
- Notion synchronization remains outside the entire pipeline under [security-boundary.md](security-boundary.md).
- Automatic merge, deployment, infrastructure writes and production remediation are never part of doc-gardening.
