# Caddy WebDAV 配置与 Tailscale ACL 故障排查

本文记录了在部署 Homepage 和 Caddy WebDAV 服务过程中遇到的两个主要问题及其解决方案：Tailscale ACL 导致的 Ansible 连接失败，以及 Caddy WebDAV 插件与 `file_server` 的指令顺序冲突。

## 1. Tailscale ACL 与 Ansible 连接问题

### 现象
在使用 Ansible 部署 Homepage 时，连接 Proxmox 宿主机 (`pve0`) 失败，报错信息如下：
```
fatal: [homepage -> pve0]: UNREACHABLE! => {"changed": false, "msg": "... tailscale: tailnet policy does not permit you to SSH to this node ..."}
```

### 原因
*   **MagicDNS 解析**: 我们的环境开启了 Tailscale MagicDNS。当 Ansible 尝试连接主机名 `pve0` 时，系统将其解析为了 `pve0` 的 Tailscale IP (`100.x.x.x`)。
*   **ACL 限制**: Tailscale 的 ACL (Access Control List) 策略禁止了从当前控制节点到 `pve0` 的 SSH 连接。

### 概念定义
*   **MagicDNS**: Tailscale 提供的一种 DNS 服务，自动将 Tailscale 网络中的设备名称解析为其对应的 Tailscale IP 地址。
*   **Ansible Inventory `ansible_host`**: Ansible 用于指定实际连接目标的变量。如果不指定，Ansible 默认使用主机名（Inventory 中的名字）进行 DNS 解析。

### 解决方案
在 Ansible Inventory 中显式指定 `pve0` 的 **内网 IP** (`192.168.1.50`)。
```yaml
pve0:
  ansible_host: 192.168.1.50
```
这样 Ansible 会直接通过局域网连接，绕过 Tailscale 网络和 ACL 检查。

---

## 2. Caddy WebDAV 与 File Server 的指令顺序

### 现象
我们希望在浏览器中访问 WebDAV URL 时能看到文件列表（由 `file_server browse` 提供），而不是 XML 代码。
初次尝试在 `handle` 块中同时配置 `webdav` 和 `file_server` 时，Caddy 报错：
```
Error: adapting config using caddyfile: parsing caddyfile tokens for 'handle': directive 'webdav' is not an ordered HTTP handler
```

### 原因
*   **指令顺序 (Directive Order)**: Caddyfile 中的指令并不是按书写顺序执行的，而是按照内置的优先级列表排序。
*   **非标准指令**: `webdav` 是一个第三方插件指令，它不在 Caddy 的默认优先级列表中。因此，Caddy 不知道应该先执行 `webdav` 还是 `file_server`。
*   **冲突**: `file_server` 和 `webdav` 都试图处理请求。如果顺序不当，一个可能会覆盖另一个，或者导致配置解析错误。

### 概念定义
*   **`route` 块**: Caddyfile 中的一个特殊块。**在 `route` 块内部的指令会严格按照书写顺序执行**，忽略内置的优先级排序。这对于控制中间件的执行顺序非常有用。

### 解决方案
使用 `route` 块将 `file_server` 和 `webdav` 包裹起来，并显式定义执行顺序。

```caddy
webdav.willfan.me {
    handle {
        # ... basic_auth ...
        
        route {
            # 1. 先尝试 file_server (用于浏览器访问 / browse)
            file_server browse {
                root /var/www/webdav
            }
            # 2. 如果 file_server 没处理（或者作为 fallback），则由 webdav 处理
            webdav {
                root /var/www/webdav
            }
        }
    }
}
```
**注意**: 这里的顺序很关键。通常 `file_server` 会处理静态文件请求（如浏览器浏览），而 `webdav` 插件会处理特定的 DAV 方法（PROPFIND 等）。通过 `route` 块，我们确保了它们共存且互不干扰。
