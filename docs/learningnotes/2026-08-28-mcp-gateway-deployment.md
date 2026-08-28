# MCP Gateway 部署记录

**日期**：2026-08-28
**范围**：`mcp-gateway` VM、Cloudflare Tunnel、Access Service Token 与 MCP
端点缓存绕过。

## 部署结果与资源标识

| 项目 | 值 |
|------|----|
| VM | `mcp-gateway`，VMID `109`，`192.168.1.109` |
| 公网端点 | `https://mcp.willfan.me/mcp` |
| Tunnel | `df495648-7b64-48e1-8283-db8e3ce4e874` |
| DNS 记录 | `c1189dd9e84c70e4d5e945499064432f` |
| Access Service Token | `16476b31-2538-4fda-9882-0668c7f41194` |
| Access Application | `50986a53-1641-44aa-92ea-bc69bef8b0a0` |
| Access Policy | `5a109b5c-2701-4dfc-be7b-d0e325cf4c8d` |
| Cache ruleset | `df1f954e765546629365d1be1c5eaad1` |
| Cache rule | `46518c8f2eeb4863a331321eee012efc` |

这些是非敏感的资源标识；Tunnel 密钥和 Access Client ID/Secret 均不记录在本
文档中，唯一持久化位置是加密的 Ansible Vault。

## 请求链路

```text
MCP agent
  → Cloudflare Access（只接受 Service Token）
  → Cache Rule（仅 mcp.willfan.me + /mcp，cache=false）
  → locally managed Cloudflare Tunnel
  → VM 109 的 cloudflared
  → http://127.0.0.1:3000/mcp
```

Tunnel 由 VM 本地的 `cloudflared` 配置管理，而不是由 Cloudflare 远程下发
ingress。该配置将 `mcp.willfan.me` 且路径精确匹配 `^/mcp$` 的请求路由至
`http://127.0.0.1:3000`，并以 `http_status:404` 拒绝其余请求。

这里的 `path` 是 ingress 的匹配条件，`service` 是 origin 的基址；因此公网
`/mcp` 最终会请求 `http://127.0.0.1:3000/mcp`。不要把 `/mcp` 重复拼接到
`service` 后面，否则实际 origin 路径会变成 `/mcp/mcp`。

## Access 与源站状态

未携带 Access 请求头的 `/mcp` 必须由 Access 返回 `401`（或等价 Access 拒绝），
不能到达 origin。携带有效 Service Token 后，Access 才会放行到 Tunnel。

在 MCP 应用尚未监听 `127.0.0.1:3000` 的阶段，认证后的 `/mcp` 返回 `502` 是
可预期的：它表示请求已通过 Access 并到达 Tunnel/origin 边界，但源站端口没有
可用应用。`502` 与 Access 的 `401` 必须分开诊断；前者不能用来证明 Access
策略失效，后者也不能用来证明源站不可用。

`/not-mcp` 不匹配 ingress 的 `^/mcp$`，应由 Tunnel 兜底规则返回 `404`。

## 使用 Access Service Token

获授权 agent 需要从 Vault 的以下两个变量取得值，并仅在请求进程内使用：

- `vault_mcp_access_client_id` → `CF-Access-Client-Id`
- `vault_mcp_access_client_secret` → `CF-Access-Client-Secret`

不要把值写入 shell 历史、日志、配置库或文档。轮换时先在 Vault 更新新凭据并让
所有 agent 切换，在明确的宽限期结束后再撤销旧 Token。

## 验证命令

以下命令均省略敏感值；认证请求的两个占位符必须从 Vault 在进程内注入。

```bash
# Access 拒绝：预期 401（或等价 Access 拒绝）
curl -sS -o /dev/null -w '%{http_code}\n' https://mcp.willfan.me/mcp

# Access 放行：应用未部署时预期为 502，而不是 401
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'CF-Access-Client-Id: <from-vault>' \
  -H 'CF-Access-Client-Secret: <from-vault>' \
  https://mcp.willfan.me/mcp

# 非 MCP 路径：预期 Tunnel 兜底 404
curl -sS -o /dev/null -w '%{http_code}\n' https://mcp.willfan.me/not-mcp

# 在 VM 上确认 ingress 的本地匹配规则
cloudflared tunnel --config /etc/cloudflared/config.yml ingress rule \
  https://mcp.willfan.me/mcp
```

缓存规则必须由 Cloudflare API 读取规则集
`http_request_cache_settings` 验证，且仅接受以下精确表达式与动作参数：

```text
(http.host eq "mcp.willfan.me" and http.request.uri.path eq "/mcp")
action: set_cache_settings
action_parameters.cache: false
```

## Q&A

### 为什么使用共享 Service Token？

共享 Token 降低了 agent 接入和运维成本，适合当前单一受控的 Homelab 使用场景；
代价是无法仅凭请求头区分每个 agent。若需要独立审计、最小权限或单独撤销，应为
每个 agent 或工作负载签发单独 Token。

### 为什么 Token 设置为一年后到期？

一年让日常运维保持低频，但仍强制进行周期性复核。应在到期前建立提醒，生成替代
Token、更新 Vault 和各 agent，再撤销旧 Token，避免到期造成中断。

### 轮换时为什么需要宽限期？

agent 的配置更新可能并非同时完成。新旧 Token 并存的短暂宽限期可避免服务中断；
宽限期必须有明确截止时间，并在所有消费者切换后撤销旧 Token。

### 为什么 `/mcp` 必须绕过缓存？

MCP 通信是动态且可能携带认证上下文的协议流量。规则只匹配指定主机和精确路径，
并设置 `cache: false`，避免边缘缓存响应或混淆会话语义。

## 已知限制

`terraform/proxmox/mcp-gateway.tf` 的 `mcp_gateway_ip` root output 仍是目标
apply 后才会由运行时状态填充的非阻塞限制。本次没有执行 refresh 或 apply；VM 的
实际地址以已验证的 `192.168.1.109` 为准。
