# 学习笔记：Ansible Vault 架构设计与标准化重构

**日期**: 2026-01-31
**标签**: #Ansible #Vault #Security #Refactoring #Architecture

随着 Homelab 服务不断增加（从最初的 3 个到现在的 7+ 个），Vault 的使用方式逐渐出现了不一致。本次对整个 Vault 架构进行了全面审计和标准化重构。

---

## 1. 背景：从简单使用到架构混乱

项目早期（2025-12）引入 Ansible Vault 时，只有几个变量，随意放置即可。但随着服务增加，密码管理出现了三个问题：

1. **明文密码残留** — `group_vars/pve_vms.yml` 中的 `ansible_ssh_pass: ubuntu`、`host_vars/immich.yml` 中的 `immich_db_password: admin`、`host_vars/anki.yml` 中的 `anki_sync_users: ["anki:anki"]`
2. **间接引用模式不一致** — 有的 vault 变量在 group_vars 中做别名，有的在 host_vars 中，有的在 role defaults 中，还有一个在 playbook vars 中，没有明确规则
3. **缺乏文档** — 新增服务时不知道该把 vault 引用放在哪里，全凭个人判断

## 2. 架构审计：发现了什么

对整个项目做了一次全面审计，扫描了所有 `vault_` 变量的定义和引用链。

### 2.1 明文密码（3 处）

| 文件 | 变量 | 明文值 |
|------|------|--------|
| `group_vars/pve_vms.yml` | `ansible_ssh_pass`, `ansible_become_password`, `vm_cipassword` | `ubuntu` |
| `host_vars/immich.yml` | `immich_db_password` | `admin` |
| `host_vars/anki.yml` | `anki_sync_users` | `["anki:anki"]` |

虽然都是弱密码（cloud-init 默认值、开发用密码），但明文出现在 git 仓库中仍然不好。

### 2.2 间接引用的 4 种模式

审计发现项目中同时使用了 4 种不同的间接引用机制：

| 模式 | 位置 | 使用者 |
|------|------|--------|
| group_vars | `inventory/group_vars/tailscale.yml` | tailscale |
| group_vars (无消费者) | `inventory/group_vars/oci.yml` | OCI（仅 Terraform 用） |
| host_vars | `inventory/host_vars/homepage.yml` | homepage |
| role defaults | `roles/pbs/defaults/main.yml` 等 | pbs, pbs_client, caddy |
| ~~playbook vars~~ | ~~`playbooks/deploy-caddy.yml`~~ | ~~caddy（已修复）~~ |

其中 playbook vars 的方式是最不合适的 —— 在修复前 caddy 的 `cloudflare_api_token` 是唯一一个在 playbook `vars:` 中做间接引用的变量。

### 2.3 其他发现

- `vault_proxmox_password` 没有任何 Ansible 消费者，纯粹给 Terraform 用
- `netbox_api_token` 在 homepage role defaults 中定义为空字符串，但从未在 vault 或 inventory 中赋值（未完成功能）
- `legacy_inventory_backup/` 中有过期的重复引用

## 3. 核心概念：Ansible 变量优先级

理解变量优先级是做架构决策的基础。Ansible 的变量优先级链（从低到高）：

```
role defaults          ← 最低优先级
group_vars/all
group_vars/<group>
host_vars/<host>
play vars              ← 较高优先级
extra vars (--extra-vars)  ← 最高优先级
```

这意味着：
- **role defaults 中的值会被 group_vars / host_vars 覆盖** — 所以在 role defaults 中放 `"{{ vault_xxx }}"` 时，如果 host_vars 中也定义了同名变量（比如之前 immich 的情况），host_vars 的值会"赢"
- **playbook `vars:` 优先级高于 host_vars** — 如果在 playbook vars 中做间接引用，会阻止 host_vars 的覆盖能力，破坏了 Ansible 的分层设计
- **`--extra-vars` 是终极覆盖** — 适合临时调试，不适合常规使用

### 为什么 playbook `vars:` 不适合做间接引用？

```yaml
# ❌ 不好：playbook vars 优先级太高，阻止了 host_vars 覆盖
- name: Deploy Caddy
  hosts: caddy
  vars:
    cloudflare_api_token: "{{ vault_cloudflare_api_token }}"
  roles:
    - caddy

# ✅ 好：放在 role defaults，允许 inventory 层覆盖
# roles/caddy/defaults/main.yml
cloudflare_api_token: "{{ vault_cloudflare_api_token }}"
```

## 4. 重构后的 Vault 架构（核心章节）

### 4.1 单一 Vault 文件

