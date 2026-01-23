# Tailscale MagicDNS 与 Split DNS 原理

**日期**: 2025-12-04
**背景**: 在检查 Proxmox VE (PVE) 节点的 DNS 配置时，发现所有节点的 `/etc/resolv.conf` 中只有一个 nameserver：`100.100.100.100`。这引发了关于 Tailscale 如何处理 DNS 以及如何自定义上游 DNS 的讨论。

## 1. 核心概念定义

### MagicDNS
Tailscale 的一项功能，它自动为 Tailnet（Tailscale 网络）中的每台设备注册一个易读的域名（如 `my-server.tailnet-name.ts.net`）。开启后，你不再需要记忆 IP 地址，直接使用机器名即可访问内网设备。

### 100.100.100.100
这是 Tailscale 在本地运行的一个**虚拟 DNS 服务器地址**。它不是互联网上的某个远程服务器，而是由运行在本地机器上的 `tailscaled` 进程监听的地址。它充当了本机 DNS 请求的“第一跳”代理。

### Split DNS (分流解析)
一种 DNS 配置策略，允许根据域名的不同，将 DNS 请求发送到不同的 DNS 服务器。
*   **内网域名** -> 发送给内网 DNS 服务器（或由 Tailscale 本地处理）。
*   **公网域名** -> 发送给公网 DNS 服务器（如 8.8.8.8 或 ISP DNS）。

## 2. 问题与解答

**Q: 为什么我的 PVE 只有 `100.100.100.100` 这一个 DNS？按理说它应该只负责 Tailnet 内部解析才对。**

**A:** 这是 Tailscale MagicDNS 的默认行为（除非在启动时使用了 `--accept-dns=false`）。
在 Linux 系统中，标准的 `/etc/resolv.conf` 通常不支持复杂的“分流”配置（即不能简单地写“域名 A 问服务器 X，域名 B 问服务器 Y”）。为了确保 MagicDNS（如 `hostname.tailnet.ts.net`）在任何情况下都能被解析，Tailscale 的策略是**接管整个 DNS 解析**。
它将系统的 nameserver 强制指向自己 (`100.100.100.100`)，然后由它在内部进行分流。

## 3. 原理详解：交通指挥员比喻

可以将 `100.100.100.100` (即本地的 `tailscaled` 进程) 想象成一个**交通指挥员**。

当 PVE 发起一个 DNS 请求（例如 `ping baidu.com` 或 `ping my-nas`）时：

1.  **拦截**: 请求首先到达“交通指挥员” (`100.100.100.100`)。
2.  **判断**: 指挥员看一眼你要去哪里。
    *   **情况 A：你要去内网 (MagicDNS)**
        *   例如访问 `my-nas`。
        *   指挥员手里有一张内部地图（内存中的节点表），他**直接告诉你**：“my-nas 在 `100.64.0.5`”。
        *   **结果**: 速度极快，不经过公网。
    *   **情况 B：你要去公网**
        *   例如访问 `baidu.com`。
        *   指挥员发现这不在他的内部地图上。
        *   他会查看你在 Tailscale 后台给他的“上级指令”（Global Nameservers 配置）。
        *   **情况 B1：配置了具体 IP (如 8.8.8.8)** -> 他代表你去问 8.8.8.8。
        *   **情况 B2：配置为 "Local DNS settings" (默认)** -> 他会去查看操作系统原本的 DNS 配置（比如 DHCP 下发的 192.168.1.1），然后代表你去问这个原本的 DNS。
        *   拿到结果后，再转告给你。

## 4. 如何配置

如果你希望在使用 MagicDNS 的同时，让 PVE 使用你指定的 DNS（如路由器的 DNS 或特定的公网 DNS），你不应该去修改 PVE 的 `/etc/resolv.conf`（因为会被 Tailscale 覆盖），而是应该：

1.  登录 **Tailscale Admin Console**。
2.  进入 **DNS** 设置页面。
3.  在 **Global Nameservers** 部分，添加你想要的 DNS 服务器 IP。
    *   如果保留默认的 **"Local DNS settings"**，Tailscale 会自动使用宿主机通过 DHCP 获取的 DNS（通常是你的路由器）。
4.  开启 **Override local DNS**（通常建议开启，以确保所有请求都受控）。

这样，PVE 表面上虽然还是只认 `100.100.100.100`，但实际上公网解析已经走了你指定的路径。
