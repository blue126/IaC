# Troubleshooting Index
此文档仅作为“问题索引”，具体问题的现象/原因/修复/预防请前往学习笔记查看对应段落。

## 索引
- Terraform Provider Panic (rc05) → `docs/learningnotes/INDEX.md`（关键词：Proxmox Provider 崩溃、rc05 回退）
- Permission Error `VM.Monitor` → `docs/learningnotes/INDEX.md`（关键词：PVE 8 权限模型、rc04 Token）
- Cloud-Init Disk Not Detected (UEFI/Q35) → `docs/learningnotes/INDEX.md`（关键词：ide2→scsi1 映射）
- Duplicate Resource (NetBox TF Split) → `docs/learningnotes/INDEX.md`（关键词：文件分层、删除旧 resources.tf）
- NetBox `DATABASE` Missing → `docs/learningnotes/INDEX.md`（关键词：netbox-docker 版本矩阵、v3.0.2）
- Postgres Upgrade Conflict → `docs/learningnotes/INDEX.md`（关键词：pg_upgrade、compose 升级策略）
- NetBox User Not Found → `docs/learningnotes/INDEX.md`（关键词：容器 user 映射、unit:root）
- Port Not Exposed (NetBox) → `docs/learningnotes/INDEX.md`（关键词：端口发布、override 说明）
- Unused Disk / Boot Fail → `docs/learningnotes/INDEX.md`（关键词：模板磁盘尺寸、不可缩小）
- Network Fails (Machine ID) → `docs/learningnotes/INDEX.md`（关键词：/etc/machine-id 冲突）
- Hostname / SSH Key Not Applied → `docs/learningnotes/INDEX.md`（关键词：cicustom 覆盖、原生 Cloud-Init 变量）
- Slow Immich Startup → `docs/learningnotes/INDEX.md`（关键词：ML 拉取/初始化、超时策略）
- Verification Port Timeout → `docs/learningnotes/INDEX.md`（关键词：分层就绪检查）
- Redis Queue Backlog → `docs/learningnotes/INDEX.md`（关键词：队列深度监控、扩容）
- Drift After Spec Change → `docs/learningnotes/INDEX.md`（关键词：NetBox 同步、apply 习惯）
- Cable Missing in Topology → `docs/learningnotes/INDEX.md`（关键词：cable 建模、termination 类型）
- EFI Disk Absent → `docs/learningnotes/INDEX.md`（关键词：efidisk 渲染、存储变量）
- Samba Var Naming Inconsistency → `docs/learningnotes/INDEX.md`（关键词：命名规范、前缀策略）
- Terraform Duplicate Resource Panic → `docs/learningnotes/INDEX.md`（关键词：重复资源检测、迁移清单）
- Slow WiFi SMB Access → `docs/learningnotes/INDEX.md`（关键词：WiFi 调优、SMB3）

## 说明
- 学习笔记采用按日归档与索引页汇总，以上条目均可通过索引页关键词快速定位。
- 若索引页尚未包含某条目，请将问题记录到学习笔记后在本索引追加一行关键词。
