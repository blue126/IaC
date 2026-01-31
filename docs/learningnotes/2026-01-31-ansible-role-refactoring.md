# 学习笔记：Ansible Role 架构重构

**日期**: 2026-01-31
**标签**: #Ansible #Refactoring #Roles #Architecture #BestPractices
**状态**: 进行中（Phase 1 已完成，Phase 2/3 待执行）

在完成 Vault 架构标准化后，我们对所有 Ansible Role 进行了全面审计和重构。本文记录了重构的背景、发现的问题、解决方案和经验教训。

---

## 1. 背景：为什么要重构 Role

项目经历了多个阶段的快速迭代（2025-11 到 2026-01），不同时期创建的 Role 风格不一致。随着服务从 3 个增长到 7+ 个，积累了以下技术债：

- **命名不一致**：部分 role 使用连字符（`pbs-zfs`、`anki-sync-server`），不符合 Ansible `snake_case` 约定
- **变量作用域混乱**：有些 role 把可覆盖变量放在 `vars/`（高优先级，难以覆盖），有些硬编码在 playbook 中
- **依赖管理不规范**：有些 role 内部通过 `include_role` 引入依赖，不透明
- **空目录残留**：部分 role 有空的 `handlers/` 目录
- **Collection 依赖未声明**：`netbox_sync` role 使用了 `netbox.netbox` collection，但 `requirements.yml` 中未声明

## 2. 全面审计

### 2.1 审计方法

使用自动化扫描检查了所有 role 的：
- 目录结构完整性（是否有 `defaults/main.yml`）
- 变量定义位置（`vars/` vs `defaults/` vs playbook `vars:`）
- 角色依赖方式（`meta/main.yml` vs `include_role` vs playbook `roles:`）
- 命名规范（是否使用 `snake_case`）

### 2.2 发现的问题

| 问题类型 | 涉及 Role | 严重程度 |
|----------|-----------|----------|
| 命名使用连字符 | `pbs-zfs`, `anki-sync-server` | 高 |
| 变量放在 `vars/` 而非 `defaults/` | `common` | 高 |
| role 内嵌 `include_role` 依赖 | `rustdesk`（内嵌 `docker`） | 高 |
| 缺少 `defaults/main.yml` | `netbox_sync` | 中 |
| 硬编码 URL/Token 在 playbook 中 | `sync-netbox.yml` | 中 |
| 空的 `handlers/` 目录 | `pbs`, `pbs_zfs` | 低 |
| Collection 依赖未声明 | `netbox_sync`（需要 `netbox.netbox`） | 中 |

---

## 3. Phase 1 重构（已完成）

### 3.1 Role 重命名：`pbs-zfs` → `pbs_zfs`

**问题**：Ansible 推荐 role 名使用 `snake_case`，连字符在某些场景下可能导致解析问题。

**操作**：
```bash
mv ansible/roles/pbs-zfs ansible/roles/pbs_zfs
```

**影响范围**（全部已更新）：
- `ansible/playbooks/deploy-pbs.yml` — role 引用
- `AGENTS.md` — role 列表
- `docs/deployment/pbs_esxi_deployment.md` — 13 处文档引用

**注意**：只改 role 目录名，不改 playbook 文件名（`deploy-pbs.yml` 保持不变，因为文件名不是 Ansible 标识符）。

### 3.2 Role 重命名：`anki-sync-server` → `anki_sync_server`

**操作**：
```bash
mv ansible/roles/anki-sync-server ansible/roles/anki_sync_server
```

**影响范围**（全部已更新）：
- `ansible/playbooks/deploy-anki.yml` — role 引用

**刻意不改的内容**：
- systemd 服务名 `anki-sync-server`（基础设施标识符）
- 模板文件名 `anki-sync-server.service.j2`
- handler 名 `Restart anki-sync-server`
- Terraform `lxc_name` / Netbox `name`

**设计决策**：Role 目录名是 Ansible 内部标识符，遵循 `snake_case`；systemd 服务名、Terraform 资源名是外部基础设施标识符，保持原样不动。这是两个不同的命名空间。

### 3.3 修复 `common` Role 变量作用域

