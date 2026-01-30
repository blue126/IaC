# Ansible 最佳实践综合指南

## 文档元数据

**创建日期**: 2026-01-30
**最后更新**: 2026-01-30
**基于 Learning Notes**:
- 2025-11-30-ansible-deployment-verification.md
- 2025-12-02-ansible-inventory-refactoring.md
- 2025-12-02-ansible-vault-secret-management.md
- 2025-12-03-ansible-abstraction-levels.md
- 2025-12-04-ansible-tags-and-variables.md
- 2026-01-29-inventory-migration-trap.md
- 2026-01-29-ansible-troubleshooting.md

---

## 简介

本指南整合了在 Homelab 环境中使用 Ansible 进行基础设施自动化的最佳实践。涵盖了从 Inventory 组织、密钥管理、抽象设计、标签策略、部署验证到故障排查的全方位内容。

这些实践来自于实际部署经验（Anki Sync Server、Samba、Immich、Netbox 等服务），提供了可复用的模式和常见陷阱的详细解析。

---

## 第一部分：Inventory 管理最佳实践

### 1.1 核心原则：单一职责

每个文件应该只负责一件事：

| 文件类型 | 职责 | 示例 |
|--------|------|------|
| `groups.yml` | **仅**定义组层级关系 | 定义 `proxmox_cluster` > `pve_lxc` 的关系 |
| `group_vars/<组名>.yml` | **仅**定义该组所有主机的共享变量 | `lxc_gateway: 192.168.1.1` |
| `host_vars/<主机名>.yml` | **仅**定义该主机特有的变量 | `ansible_host: 192.168.1.50` |
| `<组名>/hosts.yml` | **仅**列出该组的成员 | 列出 `pve0`, `pve1`, `pve2` |

**关键**: 避免在一个文件中混合多种职责。

### 1.2 推荐目录结构

```
inventory/
├── groups.yml                    # 组层级关系（新增）
├── group_vars/                   # 组变量
│   ├── proxmox_cluster.yml
│   ├── pve_lxc.yml              # 与目录名一致
│   ├── pve_vms.yml              # 与目录名一致
│   ├── tailscale.yml
│   └── all/
│       └── vault.yml            # 加密的全局变量
├── host_vars/                    # 主机变量（新增）
│   ├── pve0.yml
│   ├── pve1.yml
│   └── pve2.yml
├── proxmox_cluster/              # 组定义
│   └── hosts.yml
├── pve_lxc/                      # LXC 容器组
│   ├── anki.yml
│   └── homepage.yml
├── pve_vms/                      # Proxmox 虚拟机组
│   ├── immich.yml
│   ├── netbox.yml
│   └── samba.yml
└── oci/
    └── hosts.yml
```

### 1.3 命名一致性

**关键规则**: 目录名必须与 `group_vars` 文件名一致，都使用下划线分隔（不能使用连字符）。

```
❌ 错误
inventory/
├── group_vars/
│   └── pve_lxc.yml        # 使用下划线
└── pve-lxc/               # 使用连字符（不一致！）

✅ 正确
inventory/
├── group_vars/
│   └── pve_lxc.yml        # 使用下划线
└── pve_lxc/               # 使用下划线
```

**原因**: Ansible 组名必须是合法的 Python 变量名（不能包含连字符）。

### 1.4 何时合并，何时拆分？

**合并场景**:
- 配置简单且一致（如 3 个 Proxmox 节点的 API 配置）
- 主机数量少（< 5 个）

**拆分场景**:
- 配置复杂且差异大（如 Immich 有 10+ 个变量）
- 需要独立管理（如每个 VM 有不同的维护者）
- 希望 Git 历史清晰（独立文件 = 独立 commit）

**推荐**: 在小规模环境（< 15 台主机）中，完全拆分的清晰度优势远大于文件数量的劣势。

### 1.5 变量继承优先级

```
host_vars > group_vars > playbook vars > role defaults
```

在 `group_vars` 中定义默认值，在 `host_vars` 中覆盖特定主机的值。

---

## 第二部分：Vault 密钥管理

### 2.1 解决的问题

