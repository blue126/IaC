---
title: 'Retire legacy Claude Agent and Claude Desktop guests'
type: 'chore'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 1
baseline_commit: '312887a2613f4ce946c24ebe707f53bd2bfe0257'
context:
  - '{project-root}/docs/specs/backup-architecture-consolidation-spec.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** pve0 上的 Ubuntu LXC 109 `claude-agent` 已无用途；手工 Windows VM 110 `claude-desktop` 将由 pve1 Windows Server 112 上的人工安装取代。继续保留会浪费资源并扩大 IaC、备份与运维表面。

**Approach:** 不等待 Windows 迁移完成，立即永久退役 109/110；109 由既有 Terraform state 精确销毁，非 Terraform 管理的 110 由 Proxmox 优雅关机后手工销毁；随后删除两者全部 PBS 快照与 backup groups，最后清理仓库与活动备份作业。

## Boundaries & Constraints

**Always:** 删除前精确核对 PBS 目标只能是 `ct/109` 与 `vm/110`；109 使用只包含其 container 与 ansible_host 两个 delete action 的 saved Terraform plan；110 必须核对全部 attached/unused disk 与 passthrough 后由 guest OS 优雅关机，再执行不带 `--purge` 与 `--destroy-unreferenced-disks` 的精确 `qm destroy 110`；两台实体消失后删除其 PBS backup groups并从备份作业移除；更新 source-of-truth 与当前架构文档。

**Ask First:** 任一实例无法优雅关机；Terraform destroy plan出现其他地址、非 delete action 或身份不符；发现未审计 mount/passthrough/orphan disk；PBS 删除命令的目标无法精确限定为 `ct/109` 与 `vm/110`。

**Never:** 不强制停止；不使用 `terraform state rm`、普通全量 apply、`qm destroy --purge` 或 `--destroy-unreferenced-disks`；不删除 109/110 之外的 PBS snapshot/group；不删除历史事故与学习记录；不自动提交或 push。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Backup cleanup | 109/110 各有两份现有快照 | 仅删除 `ct/109` 与 `vm/110` 的全部快照及 groups | 目标不精确即停止 |
| Terraform retirement | 109 state 身份与实机一致 | saved plan 仅删除 container 与 ansible_host | 任何额外变化均不 apply |
| Manual VM retirement | 110 正常运行且只有已审计磁盘 | guest OS 优雅关机后精确删除 VM与 attached disks | shutdown 超时则停止，不强停 |
| Repository cleanup | 两台实体已不存在 | 109/110 不再出现在活动 Terraform/Ansible/backup 配置 | 历史事实保留并标注已退役 |

</frozen-after-approval>

## Code Map

- `terraform/proxmox/claude-agent.tf` -- Terraform 管理的 109 LXC、output 与动态 Ansible host。
- `ansible/playbooks/deploy-claude-agent.yml` -- 109 部署与人工配对流程。
- `ansible/roles/claude-agent/` -- 109 Linux systemd/tmux/Telegram Agent role。
- `ansible/inventory/host_vars/claude-agent.yml` -- 109 host 配置。
- `ansible/roles/pbs-client/defaults/main.yml` -- pve0 活动备份 VMID 白名单。
- `docs/designs/homelab-iac-architecture.md` -- 当前拓扑与备份集合。
- `docs/specs/backup-architecture-consolidation-spec.md` -- 当前退役状态与历史决策。

## Tasks & Acceptance

**Execution:**
- [x] PBS -- 实体删除后精确删除 `ct/109`、`vm/110` 的全部快照与 backup groups，不影响其他备份。
- [x] `terraform/proxmox/claude-agent.tf` -- 删除定义，生成/审计/apply只含两个 delete action 的 saved plan，优雅关闭并由 Terraform销毁 109。
- [x] pve0 VM 110 -- 审计配置与磁盘，优雅关闭后以不带 purge/unreferenced flags 的 `qm destroy 110` 删除。
- [x] `ansible/playbooks/deploy-claude-agent.yml`, `ansible/roles/claude-agent/`, `ansible/inventory/host_vars/claude-agent.yml` -- 删除已退役自动化。
- [x] `ansible/roles/pbs-client/defaults/main.yml` -- 实体删除后移除 109/110，部署活动备份作业并精确核对 VMID 集合为 100–107。
- [x] 当前架构/备份文档 -- 标记 109/110 与对应 PBS 恢复点均已删除；保留历史事故事实。

**Acceptance Criteria:**
- Given 109/110 已退役，when 查询 pve0 与 Terraform state，then 两个 guest 和 109 两个对应 state 地址均不存在。
- Given PBS 备份也需退役，when 清理完成后查询，then `ct/109` 与 `vm/110` 不再存在且其他 backup groups 不变。
- Given 活动备份范围已收缩，when读取 `/cluster/backup`，then VMID 精确为 100–107且 storage/schedule/mode/prune 参数未漂移。
- Given仓库清理完成，when运行 Terraform validate、Ansible syntax/inventory与 `rg`，then现行源码无 109/110 Claude 配置且历史记录保留。

## Spec Change Log

- 2026-08-12：完成 109/110 guest、PBS 恢复点、活动备份作业与仓库配置清理；生产与静态验收通过。

## Design Notes

用户明确接受不等待 Windows Server 112 安装完成即删除旧 guests、不做完整恢复演练，并删除 109/110 的全部 PBS 恢复点。完成后两项工作负载没有仓库内或 PBS 回退路径。

109 的代码删除与 saved plan必须在同一变更窗口完成。110 保持非 Terraform ownership，使用 Proxmox原生命令精确删除，不先 import制造临时 state。guest 与 PBS group均删除后无法恢复；shutdown 后、destroy/apply 前仍可重新启动。

## Verification

**Commands:**
- `terraform fmt -check -recursive && terraform validate` -- Terraform 配置有效。
- `terraform show retire-109.tfplan` -- 仅两个目标地址执行 delete。
- `ansible-playbook playbooks/setup-pbs-backup.yml --syntax-check` -- PBS playbook 可解析。
- `ansible-inventory --graph` -- 无 `claude-agent` host。
- `pvesh get /cluster/backup --output-format json` -- 活动作业 VMID 精确为 100–107。
- `pvesm list pbs-backup --vmid 109/110` -- 两者不再返回任何备份，其他 backup groups仍存在。
- `git diff --check` 与定向 `rg` -- 无格式错误或活动配置残留。
