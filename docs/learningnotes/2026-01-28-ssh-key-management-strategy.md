# 学习笔记：SSH Key 管理的混合策略 (Terraform + Ansible)

**日期**: 2026-01-28
**标签**: #Terraform #Ansible #SSH #DevOps

## 1. 问题背景
在 "Infrastructure as Code" 实践中，管理 SSH 密钥经常遇到一个矛盾：
-   **Terraform**: 负责创建 VM，并通过 Cloud-Init 注入初始 SSH Key。
-   **Ansible**: 负责后续的配置管理，也需要 SSH 连接。
-   **矛盾点**: 当需要添加新用户的 SSH Key 时，如果直接修改 Terraform 配置（更新 `sshkeys`），可能会导致已经运行在生产环境的 VM 被**销毁重建**，这是不可接受的。

## 2. 解决方案：Bootstrap Key 模式
为了解决这个问题，我们将 SSH Key 的管理职能分离：

### 2.1 Terraform: 仅负责 "Bootstrap" (启动)
-   **职责**: 确保 VM 创建后，自动化工具（Ansible）能够首次连入。
-   **配置**: 在 Terraform 的 `sshkeys` 中只维护**一个**长期不变的“Admin/Bootstrap Key”（例如 CI/CD 机器人的 Key 或运维负责人的主 Key）。
-   **优势**: 由于这个 Key 几乎永远不改，Terraform 就不会因为 Cloud-Init 变更而尝试重建 VM。

### 2.2 Ansible: 负责 "User Management" (日常维护)
-   **职责**: 管理所有团队成员、新设备的访问权限。
-   **配置**: 使用专门的 Ansible Role（如 `users` 或 `security`）来维护 `/home/user/.ssh/authorized_keys` 文件。
-   **优势**:
    -   **无损更新**: Ansible 修改文件是幂等的，不需要重启 VM。
    -   **灵活**: 可以针对不同主机组（Group）下发不同的 Key 列表。
    -   **快速**: 几秒钟即可完成所有机器的 Key 更新。

### 3. 操作流程示例

1.  **Day 0 (Provisioning)**:
    -   Terraform 使用 `var.bootstrap_ssh_key` 创建 VM。
    -   VM 启动，Cloud-Init 将此 Key 注入默认用户（如 `ubuntu`）。
2.  **Day 1 (Configuration)**:
    -   运行 Ansible Playbook，使用 `private_key` (对应 Bootstrap Key) 连接 VM。
    -   Ansible Role 将 `files/authorized_keys` 或 `group_vars` 中的**完整 Key 列表**覆盖到目标机器。
3.  **Day 2+ (Maintenance)**:
    -   新同事加入 -> 将其公钥添加到 Ansible 变量 -> 运行 Ansible Playbook。
    -   无需触碰 Terraform。

## 4. 总结
**“Terraform 建房子，Ansible 装修和发钥匙”**。不要让 Terraform 去管理那些经常变动的东西（如用户列表），让它专注于基础设施的不可变部分。
