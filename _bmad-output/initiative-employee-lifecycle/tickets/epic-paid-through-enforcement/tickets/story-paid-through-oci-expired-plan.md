---
title: 'paid_through 快照推到 OCI 并驱动 expired 原因'
type: 'feature'
ticket: '1'
created: '2026-11-01'
status: 'done'
baseline_revision: '040fa7d02f0a9ba1cf8cc07c922eba6f4fd8cca7'
route: 'full'
route_source: 'auto'
risk: 'high'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** OCI 不知道员工付到哪天，月底后无法自动断开隧道。

**Approach:** catalog 员工记录可带 `paid_through`；`wsctl expiry` 把整份 `employee_id → paid_through` 快照（generation = OCI 已接受值 + 1）经现有 SSH 通道交给 OCI 执行器；OCI 执行器在同一把锁内校验并存入账本，5 秒一轮的 reconcile 按快照给该员工的全部设备 peer 增删 `expired`。

## Boundaries & Constraints

**Always:** 只增删 `expired`（与既有 `quota_exhausted:*`），其他原因原样保留；快照不含邮箱；generation 不大于已接受值即拒绝；快照外的员工完全不处理（含其设备上已有的 `expired`）；`expiry` 只在执行器运行（Mac 返回 `WSCTL_WRITES_ON_EXECUTOR`）。

**Decision:** 实测员工为 `control`（2026-11-01 用户确认）。

**Never:** 不做 renew、不做开关机、不做不到期标记与初始化（2.2–2.4）；不改 IaC 仓库与 oci-hub 角色；不碰 VM Spoke（workspace）peer。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 到期 | 快照中 alice 为过去时间 | alice 所有设备 peer 加 `expired`，内核中消失 | — |
| 恢复 | 新快照 alice 为未来时间 | 只移除 `expired`，`admin_disabled`/配额原因保留 | — |
| 旧快照 | generation ≤ 已接受值 | 拒绝，账本不变 | `EXPIRY_GENERATION_STALE` |
| 非法快照 | 坏 id、无时区时间、多余字段 | 拒绝，账本不变 | `EXPIRY_SNAPSHOT_INVALID` |
| 快照外员工 | bob 不在快照，设备上有人工 `expired` | 不动 | — |
| 无快照 | 账本没有快照 | reconcile 行为与现在一致 | — |

</frozen-after-approval>

## Code Map

路径相对私有仓库 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（另有自己的 git，有用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交它们）。标 hitl 的部署与实测任务由主会话执行，实现时跳过；不 commit、不 push。

- `services/oci-hub/executor.py` -- `main()` 加命令 `expiry`（stdin JSON `{profile, generation, paid_through}`，在 `lock()` 内、不跑 `sample_live`）；`reconcile()` 设备分支里 `owned`/`desired` 扩展到 `expired`；`report()` 增 `paid_through_generation`。快照存 `meta` 表键 `paid_through`（与 generation 同事务写入，满足"原子替换"）。
- `services/oci-hub/portal.py` -- 复用 `peer_reasons`，不改。
- `oci-hub-admin.py` -- `remote(settings,command,request)` 已是 SSH+sudo 调 OCI 执行器的唯一通道，复用；action choices 加 `expiry`。
- 新 `hub-expiry.py` -- `snapshot(catalog)`、`push(h,settings)`：读 catalog（`hub-terminal.catalog`），`remote(...,'query')` 取 `paid_through_generation`，+1 后 `remote(...,'expiry',request)`。
- `wsctl` -- 动作列表与执行器写入守卫加 `expiry`。
- `pack-oci-hub.py` -- 打包 OCI 源码工件，不改。
- `../../ansible/playbooks/update-oci-hub-authority.yml` -- 现成的"暂停 timer→备份→替换三个源文件→执行一次 adopt_portal_state→恢复 timer"部署路径；用新的 `action_id` 与当前 generation 复用即可（`migrate_authority` 已执行过会直接返回），不改。
- 测试：`test-oci-hub.py`（`Accounting` 夹具已有 alice/bob 设备与 Fake Portal），`test-wsctl.py`。

## Tasks & Acceptance

