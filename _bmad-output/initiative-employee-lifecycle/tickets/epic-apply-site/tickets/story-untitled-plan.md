---
title: '从申请开户并回写已处理'
type: 'feature'
ticket: '3'
created: '2026-11-01'
status: 'done'
baseline_revision: '7c82435523d987df00ce66cf8d672d36daad97df'
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

**Problem:** 开户仍要手输邮箱；处理过的申请会一直出现在 `wsctl request` 里。

**Approach:** `wsctl provision --request <申请ID>` 从 `requests/oci-hub/site-<ID>.json` 取邮箱（只接受已验证邮箱的申请），并在该文件里记下生成的开户请求文件；开户 apply 成功后自动把该申请回写为已处理（`provisioned`）。`wsctl request --dismiss <ID>` 回写为 `dismissed`。Worker 新增只接受管理令牌的 `POST /admin/applications/<id>/processed`，列表接口返回 `email_verified`。页面提示"没收到请查看垃圾邮件"。

**Decision:** 2026-11-01 用户要求推进到 epic 3 结束；邮箱未验证的旧申请只能 dismiss，不能开户。

## Boundaries & Constraints

**Always:** `--request` 与 `--email` 互斥；申请文件不存在、`email_verified` 不为真、或已处理 → 拒绝（`REQUEST_NOT_FOUND`、`REQUEST_EMAIL_UNVERIFIED`、`REQUEST_ALREADY_PROCESSED`）；开户 plan 用申请里的邮箱作为 `recipient`，其余参数（`--username`、规格等）照常可用；回写只在 apply 返回成功后进行，回写失败不回滚开户，结果里带 `application_writeback` 错误码并非零退出，可用 `wsctl request --dismiss`/重跑回写补做；回写成功后本地申请文件加 `processed_at`、`outcome`；Worker 回写幂等（已处理再回写同 outcome 返回 200，不同 outcome 返回 409 `ADMIN_ALREADY_PROCESSED`）；未知 id 404 `ADMIN_APPLICATION_NOT_FOUND`；令牌规则与列表接口一致；`wsctl request` 不再落地已有本地 `processed_at` 的申请；`request` 结果里标出每条的 `email_verified`。

**Never:** 不改开户本身的计划、审批与执行逻辑；不做设备包（3.4）；网站不调用执行器。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 从申请开户 | `provision --request <ID>`，已验证 | 计划的 recipient 为申请邮箱；申请文件记下 request_file | — |
| 未验证 | email_verified=0 | 不出计划 | `REQUEST_EMAIL_UNVERIFIED` |
| 不存在 | 无此文件 | 不出计划 | `REQUEST_NOT_FOUND` |
| apply 成功 | 该 request_file apply 成功 | 回写 provisioned；本地加 processed_at | 回写失败 → 报码、非零退出 |
| 普通 apply | 不来自申请的开户 | 不回写 | — |
| dismiss | `request --dismiss <ID>` | 回写 dismissed；本地标记 | 网站不可达 → REQUEST_SITE_* |
| 重复回写 | 已 provisioned 再 provisioned | 200 | — |
| 冲突回写 | 已 dismissed 再 provisioned | 409 | `ADMIN_ALREADY_PROCESSED` |
| 列表 | GET /admin/applications | 只返回 new，含 email_verified | — |

</frozen-after-approval>

## Code Map

