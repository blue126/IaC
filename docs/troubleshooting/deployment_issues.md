# 部署相关问题排查 (Deployment Troubleshooting)

本文档汇总了 Docker、容器编排、应用部署等问题的排查指南。

**来源**:
- `/mnt/docs/learningnotes/2025-11-29-netbox-deployment-version-troubleshooting.md`
- `/mnt/docs/learningnotes/2026-01-29-rustdesk-deployment-lessons.md`

---

## 问题 1: Netbox 容器启动失败 - 版本兼容性

### 症状
```
django.core.exceptions.ImproperlyConfigured: 
Required parameter DATABASE is missing from configuration.
```

或

```
This is usually the result of upgrading the Docker image without upgrading 
the underlying database using "pg_upgrade"
```

或

```
unable to find user netbox: no matching entries in passwd file
```

### 环境信息
- **部署方式**: `netbox-docker` GitHub 仓库 + Ansible
- **Netbox 版本**: 4.1.11
- **netbox-docker 版本**: v3.0.2 (或 `release` 分支)

### 诊断步骤

#### Step 1: 识别版本

1. 检查 `netbox-docker` 版本：
   ```bash
   cd /opt/netbox-docker
   git branch -a
   git log --oneline -5
   ```

2. 检查 Netbox 应用版本（Docker 镜像中）：
   ```bash
   docker compose exec netbox /opt/netbox/netbox/manage.py --version
   # 或查看 docker-compose.yml 中的 image tag
   grep "image.*netbox:" docker-compose.yml
   ```

3. 查看 Postgres 版本：
   ```bash
   docker compose exec postgres postgres --version
   ```

#### Step 2: 检查配置文件

1. 查看 configuration 文件中的数据库配置：
   ```bash
   # Netbox 3.x 使用 DATABASES (复数)
   grep "DATABASES" /opt/netbox-docker/configuration/configuration.py
   
   # Netbox 4.x 使用 DATABASE (单数)
   # (会报错，因为还没有 settings.py)
   ```

2. 检查容器日志了解具体错误：
   ```bash
   docker compose logs netbox | head -100
   ```

### 原因分析

**核心问题**: `netbox-docker` 版本与 Netbox 应用版本不匹配

**版本对应关系**:

| netbox-docker 分支/版本 | Netbox 应用版本 | 配置文件 | 数据库配置键 |
|------------------------|----------------|--------|------------|
| `release` (停留在 v3.0.1) | 3.x | `configuration.py` | `DATABASES` (复数) |
| `develop` (不稳定) | 4.x (测试) | `settings.py` | `DATABASE` (单数) |
| `3.0.2` (tag) | 4.1.x | `settings.py` | `DATABASE` (单数) |

**常见错误场景**:

1. **使用 `release` 分支部署 Netbox 4.x**
   - `release` 分支的 `configuration.py` 使用 `DATABASES` (复数)
   - Netbox 4.x 的 `settings.py` 要求 `DATABASE` (单数)
   - 结果：配置参数不匹配，启动失败

2. **Postgres 版本升级冲突**
   - `release` 使用 Postgres 17
   - `develop` 使用 Postgres 18
   - 旧数据库文件与新 Postgres 版本不兼容
   - 结果：`pg_upgrade` 失败或数据损坏

3. **用户配置错误**
   - `netbox-docker v3.0.2` 的 `docker-compose.yml` 指定 `user: "netbox:root"`
   - 但 Netbox 4.1.11 镜像中不存在 `netbox` 用户，只有 `unit` 用户
   - 结果：容器启动时报 "no matching entries in passwd file"

### 解决方案

#### 方案 A: 使用稳定的 netbox-docker 版本（推荐）

```bash
# 1. 删除旧环境
cd /opt/netbox-docker
docker compose down -v  # -v 删除所有 volumes (包括数据库)

# 2. 重新克隆正确版本
cd ..
rm -rf netbox-docker
git clone https://github.com/netbox-community/netbox-docker.git
cd netbox-docker
git checkout 3.0.2  # 使用稳定的 tag 版本
```

#### 方案 B: 在 docker-compose.override.yml 中修复配置

创建 `docker-compose.override.yml` 来覆盖不兼容的设置：