**问题**：`common` role 的变量定义在 `vars/main.yml` 中，包含：
- `common_packages`（可覆盖的配置 → 应该在 `defaults/`）
- `common_authorized_keys`（5 个 SSH 公钥 → 应该在 inventory）

Ansible 变量优先级中 `vars/` (优先级 14) 远高于 `defaults/` (优先级 2)，放在 `vars/` 里意味着用户几乎无法覆盖这些值。

**解决方案**：
1. 创建 `ansible/inventory/group_vars/all/common.yml` — 存放 SSH 公钥列表
2. 创建 `ansible/roles/common/defaults/main.yml` — 存放 `common_authorized_keys: []` 默认值和 `common_packages` 列表
3. 删除 `ansible/roles/common/vars/main.yml`

**验证**：
```bash
ansible immich -m debug -a "var=common_authorized_keys"
# 正确显示 5 个 SSH 公钥，来自 inventory group_vars
```

**关键概念**：`defaults/` 提供"可以被覆盖的默认值"，`vars/` 提供"几乎不可覆盖的固定值"。大多数情况下应该用 `defaults/`。

### 3.4 修复 `rustdesk` Role 依赖管理

**问题**：`rustdesk/tasks/main.yml` 开头有：
```yaml
- name: Include docker role
  include_role:
    name: docker
```

这种方式的问题：
1. 角色依赖不透明 — 看 playbook 不知道 rustdesk 依赖 docker
2. `include_role` 在 task 层面运行，行为与 `roles:` 块不同（handler 作用域、变量作用域）
3. 破坏了"单一职责"原则

**解决方案**：
1. 从 `rustdesk/tasks/main.yml` 删除 `include_role: docker`
2. 重写 `deploy-rustdesk.yml`，改为标准 `roles:` 块格式：
```yaml
roles:
  - docker
  - rustdesk
```
3. 补充缺失的 Verify play（端口检查 + docker ps）

### 3.5 添加 `netbox_sync` 的 `defaults/main.yml`

**问题**：`sync-netbox.yml` playbook 硬编码了 Netbox URL 和 API Token：
```yaml
vars:
  netbox_url: "http://192.168.1.104:8080"
  netbox_token: "0123456789abcdef0123456789abcdef01234567"
```

这违反了两个原则：
- 变量应该在 role defaults 中定义，不应在 playbook `vars:` 中
- Token 不应以明文出现在 playbook 中

**解决方案**：
1. 创建 `ansible/roles/netbox_sync/defaults/main.yml`，包含 `netbox_url` 和 `netbox_token`
2. 简化 `sync-netbox.yml`，移除 `vars:` 和 `include_role`，改用标准 `roles:` 块

**遗留问题**：`netbox_token` 当前仍是明文值（与 `netbox` role 的 `netbox_superuser_api_token` 相同），应在 Phase 2 迁入 vault。

### 3.6 修复 Collection 依赖声明

**问题**：`netbox_sync` role 使用了 `netbox.netbox.netbox_device` 和 `netbox.netbox.netbox_virtual_machine` 模块，但 `ansible/requirements.yml` 中未声明 `netbox.netbox` collection，导致语法检查报错。

**解决方案**：在 `requirements.yml` 中添加 `netbox.netbox`。

### 3.7 清理空目录

删除了 `ansible/roles/pbs/handlers/` 和 `ansible/roles/pbs_zfs/handlers/` 两个空目录。Ansible 不要求所有标准目录都存在，空目录只是噪音。

---

## 4. Phase 2 重构（已完成）

### 4.1 Netbox 明文凭据迁入 Vault

**问题**：`netbox/defaults/main.yml` 中有两个明文凭据：
- `netbox_superuser_password: "admin"`
- `netbox_superuser_api_token: "0123456789abcdef0123456789abcdef01234567"`

同时 `netbox_sync/defaults/main.yml` 也使用了同一个明文 token。

**解决方案**：
1. 在 vault 中添加 `vault_netbox_superuser_password` 和 `vault_netbox_superuser_api_token`
2. `netbox/defaults/main.yml` 改为 vault 间接引用（Pattern B）
3. `netbox_sync/defaults/main.yml` 的 `netbox_token` 也改为引用 `vault_netbox_superuser_api_token`

### 4.2 补充 n8n/rustdesk/tailscale defaults

