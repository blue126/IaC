# ESXi 链路抖动抑制导致的"插回原端口也不恢复"故障 (2026-08-11)

## 1. 背景

网关从 GL-A1300 迁到 N100/iStoreOS（2026-08-08）之后，T7910（ESXi 8.0.3）持续无法访问：`192.168.1.251`（ESXi 管理网）、`.249`（PBS）、`.250`（vCenter）全部不通。

排查时发现一个反直觉现象——用户的原始描述：

> 最开始 T7910 连接在 Mercury 交换机上，这时可以 ping 通 `192.168.1.251`。然后我把 T7910 直接接到 sks8300 上，这时可以看到 ping 曾经短暂通过几次，端口似乎有 flapping，然后就是长时间 ping 不通。最后我又把 T7910 转移回 Mercury 上，**这下是完全彻底 ping 不通了**。

"回到已知能工作的配置反而更糟"是本次排查的核心疑点。

## 2. 核心概念定义

- **Link Flapping（链路抖动）**：物理链路在短时间内反复经历 up/down 状态切换。常见诱因是速率/双工协商失败、光模块不兼容、线缆接触不良。
- **Link Flapping Dampening（抖动抑制）**：ESXi 的保护机制。当某块物理网卡在单位时间内的 link down 次数超过阈值，ESXi 判定其"不稳定"并**主动停用该网卡**，避免流量被送入一条半死不活的链路造成间歇丢包。
- **关键特性**：该停用**不会随链路恢复而自动解除**，必须重启主机（或手工干预）才能恢复。这正是"插回原端口也不通"的原因。
- **`Net.LinkFlappingThreshold`**：控制该机制的高级参数。ESXi 内置描述为 `Max number of link down events per minute before considering a link unstable (0 to deactivate)`，默认 `60`，设为 `0` 即关闭检测。修改的 `Impact` 为 `none`，无需重启。
- **vSwitch Uplink（上联口）**：标准虚拟交换机连接物理网络的物理网卡。一个 vSwitch 可绑定多个上联做冗余；只有一个时，该网卡即单点。

## 3. 决定性证据

日志位于 `/var/log/vobd.log`（VMkernel 观测事件），三条连续记录构成完整因果链：

```
[esx.problem.net.vmnic.linkstate.flapping]
  Taking down physical NIC vmnic2 because the link is flapping.

[vob.net.pg.uplink.transition.down]
  Uplink: vmnic2 is down. Affected portgroup: Management Network. 0 uplinks up.

[esx.problem.net.connectivity.lost]
  Lost network connectivity on virtual switch "vSwitch0". Physical NIC vmnic2
  is down. Affected port groups: "vc", "Management Network"
```

`0 uplinks up` 说明 `vSwitch0` 只有 `vmnic2` 一个上联，它一停，管理网与 vCenter 端口组同时消失。

## 4. 完整因果链

| # | 事件 |
|---|---|
| 1 | 将 T7910 的上联从 Mercury 换到 sks8300 |
| 2 | 新端口协商不稳定，链路反复 up/down |
| 3 | ESXi 判定 flapping，**主动停用 `vmnic2`** |
| 4 | `vSwitch0` 失去唯一上联 → 管理网、vCenter 端口组全断 |
| 5 | 插回 Mercury —— **ESXi 不会自动恢复被停用的网卡**，依然不通 |
| 6 | 重启主机 → `vmnic2` 重新初始化 → 恢复正常 |

## 5. 排查中的次生障碍：时钟偏差

关联日志时发现 ESXi 时间**比实际快约 11 小时**，导致其日志无法与网关的 DHCP 日志对齐，一度得出"虚机拿到 DHCP 时主机却是关机状态"的矛盾结论。

根因：

```
esxcli system ntp get  →  Enabled: false
```

**NTP 从未启用。** 该机长期手动开关机，每次断电后 RTC 漂移无人校正，累积至此。

已修复：设置 NTP 服务器（`0/1.pool.ntp.org` + 网关 `192.168.1.1`）、启用、`chkconfig ntpd on` 使其随主机启动，并确认防火墙 `ntpClient` ruleset 为 `true`。大偏差下 ntpd 不会自动收敛，需先 `esxcli system time set` 手工步进。

> **教训**：时间不同步不只影响日志排查。对备份服务器尤其关键——PBS 的快照时间戳、保留策略计算、以及与 pve0 之间的证书校验都依赖时间正确。


## 6. 处置与决策

**已执行**：

```bash
esxcli system settings advanced set -o /Net/LinkFlappingThreshold -i 0
```

**用户明确选择禁用抖动抑制，且不加冗余上联。**

两个方案的对比（记录以备将来重新评估）：

| 方案 | 效果 | 代价 |
|---|---|---|
| **禁用抖动抑制**（已采用） | 网卡不再被主动停用，链路恢复即恢复 | 网卡真的半死不活时，ESXi 会继续送流量，表现为间歇丢包，比彻底断网更难定位 |
| 加冗余上联（未采用） | `vmnic2` 抖动时自动切到 `vmnic1`（Intel I210，千兆），降速但不断网 | 需占用一个网口；`vmnic1` 当前已 UP 且闲置 |

在**单上联**拓扑下，抖动本就等同于断网，抑制机制带来的额外保护有限——这是该取舍成立的前提。若将来改为多上联，应重新评估是否恢复默认值 `60`。

## 7. Q&A 摘要

**Q：为什么插回原来能工作的端口反而彻底不通？**
A：ESXi 已将该网卡标记为不稳定并停用，这个状态不随链路恢复而解除，只有重启主机才能清除。故障点已不在交换机侧。

**Q：怎么区分"物理层故障"和"ESXi 主动停用"？**
A：看 `/var/log/vobd.log`。前者只有 `linkstate.down` 事件，后者会有明确的 `esx.problem.net.vmnic.linkstate.flapping` 与 `Taking down physical NIC` 字样。

**Q：热插拔上联口安全吗？**
A：物理上安全，但**存在触发抖动抑制的风险**，且恢复需要重启。生产环境换上联口前应先确认 vSwitch 有冗余上联，或预留重启窗口。

**Q：为什么虚机能上网、主机却不通？**
A：本次并非此情形（是时钟偏差造成的误判）。但该现象确实可能出现——虚机端口组与管理网 vmkernel 若绑定不同上联，其中一个失效时会呈现这种分裂状态。

## 9. 相关文件

- `/var/log/vobd.log` —— VMkernel 观测事件，链路状态变化的权威来源
- `/var/log/vmksummary.log` —— 主机启停历史
- `esxcli system settings advanced list -o /Net/LinkFlappingThreshold`
- `esxcli network nic list` —— 网卡链路状态、速率、驱动
- `esxcli system ntp get` / `set`
