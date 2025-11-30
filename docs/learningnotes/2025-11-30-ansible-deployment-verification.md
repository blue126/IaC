# Ansible 部署验证模式学习笔记

**日期**: 2025年11月30日  
**主题**: 为现有服务添加自动化验证步骤

---

## 背景

在成功部署 Anki Sync Server 并添加验证步骤后，今天将相同的验证模式应用到所有现有服务：
- Samba (文件共享)
- Immich (照片管理，Docker Compose)
- Netbox (网络资产管理，Docker Compose)

同时完成了 Immich 的模块化重构，统一了所有服务的 playbook 结构。

---

## Part 1: 为什么需要验证步骤？

### 之前的问题
```yaml
- name: Deploy Service
  hosts: target
  roles:
    - service-role
```

部署完成后：
- ❌ 不知道服务是否真的启动了
- ❌ 错误可能被忽略
- ❌ 需要手动 SSH 登录检查

### 添加验证后
```yaml
- name: Deploy Service
  hosts: target
  roles:
    - service-role

- name: Verify Deployment
  hosts: target
  tags: [verify]
  tasks:
    - # 自动化验证任务
```

好处：
- ✅ 立即知道部署是否成功
- ✅ 可以单独运行验证：`--tags verify`
- ✅ 输出包含所有需要的信息（URL、用户名、密码）

---

## Part 2: 核心验证模块

### 2.1 `wait_for` - 等待端口就绪

**用途**：等待端口开始监听后再继续

```yaml
- name: Wait for Immich web server to be ready
  wait_for:
    port: 2283
    timeout: 60
```

**关键参数**：
- `port`: 要检查的端口号
- `timeout`: 最大等待时间（秒）

**教训**：端口开放 ≠ 服务就绪，但是必要的第一步

### 2.2 `systemd` - 查询服务状态

**用途**：获取 systemd 服务的详细状态

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
```

**关键字段**：
- `ActiveState`: `active` 或 `inactive`
- `SubState`: `running`, `dead`, `exited`

### 2.3 `assert` - 断言验证

**用途**：如果条件不满足就失败

```yaml
- name: Assert containers are running
  assert:
    that:
      - running_count.stdout | int > 0
    fail_msg: "❌ No containers running"
    success_msg: "✅ {{ running_count.stdout }} container(s) running"
```

**重要**: 不要在条件中使用 Jinja2 分隔符
```yaml
# ❌ 错误 (会有警告)
that:
  - "'{{ variable }}' in result.stdout"

# ✅ 正确
that:
  - variable in result.stdout
```

### 2.4 `uri` - HTTP 端点测试

**用途**：测试 Web 服务是否响应

```yaml
- name: Test Immich web interface
  uri:
    url: "http://localhost:2283"
    method: GET
    status_code: [200, 302]
    timeout: 10
  register: http_result
```

**常见状态码**：
- `200`: OK
- `302`: 重定向（通常用于登录页面）
- `403`: 需要认证（对于受保护的 API 是正常的）

### 2.5 `stat` - 文件/目录检查

**用途**：检查文件或目录是否存在

```yaml
- name: Check share directory
  stat:
    path: "{{ samba_share_dir }}"
  register: share_dir_stat

- name: Assert share directory exists
  assert:
    that:
      - share_dir_stat.stat.exists
      - share_dir_stat.stat.isdir
```

---

## Part 3: 三个服务的实际验证模式

### 3.1 Samba (systemd 服务)

**验证内容**：
1. 等待 SMB 端口 (445) 和 NetBIOS 端口 (139)
2. 检查 `smbd` 和 `nmbd` 服务状态
3. 验证共享目录存在
4. 使用 `smbclient` 测试共享可访问性

**关键命令**：
```yaml
- name: Test Samba share listing
  shell: smbclient -L localhost -N
  register: smbclient_result
  changed_when: false

- name: Verify share is listed
  assert:
    that:
      - smbclient_result.rc == 0
      - samba_share_name in smbclient_result.stdout
```

**教训**：功能测试比状态检查更有价值（share 列表验证配置正确）

### 3.2 Immich (Docker Compose)

**验证内容**：
1. 检查 Docker 服务状态
2. 等待端口 2283
3. 统计运行中的容器数量（预期 4 个）
4. 测试 HTTP 端点
5. 测试 PostgreSQL 数据库连接

**关键命令**：
```yaml
- name: Count running containers
  shell: docker compose ps --status running | grep -c "Up" || true
  args:
    chdir: "{{ immich_app_dir }}"
  register: running_count
  changed_when: false

- name: Test database connectivity
  command: >
    docker compose exec -T immich-server 
    sh -c 'pg_isready -h immich_postgres -U {{ immich_db_username }}'
  args:
    chdir: "{{ immich_app_dir }}"
  register: db_check
  changed_when: false
  failed_when: false
```

**教训**：
- 容器运行 ≠ 应用就绪，要测试实际功能
- 数据库检查很重要，是常见故障点

### 3.3 Netbox (Docker Compose + Health Checks)

**验证内容**：
1. 检查 Docker 服务状态
2. 等待端口 8080
3. 检查容器健康状态（6 个 healthy 容器）
4. 测试根路径和登录页面
5. 测试 PostgreSQL 数据库连接

**特殊之处**：
```yaml
- name: Check for healthy containers
  shell: docker compose ps | grep -E "netbox.*healthy" | wc -l
  args:
    chdir: /opt/netbox-docker
  register: healthy_count
```

**关键教训 - API 认证问题**：
```yaml
# ❌ 最初尝试测试 API（返回 403）
- name: Test Netbox API endpoint
  uri:
    url: "http://localhost:8080/api/"
    status_code: [200]  # 失败，返回 403

