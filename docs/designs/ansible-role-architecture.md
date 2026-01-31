# Ansible Role Architecture Design

**Last Updated**: 2026-01-31  
**Status**: ✅ Implemented  
**Owner**: Homelab IaC Project

## 概述

本文档定义了 Homelab IaC 项目中 Ansible Role 的架构设计，包括 role 职责划分、目录规范、变量管理策略、依赖关系图，以及与 inventory/playbook 层的协作模式。

## 设计目标

1. **单一职责** — 每个 role 只负责一个服务或一组紧密相关的功能
2. **可覆盖的默认值** — 通过 `defaults/main.yml` 提供合理默认值，可在 inventory 层覆盖
3. **透明的依赖关系** — role 间的依赖在 playbook 层显式声明，不在 role 内部隐式引入
4. **安全的密钥管理** — 所有凭据通过 vault 间接引用，role 中不出现明文密码

## 架构总览

```
ansible/
├── playbooks/           # 编排层：声明 role 组合和执行顺序
├── roles/               # 执行层：13 个 role，每个负责一个服务
│   ├── common/          # 基础设施 —— 所有主机的通用配置
│   ├── docker/          # 基础设施 —— 容器运行环境
│   ├── tailscale/       # 基础设施 —— VPN 接入
│   ├── netbox/          # 应用服务
│   ├── netbox_sync/     # 工具 —— 同步 inventory 到 Netbox
│   ├── homepage/        # 应用服务
│   ├── immich/          # 应用服务
│   ├── caddy/           # 应用服务
│   ├── n8n/             # 应用服务
│   ├── anki_sync_server/# 应用服务
│   ├── rustdesk/        # 应用服务
│   ├── pbs/             # 应用服务（含 ZFS 存储配置）
│   └── pbs_client/      # 工具 —— 配置 Proxmox 节点连接 PBS
└── inventory/           # 数据层：主机定义、变量赋值、vault 密钥
```

---

## Role 分类

### 基础设施 Role（3 个）

为其他 role 提供运行环境，不直接部署应用服务。

| Role | 职责 | 使用方 |
|------|------|--------|
| `common` | 安装基础包、部署 SSH 公钥、配置 sudo | 所有主机（via `site.yml`） |
| `docker` | 安装 Docker Engine + Compose 插件 | immich, netbox, rustdesk, devcontainer |
| `tailscale` | 安装 Tailscale VPN，处理 LXC 特殊配置 | 所有 tailscale 组成员 |

### 应用服务 Role（8 个）

部署和配置具体的应用服务。

| Role | 服务 | 部署方式 | 主机 |
|------|------|----------|------|
| `netbox` | Netbox IPAM/DCIM | Docker Compose（git clone 官方仓库） | netbox (VM) |
| `homepage` | Homepage 仪表板 | 源码构建（Node.js/pnpm + systemd） | homepage (LXC) |
| `immich` | Immich 照片管理 | Docker Compose（官方 compose 文件） | immich (VM) |
| `caddy` | Caddy 反向代理 + WebDAV | 自定义二进制（Alpine + systemd） | caddy (LXC) |
| `n8n` | n8n 工作流自动化 | npm 全局安装 + systemd | n8n (LXC) |
| `anki_sync_server` | Anki 同步服务 | pip venv 安装 + systemd | anki (LXC) |
| `rustdesk` | RustDesk 远程桌面 | Docker Compose | rustdesk (VM) |
| `pbs` | Proxmox Backup Server + ZFS 存储 | 系统包 + ZFS 命令 + API 配置 | pbs (VM) |

### 工具 Role（2 个）

执行运维任务，不部署长期运行的服务。

| Role | 职责 | 触发方式 |
|------|------|----------|
| `netbox_sync` | 将 Ansible facts 同步到 Netbox | `sync-netbox.yml`（按需运行） |
| `pbs_client` | 配置 Proxmox 节点连接 PBS | `setup-pbs-backup.yml`（一次性配置） |

---

## Role 目录规范

### 标准结构

```
roles/<role_name>/
├── defaults/main.yml    # 可覆盖的默认变量（优先级 2）
├── tasks/main.yml       # 任务入口
├── handlers/main.yml    # 事件处理器（有 notify 时才需要）
├── templates/           # Jinja2 模板文件
└── files/               # 静态文件（如需要）
```

### 规则