在 IaC 仓库中管理敏感信息（API 密钥、密码、Token）时面临的挑战：
- 不能在版本控制中硬编码秘密
- 本地开发和远程部署需要一致的密钥管理
- 团队协作时需要安全地共享密钥

### 2.2 Ansible Vault 概览

**Ansible Vault** 使用 AES256 加密敏感数据文件。

#### 核心组件

| 组件 | 说明 |
|------|------|
| **Vault File** | 加密的 YAML 文件（通常位于 `group_vars/all/vault.yml`） |
| **Vault Password** | 解密密钥（存储在 `.vault_pass`，必须 gitignore） |
| **ansible.cfg** | 配置文件，自动指向密钥文件位置 |

#### 目录结构

```
ansible/
├── .vault_pass              # 包含密码（GITIGNORED）
├── .gitignore              # 确保 .vault_pass 被忽略
├── ansible.cfg
└── inventory/
    └── group_vars/
        └── all/
            └── vault.yml    # 加密的全局变量
```

### 2.3 配置方法

#### 步骤 1：创建密码文件

```bash
# 生成随机密码
openssl rand -base64 32 > .vault_pass
chmod 600 .vault_pass
```

#### 步骤 2：配置 ansible.cfg

```ini
[defaults]
vault_password_file = .vault_pass
```

#### 步骤 3：创建 Vault 文件

```bash
ansible-vault create inventory/group_vars/all/vault.yml
```

### 2.4 使用模式

#### 命名约定

所有 Vault 变量使用 `vault_` 前缀：

```yaml
# vault.yml (加密)
vault_proxmox_api_password: "secure_password_here"
vault_immich_db_password: "another_secret"
```

#### 在 Inventory 中引用

```yaml
# inventory/host_vars/pve0.yml
proxmox_api_password: "{{ vault_proxmox_api_password }}"
```

#### 编辑 Vault

```bash
# 编辑已加密的 Vault 文件
ansible-vault edit inventory/group_vars/all/vault.yml

# 查看内容（需要密码）
ansible-vault view inventory/group_vars/all/vault.yml
```

#### 运行 Playbook

```bash
# 由于 ansible.cfg 已配置，无需额外参数
ansible-playbook playbooks/deploy-service.yml

# 或显式指定密码文件
ansible-playbook playbooks/deploy-service.yml --vault-password-file=.vault_pass
```

### 2.5 关键注意事项

**✅ 强制措施**:
- 在 `.gitignore` 中明确列出 `.vault_pass`：`echo ".vault_pass" >> .gitignore`
- 定期检查仓库历史，确保从未提交过密码
- 使用强密码（`openssl rand -base64 32` 生成）
- 在团队协作时通过安全渠道（1Password、LastPass等）共享密码

**❌ 常见错误**:
- 不小心提交 `.vault_pass` 到仓库
- 在代码审查中泄露 Vault 内容
- Vault 文件放在错误的位置（不是 `group_vars/all/`）

### 2.6 进阶：HashiCorp Vault

对于企业级需求，可以考虑 **HashiCorp Vault**：

| 特性 | Ansible Vault | HashiCorp Vault |
|------|--------------|-----------------|
| 存储方式 | 静态文件 | 运行服务器 |
| 密钥类型 | 静态密码 | 动态密钥 + 静态密钥 |
| 审计日志 | 无 | 完整的访问审计 |
| 集中访问控制 | 无 | 精细的 ACL 策略 |
| 集成方式 | Ansible 原生 | 需要 `community.hashi_vault` |

HashiCorp Vault 适合需要动态密钥生成、详细审计日志和团队级别访问控制的场景。

---

## 第三部分：抽象设计层次

### 3.1 三层抽象模型

在 Ansible 中，功能可以在三个不同抽象级别实现：

```
Module (Python) ─────────────────────────────────── 最复杂
    ↓
Role with tasks_from (Dedicated Task Files)──── 中等复杂度
    ↓
Inline Tasks ─────────────────────────────────── 最简单
```

### 3.2 Custom Module（`library/`）

**定义**: 用 Python 编写的自定义模块，扩展 Ansible 功能。

**位置**: `library/`（项目根）或 `roles/<role>/library/`

