---
title: '员工名单移出代码仓库并拆除旧员工模型'
type: 'refactor'
ticket: '18'
created: '2026-11-02'
status: 'built'
baseline_revision: 'IaC d8b5f2b40cf0f98fd7d95c9d884668112c65ea2b; employee-admin 7fa17f1dabf23f278ce2d961b27c402fdc130713'
route: 'full'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** oci-hub 名单（`oci-hub-workspaces.auto.tfvars.json`）在 IaC git 中，退役/开户后执行器副本与 GitHub 漂移，且需要回流 PR；旧员工模型（`employee_workspaces` 表、`employee_slot`、墓碑 `employee_retirement`、vmbr501-508、旧边界 hook、pve2 上丢弃 `tap503i0` 的退役防护）仍占用 VMID 503，demo 无法开户。

**Approach:** 名单成为执行器 `employee-data` 中的运行状态，由 settings `oci_hub.terraform_roster` 指向，`oci_hub_workspaces` 变量必填；先把 VM500 的 `employee_access` 搬到新的受跟踪文件并确认 plan 对 VM500 无变化，再删除旧名单与旧模型；拆除 pve2 退役防护；然后以 `--vmid 503` 开 demo。

**Decision (2026-11-02 用户):** 名单是状态，不依赖代码 PR；先搬 VM500 配置再删旧名单；推送执行器前先把执行器名单复制到 employee-data；CI/Jenkins 校验同步修改；所有改动低风险，但提交、推送、部署、apply 仍逐项授权。

**Decision (2026-11-02 用户, review intent_gap):** Jenkins 不读员工名单；Terraform 将拆为内部根与对外服务根（5.19，VM500、员工模板、ws-executor 归对外根）。5.18 期间 Jenkins proxmox plan 因必填名单变量缺失而失败，投影不再提供空名单。

## Boundaries & Constraints

**Always:** VM500 及其模板/引导资源零变更；现有员工 VM（502、504-508）及 oci-hub 模块资源零变更；旧网桥与旧 hook 文件仅在确认无引用后删除（2026-11-02 只读核实：所有员工 VM 用 `oh50x` 与 `oci-hub-boundary.sh`）；名单路径缺失时 Terraform 与 wsctl 直接报错，不回退到旧路径。

**Never:** 不改网关；不改 `oci-hub-boundary.sh`、oci-hub 模块或 SDN；不清理 legacy `--profile existing` 代码（`admin-core.py`、`workspace-registry.py`、`ansible/onboard.yml`，仅在最终报告中列出）；不把名单写回任何 git 仓库。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 执行器 plan | employee-data 中有名单 | 开户/退役 plan 只含目标员工变化 | — |
| 名单缺失 | settings 路径不存在 | wsctl 报 `ROSTER_MISSING`，不调用 Terraform | 非零退出 |
| Mac 手动 plan | 未给 `-var-file` | Terraform 报必填变量缺失 | — |
| 退役 | retire 完成 | 结果中无 `iac_roster_commit_required` | — |
| demo | `provision --vmid 503` | 不再被旧表校验拦截，网络不被 `tap503i0` 规则丢弃 | — |

</frozen-after-approval>

## Code Map