- **命名**：`snake_case`，不使用连字符
- **最小化目录**：只创建实际需要的目录，不保留空目录
- **`defaults/` vs `vars/`**：几乎所有变量都放 `defaults/`（可覆盖）。`vars/` 仅用于角色内部常量（当前无 role 使用 `vars/`）
- **无 `defaults/` 的例外**：`docker` 和 `n8n` — 所有值都是固定的（标准端口、版本号等），不需要可配置变量

### 当前各 Role 目录状态

| Role | defaults | tasks | handlers | templates | 说明 |
|------|----------|-------|----------|-----------|------|
| common | ✅ | ✅ | — | — | SSH 公钥在 inventory `group_vars/all/common.yml` |
| docker | — | ✅ | — | — | 纯安装，无可配置参数 |
| tailscale | ✅ | ✅ | — | — | auth_key 在 `group_vars/tailscale.yml` |
| netbox | ✅ | ✅ | — | — | |
| netbox_sync | ✅ | ✅ | — | — | 需要 `netbox.netbox` collection |
| homepage | ✅ | ✅ | ✅ | ✅ (6) | 模板包含 dashboard 配置 |
| immich | ✅ | ✅ | ✅ | ✅ (2) | |
| caddy | ✅ | ✅ | ✅ | ✅ (1) | Alpine Linux，需要 SSH/Python 预启动 |
| n8n | — | ✅ | ✅ | ✅ (1) | 无可配置参数 |
| anki_sync_server | ✅ | ✅ | ✅ | ✅ (1) | |
| rustdesk | ✅ | ✅ | — | ✅ (1) | |
| pbs | ✅ | ✅ | — | — | tasks 含 ZFS 配置（zfs-verify/zfs-pool/zfs-datastore） |
| pbs_client | ✅ | ✅ | — | — | tasks 拆分为 storage/backup-jobs/pbs-token |

---

## 变量管理策略

### 变量化原则

只提取**真正会因环境而变**的值为变量：

| 应该变量化 | 不应该变量化 |
|-----------|------------|
| 域名（`rustdesk.willfan.me`） | 标准端口（`8007`, `5678`, `21116`） |
| IP 地址（可能随环境变化） | 协议固定标识符（`root@pam`, `backup@pbs`） |
| 凭据 / 密钥 | 软件版本号（与 role 逻辑紧耦合） |
| 文件路径（`/var/lib/rustdesk`） | 第三方服务固定 URL |
| 容器镜像名（可能需要切换版本） | Dashboard 配置中的服务地址 |

### 变量来源优先级

```
inventory host_vars (优先级 10)    → 主机特定配置
inventory group_vars (优先级 8)   → 组级共享配置、vault 间接引用
role defaults (优先级 2)          → 可覆盖的默认值
```

### 密钥变量的间接引用

所有密钥统一存储在 `inventory/group_vars/all/vault.yml`，通过间接引用传递到消费点。

详细的 Vault 架构设计参见：[Ansible Vault Architecture Design](./ansible-vault-architecture.md)

### 各 Role 变量清单

#### 基础设施 Role

**common**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `common_authorized_keys` | `[]` | SSH 公钥列表（实际值在 `group_vars/all/common.yml`） |
| `common_packages` | `[vim, curl, htop, git, net-tools, sudo]` | 基础包列表 |

**tailscale**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `tailscale_dns_server` | `"192.168.1.1"` | LXC 容器的 DNS 服务器 |
| `tailscale_auth_key` | *(group_vars)* | `{{ vault_tailscale_auth_key }}` |

#### 应用服务 Role

**caddy**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `caddy_version` | `"2.8.4"` | Caddy 二进制版本 |
| `caddy_user` / `caddy_group` | `caddy` | 运行用户 |
| `caddy_config_dir` | `/etc/caddy` | 配置目录 |
| `caddy_data_dir` | `/var/lib/caddy` | 数据目录 |
| `caddy_log_dir` | `/var/log/caddy` | 日志目录 |
| `caddy_webdav_root` | `/var/www/webdav` | WebDAV 根目录 |
| `caddy_webdav_port` | `8080` | WebDAV 端口 |
| `caddy_domain` | `localhost` | 域名（实际值在 `host_vars/caddy.yml`） |
| `caddy_reverse_proxies` | `[]` | 反向代理列表（实际值在 `host_vars/caddy.yml`） |
| `cloudflare_api_token` | vault 间接引用 | Cloudflare DNS API Token |
| `caddy_webdav_password_hash` | vault 间接引用 + hash | WebDAV 密码的 bcrypt hash |

