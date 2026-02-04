# 项目规划 (Roadmap)

## 🎯 核心目标
建立以 **NetBox 为单一事实来源 (SSOT)**，由 **Jenkins 驱动 CI/CD**，通过 **Terraform + Ansible** 落地的全自动化 Homelab 基础设施。

**基础设施基准**:
- **Host**: pve0 (i5-8500T / 6C6T)
- **环境**: 混合虚拟化 (LXC + VM) + Docker

## 📅 阶段规划

### Phase 1: 基础设施即代码 (IaC) 核心 [已完成]
- [x] **Terraform 模块化**: Proxmox VM/LXC 标准模块
- [x] **Ansible 角色重构**: 标准化 Role 结构与变量管理
- [x] **密钥管理**: 实施 Ansible Vault + Terraform 桥接方案
- [x] **GitOps 基础**: 代码仓库结构确立

### Phase 2: 自动化流水线 (CI/CD) [进行中]
- [x] **Jenkins 基础**: 部署 Jenkins LXC 与 Cloudflare Tunnel Webhook
- [x] **Pipeline 逻辑**: 实现 Check -> Plan -> Apply -> Deploy 流程
- [ ] **文档自动化**: 实现变更驱动的文档同步 (NetBox 回写/拓扑生成)
  - 参考: `docs/improvement/inventory-and-document-sync-via-cicd.md`

### Phase 3: NetBox 驱动 (SSOT) [待开始]
- [ ] **NetBox 建模**: 完善 VLAN/Prefix/Device Type 模型
- [ ] **Terraform Pull 模式**:
  - 开发 POC: Terraform 读取 NetBox 数据源动态创建 Proxmox VM (替换静态 `.tf` 文件)
  - 目标: 在 NetBox 中添加 VM -> Commit 触发 -> Terraform 自动创建
- [ ] **网络自动化**: 端口冲突检测与 IP 自动分配逻辑

### Phase 4: 可观测性 (Observability) [待开始]
- [ ] **监控 (Metrics)**: 部署 Prometheus + Grafana
  - 监控对象: Proxmox 节点, 容器状态, 关键服务 (Caddy, Postgres)
- [ ] **日志 (Logs)**: 方案评估与落地
  - **硬件背景**: i5-8500T + 充足内存，足以支撑重型日志栈。
  - **备选方案**:
    1. **LPG (Loki)**: 云原生首选，资源最省，与 Grafana 统一。
    2. **ELK (Elasticsearch)**: 全文检索最强，工业标准，但运维较重。
    3. **Splunk**: 分析能力最强 (SPL)，开箱即用，但闭源且有 License 限制。
  - **决策路径**: 届时根据运维精力、学习目标和实际日志量级决定。

## 📝 备注与原则
- **SSOT 边界**: Terraform 拥有基础设施的"写"权限，但数据定义权逐步移交 NetBox。
- **安全**: 所有敏感信息必须通过 Vault 管理，严禁明文 Token。
- **文档**: 保持 `docs/learningnotes` 与实战同步，定期提炼为 Guide。
