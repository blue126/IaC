# Gitea Role 设计文档

**Last Updated**: 2026-03-02
**Status**: ✅ Implemented & Reviewed
**Owner**: Homelab IaC Project

## 背景

`jenkins` 主机（LXC 107, `192.168.1.107`）上计划运行 Gitea，作为内网私有 Git 服务，替代手动操作。目前存在一份手动安装步骤（Phase 1-6），涵盖：二进制下载、systemd 配置、Web 初始化向导、GitHub Push Mirror、Jenkins Webhook 集成。

本文档描述将 Gitea 安装以独立 role（`gitea`）纳入 Ansible 管理的设计方案，将手动步骤全部自动化，并跳过需要浏览器操作的 Web 安装向导。

## 设计目标

1. **无人值守安装** — 通过预置 `app.ini`（`INSTALL_LOCK = true`）跳过 Web 向导，管理员账号由 CLI 创建
2. **幂等性** — 重复执行 playbook 不应重建用户或重置配置，SECRET_KEY 在再次运行时保留
3. **配置即代码** — `app.ini` 以 Jinja2 模板管理，版本号和路径可覆盖
4. **与 jenkins role 共存** — 部署到同一主机，互不干扰

## 服务信息

| 属性 | 值 |
|------|----|
| **主机** | `jenkins` (LXC 107, `192.168.1.107`) |
| **运行用户** | `git`（系统用户，shell = `/usr/sbin/nologin`） |
| **Web 端口** | `3000` |
| **SSH 端口** | `2222`（避免与主机 SSH 端口 22 冲突） |
| **二进制路径** | `/usr/local/bin/gitea` |
| **数据目录** | `/var/lib/gitea/{custom,data,log}`（owner: git:git, mode: 750） |
| **配置目录** | `/etc/gitea`（owner: root:git, mode: **750**） |
| **数据库** | SQLite3（文件位于 `/var/lib/gitea/data/gitea.db`） |

## Role 结构

```
roles/gitea/
├── defaults/main.yml           # 默认变量
├── handlers/main.yml           # 服务重启 handler
├── tasks/main.yml              # 主任务
└── templates/
    ├── app.ini.j2              # Gitea 配置文件
    └── gitea.service.j2        # systemd service 文件
```

## 变量设计

### `defaults/main.yml`

```yaml
gitea_version: "1.23.7"
gitea_user: git
gitea_group: git
gitea_work_dir: /var/lib/gitea
gitea_config_dir: /etc/gitea
gitea_binary_path: /usr/local/bin/gitea
gitea_http_port: 3000
gitea_ssh_port: 2222
gitea_domain: "{{ ansible_host }}"
gitea_protocol: http          # 接 Caddy 时在 host_vars 改为 https
gitea_root_url: "{{ gitea_protocol }}://{{ gitea_domain }}:{{ gitea_http_port }}/"
                              # 接反代时直接覆盖：gitea_root_url: https://gitea.willfan.me
gitea_db_type: sqlite3
gitea_admin_user: admin
gitea_admin_email: admin@willfan.me

# 管理员密码（vault 间接引用）
gitea_admin_password: "{{ vault_gitea_admin_password }}"
```

> 敏感变量 `vault_gitea_admin_password` 存储于 `inventory/group_vars/all/vault.yml`，通过间接引用传递。

## 任务流程

```
创建 git 系统 group（先于 user，避免 group 不存在报错）
  ↓
创建 git 系统用户（shell=/usr/sbin/nologin，禁止交互登录）
  ↓
创建目录结构
  /var/lib/gitea/{custom,data,log}   owner: git:git   mode: 750
  /etc/gitea                          owner: root:git  mode: 750（仅 root 可写）
  ↓
下载 Gitea 二进制（附 SHA256 checksum 校验，版本升级时 checksum 不匹配自动重新下载）
  get_url: https://dl.gitea.com/gitea/{{ gitea_version }}/...
  checksum: sha256:<url>   mode: 0755
  ↓ (若有变更，触发 handler)
处理 SECRET_KEY / INTERNAL_TOKEN（幂等）
  若 app.ini 已存在 → 从文件读取现有值（no_log: true）
  若 app.ini 不存在 → gitea generate secret 生成新值（no_log: true）
  ↓
部署 app.ini（含 INSTALL_LOCK=true、SECRET_KEY、INTERNAL_TOKEN）
  template: app.ini.j2 → /etc/gitea/app.ini  owner: root:git  mode: 640
  ↓ (若有变更，触发 handler)
部署 systemd service（含 NoNewPrivileges、PrivateTmp）
  template: gitea.service.j2 → /etc/systemd/system/gitea.service
  ↓
启用并启动 gitea 服务
  systemd: enabled=yes state=started daemon_reload=yes
  ↓
等待服务就绪
  wait_for: port={{ gitea_http_port }} timeout=30
  ↓
创建管理员账号（幂等精确匹配）
  检查：admin user list | awk 'NR>1{print $2}' | grep -qxF admin
  若不存在：admin user create ... （no_log: true）
```

## 模板设计

### `templates/app.ini.j2`

