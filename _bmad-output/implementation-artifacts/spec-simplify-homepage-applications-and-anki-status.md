---
title: '精简 Homepage 应用卡片并修正 Anki 状态'
type: 'bugfix'
created: '2026-08-13'
status: 'done'
route: 'one-shot'
---

# 精简 Homepage 应用卡片并修正 Anki 状态

## Intent

**Problem:** Homepage 和 Open WebUI 卡片不常用且使 Applications 出现高度不一致的第二行；Anki Sync 根路径正常返回 404/405，却被 HTTP 监控显示为故障。

**Approach:** 从 Applications 移除两个入口，并将 Anki Sync 状态改为明确标注的主机可达性探测，保留同步服务本身不变。

## Suggested Review Order

**应用卡片精简**

- Applications 仅保留四个常用入口，避免不必要的第二行。
  [`services.yaml.j2:38`](../../ansible/roles/homepage/templates/services.yaml.j2#L38)

**Anki 状态语义**

- 用主机可达性替代会产生正常 404 的 HTTP 根路径探测。
  [`services.yaml.j2:139`](../../ansible/roles/homepage/templates/services.yaml.j2#L139)
