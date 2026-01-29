# 学习笔记：RustDesk 部署与 DNS 连接排查

**日期**: 2026-01-29
**标签**: #RustDesk #DNS #Troubleshooting #SelfHosted

在部署 RustDesk 自建服务器时，我们遭遇了“连不上”和“网页打不开”的困惑。以下是关键的架构知识点。

## 1. 原生 RustDesk Server 没有 Web 界面

**误区**: 访问 `https://rustdesk.willfan.me` 应该能看到一个管理后台或者网页版客户端。
**事实**:
*   RustDesk 开源版镜像 (`rustdesk/rustdesk-server`) **只**提供后台 API 和中继服务。
*   端口 `21118` 和 `21119` 是 WebSocket 端口，供客户端调用，不是给人用的 HTTP 网页。
*   如果直接用浏览器访问，会出现 404 或 Connection Closed。
*   **解决方案**: 如果需要网页版客户端，需额外部署 `rustdesk/rustdesk-server-web` 或类似的 Web 前端容器。

## 2. 客户端连接架构：直连 vs 反代

**误区**: 把所有域名都解析到 Caddy (反向代理)，让 Caddy 转发所有流量。
**事实**:
*   RustDesk 客户端主要使用 **TCP/UDP 21116** (ID服务/心跳) 和 **TCP 21117** (中继)。
*   Caddy (作为 HTTP Layer 7 代理) 默认只能转发 HTTP/HTTPS 流量。
*   **正确架构**:
    *   **Web API / Web 客户端**: 可以走 Caddy (HTTPS 443 -> 21118/21119)。
    *   **原生客户端 (PC/手机)**: 必须**直连** RustDesk 服务器 IP (`192.168.1.102`)，或者通过 L4 (TCP/UDP) 负载均衡转发。
    *   因此，域名 `rustdesk.willfan.me` 的 A 记录应该直接指向 RustDesk VM 的 IP，而不是 Caddy 的 IP。

## 3. DNS "仅主机可见" 问题 (Split-Horizon)

**现象**: 容器里 `nslookup` 失败，主机 `nslookup` 成功，客户端报错 "failed to lookup address"。
**原因**:
*   我们在内网路由器 (192.168.1.1) 上添加了 DNS 记录。
*   客户端使用了路由器 DNS，所以能解析 (但可能因缓存或系统设置有延迟)。
*   Docker 容器使用独立的内部 DNS (如 192.168.65.x)，默认可能不向上游请求或缓存了旧结果。
**调试技巧**:
*   **控制变量法**: 暂时用 IP 地址代替域名填入客户端。如果 IP 能通，说明网络层没问题，故障 100% 锁定在 DNS 层。

---

**最终结论**:
*   RustDesk 自建服务默认就是“无界面”的。
*   内网部署时，DNS 解析和端口直连是两个最大的坑。