# ✅ 改为测试公开的登录页面
- name: Test Netbox login page
  uri:
    url: "http://localhost:8080/login/"
    status_code: [200]  # 成功
```

**教训**：403 不一定是错误，可能是正常的认证要求。应该测试不需要认证的端点。

---

## Part 4: Playbook 结构

### 标准两段式结构

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

### 使用 tags 的好处

**完整部署 + 验证**：
```bash
ansible-playbook playbooks/deploy-service.yml
```

**仅运行验证**（手动修改后检查）：
```bash
ansible-playbook playbooks/deploy-service.yml --tags verify
```

**跳过验证**（开发环境快速部署）：
```bash
ansible-playbook playbooks/deploy-service.yml --skip-tags verify
```

---

## Part 5: 输出信息最佳实践

### 提供完整的部署摘要

```yaml
- name: Display deployment summary
  debug:
    msg:
      - "========================================="
      - "✅ Netbox Deployment Successful"
      - "========================================="
      - "Docker Status: {{ docker_status.status.ActiveState }}"
      - "Healthy Containers: {{ healthy_count.stdout }}"
      - "Web Server Port (8080): Listening"
      - "HTTP Status: {{ netbox_http_result.status }}"
      - "Login Page Status: {{ netbox_login_result.status }}"
      - "Database: Connected"
      - "Web Interface: http://{{ ansible_host }}:8080"
      - "API Endpoint: http://{{ ansible_host }}:8080/api/"
      - "Superuser: {{ netbox_superuser_name }}"
      - "Password: {{ netbox_superuser_password }}"
      - "Install Directory: {{ netbox_install_dir }}"
      - "========================================="
```

**为什么包含用户名密码**：
- 部署完成后立即可以登录测试
- 减少查找文档和配置文件的时间
- 对于 homelab 环境，方便性 > 安全性

---

## Part 6: Immich 模块化重构

### 重构前（所有逻辑在 playbook）

```yaml
- name: Install Docker Engine on Immich VM
  hosts: immich-node
  tasks:
    - # 50+ 行 Docker 安装任务

- name: Deploy Immich stack
  hosts: immich-node
  tasks:
    - # 40+ 行 Immich 部署任务
```

### 重构后（标准 role 模式）

```yaml
- name: Deploy Immich Service
  hosts: immich-node
  become: true
  roles:
    - docker
    - immich
```

**创建的 role 结构**：
```
roles/immich/
├── defaults/main.yml      # 默认变量
├── tasks/main.yml         # 部署任务
├── templates/env.j2       # 环境配置模板
└── handlers/main.yml      # 配置变更时重启
```

**好处**：
- ✅ 与 Samba/Netbox 保持一致
- ✅ 可重用（可以部署多个 Immich 实例）
- ✅ 清晰的关注点分离
- ✅ 更容易维护和测试

---

## Part 7: 实践中的关键教训

### 1. **容器健康检查的重要性**

Netbox 使用 Docker health checks，必须等待 "healthy" 状态：
```yaml
# ❌ 不够
docker compose ps | grep "Up"

# ✅ 正确
docker compose ps | grep -E "netbox.*healthy"
```

### 2. **数据库是常见故障点**

所有三个服务都单独测试了数据库连接：
```yaml
- name: Test database connectivity
  command: pg_isready -h <host> -U <user> -d <database>
```

### 3. **changed_when: false 是必须的**

验证任务是只读的，不应该报告 "changed"：
```yaml
- name: Check service status
  command: systemctl status myservice
  register: status_result
  changed_when: false  # 重要！
```

### 4. **超时时间要合理**

- 简单服务 (Samba): 30 秒
- Docker Compose (Immich): 60 秒
- 复杂 Docker Compose (Netbox): 60-120 秒

### 5. **公开端点 vs 受保护端点**

不是所有端点都适合健康检查：
- ✅ 登录页面、根路径（公开）
- ❌ API 端点可能需要认证

### 6. **错误消息要清晰**

```yaml
# ❌ 不好
fail_msg: "Failed"

# ✅ 好
fail_msg: "❌ PostgreSQL database is not accessible"
success_msg: "✅ PostgreSQL database is accepting connections"
```

---

## Part 8: 验证步骤对比

| 服务 | 端口 | systemd 服务 | 容器数 | 特殊检查 | 验证时间 |
|------|------|-------------|--------|---------|---------|
| Samba | 445, 139 | smbd, nmbd | - | smbclient 列表 | ~30s |
| Immich | 2283 | docker | 4 | PostgreSQL | ~60s |
| Netbox | 8080 | docker | 6 | Health checks, PostgreSQL | ~90s |
| Anki | 8080 | anki-sync-server | - | HTTP ping | ~30s |

---

## Part 9: 下一步

1. ✅ 所有服务都有验证步骤
2. ✅ Immich 完成模块化
3. ⏭️ 可以考虑：
   - 定期健康检查 cron job
   - 监控系统集成
   - 性能基准测试

---

## 总结

**核心收获**：
1. 验证应该是部署的标准组成部分，不是可选项
2. 使用 `tags: [verify]` 实现灵活的验证策略
3. 测试实际功能，不只是进程状态
4. 清晰的输出信息（包括登录凭据）节省时间
5. 模块化让所有服务保持一致的结构

**验证模式已应用到**：
- ✅ Anki Sync Server
- ✅ Samba
- ✅ Immich
- ✅ Netbox

所有服务现在都可以用 `--tags verify` 独立验证健康状态。
