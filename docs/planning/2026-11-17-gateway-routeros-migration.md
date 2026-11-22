# 网关迁移规划：iStoreOS → N100 上的 PVE + RouterOS CHR

> 状态：规划中，未执行任何变更。依据为 2026-11-17 用户在网关上执行的只读盘点。
> 本文取代 [gateway-backup.md](../guides/gateway-backup.md) 中“P2V 导入 iStoreOS VM”的迁移方向；该文的冷备步骤仍沿用。

## 目标

同一台 N100（4 核、8 GB、256 GB NVMe、eth0 WAN + eth1–3 LAN）改装 PVE：

- **RouterOS CHR VM** 接管路由、DHCP、DNS、NAT、UPnP，并以 RouterOS container 运行 AdGuard Home 与 KMS。
- **业务容器**迁入单独的 Debian Docker VM。
- open-webui 及不再使用的 iStoreOS 附带服务退役。

```
N100 (PVE 宿主，LAN 固定管理地址)
 ├─ vmbr_wan ← eth0（宿主无 IP，关闭 IPv6 accept_ra/autoconf）
 └─ vmbr0    ← eth1/2/3（LAN 二层由宿主网桥承担，不依赖 CHR）
      └─ VM: RouterOS CHR（LAN 192.168.1.1，WAN/LAN 网卡克隆原 MAC）
           ├─ 原生：DHCP、DNS、防火墙/NAT、静态路由、UPnP
           └─ container（br-containers 内网）：AdGuard Home、vlmcsd
```

## 盘点结论与去向

### 网络类服务（原生 opkg，不是 Docker）

| 现状 | 去向 |
|---|---|
| dnsmasq：`.1:53`，本地域 `willfan.me`（含 rebind_domain），12 条静态租约，`filter_aaaa=1`，上游 `127.0.0.1#3053` | ROS 原生 DHCP/DNS；静态租约逐条迁移；DHCP 池 `.150–.246`、租期 1d |
| AdGuard Home 0.107.57：DNS `:3053`，Web `:3000` | ROS container；链路保持“客户端 → ROS DNS(.1) → AGH”；netwatch 检测 AGH 失败时切换公共 DNS |
| vlmcsd（KMS）`:1688` | ROS container，dst-nat `.1:1688`；仅 LAN 可达 |
| miniupnpd | ROS `/ip upnp` |
| tailscale（tailscaler） | **待确认**是否仍需要、是否广播子网路由 |
| ddns-scripts（服务未启用）、ddnsto（已禁用）、linkease、samba4/nfsd/wsdd2/avahi | 退役（用户 2026-11-17 确认） |
| ttyd、openwrt-mcp、unetd、radius、relayd、appfilter、adb、modemmanager、istore/quickstart/unishare/webdav2 | 退役（iStoreOS 自带或 OpenWrt 专用） |

### 路由与转发

| 现状 | 去向 |
|---|---|
| WAN eth0 DHCP（公网地址，非 CGNAT），wan6 DHCPv6，LAN ULA | ROS DHCP client v4/v6；IPv6 策略另定 |
| `10.236.0.0/16 via 192.168.1.52`（OCI hub 回程，WAN NAT 须覆盖） | 迁移 |
| 8 条 `10.231.x.0 via 192.168.1.140` 员工路由（无 netmask，实为 /32） | 不迁（用户确认作废） |
| 端口转发 UDP 51820 → `192.168.1.140`（Employee-WireGuard） | 不迁（用户确认作废） |
| 防火墙规则 `kms`、`linkease`、docker 区 | kms 改为 ROS 规则；其余随服务退役 |

### Docker 业务容器 → Debian VM

| 业务 | 容器 | 现有端口 |
|---|---|---|
| xiaozhi | server、web、mqtt-gw、MySQL、Redis | `.1`:8000/8002/8003；`0.0.0.0`:1883/8007/8884udp |
| hermes | hermes、hermes-webui | `.1`:8642/9900；`0.0.0.0`:9119/8787 |
| codex-proxy | codex-proxy | `127.0.0.1`:8899 |
| cn-proxy | sing-box | `0.0.0.0`:7890 |
| ~~open-webui~~ | 退役 | — |

