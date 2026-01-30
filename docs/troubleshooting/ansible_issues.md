# Ansible 故障排查 (Ansible Troubleshooting)

本文档汇总了在使用 Ansible 进行配置管理和自动化部署时遇到的典型问题。

**来源**:
- `/mnt/docs/learningnotes/2026-01-29-ansible-troubleshooting.md`
- `/mnt/docs/learningnotes/2026-01-29-inventory-migration-trap.md`

---

## 问题 1: Ansible 回调插件 (Callback) 报错

### 症状
```
ERROR! The 'community.general.yaml' callback plugin has been removed.
```

### 诊断步骤
1. 检查 Ansible 版本：
   ```bash
   ansible --version
   ```
2. 查看 `ansible.cfg` 中的 `stdout_callback` 设置：
   ```bash
   grep stdout_callback ansible.cfg
   ```
3. 检查是否安装了 `community.general` 集合：
   ```bash
   ansible-galaxy collection list | grep community.general
   ```

### 原因分析
- **旧版本 Ansible** (Core < 2.13) 使用 `community.general.yaml` 插件
- **Ansible Core 2.13+** 移除了许多外部插件，转而依赖内置的 `default` 插件
- 内置 `default` 插件通过配置参数支持 YAML 输出格式

### 解决方案

更新 `ansible.cfg`：

```ini
[defaults]
# 使用内置的 default 插件（不需要额外安装）
stdout_callback = default

# 关键配置：输出格式为 YAML（处理多行字符串）
callback_result_format = yaml

# 可选：允许 ad-hoc 命令也使用此回调
bin_ansible_callbacks = True
```

**关键点**: 虽然 `callback_result_format` 是插件配置，但对于 `default` 插件，它的配置键直接位于 `[defaults]` 节（这是最容易踩坑的地方）。

**对比其他插件**:
```ini
# 普通插件的配置方式（不适用于 default）
[callback_custom_plugin]
option_key = value

# default 插件的配置方式（特殊）
[defaults]
callback_result_format = yaml  # 直接在 defaults 下
```

---

## 问题 2: DevContainer 环境依赖缺失

### 症状 A: Passlib 缺失
```
fatal: [target]: FAILED! => {
  "msg": "...'passlib' is not installed..."
}
```

**触发场景**: 使用 `password_hash` 过滤器生成密码（如 Caddy WebDAV 的 bcrypt 哈希）

### 症状 B: Ansible Collections 缺失
```
fatal: [target]: FAILED! => {
  "msg": "...couldn't resolve module/action 'ansible.posix.sysctl'..."
}
```

**触发场景**: 使用 `ansible.posix` 集合中的模块（如 `sysctl`, `service` 等）

### 诊断步骤
1. 检查 Python 依赖：
   ```bash
   python3 -m pip list | grep passlib
   ```
2. 检查 Ansible 集合：
   ```bash
   ansible-galaxy collection list | grep ansible.posix
   ```
3. 查看项目的依赖文件：
   ```bash
   cat requirements.txt
   cat requirements.yml
   ```

### 原因分析

Ansible 依赖分为三层：

| 依赖类型 | 安装命令 | 典型文件 |
|---------|---------|--------|
| Python 库 | `pip install` | `requirements.txt` |
| Ansible 集合 | `ansible-galaxy collection install` | `requirements.yml` |
| System 包 | `apt-get install` | Dockerfile 或 cloud-init |

**DevContainer 问题**: DevContainer 基于 Docker 的干净环境，不会自动安装这些依赖。

### 解决方案

#### 方案 A: 创建 `requirements.txt`

```txt
# Python 依赖
passlib>=1.7.4
cryptography>=3.0
PyYAML>=5.4
```

#### 方案 B: 创建 `requirements.yml`

```yaml
# Ansible 集合依赖
collections:
  - name: ansible.posix
    version: ">=1.1.0"
  - name: community.general
    version: ">=1.0.0"
```

#### 方案 C: 更新 DevContainer 配置

在 `.devcontainer/devcontainer.json` 或 `Dockerfile` 中自动安装：

```json
{
  "postCreateCommand": "pip install -r requirements.txt && ansible-galaxy collection install -r requirements.yml"
}
```

