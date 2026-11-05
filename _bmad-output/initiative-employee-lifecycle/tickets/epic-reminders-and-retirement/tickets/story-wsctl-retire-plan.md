---
title: 'wsctl retire 批量退役'
type: 'feature'
ticket: '4'
created: '2026-11-01'
status: 'done'
baseline_revision: '73f6481'
route: 'full'
route_source: 'auto'
risk: 'high'
review: 'quick'
review_source: 'pinned'
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 可退役员工（`now > paid_through + 3 天`）的 VM、接入身份、密钥与设备包只能手工逐项清理，容易漏项或误删已续费员工。

**Approach:** `wsctl retire` 两步：无审批时只读，列出所有 `lifecycle='retirable'` 的员工及每人将删除的内容，并给出一个审批 SHA-256；带同一 SHA 执行时按 AD-10 的顺序逐员工删除——Portal 身份（OCI executor 新增 `retire` 动作）→ Terraform 目标销毁（单个计划覆盖全部退役员工）→ BWS 记录 → 网站设备包 → catalog（写入墓碑）——最后推送到期快照。每步写运行记录，中断后用同一 SHA 续跑。

**Decision:** 2026-11-01 用户同意 epic 4 方案（AD-10：退役永不自动、一次确认、执行前复查 paid_through、无备份、VMID/网卡槽位/overlay 地址永不回收）。HAPI 部分留到 epic 6。主会话补充的实现决定：① roster 文件受 Git 跟踪，执行器推送用 `checkout -f`，退役只改执行器本地 roster，结果报告 `iac_roster_commit_required`，由主会话向 IaC 提 PR；② 不回收资源靠墓碑文件 `retired.json`（与 catalog 同目录）；③ 复查到已续费员工即在任何删除前停止，报 `RETIRE_REPLAN_REQUIRED`（Terraform 计划覆盖全部员工，集合变了计划就失效），重新 plan 时该员工自然不在列表中。

## Boundaries & Constraints

**Always:**
- 候选集合取 `hub-status.view(..., sessions=True)` 中 `lifecycle=='retirable'` 的员工；`no_expiry`、`orphan`、`invalid` 一律不进。可选 `--employee ID`（可重复）缩小范围，但不能扩大到非 retirable 员工。候选为空时输出空计划、退出 0。
- 计划（只读）输出：`{profile, action:'retire', employees:[{employee_id, recipient, vmid, paid_through, deletes:{portal:[identity ids], terraform:[addresses], bws:[record keys], bundles:[device ids], catalog:true}}], terraform_plan_sha256, approval_sha256}`。审批 SHA 覆盖员工列表、每人删除内容、Terraform 计划文件的 SHA-256、源码哈希（hub-onboard `source_hash` 的约定）。运行目录 `<catalog 目录>/retire-runs/<approval_sha256[:24]>/`，保存计划、`terraform.plan`、候选 roster、`state.json`。
- Terraform：候选 roster = 现 roster 去掉全部退役员工；`terraform plan -out` 加 `-target=module.oci_hub_workspace["<id>"]` 与 `-target=ansible_host.oci_hub_workspace["<id>"]`。计划 JSON 只允许 `delete` 动作，且地址都在这些目标内，否则报 `RETIRE_TERRAFORM_PLAN_UNSAFE`。apply 使用保存的计划文件，不做盲 apply。执行前 roster 哈希必须等于计划时的哈希或候选哈希（同 hub-onboard 的 `HUB_ROSTER_CHANGED_REPLAN_REQUIRED` 模式）。
- 执行（带 SHA）：先复核审批 SHA 与源码哈希；再对每名员工重新读取 catalog `paid_through`，若已不是 retirable，立即报 `RETIRE_REPLAN_REQUIRED` 并停止，不做任何删除。
- 删除顺序固定：
  1. Portal：OCI executor `retire` 动作删除该员工的 peer（device 与 workspace）与 user，并删除 ledger `identities` 行；`usage` 历史保留。
  2. Terraform apply。
  3. BWS：`hub-bws-store` 新增 `delete(key)`，只删属于该员工的 `OCI_HUB_` 记录，删前核对 `employee_id`。
  4. 网站设备包：`DELETE /admin/bundles?device=<id>`，Worker 复用现有按 device 删除的语句。
  5. catalog：移除该员工行，并写入墓碑。
  6. 全部员工完成后推送一次到期快照（`hub-expiry` 现有推送路径）。