IaC（worktree `/private/tmp/iac-roster-out-of-git`，分支 `claude/roster-out-of-git`）：
- `terraform/proxmox/employee-workspaces.auto.tfvars.json` -- 含 `employee_access`（VM500）与 `employee_workspaces`；前者搬到新 `employee-access.auto.tfvars.json`，文件删除。
- `terraform/proxmox/oci-hub-workspaces.auto.tfvars.json` -- 移出 git（`git rm --cached` 后 `.gitignore` 显式忽略）；`oci-hub-workspace.tf:2` 变量去掉 `default = {}`，删 `:42-50` 对旧表的校验。
- `terraform/proxmox/employee-workspace.tf` -- 整个文件删除；`terraform_data.employee_slot`/`employee_retirement` 用 `removed { lifecycle { destroy = false } }` 遗忘；`network_linux_bridge.employee`（vmbr501-508）与 `file.employee_boundary_hook`（7 个 `employee-*-boundary.py`）随块删除而销毁；`employee_workspace`/`ansible_host.employee_workspace` 当前 0 实例。`employee-boundary-hook.py.tftpl` 一并删除。
- `terraform/proxmox/employee-workspace-oci-adoption.tf` -- moved 已完成，删除。
- `terraform/proxmox/employee-access.tf` -- 去掉 `:25` 对 slot 的依赖、`:52-59` 动态网卡（已为空）、`:76-81,:89-104` 旧表前置条件（保留 `:83-87` uplink）、`:123-128` `employee_access_networks_json`；保留 `employee-template.tf`。
- `ansible/playbooks/configure-retired-workspace-boundary.yml`、`ansible/roles/retired-workspace-boundary/` -- 改为一次性拆除剧本 `remove-retired-workspace-boundary.yml`（停用并删除 `employee-firewall.service`、`/etc/employee-access.nft`、`/usr/local/lib/employee-firewall.py`、`nft delete table bridge employee_boundary`，幂等）+ Verify play；删除旧 role。
- `scripts/jenkins/proxmox-projection.py:17-18,61-63,78,219-223`、`ci/proxmox-plan-policy.json:41-42`、`tests/ci/jenkins-peer-test.py:221-249` -- 文件集合改为不含两个名单；名单经 Jenkins 不在仓库时投影给空 `{}`（用 `-var 'oci_hub_workspaces={}'` 或生成文件，选现有机制中更简单者），用 `update-projection-policy.py` 重生成策略。
- `tests/oci-hub/prepare-terraform.py:20` 删除 `employee_workspaces` 桩；`tests/employee-workspace/` 删除。
- 文档：`docs/deployment/oci-hub-native-provisioning.md:66`、`docs/deployment/mosh-oci-hub-vm509.md:58`、`docs/architecture/oci-employee-vpn-hub.md:245`、`docs/planning/employee-workspace-self-service.md:14`、`docs/guides/employee-claude-workspace.md` 中名单位置与旧模型描述。

employee-admin（分支 `claude/roster-runtime`）：
- `hub-terminal.py:18-22` `root_roster(root)` → `roster(settings)` 读 `settings['oci_hub']['terraform_roster']`，缺失报 `ROSTER_MISSING`；`:364` 子配置不再覆盖 `terraform_roster`。调用点：`hub-terminal.py:32,284`、`hub-remind.py:72`、`hub-enforce.py:36`、`hub-publish.py:69`、`hub-desktop.py:58`、`hub-status.py:49`、`hub-retire.py:223`。
- `hub-retire.py:14,17-25,93,171,204,301-302` -- `ROSTER` 改用 settings 路径；删除 `roster_commit_required` 与 `iac_roster_commit_required`。
- `hub-onboard.py` 已用 `config['terraform_roster']`，不改；`:114` source_hash 会因 `oci-hub-workspace.tf` 变化使进行中的 plan 失效（预期）。
- 测试：`test-hub-*.py` 中写死根名单路径的用例改为 settings 路径；`docs/admin-handbook.md:198,322-324,385,399`。

## Tasks & Acceptance

**Execution:**
- [ ] IaC Terraform：新 `employee-access.auto.tfvars.json`、删旧表/墓碑/网桥/hook/moved、变量必填、`.gitignore` -- 拆旧模型
- [ ] IaC Ansible：退役防护拆除剧本，删旧 role -- 释放 503 网络
- [ ] IaC CI/Jenkins：projection、policy、peer test、oci-hub 测试桩 -- CI 不再依赖名单文件
- [ ] IaC 文档 -- 名单位置与旧模型
- [ ] employee-admin：`roster(settings)`、retire 去提交检查、测试与手册 -- 名单读写走 employee-data
- [ ] 执行器（需授权；实现代理不做此项，也不 commit/push，只改两个工作区中的代码、测试与文档）：复制 `/srv/iac/.../oci-hub-workspaces.auto.tfvars.json` 到 settings 路径并比对哈希 → 推 employee-admin → PR 合并后推 IaC → `terraform plan -var-file=<名单>` 确认 → apply（遗忘 2 个 terraform_data，销毁 8 网桥 + 7 hook 文件，`ansible_host.employee_access` 原地更新）→ 跑拆除剧本 → `provision --vmid 503 --application`/`--email willfan@agentmail.to`