**优点**:
- ✅ 原生支持幂等性和复杂的状态管理
- ✅ Playbook 代码简洁明了
- ✅ 完全控制执行逻辑

**缺点**:
- ❌ 需要编写 Python 代码
- ❌ 维护成本较高
- ❌ 通常是过度设计

**何时使用**: 只有当现有 Ansible 模块无法表达逻辑时才使用。

### 3.3 Dedicated Task File（`tasks_from`）- 推荐

**定义**: 在 Role 内创建独立的任务文件，通过 `include_role` 的 `tasks_from` 参数引入。

**位置**: `roles/<role>/tasks/<file>.yml`

**用法**:
```yaml
- include_role:
    name: tailscale
    tasks_from: serve
  vars:
    tailscale_serve_target: "hostname"
    tailscale_serve_port: 8080
```

**优点**:
- ✅ 功能模块化但保持文件组织的内聚性
- ✅ 所有相关逻辑在同一文件夹内
- ✅ 使用标准 YAML 语法，无需 Python
- ✅ 易于复用和测试

**缺点**:
- ❌ 相比 Custom Module 代码稍多

**何时使用**: **默认选择** - 大多数情况都适用

**示例结构**:
```
roles/tailscale/
├── tasks/
│   ├── main.yml         # 主安装逻辑
│   └── serve.yml        # 独立的 Serve 配置逻辑
├── defaults/main.yml
├── templates/
└── handlers/main.yml
```

### 3.4 Separate Role

**定义**: 为特定功能创建专门的 Role。

**位置**: `roles/<feature>/`

**优点**:
- ✅ 功能完全独立
- ✅ 可在任何 Playbook 中复用

**缺点**:
- ❌ 相关文件分散
- ❌ 维护时需要跨多个文件夹

**何时使用**: 当功能与主 Role 关系不大，需要在多个上下文中独立使用时。

### 3.5 抽象选择决策树

```
功能逻辑可用现有模块表达？
├─ 是 → 直接使用 Inline Tasks
└─ 否 → 是否需要复杂的状态管理？
    ├─ 是 → Custom Module
    └─ 否 → tasks_from（推荐）或 Separate Role
            └─ 是否与其他服务紧密相关？
                ├─ 是 → tasks_from
                └─ 否 → Separate Role
```

---

## 第四部分：Tags 和变量作用域

### 4.1 Tags 的核心机制

**Tags** 是 Ansible 的任务过滤机制。

```bash
# 运行所有任务
ansible-playbook deploy-service.yml

# 仅运行带 verify 标签的任务（跳过其他所有任务）
ansible-playbook deploy-service.yml --tags verify

# 跳过验证任务
ansible-playbook deploy-service.yml --skip-tags verify
```

### 4.2 变量依赖和标签的陷阱

**问题场景**:

```yaml
- name: Check Docker service status
  systemd:
    name: docker
  register: docker_status
  # ❌ 没有加标签

- name: Display deployment summary
  debug:
    msg: "Docker Status: {{ docker_status.status.ActiveState }}"
  tags: [summary]  # ✅ 有标签
```

运行 `--tags summary` 时报错：

```
fatal: [host]: FAILED! => {"msg": "The task includes an option with an undefined variable. 'docker_status' is undefined"}
```

**根本原因**:

`--tags` 是**过滤器**，不仅运行带标签的任务，还会**跳过没有标签的任务**。如果任务 B 依赖任务 A 生成的变量，但任务 A 被跳过，变量就不会存在。

**形象比喻 - 餐厅点单**:
- 任务 A (做菜) → 生成 "菜品"（变量）
- 任务 B (结账) → 根据 "菜品" 计算价格
- 用户说 "我只要账单" (`--tags summary`)
- **结果**: 服务员无法结账，因为菜都没做！

### 4.3 解决方案

#### 方案一：级联打标签（推荐）

给所有产生数据的任务也加上标签：