- 每一步完成后先写运行记录，再做下一步；续跑时跳过已完成的步骤，但仍复查目标确实已不存在。
- 执行前后都复查：
  - Portal：`query` 中不再有该员工 identity；
  - Terraform：state 中没有目标地址；
  - PVE：`qm status` 返回不存在；
  - BWS：`records()` 中没有该员工的记录；
  - 网站：admin GET 对该 device 的包返回 410 或 404；
  - catalog：没有该员工行。
  复查失败报 `RETIRE_VERIFY_<STEP>_FAILED` 并停止。
- 墓碑 `retired.json`：`{employee_id: {recipient, vmid, vnet, address, overlay, device_addresses:[...], retired_at}}`，原子写入。现有分配逻辑（`hub-terminal.plan` 的 vmid、subnet、overlay，`allocate_device` 的设备地址）把墓碑中的值并入 used 集合。同一 employee_id 或邮箱再次开户时报 `HUB_EMPLOYEE_RETIRED`（重新开户留到以后做）。
- PVE boundary：该员工的 `workspaces` 行改为 `disabled: true`；Hub `pairs` 与 `management_access` 不动。Portal peer 删除后这些条目不再生效，地址也不会回收。如果现有 boundary 校验不允许 disabled 行引用已销毁的 vnet，在 Implementation Notes 里记录，并改为删除该行。
- 结果包含 `iac_roster_commit_required: true|false`，即本地 roster 是否与 `/srv/iac` 的 Git HEAD 不同，以及 `retired:[ids]`。错误码统一使用 `RETIRE_` 前缀，并加入安全错误码前缀列表。
- `wsctl` 动作列表与执行器写入守卫加入 `retire`。OCI executor 改动需同步 `pack-oci-hub` 的源码打包，由主会话部署到 OCI。

**Never:**
- 不自动执行，不进 Semaphore 定时。
- 不做备份，也不保留 VM 磁盘。
- 不回收 VMID、子网和地址。
- 不删除 Hub `pairs`。
- 不碰 HAPI 和 Cloudflare Access（epic 6）。
- 不处理 retirable 以外的员工。
- 不改用户未提交的文件。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 无候选 | 无 retirable | 空计划，退出 0 | — |
| 计划 | 1–n 名 retirable | 列表 + 删除内容 + approval_sha256；不写任何系统（运行目录除外） | — |
| 正常执行 | 同一 SHA | 6 步依序完成，复查通过；retired 列出；墓碑写入；快照推送 | — |
| 执行前已续费 | 计划后 renew | 不做任何删除 | `RETIRE_REPLAN_REQUIRED` |
| SHA 不符 | 错误 SHA 或源码变化 | 拒绝 | `RETIRE_APPROVAL_MISMATCH` |
| 中断续跑 | 第 3 步失败后重跑同 SHA | 跳过已完成的 1–2 步，从 3 继续 | — |
| 计划含非删除动作 | Terraform 计划含 create/update 或越界地址 | 拒绝 | `RETIRE_TERRAFORM_PLAN_UNSAFE` |
| 复查失败 | 删除后仍可见 | 停止 | `RETIRE_VERIFY_<STEP>_FAILED` |
| 墓碑生效 | 退役后新开户 | 不分配墓碑中的 vmid、子网、overlay、设备地址 | — |
| 重新开户 | 退役员工邮箱再申请 | 拒绝 | `HUB_EMPLOYEE_RETIRED` |
| BWS 记录归属不符 | 记录 employee_id 不符 | 拒绝删除 | `RETIRE_BWS_OWNERSHIP_MISMATCH` |

</frozen-after-approval>

## Code Map

私有代码在 `/Users/weierfu/Projects/IaC/remotecc/`。`employee-admin/` 中有用户未提交的改动（README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py），不得修改或提交。不 commit、不 push、不调用 Cloudflare/OCI/PVE。

