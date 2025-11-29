# Netbox 4.1.11 部署：版本匹配与配置调试

**日期:** 2025-11-29  
**标签:** Netbox, Docker, netbox-docker, Version Compatibility, Troubleshooting

## 1. 核心概念定义 (Concepts)

### 1.1 netbox-docker 项目版本 vs Netbox 应用版本
- **netbox-docker 版本**: 指 `netbox-docker` GitHub 仓库的版本号（如 3.0.2），它定义了 Docker Compose 配置文件的结构和默认设置
- **Netbox 应用版本**: 指 Netbox 软件本身的版本号（如 4.1.11），由 Docker 镜像 `netboxcommunity/netbox:v4.1.11` 提供
- **关键区别**: 
  - `netbox-docker` 是"包装纸"（部署脚本）
  - Netbox 是"糖果"（应用本身）
  - 两者版本号独立，但必须兼容

### 1.2 Docker Compose Override Pattern
- **定义**: 使用 `docker-compose.override.yml` 覆盖或扩展 `docker-compose.yml` 中的默认配置
- **合并规则**: 
  - 相同服务的配置会合并
  - `override` 中的值优先级更高
  - 数组类型（如 `environment`）会追加而非替换

### 1.3 Netbox 三容器架构
```
┌─────────────┐
│   netbox    │ ← Web UI + REST API (主服务)
└─────────────┘
┌─────────────┐
│netbox-worker│ ← 后台任务处理器 (RQ Worker)
└─────────────┘
┌─────────────┐
│netbox-house │ ← 定期维护任务 (Cron Jobs)
│  keeping    │
└─────────────┘
```
- **netbox**: 提供 Web 界面和 API，处理用户请求
- **netbox-worker**: 处理异步任务（Webhook、报告生成、批量操作）
- **netbox-housekeeping**: 执行定期清理（会话、日志、作业结果）

## 2. 版本兼容性问题排查

### 2.1 问题：DATABASE 参数缺失
**错误信息**:
```
django.core.exceptions.ImproperlyConfigured: Required parameter DATABASE is missing from configuration.
```

**根本原因**:
- Netbox 3.x 的 `configuration.py` 使用 `DATABASES` (复数)
- Netbox 4.x 的 `settings.py` 要求 `DATABASE` (单数)
- `netbox-docker` 的 `release` 分支停留在 3.x 时代，配置文件结构过时

**版本对应关系**:
| netbox-docker 分支/版本 | 支持的 Netbox 版本 | configuration.py 结构 |
|------------------------|-------------------|---------------------|
| `release`              | 3.x               | `DATABASES` (复数)   |
| `develop`              | 4.x (不稳定)       | `DATABASE` (单数)    |
| `3.0.2` (tag)          | 4.1.x             | `DATABASE` (单数)    |

**解决方案**: 使用 `netbox-docker` v3.0.2 而非 `release` 分支

### 2.2 问题：Postgres 版本升级冲突
**错误信息**:
```
This is usually the result of upgrading the Docker image without upgrading the underlying database using "pg_upgrade"
```

**原因**:
- `release` 分支使用 Postgres 17
- `develop` 分支使用 Postgres 18
- Docker Volume 中的数据库文件不兼容

**解决方案**:
```bash
docker compose down -v  # -v 参数删除所有 volumes
```

### 2.3 问题：用户配置错误
**错误信息**:
```
unable to find user netbox: no matching entries in passwd file
```

**原因**:
- `netbox-docker` v3.0.2 的 `docker-compose.yml` 使用 `user: "netbox:root"`
- 但 Netbox 4.1.11 镜像中不存在 `netbox` 用户，只有 `unit` 用户

**解决方案**: 在 `docker-compose.override.yml` 中覆盖用户配置
```yaml
services:
  netbox:
    user: "unit:root"
  netbox-worker:
    user: "unit:root"
  netbox-housekeeping:
    user: "unit:root"
```

### 2.4 问题：端口未暴露
**现象**: 容器运行但无法从外部访问

**原因**: `netbox-docker` v3.0.2 的默认 `docker-compose.yml` 不暴露端口（安全考虑）

**解决方案**: 在 `docker-compose.override.yml` 中添加端口映射
```yaml
services:
  netbox:
    ports:
      - "8080:8080"
```

## 3. 最终工作配置

### 3.1 Ansible Role 配置
**文件**: `ansible/roles/netbox/defaults/main.yml`
```yaml
netbox_git_repo: "https://github.com/netbox-community/netbox-docker.git"
netbox_git_version: "3.0.2"  # 注意：这是 netbox-docker 版本，不是 Netbox 应用版本
netbox_install_dir: "/opt/netbox-docker"
netbox_port: 8080
```