```yaml
- name: Check Docker service status
  systemd:
    name: docker
  register: docker_status
  tags: [summary]  # ✅ 加上标签

- name: Count running containers
  shell: docker compose ps --status running | grep -c "Up" || true
  register: running_count
  changed_when: false
  tags: [summary]  # ✅ 加上标签

- name: Display deployment summary
  debug:
    msg:
      - "Docker Status: {{ docker_status.status.ActiveState }}"
      - "Running Containers: {{ running_count.stdout }}"
  tags: [summary]
```

现在运行 `--tags summary` 时，所有三个任务都会执行，变量链条完整。

#### 方案二：使用 `always` 标签

对于必须每次都运行的任务（如核心检查）：

```yaml
- name: Gather critical facts
  systemd:
    name: docker
  register: docker_status
  tags: [always]  # 即使指定其他标签也会运行
```

带 `always` 标签的任务在指定其他 tag 时仍会执行（除非显式 `--skip-tags always`）。

### 4.4 标签规划建议

```yaml
# 标准的两段式 Playbook 结构
- name: Deploy Service
  hosts: target
  roles:
    - docker
    - service

- name: Verify Deployment
  hosts: target
  tags: [verify]        # 整个 play 加标签
  tasks:
    - name: Wait for port
      wait_for:
        port: 8080
      tags: [verify]    # 任务级也加标签（冗余但清晰）

    - name: Display summary
      debug:
        msg: "Service deployed successfully"
      tags: [verify, summary]  # 多个标签
```

### 4.5 常见标签约定

| 标签 | 用途 | 何时使用 |
|-----|------|--------|
| `verify` | 验证部署 | 所有验证任务 |
| `always` | 必须执行 | 依赖的数据生成任务 |
| `summary` | 打印摘要 | 最后的输出任务 |
| `debug` | 调试用 | 临时的 debug 任务 |
| `skip` | 标记跳过 | 需要手动启用的任务 |

---

## 第五部分：部署验证模式

### 5.1 为什么需要验证？

**问题**: 仅部署服务不足以确保其正常运行。

```yaml
❌ 不足以
- name: Deploy Service
  hosts: target
  roles:
    - service-role
```

部署完成后：
- 不知道服务是否真的启动了
- 错误可能被忽略
- 需要手动 SSH 验证

### 5.2 验证的标准结构

```yaml
# 第一段：部署
- name: Deploy Service
  hosts: target
  become: true
  roles:
    - docker
    - service

# 第二段：验证
- name: Verify Deployment
  hosts: target
  become: true
  tags: [verify]
  tasks:
    - # 验证任务
```

**好处**:
- ✅ 立即知道部署是否成功
- ✅ 可用 `--tags verify` 单独运行验证
- ✅ 可用 `--skip-tags verify` 快速部署
- ✅ 输出包含所有关键信息

### 5.3 核心验证模块

#### 5.3.1 `wait_for` - 端口就绪

**用途**: 等待端口开始监听

```yaml
- name: Wait for web server to be ready
  wait_for:
    port: 8080
    timeout: 60
```

**关键参数**:
- `port`: 目标端口
- `timeout`: 最大等待时间（秒）
- `host`: 目标主机（默认 localhost）

**教训**: 端口开放 ≠ 服务就绪，但这是必要的第一步。

#### 5.3.2 `systemd` - 服务状态

**用途**: 查询 systemd 服务的详细状态

```yaml
- name: Check Docker service status
  systemd:
    name: docker
  register: docker_status

- name: Assert Docker service is running
  assert:
    that:
      - docker_status.status.ActiveState == "active"
      - docker_status.status.SubState == "running"
    fail_msg: "❌ Docker service not running"
    success_msg: "✅ Docker is running"
```

**关键字段**:
- `ActiveState`: `active` 或 `inactive`
- `SubState`: `running`, `dead`, `exited`

#### 5.3.3 `assert` - 断言验证

**用途**: 在条件不满足时失败

```yaml
- name: Assert containers are running
  assert:
    that:
      - running_count.stdout | int >= 4
    fail_msg: "❌ Expected 4+ containers, found {{ running_count.stdout }}"
    success_msg: "✅ {{ running_count.stdout }} container(s) running"
```

**重要**: 不要在条件中使用 Jinja2 分隔符

```yaml
❌ 错误（产生警告）
that:
  - "'{{ variable }}' in result.stdout"

✅ 正确
that:
  - variable in result.stdout
```

