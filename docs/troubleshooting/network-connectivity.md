# 网络连接问题排查 (Network Connectivity Troubleshooting)

本文档汇总了网络层、VPN、反向代理等问题的排查指南。

**来源**:
- `./slow-smb-over-wifi.md`
- `../learningnotes/2025-12-03-caddy-webdav-tailscale-troubleshooting.md`

---

## 问题 1: SMB 文件传输速度异常慢

### 症状
- Windows 向 Proxmox VM 上传文件时，SMB 速度被死锁在 **5 MB/s**
- 无论使用 Wi-Fi 还是有线连接，速度均无法突破此瓶颈
- `iperf3` 测速显示带宽正常 (600Mbps+)
- 但 SMB 协议传输极慢，有线连接延迟异常（10-12ms，应 < 1ms）

### 环境信息
- **Client**: Windows 11 (Wi-Fi 6 + 2.5GbE Ethernet)
- **Host**: Proxmox VE (2.5GbE)
- **Guest**: Debian VM (Samba 服务)
- **网络**: 本地 LAN + Tailscale Mesh VPN

### 诊断步骤

#### Step 1: 排除存储和系统配置

1. 检查 ZFS 同步设置：
   ```bash
   zfs get sync <pool>
   # 尝试设置为 disabled（如果允许）
   ```

2. 调整 VM CPU 核心数：
   ```bash
   qm set <vmid> --cores 4
   ```

3. 启用 VM 磁盘缓存：
   ```bash
   # 在 Proxmox WebUI 中修改，或通过 API
   qm set <vmid> --scsi0 storage:image,cache=writeback
   ```

4. 优化 Samba 配置（在 VM 中）：
   ```ini
   # /etc/samba/smb.conf
   [global]
   socket options = TCP_NODELAY IPTOS_LOWDELAY
   use sendfile = yes
   aio read size = 16384
   aio write size = 16384
   ```

**观察结果**: 如果这些改动都不能提升速度，则排除了存储层瓶颈。

#### Step 2: 诊断网络层

**关键检查**：查看 Ping 延迟和路由路径

```bash
# Windows 中运行
ping 192.168.1.102
# 如果是有线直连，延迟应该 < 1ms
# 如果延迟 > 5ms，说明有问题
```

**看到延迟异常？用 tracert 跟踪路由**：

```bash
tracert -d 192.168.1.102
```

**输出示例（错误）**:
```text
Tracing route to 192.168.1.102:
  1    11 ms     100.119.126.56  (Tailscale Tunnel IP)
  2     9 ms     192.168.1.102   (Target LAN IP)
```

**分析**: 流量没有走物理交换机 (Layer 2)，而是被 Windows 路由表导向了 **Tailscale 虚拟网卡** (Layer 3 VPN 隧道)，这导致了性能下降。

### 根本原因

**Tailscale 子网路由 (Subnet Routes) 优先级劫持**

1. **路由广播**: 局域网内某台设备通过 Tailscale 广播了 `192.168.1.0/24` 网段
2. **优先级倒置**: Windows 客户端开启了"Use Subnet Routes"，且 Tailscale 接口的跃点数 (Metric) 低于物理网卡
3. **流量绕路**: Windows 误认为走 VPN 是访问内网的"最佳路径"

**性能损耗链**:
- **双重封装**: SMB 数据包被封装进 WireGuard 协议
- **MTU 碎片化**: VPN MTU (1280) < 以太网 MTU (1500)，导致数据包分片
- **加密开销**: 局域网流量被强制加密/解密，导致 CPU 和延迟双重打击

### 解决方案

在 Windows Tailscale 客户端中禁用子网路由接收：

1. 点击任务栏 Tailscale 图标 → **Preferences (首选项)**
2. **取消勾选 "Use Subnet Routes"**
3. (备选) 检查 Exit Node 设置是否为 "None"

**验证修复**:

```bash
# Windows 中运行
tracert -d 192.168.1.102
# 应该显示 1 跳直达，而不是经过 Tailscale

ping 192.168.1.102
# 有线延迟应恢复至 < 1ms
```

### 最终效果

| 连接方式 | 修复前速度 | 修复后速度 | 瓶颈 |
|---------|---------|---------|------|
| **Wi-Fi 6** | 5 MB/s | ~60 MB/s | Wi-Fi 物理带宽 (480Mbps) |
| **有线 (2.5G)** | 5 MB/s | ~200 MB/s | 2.5GbE 实际吞吐极限 |

---

## 问题 2: Tailscale MagicDNS 与 Ansible SSH 连接冲突

