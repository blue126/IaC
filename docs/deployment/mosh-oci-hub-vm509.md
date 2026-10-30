# VM509 独立 OCI Hub Mosh 试点

当前地址更新（2026-10-30）：VM509 已调为 oh509 / 10.236.9.2/30、网关 10.236.9.1，原 10.236.1.0/30 已交给 VM501 demo；overlay 10.234.0.3 和设备身份保留。以下首次部署地址属于历史记录，当前映射见 [收尾记录](2026-10-30-demo-test-hub-retirement.md)。


2026-10-30 当前执行方案。用户明确选择新建 VM509，不改造 VM502；新路径从首次验收起不依赖 VM500 或原站点隧道。此前 VM502 过渡申请已经停用，VM503 因旧退役槽位及 tap503i0 隔离规则冲突而放弃复用，不修改旧退役边界。

## 当前状态（以此节为准）

VM509 目前运行，独立 Spoke、原生员工 SSH 授权及 workspace-mosh 已配置；正式试点设备 fanweiblue-hub509 使用 10.235.0.4/32、Mosh 60000–60009，Portal 已登记启用，本地 v2 包已生成。原 RTT 测试 peer 仍停用、临时 CPE 接口/路由/私钥已清理、回显服务停止。中国端到端TCP/UDP网络测试已完成，结果见[RTT报告](../learningnotes/2026-10-30-vm509-oci-hub-rtt.md)。这不等于员工SSH/Mosh/SFTP及bootstrap完整验收。

下文的 stopped/disabled 描述是创建与启动门控阶段的历史步骤，不是当前实时电源状态。当前架构与剩余工作统一见[主架构文档](../architecture/oci-employee-vpn-hub.md)。本轮已接通常规[原生 Mosh 开户](oci-hub-native-provisioning.md)，用户明确跳过第4项专项验收，正式包标记 acceptance_waived；不记作真实 Mosh/安全恢复验收通过。公开客户端尚未推送，设备包未上传或发信。VM500 和旧后端保留，待用户确认旧入口无人使用再讨论功能退役。

## 创建计划

| 配置 | 本次选择 |
| --- | --- |
| VM | pve2 / 509 / oci-hub-pilot509 |
| 模板 | VM9001 / employee-workspace-baseline-20261022 |
| 计算 | 2 核，CPU host，4096 MiB |
| 磁盘 | 50 GiB，pve2-ssd，完整克隆；mainpool 不放新盘 |
| 固件 | seabios，与实际模板匹配 |
| 创建状态 | stopped、onboot=false、protection=true |
| 新网络 | Simple zone ocihub，VNet oh509，10.236.1.0/30 |
| VM / 网关 | 10.236.1.2 / 10.236.1.1 |
| 回程 | OpenWrt 的 10.236.0.0/16 经 pve2 192.168.1.52 |
| 出口 | PVE 纯路由，OpenWrt 已有 WAN NAT；不经 VM500 |

只读检查时 mainpool 可用约 29 GiB；pve2-ssd 是 /mnt/pve/pve2-ssd 的独立目录存储，可用约 709 GiB。容量不是预留保证，执行前仍以真实计划及创建结果为准。

## 既有管理员入口

仍使用规范私有管理员工程 onboard.sh，显式 profile=oci-hub。新增 operation=create-workspace 用于先创建受保护且停机的工作区，不提前要求尚未取得的 VM SSH host pin、桌面凭据或设备包；后续真实身份核验与接入配置另阶段执行。

真实请求、settings、inventory、计划及检查点保存在 employee-data。本次申请明确绑定 pilot509、VM509 和上述分配；通过 plan 生成摘要，apply 只接受同一计划及配置。不要把本文件字段自行拼成另一套 qm clone/terraform apply 旁路。

创建阶段依次：

1. Ansible 准备独立 PVE 边界、SDN 和回程路由。新工作区仍 disabled=true；SDN 使用全局锁并拒绝无关 pending changes，SNAT=0。
2. Terraform 只创建本 VM 和对应 inventory，复用通用 proxmox-vm module。defer_hook_binding=true 避免由 API token 写 root-only hook；VM 保持停机、禁止自启。
3. PVE 管理 SSH play 核对 VM 名称、VMID、停机状态、VNet、MAC、hook 文件所有权和原 hook，再绑定启动保护；不覆盖外来 hook，不启动 VM。
4. 返回 workspace_created_stopped；不读取设备 BWS 凭据、不调用 Portal 登记/启用、不生成或交付设备包。没有实际执行目标的 Ansible recap 就停止，不推进 Terraform。

后续才在同一私有入口完成独立 Spoke/Mosh、真实 SSH host pin、Portal 映射与配额、设备包和独立端到端验证。创建完成不等于可连接或 Mosh 验收通过。

## 审批及当前状态

创建 VM 的用户意图不替代独立 PVE SDN Apply、OpenWrt 路由重载及 Sandbox 网络授权。原创建计划获批后，独立 PVE SDN、边界和 OpenWrt 聚合回程已部署；Terraform 已创建 VM509 及 inventory。VM 保持停机、禁止自启和删除保护。克隆后机器类型回读为空，未匹配原计划 q35；其他多个未配置的可选值被 provider 从 null 回读为默认值，原状态核验因此停止，未绑定 hook。

已补齐受限恢复：保留原二进制计划/检查点；重新核对原审批、归属、全部非机器类型的已批准属性和无关 state，只有机器类型修正可进入新计划。修正计划已单独获批并执行，只 update VM509.machine 至原批准的 q35；原网络阶段没有重放。启动保护 hook 已由受控 PVE SSH play 绑定，工作流返回 workspace_created_stopped，检查点为 boundary/provisioned/hook_bound。Null 可选字段不再被误当成明确配置，started/onboot/protection、磁盘、MAC、子网和已指定机器类型仍严格校验。

已验证创建/受限恢复阶段 8 项回归、原 Hub 65 项回归、4 项 Terraform startup 契约及 Ansible 语法/lint。真实 WG、Mosh、中国网络表现和独立性仍未验收。先前失败的 VM500 过渡尝试写入过增量 controller/config/drop-in；这些已停用的任务增量保留审计，另按精确撤回范围处理，不能声称尚无任何旧主机写入。

## 创建完成核验

2026-10-30 真实核对 VM509：machine=q35、2 核 host、4096 MiB、pve2-ssd 上 50 GiB raw 盘、net0=oh509、onboot=0、protection=1，hookscript 指向受控 OCI Hub 边界脚本。VM 保持 stopped。PVE live boundary/路由校验通过；直接执行 pre-start 校验，确认因工作区 disabled 而拒绝，未启动 VM。

已将无密钥的已部署 roster 写入本任务 IaC 的 terraform/proxmox/oci-hub-workspaces.auto.tfvars.json，避免后续计划把这台 VM 视为缺少期望定义。创建完成尚不代表 WireGuard/SSH/Mosh 可用，未登记或启用设备，也未上传或发邮件。