### 最佳实践

**Infrastructure as Code 必须可复现**:

```bash
# 任何人克隆项目后，应该能一键启动
git clone <repo>
cd <repo>
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml
# 立即可用，无需手动安装
```

---

## 问题 3: 检测命令是否存在

### 症状 A: 错误做法

```yaml
- name: Check if Tailscale is installed
  command: tailscale --version
  register: check_result
```

**后果**: 如果命令不存在，Ansible 会尝试执行二进制文件，系统报 "No such file or directory"，导致 Python 抛出异常 (Traceback)，在控制台上显示非常"吓人"的错误。

### 症状 B: 正确做法

```yaml
- name: Check if Tailscale is installed
  shell: command -v tailscale
  register: check_result
  ignore_errors: true
  changed_when: false
```

**后果**: 如果没装，Shell 返回非零退出码 (RC=1)，Ansible 捕获这个码，配合 `ignore_errors: true`，优雅地跳过，没有任何报错杂音。

### 诊断步骤
1. 查看任务的输出是否有 Python Traceback
2. 检查使用的是 `command` 还是 `shell` 模块
3. 验证是否添加了 `ignore_errors: true`

### 原因分析

- **`command` 模块** - 直接执行二进制，不通过 Shell 解释器
- **Shell 内置命令** (`command -v`, `which`, `type`) - 由 Shell 处理，不存在时返回退出码，不抛异常

### 解决方案

```yaml
- name: Check if Tailscale is installed
  shell: command -v tailscale  # 使用 shell 内置命令
  register: check_result
  ignore_errors: true          # 忽略非零退出码
  changed_when: false          # 这不是一个"变更"，不影响 changed count

- name: Conditional logic based on check
  debug:
    msg: "Tailscale is installed"
  when: check_result.rc == 0

- name: Install Tailscale if not present
  apt:
    name: tailscale
    state: present
  when: check_result.rc != 0
  become: yes
```

**关键参数**:
- `ignore_errors: true` - 允许任务在失败时继续
- `changed_when: false` - 检查操作不算"变更"，保持 Play Summary 的清晰
- `check_result.rc` - 返回码 (0=成功, 非0=失败)

---

## 问题 4: 从静态到动态 Inventory 的数据丢失

### 症状
- 删除了静态 Inventory 文件（如 `inventory/pve_lxc/caddy.yml`）
- 切换到动态 Inventory (Terraform State)
- 部署后，Caddy 上的反向代理配置丢失，仅剩新配置的服务

### 诊断步骤
1. 检查删除了哪些 Inventory 文件：
   ```bash
   git log --diff-filter=D --summary | grep delete
   ```
2. 查看这些文件中是否有非 `ansible_host` 的变量：
   ```bash
   grep -v ansible_host caddy.yml
   ```
3. 验证这些变量是否已迁移到 `host_vars` 中

### 原因分析

**关键区分**:
- **基础设施数据** (Infrastructure) - 有哪些机器、IP、主机名等 → 由 Terraform 提供
- **应用配置** (Configuration) - 这些机器运行什么服务、服务的具体配置 → 由 Ansible Inventory 或 `host_vars` 提供

**误区**: 认为"Terraform 已经接管了 Inventory"就可以删除旧文件。实际上，Terraform 只提供"寻址"(Addressing)，不负责"配置"(Configuration)。

**具体例子**:

```yaml
# 旧静态 Inventory 中混合了两种数据
caddy:
  hosts:
    caddy:
      ansible_host: 192.168.1.105      # <--- 寻址 (Infrastructure)
      caddy_reverse_proxies:            # <--- 配置 (Configuration)
        - subdomain: netbox
          backend: 192.168.1.104:8080
        - subdomain: rustdesk
          backend: 192.168.1.103:21118
```

当删除这个文件时，这些反向代理配置就消失了。

### 解决方案

#### 黄金法则

> **"Don't delete the file, migrate the vars."**
> (不要直接删除文件，要先迁移变量)

#### 正确的架构