**Acceptance Criteria:**
- Given 执行器名单已复制，when 用它跑 `terraform plan`，then 只出现 15 个销毁（8 网桥 + 7 hook 文件）、2 个遗忘、`ansible_host.employee_access` 原地更新，VM500 与所有员工 VM 无变化。
- Given 拆除剧本已运行，when 在 pve2 查询，then `employee_boundary` 表与 `employee-firewall.service` 不存在，`ip link` 无 vmbr501-508。
- Given 新代码，when 跑 `wsctl status`/`publish-status`/`enforce`，then 正常读取 employee-data 名单。
- Given 以上完成，when `provision --vmid 503` 开 demo，then 开户成功且 demo 可 SSH 登录。

## Implementation Notes

- 2026-11-02 已完成：执行器名单复制到 employee-data（sha256 5ae69b62…，旧副本备份 .bak-stale-20261102）；employee-admin 14d689c、26cb3d8（检查点命令失败时输出尾部到 stderr）推到执行器；PR #221 合并（b2471a7）并推到执行器；Mac 上用执行器名单做 -target 精确 apply：1 更新 / 15 销毁 / 8 遗忘，复核全量 plan 只剩既有漂移（jenkins_agent、pnetlab、ws_executor）；拆除剧本 --check、正式执行、二次运行幂等并 verify 通过。
- AC4（demo 开户）未完成：首个检查点在 SDN 子网冲突上失败——511 尝试遗留的 oh511 占用 10.236.0.4/30。已删 oh511 与半成品 oh503 并应用 SDN。用户决定 demo 等 5.16 地址对齐完成后再开；退役遗留 oh501/oh509 归 5.23。
- 偏差：拆除剧本用 tasks 而非 role（一次性）；`tests/employee-workspace/` 保留仍在用的 login/desktop/browser 测试。

## Plan Change Log

## Review Triage Log

## Design Notes

用 `removed` 而非 `terraform state rm`：变更在代码中可审，apply 时完成遗忘，无需手工状态操作。网桥与 hook 文件真实销毁，因为已核实无 VM 引用且 verify 要求 PVE 上不再有旧网桥。

## Verification

**Commands:**
- `scripts/ci/validate-repository.sh`（或其中 terraform fmt/validate、ansible-lint、syntax-check、`tests/ci/` 子集） -- 全部通过
- `cd terraform/proxmox && terraform plan -var-file=<执行器名单副本>`（Mac，只读） -- 符合 AC1
- employee-admin：`python3 -m unittest test-hub-*.py test-wsctl.py` -- 全部通过

### Pass 1 (quick) — high 2 / medium 2 / low 2 / false 1 / maybe-false 0

| # | Finding | Verdict | Route | Evidence / action |
|---|---------|---------|-------|-------------------|
| 1 | Jenkins 部署事务 `scripts/jenkins/transaction.py:200` 全量 `terraform plan` 没有名单来源，必填变量缺失 → 所有 proxmox 部署失败 | high | intent_gap→resolved | 用户决定拆根（5.19）；5.18 期间允许失败。只链接 `peer.auto.tfvars.json`；Jenkins 拿不到 employee-data。需用户决定 Jenkins 的名单来源 |
| 2 | 投影 `public_inputs.oci_hub_workspaces: {}` 让只读 plan 预测删除全部 oci-hub VM | high | intent_gap→patched | 策略移除 `oci_hub_workspaces: {}`，peer test 断言不投影；与 #1 同根：Jenkins 无名单；peer test 断言 `{}` 固化了问题 |
| 3 | 拆除剧本 `--check` 下 `nft list` 被跳过，`rc` 未定义 | medium | patch | 已修：加 `check_mode: false` |
| 4 | `hub-onboard.py:391-393` 名单缺失回退为空表 | medium | patch | 已修：改为 `ROSTER_MISSING`，新增测试 |
| 5 | `hub-onboard.py:118` source_hash 仍列已删 role | low | patch | 已修 |
| 6 | 拆除剧本用 `tasks:` 而非 role | low | reject | 一次性拆除剧本，新建 role 只为满足形式；记录为偏差 |
| 7 | `tests/employee-workspace/` 未整体删除 | false | reject | 剩余 login/desktop/browser 测试覆盖仍在用的 `employee-workspace` role，且被 `tests/hapi-workspace/test-login-agent.py` 导入 |
