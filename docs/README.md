# Directory Index

Homelab IaC 文档导航中心。文档按**类型/生命周期**组织：架构设计、操作指南、排障、学习笔记、规划、Agent 工作流、静态参考与归档。

> 发布站点由 [`docs-site/`](../docs-site/README.md) 从本目录自动生成，目录结构即站点导航。

## 顶层结构

| 目录 | 内容 | 说明 |
|---|---|---|
| [`architecture/`](#architecture) | 架构设计与规范 | designs + specs 合并 |
| [`guides/`](#guides) | 部署与实操指南 | deployment + guides 合并 |
| [`troubleshooting/`](#troubleshooting) | 排障与事故复盘 | troubleshooting + incidents 合并 |
| [`learningnotes/`](#learningnotes) | 学习笔记（按日期） | — |
| [`planning/`](#planning) | 路线图、提案与已实现 | improvement 更名 |
| [`agent/`](#agent) | BMAD/Multica/OpenCode 工作流 | 顶层散落归位 |
| [`reference/`](#reference) | 静态参考数据 | — |
| [`archive/`](#archive) | 已退役文档 | — |

---

## architecture/

架构设计、规范与决策记录。

- **[homelab-iac-architecture.md](./architecture/homelab-iac-architecture.md)** — 系统总体架构（Terraform + Ansible + Proxmox/OCI/Netbox）。
- **[backup-architecture-consolidation-spec.md](./architecture/backup-architecture-consolidation-spec.md)** — 备份架构整合规范（含关键决策记录，取代 archive 下 PBS iSCSI/Veeam 文档）。
- **[cicd-architecture.md](./architecture/cicd-architecture.md)** — Jenkins CI/CD 流水线架构。
- **[ansible-vault-architecture.md](./architecture/ansible-vault-architecture.md)** — Ansible Vault 密钥管理设计。
- **[ansible-role-architecture.md](./architecture/ansible-role-architecture.md)** — Ansible Role 架构、边界与依赖。
- **[docker-sandbox-agent-architecture.md](./architecture/docker-sandbox-agent-architecture.md)** — Docker Sandbox Agent 架构。
- **[docker-sandbox-migration.md](./architecture/docker-sandbox-migration.md)** — Docker Sandbox 迁移记录（原 `2026-08-28-*`）。
- **[ci-only-execution-architecture.md](./architecture/ci-only-execution-architecture.md)** — CI-only 执行架构（原 `2026-08-30-*`）。
- **[proxmox-storage-monitoring-spec.md](./architecture/proxmox-storage-monitoring-spec.md)** — 集群 SMART/ZFS scrub/Prometheus/Grafana 存储监控规范。
- **[anki-desktop-role.md](./architecture/anki-desktop-role.md)** — Anki Desktop Role 设计。
- **[gitea-role.md](./architecture/gitea-role.md)** — Gitea Role 设计。
- **[cicd-pipeline-flowchart.excalidraw](./architecture/cicd-pipeline-flowchart.excalidraw)** — CI/CD 流程图（Excalidraw）。

## guides/

部署与实操指南。

- **[netbox-deployment.md](./guides/netbox-deployment.md)** — NetBox 容器化部署 + Terraform Provider 初始化。
- **[proxmox-vm-deployment.md](./guides/proxmox-vm-deployment.md)** — 用 Terraform 管理 Proxmox VM。
- **[immich-deployment.md](./guides/immich-deployment.md)** — Immich 照片栈部署（Postgres/Redis/ML）。
- **[immich-upgrade-mop.md](./guides/immich-upgrade-mop.md)** — Immich 六步升级流程（agent 向）。
- **[n8n-upgrade-mop.md](./guides/n8n-upgrade-mop.md)** — n8n 六步升级流程。
- **[terraform-proxmox-complete-guide.md](./guides/terraform-proxmox-complete-guide.md)** — Terraform + Proxmox 综合指南。
- **[ansible-patterns-and-best-practices.md](./guides/ansible-patterns-and-best-practices.md)** — Ansible 模式与最佳实践。
- **[QUICK-REFERENCE.md](./guides/QUICK-REFERENCE.md)** — Terraform/Proxmox 命令速查卡。
- **[proxmox-provider-migration-guide.md](./guides/proxmox-provider-migration-guide.md)** — telmate → bpg provider 迁移实战。
- **[jenkins-webhook-router-setup.md](./guides/jenkins-webhook-router-setup.md)** — Jenkins Webhook-Router 配置。
- **[notion-sync-setup.md](./guides/notion-sync-setup.md)** — Terraform state 同步到 Notion。
- **[cn-exit-singbox-proxy.md](./guides/cn-exit-singbox-proxy.md)** — sing-box 出境代理配置。

## troubleshooting/

排障指南与事故复盘。

- **[README.md](./troubleshooting/README.md)** — 排障文档索引。
- **[STRUCTURE.md](./troubleshooting/STRUCTURE.md)** — 排障文档结构定义。
- **[ansible-issues.md](./troubleshooting/ansible-issues.md)** — Ansible 常见问题。
- **[terraform-issues.md](./troubleshooting/terraform-issues.md)** — Terraform/Proxmox 问题。
- **[deployment-issues.md](./troubleshooting/deployment-issues.md)** — 通用部署问题（Docker 等）。
- **[network-connectivity.md](./troubleshooting/network-connectivity.md)** — 网络/ VPN / 代理问题。
- **[slow-smb-over-wifi.md](./troubleshooting/slow-smb-over-wifi.md)** — SMB 传输缓慢排查。
- **[2026-08-05-backup-outage.md](./troubleshooting/2026-08-05-backup-outage.md)** — 事故复盘：备份静默失败六个月。
- **[2026-04-12-pve0-nvme-controller-hang.md](./troubleshooting/2026-04-12-pve0-nvme-controller-hang.md)** — 事故复盘：pve0 NVMe 控制器挂起。

## learningnotes/

按日期记录的学习笔记。完整索引见 **[learningnotes/INDEX.md](./learningnotes/INDEX.md)**。

- 覆盖：Terraform、Ansible、Proxmox、Netbox、Tailscale、LXC、n8n、Immich、RustDesk、Jenkins、ESXi/PBS 迁移等。
- 子目录 `refactoring/` 存放重构专题笔记。

## planning/

路线图、改进提案与已实现记录。

- **[PLANNING.md](./planning/PLANNING.md)** — 项目路线图与阶段规划。
- **[inventory-and-document-sync-via-cicd.md](./planning/inventory-and-document-sync-via-cicd.md)** — 变更驱动文档同步提案。
- **implemented/** — 已实现的改进记录：
  - **[cloudflare-tunnel-webhook.md](./planning/implemented/cloudflare-tunnel-webhook.md)** — Cloudflare Tunnel Webhook 触发实现。
  - **[proxmox-provider-migration.md](./planning/implemented/proxmox-provider-migration.md)** — Proxmox provider 迁移记录。

## agent/

Agent 工作流契约与集成（BMAD / Multica / OpenCode）。

- **[bmad-multica-contract.md](./agent/bmad-multica-contract.md)** — BMAD × Multica 执行合同。
- **[multica-team.md](./agent/multica-team.md)** — Multica：BMAD Team 配置。
- **[bmad-review-routing.md](./agent/bmad-review-routing.md)** — 选择性跨模型审核路由。
- **[bmad-cross-model-review.md](./agent/bmad-cross-model-review.md)** — BMAD 跨模型审核：PAL 调用层。
- **[bmad-opencode-subagent-integration.md](./agent/bmad-opencode-subagent-integration.md)** — BMAD + OpenCode 双层 Agent 架构集成。

## reference/

静态参考数据。

- **[netbox-custom-fields-reference.md](./reference/netbox-custom-fields-reference.md)** — NetBox Custom Fields 定义参考（Epic 1）。

## archive/

已退役或仅历史参考的文档。

- **[pbs-esxi-deployment.md](./archive/pbs-esxi-deployment.md)** — 已退役的 ESXi/PBS 历史部署记录（不适用于当前 pve2）。
- **[pbs-iscsi-veeam-spec.md](./archive/pbs-iscsi-veeam-spec.md)** — 已归档 PBS iSCSI/Veeam 实施规范。
- **[pbs-iscsi-veeam-guide.md](./archive/pbs-iscsi-veeam-guide.md)** — 已归档 PBS iSCSI/Veeam 架构指南。
- **[veeam-backup-deployment-guide.md](./archive/veeam-backup-deployment-guide.md)** — 已归档 Veeam 部署指南。

---

## 维护约定

- 新增文档请放入对应分类目录，并同步更新本索引。
- 学习笔记命名 `YYYY-MM-DD-topic.md`，见 [learningnotes/INDEX.md](./learningnotes/INDEX.md)。
- 退役文档移入 `archive/`。
