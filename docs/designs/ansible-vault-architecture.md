# Ansible Vault Architecture Design

**Last Updated**: 2026-01-31  
**Status**: ✅ Implemented  
**Owner**: Homelab IaC Project

## 概述

本文档定义了 Homelab IaC 项目中 Ansible Vault 的架构设计原则、变量组织方式、间接引用模式选择规则，以及与 Terraform 的集成机制。

## 设计目标

1. **单一密码源** — 所有密码集中在 Ansible Vault，Terraform 通过桥接脚本同步
2. **清晰的变量流向** — 任何人都能快速追踪一个密码从 vault 到消费点的完整路径
3. **语义化的组织方式** — 密码的存放位置反映其作用域（主机/组/角色）
4. **可维护性** — 新增服务时有明确规则指导密码应该放在哪里

## 架构组成

### 1. 单一 Vault 文件

```
ansible/
├── .vault_pass                              # 解密密码（gitignored）
├── ansible.cfg                              # vault_password_file = .vault_pass
└── inventory/
    └── group_vars/
        └── all/
            └── vault.yml                    # 唯一的加密文件，所有主机自动继承
```

**设计决策**:
- ✅ **单文件** vs 多文件 — 简化管理，避免密码分散在多个 vault 中难以查找
- ✅ 放在 `group_vars/all/` — 所有主机自动继承，适合集中式密码管理
- ✅ `.vault_pass` gitignored — 防止密码文件泄漏

**命名约定**: 
- Vault 中的变量使用 `vault_` 前缀（例如 `vault_proxmox_password`）
- 消费侧变量去掉前缀（例如 `proxmox_password`）
- 这样可以清楚区分"密码源"和"密码消费点"

### 2. 当前变量清单（18 个）

| 分组 | 变量 | 消费方 | 作用域 |
|------|------|--------|--------|
| **Homepage** | `vault_proxmox_api_password_homepage` | Ansible | 主机特定 |
| | `vault_tailscale_api_key_homepage` | Ansible | 主机特定 |
| | `vault_immich_api_key_homepage` | Ansible | 主机特定 |
| **OCI** | `vault_oci_tenancy_ocid` | Terraform + Ansible预留 | 组级别 |
| | `vault_oci_user_ocid` | Terraform + Ansible预留 | 组级别 |
| | `vault_oci_fingerprint` | Terraform + Ansible预留 | 组级别 |
| | `vault_oci_private_key_path` | Terraform + Ansible预留 | 组级别 |
| **Proxmox** | `vault_proxmox_password` | Terraform-only | N/A |
| | `vault_proxmox_api_token_id` | Terraform + Ansible | 共享 |
| | `vault_proxmox_api_token_secret` | Terraform + Ansible | 共享 |
| **Tailscale** | `vault_tailscale_auth_key` | Ansible | 组级别 |
| **PBS** | `vault_pbs_root_password` | Ansible | Role配置 |
| | `vault_pbs_backup_user_password` | Ansible | Role配置 |
| | `vault_pbs_api_token_value` | Ansible | Role配置 |
| **VM 默认凭证** | `vault_vm_default_password` | Ansible | 组级别 |
| **Immich** | `vault_immich_db_password` | Ansible | Role配置 |
| **Anki** | `vault_anki_sync_users` | Ansible | Role配置 |
| **Cloudflare** | `vault_cloudflare_api_token` | Ansible | Role配置 |

## 间接引用模式

### 核心原则：按变量作用域选择模式

| 作用域 | 模式 | 别名位置 | 优先级 | 使用场景 |
|--------|------|----------|--------|----------|
| 主机特定的密码 | Pattern A | `inventory/host_vars/<host>.yml` | 高 | 只有一台主机使用 |
| 组级别共享的密码 | Pattern A | `inventory/group_vars/<group>.yml` | 中高 | 同一组的主机共享 |
| Role 配置参数型密码 | Pattern B | `roles/<role>/defaults/main.yml` | 低 | Role 的配置参数，不区分主机/组 |
| Terraform-only 密码 | 无别名 | 仅在 vault 中 | N/A | 仅 Terraform 通过 get-secrets.sh 消费 |

### Pattern A: Inventory 层别名

