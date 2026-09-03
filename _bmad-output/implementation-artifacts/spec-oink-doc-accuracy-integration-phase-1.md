---
title: 'Deterministic documentation drift detector / 确定性文档漂移检测器'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'bba0e1f7a3a6a06df14b5b5c7ec6c508f58ef041'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 仓库无法自动发现关键部署文档与已提交 Ansible defaults 之间的漂移，过期端口、镜像或版本会误导人和 coding agent。

**Approach:** 对 canonical registry 的四条 claim 实现 stdlib-only deterministic detector、稳定 JSON report、fixture suite 和无特权 PR workflow；Notion credential GUI 加固已拆为独立安全任务。

## Boundaries & Constraints

**Always:** 只读 registry 指定的两份 Markdown 和两份 defaults；要求 locator/oracle 唯一；按 typed scalar exact equality 判定；report 绑定 Git revision 与两个输入 SHA-256；任一 `contradiction`/`indeterminate` 均 exit 1。

**Ask First:** 扩大 claim registry、将 report 公开渲染到 OINK/Pages、引入 AI 编辑/runtime 证据、修改 Notion/Jenkins 或设为 Ruleset required check。

**Never:** 读取 `.env`、Vault、tfvars、Terraform state、Notion 或生产 API；输出原始异常/文档片段/环境值；自动修文档、开 PR 或 merge；写入 `docs/`、`docs-site/`、`public/` 或 `llms.txt`；触发 deploy/publish/apply。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Verified | locator/oracle 各唯一且同类型同值 | `verified`; exit 0 when all four pass | report locator, values, revision, digests |
| Contradiction | 两端唯一可解析但值/类型不同 | `contradiction`; exit 1 | 不修改输入 |
| Indeterminate | source/heading/key 缺失、重复或非标量 | `indeterminate` + enum reason; exit 1 | 不回显原始内容 |

</frozen-after-approval>

## Code Map

- `_bmad-output/specs/spec-oink-doc-accuracy-integration/claim-registry.md` -- closed claims、status contract 与 required fixtures；不扩大。
- `docs/deployment/netbox-deployment.md:87-98` + `ansible/roles/netbox/defaults/main.yml:1-10` -- table locator 及 port/image oracle；文档其他位置有同 key，必须限定 section。
- `docs/deployment/llm-server-deployment.md:120-160` + `ansible/roles/llm-server/defaults/main.yml:7-51` -- fenced-YAML locator 及 engine/webui oracle。
- `Jenkinsfile:36-44,178-217,269-364` -- `scripts/**` 进入特权 pipeline；detector 必须放 `tools/`。
- `.github/workflows/docs-pages.yml:3-116`, `docs-site/scripts/prepare-content.py:62-74` -- 公开发布边界；report 只能是 ignored local/CI artifact。

## Tasks & Acceptance

**Execution:**
- [x] `tools/check-doc-claims.py` -- 实现四条 claim、section-scoped Markdown locator、受限 YAML scalar parser、stable report 与 `--output`。
- [x] `tests/doc-claims/doc-claims-test.py` -- 用临时 fixtures 覆盖 verified/contradiction、缺失/重复 locator/key、非标量、type mismatch、schema/sentinel 和 CLI exit code。
- [x] `.github/workflows/doc-accuracy.yml` -- 添加 `pull_request` workflow；仅 `contents: read`，无 secrets/environment，运行 tests+detector，并用 `if: always()` 上传 `tmp/doc-accuracy/report.json`。

**Acceptance Criteria:**
- Given clean repository inputs, when CLI runs offline, then exactly four claims are `verified`, report has stable order/revision/digests, and exit code is 0.
- Given any contradiction or indeterminate fixture, when CLI runs, then it exits 1 with an enum reason, emits no absolute temp path/free-form source/secret sentinel, and changes no documentation.
- Given a pull request, when doc-accuracy workflow runs, then no Notion/Vault/runtime/deploy path is reachable and the non-sensitive report remains downloadable even on failure.

## Spec Change Log

## Design Notes

- Parse only top-level registry-required YAML scalars; detect duplicate keys before conversion. Preserve types, quoted `"3000"` is not integer `3000`.
- Write reports to ignored `tmp/doc-accuracy/report.json`; public OINK rendering is deferred until schema, freshness and disclosure policy receive separate approval.
- Notion remains an intentional credential GUI and is entirely outside this detector process and CI trust boundary.

## Verification

**Commands:**
- `python3 tests/doc-claims/doc-claims-test.py` -- fixture matrix passes without third-party packages/network.
- `python3 tools/check-doc-claims.py --root . --output tmp/doc-accuracy/report.json` -- four claims verified, exit 0.
- `python3 -m py_compile tools/check-doc-claims.py tests/doc-claims/doc-claims-test.py` -- syntax passes.
- `git diff --check` -- no whitespace errors.

## Suggested Review Order

**Closed registry and evaluation**

- 四条显式 claim 是全部保障边界，不做开放世界扫描。
  [`check-doc-claims.py:289`](../../tools/check-doc-claims.py#L289)

- 单条证据的唯一性、类型和状态在这里汇合。
  [`check-doc-claims.py:373`](../../tools/check-doc-claims.py#L373)

**Fail-closed parsing and evidence safety**

- 受限 scalar parser 拒绝暧昧 YAML 语义而不猜测。
  [`check-doc-claims.py:58`](../../tools/check-doc-claims.py#L58)

- Section 状态机排除 fenced code 中的假 heading。
  [`check-doc-claims.py:154`](../../tools/check-doc-claims.py#L154)

- Header-driven table locator 只提取目标 section 的 Default 列。
  [`check-doc-claims.py:210`](../../tools/check-doc-claims.py#L210)

- YAML fence locator 跟踪 marker 长度并要求唯一 key。
  [`check-doc-claims.py:252`](../../tools/check-doc-claims.py#L252)

- Source resolve 在读取前拒绝越出 checkout 的 symlink。
  [`check-doc-claims.py:329`](../../tools/check-doc-claims.py#L329)

- 同目录临时文件与 atomic replace 防止半份 report。
  [`check-doc-claims.py:442`](../../tools/check-doc-claims.py#L442)

**Verification and PR automation**

- Repository fixture 锁定四条 claim、顺序、revision 与 digests。
  [`doc-claims-test.py:96`](../../tests/doc-claims/doc-claims-test.py#L96)

- Edge fixtures 覆盖类型、Markdown 变体、symlink 和原子失败。
  [`doc-claims-test.py:128`](../../tests/doc-claims/doc-claims-test.py#L128)

- 所有 PR 都运行只读 workflow，失败也保留 report。
  [`doc-accuracy.yml:3`](../../.github/workflows/doc-accuracy.yml#L3)
