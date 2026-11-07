# Q4

公开执行器默认配置同时声明 /srv/remotecc 和 /srv/iac 两个 checkout；只有 remotecc 条目声明 /run/wsctl.lock。这是配置声明，未现场验证部署状态。 `ansible/roles/remotecc-ops-runtime/defaults/main.yml:12-27 (remotecc_ops_repositories) @ aad7d3d`

公开 Ansible 配置把 roles、collections 和 .vault_pass 解析为所在 Ansible 树的相对资源，迁离代码根不能自动带走这些运行材料。 `ansible/ansible.cfg:6-10 (roles_path) @ aad7d3d`

公开接口文档明确：源码复制不等于配置和数据绑定复制；执行器上的 IaC 根由受保护配置决定。私有入口的精确解析与拒绝条件见独立受限证据包。 `docs/architecture/remotecc-layout.md:27-39 (Worktree) @ aad7d3d`

上述为已检查范围；不是整个仓库的反向依赖穷举。全部按 load-bearing 进入验证。
