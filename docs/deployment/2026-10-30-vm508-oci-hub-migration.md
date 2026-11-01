# VM508 一次性迁移记录

日期：2026-10-30。用户明确只迁 VM508，迁后留在新架构并恢复服务；其余四台员工工作区以后处理。此次是一次性维护，没有新增迁移子命令或通用框架。 后续 VM504–507 已另获批准并完成，见 [该批迁移记录](2026-10-30-vm504-507-oci-hub-migration.md)。私有执行材料、候选/实际二进制计划、快照名、原配置及交付回执留在 employee-data，不进入 Git。

## 实际结果

| 项目 | 迁移前 | 迁移后 |
| --- | --- | --- |
| VMID / 节点 | 508 / pve2 | 不变 |
| 磁盘 | mainpool:vm-508-disk-0，50GiB | 原盘保留，未克隆、未搬盘、未扩容 |
| CPU / 内存 / 自启 | 2核 host / 4096MiB / onboot=1 | 不变 |
| 名称 | employee-suixiaoyou | oci-hub-suixiaoyou |
| 虚拟网络 | vmbr508 / 10.231.8.0/30，经VM500 | oh508 / 10.236.8.0/30，经PVE路由 |
| VM / 默认网关 | 10.231.8.2 / 10.231.8.1 | 10.236.8.2 / 10.236.8.1 |
| OCI Spoke | 无 | 10.234.0.8/32，经UDP51825，已握手 |
| 设备新地址 | 旧profile分配保留历史 | 10.235.0.8/32，经OCI UDP51824 |
| 终端 | 旧网关第二跳 | VM内原生SSH/SFTP、workspace-mosh，60000–60009 |
| 桌面 | VM500代理旧noVNC | 保留原noVNC/Firefox profile，VM内overlay HTTPS8443代理loopback6081 |

Terraform 使用一次性 moved 块，把原 VM 和 inventory 地址移至 oci_hub_workspace。旧分配通过 oci_hub_managed 标记保留，旧 VM 定义不再认领它。接管检查要求旧槽位和新定义的 VMID/MAC 相同，实际计划只允许目标 VM 原地更新、其旧 hook 片段更新及相关 inventory 元数据更新，拒绝 VM/磁盘重建与其他 VM 变更。

旧 PVE bridge 表仅移除 tap508i0 的旧规则，新 VNet/路由边界先准备、VM停机后才移交隔离归属；其他旧规则经逐行规范化比较保持不变，旧网关tap500i8隔离仍保留。新边界hook在启动前核验。VM500、VM502和其余四位员工工作区持续运行。

## 凭据、桌面与交付

新方案身份存入既有独立 BWS 项目。VM Spoke 的记录另外保存该 VM 的 presentation TLS 身份；旧 profile 密钥保留作回滚，不挪用旧私钥。客户端只收到设备 SSH/WG 私钥、目标 SSH公钥pin及桌面证书指纹，不接收 VM TLS 私钥或 Portal 管理凭据。

网络/名称切换后的 cloud-init 重新生成了 SSH host key。已通过可信 PVE QGA，并核对未变的VMID、磁盘、SMBIOS与VMGenID后更新pin；没有使用ssh-keyscan或关闭StrictHostKeyChecking。旧主机公钥和原盘快照保留于私有恢复材料。

noVNC没有替换成KasmVNC。仅新增批准的wireguard-tools、mosh、nginx；noVNC改为loopback监听，nginx只监听overlay8443并随Spoke排序启动。Firefox实际进程及原profile已恢复。桌面采用该VM自有TLS证书，公钥指纹进入v2桌面包；浏览器首次信任提示由本人核对确认。

新包沿用已合并的公开bootstrap v2。设备包和私人下载地址只存在employee-data与私人交付中；已完成Temp.sh上传和HTTP POST下载整包哈希比对，更新设置邮件已获用户批准并发送，Microsoft Mail.Send 接受请求；收件及员工本机 bootstrap 仍待本人确认。员工仍需导入新profile完成本机bootstrap，不能把服务器服务恢复说成已完成员工验收。

此次按此前用户决定保留专项验收豁免，并为该设备绑定本次精确迁移授权，状态为acceptance_waived；不声称特殊隔离/恢复或真实员工验收通过。

## 恢复材料与维护发现

原盘快照、原PVE配置、旧hook/PVE策略、原guest文件、Terraform状态与前后定义保存在本次私有目录。回滚需一致地恢复原快照/配置及旧隔离归属，反向接回Terraform资源地址，并暂停新Portal接入；不能只改一项或重新克隆空VM。

部署中修复两项必要兼容问题：PVE SDN成功写操作可能返回非JSON状态文本，读取/锁令牌仍严格要求JSON；已提交用量的sample动作在一次API/边界校验失败后，成功协调当前状态可完成其待处理记录，不重放旧计数、不重复计量。补充对应回归。迁移后日常协调会保留已有桌面模式设备包及TLS身份。