- 退役 open-webui 后合计约 2.5 GB 内存。VM 内保留 `/mnt/data` 路径与原 Compose 文件，`gateway-backup.sh` 与 HA 控制器的强制命令随之迁移。
- 客户端和 ESP32 设备当前连接 `192.168.1.1` 上的端口。过渡期由 ROS 对这些端口 dst-nat 到 VM；VM 与客户端同在 LAN，需配套 hairpin srcnat。长期逐步把客户端改为 VM 地址。
- 清理遗留：未运行的 `docker-compose.household-bill-assistant.yml`、网络 `open-webui_default`、匿名卷 `52da62…`（删除前单独确认）。
- **qnetd-witness 不迁移**：N100 入集群后 QDevice 移除，见证退役。

## 已决定（2026-11-17 用户）

1. **N100 加入 HomePVECluster，`quorum_votes: 3`**；pve0/pve1 各 1 票，总 5 票，quorum 3。先 `pvecm qdevice remove`，再空节点 `pvecm add`，然后修改 `corosync.conf` 的票数并递增 `config_version`。qnetd-witness 与 guard 随之退役。
   - 效果：N100 单独在线也有 quorum，CHR 可以开机自启。
   - 代价：**N100 离线时（含 PVE 宿主升级重启），pve0 和 pve1 合计 2 票，失去 quorum**。已运行的 guest 继续运行，但不能启停、迁移、改配置，备份等需要写 `/etc/pve` 的操作会失败。**如果 pve0/pve1 上配置了 HA 资源，节点会被 watchdog 自我隔离（fence）**，切换前必须核实 `ha-manager status` 为空，或者先移除 HA 资源。
   - 存储：N100 只有本地 LVM-thin。集群存储定义中的 pve0/pve1 专用存储要限定 `nodes`，不能对 N100 可见。
2. **业务 VM 留在 N100 本地**。不用 ZFS（ARC 会吃内存），安装时用 ext4/LVM-thin。内存预算：宿主约 1.5–2 GB，CHR 1.5 GB，业务 VM 固定 4 GB（关闭 ballooning），合计接近 8 GB，余量很小。建议业务 VM 接在 CHR 后面的独立内网桥（如 `vmbr_svc`），由 CHR 路由和 dst-nat：不需要 hairpin NAT，也把 hermes 和 LAN 隔开。
3. **tailscale 保留**，迁为 ROS container。子网路由和 exit node 设置待核实。
4. **CHR 授权**由用户自行购买（免费版每接口上传限速 1 Mbps）。
5. **没有第二块盘的空间**。回滚只能把 USB 上的整盘镜像写回 NVMe：256 GB 在 USB 3 上约需 25–45 分钟，要计入停机窗口。切换前在 pve0 上用 loop 挂载镜像中的各分区，确认镜像可读。

## 待核实

- AdGuard Home 配置文件位置与上游设置：`uci show adguardhome`。
- tailscale 状态与子网路由。
- **外网暴露**：用手机流量测试公网地址的 7890、1883、9119、8787、445、7681。smbd 当前监听在 WAN 地址；Docker 发布到 `0.0.0.0` 的端口可能绕过 fw4。
- AGH TCP 3053 盘点时 `Recv-Q 22`，确认 TCP DNS 是否正常。

## VLAN 规划：家庭网络与对外服务隔离

> 依据：IaC 公开文档（remotecc-ops、HAPI 控制面、HAPI 网络开户）和 LaaS 仓库的 v2 架构（2026-10-19，**只有设计，尚未实现**）。remotecc 私有仓库没有 GitHub 远端，未能读取，涉及它的结论需要在执行器上复核。交换机已确认支持 802.1Q。

### 现状

