# pve2 HAPI 网络实验室创建计划

> 已取消此路线。用户于2026-10-30要求直接创建两台真实测试VM并使用pve2实际交换网络验收；见[两VM真实验收](2026-10-30-hapi-two-vm-pve2.md)。本页保留原提案作记录，VM9100未创建，不再推进单台namespace实验室。

状态：已完成只读资源核对；尚未创建、安装或启动实验室。创建及其依赖安装待单独确认。2026-10-30。

## 为什么先创建一台测试 VM

这台VM承载可丢弃的Linux网络实验室，不承载HAPI或员工业务。测试脚本在其内部创建独立network namespace，模拟Alice、Bob、路由器和PVE交换网络，用实际Linux bridge／VLAN／nftables验证反冒用、跨员工拒绝、正常出网及规则失效后的启动门禁。实验室VM有自己的Linux内核，可解决当前Sandbox缺少VLAN和bridge conntrack能力的问题；这些能力仍须开机检查，不能凭发行版名称宣称通过。

这一阶段验证规则和执行顺序。随后两台真正的测试工作VM才验证PVE实际VNet、tap、offload、宿主规则及路由器接入；实验室中的模拟交换网络不能代替PVE现场验收。两阶段结果分别记录，不能把第一阶段通过写成已能为员工交付。

## 只读盘点证据

通过既有SSH agent、`BatchMode=yes`、`StrictHostKeyChecking=yes`访问已登记的`root@192.168.1.52`，并核对hostname为pve2。只执行PVE GET、版本及主机名查询，没有读取Vault、BWS、其他业务台账或个人认证。

| 对象 | 本次观察 |
|---|---|
| 宿主 | pve2，PVE 9.2.2，运行内核7.0.2-6-pve |
| 可用内存 | 约314GiB，瞬时值，创建前再检查 |
| `pve2-ssd` | dir存储，约703GiB可用，支持images和snippets；路径`/mnt/pve/pve2-ssd` |
| `mainpool` | 约13GiB可用；不作为本实验室的新增磁盘目标 |
| `local` | 支持vztmpl／backup／import／iso，没有snippets内容类型 |
| `employee-snippets` | 独立dir存储，路径`/var/lib/employee-snippets`；实验室不使用旧员工bootstrap文件 |
| 基础模板9000 | `employee-ubuntu-2604-template`，20GiB系统盘；当前网卡断开，guest agent关闭。源码声明为从官方cloud image生成的未启动基础模板；磁盘内容和启动历史本轮未检查 |
| 模板9001 | 员工基线，已有员工vendor snippet和静态管理地址；实验室不使用其业务bootstrap |
| 当前网络 | 管理桥vmbr0连接nic2；现有多座员工内部bridge。接口API未返回VLAN-aware开启标记 |
| 候选VMID9100 | 本次pve2来宾清单未占用，尚未预留；不能据此宣称其他state／IPAM无预留 |

## 拟创建的单台资源

| 项目 | 计划 |
|---|---|
| 名称／候选ID | `hapi-network-lab`／9100，执行前重查占用与所有权 |
| 位置 | pve2 |
| CPU／内存 | 2vCPU／2048MiB |
| 系统盘 | 20GiB，`pve2-ssd`；优先从确认干净的9000完整克隆，原模板不修改 |
| 管理网卡 | 一张新MAC的virtio，连接现有vmbr0；管理地址用DHCP，启动后核实租约，不猜静态空闲地址 |
| 实验网络 | 全部位于VM内部的临时namespace，不桥接实验流量到管理网卡，不添加宿主bridge／VLAN／路由／NAT |
| 引导与依赖 | 独立HAPI实验室cloud-init；安装Python3、iproute2、nftables、qemu-guest-agent并启用agent。不开启员工服务、不安装Claude、不复制员工凭据 |
| 管理身份 | 仅获批管理员SSH公钥；用PVE受信管理通道核对新VM host key后启用严格SSH校验 |
| 电源／持久性 | 停止创建、禁止随宿主自动开机；审阅计划后按测试阶段启动 |
| 状态归属 | 单独的实验室资源及私有state，不加入WireGuard roster、不接管VM500／501／502或旧模板state。具体state绑定与认证方式在执行计划中明确 |
| 生命周期 | 测完可释放；释放仍按精确VMID、磁盘及state归属单独确认，不自动清理其他资源 |

## 创建前和验收门槛

1. 重查VMID9100、名称、存储、模板和管理网络占用；确认模板9000的来源及无个人认证。不满足时停在计划阶段，不改用9001或其他业务VM。
2. 绑定单独state、管理员公钥和只管理此VM的Terraform计划；计划不得包含其他资源变化。不重新创建已有模板或修改现有bridge。
3. 用户确认具体创建与上述依赖安装后，才进行真实写入。当前“继续盘点”的授权不作为已批准apply的记录。
4. 开机后核对hostname、内核、VLAN-aware bridge、VLAN link及bridge conntrack能力，再安装并运行当前获审阅版本的测试包。测试不得通过伪造SANDBOX_ID绕过运行位置检查；测试入口须显式支持这台独立实验室，并拒绝直接在PVE宿主运行。
5. 完整回归必须使用真实VLAN与规则，不能使用`--boundary-only`或预期缺能力模式代替。保留退出码、规则摘要、测试结果及失败检查点，确认临时namespace与进程结束。

本轮真实PVE网络部署另有两个明确前提：尚无已核实的VLAN-aware trunk／路由器fabric；当前HAPI原型硬编码的`local:snippets`启动hook路径也与现场存储不符。它们必须在真实PVE双VM计划中修正和验证，不影响本台VM内部的Linux实验室测试，也不在本计划中顺带修改宿主配置。