```ini
; RUN_USER/RUN_MODE 在全局段（段头之前），go-ini 不将 [DEFAULT] 视为全局段
RUN_USER = {{ gitea_user }}
RUN_MODE = prod

[server]
DOMAIN           = {{ gitea_domain }}
HTTP_PORT        = {{ gitea_http_port }}
ROOT_URL         = {{ gitea_root_url }}
SSH_PORT         = {{ gitea_ssh_port }}
SSH_LISTEN_PORT  = {{ gitea_ssh_port }}
START_SSH_SERVER = true

[database]
DB_TYPE = {{ gitea_db_type }}
PATH    = {{ gitea_work_dir }}/data/gitea.db

[repository]
ROOT = {{ gitea_work_dir }}/data/repositories

[log]
ROOT_PATH = {{ gitea_work_dir }}/log

[security]
INSTALL_LOCK   = true
SECRET_KEY     = {{ gitea_secret_key }}     ; 首次运行生成，后续运行读取保留
INTERNAL_TOKEN = {{ gitea_internal_token }}  ; 同上

[service]
DISABLE_REGISTRATION = true
```

### `templates/gitea.service.j2`

```ini
[Unit]
Description=Gitea (Git with a cup of tea)
After=network.target

[Service]
Type=simple
User={{ gitea_user }}
Group={{ gitea_group }}
WorkingDirectory={{ gitea_work_dir }}
ExecStart={{ gitea_binary_path }} web --config {{ gitea_config_dir }}/app.ini
Restart=always
RestartSec=5s
Environment=USER={{ gitea_user }} HOME=/home/{{ gitea_user }} GITEA_WORK_DIR={{ gitea_work_dir }}
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

## 与现有架构的集成

### `playbooks/deploy-gitea.yml`

```yaml
- name: Deploy Gitea
  hosts: jenkins
  gather_facts: true
  become: true
  roles:
    - common    # 与其他 deploy playbook 保持一致
    - gitea

# 注：verify play 的端口值硬编码（3000/2222），
# 因为 role defaults 不跨 play 传递。若覆盖端口需同步修改此处。
- name: Verify Gitea Deployment
  hosts: jenkins
  gather_facts: false
  become: true
  tags: [verify]
  tasks:
    - name: Wait for Gitea web port
      wait_for: { port: 3000, timeout: 30 }
    - name: Check Gitea HTTP endpoint
      uri: { url: "http://localhost:3000", status_code: [200, 301, 302] }
    - name: Assert Gitea is running
      assert:
        that: gitea_svc.status.ActiveState == "active"
```

### `playbooks/deploy-jenkins.yml` 无需改动

Gitea 使用独立 playbook，两个 role 分别部署到同一 `jenkins` 主机，互不依赖。

## Vault 密钥

在 `inventory/group_vars/all/vault.yml` 中新增（通过 `ansible-vault edit`）：

```yaml
vault_gitea_admin_password: "<strong-password>"
```

`gitea_admin_password` 已在 `defaults/main.yml` 中定义为 `{{ vault_gitea_admin_password }}`，无需额外 vars 文件。

## 幂等性处理

| 操作 | 幂等策略 |
|------|---------|
| 创建 `git` group/user | `group`/`user` 模块，`state: present` |
| 下载二进制 | `get_url` + `checksum`：文件存在且 checksum 匹配则跳过；版本升级时 checksum 不匹配自动重下 |
| SECRET_KEY / INTERNAL_TOKEN | app.ini 已存在则读取现有值，不存在则生成；渲染到模板后不再变化 |
| 部署 `app.ini` | `template` 模块，内容不变则 skip，变更才 notify handler |
| 创建管理员账号 | `awk + grep -qxF` 精确匹配用户名，存在则跳过 |

## 安全设计

| 关注点 | 措施 |
|--------|------|
| 密码日志泄露 | `no_log: true` 覆盖 set_fact（secrets）和 admin user create |
| 配置目录可写性 | `/etc/gitea` mode `0750`，git 组只读；`app.ini` mode `0640` |
| 服务账号权限 | shell = `/usr/sbin/nologin`，禁止交互登录 |
| 二进制完整性 | `get_url checksum` 验证 SHA256，防止下载篡改 |
| 服务隔离 | systemd `NoNewPrivileges=true` + `PrivateTmp=true` |
| 反代支持 | `gitea_root_url` 可覆盖，接 Caddy HTTPS 时设 `https://gitea.willfan.me` |

## 与 ansible-role-architecture.md 的一致性检查

| 原则 | 本设计 |
|------|--------|
| 单一职责 | ✅ gitea role 只管 Gitea 安装与配置 |
| 可覆盖的默认值 | ✅ 所有变量在 `defaults/main.yml` 定义 |
| 透明的依赖关系 | ✅ 无隐式依赖，与 jenkins role 并列使用 |
| 安全的密钥管理 | ✅ 管理员密码通过 vault 间接引用，secrets 全程 no_log |

## 验证命令

```bash
cd /workspaces/IaC/ansible
ansible-playbook playbooks/deploy-gitea.yml --tags verify
```

预期结果：
- `gitea` 服务状态为 `active`
- 端口 3000 HTTP 可达（状态码 200）
- 管理员账号可登录

## 与原手动方案的对应关系

| 原 Phase | Ansible 实现 |
|---------|-------------|
| Phase 1：二进制安装 + systemd | `tasks/main.yml`（group/user、目录、`get_url`+checksum、模板、`systemd`） |
| Phase 2：Web 安装向导 | **跳过** — `INSTALL_LOCK = true`，SECRET_KEY 自动生成，管理员由 CLI 创建 |
| Phase 3：Mac 推送配置 | 不在 IaC 范围（本地 git remote 配置） |
| Phase 4：GitHub Push Mirror | 不在 IaC 范围（Gitea Web UI 操作，可后续用 Gitea API 自动化） |
| Phase 5-6：Jenkins + Jenkinsfile | 不在 IaC 范围（Jenkins 配置 + 项目代码） |
