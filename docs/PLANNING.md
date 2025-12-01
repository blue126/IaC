# 项目规划

- 工作流目标：NetBox（SSOT）→ Terraform pull → 平台落地 → Ansible 配置与验证。
- 引入最小 pull 示例：从 NetBox 读取并编排一台 VM（不覆盖人工字段）。
- 网络模型扩展：VLAN/Prefix 建模与分配策略；端口冲突检测与标签联动。
- 引入Prometheus+Grafana实现监控
- 引入Splunk作为日志收集

## 备注
- 避免在仓库存放敏感信息（如 NetBox Token）；使用环境变量或 CI Secret。
- 字段所有权保持边界：Terraform 只写权威字段；人工维护的标签/备注不覆盖。