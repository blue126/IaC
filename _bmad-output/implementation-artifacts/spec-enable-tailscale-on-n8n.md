---
title: 'Enable Tailscale on n8n'
type: 'bugfix'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 0
baseline_commit: '701ea6e9bc69dc5a09ceb4994f5913189081bbb8'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `n8n` LXC（`192.168.1.106`）没有安装或运行 Tailscale。虽然它已通过 `pve_lxc` 属于 `tailscale` inventory 组，但缺少 Tailscale role 配置 LXC TUN passthrough 所需的 Proxmox 节点和 VMID 元数据。

**Approach:** 按现有 LXC inventory 模式为 `n8n` 补充 `proxmox_node: pve0` 和 `proxmox_vmid: 106`，然后仅对 `n8n` 运行 Tailscale playbook，并验证 TUN、服务状态及 Tailscale IPv4。

## Boundaries & Constraints

**Always:** 所有部署命令必须使用 `--limit n8n`；先完成本地语法检查；部署后验证 `/dev/net/tun`、`tailscaled` active/enabled 状态和 `tailscale ip -4`；不得输出 Vault auth key。

**Ask First:** 如果需要修改除 `ansible/inventory/host_vars/n8n.yml` 以外的持久化配置，或认证失败需要更换 auth key，先停止并向用户说明。

**Never:** 不向其他 `tailscale` 组成员部署；不使用一次性 extra-vars 绕过 inventory 缺失；本次不设计或实现所有新节点的统一部署流程；不提交 Git commit。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 首次安装 | n8n 无 TUN、无 Tailscale | pve0 写入 LXC 106 TUN 配置、重启容器、安装并认证 Tailscale | 任一任务失败即停止，不扩大部署范围 |
| 认证失败 | Vault auth key 过期或不可复用 | 不泄漏 auth key，不宣称部署成功 | 停止并请求用户处理 auth key |
| 重复执行 | TUN 和 Tailscale 已就绪 | role 安全重跑，不重复修改 LXC 配置 | 检查 changed 结果及最终服务状态 |

</frozen-after-approval>

## Code Map

- `ansible/inventory/host_vars/n8n.yml` -- 待新增；提供 role 配置 LXC TUN 所需的 `proxmox_node` 和 `proxmox_vmid`。
- `ansible/roles/tailscale/tasks/main.yml:2` -- 使用两个幂等 `lineinfile` 任务确保 TUN 配置存在，实际变化时才重启 LXC。
- `ansible/roles/tailscale/tasks/main.yml:76` -- 设置 IPv4 forwarding；LXC 不执行会加载无权限内核参数的全量 sysctl reload，之后安装客户端、执行 `tailscale up` 并读取 IPv4。
- `ansible/playbooks/install-tailscale.yml` -- 只读复用；目标为 `tailscale` 组，因此执行时必须限定 `n8n`。
- `ansible/inventory/host_vars/anki.yml`、`homepage.yml`、`caddy.yml` -- 现有 LXC 元数据模式参考。
- `terraform/proxmox/n8n.tf:4` -- 只读事实来源；确认目标节点 `pve0` 和 VMID `106`。

## Tasks & Acceptance

**Execution:**
- [x] `ansible/inventory/host_vars/n8n.yml` -- 新增 `proxmox_node: pve0` 和 `proxmox_vmid: 106`，使 Tailscale role 可持久化配置 TUN。
- [x] `ansible/roles/tailscale/tasks/main.yml` -- LXC 跳过全量 sysctl reload，同时保留目标参数的即时设置；避免非特权容器因无权设置 `kernel.printk` 而中断。
- [x] `ansible/playbooks/install-tailscale.yml` -- 先 syntax-check，再用 `--limit n8n` 部署；不修改 playbook 本身。
- [x] n8n 与 pve0 -- 验证 LXC 配置、TUN 设备、tailscaled 服务和分配的 IPv4。

**Acceptance Criteria:**
- Given n8n inventory 已加载新增 host vars, when 查询变量, then `proxmox_node` 为 `pve0` 且 `proxmox_vmid` 为 `106`。
- Given 限定 n8n 执行安装 playbook, when role 完成, then `/dev/net/tun` 存在且 `tailscaled` 为 enabled 和 active。
- Given tailscaled 已认证, when 执行 `tailscale ip -4`, then 返回一个有效的 Tailscale IPv4 地址。
- Given 部署命令带 `--limit n8n`, when 执行 playbook, then 其他 inventory 主机不发生变更。

## Spec Change Log

## Verification

**Commands:**
- `ansible-playbook playbooks/install-tailscale.yml --syntax-check --limit n8n` -- expected: playbook syntax valid。
- `ansible n8n -m debug -a "var=proxmox_node"` 与 `var=proxmox_vmid` -- expected: `pve0` 与 `106`。
- `ansible-playbook playbooks/install-tailscale.yml --limit n8n` -- expected: 仅 n8n 完成安装和认证。
- `ansible pve0 --become -m command -a "pct config 106"` -- expected: 包含 TUN device allow 与 mount entry。
- `ansible n8n --become -m stat -a "path=/dev/net/tun"` -- expected: `exists: true`。
- `ansible n8n --become -m command -a "systemctl is-enabled tailscaled"` 与 `systemctl is-active tailscaled` -- expected: `enabled` 与 `active`。
- `ansible n8n --become -m command -a "tailscale ip -4"` -- expected: 返回有效 IPv4。

## Suggested Review Order

**LXC TUN 与 sysctl**

- 用幂等单行配置替代易产生重复项的 marker block。
  [`main.yml:2`](../../ansible/roles/tailscale/tasks/main.yml#L2)

- LXC 只设置目标参数，不全量加载无权限内核参数。
  [`main.yml:76`](../../ansible/roles/tailscale/tasks/main.yml#L76)

**n8n 主机映射**

- 提供 TUN 配置委派所需的节点和 VMID。
  [`n8n.yml:1`](../../ansible/inventory/host_vars/n8n.yml#L1)