私有代码：`/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（有用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交）与 `/Users/weierfu/Projects/IaC/remotecc/apply-site/`（自己的 git）。不 commit、不 push、不调用 Cloudflare；部署由主会话完成。

- `employee-admin/oci-hub-admin.py:309` `provision` 分支 -- 加 `--request`（与 `a.request` 位置参数冲突，用新选项名 `--application`；wsctl 层把 `--request <ID>` 映射过去，或直接用 `--application`，二选一并在 usage 写明）；读取 `settings['apply_site']['requests_dir']/site-<ID>.json`。`:377` `plan/apply` 分支 -- apply 成功后调用 `hub-requests.writeback`（按 request_file 匹配申请文件）。
- `employee-admin/hub-requests.py` -- 复用 `fetch()` 的 https、不跟随重定向、UA、错误码约定；新增 `post_processed(settings, id, outcome)`、`writeback_for_request_file(settings, request_file)`、`dismiss(settings, id)`；`pull()` 跳过本地已 processed 的申请并在结果里带 `email_verified`。
- `employee-admin/wsctl`、`wsctl-confirm.py` -- `request --dismiss` 透传；provision 的确认流程不变（plan 输出里的 `request_file` 照旧）。
- `apply-site/worker.js` -- 新路由 `POST /admin/applications/<id>/processed`，body `{outcome:'provisioned'|'dismissed'}`；列表 SELECT 加 `email_verified`；页面在验证码发送成功提示后加"没收到请查看垃圾邮件"。`schema.sql` 加 `outcome TEXT`；新 `migrations/0004-outcome.sql`。
- 测试：`employee-admin/test-hub-requests.py`（本地 TLS 假站点已有）、`test-wsctl.py`、新增 provision --application 的单元测试（打桩 `hub-onboard.invoke`）；`apply-site/test-worker.mjs`。

## Tasks & Acceptance

**Execution:**
- [x] `apply-site/worker.js`、`schema.sql`、`migrations/0004-outcome.sql`、`test-worker.mjs` -- 回写接口、列表字段、页面提示
- [x] `employee-admin/hub-requests.py`、`oci-hub-admin.py`、`wsctl`、测试 -- 从申请开户、apply 后回写、dismiss
- [x] 部署（hitl，主会话）-- 迁移、上传 Worker、push employee-admin
- [x] 实测（hitl）-- dismiss 全部测试申请；对已验证申请 55b6abea1076 跑 `provision --application 55b6abea1076 --plan-only` 确认 recipient；不执行 apply（不真的开户），然后 dismiss 它

**Acceptance Criteria:**
- Given 已验证申请，when `wsctl provision --application <ID> --plan-only`，then 计划的 recipient 是申请邮箱。
- Given 测试申请，when `wsctl request --dismiss <ID>`，then 它不再出现在 `wsctl request` 结果中，D1 中 status='processed'、outcome='dismissed'。

## Implementation Notes

- 选项名用 `--application <ID>`（wsctl 直接透传，usage 已写明），不做 `--request` 映射；`--application` 与 `--email` 同时给出 → `REQUEST_EMAIL_EXCLUSIVE`。
- 本地申请文件新增 `email_verified`（站点缺该字段视为未验证）；pull 保留本地字段 `request_file`/`processed_at`/`outcome`，已有 `processed_at` 的申请跳过不落地；结果新增 `email_verified: {id: bool}`。
- 回写的 `processed_at` 取 Worker 返回值；站点 404/409 映射为 `REQUEST_SITE_APPLICATION_NOT_FOUND`/`REQUEST_SITE_ALREADY_PROCESSED`。
- "apply 成功" = `hub-onboard.invoke(..., 'apply')` 正常返回；同一 request_file 关联的所有未处理申请都回写 provisioned。
- `wsctl-confirm.py` 在执行步骤失败时也输出 stdout，使 `application_writeback` 错误结果可见（确认流程不变）。
- Worker 处理接口 id 限 `[A-Za-z0-9]{1,64}`，坏 body/outcome → 400 `ADMIN_BODY_INVALID`；409 body 附带已有 `outcome`。

- 2026-11-01 部署：apply-site 02fa41d（线上源码取回后打补丁上传，哈希 0f78caa9…0e45；D1 加 outcome）；employee-admin b89041e 推到执行器。
- 2026-11-01 实测：request 拉取带 email_verified（仅 55b6abea1076 为真）；未验证申请 provision 被拒 REQUEST_EMAIL_UNVERIFIED；dismiss 5 条测试申请后只剩 338ead3560cc（用户自测，待确认）。provision --application 的计划在 BWS 预检失败 HUB_MACHINE_ACCOUNT_MUST_ONLY_ACCESS_HUB_PROJECT：执行器机器账号可见 default、EmployeeWorkspace-OCIHub、HapiWorkspace 三个项目（epic 1 遗留，执行器从未实跑开户）。AC1 待用户拆分 BWS 机器账号后复测；测试申请 c3c3c3c3c3c3 待清理。

- 2026-11-01 BWS 范围按用户选择 B 放宽（ca45a19）：机器账号须可见 Hub 项目、不可见旧项目，允许同时可见执行器 default 项目。复测：补一条已验证测试申请 c4c4c4c4c4c4（hello+cc33@willfan.me）→ `provision --application c4c4c4c4c4c4 --username cctest33 --plan-only` 出计划（VMID 510，recipient 为申请邮箱，带 application_id），未 apply；c3c3/c4c4 已 dismiss。共用管理员邮箱的申请会因多员工同邮箱被拒（与 renew 同源，开户时用 --username 指定）。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 1 / low 3 / rejected 1
  - medium, patch — provision --application 只查本地 processed_at，站点已处理的申请仍会开户、事后回写才失败：plan 前查站点待处理列表。
  - low, patch — POST 的任何 404 都报"申请不存在"，未部署路由时误导：读响应错误码区分。
  - low, patch — dismiss 站点写成功后本地写失败时异常外泄或改名：统一 REQUEST_LOCAL_WRITE_FAILED 并带站点结果。
  - low, patch — 测试中 email_verified 取值用例有死分支：逐项断言。
  - rejected — 迁移前已处理且 outcome 为空的行无法回写：D1 中所有现有申请均为 status='new'，不存在此类行。

## Verification

**Commands:**
- `cd remotecc/apply-site && node --test test-worker.mjs` -- expected: 全部通过
- `cd remotecc/employee-admin && for t in test-hub-requests.py test-wsctl.py test-oci-hub.py; do python3 $t || exit 1; done` -- expected: OK（沙箱外运行）
