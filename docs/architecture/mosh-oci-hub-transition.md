# Mosh 经 OCI Hub 接入现有工作区

当前状态：VM501/502/504–508 已接入新 Hub，VM509 底层已改为 10.236.9.0/30，VM500 旧员工入口已退役。见 [当前迁移记录](../deployment/2026-10-30-demo-test-hub-retirement.md)。以下为被替代的历史方案，不是当前运行状态。

历史记录日期：2026-10-30。当前执行方案已改为[新建 VM509](../deployment/mosh-oci-hub-vm509.md)，不改造 VM502；独立 PVE 网络、VM509 创建与 hook 绑定、Spoke配置及中国端到端网络实测已完成；正式Mosh接入与交付尚未验收。以下原 VM 接入设计仅保留为被替代的历史方案，不能用于恢复旧 apply。OCI Hub 已首次初始化，员工尚未切换。实际部署记录见 [试点部署契约](../deployment/mosh-oci-hub-pilot.md)。
源码基线：IaC `origin/main` 的 `f1e121b`，包含 Mosh #183 和 OCI Hub #186。

## 目标与拓扑

让当前员工逐步改用普通公网 OCI Hub 访问原工作区，保留 Mosh 的输入预测和重连能力。本轮不经过 GA2。设备与原工作区 VM 分别作为独立 WireGuard Spoke；OCI 解封装后路由到本人 VM，不终止员工 SSH/Mosh 会话，也不做内层 SNAT。

```text
员工电脑 Mosh
  └─ 员工设备 WireGuard → OCI 公网 UDP 51824 / wg-users
                             └─ 按设备与 VM 映射路由、隔离和计量
                                  └─ wg-workspaces / UDP 51825 ← VM 主动建立 WireGuard
                                       └─ 原员工 VM 的 SSH + mosh-server
```

SSH 用于启动会话，后续 Mosh 使用隧道内 UDP。SSH/SFTP 与 VM 内 `workspace-login` 继续可用。Mosh 不承载文件传输或桌面；个人 Claude 登录继续在本人 VM 内完成。

先在管理员保留的 VM502 和一台独立测试设备验证。之后员工保持原 VM、磁盘和个人环境，逐设备交付新路径。既有方案与新方案并行；不统一替换所有旧设备包，不退役 VM500。

## 当前实现与缺口

| 项目 | main 中的实现 | 本次需要补齐 |
| --- | --- | --- |
| Mosh 终点 | VM500 的设备账号启动 mosh-server，再固定 SSH 到本人 VM | 在本人 VM 原生启动 mosh-server，消除中间 SSH 会话 |
| 启动命令 | `employee-mosh` 是网关 dispatcher 识别的命令 | 新路径直接使用 VM 的 mosh-server；不能照搬网关命令 |
| Hub 转发 | `boundary.py` 放行本人 VM 的 TCP 22/8443 | 增加按设备分配的 Mosh UDP 目的端口和受限回包 |
| Hub 外层来源 | `ga2_sources`，要求 /24 或更窄 | 显式区分直连设备来源和 GA 来源，贯穿云防火墙与本机规则 |
| VM SSH 授权 | `employee-workspace` 按单一 profile 协调授权 | 支持现有网关公钥与新设备公钥并存，逐项撤销 |
| VM 创建 | Hub profile 面向新 VM，首次停止并校验隔离 | 增加已有 VM 接入操作，不把原 VM 纳入另一份新建资源 |
| VM 底层网络 | 原工作区出站依赖 VM500 | 首次新路径验收前接入独立 PVE 路由边界，不能复用旧出口 |

依据：`ansible/roles/employee-access/files/employee-dispatch.py`、`ansible/roles/employee-access/tasks/mosh-pilot.yml`、`ansible/roles/employee-workspace/tasks/authorization.yml`、`scripts/oci-hub/boundary.py` 与 [Hub 部署契约](../deployment/oci-hub-workspace-prototype.md)。源码配置不代替实际部署状态核对。

## 新路径从首次验收起独立

不再采用“先经 VM500、之后再去依赖”的安排。旧中继只是独立保留的对照路径；新路径的身份、握手、数据、日常开发公网出站和运行恢复均不得要求 VM500 或原站点隧道在线。已生成的 VM500 例外审批不再用于执行。