#### 5.3.4 `uri` - HTTP 端点测试

**用途**: 测试 Web 服务是否响应

```yaml
- name: Test web interface
  uri:
    url: "http://localhost:2283"
    method: GET
    status_code: [200, 302]
    timeout: 10
  register: http_result
```

**常见状态码**:
- `200`: OK
- `302`: 重定向（常见于登录页面）
- `403`: 需要认证（对受保护 API 是正常的）

**关键教训**: 测试公开端点（登录页面、根路径），避免需要认证的 API。

```yaml
# ❌ API 通常返回 403
- uri:
    url: "http://localhost:8080/api/"
    status_code: [200]

# ✅ 测试登录页面
- uri:
    url: "http://localhost:8080/login/"
    status_code: [200]
```

#### 5.3.5 `stat` - 文件检查

**用途**: 检查文件或目录是否存在

```yaml
- name: Check share directory
  stat:
    path: "{{ share_dir }}"
  register: share_stat

- name: Assert directory exists
  assert:
    that:
      - share_stat.stat.exists
      - share_stat.stat.isdir
    fail_msg: "Share directory does not exist"
```

### 5.4 验证示例

#### 示例 1: Samba (systemd 服务)

```yaml
- name: Verify Samba
  hosts: samba
  tags: [verify]
  tasks:
    - name: Wait for SMB port
      wait_for:
        port: 445
        timeout: 30

    - name: Check smbd service
      systemd:
        name: smbd
      register: smbd_status

    - name: Test share listing
      shell: smbclient -L localhost -N
      register: smbclient_result
      changed_when: false

    - name: Verify share is accessible
      assert:
        that:
          - smbclient_result.rc == 0
          - samba_share_name in smbclient_result.stdout
        fail_msg: "Share not accessible"
        success_msg: "✅ Samba share is accessible"
```

#### 示例 2: Docker Compose (Immich)

```yaml
- name: Verify Immich Deployment
  hosts: immich
  tags: [verify]
  tasks:
    - name: Check Docker service
      systemd:
        name: docker
      register: docker_status

    - name: Wait for web server
      wait_for:
        port: 2283
        timeout: 60

    - name: Count running containers
      shell: docker compose ps --status running | grep -c "Up" || true
      args:
        chdir: "{{ immich_app_dir }}"
      register: running_count
      changed_when: false

    - name: Test database connectivity
      command: >
        docker compose exec -T immich-server
        sh -c 'pg_isready -h immich_postgres -U {{ db_user }}'
      args:
        chdir: "{{ immich_app_dir }}"
      register: db_check
      changed_when: false
      failed_when: false

    - name: Assert deployment successful
      assert:
        that:
          - docker_status.status.ActiveState == "active"
          - running_count.stdout | int >= 4
          - db_check.rc == 0
        fail_msg: |
          Deployment verification failed:
          - Docker: {{ docker_status.status.ActiveState }}
          - Containers: {{ running_count.stdout }}
          - Database: {{ db_check.rc }}
        success_msg: "✅ Immich deployment successful"
```

### 5.5 输出最佳实践

提供清晰的部署摘要，包含关键信息：

```yaml
- name: Display deployment summary
  debug:
    msg:
      - "========================================="
      - "✅ Service Deployment Successful"
      - "========================================="
      - "Docker Status: {{ docker_status.status.ActiveState }}"
      - "Running Containers: {{ running_count.stdout }}"
      - "Web Interface: http://{{ ansible_host }}:8080"
      - "API Endpoint: http://{{ ansible_host }}:8080/api/"
      - "Database Status: Connected"
      - "Admin User: {{ admin_username }}"
      - "Password: {{ admin_password }}"
      - "========================================="
  tags: [verify]
```

**包含登录凭据的理由**（Homelab 环境）:
- 部署完成后立即可以测试
- 减少查找文档的时间
- 方便性 > 安全性（homelab 环境）

对于生产环境，应该避免输出明文密码，使用 `no_log: true`。

### 5.6 验证时间参考

