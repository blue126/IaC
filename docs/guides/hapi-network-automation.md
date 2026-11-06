# HAPI 网络开户自动化

> **历史记录（2026-11-03）**：本文涉及的角色、playbook、脚本与测试已在 story 5.24 中删除，员工 VM 一侧改由 `hapi` role管理（默认随`prepare-employee-desktop.yml`的provision阶段部署），见[统一入口](hapi-unified-entry.md)。下文命令不可再执行，仅供追溯。

> **保留的网络能力与历史原型。** 独立HAPI开户候选已撤回；本页不提供当前员工开户入口。QA VM9101／9102和关联定时巡检已[回收](../planning/2026-10-31-hapi-qa-retirement.md)，网络代码与验收证据保留。当前员工操作约定见[wsctl流程](../deployment/oci-hub-provision.md)。

状态：现有bridge的端口ACL已在pve2两台新VM完成35项通信与11项生命周期验收；VLAN后端尚未实测，完整员工开户与公开应用入口仍未就绪。2026-10-30。

本阶段遵循“先自动化、用新VM验证、再逐台推广”。已获授权在pve2创建两台测试VM并部署只匹配它们tap端口的边界；没有修改既有业务VM配置、路由器或Cloudflare，也没有调用WireGuard开户入口。完整的员工申请、分配台账、BWS、身份登记和交付执行器仍待实现。真实执行记录见[两VM验收](../planning/2026-10-30-hapi-two-vm-pve2.md)。

## 1. 所有权与执行顺序

| 阶段 | 实现与职责 |
|---|---|
| 计划 | `scripts/plan-hapi-network.py` 读取私有 manifest，可校验最小化的PVE快照；输出当前／候选摘要、精确资源与规则预览，不联系服务、不自行挑选空闲地址 |
| 网络 | `deploy-hapi-network.yml`／`hapi-network` 经同一部署锁和检查点，校验现有bridge或管理独立SDN对象，应用VM外nft表、hook文件与开机规则加载 |
| VM | `terraform/modules/hapi-workspace-vm` 创建受保护、停止、禁止自动开机的 VM；固定本人 VNet、MAC、静态地址和已批准网关 |
| 实际绑定 | VM创建后重新运行网络角色；root仅为已分配且停止、尚无hook、名称／IP／MAC／bridge完全匹配的VM绑定门禁，使用配置digest防止并发覆盖。未知hook和运行中的无门禁VM拒绝处理 |
| 首次启动 | 管理员执行器先检查 `hapi-network.py hook --vmid VMID`，再显式启动；PVE `pre-start` 再检查一次，失败拒绝启动 |
| 服务和交付 | 启动后部署 `hapi-workspace`，完成两员工连通／拒绝验收，再启用控制面登记；网络模块不能自行宣称可交付 |

Terraform 仅复用通用 VM 模块，不接入旧员工 roster／state；本轮没有创建新的 backend 或 HCP workspace。调用方须固定仓库现用 provider `bpg/proxmox 0.70.0`，并为 HAPI 单独批准 state 绑定。SDN 对象由 Ansible 管理，不能同时交给 Terraform。VM500 继续承担接入控制面，员工出网走原路由器，代码没有 VM500 NAT 或默认路由改写。

