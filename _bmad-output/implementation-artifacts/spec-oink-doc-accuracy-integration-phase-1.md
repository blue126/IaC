---
title: 'Known-claim documentation consistency gate / 已知文档声明一致性门禁'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'bba0e1f7a3a6a06df14b5b5c7ec6c508f58ef041'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 仓库缺少关键部署文档与 checked-in Ansible defaults 之间的确定性回归门禁，过期端口、镜像或版本可能误导维护者和 coding agent。该门禁只保障显式登记的已知值，不承担开放式 claim 发现或生产事实认证。

**Approach:** 对 canonical registry 当前六条 claim 实现 stdlib-only deterministic consistency detector、稳定 JSON report、fixture suite 和无特权 PR workflow；它作为后续 AI discovery/repair 的 evidence 与修改后验收层。Notion credential GUI 是独立人工路径，不进入 detector/CI 信任面。

## Boundaries & Constraints

**Always:** 只读 registry 指定的两份 Markdown 和两份 defaults；要求 locator/oracle 唯一；按 typed scalar exact equality 判定；report 绑定 Git revision 与两个输入 SHA-256；独立锁定六个 claim ID；任一 `contradiction`/`indeterminate` 均 exit 1。

**Ask First:** 扩大 claim registry、将 report 公开渲染到 OINK/Pages、引入真实 AI/runtime evidence、修改 Notion/Jenkins 或设为 Ruleset required check。

**Never:** 读取 `.env`、Vault、tfvars、Terraform state、Notion 或生产 API；输出原始异常/文档片段/环境值；把 `verified` 表述为生产或绝对事实；自动修文档、开 PR 或 merge；写入 `docs/`、`docs-site/`、`public/` 或 `llms.txt`；触发 deploy/publish/apply。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Verified | locator/oracle 各唯一且同类型同值 | 六条均为 `verified`; exit 0 | report locator, values, revision, digests；不声称生产正确 |
| Contradiction | 两端唯一可解析但值/类型不同 | `contradiction`; exit 1 | 不修改输入 |
| Indeterminate | source/heading/key 缺失、重复或非标量 | `indeterminate` + enum reason; exit 1 | 不回显原始内容 |
| Registry shrink/reorder | 运行时 `CLAIMS` 偏离六 ID baseline | fixture suite 失败 | 必须人工批准并同步代码、测试与 registry |

</frozen-after-approval>

## Code Map

- `_bmad-output/specs/spec-oink-doc-accuracy-integration/claim-registry.md` -- closed claims、consistency status contract 与 required fixtures。
- `docs/deployment/netbox-deployment.md:87-98` + `ansible/roles/netbox/defaults/main.yml:1-10` -- NetBox table locator 与 port/image oracle。
- `docs/designs/qwen3-tts-openai-api-integration.md:52-60` + `ansible/roles/qwen3-tts/defaults/main.yml:22-62` -- Qwen3-TTS fenced-YAML locator 与 image/GPU/port/free-VRAM oracle。
- `Jenkinsfile:52,94,220,326,377` -- `scripts/**` 与 secret/runtime/deploy 路径；detector 位于 `tools/`，避免进入该特权路径。
- `.github/workflows/docs-pages.yml:3-116`, `docs-site/scripts/prepare-content.py:62-91` -- 公开发布边界；report 仍只作为 ignored local/CI artifact。

## Tasks & Acceptance

**Execution:**
- [x] `tools/check-doc-claims.py` -- 维护当前六条 claim、section-scoped Markdown locator、受限 YAML scalar parser、stable report 与 `--output`。
- [x] `tests/doc-claims/doc-claims-test.py` -- 独立锁定六 ID，并用临时 fixtures 覆盖 verified/contradiction、缺失/重复 locator/key、非标量、type mismatch、schema/sentinel 和 CLI exit code。
- [x] `.github/workflows/doc-accuracy.yml` -- 所有 `pull_request` 上运行只读离线 tests + detector，并用 `if: always()` 上传 `tmp/doc-accuracy/report.json`。

