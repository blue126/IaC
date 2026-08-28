# MCP Gateway VM、Cloudflare Tunnel 与 Access 设计

**日期**：2026-08-28
**状态**：已确认设计，待实施计划
**目标环境**：Proxmox `pve0`、Cloudflare `willfan.me`

## 目标

在 `pve0` 上创建一台名为 `mcp-gateway` 的 Ubuntu 24.04 完整 VM，安装 Docker
Engine、Docker Compose 插件和 Cloudflared，并通过独立的 Cloudflare Tunnel 暴露
`https://mcp.willfan.me/mcp`。该端点只允许持有共享 Service Token 的 agent 访问，
并明确绕过 Cloudflare 缓存。

## 非目标

- 本阶段不部署实际监听 `127.0.0.1:3000` 的 MCP Gateway 应用。
- 本阶段不修改 Hermes、Codex 或其他 agent 的客户端配置。
- 不复用 Jenkins 或 n8n Tunnel。
- 不提交 Git commit；仓库规则要求用户明确授权后才能提交。

## 已确认的基础设施参数

| 参数 | 值 |
|---|---|
| VM 名称 | `mcp-gateway` |
| Proxmox 节点 | `pve0` |
| VMID | `109` |
| IP | `192.168.1.109/24` |
| vCPU | `2` |
| 内存 | `4096 MB` |
| 系统盘 | `32 GB` |
| OS | Ubuntu 24.04 模板 |
| Ansible 组 | 仅 `pve_vms` |

## 架构

```text
Agent
  │ CF-Access-Client-Id / CF-Access-Client-Secret
  ▼
mcp.willfan.me/mcp
  │
  ├─ Access Application: MCP Gateway
  │    └─ Service Auth policy → mcp-agents
  │
  ├─ Cache Rule
  │    └─ host = mcp.willfan.me AND path = /mcp → bypass cache
  │
  └─ CNAME → TUNNEL_UUID.cfargotunnel.com
       ▼
     named Tunnel: mcp-gateway（locally managed）
       ▼
     cloudflared on VM 109
       ├─ hostname: mcp.willfan.me
       ├─ path regex: ^/mcp$
       ├─ service: http://127.0.0.1:3000
       └─ catch-all: 404
```

Cloudflared 的 `path` 是匹配条件，`service` 是 origin 基址。进入公网 `/mcp` 的请求
保留原始路径，因此最终 origin 是 `http://127.0.0.1:3000/mcp`。不能把 `/mcp`
再次附加到 `service`，否则会产生路径重复风险。

## 仓库组件

### Terraform

`terraform/proxmox/mcp-gateway.tf` 使用现有 `proxmox-vm` 模块创建 VM，并注册
`ansible_host`。执行前必须通过 `terraform plan` 确认仅新增 VM 109；`apply` 需要用户
再次批准。

### 通用 Cloudflared role

`ansible/roles/cloudflared` 保持与 Jenkins 解耦：

- 默认 `cloudflared_configure_tunnel: false`，只安装软件。
- 启用 Tunnel 时使用通用 `cloudflared_ingress_rules`。
- credentials 可以由 Ansible Vault 下发；未提供时兼容目标机已有文件。
- ingress 模板自动追加 `http_status:404` catch-all。

### MCP Gateway host vars

新增 `ansible/inventory/host_vars/mcp-gateway.yml`：

```yaml
cloudflared_configure_tunnel: true
cloudflared_tunnel_name: mcp-gateway
cloudflared_tunnel_id: "Cloudflare 创建响应返回的 UUID"
cloudflared_tunnel_credentials: "{{ vault_mcp_gateway_cloudflared_credentials }}"
cloudflared_ingress_rules:
  - hostname: mcp.willfan.me
    path: ^/mcp$
    service: http://127.0.0.1:3000
```

### MCP Gateway playbook

新增 `ansible/playbooks/deploy-mcp-gateway.yml`，部署顺序为：

```text
common → docker → cloudflared
```

Verify play 检查 Docker 服务、Docker Compose、Cloudflared 服务、Tunnel 连接与 ingress
匹配。由于 MCP 应用不在本阶段部署，不能把 origin HTTP 200 作为成功条件。

## Cloudflare 资源

当前只读盘点确认：`willfan.me` zone active；现有 `jenkins-webhook` 与 `n8n` Tunnel
均为 locally managed；不存在 `mcp.willfan.me` DNS、Access Application、Service Token
或 zone cache entrypoint ruleset。

实施时创建以下独立资源：

