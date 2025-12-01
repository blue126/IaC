# NetBox 集成 Terraform 模块目录说明

## 背景与目标
NetBox 在本仓库中定位为 Single Source of Truth (SSOT)：集中存放 Homelab 的所有资产信息与相互关系（物理/虚拟/服务/网络）。最终目标工作流是：

- 从 NetBox 创建/维护资源 → Terraform 读取（pull）→ Terraform 在实际平台上创建/变更 → Ansible 进行软件层配置与验证。

当前阶段：在逐步过渡到“NetBox→Terraform→Ansible”的模式过程中，Terraform 仍承担将已存在或由 IaC 管控的对象登记到 NetBox（push）的职责，以建立完整的资产基线。随着 pull 能力完善，Terraform 将以 NetBox 为输入来源进行资源编排，避免双向同时写同一属性导致漂移。

角色分工（可演进）：
- NetBox：SSOT，维护资产目录与关系；业务标签、责任人、应用分组、自定义注释、运行级别等协作字段在此维护。
- Terraform：以 NetBox 为输入进行资源编排；对其“权威”范围内的字段进行落地（CPU/内存/磁盘、拓扑存在性、由 IaC 管控的 IP 分配等）。
- Ansible：应用层安装、配置、校验与运行时验证；与 NetBox/Terraform 的记录进行一致性比对。
- 双向策略：从 NetBox 拉取非 Terraform 权威字段用于编排与校验；写回时严格限定 Terraform 拥有字段，避免覆盖人工输入。

字段所有权建议（当前约定，可在将来 pull 功能实现时更新）：
| 字段类别 | 当前写入来源 | 未来是否可读回 | 说明 |
| -------- | ------------ | -------------- | ---- |
| CPU/内存/磁盘 | Terraform | 是（校验） | 读回仅用于比对漂移，不反写调整 |
| VM / LXC 存在性 | Terraform | 否 | 由 IaC 创建，即权威 |
| 接口与 Cable 拓扑 | Terraform | 是（可视化比对） | 差异提示而非自动更改（当前 provider 对 VM 接口连线有限制） |
| 服务端口列表 | Terraform | 是（警报/冲突检测） | 未来可结合 NetBox 标签联动 |
| 标签/自定义字段 | NetBox 手工 | 是（采集） | 不覆盖人工维护内容 |
| 备注/描述 | 双方，但分段 | 是 | 约定描述前缀区分来源（如 Terraform: …）|

安全与合规：不在 NetBox 存放任何凭据；API Token 以变量方式传入。读取功能上线后亦不获取敏感字段。

当前登记范围：物理节点、虚拟机 / LXC、接口、IP、服务端口；桥接连接（cable）在设备接口（dcim.interface）层面可建模，但因 provider 限制暂不对虚拟机接口（virtualization.vminterface）进行 cable 建模。暂不包含：VLAN、前缀、机柜、供应商资产编号等扩展对象（将来扩展时需重新定义字段所有权）。

期望收益：
1. 快速回答“服务运行在哪个节点 / 哪条桥？”
2. 可视化二层桥接关系（vmbr1 ↔ eth0）。
3. 服务端口集中视图支持冲突检测。
4. 形成容量与拓扑基线，支持后期漂移比对。
5. 为后期 pull 功能预留清晰的字段边界。

更新策略：
- 目标工作流：NetBox 新增/修改 → Terraform 读取（pull）生成计划 → 应用到实际平台 → Ansible 完成配置与验证。
- 过渡阶段：Terraform 侧资产变更（新增/迁移/删减）→ 更新相应文件 → `terraform apply` 将变更同步到 NetBox（push），并逐步引入从 NetBox 的读取与校验脚本以减小漂移。

本目录用于通过 Terraform 将 Homelab 的 Proxmox 物理节点、虚拟机、LXC 容器以及其上运行的服务与网络拓扑同步到 NetBox，实现“物理 → 虚拟 → 服务”分层建模。文件拆分遵循最小职责与明确依赖顺序，便于维护与扩展。

## 一、文件列表与职责
| 文件 | 角色 | 主要资源 | 依赖输入 | 提供输出 |
| ---- | ---- | -------- | -------- | -------- |
| `versions.tf` | 版本锁 | terraform / provider 版本约束 | 无 | Provider 初始化约束 |
| `variables.tf` | 入口变量 | NetBox 基础访问参数 (URL, token) | 外部环境或默认值 | 供 provider 使用 |
| `main.tf` | 基础域对象 | `netbox_site`, `netbox_tag` | `variables.tf` | Site/Tag 供其他资源引用 |
| `pvecluster.tf` | 集群层 | `netbox_cluster_type`, `netbox_cluster` | `main.tf` site | Cluster ID 给设备/VM 使用 |
| `infrastructure.tf` | 物理层 | Manufacturer, Device Type, Role, 3×`netbox_device`, 宿主接口(`vmbr0`/`vmbr1`), IP | Cluster/Site | 设备与桥接口、管理 IP |
| `vm.tf` | 虚拟机层 (QEMU) | 3×`netbox_virtual_machine` (netbox/immich/samba), 各自 `eth0` 接口、IP | Cluster | VM 与接口标识 |
| `containers.tf` | 虚拟机层 (LXC 归类为虚拟计算单元) | 1×`netbox_virtual_machine` (anki LXC), 接口、IP | Cluster | LXC 与接口标识 |
| `services.tf` | 服务层 | 各 VM/LXC 上运行的应用/数据库/缓存/协议端口 `netbox_service` | VM/LXC 资源 | 服务与端口清单 |
| `connections.tf` | 二层连接 | 4×`netbox_cable` (vmbr1 ↔ eth0) | Physical interfaces + VM/LXC interfaces | 拓扑连接关系 |
| `terraform.tfstate*` | 状态文件 | 状态快照 | Terraform 运作 | 供计划/应用比对 |

