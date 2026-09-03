---
title: '使用无密钥探测监控 Tailscale'
type: 'chore'
created: '2026-08-13'
status: 'done'
route: 'one-shot'
---

# 使用无密钥探测监控 Tailscale

## Intent

**Problem:** Homepage 的 Tailscale widget 依赖最长 90 天有效的 API access token，过期后卡片失效并需要人工轮换。

**Approach:** 移除控制面 API widget，改用本机 Quad100 metrics HTTP 探测和 OCI Tailnet IP 的 ICMP 探测，分别反映本机 Tailscale 接口与远端节点可达性。

## Suggested Review Order

**无密钥健康信号**

- 确认 Tailscale 卡片不再引用 API key，并同时配置本机 metrics 与 OCI 可达性探测。
  [`services.yaml.j2:117`](../../ansible/roles/homepage/templates/services.yaml.j2#L117)
