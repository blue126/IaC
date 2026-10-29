# VM502 Guacamole SSH 验证方案

结论：**Guacamole over Argo 方案已验证不可行，停止该方案。** 本文保留验证记录与失败结论；试点已撤销，两个测试入口及账号均已失效。 用户同意转入 HAPI 单人试点；本次先完成清理，HAPI 尚未安装。下文保留测试与决策历史，不代表当前仍有 Guacamole 服务。2026-10-29 更新。

## 退役核对结果

- VM502 上本试点 5 个容器、专用 Docker 网络和 4 个镜像已删除；部署目录 `/opt/guac-ssh-pilot/`、含私钥的 XML／备份／连接器令牌、OSC 会话辅助文件及 VM 临时检查文件均已删除，18080 不再监听。
- 专用系统账号与目录 `guac-test` 已删除；employee 授权文件仅移除本轮两条测试公钥，SHA256 恢复为试验前基线 `e0507b2907592039264e1f19fd1c261c9db85d47184d7d93db721d8d686c3080`。employee `.bashrc` SHA256 仍为 `342099da4dd28c394d3f8782d90d7465cb2eaa611193f8f378d6918261cb9bb8`，没有覆盖员工 shell 配置。
- 仅在确认 VM502 没有其他 Docker 容器、镜像、卷或自建网络，并核对 apt 安装历史及 purge 模拟后，卸载本任务安装的 `docker.io`、`docker-compose-v2` 及同事务新增的 7 个自动依赖（bridge-utils、pigz、containerd、ubuntu-fan、dnsmasq-base、runc、dns-root-data）；清理对应 Docker／containerd 数据和 Docker 默认网桥。没有运行全局 prune／autoremove。
- Cloudflare 两条 DNS 记录 `guac-ssh-test.willfan.me`／`guac-demo.willfan.me`、Access 应用 `Guacamole VM502 HTTP pilot`、专用 Tunnel `guac-ssh-pilot-20261028` 已删除；API 复核该试点的 DNS、应用、有效 Tunnel 与 Service Token 均无残留。没有修改 Argo 订阅或其他应用。
- 中国测试节点只删除本任务标记的 Hosts 行、对应备份及 `/tmp/guac-cfst-20261028/` 扫描运行时；没有覆盖整份 Hosts 或修改全局 DNS。
- 管理机上含口令的 8 份接入／邮件草稿／预览文件已删除。测试报告、发送回执、Claude 咨询原文及 UI 选型源码快照保留；未向测试者自动发送新通知。
- VM502 管理 SSH 仍正常。核对报告位于管理机 `/private/tmp/guac-vm502-pilot-bv4_nigo/guacamole-retirement-report.json`（0600）。后续 HAPI 需独立部署和验收，不能把旧 Guacamole 结果当作其验证。

**用户随后明确批准了专用 Cloudflare 基线接入（应用、Tunnel、DNS、临时机器认证及 VM502 连接器）。Argo 已准备到最终付款页，但用户选择先做 IP 优选，尚未在本任务中完成付款开通；本轮不操作其开关。下文原完整方案仅作背景，以本节最新记录为准。**

## 当前批准的精简步骤

### 新增接入要求：员工应能使用本地 IDE 连接本人 VM

2026-10-29，用户明确要求员工应被允许使用本地 IDE 连接本人 VM。将 VS Code Remote-SSH 等 IDE 远程开发接入作为正式能力要求；现有网关的 `DisableForwarding yes`、禁止转发与固定命令分发属于需要适配的实现边界，不作为拒绝该用户能力的理由。

后续接入设计应按员工／设备身份绑定本人 VM，允许 IDE 引导、远端执行与其所需的受控通信；保留跨员工 VM 的网络与身份隔离。Claude 的执行、个人凭据和认证仍留在澳洲 VM，不能以本地 IDE 界面代替运行位置与请求路径的核验。该要求不等于已完成 IDE 接入，也不授权直接将生产网关改为无目的地限制的通用转发。

当前只记录能力要求，未安装 IDE 服务、修改生产网关或改变员工设备包；后续具体接入实现与一个人的试点范围需形成可审阅方案。

用户随后明确：工作区留在澳洲是物理限制，排除迁移到近端地域；本地 UI＋远端 Claude 可以研究，但不能强制使用其认为过重的 VS Code。后续优先研究浏览器本地聊天输入界面／轻客户端，后台在本人澳洲 VM 中运行官方 Claude Code CLI；不要把这种 UI 与 Guacamole 远端终端画面混为一谈。

当前调研候选为 HAPI 的免费 Web/PWA、自托管 CloudCLI UI（原 Claude Code UI），以及 Happy 原 CLI 配合 Web／移动端。各项目公开文档支持官方 CLI 的远程界面形式；实际订阅凭据复用、请求位置、权限审批和资源占用仍需在试点确认，不以项目介绍替代验证。该调研尚未安装任何候选，未改变员工认证或接入配置。

### 原 Guacamole 试点步骤

1. 只在 VM502 安装 Docker，运行 Guacamole、guacd、Nginx 三个容器。运行时文件位于 VM502 的 `/opt/guac-ssh-pilot/` 和管理机任务临时目录；不新增仓库目录。
2. guacd 固定地址 `172.31.250.10`，经专用 Docker 网桥网关 `172.31.250.1:22` 连接 VM502 本机 sshd；网段已核对无冲突。
3. Web 仅监听 `127.0.0.1:18080`，通过现有管理 SSH 转发访问，拒绝 WebSocket 升级以验证 HTTP Tunnel。
4. 标准验收：`hostname`、`id -un`、标记输出，打字、退格、Ctrl-C 正常；成功后停止，不自动创建公网入口或修改 Argo。
5. 客户端优先级：**中国 Linux 节点 `root@192.168.8.1` 首选**，通过管理机 SSH 下发命令，替代 Windows 远程 Codex 通道；河源 ECS 备用，不提前创建。浏览器交互验收仍需要真实浏览器，不能用 curl 连通结果代替。

### 本轮执行记录

- VM502 身份核对为 `employee-control`，SSH 管理转发允许；本机授权文件基线 SHA256 为 `e0507b2907592039264e1f19fd1c261c9db85d47184d7d93db721d8d686c3080`。
- 已按批准安装 Ubuntu 仓库的 Docker 29.1.3 和 Compose 2.40.3，使用 Guacamole／guacd 1.6.0 和 Nginx；没有新增仓库目录。
- 用户明确批准本次临时密钥例外：RSA 3072 PEM 私钥只在 VM502 的受限运行时目录生成和使用；公钥通过 `from="172.31.250.10",restrict,pty` 限制来源与能力，未注册新设备或生成 WireGuard 密钥。
- 已通过管理 SSH 转发和原生 Firefox 实际进入 VM502 SSH：`hostname` 返回 `employee-control`，`id -un` 返回 `employee`，标记输出、输入、退格正常；Ctrl-C 立即中断 `sleep 300`。
- 已验证实际 HTTP Tunnel 读写。代理日志累计记录 WebSocket 请求 3 次 404、HTTP Tunnel GET 534 次 200 和 POST 3791 次 200；没有成功的 WebSocket 升级。自动协议验证同样确认主机、用户、标记、退格、Ctrl-C 全部通过。
- SSH 主机身份通过宿主机已核对的 RSA／ECDSA／Ed25519 公钥写入 guacd 的只读 `ssh_known_hosts` 校验，没有关闭主机密钥验证。
- 验证结束已停止三容器及管理 SSH 转发；删除一次性私钥文件及 XML 内的私钥副本，撤销临时授权，`authorized_keys` SHA256 与上述基线完全一致。本机临时 Web 口令副本也已删除。Docker、镜像和 VM502 的测试配置保留，尚未创建公网入口。
- 用户确认中国 Windows 已开机并设为首选；当前远程 Codex 主机通道返回不可用，尚未向该主机发送测试指令。河源 ECS 保留为备用，没有创建 ECS。
- 随后用户提供中国 Linux 节点 `192.168.8.1` 并亲自安装管理机公钥。已以 `BatchMode=yes`、严格主机密钥校验成功免密登录：OpenWrt 21.02-SNAPSHOT、Linux 4.4.60、ARMv7、root；有 curl／wget／ping／traceroute／ip，没有发现 Python3／Node。默认路由为 `pppoe-wan`，尚未核实透明代理或策略路由。后续中国侧命令测试改用该节点，不经 Windows Codex；未安装软件、修改节点网络或运行性能测试。