### 3.2 Docker Compose Override
**文件**: `ansible/roles/netbox/tasks/main.yml` (自动生成)
```yaml
services:
  netbox:
    image: netboxcommunity/netbox:v4.1.11  # 指定 Netbox 应用版本
    user: "unit:root"                       # 修复用户配置
    ports:
      - "8080:8080"                         # 暴露端口
    environment:
      - SUPERUSER_NAME=admin                # 自动创建超级用户
      - SUPERUSER_EMAIL=fanweiblue@gmail.com
      - SUPERUSER_PASSWORD=admin
      - SUPERUSER_API_TOKEN=0123456789abcdef0123456789abcdef01234567
  netbox-worker:
    image: netboxcommunity/netbox:v4.1.11
    user: "unit:root"
  netbox-housekeeping:
    image: netboxcommunity/netbox:v4.1.11
    user: "unit:root"
```

### 3.3 为什么要为所有三个服务指定镜像版本？
1. **代码一致性**: 三个容器运行相同的代码库，版本不一致会导致：
   - Worker 无法正确处理主服务创建的任务
   - Housekeeping 脚本可能与数据库 schema 不匹配
2. **避免默认行为**: 如果不指定，`docker-compose.yml` 中的默认镜像可能是 `latest` 或其他版本
3. **明确性**: 显式声明比隐式依赖更可靠

## 4. 部署流程总结

### 4.1 成功部署步骤
```bash
# 1. 清理旧环境（如果存在）
ansible netbox-01 -m command -a "chdir=/opt/netbox-docker docker compose down -v" --become

# 2. 删除旧仓库
ansible netbox-01 -m command -a "rm -rf /opt/netbox-docker" --become

# 3. 运行 Ansible Playbook
cd /home/will/IaC/ansible
ansible-playbook playbooks/deploy-netbox.yml

# 4. 等待容器健康检查通过（约 2-3 分钟）
# 5. 访问 http://192.168.1.104:8080
```

### 4.2 验证部署成功
```bash
# 检查容器状态
ansible netbox-01 -m command -a "chdir=/opt/netbox-docker docker compose ps" --become

# 测试 Web 访问
curl -s http://192.168.1.104:8080/login/ | grep -o '<title>.*</title>'
# 输出: <title>Home | NetBox</title>
```

## 5. 关键问答 (Q&A)

**Q: 为什么不能直接使用 `release` 分支？**  
**A**: `release` 分支对应 Netbox 3.x，其 `configuration.py` 使用 `DATABASES` 配置，与 Netbox 4.x 的 `DATABASE` 要求不兼容。必须使用 `netbox-docker` v3.0.2 或更高版本。

**Q: `develop` 分支可以用吗？**  
**A**: 理论上可以，但 `develop` 是开发分支，可能不稳定。我们遇到了 Postgres 18 升级问题和用户配置问题。生产环境建议使用稳定的 tag 版本（如 3.0.2）。

**Q: 如何查看 netbox-docker 支持的 Netbox 版本？**  
**A**: 
1. 查看 `docker-compose.yml` 中的默认镜像 tag
2. 查看仓库的 `VERSION` 文件
3. 参考官方文档的兼容性矩阵

**Q: 为什么 Healthcheck 一直显示 unhealthy？**  
**A**: Netbox 首次启动时需要执行数据库迁移（migrations），可能需要 2-5 分钟。只要容器没有退出，且日志显示迁移正在进行，就耐心等待。可以通过 `docker compose logs -f netbox` 查看进度。

**Q: 如何修改超级用户密码？**  
**A**: 
1. 方法一：修改 `docker-compose.override.yml` 中的 `SUPERUSER_PASSWORD`，然后重新部署
2. 方法二：登录后在 Web UI 中修改
3. 方法三：使用 Django 管理命令：
   ```bash
   docker compose exec netbox /opt/netbox/netbox/manage.py changepassword admin
   ```

## 6. 最佳实践建议

1. **版本锁定**: 始终在 `docker-compose.override.yml` 中明确指定镜像版本，避免使用 `latest`
2. **环境变量集中管理**: 将敏感信息（密码、Token）通过 Ansible Vault 加密存储
3. **健康检查宽限期**: 对于需要长时间初始化的服务，适当增加 `start_period`
4. **日志监控**: 部署后使用 `docker compose logs -f` 实时监控启动过程
5. **备份策略**: 定期备份 Postgres 数据卷和 Netbox 媒体文件

## 7. 下一步计划

- [ ] 配置 Nginx 反向代理（HTTPS + 域名）
- [ ] 使用 Terraform 向 Netbox 添加基础设施资源
- [ ] 集成 LDAP/SSO 认证
- [ ] 配置自动备份脚本
