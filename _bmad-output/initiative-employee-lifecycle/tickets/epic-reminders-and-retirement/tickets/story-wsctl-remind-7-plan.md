---
title: 'wsctl remind 到期前 7 天提醒'
type: 'feature'
ticket: '2'
created: '2026-11-01'
status: 'done'
baseline_revision: 'cc414e689ba3569fc9b6ee87c51446fe9404ca7f'
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

**Problem:** 员工不知道自己快到期，月底直接被断开。

**Approach:** 新增 `wsctl remind`：对 `paid_through` 落在未来 7 天内（Sydney，未过期）、非不到期、非孤儿的员工各发一封中文提醒邮件（执行器 Microsoft Graph 通道，与交付邮件同一发件人），按"员工 + paid_through"去重，记录存在 employee-data。Semaphore 每小时运行一次（重复运行安全；4.3 的摘要在同一命令里按"每天 08:00 后一次"发出）。

**Decision:** 2026-11-01 用户同意：到期前 7 天提醒、Microsoft 邮件通道、摘要 08:00 Sydney。

## Boundaries & Constraints

**Always:** 候选与 `wsctl status` 的推导一致（复用 `hub-status` 的 lifecycle/paid_through 推导函数，不另写一套；状态 `active` 或 `disabled` 且 `paid_through - now <= 7 天` 且 `now <= paid_through`）；去重记录 `<catalog 目录>/reminders.json` = `{employee_id: [已提醒的 paid_through, ...]}`，发信成功后原子写入；续费后 paid_through 变化 → 下个周期可再提醒一次；邮件主题"你的远程工作区将于 <日期> 到期"，正文含到期日（Sydney 日期）、"续费请联系管理员"、不到期后的影响（隧道断开、VM 关机，数据保留 3 天后可能被回收）；收件人为 catalog recipient；发信失败的员工报码并继续处理其他人，非零退出；只在执行器运行；`--dry-run` 只列出将要提醒的员工，不发信不写记录；输出 `{profile, action:'remind', reminded:[ids], skipped:[{id,reason}], failures:[{id,code}]}`。

**Never:** 不做管理员摘要（4.3）；不修改 paid_through；不提醒不到期、已过期或孤儿员工。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 窗口内首次 | pt 在 7 天内，未提醒 | 发一封，记录 | — |
| 重复运行 | 同 pt 已提醒 | skipped（already_reminded） | — |
| 续费后 | pt 变为下月底 | 不在窗口 → 不发；到新窗口再发一次 | — |
| 窗口外 | pt 在 8 天后 | 不发 | — |
| 已过期 | now > pt | 不发 | — |
| 不到期 | no_expiry | 不发 | — |
| 发信失败 | Graph 非 202 | 不写记录；failures 列出；其他人照常 | `REMIND_SEND_FAILED` |
| dry-run | `--dry-run` | 列出将提醒者，不发不写 | — |

</frozen-after-approval>

## Code Map

私有代码 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交）。IaC 的 Semaphore 模板由主会话做。不 commit、不 push、不发信。

- `hub-status.py` -- 4.1 的 lifecycle/paid_through 推导；如需复用，把推导抽成可单独调用的函数（不改 view 的输出）。
- `deliver-temp.py:310` `notify()` -- Graph `/me/sendMail` 调用方式与 `microsoft-mail-auth.token()`；提醒复用同样的发送方式（可抽一个小的 `send_mail(token, to, subject, html)` 帮助函数），不改交付行为。
- `templates/` -- 新增 `expiry-reminder.html`。
- `hub-onboard.save` -- 原子写。
- 新 `hub-remind.py`；`oci-hub-admin.py` action `remind`（`--dry-run`）；`wsctl` 动作列表与执行器写入守卫加 `remind`；安全错误码前缀加 `REMIND`。
- 测试：新 `test-hub-remind.py`（打桩推导数据、发信与时间），`test-wsctl.py`。

## Tasks & Acceptance

**Execution:**
- [x] `hub-remind.py`、`templates/expiry-reminder.html`、`oci-hub-admin.py`、`wsctl`、测试 -- 提醒与去重
- [x] IaC（主会话）-- Semaphore 模板 `wsctl remind`，定时 `0 * * * *`
- [x] 实测（hitl）-- 临时把 control 设为 7 天内到期（先去掉 no_expiry），dry-run 列出 control；真实运行一次 → fanweiblue@gmail.com 收到一封；再运行 → already_reminded；恢复 control 为 no_expiry

**Acceptance Criteria:**
- Given control 在窗口内，when 连续运行两次 `wsctl remind`，then 只收到一封提醒。

## Implementation Notes

- `hub-status.py` 新增 `reminder_due(stamp, now)`，`view` 的 `remind_pending` 计数改用它（输出不变）；`hub-remind` 复用 `paid_through` / `lifecycle` / `reminder_due`。lifecycle 以空 reasons 推导：reasons 只区分 active 与 disabled，两者都提醒，因此无需远程 query。
- `deliver-temp.py` 抽出 `mail_body(recipient, subject, html)` 与 `send_mail(token, body)`，`notify` 改为调用它们，行为不变（test-temp-delivery 通过）。
- skipped 原因：`orphan`、`paid_through_invalid`、`no_expiry`、`expired`、`retirable`、`not_due`、`already_reminded`。dry-run 输出带 `dry_run: true`，`reminded` 为将要提醒者。
- token 只在真正发信时获取；token 或发信异常一律记 `REMIND_SEND_FAILED`，失败非零退出 `REMIND_PARTIAL_FAILURE`。
- 风险：Graph 超时/传输异常（结果未知）也不写记录，下次运行可能重复发一封。

- 2026-11-01 主会话补充：邮件授权失效（AuthError 等）按员工报 REMIND_MAIL_AUTH_FAILED。提交 73f6481 部署；IaC PR #208（Semaphore `wsctl remind` 每小时，评审无发现）合并，bootstrap 已执行。
- 2026-11-01 实测：control 临时设 paid_through 2026-11-06（去掉 no_expiry）→ dry-run 仅 control；真实运行两次 → 第一次 reminded [control]，第二次 already_reminded；恢复 no_expiry 并推快照 generation 18；reminders.json 记录 control 的 2026-11-06。

- 2026-11-01 用户确认：提醒邮件与管理员摘要均已收到，且在 Gmail 收件箱（非垃圾箱）。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 1 / medium 1 / low 3 / rejected 2
  - high, patch — hub-remind 自带的加载器不重置 sys.argv，真实入口导入 deliver-temp 时触发 profile 分派、argparse 退出，命令永远跑不起来：照 oci-hub-admin.load_module 处理，并补入口级测试。
  - medium, patch — 发信成功后写记录失败会中断整轮且下小时重发：按员工报 REMIND_RECORD_WRITE_FAILED 并继续。
  - low, patch — 模板渲染在 try 外、宽 except 掩盖编程错误：按员工处理固定码，其余异常上抛。
  - low, patch — 去重比较原始字符串：改按时刻比较。
  - low, patch — 无 paid_through 报 not_due：改 no_paid_through。
  - rejected — REMINDABLE 中 disabled 不可达：无害，计划已接受。
  - rejected — AC 依赖实测：hitl。

## Verification

**Commands:**
- `cd remotecc/employee-admin && for t in test-hub-remind.py test-hub-status.py test-temp-delivery.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: OK（沙箱外运行）
