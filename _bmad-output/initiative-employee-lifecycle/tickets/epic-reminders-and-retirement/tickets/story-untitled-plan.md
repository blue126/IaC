---
title: '管理员每日摘要'
type: 'feature'
ticket: '3'
created: '2026-11-01'
status: 'done'
baseline_revision: '73f64814b0600ede9cc57f74101f8f3c326f9655'
route: 'full'
route_source: 'auto'
risk: 'low'
review: ''
review_source: ''
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 管理员要主动去跑 `wsctl status` 和 `wsctl request` 才知道有没有新申请、谁可退役、有没有多余 VM。

**Approach:** `wsctl remind` 在发完员工提醒后，每天 Sydney 08:00 之后的第一次运行给管理员发一封摘要邮件（执行器 Microsoft 邮件通道）：新申请（网站待处理、已验证与未验证分开）、可退役员工、孤儿资源、3 天内到期员工、今天发出的提醒；当天已发过就不再发。

**Decision:** 2026-11-01 用户同意：08:00 Sydney，发 fanweiblue@gmail.com；收件人放 settings `admin_summary_recipient`。

## Boundaries & Constraints

**Always:** 数据来自现有推导（`hub-status.view` 的 lifecycle/orphans 与 `hub-requests.fetch` 的待处理列表），不另写一套；任一数据源失败时摘要照发，对应栏写"无法获取：<错误码>"；去重记录 `<catalog 目录>/summary.json` = `{"last_sent": "YYYY-MM-DD"}`（Sydney 日期），发信成功后原子写；`--dry-run` 时在输出里给出摘要预览（`summary: {...}`）但不发不写；`--summary-now` 强制当次发送（用于实测，仍写记录）；摘要主题"远程工作区每日摘要 YYYY-MM-DD"；没有任何事项时仍发（内容写"今日无事项"）；输出增加 `summary: {sent: bool, reason}`；摘要失败不影响员工提醒的结果，但非零退出并报 `REMIND_SUMMARY_FAILED`。

**Never:** 不在摘要里放私钥、令牌或下载链接；不改提醒逻辑；不做退役（4.4）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 08:00 前 | Sydney 07:30 | 不发（before_window） | — |
| 当天首次 | 08:00 后，今天未发 | 发一封，记录日期 | — |
| 当天再次 | 今天已发 | 不发（already_sent） | — |
| 强制 | `--summary-now` | 发 | — |
| 网站不可达 | fetch 失败 | 照发，申请栏写错误码 | — |
| status 失败 | view 抛错 | 照发，相关栏写错误码 | — |
| 发信失败 | Graph 失败 | 不写记录，下小时重试 | `REMIND_SUMMARY_FAILED` |

</frozen-after-approval>

## Code Map

私有代码 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交）。不 commit、不 push、不发信。

- `hub-remind.py` -- 4.2 的 run()、load()、mail 发送方式（`deliver-temp.mail_body/send_mail`）；摘要接在提醒之后。
- `hub-status.py` `view(base, settings, sessions=True)` -- lifecycle、paid_through、orphans。
- `hub-requests.py` `fetch()`/`pull` 的待处理列表（含 email_verified）。
- `templates/` -- 新增 `admin-summary.html`。
- `oci-hub-admin.py` remind 分支 -- 加 `--summary-now`。
- 测试：`test-hub-remind.py` 扩展。

## Tasks & Acceptance

**Execution:**
- [x] `hub-remind.py`、`templates/admin-summary.html`、`oci-hub-admin.py`、测试 -- 每日摘要
- [x] 实测（hitl）-- 执行器 settings 加 `admin_summary_recipient`；`wsctl remind --summary-now` → 管理员邮箱收到摘要，内容与 `wsctl status` 一致；同日再运行 → already_sent

**Acceptance Criteria:**
- Given 执行器当前数据，when `wsctl remind --summary-now`，then fanweiblue@gmail.com 收到摘要，列出 0 条新申请、0 个可退役、0 个孤儿。

## Implementation Notes

- `hub-remind.run()` 在提醒循环之后调用 `summary()`；提醒循环本身未改。`view`/`applications` 可注入（测试用），默认分别为 `hub-status.view(BASE, settings, sessions=True)` 与 `hub-requests.site_settings` + `fetch` + `record`。
- 各栏结构 `{'items': [...]}`，失败时带 `'error': <code>`；孤儿栏在 `orphans_error` 非空时同时给出已知条目与错误码。3 天内到期 = lifecycle 为 active/disabled 且 `now <= paid_through <= now+3d`。
- 输出 `summary: {sent, reason}`；正常结果 reason 为小写（`before_window`/`already_sent`/`first_today`/`forced`/`dry_run`），失败 reason 为大写错误码，`hub-remind.failed()` 据此判定，`oci-hub-admin` 先打印结果再报 `REMIND_SUMMARY_FAILED`（若同时有提醒失败，仍先报 `REMIND_PARTIAL_FAILURE`）。dry-run 额外带 `preview`。
- `hub-status.view()` 新增 `save=True` 参数（现有调用不变）；remind 摘要始终传 `save=False`，dry-run 不再写 registry_view。
- 待发列表读写失败会以 `reminded_record_error` 出现在 `summary` 中（含 before_window/already_sent），`failed()` 据此判非零退出。`summary.json` 读失败（含 OSError）映射为 `REMIND_SUMMARY_RECORD_INVALID`；非鉴权类 get_token 异常为 `REMIND_SUMMARY_TOKEN_FAILED`。
- 默认申请来源 `pending_applications()` 与 `pull` 一致：本地文件已有 `processed_at` 的申请不算新申请。
- 3 天内到期栏逐行解析 paid_through，坏行只跳过该行。
- 收件人读顶层 settings `admin_summary_recipient`；缺失或格式不对 → `REMIND_SUMMARY_RECIPIENT_MISSING`（仅在需要发送时检查，08:00 前不报）。
- 发信成功、记录写失败 → `{sent: true, reason: REMIND_SUMMARY_RECORD_WRITE_FAILED}`，下一次运行会重发。