**流向图**:
```
vault.yml                          group_vars 或 host_vars              role
┌─────────────────────┐     ┌──────────────────────────┐     ┌──────────────────┐
│ vault_tailscale_    │ ──> │ group_vars/tailscale.yml │ ──> │ tailscale role   │
│   auth_key: "tskey" │     │ tailscale_auth_key:      │     │ 使用变量         │
│                     │     │   "{{ vault_... }}"      │     │ tailscale_auth_  │
└─────────────────────┘     └──────────────────────────┘     │   key            │
                                                             └──────────────────┘
```

**代码示例**:
```yaml
# ansible/inventory/group_vars/tailscale.yml
tailscale_auth_key: "{{ vault_tailscale_auth_key }}"

# ansible/inventory/host_vars/homepage.yml
proxmox_api_password: "{{ vault_proxmox_api_password_homepage }}"
tailscale_api_key: "{{ vault_tailscale_api_key_homepage }}"
immich_api_key: "{{ vault_immich_api_key_homepage }}"
```

**优点**:
- ✅ 灵活 — 可以在不同层级覆盖（group_vars → host_vars → extra_vars）
- ✅ Role 可移植 — role 本身不依赖 `vault_` 命名约定
- ✅ 语义清晰 — "这个密码属于某台主机/某个组"的语义很明确

**缺点**:
- ❌ 间接层更多 — 追踪变量需要跳两个文件
- ❌ 容易遗漏 — 新建 role 后必须记得去 inventory 补别名

**适用场景**:
- 主机特定的 API key（如 homepage 连接外部服务的凭证）
- 组级别共享的密钥（如 tailscale 网络的 auth key）

### Pattern B: Role Defaults 层别名

**流向图**:
```
vault.yml                          role defaults                         role tasks
┌─────────────────────┐     ┌──────────────────────────┐     ┌──────────────────┐
│ vault_cloudflare_   │ ──> │ caddy/defaults/main.yml  │ ──> │ caddy tasks      │
│   api_token: "5Ly"  │     │ cloudflare_api_token:    │     │ 使用变量         │
│                     │     │   "{{ vault_... }}"      │     │ cloudflare_api_  │
└─────────────────────┘     └──────────────────────────┘     │   token          │
                                                             └──────────────────┘
```

**代码示例**:
```yaml
# ansible/roles/caddy/defaults/main.yml
# Cloudflare API token for DNS challenge (vault indirect reference)
cloudflare_api_token: "{{ vault_cloudflare_api_token }}"

# ansible/roles/pbs/defaults/main.yml
# PBS credentials (vault indirect reference)
pbs_root_password: "{{ vault_pbs_root_password }}"
pbs_backup_user_password: "{{ vault_pbs_backup_user_password }}"
```

**优点**:
- ✅ 简单直接 — 只有一跳，追踪变量容易
- ✅ 自包含 — 看 role defaults 就知道需要哪些 vault 变量
- ✅ 开箱即用 — 不需要额外配置 inventory

**缺点**:
- ❌ Role 耦合 vault 命名 — role 硬编码了 `vault_` 前缀
- ❌ 覆盖灵活性低 — 如果不同主机需要不同值，需要在 host_vars 中覆盖（违反了 defaults 语义）

**适用场景**:
- Role 的配置参数（如 caddy 的 cloudflare token、PBS 的管理员密码）
- 只有一个实例在用的情况（Homelab 常见场景）

### 为什么允许混用？

**不是架构不一致，而是语义匹配**:

| 变量 | 语义 | 模式选择 | 理由 |
|------|------|----------|------|
| `tailscale_auth_key` | "加入 tailscale 网络的所有机器共享的密钥" | Pattern A (group_vars) | 组级别的配置 |
| `homepage` 的 3 个 API key | "只有 homepage 这台机器用的外部服务凭证" | Pattern A (host_vars) | 主机特定的配置 |
| `cloudflare_api_token` | "caddy 这个 role 的配置参数" | Pattern B (role defaults) | Role 配置参数 |

强制统一到一种模式会**丢失语义信息** — 比如把 `tailscale_auth_key` 放到 tailscale role defaults 中，就失去了"这是组级别共享密钥"的语义。

## Ansible 变量优先级

理解变量优先级是正确使用间接引用的基础：

```
role defaults          ← 最低优先级（可被任何层级覆盖）
  ↓
group_vars/all         ← 全局默认值
  ↓
group_vars/<group>     ← 组级别配置
  ↓
host_vars/<host>       ← 主机特定配置
  ↓
play vars              ← playbook 中的 vars: 块
  ↓
extra vars             ← 最高优先级（--extra-vars）
```

### 反模式：在 playbook vars 中做间接引用

