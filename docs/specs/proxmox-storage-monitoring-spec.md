# Proxmox 存储监控统一规范

> **版本**: 0.1
> **日期**: 2026-08-06
> **状态**: 草案（延期实施）
> **来源**: 从[备份架构整合规范](./backup-architecture-consolidation-spec.md)的阶段一 2b/2c 拆分

## 1. 背景

`HomePVECluster` 的 pve0、pve1、pve2 均使用本地 ZFS。原备份架构整合规范只要求在 pve1 为 `tank` 启用 scrub，并配置 `smartd` 与 ZED；这种单节点处理会让其他节点继续缺少同等保护，也会在未来引入 Prometheus/Grafana 时形成两套监控配置。

因此，磁盘健康、ZFS 事件、定期 scrub 和集中告警应作为一项独立的集群级监控工作统一设计和实施，不再作为备份迁移的前置步骤。

## 2. 决策

1. 监控策略覆盖 `proxmox_cluster` 中的全部 PVE 节点，而非只覆盖 pve1。
2. `smartd`、ZED 与 scrub timer 由同一个通用 Ansible role 管理，节点差异通过 inventory 变量表达。
3. 当前没有 webhook、邮件或集中监控通道，因此第一阶段只写入本地 journald，不宣称具备外部告警能力。
4. 等 Prometheus/Grafana 监控体系设计完成后，再统一接入指标采集、告警规则和通知通道。
5. 本工作延期实施，不阻塞 Fileserver、Time Machine 和 Veeam 的迁移。

## 3. 监控边界

| 组件 | 作用范围 | 职责 |
|---|---|---|
| `smartd` | 每台 PVE 主机直接可见的物理磁盘 | 定期执行 SMART 检查并记录健康状态变化、介质错误、温度和自检结果 |
| ZED | 每台 PVE 主机已导入的 ZFS 池 | 监听池降级、设备故障、校验错误及 scrub/resilver 事件 |
| `zfs-scrub-*@.timer` | 每个本地 ZFS 池 | 定期读取全部数据并验证校验和；存在冗余时修复损坏数据 |
| Prometheus exporters | 集群统一采集 | 将主机、磁盘和 ZFS 指标转换为 Prometheus 时序数据 |
| Alertmanager/通知通道 | 集中告警 | 根据持续时间和严重级别发送可操作的外部通知 |
| Grafana | 集中展示 | 展示容量、健康状态、错误趋势、scrub 新鲜度和预测性指标 |

`smartd` 与 ZED 不是重复关系：前者观察磁盘固件提供的设备健康信息，后者观察 ZFS 从池和 I/O 层看到的事件。两者都不能替代 scrub；没有 scrub 时，长期未读取的数据可能发生静默损坏而不被发现。

## 4. 第一阶段：本地可观测性

第一阶段只建立统一且可由 Ansible 重建的本地状态：

- 安装并启用 `smartmontools`/`smartd`。
- 安装并启用 ZED，事件写入 journald。
- 为每个适用的本地 ZFS 池启用月度 scrub timer。
- 不配置虚假的邮件地址、未部署的 webhook 或依赖人工查看才能生效的“告警”。
- 为未来 exporter 保留标准服务、日志和命令接口，不引入自定义状态文件。

### 4.1 节点与池发现

role 应应用到 `proxmox_cluster`，但不能把 `tank` 硬编码为全局池名。实施前应采集每台节点的：

```bash
zpool list -H -o name
lsblk --json -o NAME,TYPE,MODEL,SERIAL,TRAN
smartctl --scan-open
```

scrub timer 的目标池可由 role 根据本机已导入池发现，或通过主机变量显式声明。若采用自动发现，必须提供排除列表，以支持临时导入池或不应由该节点调度的池。

### 4.2 本地验证

每台节点至少验证：

```bash
systemctl is-enabled smartmontools
systemctl is-active smartmontools
systemctl is-enabled zfs-zed
systemctl is-active zfs-zed
systemctl list-timers 'zfs-scrub-*'
zpool status
journalctl -u smartmontools -u zfs-zed --since today
```

