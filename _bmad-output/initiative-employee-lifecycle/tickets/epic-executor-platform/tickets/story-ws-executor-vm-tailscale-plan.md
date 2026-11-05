---
title: 'ws-executor VM 上线并只对局域网与 Tailscale 开放'
type: 'feature'
ticket: '1'
created: '2026-10-31'
status: done
baseline_revision: '66f3d92e7f5de8075a357dca1db285fc5be0d0fe'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: ['{project-root}/AGENTS.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 执行器需要一台常开、只在内网可达的专用 VM，后续 story 会把 wsctl、凭据与 Semaphore 部署到这台 VM 上。

**Approach:** 在 pve0 上用现有 `proxmox-vm` 模块从 Ubuntu 24.04 模板克隆 `ws-executor`（VMID 116，192.168.1.116/24，2 核 4GB 32GB），并新增 Ansible 部署 playbook：基础配置、加入 Tailscale、主机防火墙默认拒绝入站，只放行局域网与 tailnet。

## Boundaries & Constraints

**Always:** 在任务 worktree `.worktrees/ws-executor-vm`（分支 `claude/ws-executor-vm`）中修改；遵循一个服务一个 `.tf` 文件（模块 + output + `ansible_host`）；Terraform 不管理 VM 电源状态，不改模块的 `ignore_changes`；`terraform apply`、Tailscale 授权、提交、推送、PR 均须用户分别授权；apply 前跑真实 `terraform plan` 并给用户看。

**Never:** 不用 VMID 115 / 192.168.1.115（已被未纳管的 funasr 占用）；不改 `group_vars/pve_vms.yml`、`inventory/groups.yml`、vault 文件或其他服务的 `.tf`；不改 tailscale 角色对其他主机的默认行为；不在本 story 安装 wsctl、Semaphore 或任何凭据；不导入 funasr 等未纳管 VM。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 局域网 SSH | 从 192.168.1.0/24 连 22 端口 | 连接成功 | 无 |
| Tailscale SSH | 从 tailnet 连接 | 连接成功 | 无 |
| 其他来源 | 非局域网、非 tailnet 来源访问任意端口 | 被丢弃 | 无 |
| 防火墙启用顺序 | 首次部署时 Ansible 经局域网连接 | 先放行局域网与 tailscale0 再启用默认拒绝，不锁死当前会话 | 规则缺失则在启用前失败 |

</frozen-after-approval>

## Code Map

- `terraform/modules/proxmox-vm/` -- 复用，不修改。默认模板 `ubuntu-24.04-template`（pve0 VMID 9000）、`vmbr1`、网关 192.168.1.1、`ciuser=ubuntu`、默认 cicustom snippet；`ignore_changes` 含 `started`、`clone`、密钥等，不改动。
- `terraform/proxmox/mcp-gateway.tf:1-28` -- 最接近的写法：模块 + `<name>_ip` output + `ansible_host`（groups `["pve_vms"]`，`ansible_user = "ubuntu"`）。
- `terraform/proxmox/pnetlab.tf:1-14` -- IP 分配确认 precondition 的现成写法，可借鉴。
- `terraform/proxmox/variables.tf:57-61` -- `var.storage_pool` 默认 `vmdata`。
- `ansible/inventory/groups.yml:11-16` -- `pve_vms` 已是 `tailscale` 的子组，自动获得 `tailscale_auth_key`（来自 `vault_tailscale_auth_key`）；不修改。
- `ansible/roles/tailscale/` -- 复用；always-on 主机按 defaults 注释设 `tailscale_accept_dns: false`，经 host_vars 设置。
- `ansible/roles/common`、`ansible/roles/ubuntu-vm` -- 复用（基础包、密钥、guest agent、关闭 SSH 密码登录）；参照 `ansible/playbooks/deploy-container-lab.yml` 的 cloud-init 等待与 Verify 写法。
- `ansible/playbooks/deploy-mcp-gateway.yml`、`deploy-caddy.yml:38-75` -- Deploy + Verify 两段式范例。
- 仓库中没有通用主机防火墙角色（只有 `unified-proxy` 的专用 iptables），需新增。
- `scripts/ci/validate-ansible.sh` -- CI 跑 YAML 解析、shell 任务探测、ansible-lint、`--syntax-check`；优先用 `command`/`argv`，避免 `shell`。

## Tasks & Acceptance

**Execution:**
- [x] `terraform/proxmox/ws-executor.tf` -- 新增 `module "ws_executor"`（pve0，VMID 116，`192.168.1.116/24`，2 核，4096MB，`32G`，`storage_pool = var.storage_pool`，`sshkeys = var.sshkeys`）、`ws_executor_ip` output 和 `ansible_host "ws_executor"`（name `ws-executor`，groups `["pve_vms"]`） -- 沿用 mcp-gateway 写法。
- [x] `ansible/inventory/host_vars/ws-executor.yml` -- `proxmox_node: pve0`、`proxmox_vmid: 116`、`tailscale_accept_dns: false`、防火墙允许来源变量 -- 主机级配置不进共享 group_vars。
- [x] `ansible/roles/host-firewall/{tasks,defaults,handlers}/main.yml` -- 用 ufw：先放行 `host_firewall_allowed_cidrs`（默认 192.168.1.0/24）与 `tailscale0` 接口入站，再设默认 deny incoming / allow outgoing 并启用；规则幂等 -- 仓库内首个通用主机防火墙。
- [x] `ansible/playbooks/deploy-ws-executor.yml` -- Deploy play：等待 cloud-init，角色 `common`、`ubuntu-vm`、`tailscale`、`host-firewall`；Verify play（`tags: [verify]`）：tailscaled 运行且已登录、ufw 启用且默认拒绝入站、只有预期的放行规则。
- [x] `docs/deployment/` 下新增 `YYYY-MM-DD-ws-executor.md`（中文）-- 记录 VMID/IP、部署命令、防火墙策略与验证方法。

**Acceptance Criteria:**
- Given 已批准的 apply，when 运行 `terraform plan`，then 只新增 ws-executor 一台 VM 及其 ansible_host，不改其他资源；apply 后再次 plan 无变化。
- Given 部署完成，when 从局域网和 Tailscale 分别 SSH，then 都能登录；when 从局域网外、非 tailnet 来源探测任意端口，then 无开放端口。
- Given 重复运行 deploy playbook，then 除 `ubuntu-vm` 的 sshd 校验与重载外无其他变更，Verify play 通过。（2026-10-31 用户选 A 修订）

## Implementation Notes

- host-firewall 只建了 `tasks/` 与 `defaults/`：ufw 模块即时生效，没有需要通知的 handler，按 AGENTS.md 省略空目录。
- 启用默认拒绝前用 `ufw show added` 断言放行规则全部存在（矩阵“规则缺失则在启用前失败”）。
- cloud-init 断言只要求 `done` 且无 errors，不照抄 container-lab 针对 26.04 的 DEPRECATED 白名单。
- Terraform 未加 IP 分配 precondition，保证 plan 只新增 VM 与 ansible_host 两类资源。
- 已知风险：复用的 `ubuntu-vm` 角色有一个 `changed_when: true` 的 sshd 校验任务，重复运行总会报 1 个 changed，与“幂等无变更”验收冲突；按范围未修改该共享角色。

## Plan Change Log

- 2026-10-31 评审 pass 1：验收 3 与共享角色 `ubuntu-vm` 有意的 sshd 重载冲突，用户选 A，验收改为"除 ubuntu-vm 的 sshd 校验外无变更"。KEEP：防火墙先放行后默认拒绝的顺序、VMID 116。

## Review Triage Log

- Pass 1 (quick): high 0 / medium 2 / low 2 / false 0 / maybe-false 0
  - medium — 验收 3（重复运行无变更）不成立：共享角色 `ubuntu-vm` 的 "Validate and schedule reload of complete SSH configuration" 有意写成 `changed_when: true` 并通知重载（注释说明用于补救中断的运行），每次重复运行至少 1 个 changed。route: intent_gap（修复要么改共享角色的有意行为、要么去掉该角色、要么改验收口径，计划未定），待人决定。
  - low — `terraform/proxmox/.terraform.lock.hcl` 被 `terraform init` 加入 darwin_arm64 的 h1 哈希，超出改动范围。route: patch（撤回该文件）。
  - medium — Verify play 重复写防火墙角色的默认值与预期规则推导（`default(['tailscale0'])`），只改角色 defaults 时 Deploy 与 Verify 会分叉。route: patch（预期规则移入角色，Verify 经角色的 verify 任务执行）。
  - low — Verify 只检查 ufw 用户规则；Ubuntu `before.rules` 的 ICMP/DHCP/mDNS 与 tailscaled 自身端口不在检查内，文档"没有多余放行"说法过度。route: patch（修正文档与断言措辞，公网不可达仍靠手动外部探测）。

## Design Notes

用 ufw 而不是 nftables：Ubuntu 自带、规则少、可读性好；Tailscale 自己维护的 iptables 链与 ufw 共存。为防止首次部署把 Ansible 会话锁在外面，放行规则必须在启用默认拒绝之前写入，Verify 再检查一次。公网不可达在网络层已经成立（家中 NAT、无端口映射），主机防火墙是第二层。

## Verification

**Commands:**
- `cd terraform/proxmox && terraform fmt -check && terraform validate && terraform plan` -- expected: 只新增 ws-executor 相关资源
- `cd ansible && ../.venv/bin/ansible-playbook playbooks/deploy-ws-executor.yml --syntax-check` -- expected: 通过
- `cd ansible && ../.venv/bin/ansible-lint -c .ansible-lint playbooks/deploy-ws-executor.yml roles/host-firewall` -- expected: 无错误
- `cd ansible && ../.venv/bin/ansible-playbook playbooks/deploy-ws-executor.yml --tags verify` -- expected: 全部通过（apply 与部署获批之后）

**Manual checks (if no CLI):**
- 从 Tailscale 上非局域网的设备（如手机关闭 Wi-Fi）SSH 到 VM 成功；不经 Tailscale 时无法连接。