- 所有主机都在同一个 `192.168.1.0/24` 二层网络里。员工 VNet `10.236.0.0/16` 由 pve2 三层转发，再经家庭 LAN 送到 `.1`。OpenWrt 把整个 LAN 当作一个区域，**网关这一层没有规则阻止员工网段访问家庭网络**，隔离只靠 pve2 的 nft 端口 ACL。
- RemoteCC：VM500（HAPI 控制面，pve2，`.140`，Cloudflare Tunnel 出站）、员工工作区（pve2 SDN）、模板 9000（pve2）、remotecc-ops（pve0，`.116`）。
- LaaS v2：在单个选定的 PVE 节点上运行 EVE-NG VM。控制器（Agent、监督进程、鉴权网关、cloudflared）放在独立管理 VM 中，通过 PVE HTTPS API 管理 VM。每台 EVE VM 有两个接口：管理接口，以及每租户一个 VLAN tag 的实验接口。架构要求管理网阻止跨租户访问，也不能访问 PVE、存储和备份控制面。v1 基于已退役的 ESXi，不再运行。

### 分区

| VLAN | 区域 | 网段 | 成员 |
|---|---|---|---|
| 1（untagged） | HOME | `192.168.1.0/24`（不变） | 家庭终端、PVE 宿主/PBS/NetBox 等内部服务、业务 VM、**remotecc-ops** |
| 20 | REMOTECC | `192.168.20.0/24` | VM500；pve2 新增接口 `192.168.20.52`，作为员工 VNet 的上联 |
| — | 员工 VNet | `10.236.0.0/16`（不变） | CHR 路由下一跳从 `192.168.1.52` 改为 `192.168.20.52` |
| 30 | LAAS | `192.168.30.0/24` | 只放 LaaS 控制器 VM 的上联网卡（Cloudflare Tunnel、Worker、pve2 API）。LaaS v2 定在 pve2（用户 2026-11-22 确认） |
| — | LaaS 管理网与实验网 | `10.240.x.0/24` | 由 LaaS 1.4/1.5 在 pve2 上用 PVE SDN simple zone `laas` 声明（IaC PR #303），**无上联、不走交换机、CHR 不路由**。本方案不另设实验 VLAN |
| 40 | GUEST | `192.168.40.0/24` | 访客 Wi-Fi，只能上外网 |
| 50 | IOT | `192.168.50.0/24` | ESP32 等设备，只开放到业务 VM 上小智服务所需的端口 |
| —（N100 内部桥 `vmbr_svc`） | SVC | `192.168.10.0/24` | 业务 VM（`192.168.10.10`），由 CHR 路由，`.1` 上的原端口经 dst-nat 转到这里 |

- RemoteCC 和 LaaS 分成两个 VLAN：两者服务不同的外部用户，互相之间也要隔离。
- **remotecc-ops 留在 HOME**：它持有管理员凭据。公开文档显示，它只接受 LAN 和 tailnet 的入站；网站申请由它主动拉取（`wsctl request`），`hapi-sync` 也是由它主动连接 VM500、PVE 和 Cloudflare。2026-11-22 在执行器上只读复核：只监听 SSH(22) 和 Semaphore(3000，明文 HTTP，监听所有网卡)，UFW 只放行 `192.168.1.0/24` 和 `tailscale0`；没有 Tailscale serve/funnel，Semaphore 没有任何 webhook 集成，`/srv/remotecc` 中也没有对外监听配置。**确认没有 DMZ 需要主动连接它**。改造后，它的主机防火墙放行的 `192.168.1.0/24` 天然不包含 DMZ。

### CHR 防火墙策略（默认拒绝）

