# 员工工作区当前验证

旧 VM500 gateway role、入口和对应 dispatcher/双跳/WG 运行测试已退役，执行历史位于管理员私有记录。不要从此目录重建旧网关。

当前保留：

- `test-login.py`：真实 tmux/PTY 加合成 OAuth 进程，验证 workspace-login，不读取个人登录态。
- `prepare-terraform.py`、`startup.tftest.hcl`、`retirement.tftest.hcl`、`check-startup-plans.py`、`test-disk-protection.py`：backend-free 固定 provider 夹具，验证旧永久分配/磁盘保护和退役标记；不代表旧部署入口仍可用。
- `fixture.json` 仅为上述合成 Terraform 数据，不可直接部署。

新 Hub 的原生授权、Mosh、Spoke 和边界测试见 `tests/oci-hub/README.md`；已拆出的 PVE 退役 guard 见 `tests/retired-workspace-boundary/test-offline.py`。管理员公钥维护由 `admin-ssh-keys` 共享 role 承担。

所有 Terraform/Ansible 检查在已批准验证 Sandbox 中执行，不携带生产 Vault/BWS/状态；个人 Claude 登录不属于自动验证。
