---
title: '地址对齐：VM 与设备地址末位等于 VMID-500'
type: 'feature'
ticket: '16'
created: '2026-11-02'
status: 'built'
baseline_revision: 'employee-admin 26cb3d8d51e0754a24f54a310520d32b0ba97ea6; IaC b2471a7fbc4ccf9d9caad81864e168423556ab54'
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

**Problem:** 员工地址由"第一个空闲地址"分配，与 VMID 无关；现有员工 overlay（10.234.0.x）与 Hub /30（10.236.x.0/30）已对齐 VMID-500，但设备地址（10.235.0.x）不齐（502→.11、504→.5、505→.6、506→.7、507→.9；508 已齐）。失败的 demo 开户与已退役 cctest33 的残留计划仍占用 503/510 与若干地址并阻塞开户。

**Approach:** 分配器改为由 VMID 推导三类地址（冲突即报错、不回退）；新增两步审批的迁移动作把现有员工的设备地址迁到 `10.235.0.<VMID-500>`，与 workspace-onboarding 1.1.0（5.15）一起重发设备包，员工只重新 setup 一次；先清理残留计划，最后以 VMID 503 开 demo。

**Decision (2026-11-02 用户):** 现在做，不等维护窗口；现有员工一并迁移；同一员工所有设备共用一个地址；VMID 501 对应 .1 保留给 Hub，员工从 502 起；demo 在本 story 完成后开户；低风险可放手，但推送、部署、Hub 变更、发信逐项授权。

**Decision (2026-11-02 用户, Open Question 1):** 选 A 停机切换——同一密钥改地址，旧设备包在迁移时失效，员工用新设备包重跑 setup 后恢复；用户已提前通知员工。

## Boundaries & Constraints

**Always:** 每个迁移步骤可重复执行并可从中断处继续；迁移在 admin 锁内整体进行；跨员工隔离不变；迁移后 `wsctl status` 全员 `configured`；508 只重发 1.1.0 设备包；所有员工 VM、overlay、Hub /30 与 Terraform 不变。

**Never:** 不改网关；不改 Terraform 资源；不在该员工新设备包生成并验证之前切换其地址；不新建第二个 WireGuard 身份；不给员工发信，除非该员工的新设备包已生成并验证。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 新开户 | VMID v（502..754） | overlay/设备 `.<v-500>`，Hub `/30` `10.236.<v-500>.0/30` | 目标地址被占 → `HUB_WORKSPACE_ADDRESS_CONFLICT`/`HUB_DEVICE_ADDRESS_CONFLICT` |
| VMID 越界 | v<502 或 >754 | 拒绝 | `HUB_VMID_OUT_OF_SCHEME` |
| 迁移计划 | 现有员工 | 列出每人旧→新设备地址与顺序（链式：502、504 先，505/506/507 依次） | 任一员工有进行中的动作 → 拒绝 |
| 迁移中断 | 部分员工已迁 | 再次 approve 从断点继续 | — |
| 已对齐员工 | 508 | 只重建设备包 | — |

</frozen-after-approval>

## Code Map

工作区：employee-admin `/Users/weierfu/Projects/IaC/remotecc/employee-admin` 分支 `claude/address-align`（26cb3d8 + 已合入 5.15 `claude/vm-alias`，合并提交 ac07bbe）；IaC worktree `/private/tmp/iac-address-align` 分支 `claude/address-align`（b2471a7）。实现代理只改这两处的代码、测试与文档，不 commit/push，不做任何执行器、Hub、pve2 操作。

employee-admin：
- `hub-terminal.py:327-336` -- 新工作区子网/overlay 改为 VMID 推导；`used`/`pending`/`pairs` 只做冲突检查。
- `hub-terminal.py:67-94` `allocate_device` -- 新设备地址 = `10.235.0.<VMID-500>`；现有记录复用不变。
- `hub-terminal.py:165-182,320-364` -- `started()`/`check_other_runs`/`active_plans`：残留 run 处理（见任务 1）。
- `hub-bws-store.py:53-63,137-178` -- 只能 create/delete；地址变更需新增 edit 或新记录。
- Hub 执行器 `services/oci-hub/executor.py:190-238`（IaC 仓库，部署到 Hub `/opt/oci-hub`）-- `register` 对地址变更报 `IDENTITY_IMMUTABLE`，只有整员工 `retire`；需新增按设备的地址变更/移除动作。
- `hub-terminal.py:110-113` 边界配对 + `hub-mosh-ports.py`（plan/apply/digest/`retire.play_boundary`）-- 迁移动作的模板。
- `hub-terminal.py:524-531` + `ansible/roles/employee-workspace/tasks/authorization.yml:10` -- VM 内 `AllowedIPs` 与 `authorized_keys from=` 由设备记录生成，由 `terminal_configure` play 重放（`hub-desktop.py:95` 模式）。
- `hub-terminal.py:417-424,539`、`oci-hub-admin.py:205-236,290-377` -- 设备包须重建（manifest 地址须与 Portal 一致）后用 `reissue` 发送。
- 接线：`oci-hub-admin.py:396,460-465`、`wsctl-confirm.py:14-22,55`、`wsctl:10,17,24,35,98`、`semaphore/wsctl.sh:16`、`docs/admin-handbook.md`。
- 执行器残留 run：`runs/oci-hub-terminal/` 下 `c7d4…`（及祖先 `9bb6…`、`49f8…`、`908f…`）与 `d941…`（cctest33，vmid 510）；无 abandon 机制，先例为移到 `runs/archive-*`。pve2 `/etc/oci-hub/boundary.json` 含 503（disabled）行，Hub 侧需核对。

