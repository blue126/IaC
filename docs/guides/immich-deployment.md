# Immich Deployment Guide

> 说明：本指南覆盖 Immich 在 Homelab 中的 Terraform 资源、Proxmox 规格、Ansible 角色部署、验证模式、运维与扩展。语言中文，代码注释英文。

## 1. 概述
Immich 是自托管照片/视频管理与 AI 分类平台。本环境中通过：
- Terraform：提供虚拟机 (VMID 101) 与资源规格。
- Ansible：`immich` 角色 + `docker` 角色部署 Docker Compose 服务栈。
- 验证：在部署 playbook 中使用 `--tags verify` 进行端口、容器、PostgreSQL、Redis 与 HTTP 状态检查。

功能组件（容器）：
| 容器 | 作用 |
|------|------|
| immich-server | Web/API 主服务 |
| immich-machine-learning | 图像/面部/向量分析 |
| immich-postgres | 数据库 |
| immich-redis | 缓存/队列 |

## 2. 基础设施 (Terraform)
源文件：`terraform/proxmox/immich.tf`
关键参数：
- vCPU: 2
- Memory: 8192MB
- Disk: 300G (在 NetBox 中记录为 307200 MB)
- IP: 192.168.1.101/24 网关 192.168.1.1
- BIOS: OVMF + EFI Disk
- 自定义 Cloud-Init：`cicustom = "user=local:snippets/ubuntu-password.yml"`

导入/管理注意事项：
- 初期执行 `terraform import` 时需警惕 provider crash（详见 learningnotes 中 Proxmox provider 崩溃笔记）。
- EFI 磁盘存储池可与系统盘不同，模块变量已支持 `efidisk_storage`。

## 3. Ansible 部署结构
Playbook：`ansible/playbooks/deploy-immich.yml` （简化为调用角色）
角色目录：`ansible/roles/immich/`

角色内容：
- defaults/main.yml：定义路径、端口、数据库凭据等变量。
- tasks/main.yml：
  1. 创建应用目录
  2. 模板渲染 `.env`
  3. 拉取镜像与启动 Compose
  4. 等待 Web/API 端口开放
  5. 验证容器健康与数据库连通
- templates/env.j2：包含数据库、Redis、服务端口配置。
- handlers/main.yml：配置文件变化触发重启（docker compose up -d）。

示例（缩写):
```yaml
- name: Deploy Immich Service
  hosts: immich-node
  roles:
    - docker
    - immich
```

默认变量参考：
```yaml
immich_app_dir: /opt/immich
immich_db_username: immich
immich_db_password: changeMe
immich_port: 2283
```

## 4. Docker Compose 栈说明
Compose 文件（模板/任务中生成）包含服务：server、machine-learning、redis、postgres。机器学习容器常为启动最慢部分（首次拉取模型或初始化缓存）。

性能与资源：
- Memory 8GB 足够运行轻度照片分析与嵌入生成。
- 300G 磁盘用于照片原始文件 + 数据库索引；如需扩展建议使用挂载的 ZFS dataset 或外部存储。

## 5. 部署验证模式
Playbook 中 `--tags verify` 的检查点：
1. 端口监听：`wait_for` 检查 2283。
2. 容器数量：使用 `docker compose ps` 统计 4 个核心容器是否 `healthy/up`。
3. PostgreSQL：在容器内执行 `pg_isready`（通过 `docker compose exec`）。
4. Redis：可扩展添加 `redis-cli PING`。
5. HTTP 接口：`uri` 访问首页或健康检查端点返回 200。

示例验证任务片段：
```yaml
- name: Wait for Immich web server to be ready
  wait_for:
    host: "{{ inventory_hostname }}"
    port: "{{ immich_port }}"
    timeout: 60

- name: Test Immich web interface
  uri:
    url: "http://{{ inventory_hostname }}:{{ immich_port }}"
    status_code: 200
```

