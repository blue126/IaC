# Architecture 索引

架构设计、规范与决策记录（合并自原 `designs/` 与 `specs/`）。

## 设计文档

- **[homelab-iac-architecture.md](./homelab-iac-architecture.md)** — 系统总体架构（Terraform + Ansible + Proxmox/OCI/Netbox）。
- **[cicd-architecture.md](./cicd-architecture.md)** — Jenkins CI/CD 流水线架构。
- **[ansible-vault-architecture.md](./ansible-vault-architecture.md)** — Ansible Vault 密钥管理设计。
- **[ansible-role-architecture.md](./ansible-role-architecture.md)** — Ansible Role 架构、边界与依赖。
- **[docker-sandbox-agent-architecture.md](./docker-sandbox-agent-architecture.md)** — Docker Sandbox Agent 架构。
- **[docker-sandbox-migration.md](./docker-sandbox-migration.md)** — Docker Sandbox 迁移记录。
- **[ci-only-execution-architecture.md](./ci-only-execution-architecture.md)** — CI-only 执行架构。
- **[anki-desktop-role.md](./anki-desktop-role.md)** — Anki Desktop Role 设计。
- **[gitea-role.md](./gitea-role.md)** — Gitea Role 设计。

## 规范与决策记录

- **[doc-monitoring-scope.md](./doc-monitoring-scope.md)** — 文档 AI 监管范围：说明与决策记录（监管哪些目录、为什么、当前缺口）。
- **[backup-architecture-consolidation-spec.md](./backup-architecture-consolidation-spec.md)** — 备份架构整合规范（含关键决策记录，取代 archive 下 PBS iSCSI/Veeam 文档）。
- **[proxmox-storage-monitoring-spec.md](./proxmox-storage-monitoring-spec.md)** — 集群 SMART/ZFS scrub/Prometheus/Grafana 存储监控规范。

## 图

- **[cicd-pipeline-flowchart.excalidraw](./cicd-pipeline-flowchart.excalidraw)** — CI/CD 流程图。