```text
新设备 WG → OCI Hub → VM502 的 WG Spoke → 原生 SSH/Mosh
                         ↑
VM502 新网卡 → 独立 /30 VNet → PVE 三层网关 → OpenWrt WAN → Internet
```

VM502 保留原磁盘、旧网卡和原入口；新增网卡属于独立 VNet 和 /30，由 PVE 转发边界执行隔离。新网卡不能直接接到管理 LAN。VM 的新默认公网出口及 OCI endpoint 路由必须指向 PVE 网关，旧网卡仅保留旧入口所需的精确回程；不得用旧网关作为新接口路由失败的备用。PVE 不做 SNAT，OpenWrt 使用批准的聚合回程路由及 WAN NAT。

复用原 Terraform VM resource 声明第二张网卡，不把 VM502 再放进新建工作区 module/state。需补齐原 hook 与新 VNet/net1 的联合就绪校验：现有 PVE Hub controller/hook 固定 net0/tap i0，不能原样拿来保护 net1，也不能覆盖原 hook 后丢失旧边界检查。边界就绪前保持新网卡断开，不预先承诺热插拔或无重启。

2026-10-30 只读核对：VM502 只有 net0，默认路由经旧网关；PVE2 SDN zones/vnets 为空。因此独立底层尚未部署，已有 OCI 服务或源码测试不能算作独立接入验收。

独立性验收须记录 VM 默认路由、OCI endpoint 的源地址/接口/下一跳、新旧物理出口计数和真实握手。在不影响其他员工的批准测试窗口，阻断本试点经旧路径到 OCI 的流量后，新 SSH/Mosh/SFTP 与公网开发访问仍须成功；失败时拒绝验收，不能静默回落旧出口。无须为此关闭承载其他员工的 VM500。

## Mosh 权限和会话生命周期

- Mosh UDP 仅在设备 overlay /32 → 本人 VM overlay /32 的已登记端口范围内放行；回包匹配反向地址、源端口范围和 established/reply。允许双方交换数据的 UDP conntrack 状态，拒绝跨设备范围和其他 VM。撤销映射优先于任何通用 established 放行。
- OCI 公网只开放批准的 WireGuard 外层端口，不开放 60000–61000。VM mosh-server 绑定 VM overlay 地址，包中的服务器 IP 使用该地址；不通过 SSH 转发传输 Mosh UDP。
- 沿用每设备独立端口范围，复用当前分配以降低员工理解成本；Hub 内新身份使用独立凭据和地址。多个设备访问同一 VM 时，端口范围不得重叠。
- VM 登录用户仍为 employee。Mosh 启动端必须固定自身设备的已登记范围；Hub ACL 才是设备隔离权威，不能依赖用户遵守启动参数。
- 沿用当前 604800 秒网络断连超时。它不是键盘空闲超时；会话恢复不等于命令已执行完成。
- Mosh-only 撤销关闭该设备的 UDP grant；规则不对旧 conntrack 广泛放行，因此旧会话也立即失去数据通路。完全撤销停用对应 peer。残留会话由网络断连超时回收，不新增逐进程登记器，不对共享 employee 用户整体 pkill。
- 设备完全撤销需停用 OCI peer、删除全部该设备映射并使在途连接失效。仅禁用 SSH key 不会切断已建立的 Mosh UDP。
- 员工拥有 VM sudo，同一员工各设备间的进程归属不是安全边界；跨员工隔离依靠 OCI 和 PVE。旧入口在并行期仍独立有效，停用新入口不能声称已撤销旧入口。

## 身份、凭据与管理员入口

继续使用主 checkout 的 `remotecc/employee-admin/onboard.sh --profile oci-hub`，新增明确的“接入现有 VM”操作，不创建第二套开户引擎。该操作的具体命令行是实施项，目前不可执行。

输入绑定现有 employee_id、device_id、VMID、VM 名称/节点、磁盘与网卡摘要；批准摘要包含新增网卡/路由、overlay、端口、SSH 授权、BWS 引用和交付对象。发现归属不符即停止。Terraform 接入计划必须不含 VM 替换、磁盘变更或意外新建工作区。