```
ansible/
├── inventory/
│   ├── terraform.yml          # 动态源：机器寻址 (Infrastructure)
│   ├── group_vars/
│   │   └── pve_lxc.yml        # 通用配置
│   └── host_vars/
│       ├── caddy.yml          # Caddy 专用配置 <--- 代理规则放这里
│       ├── netbox.yml         # Netbox 专用配置 <--- 数据库密码放这里
│       └── rustdesk.yml       # RustDesk 专用配置
```

#### 迁移步骤

**Step 1: 提取配置**

从旧的静态 Inventory 中提取非 `ansible_host` 的变量：

```bash
# 从 pve_lxc/caddy.yml 提取
cat pve_lxc/caddy.yml | grep -v ansible_host | grep -v "^caddy:" | grep -v "^  hosts:"
```

**Step 2: 创建 host_vars 文件**

```yaml
# host_vars/caddy.yml
caddy_reverse_proxies:
  - subdomain: netbox
    backend: 192.168.1.104:8080
  - subdomain: rustdesk
    backend: 192.168.1.103:21118
  - subdomain: homepage
    backend: 192.168.1.101:3000

caddy_domain: willfan.me
caddy_email: hello@willfan.me
```

**Step 3: 验证**

运行 Playbook 并检查是否生成了正确的 Caddyfile：

```bash
ansible-playbook playbooks/deploy-caddy.yml -v
```

**Step 4: 删除旧文件**

```bash
git rm pve_lxc/caddy.yml
git commit -m "Migrate static Inventory vars to host_vars"
```

### 最佳实践

#### 原则 1: 分离关切 (Separation of Concerns)

```
Terraform State (via terraform.yml)  ←→ 寻址 (Addressing)
                                         谁在哪里

host_vars / group_vars               ←→ 配置 (Configuration)
                                         他们做什么

Vault / Secrets                      ←→ 敏感信息 (Sensitive Data)
                                         密码、Token、API 密钥
```

#### 原则 2: Role 与 Inventory 分离

**Caddyfile 模板应该通用，不硬编码配置**:

```jinja2
{# roles/caddy/templates/Caddyfile.j2 #}
{% for proxy in caddy_reverse_proxies %}
{{ proxy.subdomain }}.{{ caddy_domain }} {
    reverse_proxy {{ proxy.backend }}
}
{% endfor %}
```

这样，Caddyfile 配置完全由 Inventory 驱动，Role 代码无需修改。

#### 原则 3: 显式优于隐式

```yaml
# ❌ 不好：依赖默认行为
- name: Deploy Caddy
  include_role:
    name: caddy

# ✅ 好：明确声明变量来源
- name: Deploy Caddy
  include_role:
    name: caddy
  vars:
    caddy_domain: "{{ caddy_domain }}"
    caddy_reverse_proxies: "{{ caddy_reverse_proxies }}"
```

---

## 问题 5: 模板硬编码导致 Role 不通用

### 症状
- 某个 Role (如 `caddy`) 硬编码了特定的域名或配置
- 在另一个环境或项目中复用该 Role 时，需要修改 Role 源代码

### 诊断步骤
1. 检查模板文件中是否有硬编码的值：
   ```bash
   grep -r "webdav.willfan.me" roles/
   grep -r "hello@willfan.me" roles/
   ```
2. 检查 Role 的 `defaults/main.yml` 中是否定义了变量

### 原因分析

违反了 **"开闭原则"** (Open/Closed Principle)：

- **对扩展开放** - 通过变量可以适配不同配置
- **对修改关闭** - Role 代码本身不需要修改

### 解决方案

#### 从硬编码到参数化

**Before (硬编码)**:
```jinja2
{# roles/caddy/templates/Caddyfile.j2 #}
webdav.willfan.me {
    basic_auth * {
        admin $2y$10$...
    }
    file_server browse {
        root /var/www/webdav
    }
}

acme_email = hello@willfan.me
```

**After (参数化)**:
```jinja2
{# roles/caddy/templates/Caddyfile.j2 #}
{{ caddy_webdav_domain }} {
    basic_auth * {
        admin {{ caddy_webdav_password }}
    }
    file_server browse {
        root /var/www/webdav
    }
}

acme_email = {{ caddy_email | default('hello@' + caddy_domain) }}
```