- 新 `employee-admin/hub-retire.py`：`plan(base,settings,employees=None)`、`apply(base,settings,approval)`。复用：
  - `hub-status.view`（候选）；
  - `hub-onboard` 的 `sha`、`save`、`run`、`terraform_snapshot`、`source_hash`、`canonical_hash`、`target_address`；
  - `hub-terminal` 的 `catalog`、`root_roster`、`ssh`；
  - `oci-hub-admin.remote`、`hub_store`；
  - `hub-expiry` 的快照推送；
  - `hub-requests` 的 `admin_request`（网站）。
- `employee-admin/services/oci-hub/executor.py`：`execute()` 的 `allowed` 加 `'retire':{'employee_id'}`。实现 `retire(request)`：删除 Portal peer（按 public_key）和 user。`portal.py` 新增 `delete(kind, identifier)`，404 视为已删除。然后删除 identities 行。`main()` 的动作白名单同步加入；replay 幂等。
- `employee-admin/hub-bws-store.py`：`delete(key, employee_id)`（`bws secret delete <id>`）。
- `remotecc/apply-site/worker.js`：`DELETE /admin/bundles?device=<id>`（管理令牌）；`test-worker.mjs` 加用例。
- `employee-admin/hub-terminal.py`：~~分配逻辑读取墓碑；`identity` 遇到墓碑中的邮箱或 ID 报 `HUB_EMPLOYEE_RETIRED`。~~ 2026-11-02 起不改（资源允许回收，见 Plan Change Log）。
- `employee-admin/oci-hub-admin.py`、`wsctl`：`retire` 动作接入（plan 与带 SHA 的 apply 两种形式，参考 `reissue`/`reissue-apply` 或 `access` 的现有模式）。
- 测试：新 `test-hub-retire.py`（打桩 remote、ssh、run、hub_store、admin_request，覆盖矩阵）；executor 的 `retire` 用例加到现有 OCI executor 测试文件（`test-portal-authority.py` 或 `test-oci-hub.py`，选现有覆盖 `execute` 的那个）；`test-wsctl.py`。

## Tasks & Acceptance

**Execution:**
- [x] `hub-retire.py`、`services/oci-hub/{executor,portal}.py`、`hub-bws-store.py`、`hub-terminal.py`、`oci-hub-admin.py`、`wsctl`、`apply-site/worker.js` 与测试 -- 实现
- [x] 部署（hitl，主会话）-- 部署 Worker；用 deploy-oci-hub 把 executor 推到 OCI（先 --check --diff）；push employee-admin
- [x] 实测（hitl）-- 先开临时测试员工（hello+cc44@willfan.me），把 paid_through 设到 4 天前；`wsctl retire` 计划只含此人；执行后 Portal、Terraform、PVE、BWS、网站包、catalog 均无记录，墓碑写入，`wsctl status` 无孤儿；另一名员工计划后 renew，执行报 `RETIRE_REPLAN_REQUIRED`

**Acceptance Criteria:**
- Given 临时测试员工可退役，when 用计划的 SHA 执行 retire，then Portal/Terraform/PVE/BWS/网站包/catalog 均无该员工，`wsctl status` 无孤儿，~~墓碑含其 vmid~~ PVE/Hub boundary 中已无该员工条目（2026-11-02 改）。
- Given 计划后某员工已续费，when 执行，then 报 `RETIRE_REPLAN_REQUIRED`，且没有任何删除。

## Implementation Notes

代码核对结论（2026-11-01，实现前逐项核对）：