| 方向 | 策略 |
|---|---|
| HOME → REMOTECC、LAAS | 允许（管理） |
| REMOTECC、员工 VNet → HOME | 拒绝 |
| LAAS → HOME | 拒绝，只放行 LaaS 控制器 → pve2 TCP 8006（专用受限 API token） |
| REMOTECC ↔ LAAS | 拒绝 |
| REMOTECC、员工 VNet、LAAS → Internet | 允许并 NAT |
| GUEST → 任何内网 | 拒绝；只能上外网 |
| IOT → HOME | 只放行业务 VM 上小智服务所需的端口（8000/8003/1883/8007/8884udp，切换前核实） |
| 各 DMZ → CHR 自身 | 只允许 DNS、DHCP、ICMP |
| WAN → 任何内网 | 只允许显式 dst-nat（目前没有） |

VM500 与员工 VM 之间的 9443 流量（控制面 → VM、Runner → Hub）由 pve2 在 `192.168.20.0/24` 与 VNet 之间直接转发，不经过 CHR，继续由 pve2 的 nft ACL 约束。

### 物理与主机配置

- **交换机**：连接 N100、pve0、pve2（以及 LaaS 节点）的端口配成 trunk，放行 VLAN 1 untagged 以及 20、30、40、50 tagged；家庭终端口配成 access VLAN 1；AP 上联口配成 trunk。实验 VLAN 3001–3099 不放行。
- **N100**：`vmbr0` 开启 VLAN-aware，宿主管理地址走 untagged；CHR 的 LAN 网卡作为 trunk，在 ROS 内建 `vlan20/30/40/50` 接口。
- **pve2**：`vmbr0` 开启 VLAN-aware，宿主 `.52` 保持 untagged，新增 `vmbr0.20`，地址 `192.168.20.52`。员工 VNet 的出站加策略路由：`ip rule from 10.236.0.0/16 lookup remotecc`，**优先级要高于 main 表**，`remotecc` 表只有一条默认路由指向 `192.168.20.1`。否则 main 表里直连的 `192.168.1.0/24` 会让员工流量绕过 CHR 直达 HOME。保留现有 nft ACL 作为第一道防线，并检查 `rp_filter`。
- **VM500**：网卡加 tag 20，地址改为 `192.168.20.140`、网关 `192.168.20.1`。`terraform/remotecc` 已有 `uplink_address` 和 `uplink_gateway` 变量，但要新增 VLAN tag 支持。Cloudflare Tunnel 是出站连接，不受影响。员工 VM 访问的 resolver 如果是 `.1`，要改为 CHR 在 VLAN 20 上的地址，并同步更新 pve2 的 nft ACL。
- **LaaS（pve2）**：EVE 的管理和实验接口留在 LaaS 自己的 SDN `laas` 区域（无上联，隔离由 SDN 和 laas 专用 nftables 表负责）。控制器 VM 另加一张 tag 30 的上联网卡。**pve2 不在 VLAN 30 上配地址**，控制器访问 pve2 API 必须经过 CHR 的单一放行规则，不能在宿主上绕过。2026-11-22 已把本方案通知 LaaS 会话。
- `terraform/modules/proxmox-vm` 目前没有 VLAN tag 参数，需要先补上。
- Corosync、PBS 和 PVE 管理流量只走 HOME。

### 无线 AP（GL-MT3000，`192.168.1.3`，OpenWrt 24.10.4）

2026-11-22 只读核对的现状：
- `br-lan` 桥接 `eth0` 和 `eth1`，`lan` 通过 DHCP 取得 `.3`，按纯 AP 工作。`wan` 指向已被桥接的 `eth0`，实际不起作用。
- `guest`、`iot` 两个网络（static，`br-guest`/`br-iot`）以及对应 SSID `guest2g`、`iot2g` 已经在 uci 里定义，但没有生效。那套是 AP 自己做 NAT 和 DHCP 的方式，不符合本方案。
- 网关 DHCP 里还登记着另一台 AP `ax3000t-ap1`（`.2`），目前不在线。用户 2026-11-22 确认这台不再使用，**不迁这条静态租约**。

目标配置：AP 只做二层，VLAN 由上联 trunk 带入。MT3000 的两个网口都是独立的以太网接口，没有 DSA 交换芯片，所以直接在 `br-lan` 上做 bridge VLAN filtering。上联口为 `eth0`（2.5G，用户 2026-11-22 确认）。