**n8n role**：
- 新增 `defaults/main.yml`：`n8n_port: 5678`、`n8n_nodejs_major_version: 20`
- 模板 `n8n.service.j2` 中 `N8N_PORT=5678` 改为 `{{ n8n_port }}`
- tasks 中 `setup_20.x` 改为 `setup_{{ n8n_nodejs_major_version }}.x`

**rustdesk role**：
- 新增 `defaults/main.yml`：`rustdesk_relay_host`、`rustdesk_data_dir`、`rustdesk_image`、`rustdesk_hbbs_port`、`rustdesk_relay_port`
- tasks 中所有 `/var/lib/rustdesk` 路径改为 `{{ rustdesk_data_dir }}`
- 模板中 `rustdesk.willfan.me` 改为 `{{ rustdesk_relay_host }}`，镜像和端口同理

**tailscale role**：
- 新增 `defaults/main.yml`：`tailscale_dns_server: "192.168.1.1"`
- tasks 中硬编码 DNS `192.168.1.1` 改为 `{{ tailscale_dns_server }}`
- `tailscale_auth_key` 已在 `group_vars/tailscale.yml` 中通过 vault 间接引用，不在 role defaults 重复定义

**设计决策**：tailscale LXC 特有逻辑保持在单文件中，用 `when` 条件区分，因为逻辑量不大且已经清晰。

### 4.3 修复 homepage role defaults 一致性

**问题**：homepage role 的 `defaults/main.yml` 为 `proxmox_api_password`、`netbox_api_token`、`immich_api_key` 等 API 凭据都定义了空字符串默认值，但模板中使用的 `tailscale_api_key` 和 `tailscale_device_id` 却没有默认值。这两个变量实际定义在 `host_vars/homepage.yml` 中，但缺少 defaults 会导致在其他主机上运行时报 undefined variable 错误。

**解决方案**：在 `homepage/defaults/main.yml` 中补充 `tailscale_api_key: ""` 和 `tailscale_device_id: ""`，与其他 API 变量保持一致。

### 4.4 硬编码配置审计与决策

对所有 role 做了硬编码扫描后，决定**只提取真正会因环境而变的值**：

**已变量化**（域名、路径、镜像）：
- rustdesk：`rustdesk_relay_host`（域名）、`rustdesk_data_dir`（路径）、`rustdesk_image`（镜像版本）
- tailscale：`tailscale_dns_server`（DNS 服务器 IP）

**刻意不变量化**（标准端口、协议标识符、版本号）：
- `21116`/`21117`（RustDesk 标准端口）、`8007`（PBS 标准端口）、`5678`（n8n 默认端口）
- `root@pam`、`backup@pbs`（PBS 协议固定的用户标识符）
- `setup_20.x`（Node.js 版本，与 role 逻辑紧密耦合）

**homepage 模板**：刻意保持硬编码。模板内容本质上是 dashboard 配置文件，需要明文可见的服务地址，不适合变量化。

**经验教训**：过度变量化会增加复杂度却没有实际收益。变量化的判断标准是"这个值在不同环境下是否**真的**会不同"。

---

## 6. 经验教训

### 6.1 重命名 Role 的影响范围检查清单

重命名一个 Ansible role 时，需要检查以下位置：
1. `playbooks/*.yml` — role 引用
2. `roles/*/tasks/main.yml` — `include_role` 引用
3. `roles/*/meta/main.yml` — 依赖声明
4. `AGENTS.md` — 项目文档
5. `docs/` — 所有文档中的路径引用
6. **不需要改的**：systemd 服务名、Terraform 资源名、Netbox 记录名（这些是外部标识符）

### 6.2 `vars/` vs `defaults/` 选择规则

```
defaults/main.yml (优先级 2)  → 用户可覆盖的配置
vars/main.yml (优先级 14)     → 角色内部常量，不希望被覆盖
inventory group_vars (优先级 8) → 环境特定的数据（如 SSH 公钥列表）
```

经验法则：**如果你不确定，就用 `defaults/`**。只有真正的角色内部常量才放 `vars/`。

### 6.3 Role 依赖的正确方式

```yaml
# BAD: 在 role tasks 中嵌套引入依赖
- include_role:
    name: docker

# GOOD: 在 playbook 的 roles 块中显式声明
roles:
  - docker
  - my_service
```