### 症状
使用 Ansible 部署 Homepage 时，连接 Proxmox 宿主机失败：
```
fatal: [homepage -> pve0]: UNREACHABLE! => {
  "changed": false, 
  "msg": "... tailscale: tailnet policy does not permit you to SSH to this node ..."
}
```

### 诊断步骤
1. 检查 Tailscale 是否启用了 MagicDNS：
   ```bash
   tailscale status
   # 查看是否有 MagicDNS 相关的标记
   ```

2. 测试 DNS 解析：
   ```bash
   nslookup pve0
   # 如果解析到 Tailscale IP（100.x.x.x），说明 MagicDNS 被启用
   ```

3. 查看 Ansible Inventory 中的 `ansible_host` 设置：
   ```bash
   grep ansible_host ansible/inventory/*.yml
   ```

### 原因分析

**两个概念的冲突**:

- **MagicDNS 解析** - 当 Ansible 尝试连接主机名 `pve0` 时，系统将其解析为 `pve0` 的 Tailscale IP（`100.x.x.x`）
- **Tailscale ACL 限制** - Tailscale 的 Access Control List (ACL) 策略限制了从当前控制节点到 `pve0` 的 SSH 连接

**结果**: 即使两台机器在同一个 Tailnet 中，也可能因为 ACL 限制而无法连接。

### 解决方案

在 Ansible Inventory 中显式指定目标的**内网 IP**，而不依赖 MagicDNS：

```yaml
# inventory/hosts.yml
pve0:
  ansible_host: 192.168.1.50    # 直接用内网 IP
  ansible_user: root
  ansible_port: 22

# 而不是
pve0:
  # 这样 Ansible 会用 DNS 解析 pve0，可能得到 Tailscale IP
  # 如果 Tailscale ACL 不允许，连接就会失败
```

**优势**:
1. **绕过 Tailscale ACL** - 通过本地 LAN 直连，不经过 Tailscale
2. **更快连接** - 局域网直连比 VPN 隧道更快
3. **避免 DNS 解析问题** - 不依赖 MagicDNS 的"正确性"

**最佳实践**: 在自建网络中，始终在 Inventory 中使用内网 IP，保留 Tailscale 用于出网或跨域连接。

---

## 问题 3: Caddy WebDAV 配置错误 - 指令顺序冲突

### 症状
在 Caddyfile 中同时配置 `webdav` 和 `file_server` 时，Caddy 报错：
```
Error: adapting config using caddyfile: parsing caddyfile tokens for 'handle': 
directive 'webdav' is not an ordered HTTP handler
```

### 诊断步骤
1. 检查 Caddyfile 语法：
   ```bash
   caddy validate --config Caddyfile
   ```

2. 查看 Caddy 日志：
   ```bash
   journalctl -u caddy -n 50
   ```

3. 确认 `webdav` 插件是否正确安装：
   ```bash
   caddy list-modules | grep webdav
   ```

### 原因分析

**Caddy 指令优先级**:

在 Caddyfile 中，指令并不是按书写顺序执行的，而是按照 Caddy 的内置优先级列表排序。这对于标准指令（如 `file_server`、`reverse_proxy`）很有效，但对于第三方插件指令（如 `webdav`）会造成问题。

**具体冲突**:
- `file_server` 是 Caddy 的标准指令，有明确的优先级
- `webdav` 是第三方插件，不在优先级列表中
- Caddy 不知道应该先执行 `webdav` 还是 `file_server`
- 结果：报错或指令无法生效

### 解决方案

使用 `route` 块强制指定执行顺序（`route` 块内的指令严格按书写顺序执行）：

```caddy
webdav.example.com {
    handle {
        # 认证
        basic_auth * {
            user $2y$10$...
        }
        
        # 使用 route 块定义执行顺序
        route {
            # 1. 先尝试 file_server (用于浏览器访问 / browse)
            file_server browse {
                root /var/www/webdav
            }
            
            # 2. 如果 file_server 没处理，由 webdav 处理
            #    (处理 WebDAV 协议的特定方法：PROPFIND、MKCOL 等)
            webdav {
                root /var/www/webdav
            }
        }
    }
}
```

**为什么这个顺序能工作**:
- `file_server browse` 处理普通的 HTTP GET 请求（浏览器访问）
- `webdav` 处理 WebDAV 特定的方法（PROPFIND、MKCOL、MOVE 等）
- 两者共存，互不干扰

### 最佳实践

```caddy
# ❌ 不好：指令顺序不明确
webdav.example.com {
    file_server browse { root /data }
    webdav { root /data }
}

# ✅ 好：使用 route 块明确顺序
webdav.example.com {
    route {
        file_server browse { root /data }
        webdav { root /data }
    }
}
```

**关键概念**:

