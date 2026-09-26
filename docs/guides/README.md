# Guides 索引

本目录集中存放所有"怎么做"类操作文档，涵盖部署、配置、迁移与最佳实践。

## 部署指南（Deployment）

- **[netbox-deployment.md](./netbox-deployment.md)** — NetBox 应用容器化部署 + Terraform Provider 资源初始化与常见问题。
- **[proxmox-vm-deployment.md](./proxmox-vm-deployment.md)** — 通过 Terraform 管理 Proxmox VM 规格、Cloud-Init、最佳实践与变量示例。
- **[immich-deployment.md](./immich-deployment.md)** — 照片/视频管理栈部署（Postgres/Redis/ML）、验证模式、性能与扩展建议。
- **[immich-upgrade-mop.md](./immich-upgrade-mop.md)** — 面向 agent 的 Homelab 六步升级流程，包含整机备份、基本验证和恢复边界。
- **[n8n-upgrade-mop.md](./n8n-upgrade-mop.md)** — 面向 npm + systemd LXC 部署的六步升级流程，包含 workflow 保持未发布、SQLite 异常排障和恢复边界。

## 实操指南（How-to）

- **[terraform-proxmox-complete-guide.md](./terraform-proxmox-complete-guide.md)** — Terraform + Proxmox 综合指南（2022 行，含 40+ 常见问题）。
- **[ansible-patterns-and-best-practices.md](./ansible-patterns-and-best-practices.md)** — Ansible 模式与最佳实践。
- **[QUICK-REFERENCE.md](./QUICK-REFERENCE.md)** — Terraform 与 Proxmox 常用命令速查卡。
- **[proxmox-provider-migration-guide.md](./proxmox-provider-migration-guide.md)** — 从 telmate 迁移到 bpg Proxmox Terraform provider 实战指南。
- **[jenkins-webhook-router-setup.md](./jenkins-webhook-router-setup.md)** — Jenkins Webhook-Router 手工配置指南。
- **[notion-sync-setup.md](./notion-sync-setup.md)** — 将 Terraform state 同步到 Notion 的配置指南。
- **[cn-exit-singbox-proxy.md](./cn-exit-singbox-proxy.md)** — sing-box 出境代理配置说明。

## 结构约定

- 部署类文档标题统一使用英文名称 + "Deployment" 或角色描述。
- 包含标准段落：概述 / 基础设施 / 部署流程 / 验证 / 常见问题 / 扩展 / 关键命令。
- 敏感变量（密码/API Token）在示例中标记为占位符，不直接暴露真实值。

## 使用建议

1. 更新规格后：先改 Terraform → `plan` → `apply` → 根据需要调整部署文档。
2. 新增服务：先在此目录创建初稿，再补充验证与故障条目。
3. 故障条目沉淀：若具有共性，抽取到 `../troubleshooting/`。
4. 与 NetBox 拓扑关联：确保新增服务端口与 VM 在 `terraform/netbox-integration` 中建模并同步。

## 后续可扩展

- 增加统一的变量命名清单文档。
- 添加 GPU / 存储扩展专门指南。
- 引入部署基准测试（启动耗时、资源占用曲线）。

---
如需新增指南，请遵循以上结构并补充必要资源与验证步骤。