- **PVE boundary 与 disabled 行**（2026-11-01 核对，2026-11-02 起被删除方案取代）：`scripts/oci-hub/boundary.py` 的 `validate` 不看 `disabled`，`render` 也不按 `disabled` 生成规则；只有 `hook pre-start` 拒绝 `disabled` 行。
- **Boundary 删除条目**（2026-11-02，资源允许回收后）：
  - `validate` 拒绝重复的 vmid 或 vnet，以及引用不存在 workspace 的 `management_access`。因此重用 vmid 前必须删除旧行，且该员工的 `management_access` 授权要一起删（只删行不删授权会被 validate 拒绝，测试的变异检查已证实）。
  - Hub 端 `pairs` 删除该员工 overlay 或设备地址的条目；`render`、`host_forward_rules` 只按剩余条目生成；`sync_host_forward` 先删全部 `oci-hub-forward-*` 再按期望重建，旧规则会被清掉。
  - `verify --routing` 在 PVE 端只检查剩余行的 vnet，在 Hub 端只检查剩余 `pairs` 的路由，删除后校验仍可通过。
  - 两个策略各自 generation+1，经同一 `terminal_boundary` play 分别只下发到 hub 与 pve2。测试使用 IaC 仓库真实的 `boundary.validate/render`。
  - **遗留 SDN 对象（风险）**：`scripts/oci-hub/pve-sdn.py` 只创建、从不删除 zone/vnet/subnet，退役后 `oh<vmid>` vnet 与其 subnet 仍留在 PVE。同一 vmid 带同一 /30 重新分配时 `ensure` 视为已存在、不报错。但 vmid 与子网若被拆开分给不同员工（例如旧子网被分给另一个 vnet），PVE SDN 的 subnet ID 按 zone+CIDR 唯一，创建可能失败，需人工删除旧 SDN 对象。SDN 归 IaC `oci-hub-pve` 角色所有，本故事不改。新分配取最小空闲 vmid 与最小空闲子网，单人退役后两者通常一起被重用。