- 2026-11-01 部署：employee-admin 7b22360 推到执行器；执行器上 test-hub-remind / test-hub-status / test-hub-requests / test-hub-wsctl 全部 OK（沙箱外）。settings 加 `admin_summary_recipient: fanweiblue@gmail.com`（备份 settings.json.pre-admin-summary）。
- 2026-11-01 实测：`--dry-run` 预览各节为空（与 `wsctl status` 一致：无新申请、无可退役、无孤儿、3 天内无到期）且未写文件；`--summary-now` 发送两次（forced，均 sent）；随后普通运行 → `already_sent`，summary.json `last_sent=2026-11-01`。

- 2026-11-01 用户确认：提醒邮件与管理员摘要均已收到，且在 Gmail 收件箱（非垃圾箱）。

- 2026-11-02 补测（epic 4 完成标准）：用执行器 settings 与 catalog 的临时副本（副本中删去 pilot509）跑 `wsctl remind --dry-run --summary-now`，摘要 orphans 节列出 `vm_without_catalog pilot509 vmid 509`；不发信、不改真实数据，副本已删除。新申请一节：2026-11-02 向 D1 插入已验证测试申请 e4d0ae4c0001，摘要 requests_verified 列出该申请，`--summary-now` 真实发信；随后 `wsctl request --dismiss e4d0ae4c0001`，复查新申请为 0。

## Plan Change Log

- 2026-11-01（Review Pass 1 后由协调者定）：新增 `<catalog 目录>/reminded-pending.json` = `{"ids": [...]}`，取代初稿的按日重置的 `reminded-today.json`。非 dry-run 的每次提醒把 id 追加进去；只有摘要发送成功后才改写为未被这封摘要列出的 id。因此 08:00 前发出的提醒进当天摘要，08:00 后发出的进次日摘要；摘要栏名改为"上次摘要以来发出的提醒"。文件损坏时不覆盖，栏内与 `reminded_record_error` 报错码。`summary.json` 形状不变。
- 2026-11-01：`wsctl` usage 行补 `--summary-now`（参数本身由 `wsctl` 原样透传，无需改逻辑）。

## Review Triage Log

Pass 1 (quick): high 0 / medium 1 / low 5 / rejected 1
- medium（已修）：dry-run 经 `hub-status.view` 写 registry_view → view 加 `save` 参数，remind 传 `save=False`。
- low（已修）：`reminded-today.json` 写失败在 before_window/already_sent 时被吞 → 输出 `reminded_record_error`，`failed()` 判非零。
- low（已修）：`summary.json` 读只捕获 ValueError、非鉴权 get_token 异常逃出 run() → 统一成大写错误码，提醒结果总能打印。
- low（已修）：默认申请列表未按本地 `processed_at` 过滤 → `pending_applications()` 与 pull 一致过滤。
- low（已修，协调者定设计）：按日重置改为待发队列 `reminded-pending.json`，摘要发送成功后才清。
- rejected：`summary.json` 损坏时每次运行都报错——有意为之。
- low（已修）：3 天内到期栏单行 paid_through 解析失败会让整栏失败 → 逐行跳过。

## Verification

- 2026-11-01：沙箱内 `test-hub-remind.py`（22 项，含 10 项新摘要用例）与 `test-hub-status.py` 通过。`test-hub-requests.py`（30 errors）和 `test-wsctl.py`（2 failures）在沙箱内全部是 `Operation not permitted`（本地 HTTP 服务 / ssh-agent socket 绑定被禁），与本改动无关；按计划需在沙箱外重跑确认。
- 2026-11-01 Pass 1 修复后：沙箱内 `test-hub-remind.py` 28 项、`test-hub-status.py` 10 项通过（新增：view save=False、默认 view 不保存、待发写失败上报、summary.json 不可读/非鉴权 token 错误、本地已处理申请过滤、待发队列跨日、坏 paid_through 单行跳过）。
- 实测（hitl）未做：需在执行器 settings 加 `admin_summary_recipient`，再跑 `wsctl remind --summary-now`。

**Commands:**
- `cd remotecc/employee-admin && for t in test-hub-remind.py test-hub-status.py test-hub-requests.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: OK（沙箱外运行）