本轮原生浏览器截图：`/private/tmp/guac-vm502-pilot-bv4_nigo/guacamole-firefox-verified.png`。VM502 受限目录内保留 `verification-result.json`、`cleanup-result.json` 和不含认证查询参数的代理日志。

验证中的差异：内置浏览器的自动化按键没有传出 Ctrl-C，已用原生 Firefox 验证功能正常，未把命令自然结束算作成功。Ubuntu 的 OSC 提示符标记在当前测试 shell 内临时清除，未修改员工的 shell 配置。当前结论仅为本机功能通过；**未证明中国侧 Guacamole 延迟或 Argo 加速收益**。下一步先审核具体 Cloudflare 接入变更，再安排中国 Linux 命令测试及真人浏览器验收。

### 中国 Linux 旁路网络探测（2026-10-28，不作为 Argo 对照基线）

纠正：此前将这些测量称作“基线”不准确。香港 ICMP 与 OCI HTTP 使用不同目的地及协议，无法回答 VM502 的 Guacamole 经 Argo 是否提速；仅保留为节点连通性和旁路网络记录，不用于评价方案优劣。

用户确认真人稍后验收浏览器，本轮先测延迟和 HTTP。所有请求从 `192.168.8.1` 执行，使用现有 curl 7.82.0，`--noproxy '*' -4`；未安装软件或改变路由。两个目标的路由查询均为 `pppoe-wan`，OUTPUT 链没有观察到请求重定向；存在 Tailscale 和按进程组标记的策略规则，故不将“未设置代理环境变量”单独当作直连证据。

| 测项 | 样本与结果 | 耗时 |
| --- | --- | --- |
| 香港 `47.57.14.220` ICMP | 20/20 回复 | 平均 23.190 ms，最大 23.616 ms |
| 香港旧 HTTP 探测端口 80 | 连接被拒绝 | 不统计 HTTP 延迟，不重新开放服务 |
| OCI `159.13.46.201` ICMP | 0/20 回复 | 不据此判断网络丢包；同 IP 的 HTTPS 可达 |
| OCI HTTPS 新建连接 | 20/20 HTTP 200 | TCP 中位数 325.9 ms；首字节中位数 1083.2 ms，最大 2358.5 ms |
| OCI HTTP 新建连接 | 20/20 HTTP 308，未跟随跳转 | TCP 中位数 325.4 ms、最大 1333.6 ms；首字节中位数 654.4 ms |
| OCI HTTPS 连接复用 | 首次连接后 19/19 HTTP 200，`num_connects=0` | 首字节中位数 327.2 ms，最大 3076.8 ms；其中 3 次超过 500 ms |

HTTPS 固定 `--resolve proxy.willfan.me:443:159.13.46.201` 并正常验证 TLS；HTTP 使用相同 Host。每次新建连接的首字节包含握手，不能当作持续会话 RTT。复用连接可以省掉反复握手，但仍观测到尖峰；短时间少量样本不能推定长期 P95，也不能定位尖峰来源。香港与 OCI 为不同目的地，此表不能证明任一完整中继方案胜出。

原始 CSV、错误日志、ping 结果及统计 JSON 位于管理机 `/private/tmp/guac-vm502-pilot-bv4_nigo/china-linux-*`。本轮没有访问 Guacamole 公网入口，也没有验证 Cloudflare 或 Argo 的端到端耗时。

### 正式 HTTP 对照方法

固定中国 Linux 节点、同一域名与请求路径、同一 VM502 源站、响应内容、认证、缓存策略及 HTTP 协议模式。A 组为 Cloudflare Tunnel 路径且确认 Argo 关闭；B 组保持其他配置一致，仅开启 Argo。采用 A／B／A 多轮短批次降低时间波动影响，并记录实际开关与源站响应证据；开关或付费变更仍须授权。

主要比较连接复用后的动态 HTTP 请求首字节中位数、尾延迟、超时与尖峰；冷连接的 TCP／TLS 建立耗时单列。响应必须确实到达 VM502，不使用缓存命中、Access 登录页或不同目的地作替代。HTTP 测量只能说明请求响应延迟，Guacamole 终端的实际交互延迟仍由后续真人及会话测试验证。

### 本轮已批准并实施的最小接入

用户明确批准整组接入后，在 VM502 增加官方 cloudflared 2026.10.5 容器，镜像固定为 `sha256:1b1d34d0a9c0bfca9de72db8460d328db3f19edd2b96169114e3e893a97bbe53`；其出站固定 HTTP/2，连接 Cloudflare 悉尼节点。沿用 loopback Web，不开放家庭公网端口；连接器校验 Access JWT 的本应用 audience。只测 Web HTTP，没有重新生成 SSH 密钥。

| 对象 | 标识／当前状态 |
| --- | --- |
| Access 应用 | `Guacamole VM502 HTTP pilot`／`fba6f6ee-65db-4945-a654-26913bac45ae` |
| Tunnel | `guac-ssh-pilot-20261028`／`7c3c9c76-5820-41c5-9502-5a2d7a995764`，healthy |
| DNS | `guac-ssh-test.willfan.me`，记录 `8b11311a01c987f9c5910549177bba90`，代理 CNAME 指向本 Tunnel |
| 人工访问 | 仅 `[邮箱已脱敏]`，会话 1 小时；未认证访问返回 302，进入 Access 登录 |
| 临时 curl 认证 | 仅本测试令牌的 Service Auth 策略；测试结束已删除策略和令牌，中国节点配置及本地副本已清除 |
| SSH | 首轮临时密钥已撤销；当前公网阶段仅确认 HTTP，不声称真人 SSH 验收完成 |

读取连接器令牌时曾因结果解析失误回显到工具记录。已取得用户仅轮换本 Tunnel 密钥的明确批准，成功轮换并确认新旧令牌不同；新令牌只保留于 VM502 的受限连接器文件，不含于 Git、进程参数或本报告。

### AMS 路径测量结果：Cloudflare Tunnel，Argo 未启用

控制台现场显示 `willfan.me` 当前套餐为 Smart Shield Free，Smart Shield + Argo 未选；证据截图为 `/private/tmp/guac-vm502-pilot-bv4_nigo/argo-baseline-plan.png`。Argo API 返回未授权，因此采用控制台核验，未更改套餐或开关。

固定测试路径：**中国 OpenWrt `192.168.8.1` → HTTPS `guac-ssh-test.willfan.me` → Access → Cloudflare Tunnel → VM502 Nginx → Guacamole API**。请求 `/guacamole/api/languages?pilot_nonce=<每次唯一值>`，IPv4、HTTP/1.1、`--noproxy '*'`、正常 TLS 验证。响应为实际 Guacamole 的 258 字节 JSON，而非 Access 登录页；源站附带唯一请求 ID 和 `Cache-Control: no-store`。

| 指标 | 结果 |
| --- | --- |
| 请求 | 3 轮 × 21 次，63/63 HTTP 200，全部 `X-Pilot-Origin: vm502`、`CF-Cache-Status: DYNAMIC` |
| 源站证据 | 63 个响应请求 ID 全部与 VM502 Nginx 日志对应 |
| 连接复用 | 每轮首个连接单列，60 次复用请求；首字节中位数 **589.4 ms**，P95 **861.6 ms**，最大 **1382.4 ms** |
| 完整响应 | 60 次复用请求，总耗时中位数 596.1 ms，P95 1272.6 ms，最大 1599.1 ms |
| 分轮首字节中位数 | 623.4／587.2／561.4 ms |
| 尖峰 | 复用请求中 3/60 首字节超过 1 秒，没有超过 2 秒；本轮无超时 |
| 冷连接 | 仅 3 个样本，首字节中位数 1943.5 ms，最大 4528.0 ms；不与持续会话混算 |
| VM502 处理耗时 | Nginx 日志中位数 9 ms、最大 22 ms；此处不是跨境往返时间 |
| Cloudflare 处理节点 | 全部响应 `CF-Ray` 后缀 `AMS`，远端地址 `104.21.32.136`；连接器在悉尼。仅据此记录处理节点，不当作完整 traceroute |