**homepage**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `homepage_version` | `"main"` | Git 分支/标签 |
| `homepage_install_dir` | `/opt/homepage` | 安装目录 |
| `homepage_user` / `homepage_group` | `root` | 运行用户 |
| `homepage_port` | `3000` | 监听端口 |
| `homepage_allowed_hosts` | `{{ ansible_host }}:{{ homepage_port }}` | 允许的 hosts |
| `proxmox_api_user` | `"root@pam"` | Proxmox API 用户 |
| `proxmox_api_password` | `""` | Proxmox API 密码（`host_vars` 覆盖） |
| `netbox_api_token` | `""` | Netbox API Token |
| `immich_api_key` | `""` | Immich API Key |
| `tailscale_api_key` | `""` | Tailscale API Key |
| `tailscale_device_id` | `""` | Tailscale Device ID |
| `nodejs_version` | `"18"` | Node.js 主版本 |

**immich**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `immich_app_dir` | `/opt/immich` | 应用目录 |
| `immich_upload_dir` | `{{ immich_app_dir }}/library` | 照片上传目录 |
| `immich_db_dir` | `{{ immich_app_dir }}/postgres` | 数据库目录 |
| `immich_version` | `release` | Docker 镜像标签 |
| `immich_db_username` | `postgres` | 数据库用户名 |
| `immich_db_name` | `immich` | 数据库名 |
| `immich_db_password` | vault 间接引用 | 数据库密码 |

**netbox**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `netbox_git_repo` | *(官方 netbox-docker)* | Git 仓库地址 |
| `netbox_git_version` | `"3.0.2"` | netbox-docker 版本 |
| `netbox_install_dir` | `/opt/netbox-docker` | 安装目录 |
| `netbox_port` | `8080` | 监听端口 |
| `netbox_image` | `netboxcommunity/netbox:v4.1.11` | Docker 镜像 |
| `netbox_superuser_name` | `"admin"` | 超级用户名 |
| `netbox_superuser_email` | `"admin@example.com"` | 超级用户邮箱 |
| `netbox_superuser_password` | vault 间接引用 | 超级用户密码 |
| `netbox_superuser_api_token` | vault 间接引用 | API Token |

**rustdesk**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `rustdesk_relay_host` | `"rustdesk.willfan.me"` | Relay 域名 |
| `rustdesk_data_dir` | `"/var/lib/rustdesk"` | 数据目录 |
| `rustdesk_image` | `"rustdesk/rustdesk-server:latest"` | Docker 镜像 |

**anki_sync_server**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `anki_port` | `8080` | 监听端口 |
| `anki_install_dir` | `/opt/anki-syncserver` | 安装目录 |
| `anki_venv_path` | `{{ anki_install_dir }}/venv` | Python venv 路径 |
| `anki_sync_users` | vault 间接引用 | 用户名:密码列表 |

**pbs**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `pbs_timezone` | `"Australia/Sydney"` | 时区 |
| `pbs_backup_user_email` | `"fanweiblue@gmail.com"` | 备份用户邮箱 |
| `pbs_root_password` | vault 间接引用 | root 密码 |
| `pbs_backup_user_password` | vault 间接引用 | 备份用户密码 |
| `pbs_zfs_pool_name` | `"backup-pool"` | ZFS 池名称 |
| `pbs_zfs_mount_point` | `"/mnt/backup-pool"` | ZFS 挂载点 |
| `pbs_zfs_hdd_devices` | `[]` | HDD 设备列表 |
| `pbs_zfs_nvme_devices` | `[]` | NVMe 设备列表（special vdev） |
| `pbs_zfs_compression` | `"zstd"` | 压缩算法 |
| *(另有 10+ ZFS 配置变量)* | | 详见 `roles/pbs/defaults/main.yml` |

**pbs_client**（20 个变量，详见 `roles/pbs_client/defaults/main.yml`）

主要包括：PBS 连接信息、Proxmox API 凭据、备份调度、保留策略、VM ID 列表等。

#### 工具 Role

**netbox_sync**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `netbox_url` | `"http://192.168.1.104:8080"` | Netbox 服务地址 |
| `netbox_token` | vault 间接引用 | API Token |

---

## 依赖关系图

Role 之间不使用 `meta/main.yml` 声明依赖，而是在 playbook 的 `roles:` 块中显式声明执行顺序。