```yaml
version: '3.7'

services:
  # 修复用户配置（Netbox 4.x 使用 unit 用户，不是 netbox）
  netbox:
    image: netboxcommunity/netbox:v4.1.11  # 显式指定 Netbox 版本
    user: "unit:root"                       # 修复用户
    ports:
      - "8080:8080"                         # 暴露端口
    environment:
      - SUPERUSER_NAME=admin
      - SUPERUSER_EMAIL=admin@example.com
      - SUPERUSER_PASSWORD=admin
      - SUPERUSER_API_TOKEN=0123456789abcdef0123456789abcdef01234567
    
  netbox-worker:
    image: netboxcommunity/netbox:v4.1.11  # 必须与 netbox 版本一致
    user: "unit:root"
  
  netbox-housekeeping:
    image: netboxcommunity/netbox:v4.1.11  # 必须与 netbox 版本一致
    user: "unit:root"
  
  # 配置数据库重启策略
  postgres:
    restart: unless-stopped
  
  redis:
    restart: unless-stopped
```

### 为什么要为三个容器都指定镜像版本？

**三容器架构**:
```
┌────────────┐
│   netbox   │ ← Web UI + REST API (主服务)
└────────────┘
┌────────────┐
│netbox-worker│ ← 后台任务处理 (RQ Worker)
└────────────┘
┌──────────────┐
│netbox-house  │ ← 定期维护任务 (Cron)
│  keeping     │
└──────────────┘
```

**一致性要求**:
1. **代码库一致** - 三个容器运行相同版本的代码库
2. **数据库 Schema** - Worker 和 Housekeeping 必须与主服务使用同一个 Schema 版本
3. **API 兼容性** - Worker 处理的任务格式必须与主服务兼容

**如果版本不一致**:
- Worker 无法正确反序列化任务
- Housekeeping 脚本与数据库 Schema 不匹配
- 导致容器启动失败或任务丢失

---

## 问题 2: Ansible 异步任务超时

### 症状
```
fatal: [netbox-01]: FAILED! => {
  "msg": "...'docker compose up -d' timed out after 120 seconds..."
}
```

但登录目标服务器后，容器仍在运行或已启动成功。

### 诊断步骤
1. 检查 Ansible 任务的 timeout 配置：
   ```bash
   grep -B5 "docker compose up" ansible/roles/netbox/tasks/main.yml
   ```

2. 查看 docker-compose.yml 中是否配置了依赖关系：
   ```bash
   grep -A5 "depends_on" docker-compose.yml
   ```

3. 查看容器启动日志：
   ```bash
   docker compose logs netbox | head -50
   ```

### 原因分析

**阻塞机制**:

当 `docker-compose.yml` 中配置了依赖关系时：

```yaml
services:
  netbox-worker:
    depends_on:
      netbox:
        condition: service_healthy
```

**执行流程**:
1. `docker compose up -d` 启动容器
2. 等待 Netbox 健康检查通过 (Healthcheck 变成 `healthy`)
3. 才认为 `up` 命令完成

**时间消耗**:
- Netbox 首次启动需要执行数据库迁移 (migrations)
- 迁移耗时 2-5 分钟，期间 Healthcheck 状态为 `unhealthy`
- `docker compose up` 一直阻塞，等待 Healthcheck 变 `healthy`
- 如果时间超过 Ansible 或 SSH 的默认超时 (通常 120s)，任务被判定失败

### 解决方案

使用 Ansible 的 `async` 和 `poll` 参数允许任务运行更长时间：

```yaml
- name: Start Netbox services
  command: docker compose up -d
  args:
    chdir: "{{ netbox_install_dir }}"
  async: 600                     # 最大允许运行时间（秒）= 10 分钟
  poll: 10                       # 轮询检查频率（秒）
  register: docker_start_result

- name: Wait for Netbox to be healthy
  command: docker compose exec netbox curl -s http://localhost:8080/login/
  args:
    chdir: "{{ netbox_install_dir }}"
  register: health_check
  until: health_check.rc == 0
  retries: 30
  delay: 10
```

**参数说明**:

| 参数 | 含义 | 示例 |
|------|------|------|
| `async` | 最大运行时间（秒） | `600` = 10 分钟 |
| `poll` | 轮询检查频率（秒） | `10` = 每 10 秒检查一次 |

**Poll 行为**:
- `poll > 0` - Ansible 阻塞并定期检查任务状态（推荐，需要确认成功）
- `poll: 0` - "Fire and forget"，Ansible 启动任务后立即返回（不等待结果）

### 最佳实践

对于需要长时间初始化的服务，组合使用以下策略：

```yaml
- name: Deploy Netbox
  block:
    # 1. 用 async/poll 启动容器（允许长时间运行）
    - name: Start Netbox
      command: docker compose up -d
      args:
        chdir: /opt/netbox-docker
      async: 600
      poll: 10
    
    # 2. 额外的健康检查（以防 docker-compose 的 healthcheck 不可靠）
    - name: Verify Netbox is healthy
      uri:
        url: "http://192.168.1.104:8080/login/"
        status_code: 200
      register: result
      until: result.status == 200
      retries: 20
      delay: 10
  
  rescue:
    # 错误处理：打印日志帮助调试
    - name: Print Netbox logs
      command: docker compose logs netbox
      args:
        chdir: /opt/netbox-docker
```

