# Proposal: 变更驱动的自动化文档同步 Pipeline

> **状态**: Draft
> **日期**: 2026-02-04
> **作者**: Vincy

## 问题背景

网络基础设施的文档（设备清单、IP 分配、接口描述、拓扑图等）长期面临”文档永远过时”的困境。手动维护文档不仅耗时，而且在变更频繁的环境中几乎不可能保持同步。

## 目标

实现 **每次配置变更合并后**，Pipeline 自动完成以下工作：

1. 更新 NetBox 中的设备信息（接口描述、IP 分配等）
1. 自动生成网络拓扑图
1. 自动更新内部 Wiki / Confluence 上的网络文档

确保文档与实际网络状态始终一致，消除手动维护的负担。

## 架构设计

### 整体流程

```
Git Push / PR Merge
       │
       ▼
  Jenkins Pipeline
       │
       ├──► 1. 配置推送到网络设备 (Nornir / Ansible)
       │
       ├──► 2. 从设备采集实际状态 (Nornir + NAPALM/Netmiko)
       │
       ├──► 3. 回写 NetBox (pynetbox API)
       │         ├── 接口描述
       │         ├── IP 地址分配
       │         ├── VLAN 绑定
       │         └── 设备状态
       │
       ├──► 4. 生成拓扑图 (Nornir + N2G)
       │         └── 输出 SVG / PNG / draw.io 格式
       │
       └──► 5. 更新 Wiki 文档
                 ├── Confluence (REST API)
                 └── 或 Git Wiki (自动 commit)
```

### 阶段拆分

#### Phase 1 — NetBox 自动回写

**触发条件**: 配置变更 PR 合并到 main 分支后

**需要同步的数据**:

- 接口描述 (`description`): 从设备 running config 或变更文件中提取
- IP 地址分配: 接口 IP、子网掩码、VRF 归属
- VLAN 分配: access/trunk 模式、allowed VLANs
- 接口状态: admin up/down、oper status
- 连接关系: LLDP/CDP 邻居信息

**技术选型**:

- `nornir` + `nornir-napalm` / `nornir-netmiko`: 设备状态采集
- `pynetbox`: NetBox API 交互
- 自定义 Python 脚本: 数据映射与转换逻辑

**关键考量**:

- 采用 **幂等操作**: 多次执行结果一致，避免重复创建
- 设备不可达时的 **错误处理与重试机制**
- 变更前后的 **diff 对比与日志记录**

#### Phase 2 — 自动生成拓扑图

**数据来源**: NetBox（Phase 1 更新后）或直接从设备采集的 LLDP/CDP 数据

**工具链**:

- `N2G` (Need to Graph): 支持从多种数据源生成网络图
  - 输入: CDP/LLDP 数据、NetBox 导出
  - 输出: draw.io XML、yEd graphml、SVG/PNG
- 备选: `pyvis`（交互式 HTML 图）、`diagrams`（代码即图表）

**拓扑图类型**:

- L2 拓扑: 交换机互联、VLAN 域
- L3 拓扑: 路由器互联、子网关系
- 物理拓扑: 机柜视图、线缆连接

**输出存储**:

- SVG/PNG 提交到 Git 仓库的 `docs/topology/` 目录
- draw.io 格式便于后续手动微调

#### Phase 3 — Wiki / Confluence 自动更新

**更新内容**:

- 设备清单总览页面（从 NetBox 拉取最新数据渲染）
- IP 地址分配表
- VLAN 列表与用途说明
- 嵌入最新的拓扑图
- 变更历史摘要（从 Git log 提取）

**实现方式 (二选一)**:

|方式                 |优点              |缺点                 |
|-------------------|----------------|-------------------|
|Confluence REST API|团队熟悉、搜索方便       |需要维护 API token、格式受限|
|Git Wiki (Markdown)|与代码仓库一体、版本控制天然集成|团队可能更习惯 Confluence |

## 技术依赖

|组件              |用途                |备注              |
|----------------|------------------|----------------|
|Jenkins         |CI/CD 编排          |已有或计划部署         |
|Nornir          |网络自动化框架           |Python 原生，适合复杂编排|
|NAPALM / Netmiko|设备交互              |NAPALM 提供统一抽象层  |
|pynetbox        |NetBox API 客户端    |官方维护            |
|N2G             |拓扑图生成             |支持多种输出格式        |
|NetBox          |网络 SoT (IPAM/DCIM)|需要预先部署并录入基线数据   |

## 前置条件

- [ ] NetBox 部署完成，基线数据已录入
- [ ] Jenkins Pipeline 基础框架搭建完成
- [ ] 网络设备的自动化访问凭据管理（Vault / Jenkins Credentials）
- [ ] Git 仓库结构规划（配置模板、文档目录等）

## 风险与注意事项

- **NetBox 数据一致性**: 如果存在手动修改 NetBox 的情况，需要明确 Pipeline 回写是否覆盖手动数据。建议 Pipeline 为唯一写入入口。
- **设备不可达**: Pipeline 应能优雅处理部分设备离线的情况，更新可达设备的信息并报告失败。
- **敏感信息**: 确保拓扑图和文档中不暴露密码、community string 等敏感数据。
- **执行时间**: 大规模环境下全量采集可能耗时较长，考虑增量更新策略。

## 后续扩展

- 集成 Batfish 做变更前的配置验证
- 集成 Slack/Teams 通知，变更完成后自动通知团队
- 网络合规检查（ACL 审计、NTP/Syslog 配置一致性）
- 基于 Git diff 的智能增量更新（只采集受影响的设备）