沿用新方案独立 BWS 项目和每设备记录；现有设备保留原 ID，新旧 profile 的 key/address/包各自独立。重跑复用本次新方案身份，不能轮换旧身份或把旧密钥复制进 Portal。OCI 不接收 SSH 私钥/BWS 令牌；BWS 保留新方案恢复权威。

VM 的 authorized_keys 由同一协调器生成两条路径所需的授权集合，附清晰所有权标记；保留原来限制选项。删除新方案授权时不删旧网关 key，不能依次运行两个互相覆盖文件的 role。原生 VM SSH host key 需要独立取得并 pin。

新包使用现有 v2 profile、独立 SSH alias 和隧道名，并新增可校验的 Mosh 目标地址与端口范围。公开客户端从包读取，设备端不猜测网关命令。保持 macOS/Linux 原生 Mosh、Windows WSL Mosh 的现有客户端约定；需要安装或系统授权时由员工确认。管理员工具仍仅在私有工程。

交付使用 Temp.sh HTTP POST 下载和现有微软邮件模板。真实验收绑定不可变包摘要后才允许上传/通知，发送前给管理员审阅。员工第一步使用 SSH 进入本人 VM；需要个人 Claude 登录时再运行 workspace-login，不要求先打开尚未启动的桌面。

## 直连 OCI 的公网来源策略

先使用测试设备实际公网 /32 和家中工作区出口 /32，经批准同时配置 OCI 网络安全组与 Hub 本机规则。公网地址改变时明确报来源不符，不能静默放宽为默认路由。

正式移动设备接入需要另行确定来源策略：可以批准仅 WG 外层监听面向动态公网来源，依靠 WireGuard 公钥认证和内层逐设备 ACL；该模式必须在输入中明确区分，保留管理面仅受信来源。现有脚本拒绝 /24 以上大网段，需要显式实现和审阅，不能偷偷修改现有 GA 源清单来绕过。

## 配额与可观测性

沿用每用户每月 5,000,000,000 字节、Asia/Shanghai、设备 RX+TX 汇总、5 秒采样和次月自动解除 quota 原因的约定。Mosh/SSH/SFTP 均经过 wg-users，同一段只计一次。配额服务仍复用 OCI 执行器、Portal 与 SQLite，不再新增另一份计量系统。

5 秒采样允许小额超用。达到额度时撤销新路径的该用户转发权限并停用其全部设备 peer，确认 SSH/Mosh/SFTP 活跃连接不能继续；月恢复不清除 admin/revoked 等其他原因。旧入口仍有自己的策略，新路径额度不能覆盖经旧入口的流量。

online 区分“近期 VPN 握手”“SSH TCP 连接”“Mosh UDP 活跃/会话登记”，不能把 Mosh 无 SSH TCP 判为无人在线，也不能因近期握手认定人在操作。查询失败返回未知，不用于自动关机。

## 实施顺序与验收

1. 只读核对 VM502、测试设备、OCI 可用资源与两边实际配置；确认地址/端口无冲突。独立规划最小改动，安装包、云防火墙/网络变更按精确范围批准。
2. 扩展 Hub ACL、请求/包字段和 VM 授权并存；给已有 VM 安装最小 Mosh 服务与 WG Spoke。补齐独立 PVE/第二网卡、路由和联合 hook，完成合成测试后生成新的精确部署 plan。
3. 用同一设备、VM、时间段交替采样旧直连与新 Hub，至少两轮各 30 次。SSH 使用会话内命令回显 RTT，报告中位数/P95/max/失败；UDP 另用固定次数的受控隧道内回显测试。记录是否启用 Clash TUN、实际 endpoint 路由/接口和后台流量，保持条件一致。
4. 人工对照 Mosh 输入、退格、Ctrl-C、命令返回和短暂断网恢复；Mosh 本地预测体感不能替代 RTT。确认 SSH/SFTP、workspace-login 保持可用。
5. 实测越权 VM、其他设备端口、OCI 管理面拒绝；撤销/恢复、网络超时与配额断开/次月恢复。配额跨月测试在隔离环境完成，不改生产系统时间。
6. 独立性、隔离及性能验收均通过后，再给自愿试点员工生成新包，审阅邮件后交付。不得先交付依赖 VM500 的临时版本。

