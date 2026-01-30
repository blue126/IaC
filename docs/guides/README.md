# Terraform + Proxmox 文档库

本目录包含关于使用 Terraform 与 Proxmox 虚拟化平台集成的完整文档。

## 文档概览

### 主指南
- **terraform_proxmox_complete_guide.md** (2022 行)
  - 综合指南，集合 5 个学习笔记的核心内容
  - 涵盖从基础配置到生产级最佳实践
  - 包含 40+ 个常见问题与解决方案

## 源学习笔记

本指南基于以下学习笔记编译整合：

1. **2025-11-28-terraform-proxmox.md**
   - 核心概念定义（Provider、Resource、State、Module 等）
   - Terraform 文件结构（main.tf、variables.tf 等）
   - 第一阶段故障排查与解决方案
   - 包含权限、存储、Cloud-Init、Agent 问题

2. **2025-11-28-terraform-modules-netbox-debugging.md**
   - 模块化重构实践
   - Netbox 作为 IPAM 数据源的集成
   - Cloud-Init 深度调试
   - UEFI/Q35 架构兼容性问题
   - Hostname 与 SSH Key 注入最佳实践

3. **2025-11-30-terraform-refactoring-best-practices.md**
   - Root Module vs Child Module 概念
   - Terraform Import 机制
   - Configuration Drift 检测与解决
   - Lifecycle Ignore Changes 使用
   - 状态对齐与资源重构

4. **2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md**
   - 磁盘缩容问题深度分析（致命问题）
   - Cloud-Init 与 QGA 依赖链关系
   - Docker Restart Policy 与 Ansible 幂等性
   - Terraform Lifecycle 与启动顺序
   - 脚本单位换算陷阱（MB vs GB）
   - VMID 稳定性与重建循环
   - 配置漂移处理（Day 2 Ops）

5. **2026-01-28-ssh-key-management-strategy.md**
   - SSH 密钥管理的矛盾与解决方案
   - Bootstrap Key 模式
   - Terraform 与 Ansible 的职能分离
   - 用户访问权限的日常维护

## 快速导航

### 按使用场景

**刚开始接触 Terraform + Proxmox**
- 阅读：简介与架构概览 → 核心概念基础 → 基础配置与初始化

**需要搭建可复用的基础设施代码**
- 阅读：模块化设计最佳实践 → Terraform 项目结构

**遇到虚拟机部署问题**
- 参考：常见问题与故障排查（按问题类型查找）

**需要管理多个用户的 SSH 访问**
- 阅读：SSH 密钥管理策略

**生产环境部署前检查**
- 查看：总结与建议 → 生产环境检查清单

### 按技术主题

| 主题 | 相关章节 |
|------|---------|
| Cloud-Init | 6. Cloud-Init 与虚拟机初始化 |
| 磁盘管理 | 7.1 磁盘相关问题 |
| 状态管理 | 7. 状态管理与配置漂移 |
| QEMU Agent | 7.3 QEMU Guest Agent 问题 |
| UEFI/Q35 | 7.4 UEFI/Q35 兼容性问题 |
| SSH 密钥 | 8. SSH 密钥管理策略 |
| 故障排查 | 8. 常见问题与故障排查 |
| 命令参考 | 9. 参考资源与命令速查 |

### 命令速查

快速查找常用命令的位置：
- **terraform 命令**: 9.1 常用 Terraform 命令
- **proxmox API 命令**: 9.2 Proxmox API 命令参考
- **错误消息**: 9.4 常见错误消息解释

## 核心知识点提炼

### "三大陷阱"（必读）

1. **磁盘缩容陷阱** (来源：2025-12-04)
   - Proxmox 不支持磁盘缩容
   - 错误的大小约束会导致 "Detach & Create" 操作
   - 结果：新磁盘为空，VM 无法启动
   - 防御：在脚本中验证 `disk_size >= template_size`

2. **Output 穿透陷阱** (来源：2025-11-28, 2025-11-30)
   - 模块内定义的 Output 不会自动对外暴露
   - 必须在 Root Module 中再次定义才能使用
   - 解决：显式声明 Output 接口

3. **SSH Key 维护陷阱** (来源：2026-01-28)
   - 频繁修改 Terraform 中的 sshkeys 会触发 VM 重建
   - 解决：使用 Bootstrap Key 模式，日常维护交由 Ansible

### "五个核心命令"

```bash
terraform init       # 初始化环境
terraform plan       # 查看执行计划（最重要！）
terraform apply      # 应用配置
terraform state      # 管理状态
terraform destroy    # 销毁资源
```

### "七个最佳实践"

1. 显式定义所有参数（不依赖默认值）
2. 使用远程状态后端（团队协作）
3. 模块化优先（可复用）
4. 严格的状态漂移检测
5. 使用 lifecycle 块精细控制
6. SSH 密钥与配置管理分离
7. 充分的脚本验证与单位转换

## 文档使用建议

1. **第一次阅读**：按顺序从头到尾，建立整体认知
2. **日常参考**：根据需要跳转到相关章节快速查询
3. **问题排查**：使用目录或搜索快速定位症状对应的解决方案
4. **最佳实践学习**：重点阅读"最佳实践"和"常见问题"章节

## 关键资源链接

- [Terraform 官方文档](https://www.terraform.io/docs)
- [Proxmox Provider 文档](https://registry.terraform.io/providers/telmate/proxmox)
- [Proxmox VE 官方文档](https://pve.proxmox.com/pve-docs/)
- [Cloud-Init 官方文档](https://cloud-init.io/documentation/)

## 文档信息

- **编译时间**: 2026-01-30
- **基础版本**: Terraform 0.12+, Proxmox 8.x, telmate/proxmox 3.0+
- **行数**: 2022 行（包含代码示例、表格、详细说明）
- **覆盖范围**: 基础配置、模块化设计、故障排查、生产最佳实践

---

**如有更新建议，欢迎反馈！**