| 服务 | 端口 | 特点 | 预计时间 |
|------|------|------|---------|
| Samba (systemd) | 445, 139 | 快速 | ~30s |
| Anki (systemd) | 8080 | 简单 | ~30s |
| Immich (Docker) | 2283 | 含数据库 | ~60s |
| Netbox (Docker) | 8080 | 多容器+健康检查 | ~90s |

---

## 第六部分：常见陷阱和故障排查

### 6.1 Inventory 迁移陷阱

#### 问题：从静态到动态 Inventory 的数据丢失

**场景**: 从 Static Inventory (YAML 文件) 迁移到 Dynamic Inventory (Terraform 状态)

```yaml
# 旧结构（混合了两种数据）
# inventory/pve_lxc/caddy.yml
caddy:
  hosts:
    caddy:
      ansible_host: 192.168.1.105        # 基础设施信息
      caddy_reverse_proxies:             # 应用配置
        - subdomain: netbox
          target: http://192.168.1.102:8000
```

迁移后删除了这个文件，认为 Terraform 已经接管了 Inventory。结果：**`caddy_reverse_proxies` 配置丢失**！

#### 根本原因

**需要区分两个概念**:

| 概念 | 定义 | 示例 | 来源 |
|------|------|------|------|
| **寻址 (Addressing)** | 机器在哪里 | `ansible_host: 192.168.1.105` | Terraform（基础设施） |
| **配置 (Configuration)** | 机器上运行什么 | `caddy_reverse_proxies: [...]` | Ansible Inventory（应用） |

Terraform 负责**寻址**，Ansible 负责**配置**。Terraform 永远不会知道 `caddy_reverse_proxies` 是什么。

#### 解决方案：迁移黄金法则

> **"Don't delete the file, migrate the vars."**
> 不要直接删除文件，要先迁移变量。

**迁移步骤**:

1. 检查静态 Inventory 文件中有哪些变量
2. 将应用配置变量（非 `ansible_host`、`ansible_user`）提取到 `host_vars/`
3. 删除静态文件之前，确保所有配置都已迁移

**示例**:

```yaml
# 新结构（完全分离）
# inventory/terraform.yml (动态，仅包含寻址)
caddy:
  hosts:
    caddy:
      ansible_host: 192.168.1.105  # Terraform 提供

# inventory/host_vars/caddy.yml (静态，包含配置)
caddy_reverse_proxies:  # 从静态文件迁移过来
  - subdomain: netbox
    target: http://192.168.1.102:8000
```

#### 关键教训

- 删除旧 Inventory 文件前必须做 Audit
- 使用 `ansible-inventory --host <hostname>` 验证变量迁移
- 在静态文件删除前，确保所有配置都已在 `host_vars` 中

### 6.2 Ansible 输出格式问题

#### 问题：YAML 回调插件被移除

**症状**: 收到错误

```
The 'community.general.yaml' callback plugin has been removed.
```

**原因**: Ansible Core 2.13+ 移除了外部回调插件，`stdout_callback = yaml` 不再工作。

#### 解决方案

现代 Ansible 使用 `default` 插件，通过 `callback_result_format` 参数配置输出格式：

```ini
# ansible.cfg
[defaults]
stdout_callback = default
callback_result_format = yaml
bin_ansible_callbacks = True  # 推荐：允许 ad-hoc 命令也使用此回调
```

**关键**: 注意配置键位置
- `default` 插件的配置在 `[defaults]` 节下（特例）
- 普通插件使用 `[callback_<name>]` 节

### 6.3 DevContainer 依赖缺失

#### 问题：Python 库和 Ansible 集合缺失

**症状 1**: `password_hash` 过滤器失败

```
ERROR! Unexpected failure during Ansible execution: No module named 'passlib'
```

**原因**: `password_hash` 过滤器调用 Python 的 `passlib` 库。

**症状 2**: `sysctl` 模块不存在

```
ERROR! couldn't resolve module/action 'ansible.posix.sysctl'
```

**原因**: `sysctl` 被移出 Ansible Core，现在在 `ansible.posix` 集合中。

#### 解决方案

显式声明依赖：

**requirements.txt** (Python 库):
```
ansible>=2.13
passlib>=1.7.4
pyyaml>=5.4
```

