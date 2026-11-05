---
title: 'wsctl renew 与开户写入 paid_through'
type: 'feature'
ticket: '3'
created: '2026-11-01'
status: 'done'
baseline_revision: '89eef9c8afa8f434af8fee275982fb41278369c3'
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

**Problem:** 管理员没有命令记录续费；新开户员工没有 `paid_through`，到期机制管不到他们。

**Approach:** 新增 `wsctl renew <邮箱> <N>`：按 AD-8 计算新的 `paid_through`，原子写回 catalog 并推送快照（2.1 的 `hub-expiry.push`）；`provision` 完成时给新员工写入当月月底并推送快照。

**Decision:** 月份规则（2026-11-01，按 AD-8 与"开户为当月月底"一致解读）：未过期 → 原到期月 + N 个月的月底；已过期 → 本月（Sydney）+ (N−1) 个月的月底，即续费从本月算起、本月计为第 1 个月。例：`2026-11-30` 未过期续 1 → `2026-12-31`；12 月 5 日已过期续 1 → `2026-12-31`；`2026-12-31` 续 2 → `2027-02-28`。

## Boundaries & Constraints

**Always:** `paid_through` 为 Sydney 当月最后一天 `23:59:59`，带该日实际偏移的 ISO 8601（夏令时 `+11:00`、标准时 `+10:00`）；`N` 为 1–24 的整数；邮箱按小写匹配 catalog `recipient`，匹配不到或多于一个即拒绝；renew 无需确认，只在执行器运行；catalog 写入用现有原子保存（`hub-onboard.save`）；推送失败时 catalog 已写入的结果照常返回，并带上推送错误码，非零退出（下次 renew 或 `wsctl expiry` 可补推）。

**Never:** renew 不重新开户、不重发设备包、不改其他字段；provision 不覆盖已有的 `paid_through`；不处理 `no_expiry`（2.4）；不做开关机（2.2）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 未过期续费 | pt 2026-11-30，N=1 | 2026-12-31T23:59:59+11:00，推送 | — |
| 已过期续费 | now 2026-12-05，pt 2026-11-30，N=1 | 2026-12-31T23:59:59+11:00 | — |
| 跨年与平闰 | pt 2026-12-31，N=2 | 2027-02-28T23:59:59+11:00 | — |
| 夏令时边界 | pt 2027-03-31，N=3 | 2027-06-30T23:59:59+10:00 | — |
| 无 pt 的员工 | catalog 无 paid_through | 按已过期处理 | — |
| 未知邮箱 | 不在 catalog | 不写 | `RENEW_EMPLOYEE_UNKNOWN` |
| 非法 N | 0、25、"x" | 不写 | `RENEW_MONTHS_INVALID` |
| 新员工开户 | provision 新员工 | catalog 写当月月底并推送 | 推送失败仅报告 |
| 已有员工再开户 | 已有 pt | 保留原值 | — |

</frozen-after-approval>

## Code Map

路径相对私有仓库 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（有用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交）。标 hitl 的任务由主会话执行；不 commit、不 push。

- `hub-expiry.py` -- 2.1 模块；在此新增 `month_end(year, month)`、`renewed(paid_through, now, months)`（纯函数，用 `zoneinfo.ZoneInfo('Australia/Sydney')`）与 `renew(h, settings, recipient, months, now=None)`；复用 `push(h, settings)`。
- `hub-terminal.py:23` `catalog()`、`:36` `identity()` -- 读 catalog 的现有方式；renew 只按 `recipient` 查找，无 catalog 文件即 `EXPIRY_CATALOG_MISSING`。
- `hub-terminal.py:474` -- provision apply 里 `updated_catalog`/`employee`；`:529` `h.save(Path(c['catalog_file']),updated_catalog)` 前，若 `employee` 无 `paid_through` 则写当月月底；保存后调用 `hub-expiry.push`，失败时把错误码写进 apply 结果（如 `state['expiry_push']`），不回滚开户。
- `hub-onboard.py:46` `save()` -- 原子写 JSON。
- `oci-hub-admin.py` -- action choices 加 `renew`（位置参数：邮箱、N）；安全错误码前缀加 `RENEW`。
- `wsctl` -- 动作列表与执行器写入守卫加 `renew`。
- 测试：`test-hub-expiry.py`（已有夹具）、`test-wsctl.py`；provision 相关测试见 `test-hub-create.py`。