```
# /etc/config/network (draft)
config bridge-vlan
        option device 'br-lan'
        option vlan '1'
        list ports 'eth0:u*'
        list ports 'eth1:u*'
config bridge-vlan
        option device 'br-lan'
        option vlan '40'
        list ports 'eth0:t'
config bridge-vlan
        option device 'br-lan'
        option vlan '50'
        list ports 'eth0:t'
config interface 'lan'
        option device 'br-lan.1'
        option proto 'dhcp'
config interface 'guest'
        option device 'br-lan.40'
        option proto 'none'
config interface 'iot'
        option device 'br-lan.50'
        option proto 'none'
# remove: interface wan/wan6/wwan*, device br-guest/br-iot
```

- 无线：`guest2g` 绑定 `guest`，开启 `isolate '1'`，可加一个 5 GHz 访客 SSID；`iot2g` 绑定 `iot`，只用 2.4 GHz，照顾 ESP32。
- AP 上停用 dnsmasq、odhcpd 和防火墙对 guest/iot 的处理，DHCP 统一由 CHR 提供。
- 改配置时有断网风险，要有有线连接或串口兜底，并设好自动回滚（例如先 `uci commit` 前做备份，用 `sleep 300 && reboot` 兜底）。

### 实施顺序

1. **路由迁移当晚**：CHR 一开始就用 VLAN-ready 配置（vlan-filtering bridge，HOME 走 VLAN 1），但其它 VLAN 先不放任何成员。
2. **交换机和 AP**：配置 trunk，验证 HOME 不受影响。
3. **REMOTECC**：先迁 VM500 → 验证 HAPI；再切 pve2 员工上联、策略路由和 `10.236/16` 路由 → 验证员工出网、OCI hub 和 9443 通信。
4. **GUEST、IOT**（用户 2026-11-22 确认本次实施）：小智设备迁到 IOT 前先在 CHR 上放行端口。
5. **LAAS**：随 LaaS v2 M0 实施，现在只预留 VLAN 号和网段。
6. **收紧防火墙**：先开日志观察，再改为默认拒绝。每一步的回滚都是撤掉 tag，恢复原地址和路由。

## 实施阶段（每步单独授权）

0. **演练**：在 pve0 建隔离网桥中的测试 CHR，导入 `.rsc`（DHCP/DNS/AGH/KMS/NAT/路由/UPnP）验证；在业务 VM 中用 PBS 归档恢复各业务。
1. **冷备**：按 gateway-backup.md 将整盘 NVMe 保存到 USB（或另装 SSD、保留原盘）。
2. **切换（午夜窗口）**：核实无 HA 资源 → 最后一次业务备份 → 安装 PVE（停网期间没有外网，CHR 镜像、ISO 和容器镜像 tar 都要事先放在 USB 或 pve0 上）→ `pvecm qdevice remove` → N100 以空节点 `pvecm add` → 设置 3 票 → CHR 上线（克隆 MAC）→ 业务 VM 恢复。
3. **验收**：DHCP/DNS/外网；AGH 故障切换；`10.236.x` 出网与回程；`.1` 端口 dst-nat 到业务；`pvecm status` 显示 Total votes 5、Quorum 3；关闭 CHR 时 pve0/pve1/PBS 仍互通；宿主断电重启后全部自动恢复；pve0/pve1 都关机时 N100 仍 quorate、CHR 能自启。
4. **回滚**：写回 USB 镜像（约 25–45 分钟）；集群侧需先移除 N100 节点，再按 qdevice 文档恢复 QDevice。

## 停机窗口分步清单

时间是估算值，以演练实测为准。每个窗口开始前都要取得用户授权。两个窗口期间员工 VM 的外网和 OCI hub 回程都会中断，要提前通知员工。

### 窗口 A：整盘冷备（单独一晚，断网约 30–45 分钟）

