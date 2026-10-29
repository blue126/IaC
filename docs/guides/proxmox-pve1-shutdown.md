# pve1 迁移完成后的关机说明

## 2026-10-27 关机前结论

本次迁移与用户确认的收尾已完成，现场检查满足 **pve1 正常关机** 的条件。该结论是关机前检查，未代替实际关机后的仲裁确认；pve1 仍保留为集群成员。

- pve1 的 `qm list`、`pct list` 及来宾配置目录均为空；`local-lvm`、`nvme-lvm` 已用量为0，两块 CT111 旧源卷已删除，原正式证据保留。
- Fileserver CT111、OpenBao112/113、HAOS114、FunASR115、PDM117、Hindsight118 均在 pve0 运行；container-lab108 位于独立 pve2，保持 stopped/onboot0；Windows116 已按用户授权删除。
- pve0 没有依赖 pve1 的 NFS/CIFS 挂载、复制任务或 HA 来宾资源；PBS 位于独立 pve2，QDevice 位于 N100，而非 pve1。
- 集群为 pve0 1票、pve1 1票、QDevice 1票，quorum2。pve0 的 QDevice Connected/TLS active，N100 上两客户端证书 verified，现有 guard 规则及 ingress hook 在位。
- Jenkins 已恢复启用，未主动触发构建。两个既有 PVE 备份作业仍为 disabled，本次未启用；不应将配置的00:00计划理解为备份正在执行。

迁移、adoption、完整 live refresh、源盘和任务临时资源清理见[最终执行状态](https://github.com/blue126/IaC/blob/751f7b6da8c4bf92cfa62c8fc77f7c61626ce146/_bmad-output/plan-proxmox-consolidation-execution.md)。取消的全量数据扫描、CT111迁后T1/verify、剩余观察和双Mac/24–48h跟进不列为未完成迁移，也未记录为验证通过。

## 正常关机与关机后确认

关机前，在 pve0 再确认见证没有失联：

```bash
# Run on pve0.
pvecm status
corosync-qdevice-tool -s -v
```

应为 `Quorate: Yes`、`Total votes: 3`、`Quorum: 2`，QDevice `Connected`、`TLS active: Yes`。确认仍符合后，由操作者在 pve1 Web UI 正常关机，或在 **pve1** 上执行：

```bash
# Run on pve1 only after confirming the checks above.
systemctl poweroff
```

关机后，在 pve0 再执行上面的两条只读命令，应为 `Quorate: Yes`、`Total votes: 2`、`Quorum: 2`、QDevice仍连接。pve1在集群UI显示离线及其本地存储不可达是预期现象，不需要删除节点或更改存储配置。

**pve1停机期间保持N100及见证路径在线，不同时重启网关、Docker或qnetd。** 此时 pve0 依赖外部见证维持2票；若见证丢失，优先恢复见证或重新启动pve1，不用 `pvecm expected` 临时降票。长期移除pve1、重构集群票数不属于本次关机。

详细机制及恢复边界见[QDevice架构](../architecture/proxmox-qdevice-architecture.md)。