- **VM 删除保护**：模块固定 `protection = true`，bpg 0.70.0 销毁时不清除保护，PVE 会拒绝删除。实现：Terraform apply 前对每个将删除的 VM 先 `qm config` 核对 name/bridge/MAC，再 `qm set <vmid> --protection 0`（见 Plan Change Log ①）。
- **Terraform 计划校验**：hub-onboard `validate_plan` 只接受 create，不能复用。新写 `hub-retire.validate_plan`：托管资源只允许 `delete`，地址必须属于退役员工的目标，删除集合必须恰好等于 state 中这些员工的全部目标地址；VM 的 `before.vm_id/name/node_name` 必须与 roster 一致；模块内 data `read/no-op` 放行。否则 `RETIRE_TERRAFORM_PLAN_UNSAFE`。计划前后 state 快照不同则 `RETIRE_TERRAFORM_STATE_CHANGED`。`-var-file=<candidate>` 覆盖 auto.tfvars，凭据仍由 `TF_CLI_ARGS_plan` 注入；apply 用保存的计划文件。
- **BWS 删除**：`bws secret delete` 需要 secret id，且即使 `-o json` 也输出纯文本。`HubStore.command` 加 `parse=False`；新 `delete(key, employee_id)` 重新列出该 key，核对 project、`OCI_HUB_` 前缀、`profile/id/employee_id` 后按 id 删除，不符报 `RETIRE_BWS_OWNERSHIP_MISMATCH`，不存在视为已删。计划的 bws 列表 = `records()` 中 `employee_id` 等于该员工的记录（含 kind=hub 的 USER 记录；接口/Portal 管理记录无 employee_id，永不进入）。
- **到期快照**：`hub-expiry.push` 由 catalog 全量生成整份快照，执行器整份替换；被移出 catalog 的员工自然不在快照中，无需特殊处理。退役在全部员工完成后调用一次 `push_result`，失败只记录在结果中，续跑时重推。
- **网站**：`admin_request` 只支持 GET/POST，扩展为 DELETE（`call` 增加 `method` 参数）。Worker 没有按 device 读取包的 admin GET（只有按 token），见 Plan Change Log ③。
- **执行器**：`retire` 在 `execute` 的白名单中，`employee_id` 校验同开户正则；先 peer 后 user，删前回读并 `check_peer` 核对归属（AD-11），删后回读必须 404，并确认 kernel 中已无该 peer（否则 `RETIRE_KERNEL_PEER_PRESENT`，ledger 行保留可重试）；最后删除 ledger `identities` 行，`usage` 保留。`main()` 在 retire 前照常 `sample_live` 计入最后的流量；retire 后同 register 一样重写 `.mapping.json` 隔离快照。replay 走现有 action_id 机制，prepared 状态重放时删除幂等。`pack-oci-hub.py` 的 FILES 已含 executor/portal/ledger，无需改动。
- **运行目录**：审批 SHA 依赖计划文件，先在 `retire-runs/.plan-*` 临时目录生成，算出 SHA 后改名为 `retire-runs/<approval[:24]>/`（含 plan.json、state.json、terraform.plan、candidate.tfvars.json）。审批覆盖员工列表与删除内容、分配信息、roster 前/候选哈希、state 快照哈希、计划文件 SHA、源码哈希（hub-onboard `source_hash` + hub-retire.py + hub-status.py）。
- **执行**：先核审批与源码；对每个尚未完成 catalog 步的员工复查 `paid_through`、recipient、vmid、设备 ID 与地址都与计划相同且仍 retirable，否则 `RETIRE_REPLAN_REQUIRED`（若 catalog 行已不在且 `state.json` 中已记录该员工的 `catalog_intent`，视为 catalog 步已完成并补记，避免崩溃后永远无法续跑；`catalog_intent` 在保存 catalog 删除之前写入，值为被删行的哈希）；`candidate.tfvars.json` 读入后先核对其 SHA 等于审批中的 `candidate_sha256`，不符报 `RETIRE_APPROVAL_MISMATCH`；roster 哈希须为计划前或候选值；terraform 未执行时 state 快照须与计划时一致（否则 `RETIRE_REPLAN_REQUIRED`），以上都在任何删除之前。步骤记录在 `state.json` 的 `done`：`portal:<id>` → `terraform` → `hub_boundary` → `pve_boundary` → 每员工 `bws:<id>`、`bundles:<id>`、`catalog:<id>`；已完成步骤跳过但仍复查。Terraform 先写 `terraform_intent` 再 apply，绝不盲重放：中断后若目标仍在 state 中报 `RETIRE_TERRAFORM_REPLAN_REQUIRED`，apply 失败报 `RETIRE_TERRAFORM_APPLY_FAILED`（重新 plan 时 Portal 步为空操作，计划只删剩余目标）。apply 成功后把候选 roster 写入 `/srv/iac` 本地 roster。
- **复查码**：`RETIRE_VERIFY_PORTAL_FAILED`、`RETIRE_VERIFY_TERRAFORM_FAILED`（state 中仍有目标或 roster 不是候选）、`RETIRE_VERIFY_PVE_FAILED`、`RETIRE_VERIFY_HUB_BOUNDARY_FAILED`、`RETIRE_VERIFY_PVE_BOUNDARY_FAILED`、`RETIRE_VERIFY_BWS_FAILED`、`RETIRE_VERIFY_BUNDLES_FAILED`、`RETIRE_VERIFY_CATALOG_FAILED`。`RETIRE` 已加入 oci-hub-admin 安全错误码前缀。
- **资源回收**（2026-11-02 用户决定）：去掉墓碑。`hub-terminal.py` 恢复到 4.4 之前（无 `retired.json`、`retired()`、`retired_check`、`HUB_EMPLOYEE_RETIRED`，分配逻辑不再并入墓碑值）。退役员工的邮箱再申请时就是一次普通新开户；退役后 vmid、子网、overlay、设备地址可以再次被分配（测试 `test_retired_vmid_subnet_overlay_and_device_address_are_allocated_again`）。`hub-terminal.py` 在 `source_hash` 内，部署后未执行的开户计划需重新 plan。
- **wsctl**：动作列表、帮助、写入守卫加入 `retire`；`wsctl-confirm` 加 `retire` 流程；候选为空时直接输出空计划退出 0。`oci-hub-admin` 加 `retire`/`retire-apply` 与可重复的 `--employee`。
- **Portal 请求的 generation**：retire 请求在首次保存时固定 `generation`；若之后有 register 抬高了 generation，同一 action 会被执行器以 `MAPPING_GENERATION_MISMATCH` 拒绝（显示为 `OCI_HUB_ACTION_PENDING`）。恢复路径是重新 plan（新审批、新 action_id），不改代码。
- **运行目录保留**：plan 失败时删除临时 `.plan-*` 目录；完成或放弃的 `retire-runs/<sha>/` 不自动清理，作为运行记录保留（含 terraform.plan，不含凭据）。
- **删除 peer 后的 ledger 残留**：已核对 `reconcile()` 只遍历 `identities`，`report()` 只对 `identities` 回读 Portal，`sample()` 只遍历 mapping；被删 peer 的 `samples`、`counter_context:*`、`sample_absent:*` 与已解决的 `gaps` 行只是残留数据，不影响运行。唯一影响：该 peer 若有未解决的 gap，`resolve_gap/adjudicate_gap` 会报 `GAP_OWNERSHIP_UNKNOWN`（`adopt_legacy_gaps` 只在迁移时运行一次，已完成）。正常采样产生的 gap 都是 resolved=1，不改代码。
- **副作用提醒**：`hub-terminal.py`、`hub-requests.py`、`hub-bws-store.py` 都在 hub-onboard `source_hash` 内，部署后尚未执行的开户计划需重新 plan。执行器端 `RETIRE_*` 错误经 `remote()` 仍显示为 `OCI_HUB_ACTION_PENDING`（现有行为，未改）。

