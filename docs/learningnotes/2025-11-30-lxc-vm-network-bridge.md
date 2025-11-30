# LXC 与 VM 网络桥接拓扑学习笔记 (2025-11-30)

## 1. 背景与新增工作范围
本次新增与验证的内容：
- 为三台 Proxmox 宿主机 (`pve0/pve1/pve2`) 补充 `vmbr1` 虚拟桥接口及其管理 IP (192.168.1.50/51/52)。
- 在 NetBox 中用 `netbox_cable` 资源建模 VM 与宿主桥接的二层连接。
- 验证 LXC 容器 (ID 100, anki-sync-server) 网络模式为桥接而非端口映射/NAT。
- 整理 Linux Bridge、veth、端口映射、桥接模式差异概念并固化为知识点。

## 2. 核心概念定义
- Linux Bridge：内核提供的二层交换组件，行为类似软件交换机，多个接口加入后共享同一广播域，可直接进行 ARP、二层转发。
- veth Pair：成对出现的虚拟网卡设备，一端放入容器/命名空间中（如 `eth0`），另一端位于宿主机并可加入 bridge。实现容器与外部二层通信的通道。
- Bridge Mode（桥接模式）：虚拟机或容器直接通过 bridge 获得独立二层身份与网段内可路由 IP，无需宿主端口映射即可被其他主机访问。
- Port Mapping（端口映射）：常用于 Docker/NAT 场景，将宿主某 TCP/UDP 端口通过 DNAT 转发到内部应用，不赋予内部直接二层身份。
- NAT/MASQUERADE：内网地址出站时转换为宿主地址，入站需显式规则，内部无法被动直接接收同网段主机发起的二层发现与 ARP 请求。
- NetBox Cable：NetBox 数据模型中用于描述两端接口的物理/逻辑 Layer1 连接对象；对虚拟环境中“桥 ↔ 虚拟接口”关系进行结构化建模，便于拓扑可视化与查询。

## 3. 实际基础设施关系
- 宿主机：`pve0` 承载当前所有 VM 与 LXC。
- Linux Bridge：`vmbr1` 作为统一虚拟交换域，拥有管理 IP `192.168.1.50/24`（`pve1`、`pve2` 预建同名桥以便迁移时使用）。
- 虚拟机：`immich (101)`、`samba (102)`、`netbox (104)` 的 `tapXXXi0` 接口加入 `vmbr1`。
- LXC：`anki-sync-server (100)` 使用 veth (`net0` -> `eth0@if91`) 加入 `vmbr1`，直接获得地址 `192.168.1.100/24`。

## 4. 验证命令与结果
### 4.1 Bridge 成员查看
命令：
```
brctl show vmbr1
```
结果关键行：
```
vmbr1 ... enp1s0 fwpr100p0 tap101i0 tap102i0 tap104i0
```
说明：宿主物理接口 `enp1s0` 与多个虚拟接口/防火墙伪端口加入同一桥。

### 4.2 LXC 配置确认
命令：
```
pct config 100
```
结果片段：
```
net0: name=eth0,bridge=vmbr1,... ip=192.168.1.100/24
```
说明：明确指定桥接到 `vmbr1`，使用 veth 类型，分配静态 IP。

### 4.3 容器内网卡状态
命令：
```
pct exec 100 -- ip -br addr show eth0
```
结果：
```
eth0@if91 UP 192.168.1.100/24 ...
```
说明：容器内部拥有独立二层接口与完整 IPv4/IPv6 地址。

### 4.4 Bridge 自身地址
命令：
```
ip -br addr show dev vmbr1
```
结果：
```
vmbr1 UP 192.168.1.50/24 ...
```
说明：桥设备同时作为管理与默认网关接入点（提供二层交换 + 三层 IP 终端）。

## 5. 结论与判定依据
- 判定：LXC 容器网络模式为 Linux Bridge 直接桥接，不是端口映射/NAT。
- 依据：`pct config` 中 `bridge=vmbr1`；容器直接持有同网段可路由地址；宿主 Bridge 成员包含其 veth/tap 接口；未出现任何端口转发表或 DNAT 规则配置；访问模型与 VM 等价。
- 桥接优势：减少额外转发与 NAT 复杂度、保留真实源地址、易于在 NetBox 按接口拓扑呈现。

## 6. 与端口映射模式对比要点
| 维度 | 桥接模式 | 端口映射/NAT |
| ---- | -------- | ------------ |
| 二层身份 | 直接拥有，参与 ARP | 不直接参与，依赖宿主 DNAT |
| 可见性 | NetBox 可建模接口与 cable | 仅表现为宿主端口开放 |
| 源地址保留 | 是 | 可能被替换为宿主地址 |
| 配置复杂度 | 需要正确 IP/网关 | 需要映射规则与防火墙管理 |
| 迁移成本 | 可直接迁移与重新桥接 | 需重新配置映射规则 |

## 7. NetBox 建模实践
- 物理层：宿主机 `netbox_device` + 接口 `vmbr1`。
- 虚拟层：VM/LXC 使用 `netbox_virtual_machine` + 接口 `eth0`。
- 连接层：`netbox_cable` 将 `dcim.interface (vmbr1)` 与 `virtualization.vminterface (eth0)` 关联。
- IP 层：分别在接口对象上挂载 `netbox_ip_address` 资源。使得拓扑 → 接口 → 地址 → 服务层链条完整。

## 8. Terraform 与单位转换注意点
- VM/LXC 磁盘字符串（如 `300G`）需转换为 MB 提交到 NetBox：`300 * 1024 = 307200`。
- 统一在 NetBox 侧使用 `disk_size_mb` 避免与模块内 `disk_size` (字符串) 混用导致误解。

## 9. 常见排错提示
| 场景 | 现象 | 排查指令 |
| ---- | ---- | -------- |
| 容器无法出站 | 无默认路由 | `pct exec <id> -- ip route` |
| IP 冲突 | ARP 异常或日志警告 | `arping -I vmbr1 <IP>` |
| 未加入桥 | 不在 `brctl show` 列表 | `ip link show type bridge` + 检查 `pct config` |
| 宿主未转发 | 访问外网失败 | 宿主检查 `sysctl net.ipv4.ip_forward` |

## 10. 知识点摘要
- LXC 默认可使用 veth + Linux Bridge 获得原生二层接入。
- 与 Docker 端口映射相比，桥接模式更适合需要完整网络身份的服务（如内网发现、直接暴露多端口）。
- NetBox 建模推荐使用接口 + cable 表达桥接关系，提高拓扑检索能力。
- 规格与网络属性应从 Terraform 源文件同步到文档与 NetBox，保持“单一事实来源”。

## 11. 后续建议
- 若未来在 `pve1`/`pve2` 上迁移实例，只需新建/调整 cable 指向对应宿主 `vmbr1`，无需修改虚拟机接口资源。
- 可扩展：为服务添加应用层依赖标签（如数据库、缓存）以增强查询语义。
- 可以引入自动比对：定期采集 `pct config` / `qm config` 与 NetBox 登记值差异。

---
本笔记基于当日新增 Terraform 资源（`vmbr1` 接口与 IP、cable 连接）及实时 Ansible 验证命令输出整理。