当前pve2使用`attachment: access-bridge`：沿用现有vmbr0，不更改bridge、VLAN、路由或SDN对象；每VM独立tap ACL并固定可信来源IP、MAC及入口端口。`attachment: vlan`为另一条尚未实测的路径，其zone、tag及锁接口参照[Proxmox VLAN plugin](https://github.com/proxmox/pve-network/blob/master/src/PVE/Network/SDN/Zones/VlanPlugin.pm)和[SDN API](https://github.com/proxmox/pve-network/blob/master/src/PVE/API2/Network/SDN.pm)。VLAN路径缺锁接口或VLAN-aware bridge时拒绝写入，不降级。

## 2. 显式输入与部署前提

合成输入位于 `tests/hapi-workspace/network-fixture.json`，其中 VMID、VLAN、地址均不代表现网预留。真实 manifest 放入独立 HAPI 私有运行区；公开仓库不保存员工映射或真实分配。角色变量为 `hapi_network_manifest`；目标 inventory 分组为 `hapi_pve`，其 hostname 必须等于 manifest.node。

manifest包含节点、bridge、控制面／管理员源地址、DNS、额外保护网段、各VM的ID／VMID／MAC／地址／网关／enabled和真实`hook_file_id`。VLAN路径要求独立VNet／tag、非重叠子网和已核实trunk。access-bridge路径的每个`vnet`字段填实际共享bridge、`vlan`填null，并提供`trusted_peers`的IP、MAC和固定入口；允许共享LAN前缀，但拒绝重复地址／MAC及把员工tap当可信入口。IPv6全部拒绝。部署还必须提供`hapi_network_expected_manifest_sha256`：首次明确填`absent`，更新填获审阅的正式摘要，不能自动接受当前值。hook路径通过`pvesm path`解析，不能假定目标存储叫local。

真实部署前必须完成共享资源只读盘点：PVE 全局 VMID／MAC／地址、其他 state 所有权、现有 VNet／原生 VLAN、trunk 允许列表、物理交换机、路由器 VLAN 网关、回程路由和 NAT。`hapi-preflight.py`现已接入SDN写入前：读取集群所有QEMU／LXC的最小网络配置，拒绝VMID／名称／MAC／VNet、静态声明网段和原生NIC tag／trunk冲突；读取目标宿主接口，拒绝宿主地址及原生VLAN冲突。一个节点或来宾读取失败就停止，不以部分结果继续；不保存原始VM配置或其中的凭据字段。

这些检查仍不包含动态DHCP租约、未声明的来宾地址、NetBox预留、其他Terraform state及物理交换机／路由器占用；同名且网卡完全匹配也不能单凭名称证明Terraform所有权。SDN全局锁只能约束SDN写入，不能锁住其他管理员的VM创建或网卡修改。完整私有执行器仍须用独立分配台账、获批资源池与state所有权绑定来协调这些边界；不能将PVE快照检查当作完整资源分配服务。

本轮没有实现路由器适配器。access-bridge使用已核实的既有网关和出网，真实测试分配另做DHCP／IPAM／邻居核对；不猜静态空闲地址。VLAN路径的接口、网关和回程须先由获批fabric提供，要求现成VLAN-aware trunk。两种路径均不调用VM500替代出网，也不自动修改旧管理地址、uplink或WireGuard接口。

部署需要PVE预装Python3、iproute2、nftables，内核支持bridge conntrack／nftables；VLAN路径另需VLAN能力。角色不自动安装宿主依赖。模板须为干净基线，保留sudo但不含个人认证。PVE设置hook需要root身份，不能假定普通API token可写；创建后必须由root角色读回并绑定实际hook，不能只相信Terraform计划里的字段。

## 3. 规则和启动门禁

每员工一个`bridge hapi_<VMID>`表，按固定tap约束。access-bridge在prerouting拒绝MAC冒用和VLAN／IPv6帧，早于FDB学习；forward再校验IPv4、ARP、连接状态与目标。员工正常出网只发给固定网关；回复已发起的管理员SSH或控制面9443连接时仅允许对应可信peer。其他RFC1918、CGNAT、链路本地、保留地址及额外保护网段默认拒绝，DNS仅开放指定resolver 53。入站同时绑定源IP、MAC和入口端口，其他员工不能伪造网关MAC绕过。PVE主机input／output对员工tap也拒绝；管理员走获批外部来源，PVE管理使用虚拟化管理通道。

规则更新仅替换自己的表，通过 nft 单次事务完成；不 flush 全局规则。先对所有候选规则做内核 `--check`，通过后才允许 SDN 写入。每表保存规则文本摘要与实际内核规则摘要，包含 hook、优先级、表达式和顺序；重跑内容未变且实际规则一致时不重载。启动门禁检查摘要、启用状态、VM 名称、hook 绑定、禁用自动开机、唯一 access NIC、MAC、cloud-init 地址／网关以及已激活 VLAN uplink。额外 NIC、tag／trunk、firewall 中间桥、PCI／USB passthrough、任意 QEMU args 均拒绝。

这不是持续完整性监视器：正在运行的 VM 的宿主规则若被 PVE 管理员改动，不会由启动 hook 自动发现并立即停止。重复执行角色可以发现／修复己有规则，验收前须读回；PVE 管理员属于信任边界。员工 sudo 无权修改 PVE 规则。

## 4. 失败和恢复

- Ansible先复制按内容摘要命名的候选文件，再由 `hapi-network-stage.py` 在同一把本地锁下执行基线检查、内核检查、实时资源盘点、SDN、规则应用／读回及正式清单原子发布。hook和开机规则加载使用同一把锁；失败不把候选清单发布为正式配置。
- 提交基线已过期时拒绝继续，防止并发申请覆盖别人新近的启用／停用状态。应重新审阅计划，不能自动换成最新摘要。若相同候选已经成功发布，原基线可用于幂等重试，仍重新检查实际资源与规则。
- 私有 `network-operation.json` 记录候选摘要、阶段和成功／失败，`sdn-operation.json`另记SDN阶段与检查快照摘要。检查点只提供恢复定位，不替代每次真实读回，也不会把网络阶段标成公网可交付。
- 保留旧员工分配；更新 manifest 不允许移除或改绑原条目，只能原地停用。停用在默认丢弃之前处理，不能让 established 连接继续绕过禁用。
- 未持有本流程本地所有权回执的现有 nft／SDN 对象拒绝接管；拓扑漂移拒绝覆盖。恢复不能通过删回执认领资源。
- SDN 全局锁要求没有其他 pending changes；不会把其他人的配置一起提交。注意 SDN apply 本身会触发集群网络 reload，真实执行计划必须列出这一影响，不能当作仅新增一个 JSON 对象。
- 创建意图先写入私有回执，再调用 API。响应丢失保留原分配；若留下 pending config，后续自动重试拒绝继续，须读回并审阅恢复，不执行全局 rollback、不猜已成功或重新分配。
- 规则检查失败或实际规则摘要不一致时，启动拒绝。单表替换失败保留原内核事务；跨员工批次不是一个全局事务，失败须读回每表回执后重试。不得将失败的停用或撤销报告为成功。
- 只有网络就绪不等于可开放入口。真实开户执行器仍须先禁用本人路由，再处理停用／隔离变更，验收后才重新开放。

## 5. 验证和当前结果

在批准 Sandbox 中运行，所有地址均为合成数据：

```bash
python3 scripts/plan-hapi-network.py tests/hapi-workspace/network-fixture.json
python3 scripts/plan-hapi-network.py tests/hapi-workspace/network-fixture.json \
  --snapshot tests/hapi-workspace/allocation-snapshot-fixture.json
python3 tests/hapi-workspace/test-network-plan.py
sudo python3 tests/hapi-workspace/test-network-kernel.py --run-isolated-netns
```

18项计划／门禁／模拟PVE测试通过，覆盖冲突、可信peer、实际hook绑定、最小化快照、所有权／幂等、pending阻断、恢复、失败不发布及过期基线拒绝。production lint与playbook语法通过；当前模块在隔离root中以固定`bpg/proxmox 0.70.0`完成init／validate。另有授权的独立真实state只管理两台测试VM，不能与离线验证混称。

历史Sandbox内核`7.0.12`不支持所需VLAN／bridge conntrack；9项负向检查曾证明缺能力时拒绝部署并保留正式清单。按用户要求，本轮已改用pve2上的两台真实VM，35项通信与11项生命周期测试全部通过；原Sandbox工具不再作为真实验收前置。以下命令仅用于历史缺能力负向回归：

```bash
sudo python3 tests/hapi-workspace/test-network-kernel.py \
  --run-isolated-netns --boundary-only --expect-no-bridge-conntrack
```

真实测试入口为`test-pve-network.py`和`test-pve-lifecycle.py`，详见[两VM记录](../planning/2026-10-30-hapi-two-vm-pve2.md)。结果只证明当前bridge端口ACL、流量与门禁生命周期；没有完成VLAN配置、PVE宿主重启、MTU／PMTU专项或实际HAPI／Cloudflare／Claude验收。下一步按具体设备生成网络与回退计划，既有业务VM和公开入口尚未推广。