- 2026-11-02 部署：employee-admin b1c2238 → b1e4261（资源可回收）→ 84b4457（测试路径）→ 4b30d2c（runtime vault 加密去掉继承的 IaC vault id）→ 8adf11d（roster 按内容比对，执行器 settings 加 `iac_git_dir=/srv/git/iac.git`）；apply-site af3f3ea（DELETE /admin/bundles）；OCI executor 经 update-oci-hub-authority.yml 部署（ok=17，备份 portal-authority-20261101T110230550958Z）。
- 2026-11-02 实测：临时员工 cc44（VMID 511）开户 → catalog 改 paid_through=2026-10-29 → status 为 retirable → `wsctl retire` 计划只含 cc44（Portal 3、Terraform 2、BWS 3、网站包、catalog）→ `--approve 6d2c1aa2…` 执行成功，快照 generation 20。独立复查：BWS、catalog、roster、Portal、Terraform state、Hub pairs、pve2 boundary、PVE（511 不存在）均无 cc44；`wsctl status` 无孤儿，8 名员工不变；roster 与 Git HEAD 内容一致（无需 IaC 提交）。网站包未上传（端到端验证需真实设备），DELETE 删 0。"续费后 RETIRE_REPLAN_REQUIRED"由单元测试覆盖，未线上实测。
- 实测期间修复的开户链路问题（首次完整在执行器上开户）：HAPI boundary 补丁并入 IaC（#209）、VM 标签排序（#211）、pve2 写回参数（#212/#213，见 docs/troubleshooting/2026-11-01-pve2-clone-resize-timeout.md）、执行器 wireguard-tools（#213）、网关授权执行器密钥与 host key、新 VM 默认授权加执行器公钥、runtime vault 加密（4b30d2c）。

- 2026-11-02 补测（epic 4 完成标准"已续费者被跳过"）：临时员工 cc46 经 semaphore/wsctl.sh 两步开户（--plan-only 得 a9d42c9b…，--approve 同一 SHA 执行；首次在 configured 步失败、原因未抓到，续跑成功），VMID 511 复用成功。catalog 改 paid_through=2026-10-29 → `retire --employee cc46` 计划 986ae51d… → `wsctl renew hello+cc46@willfan.me 1` → 以旧 SHA 执行报 RETIRE_REPLAN_REQUIRED，复查 BWS 3、catalog、roster、Portal 3、Terraform 2、Hub pair、pve2 行全部仍在（未删）。再改回可退役 → 新计划 4e380bfc… 经 Semaphore 入口执行 → retired cc46，iac_roster_commit_required=false；复查全部无 cc46、VM 511 不存在、无孤儿、8 名员工不变，cc46 开户运行目录已归档到 runs/retired/cc46-4e380bfcc299/。

## Plan Change Log