**requirements.yml** (Ansible 集合):
```yaml
---
collections:
  - name: ansible.posix
  - name: community.general
  - name: community.docker
```

安装依赖：
```bash
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml
```

**关键教训**: Infrastructure as Code 必须可复制。不能依赖"环境里正好有"某个包。

### 6.4 命令存在检测

#### 问题：检测命令是否存在的错误方式

**❌ 错误做法**:

```yaml
- name: Check if Tailscale is installed
  command: tailscale --version
  register: check_result
```

后果：
- 如果未安装，系统报 "No such file or directory"
- Python 抛出异常（Traceback）
- 输出非常难看且吓人

**✅ 正确做法**:

```yaml
- name: Check if Tailscale is installed
  shell: command -v tailscale
  register: check_result
  ignore_errors: true
  changed_when: false
```

后果：
- 如果未安装，Shell 返回非零退出码
- Ansible 优雅地捕获错误
- 无任何异常输出

**关键点**:
- 使用 `shell: command -v <binary>` 进行检测
- 添加 `ignore_errors: true` 处理不存在的情况
- 添加 `changed_when: false` 因为这是只读检查

### 6.5 验证步骤中的最佳实践

#### 关键 1：`changed_when: false`

验证任务是只读的，不应该报告 "changed"：

```yaml
- name: Check service status
  command: systemctl status myservice
  register: status_result
  changed_when: false  # 必须！
```

#### 关键 2：超时时间要合理

| 场景 | 超时时间 | 原因 |
|------|--------|------|
| systemd 服务 | 30s | 快速启动 |
| 简单 Docker 服务 | 60s | 镜像拉取 + 启动 |
| 复杂 Docker Compose | 120s | 多容器协调 + 初始化 |

#### 关键 3：容器健康检查

不要仅检查 "Up" 状态，要检查 "healthy" 状态：

```yaml
❌ 不够
docker compose ps | grep "Up"

✅ 正确
docker compose ps | grep -E "service.*healthy"
```

#### 关键 4：数据库是常见故障点

所有关键服务都应单独测试数据库连接：

```yaml
- name: Test database connectivity
  command: pg_isready -h {{ db_host }} -U {{ db_user }} -d {{ db_name }}
  register: db_check
  changed_when: false
  failed_when: false

- name: Assert database is ready
  assert:
    that:
      - db_check.rc == 0
    fail_msg: "❌ Database is not accessible"
    success_msg: "✅ Database is accepting connections"
```

---

## 第七部分：Playbook 模块化最佳实践

### 7.1 从单体到模块化

**重构前**（所有逻辑在 Playbook）:

```yaml
- name: Install Docker Engine on VM
  hosts: vm
  tasks:
    - # 50+ 行 Docker 安装任务

- name: Deploy Service stack
  hosts: vm
  tasks:
    - # 40+ 行服务部署任务
```

**问题**:
- Playbook 变得臃肿
- 重复代码多
- 难以维护和复用

**重构后**（标准 Role 模式）:

```yaml
- name: Deploy Service
  hosts: vm
  become: true
  roles:
    - docker     # 关注点分离
    - service    # 易于复用
```

**Role 结构**:

```
roles/service/
├── defaults/main.yml      # 默认变量
├── tasks/main.yml         # 部署逻辑
├── templates/config.j2    # 配置模板
├── handlers/main.yml      # 重启等处理
└── files/                 # 静态文件
```

### 7.2 Role 职责清晰化

**单一职责原则**:
- `docker` role: 仅安装和配置 Docker
- `service` role: 部署特定服务（使用 Docker）
- 不要在 `docker` role 中做服务部署

### 7.3 Role 参数化

使用变量使 Role 通用化：

```yaml
# roles/docker/tasks/main.yml
- name: Install Docker
  package:
    name: docker.io
    state: present

# roles/service/tasks/main.yml
- name: Start service container
  docker_container:
    name: "{{ service_name }}"
    image: "{{ service_image }}"
    ports:
      - "{{ service_port }}:{{ service_port }}"
```

在 Playbook 中注入变量：