playbook 是"编排层"，role 是"执行层"。依赖关系应该在编排层可见。

### 6.4 避免过度变量化

不是所有硬编码值都需要提取为变量。判断标准：

| 应该变量化 | 不应该变量化 |
|-----------|------------|
| 域名（`rustdesk.willfan.me`） | 标准端口（`8007`, `5678`, `21116`） |
| IP 地址（可能随环境变化） | 协议固定标识符（`root@pam`, `backup@pbs`） |
| 凭据/密钥 | 软件版本号（与 role 逻辑紧耦合） |
| 文件路径（`/var/lib/rustdesk`） | 第三方服务 URL（`login.tailscale.com`） |
| 容器镜像名（可能需要切换版本） | Dashboard 配置中的服务地址（需要明文可见） |

这个原则已写入 `AGENTS.md` 的 Ansible 代码风格指南中。

### 6.5 每步执行后必须验证

在本次重构中发现，`netbox_sync` 的语法检查暴露了缺少 `netbox.netbox` collection 的问题。如果不做验证，这个问题会一直潜伏到实际部署时才暴露。

**规则**：每个重构步骤完成后，至少执行一次语法检查（`--syntax-check`）或变量解析验证（`ansible ... -m debug`）。

---

## 7. 变更摘要

### Phase 1 提交记录

```
a6c5e1c refactor(ansible): standardize role naming, variable scope, and playbook structure
```

包含以下文件变更：
- 重命名：`pbs-zfs/` → `pbs_zfs/`，`anki-sync-server/` → `anki_sync_server/`
- 新增：`inventory/group_vars/all/common.yml`，`roles/common/defaults/main.yml`，`roles/netbox_sync/defaults/main.yml`
- 修改：`deploy-pbs.yml`，`deploy-anki.yml`，`deploy-rustdesk.yml`，`sync-netbox.yml`，`rustdesk/tasks/main.yml`
- 删除：`common/vars/main.yml`，空 `handlers/` 目录
- 文档：`AGENTS.md`，`pbs_esxi_deployment.md`，vault 相关文档

### Phase 2 提交记录

```
(待提交) refactor(ansible): migrate netbox secrets to vault, add role defaults, extract environment-specific configs
```

包含以下文件变更：
- Vault：添加 `vault_netbox_superuser_password` 和 `vault_netbox_superuser_api_token`
- 修改：`netbox/defaults/main.yml`、`netbox_sync/defaults/main.yml` — vault 间接引用
- 新增：`rustdesk/defaults/main.yml`、`tailscale/defaults/main.yml`
- 修改：`rustdesk/tasks/main.yml`、`rustdesk/templates/docker-compose.yml.j2` — 域名/路径/镜像变量化
- 修改：`tailscale/tasks/main.yml` — DNS 变量化
- 修改：`requirements.yml` — 添加 `netbox.netbox` collection
- 修改：`homepage/defaults/main.yml` — 补充 `tailscale_api_key` 和 `tailscale_device_id` 默认值
- 文档：`AGENTS.md`（强化分步确认规则 + 变量化原则）、`INDEX.md`（更新索引）

### Phase 3: Role 合并

```
(待提交) refactor(ansible): merge pbs_zfs into pbs role
```

将 `pbs_zfs` role 合并到 `pbs` role 中，理由：
- 这两个 role 总是一起使用，`pbs_zfs` 从未单独运行
- 减少 role 数量，简化架构（14 → 13 个 role）
- 遵循"单一职责"原则 — PBS 服务的存储配置属于 PBS 服务的一部分

变更内容：
- 合并：`pbs_zfs/defaults/main.yml` → `pbs/defaults/main.yml`
- 复制：`pbs_zfs/tasks/*.yml` → `pbs/tasks/zfs-*.yml`（添加前缀）
- 更新：`pbs/tasks/main.yml` — 添加 ZFS tasks include
- 简化：`deploy-pbs.yml` — 只使用 `pbs` role
- 删除：`ansible/roles/pbs_zfs/` 目录
- 文档：更新 `AGENTS.md`、`ansible-role-architecture.md`、`pbs_esxi_deployment.md`