```
                    ┌─────────┐
                    │ common  │  ← site.yml（所有主机）
                    └─────────┘

                    ┌─────────┐
         ┌─────────│ docker  │─────────┐──────────┐
         │         └─────────┘         │          │
         ▼              ▼              ▼          ▼
    ┌─────────┐   ┌──────────┐   ┌─────────┐ ┌──────────┐
    │ immich  │   │  netbox  │   │rustdesk │ │devcontainer│
    └─────────┘   └──────────┘   └─────────┘ └──────────┘

    ┌───────────┐
    │ tailscale │──────┐
    └───────────┘      ▼
                  ┌──────────┐
                  │ homepage │
                  └──────────┘

    ┌─────┐
    │ pbs │    （deploy-pbs.yml，含 ZFS 存储配置）
    └─────┘
        │
        ▼ （需要 PBS 先部署完成）
  ┌────────────┐
  │ pbs_client │  （setup-pbs-backup.yml）
  └────────────┘

    独立 Role（无依赖）:
    ┌───────┐  ┌──────────────────┐  ┌──────────────┐
    │ caddy │  │ anki_sync_server │  │     n8n      │
    └───────┘  └──────────────────┘  └──────────────┘
```

---

## Playbook 编排模式

### 标准部署 Playbook 结构

每个 `deploy-*.yml` 遵循两段式结构：

```yaml
# Play 1: Deploy
- name: Deploy <Service>
  hosts: <service>
  become: true
  roles:
    - <prerequisite_role>  # 如 docker
    - <service_role>

# Play 2: Verify
- name: Verify <Service> Deployment
  hosts: <service>
  become: true
  tags: [verify]
  tasks:
    - name: Wait for service port
      wait_for:
        port: <port>
        timeout: 60
    - name: Check HTTP endpoint
      uri:
        url: "http://localhost:<port>"
        status_code: [200, 301, 302]
```

### Playbook 与 Role 映射

| Playbook | 目标主机 | Role 组合 | 部署方式 |
|----------|----------|-----------|----------|
| `site.yml` | all | common | 基线配置 |
| `deploy-immich.yml` | immich | docker → immich | Docker Compose |
| `deploy-netbox.yml` | netbox | docker → netbox | Docker Compose |
| `deploy-rustdesk.yml` | rustdesk | docker → rustdesk | Docker Compose |
| `deploy-homepage.yml` | homepage | tailscale → homepage | 源码构建 |
| `deploy-pbs.yml` | pbs | pbs | 系统包 + ZFS |
| `deploy-caddy.yml` | caddy | caddy | 自定义二进制（含 SSH 预启动） |
| `deploy-anki.yml` | anki | anki_sync_server | pip venv |
| `deploy-n8n.yml` | n8n | n8n | npm 全局安装 |
| `install-tailscale.yml` | tailscale | tailscale | 脚本安装 |
| `setup-pbs-backup.yml` | pbs, pve0 | pbs_client | API 配置 |
| `sync-netbox.yml` | pve_lxc:pve_vms:proxmox_cluster | netbox_sync | API 同步 |

---

## 服务网络拓扑

```
Internet
    │
    ▼ (Cloudflare DNS → Tailscale Funnel / Direct)
┌───────────────────────────────────────────────┐
│              Caddy (LXC 105)                  │
│         caddy.willfan.me → reverse proxy      │
│  *.willfan.me:443 → 各服务内网 IP:Port        │
└───┬───────┬───────┬───────┬───────┬───────────┘
    │       │       │       │       │
    ▼       ▼       ▼       ▼       ▼
 homepage  immich  netbox   anki    n8n
 :3000     :2283   :8080    :8080   :5678

                Tailscale VPN (.ts.net)
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
 Proxmox        RustDesk         OCI VM
 Cluster        :21116          (Sydney)
 pve0/1/2

                PBS (192.168.1.249:8007)
                    ▲
                    │ (proxmox-backup-client)
                 pve0 备份任务
                 VMID: 100-106
```

---

## Collection 依赖

`ansible/requirements.yml` 声明了以下 collection：

| Collection | 使用方 |
|------------|--------|
| `community.general` | 通用模块 |
| `community.vmware` | ESXi 管理 |
| `cloud.terraform` | Terraform 动态 inventory |
| `community.docker` | Docker Compose 管理（rustdesk, immich, netbox） |
| `ansible.posix` | POSIX 模块（sysctl 等） |
| `netbox.netbox` | Netbox API 模块（netbox_sync role） |

---

## 相关文档

- [Ansible Vault Architecture Design](./ansible-vault-architecture.md) — 密钥管理架构
- [Ansible Role 重构历程](../learningnotes/2026-01-31-ansible-role-refactoring.md) — 重构过程记录
- [Ansible Patterns and Best Practices](../guides/ansible_patterns_and_best_practices.md) — 最佳实践指南
- [PBS ESXi Deployment Guide](../deployment/pbs_esxi_deployment.md) — PBS 部署指南