| 资源 | 配置 |
|---|---|
| Named Tunnel | `mcp-gateway`，`config_src: local` |
| DNS | proxied CNAME `mcp.willfan.me` → `TUNNEL_UUID.cfargotunnel.com` |
| Access Application | `MCP Gateway`，self-hosted domain `mcp.willfan.me/mcp` |
| Service Token | `mcp-agents`，`8760h`，enabled |
| Access Policy | Service Auth，仅 include `mcp-agents`，precedence 1 |
| Cache Rule | 精确匹配 host 与 `/mcp`，`set_cache_settings.cache: false` |

创建前必须按名称、domain 和 DNS hostname 查询。对象存在且属性一致时复用；存在但
配置冲突时停止，不静默覆盖。

## 密钥管理

Ansible Vault 是唯一密码源。新增变量：

```yaml
vault_mcp_gateway_cloudflared_credentials:
  AccountTag: "8e80132a8538b3f0312a8929bb065417"
  TunnelSecret: "创建 named Tunnel 时生成的 32-byte base64 secret"
  TunnelID: "Cloudflare 创建响应返回的 UUID"
vault_mcp_access_client_id: "Service Token 创建响应返回的 Client ID"
vault_mcp_access_client_secret: "Service Token 创建响应仅显示一次的 Client Secret"
```

Tunnel ID 本身不敏感，仍以明文写入 `host_vars/mcp-gateway.yml`。Service Token ID、
Access Application ID、Policy ID、DNS record ID 和 ruleset/rule ID 也不是秘密，可用于
验证或文档记录。

主 checkout 的 `ansible/.vault_pass` 仅临时复制到 Dev Container 的受限临时文件；
权限设为 `0600`，完成 Vault 更新后删除。Tunnel secret 与 Service Token secret 不在
终端、文档或最终回复中回显。Service Token secret 只在 Cloudflare 创建响应中出现
一次，因此创建后必须立即写入 Vault，写入验证成功前不继续后续资源创建。

## 实施顺序

1. 完成本地 Terraform、Ansible、host vars 与 Vault 变量结构。
2. 运行 Terraform 格式检查、初始化、验证和 plan。
3. 用户批准后 apply VM 109，并等待 SSH/cloud-init 就绪。
4. 预检 Cloudflare 资源不存在或与设计一致。
5. 创建 locally-managed named Tunnel，并立即保存 credentials 到 Vault。
6. 创建 `mcp.willfan.me` Tunnel DNS route。
7. 创建 `mcp-agents` Service Token，并立即保存 Client ID/Secret 到 Vault。
8. 创建 Access Application、Service Auth policy 和 cache bypass rule。
9. 运行 `deploy-mcp-gateway.yml` 完整部署。
10. 回读并验证本地与 Cloudflare 状态。

## 验证

### 本地静态验证

```bash
terraform fmt -check -recursive
terraform validate
ansible-playbook playbooks/deploy-mcp-gateway.yml --syntax-check
ansible-playbook playbooks/deploy-cloudflared.yml --syntax-check
```

### VM 与服务验证

- VM 109 在 `pve0` 运行，IP 为 `192.168.1.109`。
- SSH 与 cloud-init 就绪。
- Docker systemd service active。
- `docker compose version` 成功。
- Cloudflared systemd service active。
- Cloudflare API 显示 `mcp-gateway` 至少一个 connector healthy。
- `cloudflared tunnel ingress validate` 成功。
- `https://mcp.willfan.me/mcp` 命中 MCP ingress rule。
- 其他路径命中 404 catch-all。

### Access 与缓存验证

- 无 Access headers 的 `/mcp` 请求被拒绝。
- 正确 `mcp-agents` headers 的请求通过 Access。
- 在 MCP 应用尚未运行时，通过 Access 后可能返回 origin `502`；这是已知边界，不视为
  Access/Tunnel 失败。
- API 回读确认 DNS、Application、Policy、Token 和 cache bypass rule 属性与设计一致。

## 失败处理

- 中途失败时不自动删除已创建的 Cloudflare 资源，也不重新生成 secret。
- 保留已安全写入 Vault 的凭据与所有非敏感资源 ID，报告准确停点。
- 若 Cloudflare 对象存在但配置冲突，停止并请求用户决定更新、复用或删除。
- 若 Vault 写入失败，停止创建依赖资源，优先恢复密钥的安全持久化。
- 若 Terraform plan 包含 VM 109 之外的意外变更，不执行 apply。
- 若 Ansible 部署失败，修复 playbook，不使用目标机 CLI 绕过。

## 后续工作

实际 MCP Gateway 应用部署后，再进行 HTTP 200、MCP 协议握手和 agent 客户端配置验证。
共享 `mcp-agents` Token 泄露影响所有 agent，因此应配置到期提醒，并在需要时使用
Cloudflare 的 secret rotation grace period 完成无中断轮换。
