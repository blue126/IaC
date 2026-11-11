---
title: '一条命令登录（服务端）：系统 mosh-server 与整段端口'
type: 'feature'
ticket: '10'
created: '2026-11-02'
status: done
baseline_revision: 'IaC de62b750a236c8d38e132b8d1212372c9cc0e2d4; employee-admin 8268f9180cb12e37e609a509892f90076a5518ed'
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

**Problem:** 员工本机原生 `mosh <别名>` 用不了，因为 VM 要求自定义服务端 `workspace-mosh`、Hub 只放行每台设备分到的 10 个 UDP 端口，客户端必须带 `--server` 和 `--port`。

**Approach:** 服务端去掉这两个前提：VM 上系统自带的 `mosh-server` 直接可用（超时由 sshd `SetEnv` 给 `employee` 用户设置），执行器不再逐设备分配端口，Hub 边界对每个"设备 → 本人 VM"配对放行 UDP 60000–61000；现有配对在一次边界更新里全部迁移到整段。客户端（bootstrap 别名与 Include、网站主机名）在 5.15 做。

**Decision (2026-11-02 用户):** 拆分后本 story 只做服务端；mosh-server 可监听所有网卡，安全依靠 Hub 边界；系统 hostname 不改；不重发设备包。

## Boundaries & Constraints

**Always:** 上线后现有客户端照常：保留 `/usr/local/bin/workspace-mosh` 与清单 `mosh_ports` 字段，旧端口段都在 60000–61000 内；新开户设备清单的 `mosh_ports` 为 `[60000, 61000]`；其他员工的设备到该 VM 一律拒绝（隔离靠目标 VM 地址）；同一员工多台设备可共享整段；迁移走现有两步审批（`--plan-only` / `--approve`），计划列出每个配对的旧段与新段；sshd 配置写成 `sshd_config.d` 的独立文件，`sshd -t` 校验通过才 reload。

**Never:** 不改 bootstrap、设备包、交付邮件、网站与状态推送（5.15）；不改 VM 系统 hostname、PVE 名、inventory 名；不碰用户未提交的 employee-admin 文件（README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py）；不 commit、不推送、不部署、不改线上 Hub。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 新开户 | provision 新设备 | 配对与清单端口为 `[60000,61000]` | — |
| 迁移计划 | 现有配对为窄段 | `--plan-only` 列出每对旧段→全段，不写入 | — |
| 迁移执行 | `--approve` 正确摘要 | 一次边界更新全部改为全段 | 摘要不符 → 拒绝，不写 |
| 已迁移 | 再次运行 | 计划为空，不报 MAPPING_CONFLICT | — |
| 跨员工 | B 的设备 → A 的 VM UDP 60000–61000 | 拒绝 | — |
| 同员工多设备 | A 的两台设备 → A 的 VM | 都允许 | — |
| 旧客户端 | `mosh --server=workspace-mosh --port=<旧段>` | 照常 | — |
| 原生 mosh | `mosh --ssh="ssh -F <设备配置>" <别名>`（无 --server/--port） | 进入工作区，断线超时生效 | — |

</frozen-after-approval>

## Code Map

- **IaC**（worktree 基于 origin/main de62b75）：
  - `scripts/oci-hub/boundary.py:116-130` 配对与 `mosh_ports` 校验，`:127-129` 同 VM 重叠检查改为允许同一 VM 的配对共享区间（不同 VM 仍各自独立）；`:163-166` nft、`:297-302` iptables 渲染不变。
  - `ansible/roles/oci-hub-mosh/`：新增 `templates/sshd-mosh.conf.j2` → `/etc/ssh/sshd_config.d/10-mosh.conf`（`Match User employee` / `SetEnv MOSH_SERVER_NETWORK_TMOUT={{ oci_hub_mosh_network_timeout }}`），`validate: sshd -t -f %s` 不可直接校验片段，改为写入后 `sshd -t`，失败回滚；新增 `handlers/main.yml` reload ssh；`tasks/main.yml:41-47` 保留 workspace-mosh；`defaults/main.yml:4` 超时值复用。确认 Ubuntu 26.04 的 OpenSSH ≥ 8.7。
  - 测试：`tests/oci-hub/test-offline.py:92-104`（重叠拒绝改为：同 VM 允许、跨 VM 无关）、`test-network.py:138-148`（同员工跨设备由拒绝改为允许；新增跨员工拒绝断言若缺）、`test-host-forward.py:9`、`test-mosh-boundary-play.py:46`；新增 sshd drop-in 的 role 测试或 playbook 语法检查。
  - 文档：`tests/oci-hub/README.md:29-40`、`docs/architecture/mosh-oci-hub-transition.md:118-127`、`docs/deployment/mosh-oci-hub-pilot.md:57-59`。
