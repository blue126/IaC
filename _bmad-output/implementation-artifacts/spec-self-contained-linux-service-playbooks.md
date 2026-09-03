---
title: 'Make Linux service playbooks self-contained'
type: 'refactor'
created: '2026-08-26'
status: 'in-review'
review_loop_iteration: 0
baseline_commit: '701ea6e9bc69dc5a09ceb4994f5913189081bbb8'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 新建 Linux 节点触发 `deploy-<service>.yml` 时，大多数服务 playbook 只部署业务 role，遗漏 `common` 和 `tailscale`。因此节点可能在服务可用时仍缺少通用基线或 Tailscale，例如本次 n8n 事件。

**Approach:** 让每个常规 Linux 服务 playbook 自包含基础依赖，按 `common -> tailscale -> service` 顺序运行。扩展 `common` 对 Alpine 的安全支持，并为 Jenkins LXC 补齐 TUN 配置所需元数据。保留已退役、OCI 专用、Windows/ESXi 宿主机和 inventory 不完整的入口不变。

## Boundaries & Constraints

**Always:** 仅变更缺少 `common` 或 `tailscale` 的常规 Linux 服务入口；基础 roles 必须在业务 role 之前；为依赖 facts 的 LLM playbook 开启 facts；Caddy 保持既有 SSH/Python bootstrap 顺序；Tailscale role 继续只在 LXC 元数据存在时配置 TUN；所有受影响 playbook 必须通过 syntax-check。

**Ask First:** 若检查发现其他 LXC 缺少 `proxmox_node` 或 `proxmox_vmid`，或需要恢复 PBS inventory/调整 OCI、Windows、ESXi 宿主机配置，停止并向用户确认。

**Never:** 不改 `site.yml`、`install-tailscale.yml`、Jenkins 自动部署映射或 Terraform 动态 inventory 架构；不修改 `deploy-llm-server.yml`、OCI 专用 playbook、PBS playbook；不部署到任何远端节点；不提交 Git commit，直到所有本轮 Ansible 修改完成后由用户指定提交到 `main`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Debian/Ubuntu service | 服务 playbook 缺少基础 roles | `common`、`tailscale` 在业务 role 前执行 | syntax-check 失败则停止，不能部署 |
| Alpine Caddy LXC | Caddy 缺少基础 roles | common 使用可用包管理器，Tailscale 在 Caddy 前执行 | 保留现有 bootstrap，不能使用 apt-only 任务 |
| ESXi Linux VM | LLM playbook 禁用 facts | facts 启用后安全执行 common/tailscale | 不对 ESXi 宿主机执行 |
| Jenkins LXC | 加入 tailscale 但缺少 Proxmox 元数据 | inventory 提供 pve0/VMID，role 可配置 TUN | 元数据不完整则不加入 role |
| PBS | `pbs` 不在 inventory | playbook 保持不变 | 不猜测或创建主机定义 |

</frozen-after-approval>

## Code Map

- `ansible/roles/common/tasks/main.yml:2` -- 当前仅使用 Debian apt 且无条件依赖 sudoers；需让 Alpine 路径可安全执行。
- `ansible/roles/tailscale/tasks/main.yml:90` -- 未连接时使用 auth key 认证；已连接节点使用非破坏性 `tailscale set` 同步 SSH/DNS 偏好，避免服务重跑重置网络配置。
- `ansible/inventory/host_vars/jenkins.yml` -- 待新增 Jenkins LXC 的 pve0/VMID 元数据，供 cloudflared 与 gitea playbook 使用。
- `ansible/playbooks/deploy-cloudflared.yml`、`deploy-gitea.yml`、`deploy-jenkins.yml` -- Jenkins 服务入口，补齐缺少的 tailscale role。
- `ansible/playbooks/deploy-immich.yml`、`deploy-n8n.yml`、`deploy-netbox.yml`、`deploy-rustdesk.yml`、`deploy-anki-sync-server.yml` -- Proxmox Linux 服务入口，补齐基础 roles。
- `ansible/playbooks/deploy-homepage.yml` -- 已有 tailscale，仅补 common。
- `ansible/playbooks/deploy-caddy.yml` -- Alpine LXC bootstrap 后补齐 common/tailscale。
- `ansible/playbooks/deploy-qwen36.yml`、`deploy-deepseek-v4.yml`、`deploy-deepseek-v4-ik.yml`、`deploy-deepseek-v4-mainline.yml` -- llm-server Linux VM 服务入口，启用 facts 并补齐基础 roles。
- `ansible/playbooks/deploy-pbs.yml`、`deploy-anki-oci.yml`、`deploy-unified-proxy.yml`、`deploy-llm-server.yml` -- 只读排除项：分别为 inventory 缺失、OCI 专用或退役入口。

## Tasks & Acceptance

**Execution:**
- [x] `ansible/roles/common/tasks/main.yml` -- 以操作系统适配方式安装基线包，并仅在 sudo/visudo 可用时配置 sudoers，使 Debian 与 Alpine 都能安全执行。
- [x] `ansible/inventory/host_vars/jenkins.yml` -- 新增 Jenkins 的 Proxmox 节点和 LXC VMID。
- [x] `ansible/playbooks/deploy-{cloudflared,gitea,jenkins,immich,n8n,netbox,rustdesk,anki-sync-server,homepage,caddy,qwen36,deepseek-v4,deepseek-v4-ik,deepseek-v4-mainline}.yml` -- 在每个 Deploy play 中加入缺少的基础 roles，且不重复已存在角色；LLM play 启用 facts。
- [x] `ansible/roles/tailscale/tasks/main.yml` 与 `ansible/playbooks/deploy-deepseek-v4.yml` -- 将已连接节点改用非破坏性偏好同步，并在任何 role 前拒绝无操作 DeepSeek 调用。
- [x] `ansible/playbooks/deploy-pbs.yml` 与 OCI/退役入口 -- 保持不变。

**Acceptance Criteria:**
- Given 任一纳入范围的 Linux 服务 playbook, when 检查其 Deploy play, then 在业务 role 之前包含 `common` 和 `tailscale` 各一次。
- Given Caddy 是 Alpine, when 执行 common role, then 不调用 apt 或不存在的 sudoers 校验程序。
- Given 任一 llm-server 服务 playbook, when 执行基础 roles, then Ansible facts 已启用且不触发 LXC 专用 TUN 分支。
- Given Jenkins 服务 playbook, when Tailscale role 运行, then inventory 解析 `proxmox_node: pve0` 与正确 VMID。
- Given PBS、OCI 专用和退役入口, when 比对本次 diff, then 这些 playbook 未被修改。

## Spec Change Log

## Verification

**Commands:**
- `ansible-playbook playbooks/deploy-*.yml --syntax-check` -- expected: all affected playbooks parse successfully.
- `ansible-inventory --host jenkins` -- expected: exposes Jenkins Proxmox node and VMID.
- `ansible-inventory --host caddy` -- expected: resolves Caddy as an LXC target without changing its bootstrap play.
- `git diff --check` -- expected: no whitespace errors.
