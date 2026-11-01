# VM504–507 一次性迁移记录

日期：2026-10-30。此批延续 VM508 的一次性原盘接管，按逐台快照、短暂停机、恢复服务、交付新包和通知的顺序执行。用户批准精确批次预览 SHA256 `e5ee2567e54eada9c89dfbc010c34cfef9ae016b5f937c822998779b8ae76a6a`，并授权直接发送 VM508 同版更新设置通知。没有新增通用迁移命令。

| VM | 独立 VNet | 物理地址 / 网关 | OCI Spoke | 设备地址 |
| --- | --- | --- | --- | --- |
| 504 | oh504 | 10.236.4.2 / 10.236.4.1 | 10.234.0.4 | 10.235.0.5 |
| 505 | oh505 | 10.236.5.2 / 10.236.5.1 | 10.234.0.5 | 10.235.0.6 |
| 506 | oh506 | 10.236.6.2 / 10.236.6.1 | 10.234.0.6 | 10.235.0.7 |
| 507 | oh507 | 10.236.7.2 / 10.236.7.1 | 10.234.0.7 | 10.235.0.9 |

每台保留原 VMID、mainpool 原盘 50GiB、2核 host、4096MiB 内存和自启设置。只接管原 VM 与 inventory 的 Terraform 地址，并更换该 VM 的隔离 hook、VNet 和网络初始化配置。逐台实际计划核对磁盘、CPU、内存和自启；禁止重建 VM 或磁盘。原盘快照、旧配置、旧公钥与实际计划保存到私有 employee-data。

接入改为设备 WireGuard → OCI Hub → 该 VM 的独立 WireGuard Spoke，原生 SSH/SFTP/Mosh 直接终止于本人 VM。桌面保留原 noVNC/Firefox profile；新增 overlay HTTPS8443 代理 loopback6081。新身份位于独立 BWS 项目，设备包只包含本设备密钥、目标 SSH pin 与 TLS 指纹。

迁移后需员工使用更新通知中的新包，按公开 GitHub 指引重跑本机 bootstrap。服务器配置恢复、包下载哈希校验和邮件接口接受不代表员工已收件、完成 bootstrap、个人 Claude 登录或真实 Mosh 验收。专项验收按本批用户授权记录为 acceptance_waived。

设备包、下载链接、邮箱对应表、快照名、主机公钥和邮件回执保存在私有 employee-data，不进入本记录。用户与 VM 台账通过既有 registry 工具刷新。

## 完成状态

四台均已完成原盘接管、服务恢复、Portal 登记及启用、设备包上传与下载哈希比对。四份邮件回执均为 completed，主题为“你的工作区接入设置已更新”；微软接口接受时间（UTC）分别为 VM504 10:00:51、VM505 10:08:15、VM506 10:13:46、VM507 10:18:19。API 接受不能代替员工收件确认。

迁移前，旧 PVE 规则仅移除当前目标 guest tap 的规则；相应 VM500 gateway tap 隔离继续保留。VM500 实例及其他业务保留，未执行旧后端退役。

收尾只读复核确认四台均 running，原盘/2核 host/4096MiB/onboot=1 保留，ssh、wg-quick@wg-workspace、nginx、employee-browser 均 active；VM 内原 noVNC 与 overlay HTTPS 均返回 200，OCI 上四条 Spoke 均有近期握手。Spoke AllowedIPs 仅接受该员工设备地址，OCI 本机地址不在其中，因此不能用 OCI 本机直接 SSH/HTTP 的失败推断员工接入失败；真实设备 bootstrap 和会话仍由员工确认。
