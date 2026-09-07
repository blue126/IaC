---
title: 'OINK Phase 2A shadow candidate discovery / OINK Phase 2A 影子候选发现'
type: 'feature'
created: '2026-09-06'
status: 'done'
review_loop_iteration: 0
baseline_commit: '95afcd02ca86f03c0e7f8c6721165f1e81dd300d'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Doc-gardening 仍需人工指定文档并运行 Codex，不能在 PR 上自动、完整且可审计地发现 changed-document candidates；现有 fixtures 也不代表模型判断质量。

**Approach:** 新增 deterministic controller 和 GitHub Actions Shadow workflow：同仓库非 Draft PR 最多选择五份 changed Markdown，逐文档将 revision-bound manifest 交给无工具的 Claude Opus 5，验证 structured output，输出数字 Summary 与 14 天 JSON artifact；不阻塞 PR、不生成编辑。

## Boundaries & Constraints

**Always:** 仅处理 `docs/deployment/`、`docs/designs/` 的 changed `.md`；按 PR merge-base/head 固定 revision、稳定排序、串行，最多 5 次调用、每文档 job 5 分钟、`--max-turns 2`、每文档最多 20 candidates。`A/M` 每文档一个 manifest；`D/R`、空 added、超预算均记录 no-analysis 且零调用。模型 job 只 checkout base SHA，并用可信 base code 回验 head Git object；Claude 使用 `--model claude-opus-5 --allowedTools "Read"`，且 prompt 只允许读 manifest 已命名的 trusted-base 路径，禁止 Vault、`.env`、tfvars/state、Notion、生产路径、命令、网络、MCP 与 PR head。只有 Action step 获得既有 `CLAUDE_CODE_OAUTH_TOKEN`；权限仅 `contents/pull-requests: read`。所有结果都是非阻塞 Shadow evidence。

**Ask First:** 提高 limits；允许 Draft/fork；更换模型/credential；增加 tools、评论/write permission、required check、schedule/full scan；上传 execution log；进入 Phase 2B；commit、push、PR 或 merge。

**Never:** `pull_request_target`；在持模型凭据的 job checkout/执行 PR head；将 repository/PR 文本当指令；读取 `.env`、Vault、tfvars/state、Notion 或生产系统；让 Claude 声称 `verified`、产生 edit 或修改仓库；上传 prompt、execution log 或敏感派生数据。

## I/O & Edge-Case Matrix

| Scenario | Expected behavior | Failure behavior |
|---|---|---|
| In-scope `M` | one v2 manifest + one Shadow call | trusted Git-object validation |
| Non-empty `A` | added hunk/span; empty evidence allowed | unexpected base presence blocked |
| `D/R` or empty `A` | explicit no-analysis; zero calls | never silently omitted |
| No Phase 1 evidence | only `unknown/missing_evidence`, no edit | non-unknown rejected |
| More than 5 A/M | first five stable paths selected | remainder `budget_exhausted` |
| Draft/fork/no match/bootstrap | no credentialed call | audited skip; future PRs use merged trusted runtime |
| Secret/stale/action failure | no accepted candidate | safe blocked envelope; aggregation still runs |

</frozen-after-approval>

## Code Map

- `_bmad-output/specs/spec-oink-doc-accuracy-integration/automation-roadmap.md:62-73,98-106` -- canonical boundary.
- `tools/doc-gardening/{contract.py,build-candidate.py,validate-contract.py,run-analysis.py}` -- reuse v1 primitives; add compatible v2, trusted-object validation and shared provenance.
- `tools/doc-gardening/scan-changed-docs.py` -- new bounded prepare/finalize/aggregate controller.
- `.github/workflows/claude-review.yml:3-89` -- reuse pinned Action/OAuth/output pattern, not its comment renderer.
- `.github/workflows/doc-candidate-discovery.yml` -- credentialless discovery → base-only matrix → aggregation.
- `tests/doc-gardening/` -- add Phase 2A tests while retaining v1 fixtures.

## Tasks & Acceptance

**Execution:**
- [x] `tools/doc-gardening/{contract.py,build-candidate.py,validate-contract.py,run-analysis.py,schemas/}` -- add backward-compatible v2/Shadow contracts and trusted-object validation.
- [x] `tools/doc-gardening/scan-changed-docs.py` -- implement deterministic prepare/finalize/aggregate and explicit skip/budget outcomes.
- [x] `.github/workflows/doc-candidate-discovery.yml` -- implement read-only Claude Opus 5 Shadow matrix, numeric Summary and 14-day artifacts.
- [x] `tests/doc-gardening/candidate-discovery-test.py` plus offline validation entry points -- cover every matrix row with fake model output; never call Claude.
- [x] `automation-roadmap.md` and `.memlog.md` -- mark Shadow delivered without claiming model quality or Phase 2B.

**Acceptance Criteria:**
- Given any base/head diff, when prepare runs, then every in-scope A/M/D/R has one stable disposition, at most five A/M are selected, and no out-of-scope content enters a manifest.
- Given an untrusted manifest, when a credentialed matrix job starts, then trusted base code validates it against base/head objects before Claude receives exactly one inline manifest and no tools.
- Given any Claude outcome, when finalize/aggregate runs, then only contract-valid candidates are accepted, every failure/skip remains represented, Summary is numeric-only, and artifacts exclude execution logs/secrets.
- Given Shadow Mode, when candidates or failures occur, then no policy gate, file, comment, commit, push or PR is produced.
- Given final code, when offline repository checks run, then existing Phase 1/2 and new Phase 2A tests pass without live AI or external writes.

## Spec Change Log

- 2026-09-07 human renegotiation: the known-working `claude-review` Action establishes that Claude Code structured output needs a successful read/tool turn. The model is therefore granted only `Read` at most once within the two-turn bound, from the trusted merge-base checkout; the fixed prompt narrows that read to manifest-named paths and keeps sensitive/production paths forbidden.
- 2026-09-07 human renegotiation: live Actions evidence established that the pinned Claude Code Action consumes a tool attempt before it can emit structured output. `--max-turns 1` therefore makes a no-tool Shadow invocation impossible. The bound is raised to 2; `--disallowedTools "*"`, base-only checkout, read-only permissions, serial execution and the 5-minute job limit remain unchanged.
- 2026-09-06 review: `prepare` 在 PR head checkout 中运行 controller，因此矩阵与 disposition 集本身不可信。Shadow 结果不阻塞任何 gate，隐藏自己的文档不产生权限或门禁收益，凭据边界也仍由 base-only 的 `analyze`/`aggregate` 保证，故记录为 deferred，不在本 spec 内加固。进入 Phase 2B 前必须重新评估。

## Design Notes

The bootstrap PR cannot trust its own PR-head runtime: if base lacks Phase 2A validation, it records `runtime_not_bootstrapped`; later PRs use merged base code. `structured_output` is the only model result retained. Quality assessment waits for Phase 2B; Shadow data is not correctness evidence.

## Verification

**Commands:**
- `python3 tests/doc-gardening/candidate-discovery-test.py` -- selection, v2, security, budget and workflow contract pass offline.
- `python3 tests/doc-gardening/doc-gardening-test.py && python3 tests/doc-claims/doc-claims-test.py` -- v1/known-claim regressions pass.
- `python3 tools/doc-gardening/evaluate.py --fixtures tests/doc-gardening/fixtures` -- 11 v1 cases unchanged.
- `python3 -m py_compile tools/doc-gardening/*.py tests/doc-gardening/*.py && ./scripts/ci/validate-documentation.sh false && git diff --check` -- repository-only checks pass; no live Claude.