```
ansible/
├── .vault_pass                              # 解密密码（gitignored）
├── ansible.cfg                              # vault_password_file = .vault_pass
└── inventory/
    └── group_vars/
        └── all/
            └── vault.yml                    # 唯一的加密文件，所有主机自动继承
```

**命名约定**: 所有 vault 变量使用 `vault_` 前缀。消费侧变量去掉前缀。

#### 当前 Vault 变量清单（18 个）

| 分组 | 变量 | 消费方 |
|------|------|--------|
| **Homepage** | `vault_proxmox_api_password_homepage` | Ansible (host_vars → homepage role) |
| | `vault_tailscale_api_key_homepage` | Ansible (host_vars → homepage role) |
| | `vault_immich_api_key_homepage` | Ansible (host_vars → homepage role) |
| **OCI** | `vault_oci_tenancy_ocid` | Terraform (get-secrets.sh) + Ansible (group_vars 预留) |
| | `vault_oci_user_ocid` | 同上 |
| | `vault_oci_fingerprint` | 同上 |
| | `vault_oci_private_key_path` | 同上 |
| **Proxmox** | `vault_proxmox_password` | Terraform-only (get-secrets.sh) |
| | `vault_proxmox_api_token_id` | Terraform + Ansible (pbs_client role defaults) |
| | `vault_proxmox_api_token_secret` | Terraform + Ansible (pbs_client role defaults) |
| **Tailscale** | `vault_tailscale_auth_key` | Ansible (group_vars → tailscale role) |
| **PBS** | `vault_pbs_root_password` | Ansible (role defaults → pbs role) |
| | `vault_pbs_backup_user_password` | Ansible (role defaults → pbs role) |
| | `vault_pbs_api_token_value` | Ansible (role defaults → pbs_client role) |
| **VM 默认凭证** | `vault_vm_default_password` | Ansible (group_vars → pve_vms 组) |
| **Immich** | `vault_immich_db_password` | Ansible (role defaults → immich role) |
| **Anki** | `vault_anki_sync_users` | Ansible (role defaults → anki role) |
| **Cloudflare** | `vault_cloudflare_api_token` | Ansible (role defaults → caddy role) |

### 4.2 间接引用模式选择规则

**核心原则：按变量的作用域选择模式。**

| 作用域 | 模式 | 别名位置 | 实际案例 |
|--------|------|----------|----------|
| 主机特定的密码 | Pattern A | `host_vars/<host>.yml` | homepage 的 3 个 API key |
| 组级别共享的密码 | Pattern A | `group_vars/<group>.yml` | tailscale_auth_key, vm_default_password |
| Role 配置参数型密码 | Pattern B | `roles/<role>/defaults/main.yml` | caddy, pbs, pbs_client, immich, anki |
| Terraform-only 密码 | 不建别名 | 仅在 vault 中 | vault_proxmox_password |

#### Pattern A: Inventory 层别名

```
vault.yml                          group_vars 或 host_vars              role
┌─────────────────────┐     ┌──────────────────────────┐     ┌──────────────────┐
│ vault_tailscale_    │ ──> │ group_vars/tailscale.yml │ ──> │ tailscale role   │
│   auth_key: "tskey" │     │ tailscale_auth_key:      │     │ 使用变量         │
│                     │     │   "{{ vault_... }}"      │     │ tailscale_auth_  │
└─────────────────────┘     └──────────────────────────┘     │   key            │
                                                             └──────────────────┘
```

**适用场景**：
- 同一个 vault 变量可能被不同主机/组用不同值覆盖
- 变量语义上属于"某台主机的配置"或"某个组的共享配置"

**优点**: 灵活、可覆盖、role 可移植
**缺点**: 间接层更多、文件更分散

#### Pattern B: Role Defaults 层别名

```
vault.yml                          role defaults                         role tasks
┌─────────────────────┐     ┌──────────────────────────┐     ┌──────────────────┐
│ vault_cloudflare_   │ ──> │ caddy/defaults/main.yml  │ ──> │ caddy tasks      │
│   api_token: "5Ly"  │     │ cloudflare_api_token:    │     │ 使用变量         │
│                     │     │   "{{ vault_... }}"      │     │ cloudflare_api_  │
└─────────────────────┘     └──────────────────────────┘     │   token          │
                                                             └──────────────────┘
```

**适用场景**：
- 变量是 role 的配置参数，不区分主机/组
- 只有一个实例在用（Homelab 常见情况）

**优点**: 简单直接、自包含、看 role defaults 就知道需要哪些 vault 变量
**缺点**: role 耦合 vault 命名

#### 为什么混用是合理的？

不是偷懒，而是**语义匹配**：
- `tailscale_auth_key` 是"加入 tailscale 网络的所有机器共享的密钥" → 放 group_vars 语义正确
- `homepage` 的 3 个 API key 是"只有 homepage 这台机器用的" → 放 host_vars 语义正确
- `cloudflare_api_token` 是"caddy 这个 role 的配置参数" → 放 role defaults 语义正确

