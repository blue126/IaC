# 网关备份：范围、调用与恢复

`scripts/gateway-backup/gateway-backup.sh backup all` 由脚本顺序执行六项常规业务，外部控制器只需调用一次。每项记录原运行状态，按依赖顺序停服，直接调用官方 `proxmox-backup-client backup`，最后尝试启动原先运行的容器并清理临时元数据；这些步骤全部成功后才处理下一项。保留 `backup <business>` 单业务入口。按用户要求，业务数据生成未加密的原生 pxar 归档，明确使用 `--crypt-mode none`；停机时间包含整个上传过程。PBS 登录认证和 HTTPS 传输保留。

**当前状态（2026-10-09）：脚本和官方静态 PBS 客户端 4.2.6 已部署到网关；小智真实备份已验证成功，用户随后反馈已完成一次全部容器备份。恢复演练按用户决定暂缓，尚未验证恢复后的应用可用性。** 后续人工执行真实停服前仍需先通知用户业务影响和恢复安排。

2026-10-06 小智实测生成快照 `host/gateway-xiaozhi/2026-10-06T01:15:46Z`，四份业务/元数据归档的 `crypt-mode` 均为 `none`。全流程约 129 秒，客户端上传约 1.83 秒；结束后五个容器均运行，MySQL/Redis 健康，Web 返回 HTTP 200，其他业务保持运行。MQTT 网关停止超时后被 Docker 强制结束，退出慢的问题暂未修改。2026-10-09 用户反馈的全业务结果尚未逐项独立复核；`backup all` 仍按下文规则排除 qnetd。

实际仓库为 `backup@pbs!automation@192.168.1.249:backup`。2026-10-06 已将该账号和 Token 的原有三条 ACL 从 `/datastore/backup-storage` 迁移到 `/datastore/backup`，保留原角色和继承设置，认证与真实备份均成功。Token 仍保存在 Ansible Vault 的 `vault_pbs_api_token_value`，运行时通过 `PBS_PASSWORD` 注入。控制器定时调用、失败通知及 PBS 保留/校验任务是否已配置，本次收尾未核验。

网关已部署脚本 `/opt/gateway-backup/gateway-backup.sh`，客户端位于 `/usr/bin/proxmox-backup-client`；公共参数和业务清单都在脚本内，PBS Token 由控制器运行时注入。当前脚本覆盖下面列出的 Docker 业务，**尚未包含 OpenWrt 系统配置、固件和额外安装的软件包**。

## OpenWrt 备份是否覆盖容器

2026-10-03 在网关 `192.168.1.1`（iStoreOS 24.10.8，x86/64）执行只读 `sysupgrade -l`，清单共 101 个文件，包含 network、firewall、dhcp、dockerd 配置，但 `/mnt/data`、`/mnt/data/docker` 和 `/etc/sing-box` 下的文件均为 0。Docker 实际数据根目录为 `/mnt/data/docker`；当前全部容器的本地 bind mount 和 volume 来源都位于 `/mnt/data` 或 `/etc/sing-box`。

| 备份方式 | 当前能否覆盖容器 | 恢复用途 |
| --- | --- | --- |
| LuCI/sysupgrade 配置备份 | 不能；默认清单遗漏上述业务数据，`-k` 仅增加软件包清单 | 重装相容固件、重装所需软件包后恢复网关配置 |
| 仅保存系统分区和 overlay | 不完整；遗漏 `/dev/nvme0n1p4` 上的 Docker 和业务数据 | 系统恢复，仍需业务数据备份 |
| PBS 文件级备份系统和完整业务数据 | 显式纳入 `/mnt/data`、Docker 数据根及全部挂载来源后可覆盖文件；需协调停止写入 | 可以提取文件，但不是可直接写回启动的整盘镜像 |
| 正常停机后备份完整 NVMe 磁盘 | 可以覆盖当前本地系统、镜像、容器状态文件、卷与挂载目录；须包含数据分区 | 整机恢复；恢复整个镜像会同时回退所有业务 |