```yaml
- name: Deploy Immich
  hosts: immich
  become: true
  vars:
    service_name: immich
    service_image: "{{ immich_image }}"
    service_port: 2283
  roles:
    - service
```

---

## 第八部分：参考和最佳实践速查表

### 8.1 快速参考

#### Inventory 结构
```bash
# 验证组结构
ansible-inventory --graph

# 验证特定主机的变量
ansible <hostname> -m debug -a "var=variable_name"
```

#### Vault 操作
```bash
# 创建新 Vault 文件
ansible-vault create inventory/group_vars/all/vault.yml

# 编辑 Vault
ansible-vault edit inventory/group_vars/all/vault.yml

# 查看 Vault
ansible-vault view inventory/group_vars/all/vault.yml

# 加密现有文件
ansible-vault encrypt vars.yml

# 解密文件
ansible-vault decrypt vars.yml
```

#### Playbook 执行
```bash
# 完整执行
ansible-playbook playbooks/deploy.yml

# 仅运行验证
ansible-playbook playbooks/deploy.yml --tags verify

# 跳过验证
ansible-playbook playbooks/deploy.yml --skip-tags verify

# 列出所有标签
ansible-playbook playbooks/deploy.yml --list-tags

# Dry-run
ansible-playbook playbooks/deploy.yml --check
```

### 8.2 检查清单

**在删除 Inventory 文件前**:
- [ ] 确认所有变量已迁移到 `host_vars/`
- [ ] 运行 `ansible-inventory --host <name>` 验证
- [ ] 检查 Git diff 以确认没有遗漏

**在创建新 Role 前**:
- [ ] 确认无法用现有模块完成
- [ ] 考虑使用 `tasks_from` 而不是 Separate Role
- [ ] 定义清晰的 Role 职责

**在部署到生产前**:
- [ ] 添加验证步骤
- [ ] 测试 `--tags verify` 和 `--skip-tags verify`
- [ ] 检查 Vault 中敏感信息是否已加密
- [ ] 确认 `.vault_pass` 在 `.gitignore` 中

### 8.3 常见问题速解

| 问题 | 症状 | 解决方案 |
|------|------|--------|
| 变量未定义 | `undefined variable` 错误 | 检查 tags 链条，确保依赖任务也有标签 |
| Vault 密码错误 | `vault password was incorrect` | 检查 `.vault_pass` 文件内容和权限 |
| 命令找不到 | `No such file or directory` | 使用 `shell: command -v` 而不是 `command:` |
| 容器启动缓慢 | 验证超时 | 增加 `wait_for` 的 timeout 参数 |
| 组名冲突 | Inventory 加载失败 | 检查目录名和 `group_vars` 文件名是否一致 |

---

## 总结

### 核心原则

1. **单一职责**: 每个文件、每个 Role、每个任务只做一件事
2. **一致性**: 命名、结构、标签要保持一致
3. **验证优先**: 部署必须包含验证步骤
4. **安全第一**: 敏感信息必须加密，`.vault_pass` 必须 gitignore
5. **可复制性**: IaC 必须在任何环境中可复制运行
6. **清晰的关注点分离**: 区分基础设施（Terraform）和配置（Ansible）

### 最佳实践总结

| 方面 | 最佳实践 |
|------|--------|
| **Inventory** | 完全拆分，单一职责，命名一致 |
| **Vault** | 集中管理，统一前缀，自动解密 |
| **抽象设计** | 优先 `tasks_from`，避免过度设计 |
| **Tags 策略** | 级联打标签，确保依赖链完整 |
| **验证步骤** | 两段式结构，包含汇总信息 |
| **故障排查** | 明确区分寻址和配置，迁移前审计 |
| **模块化** | 使用 Role，参数化，关注点分离 |

### 推荐阅读顺序

对于新手：
1. 第一部分 - Inventory 管理
2. 第四部分 - Tags 和变量
3. 第五部分 - 验证模式

对于进阶用户：
1. 第二部分 - Vault 管理
2. 第三部分 - 抽象设计
3. 第六部分 - 常见陷阱

---

**文档版本**: 1.0
**最后更新**: 2026-01-30
**适用范围**: Ansible 2.13+