这是短时 HTTP 请求基线，不能等同于逐字终端回显，也未测出 Argo 净收益。相同条件下的 Argo 开启组须另获批准，后续保持源站、协议、请求内容和缓存策略一致。

### AMS 路径复核及适用范围

用户指出 AMS 路径会影响基线代表性。复核未改动网络配置，也未启用 Argo：

- 中国节点访问本域 `/cdn-cgi/trace` 返回 `loc=CN`、`colo=AMS`，该诊断接口由 Cloudflare 自身响应，无需经过 VM502 应用。节点到两条目标 IPv4 的路由均经 `pppoe-wan`。
- 本机所用 DNS（Tailscale DNS）与直接查询阿里 `223.5.5.5`、腾讯 `119.29.29.29` 的结果一致，均为 `104.21.32.136` 和 `172.67.152.76`。只查询，不修改 DNS 配置。
- 分别用 `--resolve` 固定这两个已公布 A 记录，保留原域名与正常 TLS 校验，各测 5 次，全部 `colo=AMS`。因此本轮更换这两个地址或上述 DNS 没有得到亚洲入口。
- 同一节点访问 `www.cloudflare.com/cdn-cgi/trace` 为 `colo=LAX`；此项仅用于诊断不同前缀的路径差异，不与 Guacamole 的请求耗时比较。
- 节点没有可用的目标 IPv6 路由，IPv6 HTTPS 未连接成功。现有 BusyBox traceroute 不支持 TCP 模式，未安装新工具，未据此虚构逐跳 HTTPS 路由或归因到某一运营商。

589.4 ms 是此时这条 AMS 路径的实测值；不得作为“亚洲就近接入 Cloudflare”的基线，也不得据此承诺普遍性能。后续 A/B 须记录并核对来源网络、目标地址及处理节点；如果改用自然进入亚洲的用户网络或路径，必须重跑关闭 Argo 的 A 组，不能沿用这批数值。当前先保留 AMS 样本，不开 Argo；真人测试前先通过同域 `/cdn-cgi/trace` 核对 `colo`，只反馈该字段即可，无需发送公网 IP。

### 就近 PoP 引导的有限探测

