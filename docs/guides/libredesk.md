# LibreDesk（已退役）

2026-10-23：管理员决定停止使用 LibreDesk，转向评估 Discord 工单机器人。

- 已删除 pve0 VM119（原内网入口 `192.168.1.119:9000`）及 Terraform inventory 记录。
- 已归档数据库、附件、配置、Redis 数据和原部署代码；从活动 Vault 移除 LibreDesk 专用凭据。
- 私有恢复归档：`/Users/weierfu/Projects/employee-workspace-admin/archive/retired-libredesk-20261023/`。
- 未配置公网域名或支持邮箱；Discord 替代方案尚未部署。

不要重新运行旧部署代码。恢复需管理员另行授权。