## 6. 常见问题与排查
| 问题 | 现象 | 排查 | 解决 |
|------|------|------|------|
| 模型初始化慢 | 首次部署长时间无响应 | `docker compose logs immich-machine-learning` | 等待模型下载或预置模型缓存 |
| 数据库连接失败 | `pg_isready` 超时 | 检查 postgres 容器启动顺序 | 添加依赖或增加等待时间 |
| Redis 队列阻塞 | 上传卡住或任务堆积 | `docker compose logs immich-redis` | 清理大批量任务/增大资源 |
| 端口未开放 | 2283 无响应 | `ss -tlnp | grep 2283` | 检查 server 容器崩溃日志 |
| 升级失败 | 新版本迁移报错 | `docker compose pull && docker compose up -d` | 先备份数据库再重试 |

## 7. 升级策略
1. 备份：`pg_dump -h immich_postgres -U immich immichdb > backup.sql`
2. 拉取镜像：`docker compose pull`
3. 滚动重启：`docker compose up -d`
4. 验证：重复运行 `--tags verify`。

## 8. 备份与恢复建议
| 类型 | 内容 | 工具 | 周期 |
|------|------|------|------|
| PostgreSQL | 元数据/索引/标签 | `pg_dump` | 每日 |
| 媒体原始文件 | 照片/视频 | rsync/ZFS snapshot | 按需/每日快照 |
| Compose 与配置 | `.env`/模板/角色变量 | Git 版本控制 | 每次变更 |

恢复流程要点：先恢复媒体数据路径，再恢复数据库，再启动服务栈。

## 9. 性能与容量规划
- 8GB 内存可支持小规模 (<200k 照片) 初始部署；若启用大量并行分析可考虑提升至 16GB。
- 磁盘 IOPS 易成为缩略图生成瓶颈，建议采用 SSD 或 ZFS ARC 调优。
- Redis 内存监控：`INFO memory`，超过阈值需调高 maxmemory 或清理队列。

## 10. 与其他服务的差异点
| 对比项 | Immich | Netbox | Samba | Anki |
|--------|--------|--------|-------|------|
| 部署方式 | Docker Compose | Docker Compose | 原生 systemd | 原生 systemd (LXC) |
| 验证重点 | 多容器 + HTTP + DB | HTTP 登录页 + DB + Redis | SMB/NetBIOS 端口 + share 列表 | 端口 + systemd 服务 |
| 资源占用 | 中等 (ML 可增大) | 中等 | 低 | 低 |

## 11. Terraform 与 NetBox 对应
NetBox 侧：
- VM：`netbox_virtual_machine.immich`
- 接口：`netbox_interface.immich_eth0`
- IP：`netbox_ip_address.immich_ip`
- 服务：`netbox_service.immich_web`, `immich_postgres`, `immich_redis`
- Cable：`netbox_cable.immich_eth0_pve0_vmbr1`

确保规格变更后同步更新 `vm.tf` 与磁盘大小单位换算。

## 12. 后续可扩展
- 增加向量数据库（例如 Qdrant）提升检索性能。
- 引入 GPU 直通：Terraform + Proxmox PCI 配置项扩展。
- 添加 Prometheus 导出：采集容器资源与分析队列指标。

## 13. 学习笔记引用
相关深入分析与模式：
- Verification Pattern: `docs/learningnotes/2025-11-30-ansible-deployment-verification.md`
- Terraform 重构最佳实践：`docs/learningnotes/2025-11-30-terraform-refactoring-best-practices.md`

## 14. 快速命令参考
```bash
# 查看容器状态
cd /opt/immich && docker compose ps

# 查看日志 (server)
cd /opt/immich && docker compose logs -f immich-server

# 检查数据库健康
cd /opt/immich && docker compose exec -T immich-postgres pg_isready -U immich

# 备份数据库
cd /opt/immich && docker compose exec -T immich-postgres pg_dump -U immich > /backup/immich.sql

# 更新栈
cd /opt/immich && docker compose pull && docker compose up -d
```

## 15. 总结
Immich 的部署已经通过角色 + 模板实现标准化与可验证。对比传统手工方式：可复用、易扩展、验证自动化、与拓扑 (NetBox) 建模一致。后续重点在于：监控、备份持续自动化、性能分析与 GPU 加速支持。