- ① **清除 VM 删除保护（新增 PVE 写入，需用户确认）**：冻结意图未提及，但不做 Terraform 无法删除 `protection=true` 的 VM。先对所有将删除的 VM 用 `qm config` 证明 name=`oci-hub-<id>`、bridge 与 MAC 一致，全部通过后才逐台 `qm set <vmid> --protection 0`，紧接着 apply 保存的计划。
- ⑥ **（已被 2026-11-02 决定取代）墓碑提前为第一个写入步骤**（评审 Pass 1）：冻结意图写的是 catalog 步写墓碑；提前到 Portal 之前，catalog 行删除仍在第 5 步，目的是不在任何资源释放前丢失“永不回收”的保留。
- ② **PVE boundary 作为独立记录步骤**：放在 Terraform 之后、BWS 之前（VM 已不存在），经现有 `terminal_boundary` play 下发。（2026-11-01 原方案：只把退役行设 `disabled: true`，Hub `pairs`、`management_access` 不动；2026-11-02 起改为删除，见下。）
- ③ **网站复查方式**：Worker 的 admin GET 只能按 token 查询，执行器不保存全部 token。改为 `DELETE /admin/bundles?device=` 返回 `{device_id, deleted}`，复查时再调用一次必须返回 `deleted: 0`。未新增 admin 读接口（AD-13 只允许列出申请、标记处理、上传/删除包、读下载记录）。
- ④ **PVE 复查用 `pvesh get /cluster/resources`** 而不是 `qm status`：`qm status` 对不存在的 VM 与 SSH 失败都是非零退出，无法区分；`pvesh` 能确认列表中没有该 vmid。
- ⑤ **`wsctl retire --approve SHA` 直接执行该运行目录**：Terraform 计划文件每次生成字节都不同，重新 plan 必然得到新 SHA；apply 自己重新推导并复核审批，所以带 SHA 时不重新 plan。交互模式仍是先显示计划再确认。

- 2026-11-01 用户确认接受上述 5 项偏差（清除删除保护、PVE boundary 单独一步、网站复查用重复 DELETE、PVE 复查用 pvesh、--approve 执行原运行目录）。
- 2026-11-02 用户决定：退役后资源允许回收（选 B），去掉墓碑；PVE/Hub boundary 改为删除该员工条目。取代冻结意图中“VMID/网卡槽位/overlay 地址永不回收”“墓碑 `retired.json`”“`HUB_EMPLOYEE_RETIRED`”“PVE 行改为 disabled、不删除 Hub pairs”各条，并取代 ⑥。实现：
  - 不写 `retired.json`；`hub-terminal.py` 恢复 4.4 之前的分配逻辑。
  - 新增 `hub_boundary` 步骤删除该员工的 Hub `pairs`；`pve_boundary` 删除其 `workspaces` 行与 `management_access` 授权，两者各 generation+1。
  - M1 续跑改用 `state.json` 中的 `catalog_intent`。

## Review Triage Log

- Pass 3 (quick，实测期间的开户修复 4b30d2c + KeyError): high 0 / medium 1 / low 3
  - medium, patch — 只去掉继承的 ANSIBLE_VAULT_PASSWORD_FILE 不够，从 ansible/ 目录启动时 ansible.cfg 的 vault_password_file 仍会造成两个 default id：改为带标签的 `--vault-id runtime@<file> --encrypt-vault-id runtime`，撤回环境变量过滤（7fa91d2；执行器上实测在 ansible/ 目录、env 与 ansible.cfg 都存在时加密成功，playbook 以 --vault-password-file 解密成功）。
  - low, patch — 设备包等待端到端验证时顶层 status 仍为 configured：结果加 `verification` 字段显示设备包状态。
  - low, defer — 解密路径同时加载两份密码：可用且 playbook 需要 IaC vault，不改。
  - low, defer（4.5）— 回归测试为源码文本检查，宜改为经现有脚手架的行为测试。