**事前准备**
- [ ] pve0、pve1 在线且 quorate。网关关机后见证票丢失，两台合计 2 票仍满足 quorum 2；窗口期间不安排 PVE 维护。
- [ ] 500 GB USB 盘：ext4 或 exFAT（不能用 FAT32），空闲空间 ≥ 256060514304 字节加余量；Ubuntu 24.04 Live U 盘。
- [ ] Mac 有线 `en9` 接交换机，配一个已核实空闲的静态地址；确认通过 IP 能访问 pve0/pve1。
- [ ] 从网关导出 `sysupgrade -b`、`uci export`、AdGuard 配置，拷到 Mac（不提交到仓库）。
- [ ] 记录 eth0（WAN）和 `br-lan` 的 MAC：`ip -br link`。

**步骤**
1. 网关上执行 `poweroff`，**断网开始**。
2. 从 Live U 盘启动，用 `lsblk -o NAME,SIZE,MODEL,SERIAL` 确认源盘 `nvme0n1` 和目标 USB 盘；NVMe 各分区保持不挂载，只挂载 USB 盘到 `/mnt/usb`。
3. 一次读取同时写镜像和算校验：
   `dd if=/dev/nvme0n1 bs=16M status=progress | tee /mnt/usb/gateway-original.img | sha256sum > /mnt/usb/gateway-original.img.sha256 && sync`
4. 核对镜像大小等于 256060514304 字节；卸载 USB 盘。
5. 拔掉 Live U 盘，重启回 iStoreOS。
6. 验证：外网、DHCP 续租、`pvecm status` 显示 `Quorate Qdevice`、业务容器全部运行。**断网结束**。

**事后（不断网）**
- [ ] 把镜像传到 pve0，`sha256sum` 与第 3 步的结果比对；用 `losetup -P -r` 只读挂载各分区，抽查 `/mnt/data`。
- [ ] USB 盘上的原始镜像保留到切换完成、稳定运行至少两周之后。

### 窗口 B：正式切换（午夜，断网约 30–45 分钟，按 1 小时预留）

**事前准备（T-7 天到 T-1 天）**
- [ ] CHR 授权或试用账号就绪。
- [ ] 在 pve0 的隔离网桥中完成测试 CHR：导入 `.rsc`，填好静态租约，AdGuard、KMS、Tailscale 容器镜像已经拉进数据盘；完成后备份到 PBS。
- [ ] 业务 VM 在 pve0 演练完成：Compose、数据、`gateway-backup.sh` 都已迁好；备份到 PBS。提前做一次 `/mnt/data` 全量同步。
- [ ] PVE 安装 ISO 的版本与集群一致（集群为 PVE 9，`pve-cluster 9.0.6`），写入 U 盘。停网期间没有外网，所有安装介质和镜像都要事先备好。
- [ ] 在 pve0 上确认 `ha-manager status` 为空。
- [ ] 确认 N100 宿主地址（建议 `192.168.1.2`，原 `ax3000t-ap1` 的地址已释放）和节点名；确认集群中 VMID 不冲突。
- [ ] 确认 USB 冷备镜像可用（窗口 A 已完成）。
- [ ] 如果采用临时路由（见下），提前准备好 GL-MT3000 的路由模式配置。
- [ ] 通知家人和员工。

**步骤**
1. **（未断网）** 停止业务容器；执行最后一次 `gateway-backup.sh backup all`，把 `/mnt/data` 的增量同步到业务 VM 的暂存位置；再导出一次 `uci export` 和 AdGuard 配置。
2. **（未断网）** 在 pve0 上执行 `pvecm qdevice remove`（两节点都 quorate 时只执行一次，不加 `force`）；确认 Total votes 2、Quorum 2。
3. 网关 `poweroff`，**断网开始**。从 PVE U 盘启动并安装：目标盘 NVMe，文件系统 ext4/LVM-thin（不用 ZFS），管理网卡选接交换机的那个口（按 MAC 识别），地址 `192.168.1.2/24`，网关 `192.168.1.1`。
4. 配置 `/etc/network/interfaces`：
   - `vmbr0`：桥接三个 LAN 口，`bridge-vlan-aware yes`，`bridge-vids 1 20 30 40 50`，宿主地址走 untagged。
   - `vmbr_wan`：桥接 WAN 口，不配地址；对它设置 `accept_ra=0`、`autoconf=0`、`disable_ipv6=1`。
   - `vmbr_svc`：不接物理口。
   - 执行 `ifreload -a`，确认能从 Mac 访问 `https://192.168.1.2:8006`。
