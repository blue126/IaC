# Learning Notes Index

这个目录包含基础设施即代码 (IaC)、网络、应用部署等领域的学习笔记和故障排查记录。

**最后更新**: 2026-01-30
**文档数量**: 31 篇
**覆盖范围**: Terraform, Ansible, Proxmox, Netbox, Tailscale, LXC, n8n, Immich, RustDesk 等

---

## 导航

1. [按日期排序](#按日期排序-最新到最旧)
2. [按主题分类](#按主题分类)
3. [学习路径](#学习路径)
4. [文档关联](#文档关联)
5. [元数据](#元数据统计)

---

## 按日期排序 (最新到最旧)

### 2026-01-29

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2026-01-29 | [Ansible 踩坑记录 (Callback, Dependencies, Command Check)](./2026-01-29-ansible-troubleshooting.md) | Ansible, Troubleshooting, Best Practices | **Active** | Ansible YAML callback 弃用、环境依赖缺失、命令检测的鲁棒性解决方案 |
| 2026-01-29 | [从静态 Inventory 迁移到动态 Inventory 的数据丢失陷阱](./2026-01-29-inventory-migration-trap.md) | Ansible, Refactoring, Best Practices | **Active** | 基础设施重构中数据丢失的根因分析，引入"库存 vs 配置分离"原则 |
| 2026-01-29 | [RustDesk 部署与 DNS 连接排查](./2026-01-29-rustdesk-deployment-lessons.md) | RustDesk, DNS, Troubleshooting | **Active** | RustDesk 架构说明、客户端 vs 代理流程、DNS Split-Horizon 问题 |

### 2026-01-28

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2026-01-28 | [Rustdesk 部署与 Terraform State 管理](./2026-01-28-rustdesk-terraform.md) | Rustdesk, Ansible, Terraform, DevOps | **Active** | 通过本地脚本从 Terraform Cloud 获取动态库存，配置 RustDesk Relay 地址 |
| 2026-01-28 | [SSH Key 管理的混合策略 (Terraform + Ansible)](./2026-01-28-ssh-key-management-strategy.md) | Terraform, Ansible, SSH, Pattern | **Active** | "Bootstrap Key" 模式：无需 Terraform VM 重建即可管理 SSH 访问 |

### 2025-12-21

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-12-21 | [ESXi 集成与 Ansible 虚拟环境实践笔记](./2025-12-21-esxi-integration-and-venv.md) | Terraform, Ansible, ESXi, Python, DevOps | **Active** | ESXi Provider 选型、VM 部署调试、Ansible Python venv 依赖管理 |

### 2025-12-15

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-12-15 | [n8n Deployment on Proxmox LXC](./2025-12-15-deploying-n8n-on-lxc.md) | n8n, LXC, Proxmox, Ansible, Terraform | **Active** | npm 方法部署 n8n，LXC 容器中的 Node.js 应用管理 |

### 2025-12-11

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-12-11 | [ELK 与 LPG 日志方案对比](./2025-12-11-elk-vs-lpg-comparison.md) | Logging, Architecture, Best Practices | **Active** | ELK 与 LPG 栈的核心区别、成本、性能、扩展性分析 |

### 2025-12-04

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-12-04 | [Ansible Tags 与变量作用域 (Variable Scope)](./2025-12-04-ansible-tags-and-variables.md) | Ansible, Scoping, Best Practices | **Active** | Ansible tags 使用时 undefined variable 问题的根因和解决方案 |
| 2025-12-04 | [混合 IaC 工作流：Terraform 与 Ansible 协同管理 Netbox](./2025-12-04-hybrid-iac-netbox-workflow.md) | Terraform, Ansible, Netbox, Architecture | **Active** | Terraform 与 Ansible 协同管理 Netbox，状态冲突解决方案 |
| 2025-12-04 | [Netbox 数据填充：Terraform vs Ansible](./2025-12-04-netbox-population-terraform-vs-ansible.md) | Terraform, Ansible, Netbox, Architecture | **Active** | Netbox 数据填充的两种方法对比，各自优缺点分析 |
| 2025-12-04 | [Tailscale MagicDNS 与 Split DNS 原理](./2025-12-04-tailscale-magicdns-and-split-dns.md) | Tailscale, DNS, Networking | **Active** | MagicDNS 原理、Split DNS 配置、DNS 解析链路 |
| 2025-12-04 | [Terraform Proxmox Disk & Cloud-Init 故障排查笔记](./2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md) | Terraform, Proxmox, Cloud-Init, Troubleshooting | **Active** | 磁盘缩小限制、Cloud-Init 驱动器挂载、UEFI/OVMF 配置问题 |
| 2025-12-04 | [ZFS 存储池迁移、扩容与重命名实战笔记](./2025-12-04-zfs-pool-migration-and-expansion.md) | ZFS, Storage, Proxmox, DevOps | **Active** | 1TB 单盘到 2TB Mirror 迁移、在线扩容、无停机时间迁移 |

### 2025-12-03

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-12-03 | [Ansible Abstraction Levels: Module vs. Role vs. Task](./2025-12-03-ansible-abstraction-levels.md) | Ansible, Abstraction, Best Practices | **Active** | Custom Module 与 Role 的设计选择，Tailscale Serve 用例 |
| 2025-12-03 | [Caddy WebDAV 配置与 Tailscale ACL 故障排查](./2025-12-03-caddy-webdav-tailscale-troubleshooting.md) | Caddy, Tailscale, WebDAV, Troubleshooting | **Active** | Tailscale ACL 导致的 Ansible 连接失败，Caddy 指令顺序冲突 |

### 2025-12-02

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-12-02 | [Ansible Inventory 结构重构与最佳实践](./2025-12-02-ansible-inventory-refactoring.md) | Ansible, Inventory, Best Practices | **Active** | Inventory 目录结构优化，group_vars 组织，多层次分组策略 |
| 2025-12-02 | [Ansible Vault Secret Management](./2025-12-02-ansible-vault-secret-management.md) | Ansible, Security, Best Practices | **Active** | Ansible Vault 密钥管理策略、加密/解密、CI/CD 集成 |
| 2025-12-02 | [Proxmox, Terraform & Ansible 集成笔记](./2025-12-02-proxmox-terraform-ansible-immich.md) | Proxmox, Terraform, Ansible, Immich | **Active** | Terraform 创建的 VM 继承 DNS、Immich 部署集成 |
| 2025-12-02 | [Tailscale 在 Proxmox LXC 与混合云环境中的深度集成](./2025-12-02-tailscale-integration-refactoring.md) | Tailscale, Proxmox, LXC, Network | **Active** | LXC 容器运行 Tailscale 的挑战、Ansible 重构、混合云集成 |

### 2025-12-01

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-12-01 | [Next.js 应用 LXC 部署中的内存需求与资源规划](./2025-12-01-homepage-lxc-deployment.md) | Homepage, LXC, Proxmox, Deployment | **Active** | Homepage (Next.js) LXC 部署、pnpm 构建、内存规划 |
| 2025-12-01 | [Homepage Proxmox 集成配置指南](./2025-12-01-homepage-proxmox-integration.md) | Homepage, Proxmox, Integration | **Active** | Proxmox VE 集成配置、API 认证、资源监控 |

### 2025-11-30

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-11-30 | [Anki Sync Server Deployment - Learning Notes](./2025-11-30-anki-sync-server-deployment.md) | Anki, Deployment, Terraform, Ansible | **Active** | Anki Sync Server 在 LXC 上的部署、配置、数据库管理 |
| 2025-11-30 | [Ansible 部署验证模式与 Immich 模块化重构](./2025-11-30-ansible-deployment-verification.md) | Ansible, Verification, Immich, Patterns | **Active** | 部署后验证模式 (ports, services, HTTP, DB)、Immich 角色重构 |
| 2025-11-30 | [LXC 与 VM 网络桥接拓扑学习笔记](./2025-11-30-lxc-vm-network-bridge.md) | LXC, VM, Network, Proxmox, Netbox | **Active** | veth/tap 网络绑定、vmbr 桥接配置、Netbox 建模 |
| 2025-11-30 | [Terraform Proxmox Provider 崩溃与版本兼容性问题](./2025-11-30-terraform-proxmox-provider-crash.md) | Terraform, Proxmox, Provider, Troubleshooting | **Superseded** | 参考 `guides/terraform_proxmox_complete_guide.md` |
| 2025-11-30 | [Terraform 代码重构与状态对齐](./2025-11-30-terraform-refactoring-best-practices.md) | Terraform, Refactoring, Modules, State | **Superseded** | 已整合到正式指南中 |

### 2025-11-29

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-11-29 | [Ansible 部署 Netbox 与 Docker Compose 最佳实践](./2025-11-29-ansible-netbox-docker.md) | Ansible, Docker, Netbox, DevOps | **Active** | Ansible Roles、Docker Compose V2、Override Pattern |
| 2025-11-29 | [Netbox 4.1.11 部署：版本匹配与配置调试](./2025-11-29-netbox-deployment-version-troubleshooting.md) | Netbox, Docker, Version Compatibility, Troubleshooting | **Superseded** | 参考 `guides/netbox_deployment_guide.md` |

### 2025-11-28

| 日期 | 标题 | 标签 | 状态 | 摘要 |
|------|------|------|------|------|
| 2025-11-28 | [Terraform 模块化重构、Netbox 部署与 Cloud-Init 深度调试](./2025-11-28-terraform-modules-netbox-debugging.md) | Terraform, Proxmox, Cloud-Init, Netbox | **Superseded** | 已整合到 `guides/terraform_proxmox_complete_guide.md` |
| 2025-11-28 | [Terraform Learning Notes - Proxmox Deployment](./2025-11-28-terraform-proxmox.md) | Terraform, Proxmox, IaC | **Superseded** | 已整合到 `guides/terraform_proxmox_complete_guide.md` |

---

## 按主题分类

### Terraform 相关

**初级 (Foundation)**
- [Terraform Learning Notes - Proxmox Deployment](./2025-11-28-terraform-proxmox.md) - 初始设置与基本概念 (Superseded)
- [SSH Key 管理的混合策略](./2026-01-28-ssh-key-management-strategy.md) - Bootstrap Key 模式

**中级 (Core Concepts)**
- [Terraform 模块化重构、Netbox 部署与 Cloud-Init 深度调试](./2025-11-28-terraform-modules-netbox-debugging.md) - 模块化设计 (Superseded)
- [Terraform 代码重构与状态对齐](./2025-11-30-terraform-refactoring-best-practices.md) - 重构最佳实践 (Superseded)
- [Terraform Proxmox Disk & Cloud-Init 故障排查笔记](./2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md) - 磁盘与 Cloud-Init 问题

**高级 (Integration & Troubleshooting)**
- [Terraform Proxmox Provider 崩溃与版本兼容性问题](./2025-11-30-terraform-proxmox-provider-crash.md) - Provider 版本问题 (Superseded)
- [Rustdesk 部署与 Terraform State 管理](./2026-01-28-rustdesk-terraform.md) - Terraform State 管理
- [混合 IaC 工作流：Terraform 与 Ansible 协同管理 Netbox](./2025-12-04-hybrid-iac-netbox-workflow.md) - 与 Ansible 协同

**相关正式指南**
- 📖 `guides/terraform_proxmox_complete_guide.md` - 完整参考

---

### Ansible 相关

**初级 (Foundation)**
- [Ansible 部署 Netbox 与 Docker Compose 最佳实践](./2025-11-29-ansible-netbox-docker.md) - Roles 与 Docker Compose
- [Ansible 部署验证模式与 Immich 模块化重构](./2025-11-30-ansible-deployment-verification.md) - 验证模式

**中级 (Best Practices)**
- [Ansible Inventory 结构重构与最佳实践](./2025-12-02-ansible-inventory-refactoring.md) - Inventory 设计
- [Ansible Vault Secret Management](./2025-12-02-ansible-vault-secret-management.md) - 密钥管理
- [从静态 Inventory 迁移到动态 Inventory 的数据丢失陷阱](./2026-01-29-inventory-migration-trap.md) - 迁移陷阱

**高级 (Advanced Patterns)**
- [Ansible Abstraction Levels: Module vs. Role vs. Task](./2025-12-03-ansible-abstraction-levels.md) - 抽象层设计
- [Ansible Tags 与变量作用域 (Variable Scope)](./2025-12-04-ansible-tags-and-variables.md) - Tags 与作用域
- [Ansible 踩坑记录](./2026-01-29-ansible-troubleshooting.md) - 常见问题解决

---

### Netbox 相关

**初级 (Foundation)**
- [Netbox 4.1.11 部署：版本匹配与配置调试](./2025-11-29-netbox-deployment-version-troubleshooting.md) - 部署与版本问题 (Superseded)

**中级 (Integration)**
- [Terraform 模块化重构、Netbox 部署与 Cloud-Init 深度调试](./2025-11-28-terraform-modules-netbox-debugging.md) - 初始集成 (Superseded)
- [LXC 与 VM 网络桥接拓扑学习笔记](./2025-11-30-lxc-vm-network-bridge.md) - Netbox 网络建模

**高级 (Architecture & Workflow)**
- [Netbox 数据填充：Terraform vs Ansible](./2025-12-04-netbox-population-terraform-vs-ansible.md) - 数据填充策略
- [混合 IaC 工作流：Terraform 与 Ansible 协同管理 Netbox](./2025-12-04-hybrid-iac-netbox-workflow.md) - 协同工作流

**相关正式指南**
- 📖 `guides/netbox_deployment_guide.md` - Netbox 部署指南

---

### 网络与连接

**Tailscale**
- [Tailscale 在 Proxmox LXC 与混合云环境中的深度集成](./2025-12-02-tailscale-integration-refactoring.md) - LXC 集成、混合云
- [Tailscale MagicDNS 与 Split DNS 原理](./2025-12-04-tailscale-magicdns-and-split-dns.md) - DNS 原理与配置
- [Caddy WebDAV 配置与 Tailscale ACL 故障排查](./2025-12-03-caddy-webdav-tailscale-troubleshooting.md) - ACL 与连接问题

**LXC 与 Proxmox**
- [LXC 与 VM 网络桥接拓扑学习笔记](./2025-11-30-lxc-vm-network-bridge.md) - 网络架构
- [Proxmox, Terraform & Ansible 集成笔记](./2025-12-02-proxmox-terraform-ansible-immich.md) - 集成问题

**DNS & 连接故障排查**
- [RustDesk 部署与 DNS 连接排查](./2026-01-29-rustdesk-deployment-lessons.md) - DNS Split-Horizon 问题

---

### 应用部署

**Homepage (Next.js 仪表板)**
- [Next.js 应用 LXC 部署中的内存需求与资源规划](./2025-12-01-homepage-lxc-deployment.md) - LXC 部署
- [Homepage Proxmox 集成配置指南](./2025-12-01-homepage-proxmox-integration.md) - Proxmox 集成

**n8n (工作流自动化)**
- [n8n Deployment on Proxmox LXC](./2025-12-15-deploying-n8n-on-lxc.md) - npm 方法部署

**Anki Sync Server**
- [Anki Sync Server Deployment - Learning Notes](./2025-11-30-anki-sync-server-deployment.md) - 部署与配置

**RustDesk (远程连接)**
- [Rustdesk 部署与 Terraform State 管理](./2026-01-28-rustdesk-terraform.md) - Terraform 集成
- [RustDesk 部署与 DNS 连接排查](./2026-01-29-rustdesk-deployment-lessons.md) - 故障排查

**Immich (相册管理)**
- [Ansible 部署验证模式与 Immich 模块化重构](./2025-11-30-ansible-deployment-verification.md) - 模块化部署
- [Proxmox, Terraform & Ansible 集成笔记](./2025-12-02-proxmox-terraform-ansible-immich.md) - 集成问题

---

### 存储与基础设施

**存储管理**
- [ZFS 存储池迁移、扩容与重命名实战笔记](./2025-12-04-zfs-pool-migration-and-expansion.md) - ZFS 操作

**ESXi 集成**
- [ESXi 集成与 Ansible 虚拟环境实践笔记](./2025-12-21-esxi-integration-and-venv.md) - ESXi 与 Ansible

---

### 其他专题

**日志与监控**
- [ELK 与 LPG 日志方案对比](./2025-12-11-elk-vs-lpg-comparison.md) - 日志栈对比

---

## 学习路径

### Terraform 学习路径

**初学者 (Beginner)**
1. 📖 `guides/terraform_proxmox_complete_guide.md` - 完整指南
2. [Terraform Learning Notes - Proxmox Deployment](./2025-11-28-terraform-proxmox.md) - 基础概念
3. [SSH Key 管理的混合策略](./2026-01-28-ssh-key-management-strategy.md) - 实践模式

**中级 (Intermediate)**
4. [Terraform Proxmox Disk & Cloud-Init 故障排查笔记](./2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md) - 常见问题
5. [Rustdesk 部署与 Terraform State 管理](./2026-01-28-rustdesk-terraform.md) - 状态管理
6. [混合 IaC 工作流：Terraform 与 Ansible 协同管理 Netbox](./2025-12-04-hybrid-iac-netbox-workflow.md) - 与 Ansible 协同

**高级 (Advanced)**
7. [Terraform 代码重构与状态对齐](./2025-11-30-terraform-refactoring-best-practices.md) - 重构最佳实践
8. [从静态 Inventory 迁移到动态 Inventory 的数据丢失陷阱](./2026-01-29-inventory-migration-trap.md) - 架构决策

---

### Ansible 学习路径

**初学者 (Beginner)**
1. [Ansible 部署 Netbox 与 Docker Compose 最佳实践](./2025-11-29-ansible-netbox-docker.md) - Roles 基础
2. [Ansible 部署验证模式与 Immich 模块化重构](./2025-11-30-ansible-deployment-verification.md) - 验证模式

**中级 (Intermediate)**
3. [Ansible Inventory 结构重构与最佳实践](./2025-12-02-ansible-inventory-refactoring.md) - Inventory 设计
4. [Ansible Vault Secret Management](./2025-12-02-ansible-vault-secret-management.md) - 密钥管理
5. [Ansible Tags 与变量作用域](./2025-12-04-ansible-tags-and-variables.md) - 高级用法

**高级 (Advanced)**
6. [Ansible Abstraction Levels: Module vs. Role vs. Task](./2025-12-03-ansible-abstraction-levels.md) - 架构设计
7. [Ansible 踩坑记录](./2026-01-29-ansible-troubleshooting.md) - 常见陷阱
8. [从静态 Inventory 迁移到动态 Inventory 的数据丢失陷阱](./2026-01-29-inventory-migration-trap.md) - 大型重构

---

### Netbox 集成路径

**初学者 (Beginner)**
1. 📖 `guides/netbox_deployment_guide.md` - 部署指南
2. [Netbox 4.1.11 部署：版本匹配与配置调试](./2025-11-29-netbox-deployment-version-troubleshooting.md) - 部署问题

**中级 (Intermediate)**
3. [LXC 与 VM 网络桥接拓扑学习笔记](./2025-11-30-lxc-vm-network-bridge.md) - 网络建模
4. [Ansible 部署 Netbox 与 Docker Compose 最佳实践](./2025-11-29-ansible-netbox-docker.md) - 部署自动化

**高级 (Advanced)**
5. [Netbox 数据填充：Terraform vs Ansible](./2025-12-04-netbox-population-terraform-vs-ansible.md) - 数据策略
6. [混合 IaC 工作流：Terraform 与 Ansible 协同管理 Netbox](./2025-12-04-hybrid-iac-netbox-workflow.md) - 协同工作流

---

## 文档关联

### 已提升到正式指南

这些学习笔记的内容已被提升到结构化的正式指南中：

| 学习笔记 | 相关正式指南 | 状态 |
|---------|------------|------|
| 2025-11-28-terraform-proxmox.md | `guides/terraform_proxmox_complete_guide.md` | Superseded |
| 2025-11-28-terraform-modules-netbox-debugging.md | `guides/terraform_proxmox_complete_guide.md` | Superseded |
| 2025-11-30-terraform-proxmox-provider-crash.md | `guides/terraform_proxmox_complete_guide.md` | Superseded |
| 2025-11-30-terraform-refactoring-best-practices.md | `guides/terraform_proxmox_complete_guide.md` | Superseded |
| 2025-11-29-netbox-deployment-version-troubleshooting.md | `guides/netbox_deployment_guide.md` | Superseded |

### 已提升到故障排查指南

这些笔记中的故障排查内容已被整合到 `troubleshooting/` 目录：

| 学习笔记 | 故障排查指南 |
|---------|------------|
| 2025-11-30-terraform-proxmox-provider-crash.md | `troubleshooting/terraform_provider_issues.md` |
| 2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md | `troubleshooting/terraform_cloud_init_disk.md` |
| 2025-12-02-tailscale-integration-refactoring.md | `troubleshooting/tailscale_lxc_issues.md` |
| 2025-12-03-caddy-webdav-tailscale-troubleshooting.md | `troubleshooting/caddy_tailscale_acl.md` |

### 活跃的学习记录

以下笔记仍然是独立的、有效的学习记录，未被更高级别的文档完全替代：

**Ansible 相关**
- ✓ 2026-01-29-ansible-troubleshooting.md - 实时故障排查
- ✓ 2026-01-29-inventory-migration-trap.md - 架构决策记录
- ✓ 2025-12-02-ansible-inventory-refactoring.md - 实践记录
- ✓ 2025-12-02-ansible-vault-secret-management.md - 安全实践
- ✓ 2025-12-03-ansible-abstraction-levels.md - 设计决策
- ✓ 2025-12-04-ansible-tags-and-variables.md - 高级用法

**Netbox 相关**
- ✓ 2025-12-04-netbox-population-terraform-vs-ansible.md - 比较分析
- ✓ 2025-12-04-hybrid-iac-netbox-workflow.md - 架构设计

**网络与连接**
- ✓ 2025-12-04-tailscale-magicdns-and-split-dns.md - 网络原理
- ✓ 2025-11-30-lxc-vm-network-bridge.md - 网络拓扑
- ✓ 2025-12-02-tailscale-integration-refactoring.md - 混合云集成
- ✓ 2026-01-29-rustdesk-deployment-lessons.md - 连接问题

**应用部署**
- ✓ 2025-12-01-homepage-lxc-deployment.md - LXC 资源规划
- ✓ 2025-12-01-homepage-proxmox-integration.md - Proxmox 集成
- ✓ 2025-11-30-ansible-deployment-verification.md - 验证模式
- ✓ 2025-11-30-anki-sync-server-deployment.md - Anki 部署
- ✓ 2025-12-15-deploying-n8n-on-lxc.md - n8n 部署
- ✓ 2026-01-28-rustdesk-terraform.md - RustDesk 集成

**基础设施**
- ✓ 2025-12-21-esxi-integration-and-venv.md - ESXi 集成
- ✓ 2025-12-04-zfs-pool-migration-and-expansion.md - ZFS 操作
- ✓ 2025-12-11-elk-vs-lpg-comparison.md - 架构对比

---

## 元数据统计

### 按状态分类

| 状态 | 数量 | 说明 |
|------|------|------|
| **Active** | 23 | 独立有效的学习记录 |
| **Superseded** | 5 | 已被正式指南替代，保留供参考 |
| **Archived** | 0 | 已过期，不再相关 |
| **总计** | 28 | (不含 INDEX.md) |

### 按标签统计

| 标签 | 数量 |
|------|------|
| Ansible | 10 |
| Terraform | 10 |
| Proxmox | 8 |
| Netbox | 6 |
| Troubleshooting | 7 |
| Deployment | 6 |
| Best Practices | 8 |
| Docker | 3 |
| Tailscale | 5 |
| LXC | 6 |
| Networking | 5 |
| DevOps | 8 |
| Cloud-Init | 3 |
| Storage | 2 |
| Monitoring | 1 |

### 按年份分类

| 年份 | 月份 | 数量 |
|------|------|------|
| 2026 | 01 | 5 |
| 2025 | 12 | 11 |
| 2025 | 11 | 12 |

---

## 使用建议

### 查找内容的方式

1. **按时间顺序**: 最近的问题和解决方案在页面顶部
2. **按主题**: 使用"按主题分类"快速定位相关领域
3. **按学习路径**: 按推荐的学习顺序查阅
4. **搜索**: 使用编辑器的查找功能搜索关键词

### 更新维护

- **学习笔记**: 记录实时的问题、解决方案和发现
- **定期审查**: 定期查看是否应将有价值的内容提升到正式指南
- **交叉引用**: 使用正式指南中的完整文档作为参考
- **标签同步**: 保持标签一致，便于分类和搜索

### 与正式文档的关系

```
Learning Notes (灵活、实时、讨论)
    ↓ (成熟、验证后)
Guides (结构化、规范、参考)
    ↓ (关键故障排查)
Troubleshooting (快速查询、最佳实践)
```

---

## 快速索引

### 最常访问的笔记

- 🔥 [Terraform Proxmox Disk & Cloud-Init 故障排查笔记](./2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md)
- 🔥 [Ansible 踩坑记录](./2026-01-29-ansible-troubleshooting.md)
- 🔥 [混合 IaC 工作流：Terraform 与 Ansible 协同管理 Netbox](./2025-12-04-hybrid-iac-netbox-workflow.md)
- 🔥 [Tailscale MagicDNS 与 Split DNS 原理](./2025-12-04-tailscale-magicdns-and-split-dns.md)

### 关键模式与最佳实践

- 🎯 [SSH Key 管理的混合策略](./2026-01-28-ssh-key-management-strategy.md) - Bootstrap Key Pattern
- 🎯 [Ansible Abstraction Levels](./2025-12-03-ansible-abstraction-levels.md) - Module vs Role 选择
- 🎯 [Ansible Inventory 结构重构与最佳实践](./2025-12-02-ansible-inventory-refactoring.md) - Inventory 组织
- 🎯 [Netbox 数据填充：Terraform vs Ansible](./2025-12-04-netbox-population-terraform-vs-ansible.md) - IaC 策略选择

---

**生成日期**: 2026-01-30
**维护者**: 基础设施团队
**反馈**: 如有问题或建议，请在相应笔记中添加备注或创建新的讨论文档