强制统一到一种模式反而会丢失语义信息。

### 4.3 Terraform 桥接机制

Ansible Vault 是**唯一的密码源**。Terraform 不直接存储密码，而是通过桥接脚本同步：

```
ansible/inventory/group_vars/all/vault.yml
            │
            │  scripts/get-secrets.sh (解密 + 提取)
            │
            ├──> terraform/proxmox/secrets.auto.tfvars
            │      pm_password = "Admin123..."
            │      pm_api_token_id = "root@pam!terraform"
            │      pm_api_token_secret = "e095389a-..."
            │
            └──> terraform/oci/secrets.auto.tfvars
                   tenancy_ocid = "ocid1.tenancy..."
                   user_ocid = "ocid1.user..."
                   fingerprint = "6c:eb:39:..."
                   private_key_path = "/home/will/.oci/..."
```

**变量分类**：
- **Terraform-only**: `vault_proxmox_password` — 没有 Ansible 消费者
- **共享**: `vault_proxmox_api_token_id/secret` — Terraform 和 Ansible (pbs_client) 都用
- **Ansible-only**: 其余 13 个 — Terraform 不需要

**工作流**: 新增密码时，先加到 vault.yml，然后运行 `get-secrets.sh` 同步到 Terraform。

### 4.4 完整变量流向总图

```
vault.yml (18 个变量)
│
├── Pattern A: Inventory 层别名
│   ├── host_vars/homepage.yml
│   │   ├── proxmox_api_password ← vault_proxmox_api_password_homepage
│   │   ├── tailscale_api_key   ← vault_tailscale_api_key_homepage
│   │   └── immich_api_key      ← vault_immich_api_key_homepage
│   │         └──> homepage role (templates/services.yaml.j2 等)
│   │
│   ├── group_vars/tailscale.yml
│   │   └── tailscale_auth_key  ← vault_tailscale_auth_key
│   │         └──> tailscale role (tasks/main.yml)
│   │
│   ├── group_vars/pve_vms.yml
│   │   ├── ansible_ssh_pass       ← vault_vm_default_password
│   │   ├── ansible_become_password ← vault_vm_default_password
│   │   └── vm_cipassword          ← vault_vm_default_password
│   │         └──> SSH 连接 + cloud-init
│   │
│   └── group_vars/oci.yml (预留，当前仅 Terraform 通过 get-secrets.sh 消费)
│       ├── oci_tenancy_ocid    ← vault_oci_tenancy_ocid
│       ├── oci_user_ocid       ← vault_oci_user_ocid
│       ├── oci_fingerprint     ← vault_oci_fingerprint
│       └── oci_private_key_path ← vault_oci_private_key_path
│
├── Pattern B: Role Defaults 层别名
│   ├── roles/caddy/defaults/main.yml
│   │   └── cloudflare_api_token ← vault_cloudflare_api_token
│   │         └──> caddy role (tasks/main.yml, environment variable)
│   │
│   ├── roles/pbs/defaults/main.yml
│   │   ├── pbs_root_password        ← vault_pbs_root_password
│   │   └── pbs_backup_user_password ← vault_pbs_backup_user_password
│   │         └──> pbs role (tasks/users.yml)
│   │
│   ├── roles/pbs_client/defaults/main.yml
│   │   ├── pbs_api_token_value      ← vault_pbs_api_token_value
│   │   ├── proxmox_api_token_id     ← vault_proxmox_api_token_id
│   │   └── proxmox_api_token_secret ← vault_proxmox_api_token_secret
│   │         └──> pbs_client role (tasks/storage.yml, tasks/pbs-token.yml)
│   │
│   ├── roles/immich/defaults/main.yml
│   │   └── immich_db_password ← vault_immich_db_password
│   │         └──> immich role (templates/env.j2)
│   │
│   └── roles/anki/defaults/main.yml
│       └── anki_sync_users ← vault_anki_sync_users
│             └──> anki role (templates/anki-sync-server.service.j2)
│
├── Terraform 桥接 (scripts/get-secrets.sh)
│   ├── vault_proxmox_password      → pm_password (proxmox/secrets.auto.tfvars)
│   ├── vault_proxmox_api_token_id  → pm_api_token_id
│   ├── vault_proxmox_api_token_secret → pm_api_token_secret
│   └── vault_oci_*                 → oci/secrets.auto.tfvars
│
└── 无别名 (Terraform-only)
    └── vault_proxmox_password — 仅 get-secrets.sh 消费
```

## 5. 重构过程记录

### 本次变更清单