Pass 1 (quick): high 0 / medium 2 / low 6
- M1 fixed：catalog 保存后、state.json 保存前崩溃会让续跑永远 `RETIRE_REPLAN_REQUIRED` → 原用墓碑判断；2026-11-02 改为保存前记录 `catalog_intent`，“行不在且有 intent”即补记 `catalog:<id>`（测试 `test_crash_after_the_catalog_save_resumes_to_the_snapshot_push`、`test_catalog_intent_is_recorded_before_the_catalog_save`、`test_absent_row_without_intent_still_requires_a_new_plan`）。
- M2 superseded：墓碑写得太晚 → 曾改为第一个写入步骤；2026-11-02 用户决定允许资源回收，墓碑整体去掉，此项不再适用。
- L3 fixed：复查只比 `paid_through` → 同时比 recipient、vmid、设备 ID 与地址（测试 `test_changed_recipient_vm_or_device_after_plan_stops_before_any_write`）。
- L4 defer/note：Portal 请求 generation 首次保存后固定 → 不改代码，恢复路径为重新 plan（见 Implementation Notes）。
- L5 fixed：写入 live roster 前未重核 candidate 文件 → 读入即核 `candidate_sha256`（测试 `test_changed_candidate_roster_is_refused_before_any_write`）。
- L6 fixed：plan 失败残留 `.plan-*` → 失败即删除；完成的运行目录保留不自动清理（测试 `test_failed_plan_leaves_no_staging_directory`）。
- L7 fixed：后一台 VM 身份不符时前一台保护已被清除 → 先全部核对再统一清除（测试 `test_one_unproven_vm_clears_no_protection_at_all`）。
- L8 note：已核对 reconcile/report/sample 忽略被删 peer 的 samples/gaps 残留，无需改动（见 Implementation Notes）。

Pass 2 (quick, resource reuse delta): high 0 / medium 1 / low 2
- M1 fixed：两次 retire 运行之间若有新开户被分到退役的 vmid/子网，续跑会删掉新员工的 PVE 行与授权 → hub/pve boundary 删除前检查本次计划以外的员工是否占用要删的 vmid、/30 子网、overlay 或设备地址，有则报 `RETIRE_BOUNDARY_OWNER_CONFLICT`，不写任何东西。检查范围是 catalog、roster，以及进行中的开户计划（`runs/oci-hub-terminal` 的 active plans）。只查 catalog 与 roster 不够：roster 一变，续跑开头就会报 `RETIRE_ROSTER_CHANGED_REPLAN_REQUIRED`；真正的窗口是进行中的开户，它的子创建计划会先写 PVE 行、后写 roster（测试 `test_onboarding_in_progress_on_a_retired_allocation_keeps_its_boundary_entries`、`test_catalog_employee_on_a_retired_overlay_keeps_its_boundary_entries`）。
- L2 fixed：`catalog_intent` 存了哈希却只查 key → 计划时在 allocations 中记录 `catalog_sha256`（该行哈希，纳入审批），续跑时 intent 必须等于它才算 catalog 步完成（测试 `test_absent_row_without_a_matching_intent_still_requires_a_new_plan`）。未在 catalog 步额外拒绝“行与计划哈希不同”：那时 Portal、Terraform、BWS、网站包都已删除，拒绝只会留下半退役员工；剩余边界情况是行的非关键字段在计划后变化，且恰好在该窗口崩溃，此时续跑报 `RETIRE_REPLAN_REQUIRED`，catalog 行其实已删，只差到期快照，可用 `wsctl expiry` 补推。
- L3 fixed：`stale()` 在过滤 pairs 前只算一次。

## Verification

**Commands:**
- `cd remotecc/employee-admin && for t in test-hub-retire.py test-hub-status.py test-oci-hub.py test-portal-authority.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: OK（沙箱外运行）
- `cd remotecc/apply-site && node --test test-worker.mjs` -- expected: 全部通过

**Result（2026-11-02，沙箱内，资源回收改动后重跑）：** `test-hub-retire.py` 18/18 OK（新增与改动的用例均经变异验证会失败，boundary 用 IaC 真实 validate/render）；`test-oci-hub.py` 70 个，仅 4 个既有的本地 HTTP 服务器用例因沙箱禁止绑定端口报错（与基线一致），新增 7 个 retire 用例全过；`test-portal-authority.py`、`test-hub-status.py`、`test-hub-remind.py`、`test-hub-create.py`、`test-hub-recovery.py`、`test-hub-mosh.py`、`test-hub-expiry.py` 等全过；`test-wsctl.py` 29 个，仅 2 个既有 ssh-agent socket 用例失败（基线即失败）；`test-hub-requests.py` 因沙箱禁止 socket 全部报错（基线即如此）；`pack-oci-hub.py` 打包与校验通过；`node --test test-worker.mjs` 81/81。尚未部署、尚未实测。
