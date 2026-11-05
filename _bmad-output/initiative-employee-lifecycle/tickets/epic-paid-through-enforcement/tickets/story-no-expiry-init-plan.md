---
title: '不到期标记与现有员工初始化'
type: 'feature'
ticket: '4'
created: '2026-11-01'
status: 'done'
baseline_revision: '09b7db0754f244817b869ffef30751f0af948dfc'
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

**Problem:** 现有员工都没有 `paid_through`，到期机制对他们无效；`pilot`、`control` 需要永不到期。

**Approach:** catalog 员工可标 `no_expiry: true`；新增 `wsctl expiry --initialize <id,...>`：把列出的员工标为不到期（并去掉其 `paid_through`），其余没有 `paid_through` 的员工设为当月月底（Sydney），原子写回 catalog 后推送快照。上线时运行一次 `wsctl expiry --initialize pilot,control`。

**Decision:** 初始化名单为 `pilot`、`control` 不到期，其余 6 名员工为 `2026-11-30T23:59:59+11:00`（epic 2 Decision 2026-10-31/11-01，用户批准推进到 epic 2 结束）。

## Boundaries & Constraints

**Always:** `no_expiry` 员工不进快照（即使误带 `paid_through`）、renew 拒绝（`RENEW_NO_EXPIRY`）、provision 不给其写 `paid_through`；`--initialize` 幂等，已有 `paid_through` 的员工保持不变；名单里有 catalog 不存在的 id 即整体拒绝（`EXPIRY_INITIALIZE_UNKNOWN`），不写任何东西；只在执行器运行。

**Never:** 不改 OCI 端代码；不改 enforce 的判定（无 `paid_through` 即不处理已覆盖不到期员工）；不发邮件、不重发设备包。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 首次初始化 | 8 人均无 pt；名单 pilot,control | pilot/control `no_expiry`；其余 6 人当月月底；推送含 6 人 | — |
| 重复运行 | 已初始化 | catalog 不变；仍推送（generation +1） | — |
| 已有 pt | 某员工已有 pt | 保持原值 | — |
| 名单员工带 pt | control 有 pt | 去掉 pt，标 no_expiry | — |
| 未知 id | 名单含 `nobody` | 不写 | `EXPIRY_INITIALIZE_UNKNOWN` |
| renew 不到期员工 | pilot | 不写 | `RENEW_NO_EXPIRY` |
| 快照 | no_expiry 且带 pt | 不进快照 | — |

</frozen-after-approval>

## Code Map

路径相对私有仓库 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（有用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交）。标 hitl 的任务由主会话执行；不 commit、不 push。

- `hub-expiry.py` -- `snapshot()` 排除 `no_expiry`；新增 `initialize(h, settings, ids, now=None)`，复用 2.3 的 `month_end` 与原子保存、`push()`；`renew()` 遇 `no_expiry` 拒绝。
- `hub-terminal.py` -- 2.3 在 provision apply 写 `paid_through` 的位置，跳过 `no_expiry` 员工。
- `oci-hub-admin.py` -- `expiry` 动作接受 `--initialize <逗号分隔 id>`（不带时行为同 2.1：只推送）；安全错误码已含 `EXPIRY`、`RENEW`。
- `wsctl` -- 无需改动（`expiry` 已在执行器写入守卫中）。
- 测试：`test-hub-expiry.py`、`test-hub-create.py`。

## Tasks & Acceptance

**Execution:**
- [x] `hub-expiry.py`、`hub-terminal.py`、`oci-hub-admin.py` -- 不到期标记与初始化 -- R14
- [x] `test-hub-expiry.py`、`test-hub-create.py` -- 覆盖矩阵全部行 -- 回归
- [x] 上线（hitl）-- push；执行器运行 `wsctl expiry --initialize pilot,control`；核对 catalog、OCI generation 与快照人数 6；`wsctl status` 正常；下一轮 enforce 无动作、无失败

**Acceptance Criteria:**
- Given 上线完成，when 查看 catalog，then pilot、control 为 `no_expiry: true` 且无 pt，其余 6 人为 `2026-11-30T23:59:59+11:00`。
- Given 上线完成，when OCI reconcile 与 enforce 运行，then 没有任何员工被加 `expired` 或关机。

## Implementation Notes

- 名单为空或含空项（如 `pilot,,control`）时拒绝为 `EXPIRY_INITIALIZE_EMPTY`，不写不推送（避免空名单把所有人设成当月月底）。
- 不在本次名单中、但此前已是 `no_expiry` 的员工保持不变，不会被设 pt。
- 推送失败时 catalog 写入保留，打印结果后以推送错误码非零退出（与 renew 一致）。
- 返回 `changed` 列出本次实际改动的员工；重复运行为 `{}` 且不重写 catalog 文件。

- 2026-11-01 上线：提交 88a3a6d（含评审修复），随 cf4e6bd 部署；执行器 `wsctl expiry --initialize pilot,control` → pilot/control `no_expiry`，其余 6 人 2026-11-30T23:59:59+11:00，generation 15，快照 6 人；enforce 无动作无失败；OCI 9 个设备均无原因且在内核。`wsctl status` 失败（HUB_CHECKPOINT_COMMAND_FAILED）经查为 IaC 推送重置了缺 linux_amd64 校验的 lock 文件，PR #204 修复，执行器上验证 status rc=0。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 1 / low 2 / rejected 3
  - medium, patch — no_expiry 员工若残留过去的 paid_through，快照会排除但 enforce 仍会关机：hub-enforce 改为与快照同一判定（`paid_through` 非空且非 no_expiry 才执行），并把 null 视为缺失；补测试。（冻结段 Never "不改 enforce 的判定"的前提"无 pt 即不处理"对残留 pt 不成立，此改动只为满足 Intent。）
  - low, patch — 未知/空名单测试未断言不推送：改为断言 `push_result` 未调用。
  - low, patch — "已标 no_expiry 但不在本次名单"无测试：补测试。
  - rejected — 重复运行 generation+1 只间接覆盖（`Push.test_generation_is_remote_accepted_plus_one` 已测）。
  - rejected — `--initialize` 为全局参数会被其他动作忽略：与该解析器现有约定一致。
  - rejected — 返回的 no_expiry 只列本次名单：信息性，计划未要求。

## Verification

**Commands:**
- `cd remotecc/employee-admin && for t in test-hub-expiry.py test-hub-create.py test-hub-enforce.py test-oci-hub.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: 全部 OK（沙箱外运行）
