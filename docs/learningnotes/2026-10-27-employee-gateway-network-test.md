# 员工网关跨地域网络测试报告

测试日期：2026-10-27（悉尼时间）。目标：比较中国员工访问澳洲工作区时可选中继地域的网络表现。

## 结论

短期保留现有香港 ECS 中继。GA 经现有 OCI 与 WireGuard 到家中的测试显示，它优于同轮 OCI 直连；但 GA 与香港 ECS 未做同时间、同方法对照，尚不能判定两者谁更好。香港 ECS 的历史 SSH 中位数为 184–208 ms，GA 本轮为 245 ms；测试时段和转发方式不同，只能参考。后续应固定同一客户端、VM 和测量方法，交替测试两条路径。

这些结果仅反映本次、这几个测试来源与时段；不同线路的分段测量不能直接替代通过网关到员工 VM 的实际 SSH 测试。

## 测试方法

在广州、深圳、新加坡、印尼和菲律宾各创建一台阿里云 ECS，使用实例自带公网 IP。分别从中国 Windows（物理网卡、绕开 VPN）、家中 Mac 和悉尼 OCI 测量：10 次 ping、10 次 TCP 80 新连接，以及各两次 5 MiB HTTP 下载和上传。TCP 表中是建连耗时中位数，单位毫秒。部分来源的传输测试时间可能重叠，5 MiB 文件较小，速率不代表稳定带宽。

| ECS 地域 | 中国 Windows | 家中 Mac | 悉尼 OCI |
| --- | ---: | ---: | ---: |
| 广州 | 19.87 | 262.77 | 312.45 |
| 深圳 | 23.55 | 323.11 | 320.51 |
| 新加坡 | 209.13 | 347.49 | 98.82 |
| 印尼 | 360.41 | 391.22 | 113.05 |
| 菲律宾 | 243.00 | 331.88 | 197.95 |

## 传输与稳定性

- 中国 Windows 到广州、深圳的 5 MiB 下载两次均完成；到新加坡、印尼、菲律宾的下载均在 30 秒时超时，接收的是部分文件。
- 中国 Windows 的上传未测：远程执行策略拒绝了包含上传和临时文件操作的批次（`rejected: blocked by policy`），没有给出具体原因。
- 家中 Mac 到新加坡两次下载约 0.53 和 1.47 Mbps；到印尼约 0.86 和 3.32 Mbps，波动明显。家中 Mac 到深圳的两次上传超时。
- OCI 到广州和深圳的两次上传均超时；OCI 到新加坡下载约 25–26 Mbps、上传约 42 Mbps；到印尼下载约 26 Mbps、上传约 37 Mbps。各方向均从客户端视角描述。
- 中国侧 ping：印尼丢失 1/10，其余四个地域均收到 10/10。小样本不能代表长期丢包率。

## 阿里云香港的历史对照

此前中国侧设备在关闭全局 VPN 后，对阿里云香港入口 `47.57.14.220` 做了 20 次 HTTP TCP 建连测量，20 次均返回 HTTP 200；建连中位数 **18.50 ms**，范围 **15.23–26.68 ms**，平均 **19.34 ms**。这组数据由当时的测试者提供，与本次五地域测试不在同一时段，且不能假定是同一台 Windows 设备。

此前记录中的香港入口到悉尼 OCI TCP 建连平均约 **152 ms**；这个值来自 Hindsight「五地域 ECS 网关网络对照」历史记录，尚未在本报告中找到对应的原始逐次日志，应视为历史参考。家中 Mac 到阿里云香港入口的可比原始测量结果暂未核实，不填推算值。香港到 OCI 的历史测量方向、测试协议和取平均方式也不同于本次 OCI 到各地域的 TCP 中位数，不能视作同一轮测试。

## 与香港试点的关系

此前另一轮中国测试主机经香港、OCI 到家中进行实际 SSH 测量，两轮中位数约 184 和 208 ms，每轮 30 次均出现两次约 436–721 ms 的尖峰。这是实际 SSH 会话测量，与本次独立 TCP 分段测试在时间和方法上不同，仅可参考，不能作严格同条件排名。