---

## 问题 3: RustDesk 架构误解

### 症状 A: 网页打不开

```
访问 https://rustdesk.willfan.me 返回 404 或 Connection Closed
```

### 症状 B: 客户端连不上

```
RustDesk 客户端显示 "failed to lookup address" 或 "connection refused"
```

### 诊断步骤

#### 确认 RustDesk 服务类型

1. 检查运行的容器：
   ```bash
   docker ps | grep rustdesk
   # 查看镜像名称：rustdesk-server 还是 rustdesk-server-web
   ```

2. 查看暴露的端口：
   ```bash
   docker port <container_id>
   # 应该显示 21116/tcp, 21117/tcp, 21118/tcp 等
   ```

3. 测试 TCP 连接：
   ```bash
   nc -zv 192.168.1.102 21116
   nc -zv 192.168.1.102 21117
   # 检查端口是否开放
   ```

### 原因分析

**RustDesk 的架构**:

RustDesk 分为两个不同的组件：

| 组件 | 镜像名称 | 功能 | 端口 |
|------|---------|------|------|
| **RustDesk Server** | `rustdesk/rustdesk-server` | ID服务 + 中继 + WebSocket | 21116-21119 |
| **RustDesk Web** | `rustdesk/rustdesk-server-web` | Web管理界面 + Web客户端 | 8000-8080 |

**常见误区**:

1. **误区**: "部署了 RustDesk Server，应该有网页后台"
   - **事实**: 原生 RustDesk Server **只有后台 API 和中继，没有 Web 界面**
   - **正确做法**: 如果需要网页版客户端，需额外部署 `rustdesk-server-web`

2. **误区**: "所有流量都通过反向代理 (Caddy)"
   - **事实**: RustDesk 客户端主要使用 TCP/UDP 21116 和 TCP 21117（**网络层的中继**）
   - **Caddy 是 HTTP/HTTPS 代理**，无法转发 TCP/UDP 中继流量
   - **正确做法**:
     - Web API/Web 客户端 → 走 Caddy (HTTPS)
     - 原生客户端 (PC/手机) → 直连 RustDesk Server IP
     - 域名应该直接指向 RustDesk VM，不经过 Caddy

### 解决方案

#### 方案 A: 仅 RustDesk Server（无网页）

```yaml
# docker-compose.yml
version: '3'
services:
  rustdesk-server:
    image: rustdesk/rustdesk-server:latest
    container_name: rustdesk
    ports:
      - "21116:21116"      # ID 服务 + 心跳
      - "21117:21117"      # 中继
      - "21118:21118"      # WebSocket (可选)
      - "21119:21119"      # WebSocket (可选)
    volumes:
      - ./data:/root
    restart: unless-stopped
```

**客户端配置**:
```
ID 服务器: 192.168.1.102  (VM 的内网 IP，不是 Caddy 的 IP)
中继服务器: 192.168.1.102
端口: 21116
```

#### 方案 B: RustDesk Server + Web 管理

```yaml
# docker-compose.yml
version: '3'
services:
  rustdesk-server:
    image: rustdesk/rustdesk-server:latest
    container_name: rustdesk
    ports:
      - "21116:21116"
      - "21117:21117"
      - "21118:21118"
      - "21119:21119"
    volumes:
      - ./data:/root
    restart: unless-stopped
  
  rustdesk-web:
    image: rustdesk/rustdesk-server-web:latest
    container_name: rustdesk-web
    environment:
      - ADMIN_USERNAME=admin
      - ADMIN_PASSWORD=admin
    ports:
      - "21110:21110"      # 图形界面
    depends_on:
      - rustdesk-server
    restart: unless-stopped
```

**DNS 配置**:
- `rustdesk.willfan.me` A 记录 → `192.168.1.102` (RustDesk VM)
- 不走 Caddy，直接指向 RustDesk 服务器

#### 方案 C: 如果要通过 Caddy 反代

只能反代 WebSocket 端口（用于 Web 客户端），不能反代原生客户端协议：

```caddy
rustdesk.willfan.me {
    # 反代 WebSocket (用于 Web 客户端)
    reverse_proxy /ws localhost:21118
    
    # 其他 Web API
    reverse_proxy /api localhost:21110
}
```

