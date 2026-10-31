# ws-executor VM 部署

日期：2026-10-31。`ws-executor` 是执行器平台的专用常开 VM，只对局域网和 tailnet 开放。本次只交付 VM、Tailscale 和主机防火墙；wsctl、Semaphore 与任何凭据由后续 story 部署。

## 基本信息

| 项目 | 值 |
| --- | --- |
| 节点 | pve0 |
| VMID | 116（115 已被未纳管的 funasr 占用，不可使用） |
| IP | 192.168.1.116/24，网关 192.168.1.1，网桥 vmbr1 |
| 规格 | 2 核、4096 MB 内存、32G 系统盘（`var.storage_pool`，默认 vmdata） |
| 系统 | 从 `ubuntu-24.04-template`（pve0 VMID 9000）完整克隆，登录用户 `ubuntu` |
| Inventory | `ansible_host.ws_executor`，组 `pve_vms`（因此自动属于 `tailscale` 组） |

相关文件：

- Terraform：`terraform/proxmox/ws-executor.tf`
- 主机变量：`ansible/inventory/host_vars/ws-executor.yml`
- Playbook：`ansible/playbooks/deploy-ws-executor.yml`
- 防火墙角色：`ansible/roles/host-firewall/`

## 部署步骤

`terraform apply`、Tailscale 授权（真实运行 playbook 会用 vault 中的 auth key 加入 tailnet）均需用户分别授权。

```bash
# 1. 在 terraform/proxmox/ 中先看真实 plan，确认只新增 ws-executor 的 VM 与 ansible_host
terraform plan
terraform apply            # 获批后

# 2. 在 ansible/ 中用本检出的 .venv 部署（详见 AGENTS.md 的运行位置说明）
ansible-playbook playbooks/deploy-ws-executor.yml --syntax-check
ansible-playbook playbooks/deploy-ws-executor.yml --check --diff
ansible-playbook playbooks/deploy-ws-executor.yml
ansible-playbook playbooks/deploy-ws-executor.yml --tags verify
```

若 Ansible 提示 "no hosts matched"，先在仓库根目录运行 `./scripts/refresh-terraform-state.sh`。

重复运行 deploy 时，除 `ubuntu-vm` 角色每次都会做的 sshd 配置校验与重载（该角色有意为之，用于补救中断的运行）外，应无其他变更。

Deploy play 依次：等待 SSH 与 cloud-init 完成、确认 Ubuntu 24.04 虚拟机，然后运行 `common`、`ubuntu-vm`（guest agent、经独立密钥校验后关闭 SSH 密码登录）、`tailscale`（`tailscale_accept_dns: false`，DNS 不依赖 tailscaled）、`host-firewall`。

## 主机名

共享的 cloud-init 片段 `cloud-init-ubuntu.yml` 会覆盖 Proxmox 生成的 hostname，克隆出的 VM 默认沿用模板名 `ubuntu-24`。Deploy play 因此把主机名设为 inventory 名 `ws-executor`，并在 Tailscale 节点名不一致时执行 `tailscale set --hostname`。

## 防火墙策略

使用 ufw，由 `host-firewall` 角色管理：

- 放行：`host_firewall_allowed_cidrs`（本机为 `192.168.1.0/24`）的所有入站；`host_firewall_allowed_interfaces`（默认 `tailscale0`）的所有入站，Tailscale SSH 走这条。
- 默认：拒绝入站、允许出站。
- 启用顺序：先写放行规则，用 `ufw show added` 断言规则全部存在，然后才设置默认拒绝并启用。规则缺失时在启用前失败，首次部署经局域网连接的 Ansible 会话不会被锁在外面。

公网不可达在网络层已经成立（家中 NAT、无端口映射），主机防火墙是第二层防护。Tailscale 自己维护的 iptables 链与 ufw 共存。

## 验证

`--tags verify` 检查：

- `tailscaled` 运行，且 `tailscale status --json` 的 `BackendState` 为 `Running`（已登录）。
- `ufw status verbose` 为 `Status: active` 且 `Default: deny (incoming)`。
- `ufw show added` 中的 ufw 用户规则与预期集合完全一致。Ubuntu 默认 `before.rules`（ICMP、DHCP 客户端、mDNS）与 tailscaled 自己维护的链不在此检查内，公网不可达以下面的手动外部探测为准。

手动检查：

- 从局域网设备 `ssh ubuntu@192.168.1.116` 成功。
- 从 Tailscale 上非局域网的设备（如手机关闭 Wi-Fi）SSH 到 VM 的 tailnet 地址成功；不经 Tailscale 时无法连接。
- 从非局域网、非 tailnet 来源探测任意端口，无开放端口。

## Q&A

**问：为什么用 ufw 而不是 nftables？**
答：Ubuntu 自带、规则少、可读性好，且与 Tailscale 的 iptables 链共存。

**问：为什么不用 VMID 115？**
答：115 / 192.168.1.115 已被未纳管的 funasr 占用，本 story 不导入它。

## 执行器运行环境（story 1.5）

`ws-executor-runtime` 角色在 VM 上安装钉住版本与校验和的 Terraform、uv、bws，并建立运行目录与两个裸仓库：

| 裸仓库 | 推送后检出到 | 分支 |
| --- | --- | --- |
| `/srv/git/employee-admin.git` | `/srv/remotecc/employee-admin` | `main` |
| `/srv/git/iac.git` | `/srv/iac` | `main` |

部署代码就是 `git push`。Mac 侧远程配置（`ubuntu` 用户经 sudo 写 root 拥有的仓库）：

```bash
git remote add ws-executor ssh://ubuntu@192.168.1.116/srv/git/employee-admin.git   # 或 iac.git
git config remote.ws-executor.receivepack "sudo git-receive-pack"
git config remote.ws-executor.uploadpack "sudo git-upload-pack"
git push ws-executor HEAD:main
```

IaC 首次推送后，再跑一次 deploy playbook 会执行 `scripts/setup-dev-env.sh` 建好 `/srv/iac/.venv` 与 Ansible collections。运行数据目录 `/srv/remotecc/employee-data`（0700）由后续迁移 story 填充。
