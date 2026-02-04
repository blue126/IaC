# 故障排查文档结构总结

## 文件清单与统计

| 文件名 | 大小 | 问题数 | 主要关键词 |
|------|------|--------|-----------|
| **README.md** | 6.0K | - | 导航、快速诊断、最佳实践 |
| **terraform-issues.md** | 14K | 8 | Provider版本、磁盘调整、API Token |
| **ansible-issues.md** | 15K | 6 | 依赖管理、Inventory迁移、模板参数化 |
| **network-connectivity.md** | 12K | 4 | SMB性能、Tailscale、Caddy、DNS |
| **deployment-issues.md** | 16K | 4 | Netbox版本、异步任务、RustDesk架构 |
| **总计** | **63K** | **22** | 综合覆盖 |

---

## 文档内容详细列表

### README.md (入口文档)
**功能**: 文档导航和快速诊断

**包含章节**:
1. 按症状分类表 - 快速定位问题
2. 四个主文档概览
3. 快速诊断流程图
4. 通用诊断步骤 (3 步)
5. 最佳实践建议 (7 个)
6. 相关资源链接

**使用场景**: 
- 第一次使用本文档集的用户
- 不确定问题属于哪个类别时

---

### terraform-issues.md (Terraform 故障)
**问题数**: 8 个完整问题

#### 问题列表:
1. **Provider 崩溃 (Panic)**
   - 症状: panic: interface conversion: interface {} is nil
   - 原因: v3.0.2-rc05 版本 Bug
   - 解决: 升级到 v3.0.2-rc04

2. **权限错误 (Permission Denied)**
   - 症状: missing: [VM.Monitor] 权限
   - 原因: PVE 8 权限模型变更，Provider 不适配
   - 解决: 使用 API Token + privsep 0

3. **虚拟机无法启动 / UEFI Shell**
   - 症状: VM 启动进入 UEFI Shell，Cloud-Init 无法运行
   - 原因: 磁盘缩容导致系统盘被替换为空盘
   - 解决: 脚本校验：final_size >= template_size

4. **Cloud-Init 与 QEMU Agent 依赖链**
   - 症状: QEMU guest agent is not running
   - 原因: 操作系统丢失 → Cloud-Init 无法运行 → Agent 无法安装
   - 解决: 先解决磁盘问题，确保模板配置完整

5. **Docker Restart Policy 配置漂移**
   - 症状: 重启后服务没有自动拉起
   - 原因: 缺少 `restart: unless-stopped` 策略，且没有覆盖依赖服务
   - 解决: 为所有服务（含 DB）添加重启策略

6. **Terraform Lifecycle 与启动顺序**
   - 症状: VM 启动顺序错误，Terraform 虚假变更
   - 原因: 未显式定义启动顺序，残留磁盘属性漂移
   - 解决: 添加 `boot = "order=scsi0;ide2;net0"` + `ignore_changes`

7. **Terraform ID 漂移**
   - 症状: terraform plan 显示 vmid: 102 -> 0 (强制重建)
   - 原因: State 中的 VMID 与配置不一致
   - 解决: 从 IP 最后一段提取 VMID (192.168.1.102 → VMID 102)

8. **Terraform Drift - 虚假变更**
   - 症状: Plan 显示大量虚假变更 (tags, format, description)
   - 原因: Provider 默认值不一致，外部修改
   - 解决: 显式定义字段或使用 `ignore_changes`

---

### ansible-issues.md (Ansible 故障)
**问题数**: 6 个完整问题

#### 问题列表:
1. **Ansible Callback 插件报错**
   - 症状: The 'community.general.yaml' callback plugin has been removed
   - 原因: Ansible 2.13+ 移除了外部插件
   - 解决: 更新 ansible.cfg，使用 `default` + `callback_result_format = yaml`

2. **DevContainer 环境依赖缺失**
   - 症状 A: passlib 库缺失
   - 症状 B: ansible.posix 集合缺失
   - 原因: DevContainer 是干净环境，未自动安装
   - 解决: 创建 `requirements.txt` + `requirements.yml`

3. **检测命令是否存在**
   - 错误做法: 使用 `command` 模块（会抛异常）
   - 正确做法: 使用 `shell: command -v <cmd>` + `ignore_errors: true`
   - 原因: Shell 返回退出码，而不是抛异常

4. **从静态到动态 Inventory 的数据丢失**
   - 症状: 删除静态 Inventory 后，配置丢失
   - 原因: 混淆了"寻址"(Infrastructure) 与"配置"(Configuration)
   - 解决: 黄金法则 - "迁移变量到 host_vars，再删除文件"
   - 结构: terraform.yml (寻址) + host_vars/ (配置)

5. **模板硬编码导致 Role 不通用**
   - 症状: Role 绑定特定域名，无法在其他环境复用
   - 原因: 模板中硬编码了业务逻辑
   - 解决: 参数化模板，使用 Jinja2 变量

6. **配置管理幂等性问题**
   - 症状: 修改 Ansible 代码后，问题仍然存在
   - 原因: 误认为 Ansible 会自动监测文件变更
   - 解决: 必须重新运行 Playbook 才能应用配置

---

### network-connectivity.md (网络问题)
**问题数**: 4 个完整问题 + 1 个诊断指南

