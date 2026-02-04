# 📝 Troubleshooting Log: Windows SMB Upload Slowness (Tailscale Routing Loop)

**Date**: 2025-11-27
**Status**: ✅ Solved
**Environment**:
- **Client**: Windows 11 (Wi-Fi 6 + 2.5GbE Ethernet)
- **Host**: Proxmox VE (2.5GbE)
- **Guest**: Debian VM (Samba Service on Zvol)
- **Network**: Local LAN + Tailscale Mesh VPN

---

## 1. 问题描述 (Problem)
* Windows 向 Proxmox VM 上传文件时，SMB 速度被死锁在 **5 MB/s**。
* 无论使用 Wi-Fi 还是有线连接，速度均无法突破此瓶颈。
* `iperf3` 测速显示带宽正常 (600Mbps+)，但 SMB 协议传输极慢。

## 2. 排查过程 (Investigation Timeline)

### 阶段一：排除存储与系统配置 (Hardware/Config)
* **怀疑**: ZFS 同步写 (Sync Write) 或 CPU 单核瓶颈。
* **验证操作**:
    * 调整 VM CPU 核心数 (1 -> 4).
    * 设置 ZFS `sync=disabled` (Host端).
    * 开启 VM 磁盘缓存 `Cache=WriteBack`.
    * Samba 调优 (`aio read/write`, `TCP_NODELAY`).
* **结果**: 速度无变化，仍为 5 MB/s。**排除存储层瓶颈。**

### 阶段二：发现网络层异常 (Network Anomaly)
* **现象**:
    * 切换到 **有线直连 (Ethernet)** 后，Ping 值依然高达 **10ms - 12ms**。
    * **正常局域网有线 Ping 值应 < 1ms**。
* **关键诊断**: 使用 `tracert -d <Target_IP>` 追踪路由。
* **发现**:
    ```text
    Tracing route to 192.168.1.102:
    1    11 ms     100.119.126.56  (Tailscale Tunnel IP)
    2     9 ms     192.168.1.102   (Target LAN IP)
    ```
* **分析**: 流量没有走物理交换机 (Layer 2)，而是被 Windows 路由表导向了 **Tailscale 虚拟网卡** (Layer 3 VPN 隧道)。

## 3. 根本原因 (Root Cause)
**Tailscale 子网路由 (Subnet Routes) 优先级劫持。**

1.  **路由广播**: 局域网内某台设备通过 Tailscale 广播了 `192.168.1.0/24` 网段。
2.  **优先级倒置**: Windows 客户端开启了 "Use Subnet Routes"，且 Tailscale 接口的跃点数 (Metric) 低于物理网卡。Windows 误认为走 VPN 是访问内网的“最佳路径”。
3.  **性能损耗**:
    * **双重封装**: SMB 数据包被封装进 WireGuard 协议。
    * **MTU 碎片化**: VPN MTU (1280) < 以太网 MTU (1500)，导致数据包分片严重。
    * **加密开销**: 局域网流量被强制加密/解密，导致 CPU 和延迟双重打击。

## 4. 解决方案 (Solution)

### 修复步骤
在 Windows Tailscale 客户端中禁用子网路由接收：
1.  点击任务栏 Tailscale 图标 -> **Preferences (首选项)**。
2.  **取消勾选 "Use Subnet Routes"**。
3.  (备选) 检查 Exit Node 设置是否为 "None"。

### 验证
* 执行 `tracert -d 192.168.1.102` -> 变为 **1 跳直达**。
* 执行 `ping 192.168.1.102` -> 有线延迟恢复至 **< 1ms**。

## 5. 最终性能 (Final Results)

| 连接方式 | 修复前速度 | 修复后速度 | 状态 |
| :--- | :--- | :--- | :--- |
| **Wi-Fi 6** | 5 MB/s | **~60 MB/s** | 已跑满无线物理带宽 (480Mbps) |
| **有线 (2.5G)**| 5 MB/s | **~200 MB/s** | 接近 2.5GbE 实际吞吐极限 |

## 6. 经验总结 (Key Takeaways)
1.  **Ping 值是第一指标**: 局域网有线 Ping 值只要超过 1ms，必有物理介质故障或路由绕路。
2.  **Tracert 是神器**: 当网络表现不符合物理直连逻辑时，第一时间用 `tracert` 检查路径。
3.  **VPN 共存风险**: 在同网段下运行 Mesh VPN (Tailscale/ZeroTier) 时，务必注意**子网路由 (Subnet Routes)** 的配置，防止流量回环 (Hairpinning)。