| 步骤 | 文件 | 变更内容 |
|------|------|----------|
| 1 | `vault.yml` | 新增 `vault_vm_default_password`, `vault_immich_db_password`, `vault_anki_sync_users` |
| 2 | `group_vars/pve_vms.yml` | 3 个明文密码 → `"{{ vault_vm_default_password }}"` |
| 3 | `roles/immich/defaults/main.yml` | `immich_db_password: admin` → `"{{ vault_immich_db_password }}"` |
| 4 | `host_vars/immich.yml` | 删除 `immich_db_password` 行（role defaults 接管） |
| 5 | `roles/anki/defaults/main.yml` | `anki_sync_users: ["user:pass"]` → `"{{ vault_anki_sync_users }}"` |
| 6 | `host_vars/anki.yml` | 删除 `anki_sync_users` 行（role defaults 接管） |
| 7 | `AGENTS.md` | 新增 Vault Architecture 章节 |

### 验证方法

**语法检查** — 确认 YAML 和 playbook 结构没有被破坏：
```bash
ansible-playbook playbooks/deploy-immich.yml --syntax-check
```

**运行时变量解析** — 确认 vault 变量能正确解析为实际值：
```bash
# 对于 group_vars/host_vars 中的变量，可以直接验证
ansible immich -m debug -a "msg='ssh={{ ansible_ssh_pass }}'"
# 输出: ssh=ubuntu ✅

# 对于 role defaults 中的变量，ansible -m debug 无法解析
# 因为 role defaults 只在 playbook 通过 roles: 加载时才生效
ansible immich -m debug -a "var=immich_db_password"
# 输出: VARIABLE IS NOT DEFINED ← 这是正常的！不是 bug
```

**关键区别**: `ansible -m debug` 只加载 inventory 层变量，不加载 role defaults。要验证 role defaults 中的 vault 引用是否正确，需要在实际部署时观察，或用 `--check` 模式执行完整 playbook。

## 6. Q&A 总结

### Q: role defaults 中引用 vault 变量，`ansible -m debug` 为什么解析不到？

**A**: 因为 `ansible` ad-hoc 命令不经过 role 加载机制。Role defaults 只在 playbook 执行中通过 `roles:` 指令触发加载。这不是 bug，是 Ansible 的设计。验证方法是用 `ansible-playbook --check` 或实际部署。

### Q: 为什么 homepage 的密码放 host_vars 而不是 role defaults？

**A**: 因为 homepage 的 3 个 API key（Proxmox、Tailscale、Immich）在语义上是"这台主机需要连接的外部服务凭证"，不是 homepage role 自身的配置参数。如果将来有第二个 homepage 实例连接不同的 Proxmox 集群，只需在新的 host_vars 中覆盖即可。

### Q: 同一个变量在 host_vars 和 role defaults 中都定义了会怎样？

**A**: host_vars 优先级更高，会覆盖 role defaults。重构前 `immich_db_password` 就是这种情况 — host_vars 中有 `admin`，role defaults 中也有 `admin`，实际使用的是 host_vars 的值。重构时需要先改 role defaults 为 vault 引用，再删 host_vars 中的重复定义，确保 vault 引用能生效。

### Q: Terraform 中的明文密码（pve-cluster.tf 的 `ansible_ssh_pass = "Admin123..."`）要不要一起迁？

**A**: 本次暂不处理。方案有两个：(A) Terraform 用 `var.pm_password` 引用 secrets.auto.tfvars；(B) 从 Terraform 删除 `ansible_ssh_pass`，改在 Ansible `group_vars/proxmox_cluster.yml` 中管理。方案 B 更符合"Ansible 管密码、Terraform 管基础设施"的分工原则，但改动较大，留作后续任务。

### Q: vault 中存储列表类型（如 `vault_anki_sync_users`）有什么注意事项？

**A**: YAML vault 支持存储任意 YAML 类型（string, list, dict）。但需要确保 vault 中的值类型与消费侧一致。`anki_sync_users` 在模板中用 `{% for sync_user in anki_sync_users %}` 遍历，所以 vault 中必须是 list 格式。验证方法：`ansible-vault view vault.yml | grep -A2 vault_anki_sync_users`。

---

## 参考

- **架构设计文档**：[Ansible Vault Architecture Design](../designs/ansible-vault-architecture.md) — 完整的架构设计规范（本文精简版）
- 前置笔记：[Ansible Vault Secret Management (2025-12-02)](./2025-12-02-ansible-vault-secret-management.md) — Vault 基础入门
- 项目规范：[AGENTS.md § Ansible Vault Architecture](../../AGENTS.md) — 快速参考手册
- Ansible 官方文档：[Variable Precedence](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)