```yaml
# ❌ 不好：playbook vars 优先级太高，阻止了 inventory 层覆盖
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

**为什么这是反模式**:
- playbook `vars:` 的优先级高于 host_vars，会阻止主机级别的覆盖
- 破坏了 Ansible 的分层设计理念
- playbook 应该专注于"执行流程"，不应该管"配置数据"

## Terraform 集成：secrets 桥接机制

### 架构图

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

### 设计原则

**Ansible Vault 是唯一密码源** — Terraform 不存储密码，只通过桥接脚本从 Vault 同步。

**变量分类**:
- **Terraform-only**: 仅 `vault_proxmox_password` — 没有 Ansible 消费者
- **共享**: `vault_proxmox_api_token_id/secret` — Terraform 和 Ansible (pbs_client) 都用
- **Ansible-only**: 其余 13 个 — Terraform 不需要

**工作流**:
1. 新增密码时，先加到 `vault.yml`
2. 运行 `./scripts/get-secrets.sh` 同步到 `*.auto.tfvars`
3. Terraform 在 `plan/apply` 时自动读取 `.auto.tfvars`

### 为什么不在 Terraform 中直接读 Vault？

**考虑过的方案**:
- ❌ Terraform `local-exec` 调用 `ansible-vault view` — 在每次 plan 时都要解密，性能差
- ❌ 使用 `external` data source 调用 Python 脚本 — 增加依赖复杂度
- ✅ **pre-apply 桥接脚本** — 简单、可控、性能好

## 完整变量流向图

```
vault.yml (18 个变量)
│
├── Pattern A: Inventory 层别名
│   ├── host_vars/homepage.yml
│   │   ├── proxmox_api_password ← vault_proxmox_api_password_homepage
│   │   ├── tailscale_api_key   ← vault_tailscale_api_key_homepage
│   │   └── immich_api_key      ← vault_immich_api_key_homepage
│   │         └──> homepage role (templates/services.yaml.j2)
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
│   └── group_vars/oci.yml (预留，当前仅 Terraform 消费)
│       ├── oci_tenancy_ocid    ← vault_oci_tenancy_ocid
│       ├── oci_user_ocid       ← vault_oci_user_ocid
│       ├── oci_fingerprint     ← vault_oci_fingerprint
│       └── oci_private_key_path ← vault_oci_private_key_path
│
├── Pattern B: Role Defaults 层别名
│   ├── roles/caddy/defaults/main.yml
│   │   └── cloudflare_api_token ← vault_cloudflare_api_token
│   │         └──> caddy role (tasks/main.yml)
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
│   │         └──> pbs_client role (tasks/*.yml)
│   │
│   ├── roles/immich/defaults/main.yml
│   │   └── immich_db_password ← vault_immich_db_password
│   │         └──> immich role (templates/env.j2)
│   │
│   └── roles/anki_sync_server/defaults/main.yml
│       └── anki_sync_users ← vault_anki_sync_users
│             └──> anki role (templates/*.service.j2)
│
├── Terraform 桥接 (scripts/get-secrets.sh)
│   ├── vault_proxmox_password      → proxmox/secrets.auto.tfvars
│   ├── vault_proxmox_api_token_id  → proxmox/secrets.auto.tfvars
│   ├── vault_proxmox_api_token_secret → proxmox/secrets.auto.tfvars
│   └── vault_oci_*                 → oci/secrets.auto.tfvars
│
└── 无别名 (Terraform-only)
    └── vault_proxmox_password — 仅 get-secrets.sh 消费
```

## 运维规范

### 新增密码的标准流程

1. **编辑 vault 文件**:
   ```bash
   ansible-vault edit ansible/inventory/group_vars/all/vault.yml
   ```

2. **添加变量**（使用 `vault_` 前缀）:
   ```yaml
   # Netbox
   vault_netbox_superuser_password: "NewSecurePassword123"
   ```

3. **创建间接引用**（按作用域选择模式）:
   
   **如果是主机特定**:
   ```yaml
   # ansible/inventory/host_vars/netbox.yml
   netbox_superuser_password: "{{ vault_netbox_superuser_password }}"
   ```
   
   **如果是组级别**:
   ```yaml
   # ansible/inventory/group_vars/netbox_cluster.yml
   netbox_db_password: "{{ vault_netbox_db_password }}"
   ```
   
   **如果是 role 配置参数**:
   ```yaml
   # ansible/roles/netbox/defaults/main.yml
   # Netbox admin password (vault indirect reference)
   netbox_superuser_password: "{{ vault_netbox_superuser_password }}"
   ```

4. **如果 Terraform 需要**，运行桥接脚本:
   ```bash
   ./scripts/get-secrets.sh
   ```

5. **验证变量解析**:
   ```bash
   # 对于 inventory 层的变量
   ansible netbox -m debug -a "var=netbox_superuser_password"
   
   # 对于 role defaults 层的变量
   ansible-playbook playbooks/deploy-netbox.yml --syntax-check
   ```

### 密码轮换流程

1. 在实际系统中更改密码（如 Proxmox Web UI、PBS CLI）
2. 用 `ansible-vault edit` 更新 vault.yml
3. 如果是 Terraform 使用的密码，运行 `get-secrets.sh`
4. 重新运行受影响的 playbook（如果有服务配置文件引用该密码）

### 备份与恢复

**Vault 密码文件备份**:
- `.vault_pass` 存储在 1Password / KeePass 等密码管理器中
- 定期备份 `vault.yml`（虽然在 git 中，但加密的，建议额外备份解密版到安全位置）

**恢复流程**:
1. 从密码管理器恢复 `.vault_pass`
2. 从 git 恢复 `vault.yml`
3. 验证解密：`ansible-vault view ansible/inventory/group_vars/all/vault.yml | head`

## 常见问题

### Q: 为什么不使用 HashiCorp Vault？

**A**: HashiCorp Vault 是企业级方案，提供动态密码、细粒度 ACL、审计日志等高级功能。但对于 Homelab：
- Ansible Vault 够用 — 静态密码、文件级加密、简单直接
- 无需额外服务 — HashiCorp Vault 需要运行服务器，增加维护负担
- 学习成本低 — Ansible Vault 是 Ansible 内置功能

未来如果服务规模扩大（10+ 个服务，多人协作），可以考虑迁移到 HashiCorp Vault。

### Q: 为什么不把每个 role 的密码放在 role 自己的 vault 文件中？

**A**: 多 vault 文件方案的问题：
- 密码分散 — 难以查找"某个密码在哪个 vault 文件里"
- 需要多个 vault 密码 — 增加管理负担
- 跨 role 共享密码困难 — 如 `vault_proxmox_api_token_id` 被多个 role 使用

单文件方案的优势：
- 一次解密，全局可用
- 密码集中管理，便于审计
- 适合 Homelab 规模（<20 个密码）

### Q: role defaults 中引用 vault 变量，为什么 `ansible -m debug` 解析不到？

**A**: 因为 `ansible` ad-hoc 命令不经过 role 加载机制。Role defaults 只在 playbook 通过 `roles:` 指令时加载。验证方法：
```bash
# ❌ 不会解析 role defaults
ansible immich -m debug -a "var=immich_db_password"

# ✅ 正确验证方式
ansible-playbook playbooks/deploy-immich.yml --check --diff
```

### Q: 同一个变量在 host_vars 和 role defaults 中都定义了会怎样？

**A**: host_vars 优先级更高，会覆盖 role defaults。重构时需要注意：
1. 先改 role defaults 为 vault 引用
2. 再删 host_vars 中的重复定义
3. 验证 role defaults 的 vault 引用能生效

### Q: vault 中可以存储复杂类型（list, dict）吗？

**A**: 可以。Vault 支持任意 YAML 类型：
```yaml
# 字符串
vault_simple_password: "admin"

# 列表
vault_anki_sync_users:
  - "anki:anki"
  - "user2:password2"

# 字典
vault_complex_config:
  username: admin
  password: secret
  options:
    timeout: 30
```

注意：消费侧需要能处理对应类型。例如 `anki_sync_users` 在模板中用 `{% for %}` 遍历，vault 中必须是 list。

## 变更历史

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-01-31 | 1.0 | 初始版本，基于架构审计和标准化重构 |

## 参考文档

- 实施笔记：[Ansible Vault 架构设计与标准化重构](../learningnotes/2026-01-31-ansible-vault-architecture-refactoring.md)
- 入门文档：[Ansible Vault Secret Management](../learningnotes/2025-12-02-ansible-vault-secret-management.md)
- 项目规范：[AGENTS.md § Ansible Vault Architecture](../../AGENTS.md)
- Ansible 官方文档：[Using Vault in playbooks](https://docs.ansible.com/ansible/latest/vault_guide/vault_using_encrypted_content.html)