**但原生客户端仍需配置**:
```
ID 服务器: 192.168.1.102  (直连，不走 Caddy)
```

---

## 问题 4: 内网 DNS 解析问题

### 症状
```
RustDesk 客户端显示 "failed to lookup address rustdesk.willfan.me"
但其他机器能正常 ping 到该域名
```

或

```
Docker 容器内 nslookup rustdesk.willfan.me 失败
但宿主机能解析
```

### 诊断步骤

#### 在不同位置测试 DNS 解析

1. **宿主机**:
   ```bash
   nslookup rustdesk.willfan.me
   host rustdesk.willfan.me
   ```

2. **容器内**:
   ```bash
   docker compose exec rustdesk nslookup rustdesk.willfan.me
   ```

3. **客户端**:
   ```bash
   nslookup rustdesk.willfan.me
   # Windows
   ping rustdesk.willfan.me
   ```

4. **指定 DNS 服务器**:
   ```bash
   nslookup rustdesk.willfan.me 192.168.1.1  # 查询路由器 DNS
   nslookup rustdesk.willfan.me 8.8.8.8      # 查询公网 DNS
   ```

### 原因分析

**DNS Split-Horizon 问题**:

| 位置 | DNS 服务器 | 结果 |
|------|----------|------|
| 客户端 | 路由器 192.168.1.1 | ✅ 成功 (路由器配置了 DNS 记录) |
| 宿主机 | 默认系统 DNS | ✅ 成功 |
| Docker 容器 | 内部 DNS 192.168.65.x | ❌ 失败 (无法向上游请求) |

**可能原因**:
1. Docker 容器使用独立的内部 DNS，不会自动查询外部 DNS
2. DNS 缓存问题 - 旧版本的 DNS 解析结果仍在缓存
3. 路由器 DNS 配置不完整 - 只在某些 DNS 客户端上生效

### 解决方案

#### 方案 A: 使用控制变量法隔离问题

**先用 IP 地址，再用域名**:

```
1. 测试用 IP：RustDesk 客户端配置服务器为 192.168.1.102
   ✅ 成功 → 说明网络层没问题，是 DNS 问题
   ❌ 失败 → 说明网络层有问题

2. 测试用域名：rustdesk.willfan.me
   ❌ 失败 + IP 成功 → 100% 确认是 DNS 问题
```

#### 方案 B: 修复 Docker DNS 配置

```yaml
# docker-compose.yml
services:
  rustdesk:
    image: rustdesk/rustdesk-server:latest
    dns:
      - 192.168.1.1       # 路由器 DNS
      - 8.8.8.8           # 公网 DNS 备选
```

或编辑 `/etc/docker/daemon.json`:

```json
{
  "dns": ["192.168.1.1", "8.8.8.8"]
}
```

然后重启 Docker：

```bash
systemctl restart docker
```

#### 方案 C: 在路由器配置 DNS 记录

在 OpenWrt / 小米路由器等的 DHCP/DNS 设置中添加：

```
域名: rustdesk.willfan.me
IP: 192.168.1.102
```

**最佳实践**:
```
内网部署时，最好的方案是：
1. 在路由器配置 DNS 记录
2. 所有设备使用路由器作为首选 DNS (通过 DHCP)
3. 这样所有设备（包括 Docker 容器）都能正确解析
```

---

## 总结与最佳实践

### 记住这些要点

1. **版本匹配很关键** - netbox-docker 与 Netbox 应用版本必须对应
2. **三容器版本一致** - netbox、netbox-worker、netbox-housekeeping 必须同版本
3. **异步处理长时间任务** - 使用 `async` 和 `poll` 参数
4. **理解应用架构** - RustDesk Server 无网页、需直连、不能完全通过反代
5. **DNS 分层测试** - IP → 本地 → 容器，逐步隔离问题
6. **显式配置优于默认** - 指定用户、端口、版本、重启策略等

### 快速参考

| 问题 | 快速修复 |
|------|---------|
| DATABASE 配置错误 | 使用 netbox-docker v3.0.2 tag |
| 用户不存在 | 在 override.yml 中设置 `user: "unit:root"` |
| 容器启动失败 | 检查 Postgres 版本，执行 `docker compose down -v` |
| Ansible 超时 | 添加 `async: 600` 和 `poll: 10` |
| RustDesk 网页打不开 | 检查是否需要 `rustdesk-server-web`，原生 Server 没有网页 |
| 客户端连不上 | 客户端配置服务器 IP，不走反代；DNS 问题用 IP 先测试 |
| Docker DNS 失败 | 在 docker-compose.yml 中指定 DNS 服务器 |

