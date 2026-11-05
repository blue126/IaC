---
title: 'wsctl reissue 重发设备包'
type: 'feature'
ticket: '5'
created: '2026-11-01'
status: 'done'
baseline_revision: 'adf5e669e55350fa2bdb3b589bc561e2f94d9715'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 员工的下载链接过期、用尽或丢失后，管理员要手写交付请求、分两步上传和发信才能重发。

**Approach:** 新增 `wsctl reissue --device <id>`：从 catalog 取该设备的员工邮箱，用 `bundle_output_dir/oci-hub/<device>` 的现有设备包，新建一个交付运行目录，按"展示计划 → 以同一 SHA 确认"上传到网站并发出邮件（purpose `reissue`，主题"你的设备接入包已重新发送"）。网站对同一设备的新包会让旧链接立即失效（3.4 已实现）。

**Decision:** 2026-11-01 用户要求推进到 epic 3 结束；reissue 不重新生成密钥、不改 VM，只重发现有设备包。

## Boundaries & Constraints

**Always:** 只在执行器运行；设备不在 catalog 或设备包目录不存在 → 拒绝（`REISSUE_DEVICE_UNKNOWN`、`REISSUE_BUNDLE_MISSING`）；计划输出包含 recipient、device_id、outer_sha256、邮件主题，审批 SHA 绑定这些内容；确认后依次执行现有 `publish` 与 `notify`（复用 deliver-temp 的收据与核对逻辑，不另写上传代码）；任一步失败按现有错误码停止，重跑同一运行目录可继续（publish/notify 已幂等）；邮件正文沿用 onboarding 模板（两步验证码下载说明），只换主题；Semaphore 增加 `wsctl reissue` 模板（带 WSCTL_APPROVE survey 与设备参数）。

**Never:** 不生成新密钥、不重新打包；不改 provision、enforce；不做 Temp.sh 退役（3.6）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 计划 | `reissue --device control --plan-only` | 输出 approval_sha256、recipient、outer_sha256、主题 | — |
| 执行 | `--approve <SHA>` | 新链接、邮件发出；收据 phase completed | — |
| 旧链接 | 重发后访问旧链接 | 410 | — |
| 未知设备 | catalog 无此设备 | 不出计划 | `REISSUE_DEVICE_UNKNOWN` |
| 无设备包 | 目录缺失 | 不出计划 | `REISSUE_BUNDLE_MISSING` |
| SHA 不符 | 计划后包被改 | 拒绝 | 现有 `PLAN_APPROVAL_MISMATCH` 或等价码 |

</frozen-after-approval>

## Code Map

私有代码 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（有用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交）。IaC 仓库部分：`ansible/roles/semaphore/files/semaphore-bootstrap.py` 的 TEMPLATES（主会话在 worktree 里做，实现时跳过）。不 commit、不 push、不调用网站或发信。

- `oci-hub-admin.py` -- `deliver` 分支（约 :416 起）、`delivery_binding()`（:260，purpose 白名单 `onboarding/trial/migration` 需加 `reissue`）、`require_delivery_owner()`；新增 `reissue` 动作：组装交付请求（profile、device_id、recipient、run_dir、bundle_dir、notify、purpose='reissue'），run_dir 放 `settings['oci_hub']['bundle_output_dir']` 旁的 `runs/reissue-<device>-<UTC 时间>`（或现有运行目录约定）。
- `deliver-temp.py` -- `load_bound()` purpose 白名单加 `reissue`；`mail_subject()` 对 reissue 返回"你的设备接入包已重新发送"；`publish()`、`notify()` 复用。
- `wsctl-confirm.py` -- 现有 `deliver` 流程（plan → deliver）；加 `reissue` 流程：plan 产出 approval，执行时先上传再发信（可在 oci-hub-admin 里实现一个 `reissue-apply` 依次调用 publish 与 notify）。
- `wsctl` -- 动作列表与执行器写入守卫加 `reissue`。
- 测试：`test-temp-delivery.py`、`test-oci-hub.py`、`test-wsctl.py`（打桩站点与邮件）。