#### 问题列表:
1. **SMB 文件传输速度慢 (5 MB/s)**
   - 症状: Windows SMB 上传速度卡在 5 MB/s
   - 诊断: Ping 延迟异常 (10-12ms)，Tracert 显示经过 Tailscale IP
   - 原因: Tailscale 子网路由优先级劫持，流量被强制通过 VPN 加密
   - 解决: 禁用 Tailscale "Use Subnet Routes"
   - 效果: Wi-Fi 提升到 60 MB/s，有线提升到 200 MB/s

2. **Tailscale MagicDNS 与 Ansible 冲突**
   - 症状: Ansible SSH 连接到 pve0 失败 (Tailscale ACL 限制)
   - 原因: MagicDNS 将 pve0 解析到 Tailscale IP (100.x.x.x)，触发 ACL
   - 解决: Inventory 中使用内网 IP (192.168.1.50) 而不依赖 DNS

3. **Caddy WebDAV 指令顺序冲突**
   - 症状: Error: directive 'webdav' is not an ordered HTTP handler
   - 原因: `webdav` 是第三方插件，不在 Caddy 优先级列表中
   - 解决: 使用 `route` 块明确执行顺序
   - 示例: route { file_server browse; webdav; }

4. **SSH 连接权限问题**
   - 症状: Permission denied (publickey,password) 或密钥类型不匹配
   - 原因: SSH 密钥配置错误或 known_hosts 缺失
   - 解决: 配置 `ansible.cfg` + SSH 公钥部署

**诊断指南**: 网络诊断三板斧
- Ping (检测连通性和延迟)
- Tracert (跟踪路由路径)
- Route (查看系统路由表)

---

### deployment-issues.md (部署问题)
**问题数**: 4 个完整问题

#### 问题列表:
1. **Netbox 容器启动失败 - 版本兼容性**
   - 症状 A: DATABASE 参数缺失 (django.core.exceptions.ImproperlyConfigured)
   - 症状 B: Postgres 版本升级冲突
   - 症状 C: 用户不存在 (unable to find user netbox)
   - 原因: netbox-docker 版本与 Netbox 应用版本不匹配
   - 解决: 使用 netbox-docker v3.0.2 tag + 修复 docker-compose.override.yml
   - 关键: 三容器 (netbox/worker/housekeeping) 版本必须一致

2. **Ansible 异步任务超时**
   - 症状: docker compose up -d 超时失败，但容器实际在运行
   - 原因: Netbox 首次启动需要数据库迁移 (2-5 分钟)，docker compose 阻塞等待
   - 解决: 使用 `async: 600` + `poll: 10` 允许长时间运行

3. **RustDesk 架构误解**
   - 误解 A: 原生 RustDesk Server 有 Web 界面 (实际无)
   - 误解 B: 所有流量都通过反代 Caddy (实际 TCP/UDP 21116/21117 需直连)
   - 原因: 架构设计的基本理解缺陷
   - 解决: RustDesk Server 仅提供后台服务，网页需额外部署 rustdesk-server-web
   - DNS 配置: rustdesk.willfan.me 指向 RustDesk VM，不走 Caddy

4. **内网 DNS 解析问题**
   - 症状: Docker 容器无法解析域名，但宿主机能解析
   - 原因: DNS Split-Horizon，容器使用独立的内部 DNS
   - 诊断法: 控制变量法 - 先用 IP 测试，再用域名，隔离 DNS 问题
   - 解决: 在 docker-compose.yml 中配置 DNS 服务器

---

## 学习路径建议

### 场景 1: 遇到一个具体问题
1. 读 **README.md** 的"按症状分类表"
2. 定位相关的专题文档
3. 查看相应的"问题"章节

### 场景 2: 学习基础设施部署
推荐阅读顺序:
1. **terraform-issues.md** - 理解基础设施代码管理
2. **ansible-issues.md** - 理解配置管理
3. **network-connectivity.md** - 理解网络架构
4. **deployment-issues.md** - 理解容器部署

### 场景 3: 完全新手
1. 先读 **README.md** 的"最佳实践建议"
2. 按照推荐阅读顺序学习
3. 对照实际项目查看具体问题

---

## 核心原则总结

### 1. 显式定义，不相信默认值
- 磁盘大小、引导顺序、重启策略、权限、版本都要明确指定
- 不要依赖系统"可能"的默认行为

### 2. 环境隔离与复现
- 使用 DevContainer 确保可复现
- 显式声明依赖 (requirements.txt / requirements.yml)

### 3. 数据与逻辑分离
- 基础设施数据 (Terraform) ≠ 应用配置 (Ansible)
- 从静态 Inventory 迁移到动态 Inventory 时要先迁移数据

### 4. 版本锁定
- 避免使用 `latest` tag
- 容器组必须版本一致 (netbox/worker/housekeeping)

### 5. 异步处理长时间任务
- 使用 async/poll 参数避免超时

### 6. 增量诊断
- IP → DNS → 应用，逐层排除
- 控制变量法隔离问题根本原因

---

## 相关外部资源

- Terraform: https://www.terraform.io/
- Terraform Proxmox Provider: https://github.com/telmate/terraform-provider-proxmox
- Ansible: https://docs.ansible.com/
- Proxmox VE: https://pve.proxmox.com/wiki/
- Docker: https://docs.docker.com/
- Tailscale: https://tailscale.com/kb/

---

**文档生成日期**: 2026-01-30
**覆盖的技术栈**: Terraform 1.x, Ansible 2.13+, Docker 20+, Proxmox VE 8+, Tailscale
**总知识库**: 22 个问题，63KB 文档，覆盖 5 个主要技术领域
