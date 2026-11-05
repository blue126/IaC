---
title: 'wsctl enforce 到期关机、续费开机'
type: 'feature'
ticket: '2'
created: '2026-11-01'
status: 'done'
baseline_revision: 'a564a9e6563744975f058580320c119f95a3c2ef'
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

**Problem:** 到期员工的 VM 仍在运行，可在 VM 内预置反向隧道绕过 Portal；续费后也没有人把 VM 开回来。

**Approach:** 新增 `wsctl enforce`：按 catalog 对 `now > paid_through` 的员工正常关机（超时强制停止）并记录"由执行器关机"；对已续费且有该记录的员工开机并删除记录。Semaphore 每 5 分钟运行一次。

**Decision:** 实测员工为 `control`（2026-11-01 用户批准推进到 epic 2 结束）。

## Boundaries & Constraints

**Always:** 只处理 catalog 中带 `paid_through` 的员工，且其 catalog `vmid` 必须与 Terraform 清单 `oci_hub_workspaces[<employee_id>].vmid` 一致，否则跳过并在结果中报告；关机为 `qm shutdown <vmid> --timeout 120`，失败或超时后 `qm stop <vmid>`；只开有执行器关机记录的 VM；记录写入先写临时文件再原子改名；单个员工失败不阻断其他员工，整体以非零退出报告失败；无需确认；只在执行器运行（Mac 返回 `WSCTL_WRITES_ON_EXECUTOR`）。

**Never:** 不删除磁盘、不改 Terraform、不碰 catalog 以外或无 `paid_through` 的 VM；不开管理员手动关掉的 VM；不处理 HAPI（epic 6）；不改 renew/初始化（2.3、2.4）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 到期运行中 | 过期，VM running | shutdown；写记录 | shutdown 失败 → stop |
| 到期已关 | 过期，VM stopped，无记录 | 不动作、不写记录（不认领手动关机） | — |
| 续费且有记录 | 未过期，stopped，有记录 | start；删记录 | — |
| 未过期手动关 | 未过期，stopped，无记录 | 不开机 | — |
| 续费已开 | 未过期，running，有记录 | 删记录 | — |
| 无 paid_through / 不在 catalog | — | 不动作 | — |
| vmid 不一致 | catalog 与 Terraform 不同 | 不动作 | 结果列出 `ENFORCE_VMID_MISMATCH`，非零退出 |
| PVE 不可达 | ssh 失败 | 该员工记为失败，其他员工照常 | 非零退出 |

</frozen-after-approval>

## Code Map

路径相对私有仓库 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（有用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交）。IaC 仓库部分在 worktree 里做。标 hitl 的任务由主会话执行，实现时跳过；不 commit、不 push。

- `hub-terminal.py` -- 复用 `ssh(h,target,args)`（PVE 目标 `settings['oci_hub']['terminal']['pve_ssh_target']`，root@pve2）、`catalog(h,settings,root)`、`root_roster(root)`。
- `hub-status.py:21` -- 现有 `qm status` 用法（输出 `status: running|stopped`）。
- `hub-expiry.py` -- 2.1 新模块；`EXPIRY_CATALOG_MISSING` 的写法可照搬（无 catalog 文件即拒绝）。
- 新 `hub-enforce.py` -- `run(h,settings,now=None)`：读 catalog、Terraform 清单，记录文件为 `Path(catalog_file).parent/'enforce-stopped.json'`（`{employee_id: {"vmid":…, "stopped_at":…}}`）；返回 `{profile, action:'enforce', stopped:[…], started:[…], failures:[{employee_id, code}]}`，有失败时 `ValueError('ENFORCE_PARTIAL_FAILURE')` 前先打印结果（或把结果附在异常上，按 `oci-hub-admin.py` 现有输出约定）。
- `oci-hub-admin.py` -- action choices 加 `enforce`；安全错误码前缀加 `ENFORCE`。`main()` 在 `exclusive_admin_lock` 下运行（忙时 `HUB_ADMIN_BUSY`，下一轮重试即可）。
- `wsctl` -- 动作列表与执行器写入守卫加 `enforce`。
- `h`（`hub-onboard` 模块）提供 `run`；测试用假 `ssh` 记录调用。
- IaC：`ansible/roles/semaphore/files/semaphore-bootstrap.py` -- `TEMPLATES` 加 `'wsctl enforce':(['enforce'],[],False)`，`SCHEDULES` 加 `'wsctl enforce':'*/5 * * * *'`。