5. N100 执行 `pvecm add 192.168.1.50`；然后在 `/etc/pve/corosync.conf` 中把 N100 的 `quorum_votes` 设为 3，并递增 `config_version`。确认 `pvecm status` 显示 Total votes 5、Quorum 3；集群存储定义中 pve0/pve1 专用的存储限定 `nodes`。
6. 在 N100 上从 PBS 恢复 CHR 到 `local-lvm`：
   - `net0`：`vmbr_wan`，MAC 设为旧 eth0 的 MAC；`net1`：`vmbr0`，不设 tag，MAC 设为旧 `br-lan` 的 MAC；`net2`：`vmbr_svc`。
   - `onboot=1`，`startup order=1`。开机。
7. 验证：WAN 拿到地址；客户端 DHCP 续租成功；`nslookup` 经 AdGuard 解析正常；能访问外网；`10.236.x` 员工 VM 出网正常。**断网结束**。
8. **（不断网）** 在 N100 上从 PBS 恢复业务 VM：接 `vmbr_svc`，地址 `192.168.10.10`，`startup order=2`；补上最终数据，启动 Compose；从 HOME 客户端和一台 ESP32 验证 `.1` 上的端口转发；把 HA 备份控制器改为指向业务 VM。
9. **（短暂断网约 5 分钟，建议当晚完成）** 重启 N100 宿主，确认 CHR 和业务 VM 自动启动、网络恢复。

**回滚**
- 触发条件：断网开始 90 分钟后外网仍未恢复，或第 7 步任一核心验证失败且无法快速修复。
- 步骤：从 Live U 盘启动，`dd if=/mnt/usb/gateway-original.img of=/dev/nvme0n1 bs=16M status=progress && sync`（约 25–45 分钟），重启回 iStoreOS。
- 集群侧：如果 N100 已经加入，在 pve0 上 `pvecm delnode` 移除它。恢复 QDevice 要按 [qdevice 文档](../architecture/proxmox-qdevice-architecture.md) 的受控 setup 流程另行执行；在那之前 pve0、pve1 各 1 票，两台都在线时仍 quorate。
- 回滚后，业务数据以第 1 步的最终备份为准；窗口期间产生的新数据很少。

### 可选：用 GL-MT3000 做临时路由

窗口期间让家人用 Wi-Fi 上网，把家里的断网缩短到几分钟：
- 事先在 MT3000 上准备好一套路由模式配置：WAN 接 `eth0`（如果运营商绑定 MAC，就克隆旧 eth0 的 MAC），LAN 用独立网段（如 `192.168.88.0/24`），开启 DHCP 和 NAT。
- 窗口开始时，把运营商的线改插到 MT3000，并**断开 MT3000 与家里交换机的连接**，避免两套 DHCP 冲突。
- 这期间只有 Wi-Fi 设备能上网；员工路由、静态地址主机和 AdGuard 都不可用。
- 第 7 步验证通过后，把线插回 N100，MT3000 恢复 AP 配置。

## 收尾

更新 inventory（`network_appliance`）、NetBox 地址、qdevice/gateway-backup/cn-proxy/OCI hub 文档中关于 OpenWrt 的描述；CHR 定时 `/export`，两台 VM 交由 PBS 整机备份。

ROS 配置草稿：[2026-11-22-gateway-routeros-draft.rsc](2026-11-22-gateway-routeros-draft.rsc)。