## 二、资源分层与依赖顺序
1. Site/Tag (`main.tf`) → Cluster (`pvecluster.tf`)
2. Physical Devices & Bridges (`infrastructure.tf`) 引用 Cluster/Site
3. Virtual Machines / LXC (`vm.tf`, `containers.tf`) 引用 Cluster
4. Services (`services.tf`) 引用 VM/LXC
5. Connections (`connections.tf`) 引用 Physical 接口 + 虚拟接口

应用顺序（推荐）:
```
main.tf → pvecluster.tf → infrastructure.tf → vm.tf & containers.tf → services.tf → connections.tf
```

## 三、关键 NetBox 资源类型定义
- `netbox_site`: 地理或逻辑站点归属。
- `netbox_cluster_type`: 集群类型（此处为 Proxmox）。
- `netbox_cluster`: 虚拟化集群抽象，设备/VM 可挂靠其上。
- `netbox_device`: 物理服务器节点 (pve0/pve1/pve2)。
- `netbox_device_interface`: 物理设备的网络接口（含 Linux bridge 抽象 vmbrX）。
- `netbox_virtual_machine`: 虚拟计算单元（QEMU VM 与 LXC 容器在建模上统一处理）。
- `netbox_interface`: 虚拟机网络接口（eth0）。
- `netbox_ip_address`: 绑定到接口的地址对象，`object_type` 区分设备或虚拟接口。
- `netbox_service`: 应用或协议端口集合（支持多端口数组）。
- `netbox_cable`: 二层连接关系，将宿主 bridge 接口与虚拟机接口进行拓扑关联。

## 四、命名规范与约定
- 资源名称使用功能性短标识，如 `netbox_virtual_machine.immich`。
- 物理桥接口统一：`vmbr0` (管理/外部基础), `vmbr1` (虚拟工作负载)。
- VM/LXC 接口统一为 `eth0`，保持简单一致性。
- 磁盘大小统一换算为 MB (`disk_size_mb`)：例如 300G → 307200MB。
- 注释中标明来源：例如 VM 规格来自 `terraform/proxmox/*.tf`。

## 五、扩展与修改指引
| 场景 | 操作步骤 | 注意事项 |
| ---- | -------- | -------- |
| 新增物理节点 | `infrastructure.tf` 添加 device/interface/IP | 需引用现有 cluster/site ID |
| 新增 VM | `vm.tf` 添加 VM + 接口 + IP | 配合 `services.tf` 与 `connections.tf` 更新 |
| 新增 LXC | `containers.tf` 添加虚拟机资源 | 与 VM 模式保持一致接口命名 |
| 新增服务 | `services.tf` 添加 `netbox_service` | 避免端口重复冲突，明确描述 |
| 新增桥接连接 | `connections.tf` 添加 cable | termination 类型与接口 ID 匹配 |
| 修改规格 (CPU/内存/磁盘) | 更新 `vm.tf` / `containers.tf` | 保持与实际 Proxmox 配置一致并记录来源 |

## 六、连接与拓扑示意
```
[pve0 vmbr1]─┬─(cable)─[VM netbox eth0]
             ├─(cable)─[VM immich eth0]
             ├─(cable)─[VM samba eth0]
             └─(cable)─[LXC anki eth0]
```
所有虚拟计算节点通过同一二层广播域 `vmbr1` 获得独立 IP（192.168.1.100/101/102/104）。目前仅在设备接口侧（dcim.interface）记录桥接拓扑；虚拟机接口的 cable 建模因 provider 限制暂不启用。

## 七、与 Ansible 的对应关系
- Ansible 中的宿主组：`proxmox_cluster`（包含 pve0/pve1/pve2） ↔ 本目录 `infrastructure.tf` 物理节点。
- 部署的服务（Samba, Immich, Netbox, Anki）↔ `services.tf` 的端口/协议建模。
- 验证命令（Ansible `--tags verify` 输出）可与 NetBox 中服务端口对比，检验运行状态与配置一致性。

## 八、移除文件说明
- 原 `resources.tf` 已废弃（包含旧 Netbox VM 定义），重命名逻辑迁移至 `pvecluster.tf`，避免重复资源冲突。

## 九、后续改进建议
- 引入标签：为 VM/Service 添加分类标签（如 `database`, `cache`, `web`）。
- 自动校验：编写脚本比对实际 Proxmox (`qm config` / `pct config`) 与 NetBox 记录差异。
- 可添加 VLAN/子网：进一步用 NetBox 建模 L2/L3 网络结构。

## 十、常见错误与排查
| 错误 | 原因 | 解决 |
| ---- | ---- | ---- |
| Duplicate resource | 文件重命名后旧文件未删除 | 确认只保留一个定义 (grep 资源名) |
| 初始化失败 provider | versions.tf 漏写或版本不兼容 | 添加/更新 `required_providers` |
| IP 无法绑定 | 接口对象引用错误 | 核对 `interface_id` 与 `object_type` 匹配 |
| Cable 无法创建 | provider 限制或 termination 类型错误 | 设备侧使用 `dcim.interface`；虚拟机侧 `virtualization.vminterface` 目前不被 cable 端点支持，暂不创建 VM 接口 cable |

---
最后更新：2025-11-30。若新增层次请保持“物理 → 虚拟 → 服务 → 拓扑连接”结构，不要在单文件中混合多层资源。