## Tasks & Acceptance

**Execution:**
- [ ] `hub-enforce.py` -- 实现 I/O 矩阵 -- 到期关机与续费开机
- [ ] 新 `test-hub-enforce.py` -- 覆盖矩阵全部行（假 ssh/假时间） -- 回归
- [ ] `oci-hub-admin.py`、`wsctl`、`test-wsctl.py` -- 入口与 Mac 拒绝 -- 执行器专属
- [x] IaC worktree：`semaphore-bootstrap.py` 加模板与 5 分钟定时（PR #202，主会话负责 CI 与合并）
- [x] 部署（hitl）-- push employee-admin；执行器上安装并运行 bootstrap
- [x] 实测（hitl）-- `control` 设过去 → `wsctl expiry` → 5 分钟内 VM 关机并有记录；设未来 → 5 分钟内开机、记录删除；其他 VM 状态不变；收尾先恢复再删字段

**Acceptance Criteria:**
- Given 定时任务已建，when 查看 Semaphore，then `wsctl enforce` 每 5 分钟成功运行一次。
- Given `control` 到期，when 下一轮 enforce，then `qm status` 为 stopped 且记录存在；续费后下一轮为 running 且记录消失。
- Given 整个过程，when 比较其他员工 VM 电源状态，then 不变。

## Implementation Notes

- 2026-11-01 主会话改动：关机失败时保留记录（VM 可能已关，仍在运行则下一轮再关），测试同步改名。提交 89eef9c，推到执行器；PR #202 合并，iac 推到执行器 17400ac，bootstrap 重跑 changed=true。
- 2026-11-01 实测（control，VMID 502）：设过去 → 255 秒后 Semaphore 定时 enforce 关机且有记录；设未来 → 304 秒后开机且记录删除；收尾 generation 6、0 名员工、记录文件为空；其他 VM 电源状态无变化。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 3 / low 4 / false 1
  - medium, patch — 记录在关机之后才写，中途被杀则续费后永不开机：改为关机前写记录，失败时撤回。
  - medium, patch — 串行关机每台最多 120 秒且持锁，月底多人同时到期会超出 5 分钟：改为并发 `qm shutdown --timeout 120 --forceStop 1`。
  - medium, patch — 记录存在但 catalog 行已无 paid_through 时被忽略，VM 永远关着：无 paid_through 视为未到期（开机、删记录）；员工不在 catalog 报 `ENFORCE_RECORD_ORPHANED`。
  - low, patch — 无时区的 paid_through 按本机时区解析，与 OCI 不一致：视为 `ENFORCE_PAID_THROUGH_INVALID`。
  - low, patch — vmid 缺失时 None==None 通过后崩溃：要求 int 且相等。
  - low, patch — 记录条目非 dict 或 JSON 损坏时整轮中断且错误码不稳定：逐条校验，统一 `ENFORCE_RECORD_INVALID`。
  - low, patch — 多个失败分支与 `__main__` 退出路径缺测试：补测试。
  - false — "IaC 部分不在 diff 中"：PR #202 已含模板与定时，CI 全绿。

## Verification

**Commands:**
- `cd remotecc/employee-admin && for t in test-hub-enforce.py test-hub-expiry.py test-oci-hub.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: 全部 OK（需在沙箱外运行，部分测试要绑定本地 socket）