**Acceptance Criteria:**
- Given clean repository inputs, when CLI runs offline, then exactly six known claims are `verified`, report has stable order/revision/digests, and exit code is 0.
- Given any contradiction or indeterminate fixture, when CLI runs, then it exits 1 with an enum reason, emits no absolute temp path/free-form source/secret sentinel, and changes no documentation.
- Given the runtime claim list loses, replaces or reorders an ID, when the repository fixture runs, then it fails against the independently declared six-ID baseline.
- Given a pull request, when doc-accuracy workflow runs, then no real AI/Notion/Vault/runtime/deploy path is reachable and the non-sensitive report remains downloadable even on failure.

## Spec Change Log

- 2026-09-05 — Human renegotiation aligned this done artifact with the current six-claim NetBox + Qwen3-TTS implementation, retired llm-server paths, independent ID baseline and consistency-only semantics. This preserves the delivered Phase 1 boundary while avoiding the known-bad claim that it performs open-world or production correctness detection.

## Design Notes

- Parse only top-level registry-required YAML scalars; detect duplicate keys before conversion. Preserve types: quoted `"3000"` is not integer `3000`.
- `verified` means only that the selected Markdown and defaults values agree. If both move to the same wrong value, this pairwise gate can still pass; AI semantic eval or later runtime evidence addresses different questions.
- Write reports to ignored `tmp/doc-accuracy/report.json`; public OINK rendering remains separately gated.
- Notion remains an intentional credential GUI and is entirely outside this detector process and CI trust boundary.

## Verification

**Commands:**
- `python3 tests/doc-claims/doc-claims-test.py` -- six-ID baseline and fixture matrix pass without third-party packages/network.
- `python3 tools/check-doc-claims.py --root . --output tmp/doc-accuracy/report.json` -- six claims verified, exit 0.
- `python3 -m py_compile tools/check-doc-claims.py tests/doc-claims/doc-claims-test.py` -- syntax passes.
- `git diff --check` -- no whitespace errors.

## Suggested Review Order

**Closed registry and evaluation**

- Six explicit claim IDs are the entire deterministic protection boundary; AI candidate discovery is separate.
  [`check-doc-claims.py:289`](../../tools/check-doc-claims.py#L289)

- Per-claim uniqueness, type and consistency status converge here.
  [`check-doc-claims.py:401`](../../tools/check-doc-claims.py#L401)

**Fail-closed parsing and evidence safety**

- Restricted scalar parsing rejects ambiguous YAML semantics instead of guessing.
  [`check-doc-claims.py:58`](../../tools/check-doc-claims.py#L58)

- The section state machine excludes fake headings inside fenced code.
  [`check-doc-claims.py:154`](../../tools/check-doc-claims.py#L154)

- The header-driven table locator extracts only the target section's Default column.
  [`check-doc-claims.py:210`](../../tools/check-doc-claims.py#L210)

- The fenced-YAML locator tracks marker length and requires a unique key.
  [`check-doc-claims.py:252`](../../tools/check-doc-claims.py#L252)

- Source resolution rejects symlinks outside the checkout before reading.
  [`check-doc-claims.py:357`](../../tools/check-doc-claims.py#L357)

- Same-directory temporary files and atomic replacement prevent partial reports.
  [`check-doc-claims.py:470`](../../tools/check-doc-claims.py#L470)

**Verification and PR automation**

- The repository fixture independently locks six IDs, order, status, revision and digests.
  [`doc-claims-test.py:142`](../../tests/doc-claims/doc-claims-test.py#L142)

- Edge fixtures cover type handling, Markdown variants, symlinks and atomic failure.
  [`doc-claims-test.py:158`](../../tests/doc-claims/doc-claims-test.py#L158)

- Every PR runs the read-only workflow and retains a report even on failure.
  [`doc-accuracy.yml:3`](../../.github/workflows/doc-accuracy.yml#L3)