**Inventory 中定义变量** (`host_vars/caddy.yml`):
```yaml
caddy_domain: willfan.me
caddy_email: hello@willfan.me
caddy_webdav_domain: webdav.willfan.me
caddy_webdav_password: "$2y$10$..."  # 或使用密码过滤器动态生成
```

#### Role Defaults 的最佳实践

```yaml
# roles/caddy/defaults/main.yml
caddy_port: 80
caddy_https_port: 443

# 这些应该只定义默认值或空值，不是具体配置
caddy_reverse_proxies: []
caddy_domain: ""
caddy_email: ""
```

**为什么不在 defaults 中定义具体配置？**

1. **复用性** - 如果 defaults 包含具体业务逻辑，Role 就绑定到特定环境
2. **多环境** - 不同环境（Prod/Dev/Test）应该有不同的 Inventory，共享同一个 Role
3. **清晰性** - 基础设施的"地图" (Inventory) 应该清晰可见，不要隐藏在 Role 里

---

## 问题 6: 配置管理幂等性问题

### 症状
- 修改 Ansible Role 代码后，不重新运行 Playbook，问题仍然存在
- 手动在服务器上修改文件"救火"，重启后又回到旧状态

### 诊断步骤
1. 检查是否重新运行了 Playbook：
   ```bash
   ansible-playbook playbooks/deploy-*.yml -v
   ```
2. 查看 Ansible 执行历史是否包含此 task
3. 手动验证服务器上的配置是否与 Ansible 预期一致

### 原因分析

这是对 **Ansible 幂等性** 的误解。

Ansible 不会自动监测文件变更并重新应用。它只在你运行 Playbook 时执行。

**例子**:

```yaml
# docker-compose.yml 中缺少 restart 策略
# (Netbox 在重启后无法自动拉起)
services:
  netbox:
    # 没有 restart: unless-stopped
    image: netboxcommunity/netbox:v4.1.11
```

**修复方式** ❌ (临时救火，不是解决方案):

```bash
# SSH 到服务器，手动修改
docker compose up
```

**修复方式** ✅ (正确):

```yaml
# ansible/roles/netbox/tasks/main.yml
- name: Generate docker-compose.override.yml
  template:
    src: docker-compose.override.yml.j2
    dest: "{{ netbox_install_dir }}/docker-compose.override.yml"
  
# 添加 restart 策略
services:
  postgres:
    restart: unless-stopped  # 添加这行
  netbox:
    restart: unless-stopped  # 添加这行
```

```bash
# 重新运行 Playbook
ansible-playbook playbooks/deploy-netbox.yml
```

### 解决方案

**记住**: Ansible 配置修改后，**必须重新运行 Playbook 才能生效**。

建议流程：
1. 修改 Ansible Role 或 Playbook
2. 立即运行 Playbook 验证
3. 检查服务状态
4. 提交代码到 Git

不要依赖手动修改，手动修改只是临时救火，重启后会失效。

---

## 总结与最佳实践

### 记住这些要点

1. **Callback 插件** - 使用 `default` + `callback_result_format = yaml`
2. **依赖管理** - 使用 `requirements.txt` 和 `requirements.yml` 显式声明
3. **命令检测** - 用 `shell: command -v` 代替 `command` 模块
4. **Inventory 迁移** - 先迁移变量到 `host_vars`，再删除旧文件
5. **Role 设计** - Role 定义"怎么做"，Inventory 定义"做什么"
6. **模板参数化** - 避免硬编码，使用变量使 Role 通用
7. **幂等性** - Ansible 修改必须重新运行 Playbook 才能生效

### 快速参考

| 问题 | 快速修复 |
|------|---------|
| Callback 报错 | 更新 ansible.cfg，使用 `default` + `callback_result_format = yaml` |
| Passlib 缺失 | 添加 `requirements.txt`，包含 `passlib>=1.7.4` |
| Collection 缺失 | 添加 `requirements.yml`，声明 `ansible.posix` 等 |
| 命令检测出错 | 用 `shell: command -v <cmd>` + `ignore_errors: true` |
| 配置丢失 | 迁移变量到 `host_vars/<hostname>.yml` |
| Role 不通用 | 参数化模板，使用 Jinja2 变量替换硬编码值 |
| 修改不生效 | 重新运行 Playbook（`ansible-playbook playbooks/*.yml`） |