`sysupgrade` 生成文件清单并用 tar 打包，不会协调数据库停写；即使手动把业务目录加入清单，也不能据此保证运行中 MySQL/Redis 的一致性。整盘冷备应从救援环境读取静止磁盘，期间网关和容器不可用；当前 ext4 布局没有现成快照层，在线读整块磁盘不能视为一致性镜像。

PBS 客户端默认跳过内部挂载点，因此仅备份 `root.pxar:/` 不会自动包含独立分区 `/mnt/data`。文件级整机备份须显式增加该归档或使用 `--include-dev`，核对排除规则；完整 Docker 数据根的一致性捕获还需停止相关容器及 Docker daemon。原生 `.img` 支持块设备镜像，但不会自动使运行中的磁盘一致。依据见 [PBS 客户端文档](https://pbs.proxmox.com/docs/backup-client.html)。

官方依据：[OpenWrt 24.10 sysupgrade 源码](https://github.com/openwrt/openwrt/blob/openwrt-24.10/package/base-files/files/sbin/sysupgrade)、[Docker 数据目录](https://docs.docker.com/engine/daemon/)、[Docker volumes](https://docs.docker.com/engine/storage/volumes/)。

## USB 中转 P2V 迁移路线（待实施）

用户已接受午夜停服，并提出先将现有系统保存到 USB，再在原 NVMe 安装 PVE，最后导入 iStoreOS 虚拟机；新网关 PVE 加入 pve0/pve1 集群，形成三节点并移除 QDevice。按此方向规划，整盘冷备作为迁移回退副本，长期整机备份由 PVE/PBS 承担。下文 `gateway-backup.sh` 仍只实现原来的业务文件备份，`backup all` 不会创建或迁移虚拟机。

用户已确认有 16 GB 和最大 500 GB 的 USB 设备，并能保证新网关与 pve0/pve1 中至少一台同时在线。本次按 USB 保存未加密镜像文件的路线准备；未来网关 VM 的 PVE/PBS 备份也按不启用客户端加密规划，现有 PVE/PBS 设置尚未更改：

| 设备 | 用途 |
| --- | --- |
| 16 GB USB | Ubuntu 24.04 LTS amd64 Live 救援启动介质；完成副本验证后，可分阶段重写为 PVE 安装介质 |
| 500 GB USB | 直接接网关，在救援系统中保存完整原始磁盘镜像文件；迁移期间保留原始镜像，不在它上面缩容 |
| pve0 的 `local-zfs` | 放置用于缩容、虚拟硬件适配和隔离试启动的工作副本；本次只读检查可用约 878 GiB |
| 原 256 GB NVMe | 副本验收后安装 PVE，再承载正式 iStoreOS VM |

Ubuntu 24.04 LTS 的 **amd64** Live ISO 可用于本次救援，目标是 Intel N100 网关。Desktop 版进入 **Try Ubuntu**；若手头已有 `live-server-amd64.iso`，可从安装器 **Help → Enter shell**（或 F2）进入终端，不推进磁盘安装步骤。Live 环境的基础磁盘与校验工具可完成本地整盘复制；缩容和 P2V 转换仍在 pve0 的工作副本上进行。进入 Live 后先确认源 NVMe、目标 USB 盘及维护网卡，保持 NVMe 各分区未挂载，只将目标 USB 文件系统挂载用于保存镜像。依据：[Ubuntu 24.04 镜像](https://releases.ubuntu.com/24.04/)、[Ubuntu Server 安装器 Shell](https://github.com/canonical/subiquity/blob/main/doc/tutorial/operate-server-installer.rst)。

本地键盘/显示器操作不依赖 SSH。若需从 Mac 远程继续操作，应在切换前准备好救援环境的 SSH 服务、访问方式和静态地址；不能假定 Desktop Live 已提供 SSH 服务端。核对到的官方 Desktop 镜像清单包含 coreutils、e2fsprogs 等基础工具，但未列出 openssh-server；首次本地备份不必为此依赖断网后的软件安装。当前尚未下载 ISO、制作启动盘或安装额外软件。

500 GB 是用户提供的标称容量；制作前仍需识别实际设备、已有数据和空闲空间。保存未压缩原始镜像需至少 256060514304 字节空闲及文件系统余量，并使用支持大文件的文件系统，不能使用 FAT32。不要计划在 500 GB 设备上同时保存两份完整的 256 GB raw 镜像。制作启动盘、格式化或覆盖设备不属于容量确认授权。

同次只读检查中，pve2 的 `mainpool` 仅剩约 72 GiB，因此本次选择 pve0 承载工作副本。pve0 的 `local` 与 `local-zfs` 不能作为两份独立可用容量相加；实际创建和导入前需再核对可用空间。网关当时只检测到原 NVMe，尚未检测到 USB 存储，也未核验用户这两件介质的型号、文件系统和现有数据。

2026-10-03 只读检查确认：N100/4 核、约 8 GB 内存、UEFI 启动，源盘 `/dev/nvme0n1` 为 **256060514304 字节**。四个分区依次承载 boot、squashfs 固件、overlay 和 `/mnt/data`；根分区使用 PARTUUID，数据分区使用 UUID。VirtIO PCI/块设备/SCSI/网络、AHCI 和 USB storage 驱动均已注册，可支持后续 P2V 验证，但尚未完成虚拟机试启动。

P2V 整体保留现有 iStoreOS、Docker 镜像和容器记录、匿名卷及 bind mount 目录，包括 Redis、Hermes 共享卷和 CN Proxy 的身份文件。主要适配项是 UEFI 启动、虚拟磁盘、WAN/LAN 网卡及旧 qnetd 自启动配置；不必在本次同时拆分或重新部署每个业务。

**USB 有两种用法。** 保存完整磁盘镜像文件即可作为 `qm disk import` 的来源，不要求该 USB 自己能启动。若还要从 USB 启动原 iStoreOS，则需完整可引导克隆并验证所有挂载都来自 USB。克隆盘与原 NVMe 会有重复 UUID，不能仅凭出现登录界面就认为 USB 已独立启动；验收时应暂时断开原 NVMe，或明确处理副本的 UUID 与启动/挂载引用。不要让运行中的 USB 系统同时作为 P2V 导入源。

**NVMe 容量规划。** 原 256 GB NVMe 安装 PVE 后还要容纳宿主系统，不能将同样大小的虚拟盘全额分配回去；稀疏格式虽可能暂时导入，仍有超配风险。以 **128 GiB 虚拟磁盘**作为迁移工作副本的初始目标，在副本上先检查并缩小 ext4 文件系统、再缩分区及镜像；最终容量以缩容检查、业务增长空间和实际 PVE 存储容量为准，原始完整镜像保留。PVE 使用 ext4/LVM-thin 的安装布局，先预留 root、swap 和 VG 空闲，再确认 VM 磁盘及余量可放入本地池。格式转换不等于文件系统缩容，不能直接截断镜像。依据：[QEMU 镜像工具](https://www.qemu.org/docs/master/tools/qemu-img.html)、[PVE 安装分区参数](https://github.com/proxmox/pve-docs/blob/master/pve-installation.adoc)。

迁移顺序：

1. 先确认 pve0/pve1 均在线，且它们之间的集群通信不会因网关停机而断开。核对 500 GB 目标设备及空闲空间，通知停服，从 16 GB 救援盘启动；源 NVMe 的分区保持未挂载，在本机将完整磁盘保存为外置盘上的 `gateway-original.img` 文件，包含 `/mnt/data`。检查镜像大小、完整性和可读取性；原 NVMe 暂时保留。
2. 首份冷备完成后重启原 iStoreOS 恢复网络，再将镜像传到 pve0 的工作存储，导入隔离测试 VM。外置盘保留原始镜像；缩容和虚拟硬件适配在 pve0 的工作副本上完成。采用匹配的 UEFI 启动和磁盘驱动，调整虚拟 WAN/LAN 映射，验证 Docker 数据、先验收小智再核对其余业务。测试 VM 不连接生产 LAN，避免重复 `192.168.1.1`、DHCP、MAC 或 qnetd 身份。
3. 若测试后旧网关继续服务，正式切换前需再次停服，把后续业务数据更新到最终迁移副本并复核适配。确定副本可恢复后，才在 NVMe 安装兼容现有集群版本的 PVE；配置宿主静态管理地址与 WAN/LAN 网桥，保持空节点，暂不创建生产 VM。
4. 两个旧节点在线且仲裁正常时，先从集群执行正式的 QDevice 移除，再加入新网关节点，确认三节点、每节点一票和 quorum。新节点加入前不得已有 VM 或 LXC，因为加入会覆盖 `/etc/pve` 并继承集群存储配置。
5. 新节点加入完成后，再将已验证的最终副本导入 PVE 管理的虚拟磁盘，使用集群内空闲 VMID。PVE 宿主使用另一个固定地址，iStoreOS VM 保留 `192.168.1.1`；映射虚拟网卡、确认数据分区挂载，再恢复业务。QDevice 已解除后，检查并停用旧 qnetd 容器及相关自启动/守护脚本。
6. 验证路由、DNS、Docker 数据和应用功能，再为整台 VM 配置 PVE/PBS 备份并做隔离恢复验证。另保留 PVE 宿主的网桥和管理配置，USB 原始副本保留到迁移与恢复均验收完成。

**管理路径不一定需要独立物理网或 VLAN。** 现有 LAN 可以承载固定地址的 PVE、PBS 和管理电脑，前提是 LAN 二层转发由宿主网桥/交换机提供，而不是依赖 iStoreOS VM。必须验证网关 VM 关闭时仍能访问 PVE/PBS、节点之间仍能通信；若现有节点互通依靠旧 OpenWrt 的物理 LAN 桥，迁移期也要先处理该链路。

2026-10-04 的只读网络核对进一步确认：网关 LAN 为静态 `192.168.1.1/24`，WAN 使用 DHCP；网关给 LAN 提供 DHCP，地址池为 `.150–.246`、租期 24 小时。Mac 当时经 Wi-Fi `en0` 使用 `192.168.1.228`，DHCP 服务器为 `.1`；已有 USB 2.5G 有线网卡 `en9`，当时未接通。网桥转发表显示 Mac 的实际 Wi-Fi MAC 从 **eth1** 接入，而 pve0/pve1 的 MAC 均从 **eth2** 接入。用户随后确认 eth2 下游有交换机，可将 Mac 直接有线接入；接线后的实际路由尚待核验。

维护连接采用这台独立交换机：Mac 的 `en9` 接入与 PVE 相同的 LAN/VLAN，网关救援系统通过原 eth2 对应的物理网口接入；救援环境中的网卡名称需按 MAC/PCI 对照确认。用户确认 500 GB 设备也可直接接网关后，本次选择本地 NVMe 到 USB 镜像文件的复制路径，大文件复制不经过 Mac 或 LAN；Mac 用于管理和查看进度，首份冷备结束后恢复原系统网络，再向 pve0 传送测试副本。交换机保持供电，Mac 和救援系统使用先核实未占用的静态地址；另核对 PVE/PBS 固定地址及 PBS 的实际连接路径。

验收时确认 Mac 到 pve0/pve1 的流量实际使用有线 `en9`，以 IP 访问而不依赖网关 DNS；网关原系统停机后，这些连接仍应可用。Mac 有线口负责本地维护路径，Wi-Fi 可断开或切到手机热点维持外网，避免两个接口在同一 LAN 上造成路径混淆。此接法维持本地备份/管理通信，不会代替已停机网关的互联网出口。无需为了此次迁移把所有家庭终端改为静态地址。已取得的 DHCP 地址可能在剩余租期内继续使用，但不作为维护保障；租期 24 小时也不等于当前仍剩 24 小时。依据：[RFC 2131](https://www.rfc-editor.org/rfc/rfc2131)。

首次本地复制可通过现场控制台执行，不需要 LAN 传送镜像；后续的远程管理、P2V 验证和集群操作仍需准备并验证维护连接，网关停网窗口仍然存在。若要求该窗口家庭网络持续上网，则需要独立临时路由器接管 WAN、DHCP 和 DNS；单独迁移 DHCP 不能维持网关转发，也不能恢复消失的 LAN 网桥。上述方案均未执行网络变更。

**三节点无 QDevice 需要至少两票。** 目前 pve0/pve1 为两节点加 QDevice、共三票。用户已确认能保持新网关与 pve0/pve1 中至少一台同时在线，可按三个实体节点的默认三票规划，pve2 仍不计入该集群票数。若临时只开网关、另两台都关闭，网关节点重启后的 VM 自动启动默认会等待 quorum；不以常态化降低预期票数绕过这一设计。本轮按网关 VM 固定运行在新网关节点规划。

上述顺序依据 [Proxmox 集群文档](https://github.com/proxmox/pve-docs/blob/master/pvecm.adoc) 的 QDevice 移除及空节点加入要求；自动启动等待仲裁可见 [PVE startall 实现](https://github.com/proxmox/pve-manager/blob/master/PVE/API2/Nodes.pm)。当前 PVE 的 `qm help disk import` 已只读核对。尚未制作 USB、修改磁盘、安装 PVE、迁移业务、加入节点或移除 QDevice。

## 独立业务范围

[脚本内的业务定义](../../scripts/gateway-backup/gateway-backup.sh) 使用已核实的容器名，表中顺序就是启动顺序，停止时反向执行。每份快照还包含 `metadata.pxar`。

| 业务名 | PBS 组 | 容器（启动顺序） | 原生归档与来源 |
| --- | --- | --- | --- |
| `xiaozhi` | `host/gateway-xiaozhi` | `xiaozhi-esp32-server-db`、`xiaozhi-esp32-server-redis`、`xiaozhi-esp32-server`、`xiaozhi-esp32-server-web`、`xz-mqtt-gw` | `xiaozhi.pxar` ← `/mnt/data/xiaozhi`；`mqtt.pxar` ← `/mnt/data/xiaozhi-mqtt-gateway`；`redis.pxar` ← Redis 的 `/data` volume |
| `hermes` | `host/gateway-hermes` | `hermes`、`hermes-webui` | `hermes.pxar` ← `/mnt/data/hermes`；`hermes-source.pxar` ← `hermes` 的 `/opt/hermes` 共享源码 volume |
| `open-webui` | `host/gateway-open-webui` | `open-webui` | `open-webui.pxar` ← `/mnt/data/open-webui` |
| `codex-proxy` | `host/gateway-codex-proxy` | `codex-proxy` | `codex-proxy.pxar` ← `/mnt/data/codex-openai-proxy` |
| `cn-proxy` | `host/gateway-cn-proxy` | `cn-proxy` | `cn-proxy.pxar` ← `/etc/sing-box`，包含 `ts-state` 节点身份 |
| `qnetd-witness` | `host/gateway-qnetd-witness` | `qnetd-witness` | `qnetd.pxar` ← `/mnt/data/qnetd`，包含状态、Compose 及 guard/bootstrap 脚本 |
| `youtube-mcp` | `host/gateway-youtube-mcp` | `youtube-mcp-youtube-mcp-1` | `youtube-mcp.pxar` ← `/mnt/data/xiaozhi/youtube-mcp` |

小智使用原生 `--exclude /youtube-mcp`，相对于归档根目录排除独立子项目；备份小智时 youtube-mcp 的容器保持原状态。youtube-mcp 的业务定义 不带该排除项。Redis 和 Hermes 的卷路径只按表中明确的容器、挂载目标读取 Docker inspect 的 `Source`，因此无需固定匿名卷或带版本的卷名。

CN Proxy 的 Tailscale 身份位于 `/etc/sing-box/ts-state`，依据见 [CN 出口代理指南](cn-exit-singbox-proxy.md)。它随配置目录捕获。

`all` 始终排除 qnetd，并在输出中明确说明。qnetd 必须先在单独安排的 quorum 维护窗口中停止，再显式调用 `backup qnetd-witness`。工具发现 witness 运行时立即拒绝，不负责停机或维护决策；备份完成后也保持停止，由维护操作者决定恢复时间。

## 配置与运行

在数据所在的 Linux 网关运行，使用其本地 Docker daemon、已有 Bash、Docker、flock、xargs 和官方 PBS 客户端。脚本清除 `DOCKER_CONTEXT`，固定 `DOCKER_HOST=unix:///var/run/docker.sock`，确保容器与数据来自同一主机。以能读取全部业务文件和 Docker 卷的 root 身份执行。依赖安装和凭证下发需先获授权。

[脚本](../../scripts/gateway-backup/gateway-backup.sh) 顶部集中放置客户端路径、停服等待时间、共享锁目录和 PBS 仓库参数；业务容器和来源目录在同一文件的 `case` 中维护。客户端默认从 PATH 查找，也可将 `client_bin` 改为实际安装路径。只允许可信管理员修改脚本。

外部控制器在运行时导出 `PBS_REPOSITORY`（格式 `user@realm!token@server:datastore`）和 `PBS_PASSWORD`（PBS 登录 Token）；服务器证书需要显式信任时，再导出 `PBS_FINGERPRINT`。仓库地址也可直接写入脚本顶部。Token 从 [Ansible Vault](../architecture/ansible-vault-architecture.md) 取得，通过进程环境注入，无需落地配置或凭据文件，也不要写入脚本或命令历史。每次备份明确使用 `--crypt-mode none`，无需加密密钥或密钥口令。

配置权限时，为 token 和其所属用户分别授予目标 datastore/namespace 的 `DatastoreBackup` 角色；token 的有效权限受所属用户限制。该角色可备份和恢复自己拥有的备份，已有组还需核对 owner 是否允许当前身份写入。停服前的 `snapshot list` 成功只证明可以读取列表，不能证明具有写权限。依据见 [PBS 权限与角色说明](https://pbs.proxmox.com/docs/user-management.html)。

所有使用此版本的单业务和批次调用必须使用同一 `lock_dir`，默认 `/var/lock`。它们共用 `gateway-backup.lock`，原生 flock 从读取运行状态前一直持有到完整批次的重启和元数据清理结束；锁文件留在原位置。并发调用在任何 Docker/PBS 操作前非零退出，包括不同业务之间的调用。该锁协调本工具，维护窗口中仍需避免人工部署或其他工具同时改动所选业务。

操作者还需核对各来源目录中的原生 `.pxarexclude` 规则和内部挂载点。必要的内部挂载点应显式加入脚本对应业务的 `sources`，或通过原生 `--include-dev` 纳入。保留小智的 `--exclude /youtube-mcp` 隔离边界，逐项核对排除和重新包含规则，避免用宽泛规则改变独立业务的备份范围。

以下为交给外部控制器的调用（仓库内示例路径；网关使用 `/opt/gateway-backup/gateway-backup.sh`）：

```bash
bash scripts/gateway-backup/gateway-backup.sh backup all
```

固定顺序为 **小智 → Hermes → Open WebUI → Codex Proxy → CN Proxy → youtube-mcp**。脚本输出每项进度和独立 PBS 组结果，不需要 cron 或外层循环。每项的备份、原容器启动尝试和元数据清理全部成功后才继续；任何一步失败或收到取消，队列立即停止，保留非零退出码并标出当前业务。只有六项全部完成才返回 `0`；`docker start` 成功仅表示启动请求被接受，应用可用性由调用方另行检查。

单业务用法仍然可用：

```bash
bash scripts/gateway-backup/gateway-backup.sh backup xiaozhi
```

将 `xiaozhi` 替换为表中另一个业务名即可选择它。单业务和 `all` 中的每项都使用自己的 `host/gateway-<business>` 组及表中的原生归档。

停服前检查认证环境变量、源目录、两个必要卷、容器状态以及 PBS 列表读取。MySQL/Redis 必须已经停止且退出码为 `0`、没有 OOM 标记，才能物理捕获。小智按 MQTT → Web → 后端 → Redis → MySQL 停止；原先停止的容器不被启动。退出时按表中正序尝试启动所有原先运行的容器，实际业务可用性由演练中的应用检查确认。

Docker inspect 可能包含环境变量和凭证，采集时暂存于本次私有临时目录：目录模式 `700`、文件模式 `600`、`umask 077`。容器 inspect、原生 `docker image inspect` 输出（包含 `RepoDigests` 和平台）及原运行容器名通过未加密的 `metadata.pxar` 保存，退出时清理本次临时目录。此目录仅有重建参考信息，业务文件由客户端直接读取。

## 网关本地快照检查

2026-10-03 的只读存储检查确认：`/mnt/data` 和 Docker volumes 位于直接使用 `/dev/nvme0n1p4` 的 ext4 文件系统；根目录 overlay 的底层是 `/dev/nvme0n1p3` 上的 ext4；数据卷没有 LVM/device-mapper 层。系统虽有 `btrfs` 命令，实际文件系统仍是 ext4。当前布局没有已可用的原生文件系统快照路径，检查没有修改磁盘。

因此本实现继续停服后直接上传，不加入快照或数据暂存。顺序执行使各业务依次停服；每项仍需等自己的上传结束后再启动，不能缩短单个业务的上传停机窗口。

## 使用原生命令列举和还原

列表、归档检查与还原直接使用官方客户端。先在已获授权的隔离 Linux 演练机上通过上述环境变量提供同一 PBS 仓库与认证信息，并选择 `snapshot list` 返回的实际快照。示例日期是占位值。

```bash
umask 077
proxmox-backup-client snapshot list host/gateway-xiaozhi
snapshot='host/gateway-xiaozhi/2026-10-03T00:00:00Z'
proxmox-backup-client snapshot files "${snapshot}"

restore_root="$(mktemp -d /tmp/xiaozhi-restore.XXXXXXXX)"
# Each archive gets a new, empty target under this private directory.
proxmox-backup-client restore "${snapshot}" xiaozhi.pxar "${restore_root}/xiaozhi" --crypt-mode none
proxmox-backup-client restore "${snapshot}" mqtt.pxar "${restore_root}/mqtt" --crypt-mode none
proxmox-backup-client restore "${snapshot}" redis.pxar "${restore_root}/redis" --crypt-mode none
proxmox-backup-client restore "${snapshot}" metadata.pxar "${restore_root}/metadata" --crypt-mode none
```

其他业务按表中的组和归档名还原，每个归档使用独立空目标。例如 Hermes 需要同时还原 `hermes.pxar`、`hermes-source.pxar` 和 `metadata.pxar`。后续若恢复验收，需记录客户端版本、上述四份归档的还原结果及无需加密密钥的证据。先确认原生客户端完成下载和归档还原，再人工恢复服务：

1. 阅读还原出的 Compose、配置、`metadata/docker-inspect.json`、`metadata/docker-images.json` 及 `running-containers.txt`。核对镜像摘要、平台、数据库版本、挂载、端口、网络及原运行状态；inspect 仅作为资料读取。有 `RepoDigests` 的镜像按摘要从原镜像仓库取得；本地构建且无仓库摘要的镜像依据归档源码人工重建。快照保存的是文件与元数据。
2. 在隔离环境准备相容的 Linux/CPU 架构、目录和独立网络。准备空的数据目录及新卷，再按记录接入 Compose。MySQL 使用相同数据库版本；Redis 接入 `redis.pxar` 还原的数据，Hermes 的两个容器继续共享恢复后的源码卷。
3. 如需恢复现有部署，先取得切换授权并通知停机，按脚本中容器列表的反序停下所选业务。保留它原有数据和卷供人工回退，再把已检查的还原内容放到目标位置。数据库目录整体替换为还原的数据，避免将新旧物理文件混合。
4. **小智恢复必须保留 `/mnt/data/xiaozhi/youtube-mcp` 原位置。** 回填前，将该根目录中除 `youtube-mcp` 外的所有当前顶层条目保留到业务根目录外的私有回退目录，包括隐藏项及快照后新增项；确认根目录只剩独立子项目，再回填小智归档，避免混合版本。不得整体删除或替换父目录。独立 youtube-mcp 恢复只处理该子目录，其他小智文件保留。该业务的容器、网络与停机决定仍由其独立维护负责。
5. 按归档配置人工重建所选业务容器，先保持全部停止，再按表中顺序只启动 `running-containers.txt` 中原先运行的容器。小智先启动 MySQL/Redis 并确认数据库正常，再启动后端、Web 和 MQTT；qnetd 仍遵循单独批准的 quorum 恢复安排。
6. 检查业务数据与应用功能。小智记录 MySQL/Redis 内容、上传文件、配置/补丁、Web/HTTP/WS/MQTT 功能、停机起止，以及 youtube-mcp、Codex Proxy 等无关容器的前后状态。`docker start` 返回成功只是启动请求成功。用户已反馈全业务备份成功；上述恢复步骤保留供后续演练，目前暂缓执行。

## 失败处理与离线验证

| 情况 | 处理 |
| --- | --- |
| 全局锁已占用、PBS/认证不可用、源目录或卷不可用 | 当前业务停服前非零退出；不进入后续业务 |
| 停服失败、MySQL/Redis 非干净退出 | 拒绝物理备份，尝试恢复原先运行的容器 |
| 客户端备份失败或 INT/TERM 中断 | 取消信号转发给该客户端并等待其退出，随后才尝试原容器重启、清理私有元数据；取消仍返回 `130`/`143`，即使客户端最终返回 `0`；不进入后续业务 |
| 重启失败 | 报出具体容器并继续尝试其余原运行容器，非零退出且停止队列；已成功上传的快照可能仍存在 |
| 私有元数据清理失败 | 报出目录并非零退出，停止队列；已有备份错误码保留 |

正常重启或元数据清理期间首次收到 INT/TERM 时，完成当前清理后退出，停止剩余队列。重复信号不会中断清理，已有错误码保留。强制杀进程或主机掉电无法执行 EXIT 清理，需人工核对并恢复服务。还原后的切换、重建和回退由操作者明确执行。

批次失败后，已完成业务的快照保留。先核对失败业务的容器启动状态，并用原生 `snapshot list` 确认它是否已经生成快照，再按原顺序用 `backup <business>` 处理需要补做的业务及剩余项目。直接重跑 `backup all` 会从小智重新开始，再次备份此前已完成的业务。

```bash
for file in scripts/gateway-backup/gateway-backup.sh tests/gateway-backup/gateway-backup-test.sh; do
    bash -n "${file}"
done
shellcheck -s bash scripts/gateway-backup/gateway-backup.sh tests/gateway-backup/gateway-backup-test.sh
bash tests/gateway-backup/gateway-backup-test.sh
```

离线测试使用临时虚构目录和针对本适配器的 Docker/PBS 命令替身，验证七组原生参数、本机 Docker 固定、两种卷解析、停启顺序、独立子项目排除、锁覆盖、容器与镜像元数据权限及错误清理。批次场景实际执行六项，检查每项清理完成后才进入下一项、qnetd 排除、中途失败停止队列，以及批次/单业务并发拒绝。取消场景覆盖客户端延迟退出并返回 `0`、PID 登记窗口、清理期间重复 TERM 和正常清理阶段首次取消；数据库场景独立覆盖非 OOM 异常退出和 OOM 标记。无加密测试验证适配器传入 `--crypt-mode none`、不检查或传入密钥的命令契约。测试所用 Python 仅在开发机运行；不连接真实 Docker daemon、PBS 或读取真实凭证，也不证明实际归档的加密状态、真实数据库恢复或应用可用性。

参考：[PBS 客户端用法](https://pbs.proxmox.com/docs/backup-client.html)、[原生命令手册](https://pbs.proxmox.com/docs/proxmox-backup-client/man1.html)。
