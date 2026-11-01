# Demo／管理员测试工作区与旧接入退役

日期：2026-10-30。用户批准在原盘上迁移 VM501、502，并将 VM509 的底层子网让给 VM501；允许测试机短暂停机。保留原 VM、磁盘、规格及用途，后续磁盘备份与快照按用户要求取消。VM509 的离线副本在该要求到达前已完成，没有继续为 VM501/502 建立快照。

| VM | 用途 | VNet / 物理地址 | 默认网关 | OCI overlay |
| --- | --- | --- | --- | --- |
| 501 | demo | oh501 / 10.236.1.2/30 | 10.236.1.1 | 10.234.0.9/32 |
| 502 | 管理员本人测试 | oh502 / 10.236.2.2/30 | 10.236.2.1 | 10.234.0.2/32 |
| 509 | 独立测试 | oh509 / 10.236.9.2/30 | 10.236.9.1 | 10.234.0.3/32 |

执行顺序为先调整并恢复 VM509，释放原子网后再逐台迁移 VM501/502。使用原 VM 和原盘，保留 2 核 host、4096MiB、原磁盘容量及原自启设置；Terraform 只接管两台原资源地址并修改已批准的网络/名称/标签/启动保护，拒绝磁盘或 VM 重建。通用 module 同步补齐 serial0 控制台声明。VM509 只改变物理地址和网关，原 overlay、SSH host key 和设备凭据保持，原设备包无需因本次物理子网调整重发。

两台旧工作区保留原 cloud-init vendor 引用和管理员公钥；启动后原初始化重新执行，playbook 等它完成后再安装 WG/Mosh/Nginx，避免争抢 dpkg 锁。新接入使用独立 BWS/Portal 身份，SSH/Mosh 直接在目标 VM 终止；原 noVNC 和 Firefox profile 保留，并增加仅 overlay 的 HTTPS 入口。

VM502 原有 employee-hapi-hub、employee-hapi-runner、employee-hapi-tunnel、employee-login-guide、tailscaled 均 active。复用已安装的 HAPI 标准验证器，缺失/无效凭据拒绝、有效 API、Runner、SSE 和会话列表重载检查通过；没有在日志中输出 token 或会话内容。这不代表员工本机或浏览器端验收完成。

## VM500 旧接入退役

保留用途已由用户明确为 **HAPI 控制面**。退役只指旧员工 gateway 后端；VM500 不再负责员工网络隔离。此前根据单次服务清点推断可能没有其他业务的说法不准确，不得用于整机退役。主机自身防护不等于员工网络隔离。

用户明确确认旧入口无人使用后执行。VM500 本体、原盘、管理 SSH、主机防火墙及系统基础服务保留。只停用并 mask 以下六项：

- employee-auth-viewer.service
- employee-hk-browser.service
- employee-sshd.service
- employee-oci-home-sshd.service
- wg-quick@wg-employee.service
- wg-quick@wg-oci-home.service

旧中继的三个防火墙 drop-in（oci-backhaul.conf、zz-browser.conf、zzzz-hub-spokes.conf）退出运行路径。防火墙按最终全部 disabled 的旧分配重新生成，实际内核规则校验通过；旧 WG 接口和旧 SSH/桌面监听消失，192.168.1.140:22 保持可达。不卸载软件，不修改 VM500 网卡、OpenWrt、其他 VM 或 OCI 旧实验资源；旧基础设施槽位、历史凭据与台账继续保留。

`/etc/employee-access-retired` 和 inventory 退役标记阻止旧 role 重新部署；私有 `onboard.sh` 在同步/开户前拒绝已退役的默认/explicit existing 写入入口，login、auth-status 和历史 registry 仍可读取。活动工作区一律通过 `--profile oci-hub` 维护。管理员同一邮箱的多个测试工作区必须显式选择 ID；普通邮箱唯一开户的冲突保护仍保留。

## 本地交付与后续

VM501 和 VM502 的新包只保存在私有 employee-data，本次不上传、不发送邮件。使用新 profile 和独立状态目录；旧包不可继续访问这两台。包和私钥不进入源码 Git。专项验收仍按此前授权标记 acceptance_waived，不记为通过。

架构及项目 skill 同步记录旧后端退役。源码仍待按独立内容分批提交；私有管理员代码与 IaC 分仓，其他任务改动及临时诊断材料不混入提交。当前未执行这些源码的 commit/push/PR。

后续：用户另行授权清理 VM500 旧网卡，net1–net8 及旧 gateway 网络配置现已移除；以上“不修改网卡”仅描述先前退役阶段。当前结果见 [网卡清理记录](2026-10-30-vm500-legacy-nic-cleanup.md)。

源码收口：本次一次性退役/清理程序已从源码移出，执行副本留在私有运行记录；主线保留最终声明、旧写入口拒绝及独立PVE退役保护。本轮不包含 HAPI 配置实现。

后续源码收口已删除旧 role，而非继续保留其主入口保护。通用管理员公钥与PVE退役guard已分别抽取，登录/browser/helper文件不删除。此步未再次部署或改线上。
