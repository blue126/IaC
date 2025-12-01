# Ansible 部署 Netbox 与 Docker Compose 最佳实践

**日期:** 2025-11-29
**标签:** Ansible, Docker, Netbox, Docker Compose, DevOps

## 1. 核心概念定义 (Concepts)

*   **Ansible Roles (角色)**:
    *   **定义**: Ansible 中用于组织 Playbook 的一种方式。它将相关的变量、任务、文件、模板和处理器打包在一起。
    *   **应用**: 我们创建了 `docker` Role（负责安装 Docker 环境）和 `netbox` Role（负责部署应用），实现了关注点分离。
*   **Docker Compose V2**:
    *   **定义**: Docker 官方推荐的新版编排工具，重写为 Go 语言，集成在 Docker CLI 中。
    *   **命令**: 使用 `docker compose` 替代了旧版的 `docker-compose`（Python 版）。
*   **Override Pattern (覆盖模式)**:
    *   **定义**: Docker Compose 的一种特性，允许使用额外的 YAML 文件（如 `docker-compose.override.yml`）来合并或覆盖默认配置。
    *   **优势**: 保持上游 `docker-compose.yml` 的纯净，便于升级；将本地定制（端口、卷）隔离在 `override` 文件中。

## 2. 架构决策 (Architecture Decisions)

### 2.1 Inventory 组织
我们将 VM 的定义从物理机 Inventory (`hosts.yml`) 中分离出来，放入 `inventory/pve_vms/` 目录。
*   **目的**: 清晰区分"物理基础设施"（Proxmox 节点）和"虚拟应用设施"（VMs）。
*   **结构**:
    ```yaml
    # inventory/pve_vms/netbox.yml
    application_vms:
      hosts:
        netbox-01: ...
    ```

### 2.2 Netbox 部署策略
我们选择了 **Docker 部署** 而非源码部署，并采用了"轻量化"策略：
*   **不 Clone 仓库**: 仅下载官方发布的 `docker-compose.yml`。
*   **自包含环境**: 在 Ansible Role 中自动生成 `env/` 目录和环境变量文件 (`netbox.env`, `postgres.env`, `redis.env`)，确保部署的原子性。

## 3. 遇到的问题与解决方案 (Troubleshooting)

### A. Docker Compose 版本混淆
*   **问题**: 习惯性使用 `docker-compose` 命令，但新版 Docker 推荐使用插件形式的 `docker compose`。
*   **解决**: 在 Ansible Task 中明确使用 `docker compose` 命令，并确保安装了 `docker-compose-plugin` 包。

### B. 依赖文件缺失
*   **问题**: 仅下载 `docker-compose.yml` 后启动失败，因为缺失了引用的 `env` 文件。
*   **解决**: 在 Ansible Role 中增加了创建 `env` 目录和生成默认环境变量文件的任务。

### C. 配置示例文件缺失
*   **问题**: Ansible Role 尝试复制 `configuration.py.example`，但该文件在最新的 `netbox-docker` 仓库中已不存在。
*   **原因**: `netbox-docker` 现在默认提供一个基于环境变量配置的 `configuration.py`，不再需要手动从 example 复制。
*   **解决**: 移除了复制 `.example` 文件的 Ansible 任务，直接使用仓库提供的默认配置。

### D. 数据库连接失败 (fe_sendauth: no password supplied)
*   **问题**: Netbox 容器无法连接到 Postgres 数据库，报错 "no password supplied"。
*   **原因**: `configuration.py` 默认使用 `localhost` 作为数据库主机，且需要 `DB_PASSWORD` 环境变量。而 Docker Compose 中数据库服务名为 `postgres`，且我们只在 `postgres.env` 中设置了 `POSTGRES_PASSWORD`，未在 `netbox.env` 中设置 `DB_PASSWORD`。
*   **解决**: 在 `netbox.env` 中明确添加以下变量：
    ```bash
    DB_HOST=postgres
    DB_USER=netbox
    DB_PASSWORD=netbox
    REDIS_HOST=redis
    REDIS_PASSWORD=netbox
    REDIS_CACHE_HOST=redis-cache
    REDIS_CACHE_PASSWORD=netbox
    ```

### E. 部署超时 (Healthcheck failed)
*   **问题**: `docker compose up -d` 失败，提示 Netbox 容器 unhealthy。
*   **原因**: Netbox 首次启动时需要执行大量数据库迁移（Migrations），耗时超过了默认的 Healthcheck 启动宽限期（start_period）。
*   **解决**: 在 `docker-compose.override.yml` 中增加 `start_period`：
    ```yaml
    services:
      netbox:
        healthcheck:
          start_period: 300s
    ```

## 4. 关键问答 (Q&A)

**Q: 为什么不直接修改 `docker-compose.yml`，而是要创建一个 `override` 文件？**
**A:**
1.  **上游兼容性**: 保持 `docker-compose.yml` 与官方仓库一致，方便未来直接覆盖升级。
2.  **关注点分离**: 官方文件定义"架构"（服务、镜像），Override 文件定义"部署细节"（端口映射、本地路径）。
3.  **自动化友好**: Ansible 可以放心地幂等下载官方文件，而不会覆盖掉我们自定义的端口配置。

**Q: 为什么要把 Netbox 归类到 `application_vms` 而不是单独建一个 `netbox` 组？**
**A:** `application_vms` 是一个逻辑分组，用于管理所有运行业务应用的 VM。对于单实例应用（如 Netbox），直接作为该组下的一个 Host 管理更加扁平化，避免了 Inventory 层级过深。

## 5. 下一步计划
*   [x] 执行 `ansible-playbook playbooks/deploy-netbox.yml` 完成部署。
*   验证 Netbox Web UI (http://192.168.1.104:8000)。
*   配置 Nginx 反向代理（可选，如果需要 HTTPS 或标准 80/443 端口）。
