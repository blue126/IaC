# OCI Hub 公网 IP 变更预案

OCI Hub 用的是临时公网 IP（AD-32）。Oracle 文档写明，停机不会丢 IP，只有实例被删除、VNIC 被分离或私有 IP 被删除时才会丢。在同一实例上替换启动卷预计也不丢，这是推断，要靠恢复演练确认。

## 现在还不能完整执行

下面两步目前没有现成入口，要先做一个“全量切换 endpoint”的 story：

- **设备包。** `wsctl reissue` 重发的是磁盘上已有的 `device-bundle.zip`，里面还是旧 IP，校验也不检查 endpoint。要增加按新 endpoint 重建设备包的命令，并支持批量。
- **员工 VM。** 已有 VM 没有批量重跑 `oci-hub-spoke` 的入口。

## 影响范围

| 依赖 | 位置 | 处理 |
| --- | --- | --- |
| `endpoint` | AD-25 落地前：settings 的 `pool.endpoint` 和 PVE 线上的 `boundary.json`，两处都要改。落地后：一个 IaC 变量 | 改值 |
| Ansible inventory | `ansible/inventory/oci/hosts.yml` 的 `ansible_host` | 改地址 |
| Homepage | `ansible/roles/homepage/templates/services.yaml.j2` | 改地址 |
| 公网 DNS | `proxy.willfan.me`、`ankiwriter.willfan.me`、`wgportal.willfan.me`、`bookorbit.willfan.me` 及其他指向 OCI Hub 的记录，不在本仓库 | 手工改 |
| PVE 防火墙 | 放行 OCI Hub 地址的 UDP 51825 | 落地前 apply，落地后跑 `oci-hub-pve` role |
| 员工 VM 的 WireGuard | `oci-hub-spoke` 写入的 `wg-workspace.conf`（`oci_hub_spoke_endpoint`） | 每台 VM 重跑配置 |
| 设备包 | 每台设备的 `wireguard_endpoint` | 重建并发送 |
| 执行器到 OCI Hub 的 SSH | settings 的 `oci_hub.ssh_target`、`known_hosts` | 写的是 IP 就要改 |

不受影响：`workspace_sources`、OCI NSG、WireGuard 密钥。

地址写在 inventory 和 Homepage 里是接受的例外，它们不属于 `endpoint` 这个变量。

## 步骤

1. 取得新 IP，确认能登录 OCI Hub。
2. 改 `endpoint`、inventory、Homepage、`ssh_target`，经 PR 合并后同步到执行器。
3. 改公网 DNS。
4. 更新 PVE 防火墙，员工 VM 才能访问新地址。
5. 对所有员工 VM 重跑 `oci-hub-spoke` 配置，确认 VM 和 OCI Hub 重新握手。
6. 重建全部设备包并发送，员工收到邮件后导入。
7. 用 `wsctl status` 检查，并抽一台设备实际连接。

从 IP 变化到第 6 步完成前，对应员工都连不上，所以第 2 到 5 步要连续做完。

## 需要提前准备

- 完成上面的“全量切换 endpoint” story。
- 做一次恢复演练，确认替换启动卷后公网 IP 不变。
- 列全指向 OCI Hub 的 DNS 记录，放到执行器运行手册里。