## Tasks & Acceptance

**Execution:**
- [x] `oci-hub-admin.py`、`deliver-temp.py`、`wsctl-confirm.py`、`wsctl`、测试 -- reissue 计划与执行
- [x] IaC（主会话）-- Semaphore 模板 `wsctl reissue`
- [x] 部署与实测（hitl）-- 对 control 执行 reissue：新链接可用、旧链接 /d/c33beb63… 返回 410、邮件到达

**Acceptance Criteria:**
- Given control 已有有效链接，when `wsctl reissue --device control` 确认执行，then 旧链接 410，新邮件含新链接。

## Implementation Notes

- 运行目录用编号 `<bundle_output_dir 的上级>/runs/reissue-<device>-NNN`，不用 UTC 时间：Semaphore 的 plan-only 和 `--approve` 是两次独立运行，目录名必须确定。只有"无收据"或"收据 phase 为 uploaded/verified、未过期、outer_sha256 与当前包一致"的目录才沿用；其余（已完成、过期、uploading/notifying、SHA 不同、收据损坏）换下一个编号。
- 审批 SHA = fingerprint(request, outer_sha256, mail_digest)；mail_digest 是用固定占位链接 `https://reissue.invalid/d/000…` 渲染的主题+正文（含 mosh 措辞），计划把预览写到 `<run_dir>/mail-preview.html`。上传后用同一占位链接重新渲染，不一致 → `DELIVERY_APPROVAL_MISMATCH`，一致才用真实链接发信。
- 续跑一个 verified 的运行时，发信前先查站点状态（available 且 downloads==0）；站点说已失效（UNAVAILABLE / CHECKSUM_MISMATCH / BUNDLE_NOT_FOUND）→ 收据 phase 记为 `link_stale`，报 `REISSUE_LINK_STALE`，下一次计划换新目录。uploaded 阶段续跑时 publish 自身核对报同样的码，也按此处理。
- `oci-hub-admin.py reissue --device X` 出计划（只写预览）；`reissue-apply <SHA> --device X` 重新推导并核对 SHA，然后依次跑现有 `publish` 与 `notify`（purpose='reissue'）。失败时错误带 run_dir。
- 错误码安全前缀加了 `REISSUE`。

- 2026-11-01 部署：employee-admin a1baac3（含 semaphore/wsctl.sh 支持 reissue）；IaC PR #205 加 Semaphore 模板（待合并）。
- 2026-11-01 实测：`reissue --device control --plan-only` → recipient fanweiblue@gmail.com、outer_sha256 99bd3449…、主题"你的设备接入包已重新发送"、预览在 runs/reissue-control-001；审阅后以该 SHA 执行 → phase completed，新链接 /d/df603579…（200，至 2026-11-04），旧链接 /d/c33beb63… 返回 410。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 3 / low 1 / rejected 1
  - medium, patch — 未完成的运行目录不论是否匹配当前包都被沿用，可卡住重发至过期：只沿用同包且 uploaded/verified 的目录，损坏收据跳过。
  - medium, patch — 续跑 verified 运行可能发出已被作废的链接：发信前查站点状态，失效则标 link_stale 并报 REISSUE_LINK_STALE。
  - medium, patch — 审批只绑主题，正文随 mosh 设备变化：用占位链接渲染正文纳入审批并给预览，发信前复核。
  - low, patch（同上）— 损坏收据报通用错误：视为不可沿用。
  - rejected — AC 依赖实测。

## Verification

**Commands:**
- `cd remotecc/employee-admin && for t in test-temp-delivery.py test-oci-hub.py test-wsctl.py test-hub-requests.py; do python3 $t || exit 1; done` -- expected: OK（沙箱外运行）