## Tasks & Acceptance

**Execution:**
- [ ] 执行器：归档残留 run（需授权）并核对 Hub/pve2 boundary 中 503 残留行 -- 解除开户阻塞
- [x] `hub-terminal.py` 分配器 + 测试 -- 新开户对齐
- [x] 迁移动作 `wsctl address-migrate`：两步审批，按 504→505→506→507、502 顺序逐人执行（Hub 执行器按设备改地址 → BWS 记录更新 → Hub 边界配对 → VM `AllowedIPs`/`authorized_keys` 重放 → 重建设备包），可断点续跑；Hub 执行器新增按设备改地址动作（`services/oci-hub/executor.py`）；BWS 新增 edit；测试 + 手册
- [ ] 合入 5.15（`claude/vm-alias`）并发布 workspace-onboarding 1.1.0（需授权）
- [ ] 执行器（需授权）：部署 → 迁移 plan/approve → 为每位员工重建设备包 → 通知员工重新 setup（发信需授权）→ 以 `--vmid 503` 开 demo

**Acceptance Criteria:**
- Given 迁移完成，when `wsctl status`，then 每位员工设备地址末位 = VMID-500 且 `configured`。
- Given 员工用新设备包重跑 setup，when `mosh <员工ID>-vm`，then 登录成功。
- Given 残留 run 已归档，when `provision --vmid 503`，then demo 得到 `10.236.3.0/30`、`10.234.0.3`、`10.235.0.3` 并开户成功。
- Given 两名员工，when 互相访问对方 VM，then 仍被拒绝。

## Implementation Notes

- 2026-11-02 实现代理（未 commit/push，未做执行器/Hub/pve2 操作）：
  - 分配器：`hub-terminal.py` 新增 `scheme_index/scheme_address/scheme_subnet`（VMID 502–754，地址由 Hub/PVE policy 的网段推导）；新工作区 overlay、`/30`、设备地址都由 VMID 推导，被占即 `HUB_WORKSPACE_ADDRESS_CONFLICT`/`HUB_DEVICE_ADDRESS_CONFLICT`；越界 `HUB_VMID_OUT_OF_SCHEME`。员工已有设备身份时不再分配第二个（共用一个地址）。恢复中的旧计划（reserved）保持原地址。
  - 迁移：新文件 `hub-address-migrate.py`（plan/apply，运行目录 `runs/address-migrate/<SHA24>`）。每人顺序：stage 新包（切换前生成并校验）→ 执行器 `readdress` → BWS `HubStore.readdress`（`bws secret edit`，compare-and-set）→ Hub 边界配对（`hub-retire.play_boundary`）→ `terminal_configure` 重放 → 安装新包（旧包移到 `bundle_output_dir/archive-address-migrate-<SHA12>/`）→ catalog。`wsctl address-migrate --approve` 直接执行已批准运行（同 retire），首次执行前重新推导核对摘要。
  - 执行器：`services/oci-hub/executor.py` 新增 `readdress` 动作（`identity/address_before/address_after`），Portal 先写、ledger 后写，可重放；校验 Hub 内核 `wg show wg-users allowed-ips`。`portal.py` 新增 `Portal.readdress`。注意：执行器源码实际在 employee-admin（`pack-oci-hub.py` 打包），不在 IaC 仓库；IaC worktree 无改动。

## Plan Change Log

## Review Triage Log

## Verification

**Commands:**
- `python3 -m unittest`（`test-hub-*.py`、`test-wsctl.py`、`test-oci-hub.py`）-- 全部通过
- IaC：`services/oci-hub` 测试与 `scripts/ci/validate-repository.sh` 相关子集 -- 通过

### Pass 1 (quick) — high 0 / medium 2 / low 3 / false 0 / maybe-false 0

| # | Finding | Verdict | Route | Evidence / action |
|---|---------|---------|-------|-------------------|
| 1 | readdress 请求在重试时原样重放旧 generation，被拒后永远无法完成 | medium | patch | 已修：Hub 无挂起且设备未到新地址时按当前 generation 重建请求；新增测试 |
| 2 | `stage:` 完成后跳过整体重推导检查 | medium | patch | 已修：仅外部步骤计入；新增测试 |
| 3 | 手册 3.2 仍写"已有员工的新设备" | low | patch | 已修 |
| 4 | 越界 VMID 报 UNAVAILABLE 而非 OUT_OF_SCHEME | low | patch | 已修：先查范围；新增测试 |
| 5 | `derive` 的 `allowed_actions` 未使用 | low | patch | 已删除 |

用户追加要求：`address-migrate --employee`（可重复）只迁指定员工，已实现并测试。2026-11-02 用户决定：先完成 5.21/5.22 邮件，再部署并执行迁移（迁移与发新设备包同时进行）。
