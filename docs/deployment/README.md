# 部署指南索引

集中存放所有服务与平台的部署文档，统一结构便于检索与扩展。

## 列表

- **NetBox Deployment** (`netbox-deployment.md`): NetBox 应用容器化部署 + Terraform Provider 资源初始化与常见问题。
- **Proxmox VM Provisioning** (`proxmox-vm-deployment.md`): 通过 Terraform 管理 Proxmox VM 规格、Cloud-Init、最佳实践与变量示例。
- **Samba File Server** (`SAMBA_VM_DEPLOYMENT.md`): 匿名共享服务器自动化创建、权限设计、故障排查与变量规范化经验。
- **Immich Deployment** (`immich-deployment.md`): 照片/视频管理栈部署（Postgres/Redis/ML）、验证模式、性能与扩展建议。
- **Tailscale Deployment** (`TAILSCALE_DEPLOYMENT.md`): 跨平台 VPN 组网部署，包含 Proxmox 宿主机、LXC 容器（Passthrough/DNS修复）及 OCI 实例的统一管理。

## 结构约定
- 标题统一使用英文名称 + "Deployment" 或角色描述。
- 包含以下标准段落：概述 / 基础设施 / 部署流程 / 验证 / 常见问题 / 扩展 / 关键命令。
- 敏感变量（密码/API Token）在示例中标记为占位符，不直接暴露真实值。

## 使用建议
1. 更新规格后：先改 Terraform → `plan` → `apply` → 根据需要调整部署文档。
2. 新增服务：先在此目录创建初稿，再补充验证与故障条目。
3. 故障条目沉淀：若具有共性，抽取到 `docs/troubleshooting-issues.md`。
4. 与 NetBox 拓扑关联：确保新增服务端口与 VM 在 `terraform/netbox-integration` 中建模并同步。

## 后续可扩展
- 增加统一的变量命名清单文档。
- 添加 GPU / 存储扩展专门指南。
- 引入部署基准测试（启动耗时、资源占用曲线）。

---
如需新增指南，请遵循以上结构并补充必要资源与验证步骤。