## Tasks & Acceptance

**Execution:**
- [x] `hub-expiry.py` -- 月份计算与 renew -- AD-8
- [x] `hub-terminal.py` -- provision 写入当月月底并推送 -- AD-6、AD-8
- [x] `oci-hub-admin.py`、`wsctl` -- 入口 -- 执行器专属
- [x] `test-hub-expiry.py`、`test-hub-create.py`、`test-wsctl.py` -- 覆盖矩阵全部行 -- 回归
- [x] 部署与实测（hitl）-- push；`control` 先 renew（无 pt → 本月底），确认 catalog 与 OCI generation；再与 2.2 实测合并验证"renew 后隧道与 VM 一起恢复"；收尾删字段并推送

**Acceptance Criteria:**
- Given 执行器上 `control` 无 pt，when `wsctl renew <control 邮箱> 1`，then catalog 为 `2026-11-30T23:59:59+11:00`，OCI `paid_through_generation` 加 1。
- Given `control` 已过期且 VM 被 enforce 关机，when renew，then 一个 timer 周期内隧道恢复、5 分钟内 VM 开机。

## Implementation Notes

- `hub-expiry.py`：`month_end`、`renewed`、`renew`，另加 `push_result`（把推送异常收成错误码，非代码文本统一为 `EXPIRY_PUSH_FAILED`）；`push` 增加可选 `admin` 参数，provision 传入已加载的 admin 模块。邮箱多于一个匹配用 `RENEW_EMPLOYEE_AMBIGUOUS`；catalog 中无法解析或无偏移的 `paid_through` 用 `RENEW_PAID_THROUGH_INVALID`；`renew` 缺参数用 `RENEW_USAGE`。
- 过期判定为 `now > paid_through`（与 R2 一致），等于时按未过期。
- `hub-terminal.py`：新增 `initial_paid_through`，只给无 `paid_through` 的员工写值，并把选定值钉在 `state['runtime']['paid_through']`，跨月续跑写同一日期；只有新写入时才推送，结果存 `state['runtime']['expiry_push']` 并出现在 apply 返回值里，失败不回滚。
- `oci-hub-admin.py renew`：先打印结果，推送失败再以推送错误码非零退出。

- 2026-11-01 实测第一轮失败：`control`、`pilot`、`pilot509` 共用管理员邮箱，`renew <邮箱>` 返回 `RENEW_EMPLOYEE_AMBIGUOUS`；测试脚本未止步，删除 control 的 pt 时 control 仍带 `expired`（延期清单所述情形），已推未来日期清除并由 enforce 开机恢复。修复 cf4e6bd：renew 也接受精确的 employee_id。

- 2026-11-01 实测第二轮（cf4e6bd，control 按 employee_id）：无 pt 续 1 → 2026-11-30T23:59:59+11:00，generation 10→11；设过去后关机，再续 1 → 11-30，10 秒内隧道恢复，291 秒后 enforce 开机；收尾 generation 14、0 名员工。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 2 / low 3 / false 0 / rejected 1
  - medium, patch — hub-expiry.py 不在 provision 审批的源码哈希列表里：加入 `source_hash()`。
  - medium, defer — renew 改写整份 catalog，会让计划与执行之间的其他员工开户以 `HUB_TERMINAL_CATALOG_CHANGED` 拒绝（fail-closed，需重新 plan）；只比对非 paid_through 字段需同时合并保存，否则丢失续费，留待后续。
  - low, patch — `bundled` 后续跑的早返回缺 paid_through/expiry_push：补上。
  - low, patch — paid_through 为 null 时三处处理不一致：一律视为缺失。
  - low, patch — provision 矩阵行只做源码顺序检查：有 `_apply` 测试夹具则补行为测试。
  - rejected — AC 未证明：依赖 hitl 部署实测。

## Verification

**Commands:**
- `cd remotecc/employee-admin && for t in test-hub-expiry.py test-hub-create.py test-hub-enforce.py test-oci-hub.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: 全部 OK（沙箱外运行）
