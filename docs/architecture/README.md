# Architecture 索引

架构设计、规范与决策记录（合并自原 `designs/` 与 `specs/`）。

## 设计文档

- **[homelab-iac-architecture.md](./homelab-iac-architecture.md)** — 系统总体架构（Terraform + Ansible + Proxmox/OCI/Netbox）。
- **[proxmox-qdevice-architecture.md](./proxmox-qdevice-architecture.md)** — 双节点集群与 N100 外部见证：1/1 + 1 投票、权限、启动门控、验证与回滚。
- **[hindsight-memory-architecture.md](./hindsight-memory-architecture.md)** — pve1 LXC 118 上的 Hindsight 共享记忆服务：拓扑、Codex 登录、端口与认证（含无登录的网页控制台）、资源与重排性能、逻辑导出方法、网络依赖与已知事故、网关旧部署的经验教训与未完成项。
- **[cicd-architecture.md](./cicd-architecture.md)** — Jenkins CI/CD 流水线架构。
- **[ansible-vault-architecture.md](./ansible-vault-architecture.md)** — Ansible Vault 密钥管理设计。
- **[ansible-role-architecture.md](./ansible-role-architecture.md)** — Ansible Role 架构、边界与依赖。
- **[docker-sandbox-agent-architecture.md](./docker-sandbox-agent-architecture.md)** — Docker Sandbox Agent 架构。
- **[docker-sandbox-migration.md](./docker-sandbox-migration.md)** — Docker Sandbox 迁移记录。
- **[ci-only-execution-architecture.md](./ci-only-execution-architecture.md)** — CI-only 执行架构。
- **[anki-desktop-role.md](./anki-desktop-role.md)** — Anki Desktop Role 设计。
- **[gitea-role.md](./gitea-role.md)** — Gitea Role 设计。

## 规范与决策记录

- **[deferred-work-sync.md](./deferred-work-sync.md)** — BMAD 延期工作清单与 GitHub Issues 的同步机制。
- **[doc-monitoring-scope.md](./doc-monitoring-scope.md)** — 文档 AI 监管范围：说明与决策记录（监管哪些目录、为什么、当前缺口）。
- **[backup-architecture-consolidation-spec.md](./backup-architecture-consolidation-spec.md)** — 备份架构整合规范（含关键决策记录，取代 archive 下 PBS iSCSI/Veeam 文档）。
- **[proxmox-storage-monitoring-spec.md](./proxmox-storage-monitoring-spec.md)** — 集群 SMART/ZFS scrub/Prometheus/Grafana 存储监控规范。

## 图

- **[cicd-pipeline-flowchart.excalidraw](./cicd-pipeline-flowchart.excalidraw)** — CI/CD 流程图。