**Execution:**
- [x] `services/oci-hub/executor.py` -- 实现 `expiry` 命令、reconcile 中的 `expired`、query 回报 generation -- OCI 端判定
- [x] `test-oci-hub.py` -- 覆盖 I/O 矩阵全部行 -- 回归
- [x] `hub-expiry.py`、`oci-hub-admin.py`、`wsctl` -- 推送快照与 wsctl 入口 -- 执行器端
- [x] 新 `test-hub-expiry.py`、`test-wsctl.py` -- 快照只含有 `paid_through` 的员工、无邮箱；generation 取远端+1；Mac 拒绝 `expiry` -- 回归
- [x] 部署（hitl）-- push 到执行器；打包工件，经 `update-oci-hub-authority.yml` 部署到 OCI（管理员确认）
- [x] 实测（hitl）-- 测试员工 `paid_through` 设为过去 → `wsctl expiry` → 一个 timer 周期内其设备 peer 有 `expired` 且不在 `wg show`；改为未来 → 恢复；重放旧 generation 被拒；测试后从 catalog 删除该字段并再推一次

**Acceptance Criteria:**
- Given 部署完成且测试员工已过期，when 等 10 秒，then `wsctl status` 显示其设备原因含 `expired`，`wg show wg-users` 无其 peer。
- Given 改回未来并推送，when 等 10 秒，then `expired` 消失，其他原因不变，隧道可重连。
- Given 其他员工不在快照，when 整个过程，then 他们的 Portal 原因与 peer 完全不变。

## Implementation Notes

- 执行器 `expiry` 只存账本（`meta.paid_through` + `meta.paid_through_generation` 同一事务），不跑 sample/reconcile；由 timer 的 sample→reconcile 生效。
- `EXPIRY_*` 拒绝码经执行器 stderr JSON 回传，`remote()` 对 `expiry` 命令透传该码（否则仍为 `OCI_HUB_ACTION_PENDING`）；管理端安全码前缀加 `EXPIRY`。
- 判定：`now > paid_through` 即加 `expired`。时间解析用 `datetime.fromisoformat`，OCI 上 Python < 3.11 时 `Z` 后缀会被判非法，catalog 里应写 `+08:00` 形式。

- 2026-11-01 部署：employee-admin a564a9e 推到执行器；执行器上打包工件 d857a346…d0fa，经 update-oci-hub-authority.yml（adopt_portal_state，action_id expiry-deploy-20261101，generation 10）部署，ok=17 failed=0，备份 /var/lib/oci-hub/backups/portal-authority-20261101T030733597810Z。OCI Python 3.12.3。
- 2026-11-01 实测（control）：past → generation 1，control 设备 ['expired'] 且不在内核，其余 8 个设备无变化；future → generation 2，原因清空并回到内核；重放 generation 2 → EXPIRY_GENERATION_STALE；clear（先恢复后删除）→ generation 3、0 名员工；catalog 无 paid_through；wsctl status 正常。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 1 / low 0 / false 0 / maybe-false 0 / rejected 1 / deferred 1
  - medium, patch — `hub-expiry.py` push：catalog 文件不存在时 `hub-terminal.catalog` 由 settings 合成，快照为空并覆盖 OCI 已接受快照。修复：无 catalog 文件即 `EXPIRY_CATALOG_MISSING`。
  - medium, defer — 员工带着 `expired` 离开快照后，`expired` 不再被任何自动流程移除；冻结意图明确"快照外不处理"，留给 2.4（不到期）与 epic 4（退役）在移出快照前先推未来日期。
  - rejected — "AC 未由 diff 证明"：AC 依赖 hitl 部署与实测，属流程未完成，不是代码缺陷。

## Design Notes

AD-9 字面写的是给 `oci-hub:user:<id>` 加原因；实现改为给该用户在 `wg-users` 上的全部设备 peer 加，理由：现有配额停用就是 peer 级（`docs/architecture/oci-employee-vpn-hub.md` §289），reconcile 已有"peer 停用后确认内核中消失"的检查，而 wg-portal v2.3.1 用户级停用对 peer 与内核的效果没有在本仓库验证过。原因字符串、只增删自有原因、快照外不处理与 AD-9 一致。

generation 不在执行器本地存计数器，以 OCI 已接受值为准（单一执行器 + admin 锁，无并发推送）。

## Verification

**Commands:**
- `cd remotecc/employee-admin && for t in test-oci-hub.py test-hub-expiry.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: 全部 OK
- `python3 pack-oci-hub.py --output $TMPDIR/oci-hub.tgz` -- expected: 输出 artifact_sha256