| 块类型 | 特点 | 用途 |
|------|------|------|
| `handle` | 指令按优先级排序 | 标准指令的快速配置 |
| `route` | 指令严格按顺序执行 | 需要精确控制执行顺序的插件 |

---

## 问题 4: Ansible 连接 Proxmox 宿主机权限问题

### 症状
```
UNREACHABLE! => {
  "msg": "... Permission denied (publickey,password) ..."
}
```

或

```
UNREACHABLE! => {
  "msg": "... Does not match key type ssh-rsa ..."
}
```

### 诊断步骤
1. 直接测试 SSH 连接：
   ```bash
   ssh -vvv root@192.168.1.50
   # -vvv 显示详细的认证过程
   ```

2. 检查 Ansible 的 SSH 配置：
   ```bash
   grep -A5 "\[defaults\]" ansible.cfg
   grep -A5 "\[ssh_connection\]" ansible.cfg
   ```

3. 验证 SSH 公钥是否在目标服务器上：
   ```bash
   ssh-keyscan -H 192.168.1.50 >> ~/.ssh/known_hosts
   ssh root@192.168.1.50 "cat ~/.ssh/authorized_keys"
   ```

### 原因分析

常见原因：
1. **SSH 密钥不匹配** - 使用了错误的密钥或密钥权限不正确
2. **known_hosts 缺失** - SSH 第一次连接时需要确认主机
3. **密钥类型不支持** - 某些老系统不支持新的密钥类型（如 ssh-ed25519）

### 解决方案

#### 方案 A: 使用密钥认证

```ini
# ansible.cfg
[defaults]
private_key_file = ~/.ssh/id_rsa

[ssh_connection]
ssh_args = -o ControlMaster=auto -o ControlPersist=60s -o StrictHostKeyChecking=accept-new
```

**生成密钥** (如果还没有):

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
# 复制公钥到目标服务器
ssh-copy-id root@192.168.1.50
```

#### 方案 B: 使用密码认证

```ini
# ansible.cfg
[defaults]
host_key_checking = False

[ssh_connection]
ssh_args = -o StrictHostKeyChecking=accept-new
```

**在命令行中指定密码**:

```bash
ansible-playbook playbooks/deploy.yml -k
# -k 会提示输入 SSH 密码
```

或在 Inventory 中使用 `ansible_password` (不推荐，安全风险)。

---

## 网络诊断三板斧 (Network Diagnosis Trinity)

当网络性能异常时，按以下顺序逐一排除：

### 1. Ping - 检测连通性和延迟

```bash
# 单个包测试
ping -c 4 192.168.1.102

# 连续测试 30 秒
ping -c 30 192.168.1.102 | tail -5  # 查看统计
```

**关键指标**:
- **有线局域网**: < 1ms 为正常，> 5ms 为异常
- **Wi-Fi**: < 5ms 为正常，> 20ms 为异常
- **VPN/远程**: 10-50ms 为正常

### 2. Tracert (Linux: traceroute) - 跟踪路由路径

```bash
# Windows
tracert -d 192.168.1.102

# Linux
traceroute 192.168.1.102
```

**看什么**:
- 跳数 (hop count) - 是否过多（> 15 通常表示绕路）
- 延迟增长 - 是否逐步增长（正常）还是突然跳变（可能是路由问题）

### 3. Route - 查看系统路由表

```bash
# Windows
route print

# Linux
route -n
或
ip route show
```

**看什么**:
- 目标网段 `192.168.1.0/24` 是否被路由到正确的接口（网卡）
- 是否被 VPN 或其他虚拟接口"劫持"

---

## 总结与最佳实践

### 记住这些要点

1. **Ping 是第一指标** - 局域网有线 Ping 只要超过 1ms，必有物理故障或路由绕路
2. **Tracert 是神器** - 当网络表现不符合物理直连逻辑时，用 `tracert` 检查路径
3. **VPN 共存风险** - 在同网段下运行 Mesh VPN 时，务必注意子网路由的配置
4. **显式优于隐式** - Inventory 中使用内网 IP，不依赖 DNS 解析或 VPN 路由
5. **测试分层** - 先测 IP（网络层），再测域名（应用层），逐步排除

### 快速参考

| 症状 | 诊断命令 | 快速修复 |
|------|---------|--------|
| SMB 速度慢 | `tracert <ip>` / `ping <ip>` | 禁用 Tailscale Subnet Routes |
| Ansible 连接失败 | `ssh -v <host>` | 在 Inventory 中使用内网 IP |
| Caddy 指令报错 | `caddy validate` | 用 `route` 块包裹 `webdav` + `file_server` |
| DNS 解析问题 | `nslookup <hostname>` / `dig <hostname>` | 使用 IP 直连测试，隔离 DNS 问题 |

