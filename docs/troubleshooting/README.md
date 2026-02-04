# 故障排查文档索引 (Troubleshooting Index)

本目录包含基础设施和自动化部署中常见问题的排查指南。每个文档采用**症状-诊断-原因-解决方案**的结构。

---

## 快速导航

### 按症状分类 (Symptoms)

| 症状描述 | 相关文档 | 关键词 |
|---------|---------|-------|
| Terraform 命令崩溃或报权限错误 | [terraform-issues.md](./terraform-issues.md) | Provider版本、Proxmox兼容性、API Token |
| 虚拟机无法启动或进入UEFI Shell | [terraform-issues.md](./terraform-issues.md) | 磁盘调整、Cloud-Init、QEMU Agent |
| Ansible连接失败或依赖缺失 | [ansible-issues.md](./ansible-issues.md) | Callback插件、环境依赖、模块导入 |
| Inventory变更导致配置丢失 | [ansible-issues.md](./ansible-issues.md) | 动态Inventory、变量迁移、数据分离 |
| SMB/文件传输速度异常慢 | [network-connectivity.md](./network-connectivity.md) | Tailscale路由、网络延迟、MTU碎片 |
| Caddy WebDAV或反代配置出错 | [network-connectivity.md](./network-connectivity.md) | Caddyfile语法、指令顺序、ACL限制 |
| Netbox容器启动失败 | [deployment-issues.md](./deployment-issues.md) | Docker版本、配置参数、数据库迁移 |
| RustDesk客户端连不上 | [deployment-issues.md](./deployment-issues.md) | DNS解析、端口直连、架构设计 |

---

## 文档概览

### 1. [terraform-issues.md](./terraform-issues.md) - Terraform故障排查
**包含内容**:
- Terraform Proxmox Provider版本选择 (rc04 vs rc05 vs v2.9.14)
- Provider崩溃和权限错误的原因与解决方案
- API Token认证与权限分离 (privsep)
- 磁盘调整危险行为：缩容导致磁盘替换
- Cloud-Init与QEMU Guest Agent依赖链
- Docker Restart Policy配置漂移
- Terraform Lifecycle与引导顺序
- VMID稳定性与ID漂移问题

**来源**:
- `/mnt/docs/learningnotes/2025-11-30-terraform-proxmox-provider-crash.md`
- `/mnt/docs/learningnotes/2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md`

---

### 2. [ansible-issues.md](./ansible-issues.md) - Ansible故障排查
**包含内容**:
- Ansible 输出格式 (Callback 插件) 演变
- DevContainer 环境依赖缺失：passlib、ansible.posix
- 优雅地检测命令是否存在
- 从静态到动态Inventory的数据丢失风险
- 寻址 (Addressing) 与配置 (Configuration) 分离
- host_vars 最佳实践
- 模板通用化与避免硬编码

**来源**:
- `/mnt/docs/learningnotes/2026-01-29-ansible-troubleshooting.md`
- `/mnt/docs/learningnotes/2026-01-29-inventory-migration-trap.md`

---

### 3. [network-connectivity.md](./network-connectivity.md) - 网络连接问题
**包含内容**:
- Windows SMB 上传速度慢：Tailscale子网路由优先级问题
- 网络诊断三板斧：Ping、Tracert、路由表
- Tailscale MagicDNS 与 Ansible 连接冲突
- Caddy WebDAV 配置：指令顺序与 route 块
- 第三方插件与标准指令的优先级
- Caddyfile 最佳实践

**来源**:
- `/mnt/docs/slow-smb-over-wifi.md`
- `/mnt/docs/learningnotes/2025-12-03-caddy-webdav-tailscale-troubleshooting.md`

---

### 4. [deployment-issues.md](./deployment-issues.md) - 部署相关问题
**包含内容**:
- Netbox 版本兼容性：netbox-docker vs Netbox应用版本
- DATABASE (单数) vs DATABASES (复数) 配置
- Docker Compose Override Pattern
- Postgres 版本升级冲突与 Volume 清理
- 用户配置错误：netbox vs unit
- Netbox 三容器架构与版本一致性
- Ansible 异步任务与超时处理 (async/poll)
- RustDesk 架构：无Web界面、TCP/UDP直连、DNS解析
- 内网部署的DNS问题与控制变量法

**来源**:
- `/mnt/docs/learningnotes/2025-11-29-netbox-deployment-version-troubleshooting.md`
- `/mnt/docs/learningnotes/2026-01-29-rustdesk-deployment-lessons.md`

---

## 快速诊断流程 (Quick Diagnosis Flow)

```
遇到问题
 │
 ├─ 是否涉及Terraform? ─────────→ 查看 terraform-issues.md
 │
 ├─ 是否涉及Ansible/Inventory? ──→ 查看 ansible-issues.md
 │
 ├─ 是否涉及网络/性能/连接? ─────→ 查看 network-connectivity.md
 │
 └─ 是否涉及Docker/容器/部署? ──→ 查看 deployment-issues.md
```

---

## 通用诊断步骤 (Generic Steps)

### 1. 收集信息
- 错误消息的完整内容
- 相关组件的版本号 (Terraform, Ansible, Docker, Proxmox VE等)
- 环境信息 (控制节点OS, 目标节点OS)
- 最后一次成功的操作和之后的变更

### 2. 隔离问题
- 逐一排除可能的原因
- 使用"控制变量法"：修改一个变量，观察结果是否变化
- 查看相关的日志输出

### 3. 确认解决方案
- 在测试环境复现问题
- 应用解决方案
- 验证问题是否解决
- 更新文档（如果发现新的模式）

---

## 最佳实践建议 (Best Practices)

1. **显式定义，不相信默认值** - 磁盘大小、引导顺序、重启策略、权限、版本
2. **环境隔离与复现** - 使用DevContainer或虚拟环境确保可复现性
3. **数据分离** - 基础设施数据(Terraform)、应用配置(Ansible host_vars)、业务数据(环境变量/Vault)
4. **版本锁定** - 避免使用 `latest` tag，始终显式指定版本
5. **异步处理** - 长时间运行的任务使用 `async/poll`，避免超时
6. **日志监控** - 部署后使用 `logs -f` 或类似工具实时监控
7. **增量验证** - 先用IP测试网络层，再用域名测试DNS层，逐步排除

---

## 相关资源

- **Terraform**: [hashicorp/terraform](https://github.com/hashicorp/terraform)
- **Terraform Proxmox Provider**: [telmate/proxmox](https://github.com/telmate/terraform-provider-proxmox)
- **Ansible**: [ansible/ansible](https://github.com/ansible/ansible)
- **Proxmox VE**: [Proxmox Documentation](https://pve.proxmox.com/wiki/Main_Page)
- **Docker**: [Docker Documentation](https://docs.docker.com/)
- **Tailscale**: [Tailscale Documentation](https://tailscale.com/kb/)

---

**最后更新**: 2026-01-30
**覆盖范围**: Terraform 1.x, Ansible 2.13+, Docker 20+, Proxmox VE 8+
