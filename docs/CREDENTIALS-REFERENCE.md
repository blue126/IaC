# 基础设施凭证参考文档

> ⚠️ **隐私警告**: 本文档包含敏感的凭证信息。请妥善保管，不要提交到公开仓库。建议存储在安全的密钥管理工具中。

**文档创建日期**: 2026-01-30  
**更新日期**: 2026-01-30

---

## 目录

- [1. 快速参考](#1-快速参考)
- [2. 服务凭证详细信息](#2-服务凭证详细信息)
- [3. 虚拟机和 LXC 凭证](#3-虚拟机和-lxc-凭证)
- [4. 数据库凭证](#4-数据库凭证)
- [5. API 令牌和密钥](#5-api-令牌和密钥)
- [6. 安全建议](#6-安全建议)
- [7. 密钥轮换计划](#7-密钥轮换计划)

---

## 1. 快速参考

| 服务 | 用户名 | 密码 | 端口 | IP 地址 | 类型 |
|------|--------|------|------|---------|------|
| Anki Sync Server | `anki` | `anki` | 8080 | 192.168.1.100 | LXC |
| Immich PostgreSQL | `postgres` | `admin` | 5432 | 192.168.1.101 | VM (数据库) |
| Immich Web UI | - | - | 2283 | 192.168.1.101 | VM |
| Netbox | `admin` | `admin` | 8080 | 192.168.1.104 | VM |
| Homepage | - | - | 3000 | 192.168.1.103 | LXC |
| Caddy | `admin` | `Admin123...` | 8080 | 192.168.1.105 | LXC (WebDAV) |
| RustDesk | `ubuntu` | `ubuntu` | 21118 | 192.168.1.102 | VM |
| n8n | - | 无密码 | 5678 | 192.168.1.106 | VM |
| Proxmox VE | `root@pam` | 见 SSH 密钥 | 8006 | 192.168.1.50 | 虚拟化主机 |

---

## 2. 服务凭证详细信息

### 2.1 Anki Sync Server (LXC 100)

**用途**: 卡牌同步服务

| 属性 | 值 |
|------|-----|
| 用户名 | `anki` |
| 密码 | `anki` |
| 端口 | 8080 |
| IP 地址 | 192.168.1.100 |
| 类型 | LXC 容器 |
| 安装目录 | `/opt/anki-syncserver/` |
| 服务运行用户 | `root` (家庭实验室简化配置) |
| 配置文件 | `/etc/systemd/system/anki-sync-server.service` |
| 数据目录 | `/opt/anki-syncserver/` |

**连接方式**:
```bash
# SSH 连接 (使用 SSH 密钥)
ssh root@192.168.1.100

# 通过浏览器访问
http://192.168.1.100:8080

# AnkiDroid 配置
同步 URL: http://192.168.1.100:8080
用户名: anki
密码: anki
```

**配置来源**: `ansible/inventory/host_vars/anki.yml`

---

### 2.2 Immich (VM 101)

#### Web 界面
| 属性 | 值 |
|------|-----|
| 端口 | 2283 |
| IP 地址 | 192.168.1.101 |
| URL | `http://192.168.1.101:2283` |
| 类型 | Docker Compose 容器 |

#### PostgreSQL 数据库
| 属性 | 值 |
|------|-----|
| 用户名 | `postgres` |
| 密码 | `admin` |
| 端口 | 5432 (容器内部) |
| 数据库 | `immich` |
| 容器 | `immich_postgres` |

#### Redis 缓存
| 属性 | 值 |
|------|-----|
| 端口 | 6379 (容器内部) |
| 容器 | `immich_redis` |

**连接方式**:
```bash
# SSH 连接
ssh ubuntu@192.168.1.101

# 进入 PostgreSQL 容器
docker exec -it immich_postgres psql -U postgres

# 查看 Docker Compose 状态
docker compose ps
```

**配置来源**: 
- Web: `ansible/inventory/host_vars/immich.yml`
- DB: `ansible/roles/immich/templates/env.j2`

---

### 2.3 Netbox (VM 104)

**用途**: IP 地址管理 (IPAM) 和 数据中心管理 (DCIM)

| 属性 | 值 |
|------|-----|
| 用户名 | `admin` |
| 密码 | `admin` |
| 端口 | 8080 |
| IP 地址 | 192.168.1.104 |
| URL | `http://192.168.1.104:8080` |
| 类型 | Docker Compose 容器 |
| API 令牌 | `0123456789abcdef0123456789abcdef01234567` (默认示例) |

**连接方式**:
```bash
# SSH 连接
ssh ubuntu@192.168.1.104

# 登录 Web UI
http://192.168.1.104:8080
用户名: admin
密码: admin

# API 调用示例
curl -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
     http://192.168.1.104:8080/api/dcim/devices/
```

**配置来源**: `ansible/roles/netbox/defaults/main.yml`

---

### 2.4 Homepage (LXC 103)

**用途**: 仪表板/门户网站

| 属性 | 值 |
|------|-----|
| 端口 | 3000 |
| IP 地址 | 192.168.1.103 |
| URL | `http://192.168.1.103:3000` |
| 类型 | LXC 容器 (Node.js) |
| 安装目录 | `/opt/homepage` |

**相关凭证** (集成使用):
- Proxmox API 用户: `root@pam!homepage` (Proxmox 集成用)
- Proxmox API 密码: 见 Vault
- Immich API Key: 见 Vault
- Tailscale Device ID: `n9rsyfnzLp11CNTRL`

**连接方式**:
```bash
# SSH 连接
ssh root@192.168.1.103

# 访问仪表板
http://192.168.1.103:3000
```

**配置来源**: `ansible/inventory/host_vars/homepage.yml`

---

### 2.5 Caddy (LXC 105)

**用途**: 反向代理和 WebDAV 服务

| 属性 | 值 |
|------|-----|
| 用户名 (WebDAV) | `admin` |
| 密码 (WebDAV) | `Admin123...` |
| 端口 | 8080 |
| IP 地址 | 192.168.1.105 |
| 类型 | LXC 容器 |
| 域名 | `willfan.me` |

**反向代理配置**:
```yaml
- Homepage: 192.168.1.103:3000
- Immich: 192.168.1.101:2283
- Netbox: 192.168.1.104:8080
- Anki: 192.168.1.100:8080
- Proxmox: 192.168.1.50:8006 (不验证 HTTPS)
- n8n: 192.168.1.106:5678
- RustDesk: 192.168.1.102:21118
```

**连接方式**:
```bash
# SSH 连接
ssh root@192.168.1.105

# WebDAV 连接 (文件管理器/Finder)
webdav://admin:Admin123...@192.168.1.105:8080
```

**配置来源**: `ansible/inventory/host_vars/caddy.yml`

---

### 2.6 RustDesk (VM 102)

**用途**: 远程桌面访问

| 属性 | 值 |
|------|-----|
| SSH 用户 | `ubuntu` |
| SSH 密码 | `ubuntu` |
| RustDesk 端口 | 21118 |
| IP 地址 | 192.168.1.102 |
| 类型 | VM |

**连接方式**:
```bash
# SSH 连接
ssh ubuntu@192.168.1.102

# RustDesk 连接信息
端口: 21118
```

**配置来源**: `ansible/playbooks/deploy-rustdesk.yml`

---

### 2.7 n8n (VM 106)

**用途**: 工作流自动化

| 属性 | 值 |
|------|-----|
| 端口 | 5678 |
| IP 地址 | 192.168.1.106 |
| URL | `http://192.168.1.106:5678` |
| 类型 | VM |
| 认证 | 无密码 (仅本地网络) |

**连接方式**:
```bash
# SSH 连接
ssh ubuntu@192.168.1.106

# 访问 n8n UI
http://192.168.1.106:5678
```

---

## 3. 虚拟机和 LXC 凭证

### 3.1 Proxmox VE 虚拟机 (VM) - 通用凭证

**云初始化默认配置**:

| 属性 | 值 |
|------|-----|
| SSH 用户 | `ubuntu` |
| SSH 密码 | `ubuntu` |
| 操作系统 | Ubuntu 22.04 LTS |
| 认证方式 | SSH 密钥 (推荐) + 密码 |

**cloud-init 设置**:
```yaml
vm_ciuser: ubuntu
vm_cipassword: ubuntu
vm_ssh_pwauth: true
```

**SSH 连接**:
```bash
# 使用密钥 (推荐)
ssh -i ~/.ssh/id_rsa ubuntu@<vm-ip>

# 使用密码
ssh ubuntu@<vm-ip>
# 输入密码: ubuntu
```

**Ansible 连接**:
```yaml
ansible_user: ubuntu
ansible_ssh_pass: ubuntu
ansible_become_password: ubuntu
```

**配置来源**: `ansible/inventory/group_vars/pve_vms.yml`

---

### 3.2 Proxmox LXC 容器 - 通用凭证

**SSH 配置**:

| 属性 | 值 |
|------|-----|
| SSH 用户 | `root` |
| 认证方式 | SSH 密钥 |
| 密钥对 | 存储在 Proxmox/Terraform 配置中 |

**Ansible 连接**:
```yaml
ansible_user: root
# SSH 密钥认证
```

**配置来源**: `ansible/inventory/group_vars/pve_lxc.yml`

---

## 4. 数据库凭证

### 4.1 Immich PostgreSQL

| 属性 | 值 |
|------|-----|
| 用户 | `postgres` |
| 密码 | `admin` |
| 数据库 | `immich` |
| 主机 | `immich_postgres` (容器名) |
| 端口 | 5432 |

**连接**:
```bash
# 从宿主机 SSH 后
docker exec -it immich_postgres psql -U postgres -d immich

# 备份数据库
docker exec immich_postgres pg_dump -U postgres immich > backup.sql

# 恢复数据库
docker exec -i immich_postgres psql -U postgres immich < backup.sql
```

**配置来源**: 
- `ansible/roles/immich/defaults/main.yml`
- `ansible/inventory/host_vars/immich.yml`

---

### 4.2 Netbox PostgreSQL

| 属性 | 值 |
|------|-----|
| 用户 | `netbox` (Docker 内部用户) |
| 密码 | 在 Docker Compose 中配置 |
| 数据库 | `netbox` |
| 主机 | `netbox-postgres` |
| 端口 | 5432 |

**配置来源**: `ansible/roles/netbox/defaults/main.yml`

---

## 5. API 令牌和密钥

### 5.1 Netbox API 令牌

**默认 API 令牌**:
```
0123456789abcdef0123456789abcdef01234567
```

> ⚠️ **注意**: 这是示例令牌，实际部署中应该生成新的。

**生成新令牌**:
```bash
# 登录 Netbox Web UI
http://192.168.1.104:8080

# 导航: Admin -> API Tokens -> Add Token
# 选择用户: admin
# 生成令牌
```

**API 调用示例**:
```bash
curl -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
     http://192.168.1.104:8080/api/dcim/devices/
```

**配置来源**: `ansible/roles/netbox/defaults/main.yml`

---

### 5.2 Cloudflare API 令牌 (Caddy DNS-01)

**变量**: `vault_cloudflare_api_token`

**用途**: Caddy 自动 HTTPS 证书更新 (DNS-01 质询)

**获取方式**:
1. 登录 Cloudflare 账户
2. Account → API Tokens → Create Token
3. 选择 "Edit zone DNS" 权限
4. 复制令牌

**配置来源**: `ansible/playbooks/deploy-caddy.yml`

---

### 5.3 Tailscale 凭证

#### Tailscale Auth Key
**变量**: `vault_tailscale_auth_key`

**用途**: 通过 Tailscale VPN 连接设备

**获取方式**:
1. 登录 Tailscale Admin
2. Settings → Keys
3. 生成 Auth Key
4. 选择"可重用"和"预授权"选项

#### Tailscale Device ID & API Key
**变量**: 
- `tailscale_device_id`: `n9rsyfnzLp11CNTRL`
- `vault_tailscale_api_key_homepage`

**用途**: Homepage 仪表板集成

**配置来源**: `ansible/inventory/host_vars/homepage.yml`

---

### 5.4 Immich API Key

**变量**: `vault_immich_api_key_homepage`

**用途**: Homepage 集成 Immich 相册查看

**获取方式**:
1. 登录 Immich Web UI (http://192.168.1.101:2283)
2. 设置 → API Keys → New API Key
3. 生成密钥
4. 复制到 Vault

---

### 5.5 Proxmox API 凭证

**Proxmox API 用户** (Homepage 集成):
```
root@pam!homepage
```

**密码**: `vault_proxmox_api_password_homepage`

**用途**: Homepage 仪表板显示 Proxmox 资源

**获取 API Token** (更安全):
```bash
# 在 Proxmox 节点上
pveum user add automation@pam
pveum aclmod / -user automation@pam -role Administrator
pveum user token add automation@pam dashboard-token
```

---

## 6. 安全建议

### 6.1 密码管理

**✅ 推荐做法**:
- [ ] 使用 Ansible Vault 加密所有机密信息
- [ ] 生成强密码 (最少 16 个字符，包含大小写、数字、特殊字符)
- [ ] 定期轮换密码 (建议每 90 天)
- [ ] 不要将凭证提交到 Git
- [ ] 使用专用的密钥管理工具 (例如: HashiCorp Vault, 1Password)

### 6.2 Vault 加密

**编辑 Vault 文件**:
```bash
cd /Users/weierfu/Projects/IaC/ansible

# 编辑加密文件
ansible-vault edit inventory/group_vars/all/vault.yml

# 查看加密文件
ansible-vault view inventory/group_vars/all/vault.yml
```

### 6.3 SSH 密钥管理

**生成新 SSH 密钥对** (Proxmox LXC):
```bash
# 在本地机器上
ssh-keygen -t ed25519 -f ~/.ssh/id_proxmox -N ""

# 添加到 Terraform 配置
# terraform/proxmox/variables.tf
variable "sshkeys" {
  type = list(string)
  default = [
    file("~/.ssh/id_proxmox.pub")
  ]
}
```

### 6.4 网络隔离

**当前网络配置**:
- LXC 容器: `192.168.1.x/24` (本地网络)
- Tailscale VPN: 用于远程安全访问
- **没有公网直接暴露** ✓

**加强措施**:
- [ ] 配置防火墙规则 (iptables)
- [ ] 使用 Tailscale 作为所有外部访问的入口
- [ ] 启用 HTTPS/TLS 加密所有连接

### 6.5 审计和监控

**建议工具**:
- [ ] 启用 Docker 容器日志
- [ ] 配置 syslog 集中日志
- [ ] 定期检查访问日志
- [ ] 设置告警规则

---

## 7. 密钥轮换计划

### 7.1 轮换时间表

| 凭证类型 | 轮换周期 | 优先级 | 备注 |
|---------|---------|--------|------|
| SSH 密钥 | 90 天 | 高 | 使用 Ed25519 密钥 |
| 应用密码 | 90 天 | 中 | Immich, Netbox 等 |
| API 令牌 | 180 天 | 中 | Cloudflare, Tailscale 等 |
| 数据库密码 | 90 天 | 高 | PostgreSQL 凭证 |
| Vault 加密密钥 | 365 天 | 低 | 仅在必要时轮换 |

### 7.2 轮换步骤示例

**轮换 Immich PostgreSQL 密码**:

1. 生成新密码
2. 更新 `ansible/inventory/host_vars/immich.yml`:
   ```yaml
   immich_db_password: new_secure_password
   ```
3. 运行 Ansible playbook:
   ```bash
   ansible-playbook playbooks/deploy-immich.yml --tags config
   ```
4. 更新连接字符串
5. 测试数据库连接
6. 更新备份/文档

### 7.3 日志记录

**建议格式**:
```markdown
## 密钥轮换记录

### [日期] 轮换 Immich PostgreSQL 密码
- **原因**: 定期轮换
- **执行人**: [人名]
- **变更内容**: PostgreSQL 密码更新
- **验证**: 数据库连接测试通过 ✓
```

---

## 附录 A: 快速故障排除

### 问题: 无法连接到 Anki Sync Server

**检查清单**:
```bash
# 1. 检查 LXC 是否运行
pct status 100

# 2. SSH 连接
ssh root@192.168.1.100

# 3. 检查服务状态
systemctl status anki-sync-server

# 4. 查看日志
journalctl -u anki-sync-server -n 50

# 5. 检查端口监听
ss -tlnp | grep 8080
```

### 问题: 数据库密码错误

```bash
# Immich PostgreSQL
docker exec immich_postgres psql -U postgres -c "ALTER USER postgres WITH PASSWORD 'newpass';"

# 更新环境变量后重启
docker compose restart
```

### 问题: API 令牌失效

```bash
# 重新生成 Netbox API 令牌
# 1. 登录 Web UI
# 2. Admin → API Tokens → Delete old token
# 3. Admin → API Tokens → Add Token
# 4. 生成新令牌
# 5. 更新配置
```

---

## 附录 B: 相关配置文件位置

| 配置项 | 文件路径 |
|--------|---------|
| Anki Sync Server | `ansible/inventory/host_vars/anki.yml` |
| Immich | `ansible/inventory/host_vars/immich.yml` |
| Netbox | `ansible/roles/netbox/defaults/main.yml` |
| Homepage | `ansible/inventory/host_vars/homepage.yml` |
| Caddy | `ansible/inventory/host_vars/caddy.yml` |
| VM 通用凭证 | `ansible/inventory/group_vars/pve_vms.yml` |
| LXC 通用凭证 | `ansible/inventory/group_vars/pve_lxc.yml` |
| Vault 机密 | `ansible/inventory/group_vars/all/vault.yml` |

---

## 附录 C: 密码强度检查

**生成强密码示例**:
```bash
# 使用 openssl
openssl rand -base64 32

# 使用 python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 使用 pwgen (需要安装)
pwgen -s 32 1
```

**密码强度要求**:
- 最少 12-16 个字符
- 包含大写字母 (A-Z)
- 包含小写字母 (a-z)
- 包含数字 (0-9)
- 包含特殊字符 (!@#$%^&*)
- 避免字典词汇
- 避免个人信息 (生日、名字等)

---

## 文档更新历史

| 版本 | 日期 | 变更 | 作者 |
|------|------|------|------|
| 1.0 | 2026-01-30 | 初始创建 - 总结所有服务凭证 | AI Assistant |

---

**最后更新**: 2026-01-30  
**下次审查**: 2026-04-30 (每季度审查一次)

> **免责声明**: 本文档包含敏感信息。请确保按照公司安全政策妥善保管和销毁。