Cloudflare 官方明确不能按域名、账号或支持请求固定接入数据中心；Anycast 入口受运营商路由与互联策略影响。来源：[Cloudflare geographic traffic routing](https://developers.cloudflare.com/support/troubleshooting/general-troubleshooting/geographic-traffic-routing/)。因此替换连接 IP 只能尝试影响路径，不能把一个 Anycast IP 视为固定的香港或东京节点。

在同一中国节点进行了 9 次小规模候选探测：候选均从 Cloudflare `/ips` 官方 IPv4 网段选取，使用 `curl --resolve` 保留本域名、SNI 和正常 TLS 验证，只请求 Cloudflare 自身 `/cdn-cgi/trace`；没有改 DNS、Hosts 或网络配置，没有重新建立机器认证。

| 候选 IP | 结果 |
| --- | --- |
| `104.16.0.1`、`103.21.244.1` | LAX |
| `104.24.0.1`、`188.114.96.1` | AMS |
| `103.31.4.1` | DEN |
| `172.64.0.1`、`162.158.0.1`、`198.41.128.1`、`103.22.200.1` | 3 秒建连超时 |

本轮未找到亚洲入口；单次样本只用于筛选方向，不作为稳定性证明或 Guacamole 源站性能结果。候选日志位于 `/private/tmp/guac-vm502-pilot-bv4_nigo/cf-pop-candidates.log`。后续可由真实员工的其他运营商网络验证自然入口，或另行评审从已验证能进入亚洲 Cloudflare 的出口中转；当前未实施中转，也不干预另一 worktree 的阿里云资源。

### DNS 切换对照

按用户要求，从中国节点逐次指定 8 个 DNS 地址查询本域：默认 Tailscale DNS `100.100.100.100`，WAN 下发的 `202.100.199.8`／`202.100.192.68`，阿里 `223.5.5.5`、腾讯 `119.29.29.29`、114 `114.114.114.114`、Cloudflare `1.1.1.1`、Google `8.8.8.8`。8/8 查询成功，IPv4 集合均为 `104.21.32.136`／`172.67.152.76`，IPv6 集合也相同，只有记录顺序可能变化。

另外使用 curl 的 `--doh-url https://dns.alidns.com/dns-query` 通过阿里加密 DNS 实际请求同域诊断页，正常验证 TLS，结果为 HTTP 200、`colo=AMS`，连接地址仍为 `104.21.32.136`。因此本轮更换解析器没有改变目标集合或获得亚洲入口；不能把公共 UDP DNS 查询成功单独当作绝无中间干预的证明，DoH 请求提供了额外交叉核对。本次未更改路由器全局 DNS、Hosts 或路由。日志及解析后的结果为 `/private/tmp/guac-vm502-pilot-bv4_nigo/cf-dns-comparison.log` 和 `cf-dns-comparison.json`。

### CloudflareSpeedTest 优选及 Hosts 落地

用户选择先执行优选 IP 方案，暂缓 Argo 付款，并明确批准本轮 2 小时临时 Access 探测凭据。使用官方 [CloudflareSpeedTest v2.3.5](https://github.com/XIU2/CloudflareSpeedTest/releases/tag/v2.3.5) ARMv7 Release，归档 SHA256 为 `73386234fe07a766071709859168e19b37f6878345317ccaa992efe35f4ef5f0`；在管理机和中国节点均验证一致。仅提取主程序到 `/tmp/guac-cfst-20261028/`，没有运行归档内的自动 Hosts 脚本，也未安装系统依赖。

从官方 15 个 IPv4 网段分散抽取 256 个独立地址，8 并发、每地址 2 次、关闭下载测速。首轮错误地要求诊断页返回 200，因工具使用 HEAD、Access 返回正常 302 而全部误判；已通过已知可达地址和 v2.3.5 源码核实并修正。有效筛选命令为：

```sh
GOMAXPROCS=2 ./cfst_linux_armv7/cfst -n 8 -t 2 \
  -httping -httping-code 302 -dd \
  -url https://guac-ssh-test.willfan.me/guacamole/api/languages \
  -f candidates.txt -o results-valid.csv -p 12
```

此处 302 只用于未认证入口的初筛，不能冒充源站测试。工具按其 2 秒 HTTP 超时等条件收录 52 个地址：26 LAX、15 AMS、8 SIN、3 DEN；其余未收录，不代表长期不可达。随后对默认地址、最快的两个 LAX 和三个 SIN 候选进行授权 GET 源站对照，每个 6 次，正常 TLS 校验、全部 200／DYNAMIC／VM502。快筛结果如下（复用请求仅 5 次，用于选候选）：

| 地址 | PoP | 源站首字节中位数 |
| --- | --- | --- |
| 默认 `104.21.32.136` | AMS | 598.5 ms |
| `104.17.70.47` | LAX | 453.1 ms |
| `190.93.247.78` | LAX | 460.8 ms |
| `108.162.193.205` | SIN | 809.2 ms |
| `162.159.5.203` | SIN | 547.4 ms |
| `162.159.11.167` | SIN | 808.7 ms |

不能按地理标签选择地址；SIN 候选没有胜过最佳 LAX。再对 `104.17.70.47` 做 A／B／A 源站复核，每组 21 次、首个冷连接单列，以下统计各 20 次复用请求。63 次均 200、无缓存、TLS 正常：

| 组别 | 地址／PoP | 首字节中位数 | P95 | 最大值 |
| --- | --- | --- | --- | --- |
| A1 | 默认／AMS | 588.7 ms | 902.5 ms | 1214.8 ms |
| B | 候选／LAX | **362.0 ms** | **672.8 ms** | **896.0 ms** |
| A2 | 默认／AMS | 608.8 ms | 1216.8 ms | 1268.8 ms |

本轮中位数改善约 40%。仅在中国测试节点 `/etc/hosts` 追加以下一行，没有重启网络、修改全局 DNS 或变更员工客户端：

```text
104.17.70.47 guac-ssh-test.willfan.me # guac-cfst-20261028
```

原文件备份为该节点 `/etc/hosts.guac-cfst-20261028.bak`。回滚时仅删除上述精确标记行；如果之后还有其他 Hosts 变更，不直接用备份覆盖整个文件。

Hosts 首次落地复核中出现 **1 次 TLS 冷连接超时**，随后的请求成功；该失败保留在证据中。补充默认、最佳候选、次优候选各 5 次交替冷连接，15/15 成功；最佳候选冷连接首字节中位数 1116.3 ms、最大 2401.2 ms，次优候选最大 6833.9 ms。最终不使用 `--resolve` 的 Hosts 验证 4/4 成功，均连接 `104.17.70.47`、LAX、真实 VM502、DYNAMIC；3 次复用请求中位数 412.1 ms。短时改善不保证长期稳定，也不等同于真人终端回显。

本轮授权源站探测共 125 次：124 次成功响应的请求 ID 全部与 VM502 Nginx 日志匹配，1 次为上述 TLS 超时。源站处理耗时中位数 8 ms、最大 16 ms。临时 Access 策略和令牌已删除，中国节点配置及管理机凭据副本已清除；含潜在认证会话头的原始响应也已删除。Hosts 生效后，未认证访问仍回到 Access 登录。Argo 尚未付款或激活。

经筛选的证据位于管理机 `/private/tmp/guac-vm502-pilot-bv4_nigo/`：`cfst-results-valid.csv`、`cfst-compare-summary.json`、`cfst-aba-summary.json`、`cfst-cold-summary.json`、`cfst-hosts-final-summary.json` 和 `cfst-origin-proof.json`。对应命令与逐请求脱敏样本同目录保留。

#### 处理节点标签与分段耗时的补正

此前对话有时把 `CF-Ray`／`colo` 标签直接称为“入口”，表述不严谨。[Cloudflare 官方说明](https://developers.cloudflare.com/support/troubleshooting/general-troubleshooting/geographic-traffic-routing/#my-traceroute-shows-traffic-entering-cloudflare-in-one-city-but-the-cf-ray-value-shows-another-why)指出实际入网位置与请求处理位置可以不同。本文的 AMS／LAX／SIN 是处理节点标记，不构成完整逐跳物理路径证据。

同批源站候选数据还显示：LAX 候选 `104.17.70.47` 的首次 TCP 建连约 224.5 ms、复用请求首字节中位数 453.1 ms；SIN 候选 `162.159.5.203` 分别为 58.3 ms、547.4 ms，`108.162.193.205` 为 94.0 ms、809.2 ms。单次 TCP 建连与复用中位数不能精确相减归因，但这些结果表明：亚洲候选的 TCP 建连较快，完整源站请求仍较慢，不能把优选结果解释为“中国到洛杉矶比到新加坡更快”。后续 Cloudflare 内部路由／处理与 Tunnel 往返可能产生差异，具体绕行点未核实，不声称已证明经美国等路径。

#### SIN 候选复测：2026-10-28 21:48–21:49 悉尼时间

按用户要求，将此前筛出的 8 个 SIN 候选全部重测。仍从 `192.168.8.1` 请求相同 Guacamole API，固定 IPv4、HTTP/1.1、正常 TLS 与 Access 认证，通过每次请求的 `--resolve` 指定候选地址；未更改 Hosts、DNS 或 Argo。当前 WAN 地址与午间批次不同，因此不直接套用旧数值，在开始、测完 4 个候选后和结束各插入一次当前 LAX 地址作为同期对照。

每组在同一连接执行 6 次 GET，首个冷连接单列，下表各统计 5 次复用连接的**完整 HTTP 响应耗时**（不是 SSH 回显）：

| 组别／地址 | 响应处理标记 | 中位数 | 最大值 |
| --- | --- | --- | --- |
| LAX 开始对照 `104.17.70.47` | LAX | 373.1 ms | 665.4 ms |
| `108.162.193.205` | SIN | 691.4 ms | 1852.4 ms |
| `162.159.5.203` | SIN | 688.6 ms | 754.8 ms |
| `162.159.11.167` | SIN | 573.2 ms | 585.3 ms |
| `108.162.196.227` | SIN | 720.6 ms | 941.1 ms |
| LAX 中途对照 `104.17.70.47` | LAX | 362.6 ms | 370.5 ms |
| `173.245.59.151` | SIN | 686.2 ms | 739.8 ms |
| `104.18.37.52` | SIN | **564.1 ms** | 683.4 ms |
| `108.162.196.193` | SIN | 694.1 ms | 1810.9 ms |
| `162.159.23.76` | SIN | 675.9 ms | 842.4 ms |
| LAX 结束对照 `104.17.70.47` | LAX | 366.5 ms | 1014.8 ms |

66/66 次均返回 HTTP 200、`X-Pilot-Origin: vm502`、`CF-Cache-Status: DYNAMIC`、TLS 验证通过；66 个响应请求 ID 全部匹配源站日志，源站处理耗时中位数 8 ms、最大 15 ms。本次采集从 10:48:22 到 10:49:14 UTC。SIN 各组中位数为 564–721 ms，仍慢于同期 LAX 的 363–373 ms；这是一次短时复测，每地址只有 5 次复用样本，不以此推定长期尾延迟或具体绕行原因。

本轮 2 小时临时 Access 策略、令牌及中国节点配置已撤销删除，本机凭据与潜在含认证会话头的原始响应已删除。Hosts 测前测后的 SHA256 均为 `d53d7f8cba73855daad5a8a11dce1f63ba044602765f38359f13dd9b02c2dedc`，继续保留当前 LAX 映射。脱敏证据为同一管理机临时目录下的 `sin-retest-targets.json`、`sin-retest-command.sh`、`sin-retest-samples.json`、`sin-retest-summary.json` 和 `sin-retest-origin.log`。

#### 香港／日韩台候选扩展筛选及东京复核

用户批准继续扩大香港、日本、台湾和韩国候选覆盖。新增 1024 个与前轮 256 个不重复的地址，仍从官方 15 个 IPv4 网段分散抽样，分两批各 512 个，并各加入现有 LAX／SIN 两个对照地址；两批顺序执行，8 并发、每 IP 两次 HTTPing、禁下载测速，保持 HEAD 302 筛选与 TLS 验证。未安装新工具、未修改 Hosts／DNS／网络配置，也未操作 Argo。IPv6 目标仍没有可用路由，本轮全部为 IPv4。

两批分别收录 118／97 条记录（含重复对照）。在本轮目标地区，只找到一个 NRT 处理标记候选 `172.64.52.8`，入口 HTTPing 约 88.92 ms；未筛出 HKG、KIX、FUK、OKA、TPE、KHH、ICN 等目标代码。此为有限抽样，不能证明这些地区没有服务节点或永远不可达。SIN 状态页此前仍列有维护公告，只将其作为潜在干扰因素，不确认它导致了本任务的延迟。

停止扫描后，东京地址通过 Access 授权 GET，返回真实 VM502 JSON、HTTP 200、DYNAMIC。首轮每组 6 次的小样本中，NRT 复用完整响应中位数 343.0 ms，LAX 前后对照为 381.9／368.4 ms，SIN 为 665.6 ms。随后继续做 LAX → NRT → NRT → LAX 确认，每组 21 次，首个冷连接单列，各保留 20 个复用样本。以下均为**到 VM502 的完整 HTTP 响应**，不是 SSH 或按键回显：

| 确认组 | 处理标记 | 复用样本 | 完整响应中位数 | P95 | 最大值 |
| --- | --- | --- | --- | --- | --- |
| LAX 第 1 组 | LAX | 20 | 378.7 ms | 1002.2 ms | 1274.4 ms |
| NRT 第 1 组 | NRT | 20 | 233.4 ms | 257.0 ms | 257.0 ms |
| NRT 第 2 组 | NRT | 20 | 200.4 ms | 263.4 ms | 406.0 ms |
| LAX 第 2 组 | LAX | 20 | 376.5 ms | 1684.2 ms | 2464.6 ms |
| **NRT 合并** | NRT | **40** | **202.5 ms** | **257.0 ms** | **406.0 ms** |
| LAX 合并 | LAX | 40 | 378.7 ms | 1274.4 ms | 2464.6 ms |

确认采集时间为 2026-10-28 22:27:20–22:27:56 悉尼时间（11:27:20–11:27:56 UTC）。本轮确认中位数 NRT 比 LAX 低约 47%，尾延迟也较低；但首个小样本与后续样本存在差异，不能据短时结果承诺长期稳定性，也不代表 Guacamole SSH 已达到相同回显速度。

首轮 24 次与确认 84 次共 108 次计时请求全部 HTTP 200、无缓存、正常 TLS、源站标记 VM502，108 个响应请求 ID 全部与 Nginx 日志匹配；源站处理耗时中位数 7 ms、最大 14 ms。本轮仅比较相同现有运行配置下的不同连接 IP，不能把收益归因于 Argo。

按本轮约定，**Hosts 没有改为东京**，仍保留 `104.17.70.47`；确认前后 SHA256 均为 `d53d7f8cba73855daad5a8a11dce1f63ba044602765f38359f13dd9b02c2dedc`。临时机器策略、令牌、中国节点配置及本机凭据已清除，含潜在认证会话头的原始响应已删除。候选及脱敏证据仍在管理机原任务临时目录：`asia-candidates-1.txt`／`asia-candidates-2.txt`、`asia-results-1.csv`／`asia-results-2.csv`、`eastasia-screen-summary.json`、`eastasia-confirm-summary.json`、对应命令和脱敏样本，以及 `eastasia-origin-proof.json`。后续若采用东京候选，仍需单独验证实际用户网络、逐键回显和长时间稳定性。

结果与经筛选的逐请求数据位于 `/private/tmp/guac-vm502-pilot-bv4_nigo/cf-baseline-summary.json`、`cf-baseline-samples.json`、`cf-baseline-origin.log`。包含潜在会话头的原始响应文件已删除。Web 与 Tunnel 保持运行，人工 Access 策略保留；未交付新的 SSH 身份或宣称终端已可公开验收。

### Cloudflare DNS 条目直接指定优选 IP 的验证

用户要求验证不依赖客户端 Hosts、直接修改 Cloudflare DNS 条目的做法。先备份测试域名的原始代理 CNAME，然后仅将同一条记录临时改为 `A 172.64.52.8`、`proxied: false`、TTL 60。原 Tunnel、Access 策略和连接器均未改动。

在管理机上使用相同域名、正常 TLS 和 `--resolve` 固定连接地址，以排除递归 DNS 缓存影响。更改前未认证请求返回 Access 登录重定向 HTTP 302；更改后连续三次均为 HTTP 403；恢复原始代理 CNAME 后重新返回 HTTP 302。TLS 校验始终成功。本轮没有建立临时认证或测量 VM502 性能；403 正文未进一步分类，不能将其写成已确认的 Error 1000。

已通过 API 恢复原 CNAME、目标、代理状态、TTL、注释、标签和设置，并查询权威 DNS 确认重新返回 `104.21.32.136`／`172.67.152.76`。客户端 Hosts 未变更。证据：原任务临时目录中的 `dns-tokyo-record-backup.json` 和 `dns-tokyo-probe.json`。

结论限于当前 Full Setup 与 Tunnel 配置：直接把承担 Tunnel 回源关联的 DNS 记录替换为优选边缘 IP，没有复现客户端 Hosts 覆盖的行为。客户端解析覆盖只改变连接地址，仍保留 Cloudflare 内部的原 Tunnel 路由；修改公开记录同时改变了后者。免 Hosts 的客户端 DNS 覆盖需要设备实际使用相应解析服务，不能说只改一条公开记录即可完成。

参考：[Tunnel DNS 路由](https://developers.cloudflare.com/tunnel/concepts/routing/)、[代理状态与 DNS-only 的区别](https://developers.cloudflare.com/dns/proxy-status/)。

### 张同学真人试点准备与邮件交付

用户批准恢复测试 SSH 并为 `[邮箱已脱敏]` 准备 bootstrap 邮件，明确要求确认内容后才发送。沿用本测试域名、VM502 和既有 Access／Tunnel，不运行员工常规开户、不改张同学个人 VM，也不生成或发放 VPN 设备包。

- Access 原人工 Allow 策略保留管理员邮箱，只追加张同学上述精确邮箱；没有添加全域名或 Everyone 放行。
- 沿用已批准的临时密钥例外，在 VM502 受限 runtime 中生成本轮专用 RSA 3072 PEM 密钥；授权限制为 `from="172.31.250.10",expiry-time="20261101120000Z",restrict,pty`。公钥指纹 `SHA256:fdkZC7ud03Zxscrcyswpuk5i6H24mCm/AqeM46TJeq4`，不交付给客户端、不进入 Git。SSH 授权到北京时间 2026-11-01 20:00 自动失效。
- Guacamole 新增独立网页登录账号 `zhang171903992`，只含 `VM502 browser SSH test` 一个连接。连接目标仍为 `employee-control`、Unix 用户 `employee`，不是张同学的个人 VM。网页登录口令与 SSH 私钥只存放受限运行时文件，邮件草稿包含临时网页登录口令，不包含 SSH 私钥。
- 重新执行现有 HTTP 协议功能验证，主机名、用户、标记输出、退格、Ctrl-C 全部通过；另以张同学凭据验证 API 登录及仅一个可见连接。自动验证后移除全部终端录制参数，真人会话不启用 typescript／图形录制。
- 从中国 Linux 节点固定 NRT 候选访问公网登录入口，三次均为正常 TLS、HTTP 302、CF-Ray 后缀 NRT。它只证明当前登录入口可达，不是认证后 SSH 性能或真人体验结果；没有改该节点 Hosts。
- 邮件以加粗带引号的 Agent 提示词开头，后用 bullet points 说明 Hosts、系统授权、Access、Guacamole 登录、固定测试命令和预期结果、输入体验与回滚。明确不运行旧 WireGuard bootstrap、不擅自修改现有 VPN／代理、本轮不登录个人 Claude 或上传个人项目。

私有邮件预览与草稿位于管理机原任务目录 `/private/tmp/guac-vm502-pilot-bv4_nigo/zhang-guacamole-mail-preview.html`、`zhang-guacamole-mail-draft.json`，均为 0600。对应草稿摘要为 `55f4577f47ab34b46da842c77392561c10ae4d71ae3582a2cdb7515b4ca6d20b`。用户确认“可发送”后，按该摘要校验的原内容调用微软 Graph `sendMail`，2026-10-28 12:37:09 UTC（悉尼 23:37:09）返回 HTTP 202。回执为同目录 `zhang-guacamole-mail-receipt.json`，请求 ID `5f75b61c-816b-4b8c-891e-357a3f10e076`；只证明接口已接受，不代表已确认到达收件箱。不将邮件正文、口令、私钥或个人设备包提交仓库。

试点结束的定向撤销对象：Guacamole 用户 `zhang171903992`、`guac-zhang-uat-vm502` 授权行及本轮私钥／XML 副本、Access 策略内追加的张同学邮箱。保留管理员权限与其余授权，不按旧文件整份覆盖用户的后续变更；当事设备上仅撤销本测试域名的 Hosts 映射。

### 第二位真人测试者（邮件已发送）

用户随后要求安排 `[邮箱已脱敏]` 一起测试。已在相同 Access 策略中仅追加该邮箱，保留管理员与张同学。Guacamole 新增独立网页登录账号 `ritsuka2020`，仍只连接 VM502 的 `VM502 browser SSH test`，未执行个人 VM 开户。

为其连接生成独立临时 SSH 服务密钥，按相同 VM502 runtime 例外管理；授权行标记 `guac-ritsuka-uat-vm502`，来源限 `172.31.250.10`，`restrict,pty`，到期仍为 `20261101120000Z`。公钥指纹 `SHA256:rTXD0nZ7eS+MwapOvjJc/ubQAnxbexmdAmWSoAmmVSA`。新账号通过相同 HTTP Tunnel 的主机名、用户、标记输出、退格和 Ctrl-C 检查；验证后移除该连接的录制参数。没有变更张同学的账号、口令或测试密钥。

邮件沿用已确认版本，替换收件人及其独立临时网页登录口令、Hosts 标记，提示词按首次接入编写，包含 Hosts 映射、标准 curl 命令、预期输出、网页 URL 和本人操作交接，不依赖 Agent 读取邮件正文，去掉“旧工作区 bootstrap”等老用户前提；正文说明先使用临时共用测试机体验浏览器终端。预览为管理机原任务目录 `ritsuka-guacamole-mail-preview.html`，草稿为 `ritsuka-guacamole-mail-draft.json`，均 0600；摘要 `12dafc69a11b794311d29db927982e98675a7bf8f6e1c4d9bce1a02500aa47bd`。用户确认更新为 Agent／真人分工明确的版本后发送：Agent 修改 Hosts、执行 curl 并检查结果、打开网页和整理反馈；本人确认系统授权、完成登录并体验输入／退格／Ctrl-C／重连。提示词自包含，明确 curl 成功只说明接入检查通过。2026-10-28 12:56:03 UTC 调用微软 Graph sendMail 返回 HTTP 202，请求 ID `28b507e8-8706-4387-a264-e5372efdfe06`；回执为同目录 `ritsuka-guacamole-mail-receipt.json`，尚未确认收件箱实际投递或真人验收结果。

两位测试者使用同一 `employee` Unix 账号和测试机文件环境；独立网页登录不构成员工 VM 隔离。邮件明确不存个人项目、不登录个人 Claude，仅进行短时交互验收。

### 两位真人均反馈明显卡顿：当前 HTTP 方案未通过体验验收

2026-10-29 悉尼时间，用户反馈张同学与 ritsuka2020 均有明显卡顿，从其所看视频判断回显明显超过 200 ms；本任务未收到视频文件，未自行从视频测量数值。此前 202.5 ms 是中国 Linux 节点的复用 HTTP API 响应中位数，不是两位用户浏览器的按键到显示延迟，不能用于覆盖此次真人反馈。

只读核查时 VM502 loadavg 为 0.00、可用内存约 3 GB，Guacamole 容器 CPU 约 0.09%；最近 12 小时保留的 Nginx 日志未见 5xx。存在少量 guacd 连接超时、客户端不响应／结束和 Access 令牌到期记录，尚未与用户具体卡顿时刻对应，不能据此排除测试时的短时异常或认定原因。Nginx 已关闭请求与响应缓冲；实际 `/guacamole/websocket-tunnel` 为主动 404，HTTP Tunnel 读写为 200，说明试点仍按原约定强制 HTTP 模式。

Guacamole 官方说明 HTTP 回退会放大输入对网络延迟的敏感性，这是下一项待验证因素，尚未证明它就是本次卡顿根因：[反向代理与 WebSocket](https://guacamole.apache.org/doc/gug/reverse-proxy.html)。此外，客户端 curl 使用 `--noproxy '*'` 并不能证明浏览器也采用同一路径；需核对用户浏览器本域 `/cdn-cgi/trace` 的处理节点，以及原始用户请求的网络证据，避免浏览器代理绕过系统 Hosts。

建议的最小对照（待批准）：保持原域名、VM502、账号和优选 IP，用同一用户设备在短时间内比较原 HTTP 与 WebSocket。变更仅为把 VM502 Nginx 中 WebSocket 路径的 404 改为标准 Upgrade 代理，先 `nginx -t` 再平滑 reload；记录成功 101 与真人同一组输入／退格／Ctrl-C／重连反馈。保留可恢复的原配置。WebSocket 不兼容 Argo Smart Routing，因此这用于定位当前传输开销，不得称为 Argo 加速测试。当前没有实施此对照，也未启用任何付费功能。

### WebSocket 最小对照已部署（真人重测待进行）

用户同意上述最小对照后，仅在 VM502 将 Nginx 的 `/guacamole/websocket-tunnel` 从主动 404 改为标准 HTTP/1.1 Upgrade 代理，关闭该路径请求／响应缓冲并保持 3600 秒超时。`nginx -t` 成功后平滑 reload。原 HTTP 通道继续可用，未重启容器、修改 DNS／Access 账号或 Argo。区域 WebSockets 设置只读核实为 `on`，没有改动。

原配置备份位于 VM502 `/opt/guac-ssh-pilot/runtime/nginx-before-websocket.conf`，变更前 SHA256 为 `4ab4bf848ef58c636bfdcddfcfa86d31c781ec89652ce0850650ff650219789c`，变更后为 `135e03be6e23d1c325588f49751bd0e50301e336dde79d10546ac4dc5da18b97`。部署 UTC 时间 2026-10-28 16:22:37（悉尼 2026-10-29 03:22:37）。撤销时仅恢复这一测试 Nginx 配置，验证后平滑 reload；不覆盖其他运行时状态。

复用 VM502 已安装的 Node.js 22 内置 WebSocket 与 fetch，没有新增软件包。通过 Nginx loopback 实际建立 WebSocket，核对执行结果为 `employee-control`／`employee`，标记、退格和 Ctrl-C 通过；Nginx 记录 HTTP 101。证明文件为 VM502 runtime 的 `websocket-verification-result.json`，检查时间 UTC 16:24:56。检查使用随机临时标记文件而非录制终端；只清理本次检查创建的文件，没有启用真人会话录制。首轮检查代码的退格位置误删了重定向路径字符，出现标记等待超时；修正检查命令后通过，不将此错误归因于服务端。

该自动检查仅覆盖 VM502 loopback 经 Nginx 的 WebSocket SSH 功能，尚未证明任一员工公网浏览器已切换为 WebSocket，也未测出真人键显收益。两位用户应关闭旧终端标签后重开原 HTTPS 网址，保持相同网络、Hosts 和测试动作；后台确认其新连接的 101，浏览器本域 `/cdn-cgi/trace` 的 `colo` 仅用于辅助核对处理节点。原 HTTP 与 WebSocket 的真人反馈均须保留，不能用本机检查耗时或此前 HTTP API 的 203 ms 替代。

### 终端长串提示符：systemd OSC 3008 显示兼容问题

用户截图中出现 `machineid`、`hostname`、`bootid`、`pid`、`type=shell` 等长串。只读核实 VM502 的 `hostname` 实际仍为 `employee-control`，Bash 为 5.3.9；`/etc/profile.d/80-systemd-osc-context.sh` 向 `PROMPT_COMMAND` 添加 `__systemd_osc_context_precmdline`，向 `PS0` 添加 `__systemd_osc_context_ps0`，输出相同 OSC 3008 上下文字段。该输出由 systemd 的 profile 脚本提供，不能称为 Bash 5.3 内置功能。

截图与该脚本输出吻合，属于 Guacamole SSH 终端控制序列兼容性问题，不是主机名配置异常。Apache 已有同类报告 [GUACAMOLE-2213](https://issues.apache.org/jira/browse/GUACAMOLE-2213)，上游格式见 [UAPI OSC 3008](https://uapi-group.org/specifications/specs/osc_context/)。本次仅定位原因，没有改主机名、用户 shell 配置或全局 systemd profile。若实施修复，应限定在 Guacamole 会话，保留员工其他终端环境和现有提示符功能。

### OSC 3008 会话修复已实施

用户继续提供逐次回车打印控制串的输出后，按显示兼容问题修复。VM502 新增仅供本试点使用的 `/usr/local/libexec/guac-ssh-pilot-bashrc`（root 所有、0644），先加载正常系统与用户 profile，再只移除 `PROMPT_COMMAND` 中的 `__systemd_osc_context_precmdline` 项及 `PS0` 中的 `$(__systemd_osc_context_ps0)` 片段，保留其他提示符钩子。未修改员工 `.bashrc`／`.profile`、全局 systemd profile 或主机名。

仅在 Guacamole 的现有三位 Web 用户 SSH 连接中添加 `command`：`exec /bin/bash --noprofile --rcfile /usr/local/libexec/guac-ssh-pilot-bashrc -i`。原含凭据的 XML 备份只留于 VM502 受限 runtime 的 `user-mapping-before-osc-fix.xml`。员工 `.bashrc` SHA256 前后一致：`342099da4dd28c394d3f8782d90d7465cb2eaa611193f8f378d6918261cb9bb8`。

已验证 Bash 语法及 employee 交互启动：普通 profile 被加载、hostname／用户正确，标准输出与错误中无 OSC 3008 序列；随后复跑 WebSocket SSH 的标记、回车、退格、Ctrl-C 检查。新配置由 Guacamole 自动读取，适用于新建连接；已打开的 shell 保留原钩子，需要断开旧终端后重连，旧滚屏内容不会自动消失。此为显示修复，不能据此声称跨境延迟已改善。

### 免邮箱验证码的专用共享测试账号

用户要求可转发给其他人的专用测试账号，不再要求邮箱验证码。已增加独立入口 `https://guac-demo.willfan.me/guacamole/`，只使用 Guacamole 用户名／口令认证，用户名 `guac-test`。新代理 CNAME 记录 ID 为 `2c085d93677ddce135f7c5b318bbb936`，仍指向本试点 Tunnel；配置版本由 1 更新为 2，只增加该 hostname 的 ingress，原域名的 Access JWT 校验配置保持一致。新 ingress 固定源站 Host 为 `guac-demo.willfan.me`。

为避免共享入口成为原员工账号绕过 Access 的入口，VM502 复用已安装的 `guacamole/guacamole:1.6.0` 镜像增加独立 Web 容器 `guac-ssh-pilot-guacamole-demo-1`。其独立认证目录 `runtime/guest-guacamole/` 只含一个 `guac-test` Web 用户；原 Guacamole 应用、账号与 Access 策略不变。复用原 guacd 与 SSH 主机身份校验；Nginx 只增加该 hostname 的虚拟主机，语法检查后平滑 reload，没有重启原服务或拉取镜像。

VM502 同时建立独立系统用户 `guac-test`（UID/GID 1002），只有同名主组、独立 0700 home、没有 sudo。检查确认它不能读取 `/home/employee/.bashrc`，也不使用 employee 的 Unix 身份。独立临时 SSH 私钥只在 VM502 受限 runtime 保存，公钥来源限 `172.31.250.10`，`restrict,pty`，终端授权到 `2026-11-05T04:53:00Z`（悉尼 11 月 5 日 15:53）失效；系统账号另设到期日期。该临时试点密钥不交付客户端、不写入常规员工开户或 BWS。

新账号沿用 WebSocket、SSH 主机公钥校验与会话限定的 OSC 修复。已通过真实公网 HTTPS/WSS → Cloudflare Tunnel → 独立 Web 应用 → guacd → VM502 的主机名／用户、标记、退格、Ctrl-C 验证，用户应为 `guac-test`，主机仍为 `employee-control`。未认证的连接 API 返回 403，原张同学账号在共享应用登录返回 403；正确共享账号可以登录。新网页无需认证即返回登录页 200，原员工域名仍返回 Access 登录跳转 302。源站证明文件为 `runtime/demo-preparation.json`、`demo-web-proof.json`、`demo-websocket-verification-result.json`。

口令及可转发指引只放管理机原私有任务目录 `demo-delivery.json`／`demo-forward.txt`（0600）与 VM502 `runtime/demo-web-login.json`，不进入 Git 或知识库。测试者的 Agent 应为新域名维护 `172.64.52.8 guac-demo.willfan.me` 的单域名 Hosts 映射，本人登录后体验打字与重连；本账号仅临时终端测试，不登录个人 Claude、不存个人项目。本任务没有向第三方发送新邮件。

撤销对象：该 DNS 记录、Tunnel 中该 hostname 的 ingress、Nginx 对应虚拟主机、独立 Web 服务及其认证配置、专用系统账号和本次 SSH 授权／密钥。原配置备份为 VM502 `runtime/compose-before-demo.yml` 与 `runtime/nginx-before-demo.conf`；实施撤销前应审阅后续变化，不能用旧备份整份覆盖新增的无关配置。

### 云资源只读复核

AWS 的 `ap-east-1`（香港）、`ap-southeast-2`（悉尼）、`ap-southeast-1`（新加坡）实例、卷、EIP、NAT 网关、自有快照、AMI、经典／应用／网络负载均衡器和密钥对查询均为空；各地域只剩默认 VPC 和默认安全组，没有发现此前测试资源。阿里云只读检查发现仍有香港员工试点网关；用户随后说明另一个 worktree 正在处理阿里云测试，本任务停止干预阿里云资源，没有释放或修改任何云资源。

原完整方案如下，仅保留背景；实施以本节和用户最新授权为准。

## 1. 目标和本次范围

先证明浏览器经 Guacamole 的 **HTTP Tunnel** 能正常使用 VM502 的 SSH 终端，保留后续验证 Argo 的可能性。本次只申请第一阶段功能验证；Argo 付费开关及延迟对照另行提交审核。

> 🧠 **From Hindsight memory (Guacamole HTTP Tunnel 经 Argo 的 SSH 验证)** — 最初约定是验证 HTTP 承载的交互流量能否获得 Argo 的净收益；协议连通和实际提速需要分别验证。

本轮以用户最新指令和以下现场记录为准，不把历史计划当作已实施状态。

## 2. 当前状态和纠正

- 正确目标：**pve2 的 VMID 502**。仓库定义为 `employee_workspaces.control`，地址 `10.231.2.2/30`；已进行的 SSH 只读核查返回主机名 `employee-control`。
- VM502 先前只读核查显示约 4 GiB 内存、43 GiB 可用磁盘；没有发现 Docker、Podman、cloudflared 命令。这不等于获准安装。
- 错误操作：代理擅自在 **pve0 / VM102 / 192.168.1.102 / rustdesk** 部署了试验。随后用户明确要求恢复原状，已完成定向恢复：删除本次四个容器、两个网络、一个卷、四个新镜像、专用配置目录及四个临时文件；`127.0.0.1:18080` 已关闭。清理前后核对既有容器的 ID、镜像、状态、启动时间和重启策略一致，原有 `hbbs`、`hbbr` 持续运行；原有 DeepLX 停止容器和镜像保留。
- 该次只确认错误主机上的 Guacamole HTTP 返回 200，**没有完成 SSH 交互验证**，不能沿用为 VM502 的验收结果。
- Cloudflare Access 应用及 Tunnel 的创建请求被自动审批拒绝，未成功创建，也未新增 DNS。本轮未操作 Argo 开关；Argo 当前状态因 API 拒绝读取而尚未核实。
- 误建的 `experiments/guacamole-ssh/` 及其五个文件已按用户纠正撤销，空的 `experiments/` 顶层目录也已移除。当前只保留本待审方案；实施文件及其位置仍需审核，不擅自新增目录。

## 3. 固定拓扑

```text
测试者浏览器
  → HTTPS：guac-ssh-test.willfan.me
  → Cloudflare Access：仅允许 [邮箱已脱敏]
  → 本次专用 Cloudflare Tunnel
  → VM502 上 cloudflared → Nginx → Guacamole Web
  → guacd → VM502 本机现有 sshd → employee 账号
```

Guacamole、guacd、Nginx、cloudflared 都部署在 **VM502**。SSH 终点也是 VM502 本机；不再另建 SSH 目标容器，不使用其他业务 VM 作为试验宿主，不经香港、OCI 或新加坡中转。

Guacamole HTTP 与 Tunnel 连接使用的 HTTP/2／QUIC 是不同层的协议。验收必须确认浏览器至 Guacamole 的会话数据使用 HTTP Tunnel。

## 4. 拟执行的具体变更

| 对象 | 变更 | 边界 |
| --- | --- | --- |
| VM502 软件 | 安装 Docker Engine 和 Compose 插件；运行 Guacamole Web 1.6.0、guacd 1.6.0、Nginx、cloudflared | 在执行前固定镜像版本及摘要，记录安装清单；新增内存预算约 1 GiB，不自动扩容 VM |
| VM502 文件 | 独立目录 `/opt/guac-ssh-pilot/`、独立 Compose 项目 `guac-ssh-pilot` | 不挂载员工 HOME、Claude 登录态或 Docker socket 到 Web／guacd 容器 |
| VM502 SSH | 为现有 `employee` 账号追加一把测试专用公钥 | 私钥按现有私有管理员流程存入 BWS 独立 Secret；只允许 guacd 来源、允许 PTY、禁止转发；不复用管理员或现有设备私钥，不覆盖原 authorized_keys |
| VM502 容器网络 | 专用私有 Docker 网络；内部 guacd 和 SSH 连接不发布端口 | 发布到主机的 Web 端口仅绑定 `127.0.0.1:18080`；网段执行前检查冲突，有冲突则停止并修订方案 |
| Cloudflare Tunnel | 新建 `guac-ssh-pilot-20261028` | 只配置本次域名，最终兜底 404；连接器仅运行在 VM502，保留现有 Tunnel |
| Cloudflare DNS | 新增 `guac-ssh-test.willfan.me` 的代理 CNAME 指向本次 Tunnel | 先创建并验证 Access 策略，后发布 DNS |
| Cloudflare Access | 新建同域名 Self-hosted 应用，Allow 仅 `[邮箱已脱敏]`，会话 1 小时 | 不添加 Everyone／Bypass；Tunnel 源站再次校验该应用的 Access JWT audience |
| Cloudflare 缓存 | 检查该测试域名是否会被现有规则缓存；必要时新增仅匹配该主机名的绕过规则 | 不改写其他主机的缓存策略；会话响应包含 `Cache-Control: no-store` |
| 出站／管理连接 | 测试 Sandbox 仅管理 `10.231.2.2:22`；核对 VM502 到 Cloudflare 官方 Tunnel 端点的 TCP/UDP 7844 | 不新增家庭路由器公网映射，不向公网开放 VM502 的 22／8080／4822；若现有隔离规则阻断，先列出精确差异再审批，不临时绕过 |

Guacamole Web 登录使用独立测试口令，凭据只保存在私有存储和受限运行时文件中，不放入仓库、聊天、命令参数或访问日志。Nginx 日志不记录认证查询参数。

## 5. 实施方式和顺序（审批后）

1. **误部署恢复已完成**：本轮已获用户明确授权并执行，仅清理经项目标签、配置 SHA256 和镜像引用核实属于本次试验的 VM102 资源。未执行全局 prune。后续审批和实施只涉及 VM502，不重复操作 VM102。
2. 在本任务 worktree `codex/guacamole-argo-ssh` 完善 **仅限 VM502** 的部署与撤销配置；使用任务专用 Docker Sandbox 执行 Ansible，单主机 inventory，不使用本机 Ansible，不执行 Terraform apply。
3. 只读确认 VM502 的实际身份、当前服务、磁盘、端口和防火墙基线；检查拟安装软件和网络差异。身份不符或发现未在本方案覆盖的改动则停止。
4. 安装已批准依赖，在 VM502 上部署 Guacamole 和 guacd，连接 VM502 本机 sshd，先在 loopback 验证。使用测试公钥；保持原 SSH 与浏览器服务可用。
5. 为 HTTP 试验入口拒绝 `/guacamole/websocket-tunnel`，关闭反向代理响应缓冲和请求缓冲；确认客户端回退到 HTTP Tunnel 后仍可交互。
6. 创建本次 Access、Tunnel 和 DNS，并核对未授权请求被挡在入口外；再进行浏览器 SSH 验收。
7. 输出功能结果、真实传输协议证据和试验入口。**到此停止，不自动进入 Argo 付费开通或性能测试。**

## 6. 第一阶段验收

| 检查 | 标准操作／预期结果 |
| --- | --- |
| 目标正确 | PVE／配置对应 VMID 502；浏览器 SSH 执行 `hostname` 返回已核实的 VM502 主机名，当前为 `employee-control` |
| 身份正确 | 浏览器 SSH 执行 `id -un`，返回 `employee` |
| 真正可交互 | 逐条输入 `printf '__GUAC_SSH_OK__\n'`、`pwd`，看到对应输出；打字、退格、Ctrl-C 正常。不得只以网页 200 或登录页可见认定成功 |
| HTTP Tunnel | 代理日志及浏览器请求证据显示使用 `/guacamole/tunnel` 的读写；会话没有 WebSocket 101 升级；不以 Tunnel 自身使用 QUIC／HTTP2 作为证明 |
| 断线恢复 | 关闭网页后重开，能够重新建立 SSH；不承诺恢复原 shell 进程 |
| 入口授权 | 无 Access 会话进入登录流程；不匹配 Allow 的身份无法访问；已授权身份可使用 Guacamole |
| 隔离与端口 | 公网不直接暴露 Web／guacd／SSH 新端口；测试密钥不能用于转发；现有员工入口不受影响 |

Agent 使用上述固定命令逐条验证。异常时保留错误与日志，不自行更改员工 SSH 策略、其他 VPN 或现有设备包。

本阶段不评判延迟优劣，不测试桌面或个人 Claude 登录。

## 7. 后续 Argo 对照需要再次审核

只有第一阶段通过后，才准备第二份具体测试单：同设备、同 VM502、同 SSH 目标，比较 WebSocket 基线、HTTP Tunnel 基线和 HTTP＋Argo，测持续交互的中位数、P95／P99、尖峰频率。

当前 Argo 状态未核实，因此不能把第一阶段流量称为“Argo 关闭基线”。必须核实实际开关与路由证据；若无法证明 Argo 生效，只报告功能结果，不报告加速收益。

Argo 属于域级付费功能，不能假定只计本次子域名的流量。开通前需向用户说明 `willfan.me` 其他流量的计费影响、控制台实际价格和测试预算；**本方案不授权任何 Argo 订阅或开关变更**。中国侧设备恢复可用后再安排真实用户测试；本阶段不创建河源、香港或 AWS 测试机。

## 8. 撤销

移除仅本次创建的 DNS、Access 和 Tunnel；停止并清理 VM502 的测试 Compose 项目、测试密钥及 BWS 测试 Secret，保留原 authorized_keys。只删除已核实归属本次试验的文件和数据，不还原整台 VM 的磁盘、不删除用户文件。

Docker 的安装及 Docker 防火墙规则也需有清单。若要求恢复到安装前状态，单独审阅卸载清单和网络差异后执行，避免影响试验期间新增的其他容器。本方案不批准 Git commit、push 或 PR。

## 9. 本次请审核的范围

VM102 定向恢复已按用户本轮指令完成，**该清理授权不构成 VM502 部署授权**。请审核 **第 4 节具体变更和第 5 节第一阶段执行顺序**。第一阶段通过前，不增加测试宿主、测试账号范围、云资源或 Argo 付费功能；发生实质变更先修订方案再执行。

参考：

- [Cloudflare：Argo 与 WebSocket 不兼容](https://developers.cloudflare.com/network/websockets/)
- [Guacamole：Docker 部署](https://guacamole.apache.org/doc/gug/guacamole-docker.html)
- [Guacamole：代理缓冲与 HTTP 回退注意事项](https://guacamole.apache.org/doc/gug/reverse-proxy.html)
- [Cloudflare：Argo／Smart Shield 计费](https://developers.cloudflare.com/billing/understand/how-billing-works/)