实施时提供统一的 verify 命令与预期状态；不让员工 Agent 自由探测、修改其他 VPN 或通过管道灌入交互 Claude 测试。当前文档不把尚未实现的测试入口当作可执行命令。结果须能区分服务就绪、隧道握手、目标身份、Mosh 实际连接和人工验收。

不使用 GA2 后的 OCI 路径尚无本轮同条件结果；旧 GA2 数据不能用于承诺收益。若新路径 P95、丢包或稳定性不理想，保留旧入口并停止扩大试点。

## 回退

先停止试点设备的新隧道，恢复原 alias 使用旧包；原 VM 文件和 Claude 登录态无需迁移。已建立的 Mosh 会话不能跨终点搬迁，需要重新连接，先提示保存交互工作。

服务端只撤销本次新设备的 Hub 权限和授权，停止能确认归属的新增会话。按批准计划撤回新增 endpoint 路由与第二网卡；不回滚其他 SDN pending changes、不 flush 全局防火墙、不停止 VM500、不删除原工作区。保留 BWS、新方案月账、审批和测试记录供恢复。

## 已有基础代码与待修正入口

本任务分支已实现以下服务端基础能力。OCI 端已初始化，VM 侧尚未部署：

- Hub/PVE boundary 保持独立表；Hub 的 `pairs` 可选 `mosh_ports: [60030, 60039]`，按设备→本人 VM 放行，已有 UDP conntrack 也不能绕过撤销。未提供该字段的映射保持原 TCP 权限。
- Hub boundary 使用互斥的 `device_sources` 或旧 `ga2_sources`；OCI Terraform 对应提供同名互斥来源，保留旧规则资源地址。试点继续限制 /24 或更窄；没有放开动态公网来源。
- `employee-workspace` 的显式 `employee_workspace_hub_parallel_access=true` 生成新旧授权合集；普通重跑遗漏该配置或误用 native-only profile 时，在覆盖旧授权前拒绝。移除某台设备不清除旧网关和其他设备授权。
- `oci-hub-spoke` 拆出 `tasks/vpn.yml`；历史一次性 `deploy-oci-hub-mosh-pilot.yml`（现已移至私有执行记录）当时只处理一个明确的现有工作区，不执行 Terraform、不启动其他 VM、不配置桌面。校验目标主机、员工归属和 VM 主机名；需要已批准的新方案密钥与完整设备清单。
- VM 的 `workspace-mosh` 启动器调用原生 mosh-server，绑定 VM overlay，保留 7 天网络断连超时。Mosh 和 WireGuard 包安装默认关闭，只有另行批准 `oci_hub_mosh_install_authorized=true` 才执行。

真实设备启动命令将由公开客户端根据经过校验的新包产生，形态如下；这是供实施使用的命令模板，alias、SSH 配置路径与端口必须来自本设备包：

```bash
mosh --ssh='ssh -F <本设备SSH配置>' --server=workspace-mosh --port=<本设备端口范围> <新方案SSH别名>
```

私有 `onboard.sh --profile oci-hub` 仍是唯一管理员入口，终端候选包沿用 `access_mode=mosh` 和 `mosh_ports`。现有 `attach-mosh` 实现依赖 VM500 例外，仅只读核对 Terraform state，**不能用于当前独立目标**。需在同一入口补齐独立 PVE 网络、原 VM 第二网卡的受限 Terraform 计划、来宾路由和联合 hook 的审批/恢复，不另造 provisioning 引擎。原计划及其失败检查点只留作审计，不能恢复 apply。独立接入命令尚未就绪。

逐设备/配额访问撤销由 Hub grant/peer 阻断，这不代表终止了 VM 内残留 shell。断连超时负责最终回收，不为试点新增进程管理服务。源码已接通不代表真实网络、Mosh 体验或员工交付已通过；客户端更新也尚未发布。
合成校验入口与结果边界见 [OCI Hub 验证说明](../../tests/oci-hub/README.md)。实际试点前准备独立 PVE 网络、VM 和 OCI 运行条件，再生成具体计划；真实部署与交付继续按精确范围审批。
