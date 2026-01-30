# IaC 项目文档中心

欢迎来到基础设施即代码（Infrastructure as Code）项目的文档中心。本文档库包含完整的部署指南、学习笔记、故障排查和最佳实践。

---

## 📚 文档导航

### 🎯 快速开始

**新手推荐路径**：
1. 📖 阅读 [项目规划](PLANNING.md) 了解整体架构
2. 🔧 浏览 [部署指南](#-部署指南) 快速上手
3. 📝 查看 [学习笔记](#-学习笔记) 深入理解
4. 🔍 遇到问题？访问 [故障排查](#-故障排查)

---

## 📂 文档分类

### 🚀 部署指南

**位置**: `deployment/`

生产级部署文档，提供详细的步骤说明和配置示例。

| 服务 | 文档 | 说明 |
|------|------|------|
| **Netbox** | [netbox_deployment.md](deployment/netbox_deployment.md) | 网络资源管理系统部署 |
| **Proxmox VM** | [proxmox_vm_deployment.md](deployment/proxmox_vm_deployment.md) | Terraform VM 模块化部署 |
| **Immich** | [immich_deployment.md](deployment/immich_deployment.md) | 照片管理与 ML 分析服务 |
| **PBS + ESXi** | [pbs_esxi_deployment.md](deployment/pbs_esxi_deployment.md) | Proxmox Backup Server 集成 |
| **Caddy** | [caddy_deployment.md](deployment/caddy_deployment.md) | Web 服务器与反向代理 |
| **Tailscale** | [tailscale_deployment.md](deployment/tailscale_deployment.md) | VPN 零配置网络 |
| **Homepage Dashboard** | [homepage_dashboard_deployment.md](deployment/homepage_dashboard_deployment.md) | 服务监控仪表板 |
| **N8N** | [n8n_deployment.md](deployment/n8n_deployment.md) | 工作流自动化平台 |

**查看更多**: [deployment/README.md](deployment/README.md)

---

### 📘 综合指南

**位置**: `guides/`

从学习笔记中提炼的系统性知识，深入讲解核心技术栈。

| 指南 | 文档 | 说明 |
|------|------|------|
| **Terraform + Proxmox** | [terraform_proxmox_complete_guide.md](guides/terraform_proxmox_complete_guide.md) | 完整的 Terraform 实践指南（2000+行） |
| **Ansible 最佳实践** | ⏳ 计划中 | Ansible 模式与实践（待创建） |
| **Netbox 集成** | ⏳ 计划中 | Netbox 与 IaC 工具集成（待创建） |
| **LXC/VM 网络** | ⏳ 计划中 | 容器与虚拟机网络配置（待创建） |

**查看更多**: [guides/README.md](guides/README.md)

---

### 🔧 故障排查

**位置**: `troubleshooting/`

按问题类型分类的故障诊断和解决方案集合。

| 类别 | 文档 | 覆盖问题 |
|------|------|---------|
| **Terraform 问题** | [terraform_issues.md](troubleshooting/terraform_issues.md) | Provider崩溃、磁盘配置、Cloud-Init等（8个问题） |
| **Ansible 问题** | [ansible_issues.md](troubleshooting/ansible_issues.md) | Callback错误、Inventory陷阱、幂等性等（6个问题） |
| **网络连接** | [network_connectivity.md](troubleshooting/network_connectivity.md) | SMB慢速、DNS冲突、路由问题等（5个问题） |
| **部署问题** | [deployment_issues.md](troubleshooting/deployment_issues.md) | 版本兼容、超时、架构误解等（4个问题） |

**快速诊断**: [troubleshooting/README.md](troubleshooting/README.md)

---

### 📝 学习笔记

**位置**: `learningnotes/`

按时间顺序记录的学习日志（2025年11月至今，共31篇），包含探索过程、踩坑经历和经验总结。

**主题分类**：
- **Terraform** (10篇) - 从初学到模块化重构
- **Ansible** (10篇) - 从基础到高级模式
- **Netbox** (6篇) - 部署、集成、数据管理
- **网络** (8篇) - Tailscale、LXC、DNS
- **应用部署** (10篇) - Homepage、n8n、RustDesk等

**完整索引**: [learningnotes/INDEX.md](learningnotes/INDEX.md)

**学习路径推荐**：
1. **Terraform 路径**: 初学 → 模块化 → 最佳实践 → 故障排查 → SSH密钥策略
2. **Ansible 路径**: 基础 → Inventory → Vault → 抽象层次 → 验证模式
3. **Netbox 路径**: 部署 → Docker集成 → 数据填充 → 混合工作流

---

### 📋 其他文档

| 文档 | 说明 |
|------|------|
| [PLANNING.md](PLANNING.md) | 项目整体规划和架构目标 |
| [infrastructure_notes.md](infrastructure_notes.md) | 网络拓扑和基础设施笔记 |
| [concepts_qna.md](concepts_qna.md) | 核心概念问答 |
| [troubleshooting_issues.md](troubleshooting_issues.md) | 常见问题汇总 |
| [slow_smb_over_wifi.md](slow_smb_over_wifi.md) | SMB性能问题案例研究 |

---

## 🗂️ 文档类型说明

| 类型 | 用途 | 特点 | 何时使用 |
|------|------|------|---------|
| **部署指南** | 生产级部署 | 详细步骤、可复现 | 需要部署新服务时 |
| **综合指南** | 系统性学习 | 深度讲解、最佳实践 | 想深入理解技术栈时 |
| **故障排查** | 问题诊断 | 症状→原因→方案 | 遇到具体问题时 |
| **学习笔记** | 探索记录 | 时间序列、真实过程 | 想了解思考过程时 |

---

## 🔍 如何查找文档？

### 按场景查找

| 场景 | 推荐文档 |
|------|---------|
| 🆕 我是新手，想了解项目 | [PLANNING.md](PLANNING.md) → [guides/](guides/) |
| 🚀 我要部署一个服务 | [deployment/README.md](deployment/README.md) |
| ❓ 我遇到了问题 | [troubleshooting/README.md](troubleshooting/README.md) |
| 📖 我想系统学习 Terraform | [guides/terraform_proxmox_complete_guide.md](guides/terraform_proxmox_complete_guide.md) |
| 🔗 我想了解 Netbox 集成 | [learningnotes/INDEX.md](learningnotes/INDEX.md) → Netbox 分类 |
| 🌐 我在配置网络 | [troubleshooting/network_connectivity.md](troubleshooting/network_connectivity.md) |

### 按技术栈查找

| 技术 | 相关文档 |
|------|---------|
| **Terraform** | [guides/terraform_proxmox_complete_guide.md](guides/terraform_proxmox_complete_guide.md) + [troubleshooting/terraform_issues.md](troubleshooting/terraform_issues.md) |
| **Ansible** | [troubleshooting/ansible_issues.md](troubleshooting/ansible_issues.md) + learningnotes Ansible系列 |
| **Netbox** | [deployment/netbox_deployment.md](deployment/netbox_deployment.md) + learningnotes Netbox系列 |
| **Proxmox** | [deployment/proxmox_vm_deployment.md](deployment/proxmox_vm_deployment.md) |
| **Docker** | deployment/ 中的各个服务部署文档 |
| **Tailscale** | [deployment/tailscale_deployment.md](deployment/tailscale_deployment.md) |

---

## 📊 项目统计

- **文档总数**: 40+ 篇
- **部署指南**: 11 篇
- **综合指南**: 1 篇（更多计划中）
- **故障排查**: 4 大类，23 个问题
- **学习笔记**: 31 篇
- **覆盖技术**: Terraform, Ansible, Proxmox, Docker, Netbox, Tailscale...

---

## 🔄 文档维护

### 最近更新
- ✅ 2026-01-30: 重组文档结构，新增 guides/ 和 troubleshooting/ 目录
- ✅ 2026-01-30: 创建 Terraform 综合指南（2000+行）
- ✅ 2026-01-30: 增强 learningnotes/INDEX.md
- ✅ 2026-01-30: 统一文件命名为小写+下划线风格

### 文档关联关系
- **learningnotes** → 提炼为 → **guides**（系统性知识）
- **learningnotes** → 提炼为 → **troubleshooting**（问题解决方案）
- **guides** + **troubleshooting** → 支持 → **deployment**（部署实践）

---

## 🎯 下一步计划

- [ ] 创建 Ansible 最佳实践综合指南
- [ ] 创建 Netbox 集成综合指南
- [ ] 创建 LXC/VM 网络配置指南
- [ ] 添加快速参考卡片（quick_reference/）
- [ ] 建立文档搜索功能

---

## 📞 帮助与反馈

遇到问题？
1. 先查看 [troubleshooting/README.md](troubleshooting/README.md)
2. 搜索 [learningnotes/INDEX.md](learningnotes/INDEX.md) 中的相关主题
3. 查看对应的部署指南或综合指南

建议改进？欢迎提交反馈！

---

**最后更新**: 2026-01-30
**文档版本**: v2.0（重组版）