- **employee-admin**（main 8268f91）：
  - `hub-terminal.py:84-90` 分配改为固定 `[60000,61000]`；`:105-107` 现有配对不同会 `HUB_TERMINAL_MAPPING_CONFLICT`——迁移命令负责把旧段改成全段，之后不再冲突；`:382/:510/:530` 新设备写全段；`:411` 复用旧包时允许旧窄段。
  - 迁移入口：找到现有"重算全部配对并推送边界"的路径（hub-mosh.py / boundary 推送处），新增 `wsctl mosh-ports-migrate`（或 `access` 计划中的一类变更），走两步审批，结果写运行记录。
  - `hub-bundle.py:15,20-24`、`hub-bws-store.py:97-99`、`hub-onboard.py:243`、`oci-hub-admin.py:156`（`mosh_port_isolation` 验收改为"跨员工隔离"）、`hub-status.py:81`（监听统计改为全段）。
  - 测试：`test-hub-mosh.py:43-54,97-99`、`test-oci-hub.py:681,823-842`、`test-hub-retire.py:50,61,205`、`test-hub-status.py:75`、`test-hub-credential-preparation.py:30,68`、`test-wsctl.py`（新命令分发）。

## Tasks & Acceptance

**Execution:**
- [x] IaC boundary.py + 测试 -- 同 VM 共享整段、跨员工隔离
- [x] IaC oci-hub-mosh role -- sshd SetEnv drop-in + handler + 文档
- [x] employee-admin -- 固定全段、迁移命令（两步审批）、校验与状态适配、测试

**Acceptance Criteria:**
- Given 迁移计划，when 执行器上 `--plan-only`，then 列出全部现有配对旧段→`[60000,61000]` 且摘要稳定（两次相同）。
- Given 渲染后的边界规则，when 检查 nft/iptables，then 每个配对为 `ip saddr <设备> ip daddr <本人 VM> udp dport 60000-61000`，不存在跨员工规则。
- Given oci-hub-mosh role 在测试 VM 上运行，when 员工通过 ssh 登录，then 环境含 `MOSH_SERVER_NETWORK_TMOUT`，`sshd -t` 通过。

## Implementation Notes

- 两个仓库各自工作：IaC 在 worktree `/Users/weierfu/Projects/IaC/.worktrees/mosh-full-range`（分支 `claude/mosh-full-range`，基于 origin/main），employee-admin 在主检出 main 上改（不碰用户文件）。

## Plan Change Log

- 2026-11-02 实现：验收检查名 `mosh_port_isolation` 改为 `mosh_cross_employee_denied`（回执 1 小时有效，无历史回执受影响）；迁移入口为新模块 `hub-mosh-ports.py`（`wsctl mosh-ports-migrate`），运行记录写 `runs/mosh-ports-migrate/<摘要前24位>.json`；hub-bundle / hub-bws-store / hub-onboard 校验已接受 `60000:61000`，未改代码，只补了测试。

## Review Triage Log

### Pass 1 (quick) — high 0 / medium 2 / low 4 / false 0 / maybe-false 1; rejected 3

| # | Finding | Verdict | Route | Evidence / action |
|---|---------|---------|-------|-------------------|
| 1 | 架构文档 `mosh-oci-hub-transition.md:59/:118` 与 `oci-employee-vpn-hub.md:168` 仍写逐设备端口、overlay 绑定 | low | patch | 与新段落矛盾；改写这几处 |
| 2 | 迁移计划只列需要变更的配对 | low | reject | 已是全段的配对无需迁移，列出变更即满足"旧段→全段"；计划内含完整候选 |
| 3 | 上线顺序未记录：执行器 iac_root 未含新 boundary.py 时，迁移与"员工第二台设备开户"都会失败，且报通用错误 | medium | patch | 在 `docs/deployment/mosh-oci-hub-pilot.md` 写明先部署 IaC、再部署 employee-admin、再迁移；hub-mosh-ports 把 boundary 校验的 ValueError 包成 `HUB_MOSH_BOUNDARY_INVALID` |
| 4 | sshd -t 回滚把任何失败都归咎于 drop-in；`register` 未用 | low | patch | 失败信息改为附 sshd -t 输出、说明已回滚 drop-in；删未用 register |
| 5 | 验收 3 只在配置层面验证 | maybe-false | reject | 真实 employee 会话的环境变量在部署后的手工检查中验证（计划 Verification 已列） |
| 6 | `hub-mosh-ports.apply` 复制了第三份 terminal_boundary play 调用 | medium | patch | 复用 hub-retire.py:127 的现有 helper，不另写 |
| 7 | `mosh_udp_listeners` 变为 VM 级但仍挂在每台设备下 | low | reject | 只用于管理员 status 视图，网站副本不用；改字段结构会牵动 status 输出与测试 |

## Verification

**Commands:**
- IaC：`python3 -m unittest` 运行 `tests/oci-hub/` 中受影响的测试 -- 全部通过；`ansible-playbook --syntax-check` 相关 playbook
- employee-admin：`python3 -m unittest test-hub-mosh.py test-oci-hub.py test-hub-retire.py test-hub-status.py test-hub-credential-preparation.py test-wsctl.py test-hub-publish.py` -- 全部通过（在 IaC 根下有 scripts/oci-hub 的位置运行）

**Manual checks (部署阶段，另行授权):**
- 执行器 `--plan-only` 迁移计划；IaC 边界与 role 的 `--check --diff`；上线后用 control 设备以原生 mosh（无 --server/--port）登录。
