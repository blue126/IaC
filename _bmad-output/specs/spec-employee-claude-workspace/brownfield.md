# 现有环境与 IaC 边界 / Brownfield context

以下环境表保留2026-10-21规格阶段的源记录与仓库核对，原基线为 `d47f12d9748f0343f69afd601376f0512813df00`；本次Build工作树基线为 `a6bffdfef447fdf54485ca4882dfe1e87b6ae04a`。未连接实机，不代表最新现场状态；实施前仅核验会影响选择的现场差异。

## 已知环境

| 对象 | 来源和已知事实 | 对规格的影响 |
|---|---|---|
| 家庭路由器 | [bare-metal inventory](../../../ansible/inventory/bare_metal/hosts.yml)：gateway=`192.168.1.1`，iStoreOS 24.10.8（OpenWrt 衍生），root SSH、无 Python，network_appliance 组 | 不再询问路由器类型；不能套用 Python-backed roles 或经 site.yml 广泛配置 |
| 家庭网络 | [网关指南](../../../docs/guides/gateway-backup.md)：2026-10-04 记录 LAN `.1/24`、WAN DHCP、DHCP 池 `.150–.246`、Mac Wi-Fi 经 eth1、PVE 经 eth2 下游交换机 | 当前转发／入站、地址稳定性、交换 VLAN 能力待核；不能从 DHCP 或公网 IP 一致推断实时端口可达 |
| PVE 集群 | [节点定义](../../../terraform/proxmox/pve-cluster.tf) 与 [QDevice 架构](../../../docs/architecture/proxmox-qdevice-architecture.md)：pve0／pve1 的 vmbr0=`.20/.21`、vmbr1=`.50/.51`，均在 `192.168.1.0/24` | 现有桥名不是租户隔离；保护家庭、管理与节点通信路径 |
| 独立 pve2 | 节点定义为 `.52`、管理桥 vmbr0，非上述集群成员，VMID 空间独立 | 不能把 inventory 分组名理解为集群成员资格，也不能沿用 pve0／pve1 桥约定 |
| 外部见证 | QDevice 架构记录 N100 上 qnetd-witness=`192.168.1.53` | 网关及其网络变更涉及已有见证环境，不能影响其通信 |
| 个人中国出口代理 | [CN Proxy 指南](../../../docs/guides/cn-exit-singbox-proxy.md)：`.1:7890`，独立 sing-box／Tailscale 身份 | 员工隔离规则应阻止访问，不用于 Claude 请求出口 |
| 网关 P2V | 网关指南仍记录为待实施方向 | 不假定 N100 已迁移或旧网络已被替换 |
| 现有员工试用入口 | 源脑爆记录用户2026-10-20已建试用VM并经Cloudflare Access供员工使用；VMID、网络位置、隔离状态、Access应用／路由、服务端cloudflared连接器位置及当前存续状态未现场核实 | Q-4／5先形成公司入口清单；正式上线前对仍存在的旧公司入口明确下线，或纳入同一访问／出口约束，不能遗留未纳管通道；不假定旧VM已无隔离或已关闭 |

用户在源脑爆中报告 WAN IPv4 与外部查询一致；入站连通与地址稳定性未验证。用户判断 PVE cluster 和 pve2 内存充足，但本轮没有现场 CPU、磁盘或内存证据。上行暂按 A-2 理解；5–10 人规模未区分总人数和同时在线人数。

决策历史：早期脑爆明确客户机管理员权限及sudo；后续规格阶段曾允许重评权限与接入，并写入“不承诺root”。用户在本轮再次明确sudo必需，依赖和工具全部由员工自主管理，该决定覆盖后续规格中的权限收紧表述。

本轮用户确认的实施边界为按设备身份进入受管SSH堡垒机，由其另建到固定本人VM的第二段SSH／SFTP，不使用ProxyJump或员工直连客机SSH。正常公网开发访问经澳洲受管路由，受保护目的地在VM外拒绝；不再要求全面阻止员工自定义加密／终端中继或建立对抗sudo的令牌来源绑定。实际OAuth浏览器与Claude CLI位于澳洲VM、身份和出口流程证据仍需验证；图形授权入口未获准。员工停用仍从VM外断网或停机并保盘，设备级撤销覆盖公司受管身份／会话。以上为当前用户决定；旧方案及其验收推定保留为历史，不据此恢复已撤回的保证。

## 仓库配置衔接

- [proxmox-vm/main.tf](../../../terraform/modules/proxmox-vm/main.tf) 实际使用 `bpg/proxmox`。当前 `network_device` 只显式配置 model 和 bridge，[模块变量](../../../terraform/modules/proxmox-vm/variables.tf) 没有 VLAN／网卡防火墙输入；需要时只补满足隔离的最小参数，先核对所用 provider 能力。
- 模块忽略创建时 Cloud-Init SSH keys 的后续变化，后续公钥配置由 Ansible 管理；个人 OAuth 或私钥不通过模板和 Terraform state 传递。
- [Terraform inventory](../../../ansible/inventory/terraform.yml) 使用 `cloud.terraform.terraform_provider`。沿用 Terraform 管 VM 基础设施、Ansible 管主机配置的现有职责。
- 系统部署凭据遵循采用的 [Vault 架构](../../../docs/architecture/ansible-vault-architecture.md)；个人 OAuth 按 access-and-isolation.md 由员工管理，不自动集中托管。
- 单节点独立内部bridge＋多网卡网关只是本轮实施建议，未作现场验证。bpg/proxmox 0.70.0的bridge资源会重载节点网络；须先核对待应用网络更改及管理恢复路径，不能把创建新bridge理解为对既有网络没有应用影响。

本文件是Build采用的现有环境说明；进入Build并不授权安装、基础设施变更或提交／推送／发布，仍按项目既有边界取得对应授权。不能从上游脑爆文档的PR发布过程继承新任务授权。

公司旧入口处置限核实后的员工业务对象；若连接器与其他业务共用，不能笼统停用整个cloudflared服务。下线／调整仍需相应外部写入授权，VM磁盘和数据按Q-6另定。