后续应让不同地区、运营商的员工在白天和晚高峰测试现有香港路径的实际 SSH，记录中位数、高分位、丢包和卡顿频率；必要时同时测各段链路以定位尖峰。

## 资源状态

五台测试 ECS、系统盘、专用 VPC、交换机和安全组已删除并核实；未创建 EIP。随后用于河源直连测试的 ECS、EIP、安全组和云端测试密钥对已释放。原有河源 VPC 与交换机不是本次新建资源，予以保留。

## AWS 香港公开端点预检

AWS 的 [EC2 Reachability Test](https://ec2-reachability.amazonaws.com/) 列出香港区 `ap-east-1` 的公开探测地址 `18.162.80.8`。2026-10-27 从三处各发送 10 次 ICMP ping，间隔约 1 秒，均收到 10/10：

| 来源 | 最小 RTT | 平均 RTT | 最大 RTT |
| --- | ---: | ---: | ---: |
| 中国 Windows（物理接口） | 105 ms | 106.4 ms | 109 ms |
| 家中 Mac | 272.5 ms | 297.1 ms | 348.1 ms |
| 悉尼 OCI | 241.1 ms | 247.0 ms | 256.4 ms |

该 AWS 公共地址只用于初步连通性和延迟探测，不是专用 EC2 的传输或端到端 SSH 测试。账号当时尚未启用香港区，尚未创建 EC2 或进行完整传输测试。与其他地域的测试时间不同，不能据此给线路做严格排名。

## AWS 北京公开端点预检

AWS 官方可达性列表中的北京公开探测地址 `52.80.5.207`，各来源测试 10 次 ping：中国 Windows 平均 50.5 ms、10/10 成功；家中 Mac 平均 299.11 ms、10/10 成功；悉尼 OCI 平均 316.02 ms、8/10 成功。公开探测点可能限速，小样本不能推断长期丢包或吞吐。北京专用实例和实际中继未测试。

## 香港 GA 到现有 OCI 和家中：受控复测

测试路径为中国 Windows → 香港 GA 普通 BGP 接入 → 新加坡 GA 终端组 → 悉尼 OCI → 现有 WireGuard → 家中网关 → VM502。当前账户配置悉尼 GA 终端组的干运行被拒绝，故本次使用新加坡终端组。

第一组使用同一个 OCI HTTPS 服务、相同 SNI 和证书、两条持久连接交替各 20 次：GA 完整响应中位 168.37 ms、P95 178.62 ms、最大 183.51 ms；直连 OCI 中位 326.56 ms、P95 332.44 ms、最大 900.71 ms。两组各成功 20/20。这只测到 OCI。

随后同一中国 Windows 使用相同 wpan 设备身份，通过相同 OCI、现有 WireGuard、家中网关和 VM502 测实际 SSH：两组各保持一个 SSH 会话，逐条发出标记并等待对应输出，各 30 次成功。GA 路径中位 **245.00 ms**、P95 **252.21 ms**、最大 **256.91 ms**；直连 OCI 中位 **533.52 ms**、P95 **1437.89 ms**、最大 **1996.11 ms**。测试在 2026-10-27 22:46:43–22:47:38 悉尼时间进行，GA 先测、直连后测，非交替或同时采样；不含建连及身份验证耗时。测试期间直连出现明显尖峰，结果值得继续用其他时段、多个设备和运营商交替复测。

临时 OCI SSH 授权仅允许转发至家中网关，测试后删除；GA 实例及临时终端组、监听与加速入口已清理并核实实例不存在。现有 OCI→家中的 WireGuard 和员工入口保留。

## Tailscale 直连 VM502 测试

Windows 与 VM502 加入独立测试 tailnet，均使用 Tailscale 1.104.2。2026-10-27 23:22:01–23:22:27（悉尼时间），Windows 使用既有设备 SSH 公钥直接访问 VM502；保持一个 SSH 会话，30 次标记往返全部成功。中位数 **332.55 ms**、P95 **929.21 ms**、最大 **943.22 ms**；其中三次约 914–943 ms。测试前、10 次后、20 次后和结束时的 Tailscale 状态均为 direct，快照不能排除间隙中短暂切换。计时不含建连。

此前香港 GA→OCI→WireGuard→VM502 的 SSH 中位数为 245 ms、P95 252 ms；两轮时段不同，且 Tailscale 路径直接连接 VM，不能作为同时间严格对照。VM502 临时 SSH 测试授权测后移除；Tailscale 客户端和独立 tailnet 保留供后续 Peer Relay 测试。

Tailscale 测试后补充只读路由核查：当前 `direct` 对端为家中公网 UDP 端点，Windows 到该公网 IP 的选中路由为 Clash/Meta TUN，SSH 内层则走 Tailscale 虚拟网卡。此前 SSH 测试时没有保存外层 UDP 端点和路由，不能确认当时是否经过 Clash；当前路由表也不能单独证明 Clash 实际如何转发数据包。需在同一轮测量中记录路由和流量，才能可靠比较开启与关闭 Clash 的效果。

## Tailscale：Clash TUN 开关对照

中国 Windows 同一设备到 VM502，用户自行切换 Clash TUN，分别使用同一脚本进行各 30 次 SSH 会话内标记往返，均成功 30/30。结果文件时间为北京时间（UTC+8）：TUN 关闭轮 2026-10-27 20:35:22–20:35:50，开启轮 20:37:40–20:38:08。

| 状态 | 测试开始及结束路径快照 | 中位数 | P95 | 最大值 |
| --- | --- | ---: | ---: | ---: |
| TUN 开启 | 开始和结束均 direct，外层选中 Meta/Clash TUN | 325.38 ms | 952.85 ms | 957.52 ms |
| TUN 关闭 | 开始为 DERP(syd)，结束为 direct，外层选中 WLAN | 330.79 ms | 335.32 ms | 948.85 ms |

关闭轮的路径在测试期间从 DERP 变为 direct，快照不足以确认切换发生在哪个样本。两轮非同步，30 个样本的 P95 容易受单次尖峰影响；本轮中位数相差约 5.4 ms，不能单凭此次测试断言两种模式长期稳定性相同。

## 香港 Tailscale Peer Relay 试点

使用独立测试 tailnet 和临时香港阿里云 ECS，Peer Relay UDP 40000。为排除 Tailscale 自动优先直连，测试期间仅在 VM502 临时丢弃与该 Windows 公网地址之间的 UDP，并配置自动回滚；测试后已移除规则并恢复直连。Windows 保持当时的 Clash TUN 设置。

Windows→香港 Peer Relay→VM502 单个 SSH 会话 30 次标记往返均成功：中位数 **413.09 ms**、P95 **435.05 ms**、最大 **888.06 ms**。测试前、登录后、第 10 和第 20 次后、结束时均观察到指定香港 Peer Relay；离散快照不能排除间隙切换。初始 ping 先经过悉尼 DERP，后切换为香港 Peer Relay；SSH 测量只在确认中继后开始。

对照此前 Tailscale 直连的中位数约 333 ms、P95 929 ms，Peer Relay 此轮中位数较高但 P95 较低；两次测试不同时间且样本只有 30 次，不构成长时间稳定性结论。此前 GA 经 OCI 的 245 ms 中位数亦不能作为同时段对照。

测试结束后移除 VM502 临时防火墙和 SSH 授权，恢复 Tailscale；删除临时香港 ECS、专用安全组、一次性 SSH 密钥及本次中继 grant。保留独立测试 tailnet 的既有设备及其他策略。
测试中继 ECS 已释放；Tailscale 管理页仍保留 `hk-peer-relay-test` 节点登记，相关中继 grant 已移除。

## 新加坡与印尼 ECS 至家中公网补测

2026-10-28 悉尼时间，使用临时阿里云 ECS 分别向家中公网 IP 发送 30 次 ICMP，新加坡 29/30 成功、平均 409.812 ms、最大 446.850 ms；印尼（雅加达）30/30 成功、平均 415.396 ms、最大 449.673 ms。两轮先后进行，30 包样本不足以区分性能；这是 ECS 公网测试，不是 GA 终端节点回源、吞吐或端到端 WireGuard 测试。两台临时 ECS 已删除，专用网络的删除 API 已成功；未创建 EIP。

## 香港 GA UDP → OCI → 家中 WireGuard 对照

2026-10-28（悉尼时间）使用香港 GA 普通 BGP 接入、香港终端节点组，经公网回源悉尼 OCI，再由既有 OCI→家中 WireGuard 转发 UDP 到 VM500 的临时 WireGuard peer；没有使用新加坡终端组。中国 Windows 对照家中公网 endpoint，使用同一临时密钥、VM502、MTU 1280、PersistentKeepalive 15 秒。两组先后测试，且公网 endpoint 的本机路由均选中 Clash/Meta TUN，故直连是连接家中公网 endpoint，并非绕过 Clash 的物理直连。

| 指标 | 香港 GA→OCI→家中 | 家中公网 endpoint 直连 |
| --- | ---: | ---: |
| 握手 / SSH | 成功；30/30 | 成功；30/30 |
| SSH 中位数 | 199.538 ms | 339.344 ms |
| SSH P95 | 207.377 ms | 973.670 ms |
| SSH 最大值 | 207.791 ms | 973.683 ms |
| 无 SSH 会话 60 秒后重连 | 成功 | 成功 |
| 2 MiB SFTP 上传 | 7.862 s / 2.134 Mbps | 20.957 s / 0.801 Mbps |
| 2 MiB SFTP 下载 | 22.498 s / 0.746 Mbps；SHA256 一致 | 45 秒超时，未完成 |

速度按完整文件大小除以整个 SFTP 会话时间计算，包含连接开销，不是持续吞吐。空闲重连期间 WireGuard 仍以 15 秒 keepalive 工作，不代表完全无 UDP 流量时的重连；未测更大 MTU。用户自行安装 Windows WireGuard，测试临时密钥、Windows 隧道、OCI 受限 NAT 与 NSG、VM500 临时规则及 GA 测试实例均于测试后删除。

## 低延迟接入路径与协议候选（2026-10-28）

核心目标是以可接受成本降低中国员工到家中 VM 的端到端交互延迟，并减少持续卡顿和高延迟尖峰。SSH 或桌面是承载业务的方式；不能把桌面功能、客户端便利性或产品数量作为方案筛选的首要依据。以下新增桌面及 Argo 组合尚未实测。

比较对象首先是完整网络路径：香港 ECS 中转、香港 GA 经 OCI 到家中、Cloudflare Argo，以及其他提供更优跨境中继路径的服务。桌面方案只有在能利用较好的网络路径，或能在相同路径下实测降低交互响应耗时时，才有优先验证的理由。

评价指标以同设备到同一 VM 的应用交互中位数、P95、尖峰频率和失败率为主，同时记录外层路由、丢包及成本。桌面必须测输入到对应画面更新的耗时，SSH 测输入到对应标记返回的耗时；不能拿入口 TCP 建连耗时替代全程交互时延，也不能用不同设备和时段的数据直接判定优劣。分开核对网络往返与代理、缓冲、编码解码及排队的额外耗时。

用户同意把 Guacamole HTTP Tunnel＋Cloudflare Access＋Tunnel＋Argo Smart Routing 记录为候选，同时继续比较远程桌面方案；本节为研究记录，不代表已批准实施或已经验证提速。员工端不安装 WARP。

### 候选 A：浏览器 → HTTP Tunnel → Guacamole → RDP/VNC/SSH

路径：员工浏览器 HTTPS → Cloudflare Access／Argo → Cloudflare Tunnel 的 HTTP 服务 → 家中 Guacamole → 员工专属 VM 的 RDP、标准 VNC 或 SSH。Guacamole 本身支持完整远程桌面，并非仅提供终端。

必须让交互数据使用 Guacamole 的 HTTP Tunnel；默认 WebSocket 模式不能因开启普通 Argo 而获得加速。HTTP 模式具备进入普通 HTTP 加速路径的协议基础，但 Cloudflare Tunnel＋HTTP 流式会话能否实际被 Smart Routing 优化，以及净收益，均未验证。Guacamole 官方提醒回退 HTTP 可能降低性能，代理还必须关闭响应缓冲并绕过会话缓存。

优先考虑 Guacamole＋xrdp 作为 Linux 桌面验证组合；标准 VNC 可作为对照。KasmVNC 官方明确不兼容标准 RFB，不能假定 Guacamole 能直接连接 KasmVNC 的现有服务。

最小对照：同一中国设备、同一 VM 与桌面负载，分别测 Guacamole WebSocket／Argo 关闭、HTTP Tunnel／Argo 关闭、HTTP Tunnel／Argo 开启。记录真实传输协议、Cloudflare 路由证据、输入到画面响应、画面更新、流量和断线恢复。先证实路由生效，再判断是否值得使用 HTTP。

### 其他桌面候选

| 方案 | 适用方向 | 普通 HTTP Argo | 主要限制 |
| --- | --- | --- | --- |
| 原生 RDP 客户端 → 安全网关 → Linux xrdp | 日常开发桌面、文本和剪贴板 | 原生 RDP 不适用 | 仍需优化跨境路径；按设备授权并固定目标 VM，不直接公开各 VM 的 RDP 端口 |
| NoMachine 原生客户端／NX | 比较专用远程桌面的编码和 TCP/UDP 体验 | 不直接适用 | 必须实测；当前 v10 服务端需商业许可，不能按历史免费版估算成本 |
| RustDesk＋自建中继 | 简单客户端接入和自主选择中继位置 | 原生 TCP/UDP 不适用，WebSocket 也不适用 | 须验证无显示器 Linux 会话、设备隔离和中继流量成本；自建中继不自动获得优化线路 |
| Amazon DCV 原生客户端／QUIC | 高延迟、丢包环境下的桌面协议对照 | QUIC 和 WebSocket 均不适用 | 家中部署需要许可；UDP、编码资源和实际改善均需验证 |
| KasmVNC／noVNC 浏览器访问 | 保留浏览器桌面使用方式 | WebSocket 数据不适用 | 网页走 HTTPS 不等于桌面数据获得 Argo 加速；WebRTC 媒体也不能据此判定可加速 |

Microsoft RD Gateway 虽使用 HTTPS，但协议含 RDG_IN_DATA／RDG_OUT_DATA 自定义方法；未验证普通 Cloudflare HTTP 代理及 Argo 兼容性，不把它列作已确认的低成本 Argo 路径。

候选优先级以实测端到端延迟和成本决定。香港 ECS 与 GA 的既有测量用于参考；Argo 需要验证实际 Smart Routing 路由收益能否超过 HTTP Tunnel 及网关增加的耗时。Guacamole HTTP 是验证 Argo 的协议适配候选，原生 RDP、NoMachine、RustDesk 和 DCV 暂列协议备选，不能仅因桌面体验或编码能力就优先部署。若某远程桌面服务自带较好的跨境中继，应把其完整路径作为独立候选测试，不能仅按软件名称推断速度。远程桌面可改善编码和操作方式，但不能消除物理 RTT；滚动、视频画面通常也比纯终端消耗更多带宽。

资料：

- [Cloudflare WebSocket 与 Argo 不兼容](https://developers.cloudflare.com/network/websockets/)
- [Guacamole 支持 RDP、VNC、SSH](https://guacamole.apache.org/)
- [Guacamole 反向代理、HTTP 回退与缓冲要求](https://guacamole.apache.org/doc/gug/reverse-proxy.html)
- [xrdp 官方项目](https://github.com/neutrinolabs/xrdp)
- [KasmVNC 不兼容标准 RFB](https://www.kasmweb.com/kasmvnc/docs/latest/index.html)
- [NoMachine UDP 性能需要实际环境验证](https://kb.nomachine.com/AR01M00832)
- [NoMachine v10 服务端许可变化](https://kb.nomachine.com/AR03P00972)
- [RustDesk 自托管协议和中继](https://rustdesk.com/docs/en/self-host/)
- [DCV WebSocket 与 QUIC](https://docs.aws.amazon.com/dcv/latest/adminguide/disable-quic.html)
- [DCV 许可要求](https://docs.aws.amazon.com/dcv/latest/adminguide/setting-up-license.html)
- [RD Gateway 连接协议](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-tsgu/f4de010f-ee2b-4f6f-bf26-7792ac1b38e4)

## xTom 悉尼、东京 Premium 与现有香港 ECS 同轮筛选

2026-10-28 01:44–01:49（悉尼时间；UTC 为 10 月 27 日 14:44–14:49）。中国 Windows 已关机，按用户要求创建临时河源 ECS 作为国内阿里云出口探测源，同时使用家中 Mac 和现有悉尼 OCI。河源云网络不能代表员工电信、联通或移动家宽。本轮没有部署 RustDesk 或候选节点中继，测量的是公共测试 IP 的网络分段。

目标由官方 Looking Glass 域名的当时 IPv4 解析确认：xTom 悉尼 `syd.lg.xtom.com` → `146.19.0.4`；东京 Premium `tok-premium.lg.xtom.com` → `45.94.40.13`。香港为现有员工 ECS 普通 BGP EIP `47.238.205.238`，不使用已释放的旧 Pro EIP。

主对照在三处来源均使用相同 TCP 80：每目标 30 次新连接，轮换目标顺序交替探测，连接超时 3 秒，不包含 TLS、HTTP 内容、SSH 登录或桌面编码。各源末次样本 UTC 时间为 OCI 14:48:44、河源 14:48:58、Mac 14:48:59；三处采样窗口重叠。此前另测了 Looking Glass TCP 443 与香港 TCP 80，因端口不同，只作预检，不混入主表。

表内为中位数 / P95，单位 ms；九组 TCP 均成功 30/30：

| 来源 | xTom 悉尼 | xTom 东京 Premium | 阿里云香港 ECS |
| --- | ---: | ---: | ---: |
| 河源 ECS | 244.694 / 1282.090 | 62.773 / 65.929 | 17.762 / 21.491 |
| 家中 Mac | 6.724 / 62.642 | 271.030 / 348.730 | 401.480 / 1412.627 |
| 悉尼 OCI | 1.284 / 1.535 | 101.015 / 101.212 | 153.410 / 233.240 |

家中 Mac 到三个目标的选中路由均经 `en0`、网关 `192.168.1.1`；OCI 均经 `enp0s6`、默认网关 `10.0.0.1`，未选中 WireGuard 接口。探测使用固定目标 IPv4 和原生 socket，不经过 HTTP 代理。

补充 ICMP：河源到悉尼 29/30，平均 244.596 ms、最大 248.865 ms；到东京 30/30，平均 61.503 ms；到香港 30/30，平均 17.299 ms。河源到悉尼的 TCP 80 最大 1301.737 ms，预检 TCP 443 最大 1279.602 ms；两种 TCP 探测均见约 1.3 秒尖峰。单次 ICMP 丢包和这些尖峰不足以单独确认丢包根因。

### 对完整接入路径的意义

- **悉尼中继直接到家中**：河源→悉尼约 244.7 ms，家中→悉尼约 6.7 ms；两段中位数相加约 **251.4 ms**，且第一段有尖峰。此次未体现优于现有香港入口的潜力。
- **东京→OCI→家中**：河源→东京约 62.8 ms，OCI→东京约 101.0 ms；到 OCI 的两段估算约 **163.8 ms**，之后再走既有 OCI→家中路径。
- **香港→OCI→家中**：河源→香港约 17.8 ms，OCI→香港约 153.4 ms；到 OCI 的两段估算约 **171.2 ms**，之后走相同的 OCI→家中路径。

后两条的估算中位数相差约 **7.4 ms**，不足以判定东京值得替换现有香港 ECS。东京与 OCI 的这组分段数据比香港更稳定，可保留为减少尖峰的候选；必须实际建立中继后再验收。不能相加分段 P95 得到端到端 P95。

上述求和仅用于筛选：使用了反方向的同轮 RTT、公共测试端口及不同主机，未验证真实转发路径和协议开销，不是端到端 SSH／桌面测量。家中直连香港约 401 ms 不能当作现有香港员工入口的时延，因为该入口通过 OCI 回家。东京直接回家同样偏慢，若继续验证，应明确与“东京经 OCI”区别。Looking Glass 网页当前返回 403，本轮未取得反向诊断或有效文件下载吞吐。

### 资源与证据

河源探测机 `i-f8zchzqeihtuqye8vkj6`，公网 `47.113.207.156`，Ubuntu 24.04、`ecs.e-c1m1.large`、20 GiB 系统盘、实例自带公网 IP、按流量出网，未创建 EIP。使用独立 VPC、vSwitch、安全组；未开放入站管理端口，命令经阿里云云助手执行，未安装额外软件。已设置两小时自动释放作为兜底；测试后立即删除，并经 API 确认实例、独立 VPC、vSwitch、安全组均已不存在，两条临时云助手命令亦已不存在。

原始逐次 TCP 数据、ping 输出、云助手结果和资源清理记录保存于本机 `/private/tmp/relay-lg-screen-20261028/`。本次只筛选 xTom 悉尼、东京 Premium，未测试 DMIT。正式购买仍需核对套餐与测试网络是否一致。

## 腾讯 GA 2.0 普通 BGP 对照：账号开通预检

2026-10-28（悉尼时间），用户授权测试腾讯 GA 2.0 香港普通 BGP，并允许安装腾讯云 CLI。通过 uv 独立工具环境安装官方 TCCLI 3.1.190.1，使用 `tccli auth login --profile ga-test` 完成官方浏览器授权；没有要求用户配置长期 SecretId／SecretKey。凭据仅保存在本机私有目录，权限已收紧为 0600。

只读查询 `DescribeGlobalAccelerators` 成功且实例数为 0；`DescribeAccelerateRegions` 返回香港 BGP 和 QUALITY_BGP 可用。该产品的全局查询不应传 `--region ap-hongkong`，传入会返回 Region 无效；地域列表显示可用不等于账号已获创建权限。

按已授权范围尝试创建临时按量实例 `iac-ga2-hk-bgp-test-20261028`，返回 `UnsupportedOperation.CurrentAccountNotAllowed`，RequestId 为 `9a47cb57-a4b4-4c49-9775-3cb6f3bfa2e3`。随后只读复查实例列表仍为空；未启动河源探测机。Firefox 已登录控制台，创建入口跳转 `https://buy.cloud.tencent.com/ga2` 后显示“全球加速2.0尚未对外开放”。[官方实例类型说明](https://cloud.tencent.com/document/product/1817/128971)注明 GA 2.0 需提交工单申请灰度。

当前尚无腾讯网络性能数据，不能把地域列表、控制台可见或登录成功当作测速完成。需由腾讯开通灰度后，继续验证香港普通 BGP→既有 OCI→家中路径，并明确河源云出口与员工家宽的差异。此次预检没有创建腾讯 GA 实例或河源计费资源。

随后用户批准向腾讯提交灰度申请。控制台现场核实已存在同名工单 [202610288902](https://console.cloud.tencent.com/workorder/detail?ticketId=202610288902)，状态为“处理中”，腾讯工程师已接手；批准的用途、错误码和 RequestId 补充说明也已出现在该工单对话中。未重复建单或重复发送，等待腾讯开通权限后继续测试。