实际 unit 名称必须以目标 PVE/Debian 版本提供的包为准，role 不应假设所有版本都使用相同别名。

## 5. 第二阶段：Prometheus 与 Grafana

集中监控阶段至少覆盖以下信号：

### 5.1 磁盘指标

- SMART overall health 与可用性
- Reallocated、Pending、Offline Uncorrectable sectors
- UDMA CRC error 计数及增量
- SAS grown defect list
- NVMe critical warning、media errors、percentage used
- 温度及持续超温
- 最近一次 short/long self-test 状态和时间

### 5.2 ZFS 指标

- pool state 与 vdev state
- read/write/checksum error 计数及增量
- usable、allocated、capacity 与 fragmentation
- 最近一次 scrub 的完成时间、结果和持续时间
- scrub/resilver 是否运行、进度及预计完成时间
- ARC 命中率、大小与受限情况
- dataset quota/refquota 使用率

### 5.3 主机指标

- 节点在线状态
- 文件系统和 inode 使用率
- I/O latency、吞吐和队列深度
- 内存、swap 与 OOM
- exporter/Prometheus 自身存活状态

## 6. 告警原则

集中告警上线后按以下层次设计：

| 严重级别 | 示例 | 目标 |
|---|---|---|
| Critical | pool DEGRADED/FAULTED、设备离线、不可纠正错误持续增长 | 立即通知 |
| Warning | SMART 属性恶化、温度持续过高、容量超过阈值、scrub 失败 | 在造成服务中断前处理 |
| Info | scrub/resilver 完成、短暂温度峰值 | 保留事件，不默认打扰 |

所有告警必须包含节点、池或设备稳定标识、首次发生时间、当前值和建议检查命令。不得只发送“ZFS 有错误”这类不可操作消息。

还必须设置 dead-man 告警：节点或 exporter 长时间没有数据本身就是故障，不能因为没有上报错误而被判断为健康。

## 7. IaC 变更范围

预计新增：

- `ansible/roles/pve-storage-monitoring/`
- `ansible/playbooks/deploy-pve-storage-monitoring.yml`
- `ansible/inventory/group_vars/proxmox_cluster.yml` 中的集群默认值
- 必要时在 `host_vars/` 中声明节点特有的池或设备参数
- Prometheus scrape 配置、告警规则及 Grafana dashboard（集中监控阶段）

role 必须保持幂等，并遵循以下边界：

- role 管理服务、配置和 timer，不创建、导入或销毁 ZFS 池。
- role 不自动执行破坏性 SMART 测试。
- scrub 调度应错峰，避免所有节点同时产生高 I/O。
- 设备引用和告警标签优先使用 serial、WWN 或 `/dev/disk/by-id/`，不依赖易漂移的 `sdX` 名称。

## 8. 验收标准

### 第一阶段

1. Given 任一 PVE 节点重启，When 系统恢复，Then `smartd` 与 ZED 自动运行。
2. Given 节点存在受管 ZFS 池，When 查询 systemd timers，Then 每个目标池都有启用且带下一次执行时间的 scrub timer。
3. Given SMART、ZFS 或 scrub 产生事件，When 查询 journald，Then 可按服务、节点、池或设备定位事件。
4. Given 重复运行 Ansible playbook，When 配置没有变化，Then play recap 不产生非必要变更。

### 集中监控阶段

1. Given 任一节点或 exporter 停止上报，When 超过设定窗口，Then Alertmanager 产生 dead-man 告警。
2. Given pool 进入非 ONLINE 状态，When Prometheus 完成下一次采集，Then 产生包含节点、池名和状态的 Critical 告警。
3. Given scrub 超过规定周期未成功完成，When 告警规则评估，Then 产生 scrub stale 告警。
4. Given 磁盘错误计数持续增长，When 达到规则条件，Then 产生包含稳定设备标识的告警。

## 9. 实施前未决项

- Prometheus、Alertmanager 和 Grafana 的部署位置及高可用要求
- exporter 选择及其维护状态
- 外部通知通道（邮件、聊天平台或其他 webhook）
- 各节点池清单、scrub 错峰时间及排除项
- SMART short/long self-test 的统一周期
- 指标与日志保留周期
