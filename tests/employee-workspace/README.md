# 员工工作区当前验证

旧 VM500 gateway role、入口和对应 dispatcher/双跳/WG 运行测试已退役，执行历史位于管理员私有记录。不要从此目录重建旧网关。

当前保留：

- `test-login.py`：真实 tmux/PTY 加合成 OAuth 进程，验证 workspace-login，不读取个人登录态。
- `test-desktop-*.py`、`test-browser-lifecycle.py`：桌面与浏览器生命周期的合成验证。
- `test-locale.py`：对临时文件执行实际的 `locale.yml` 任务，验证写入 `LANG=C.UTF-8`、`AcceptEnv LANG LC_*` drop-in、重跑无变更、缺少 C.UTF-8 时拒绝；本机有 `sshd` 时再用 `sshd -T` 检查它与 Mosh drop-in 共存。

旧员工模型（`employee_workspaces` 永久分配、磁盘保护与退役标记）的 Terraform 夹具已随该模型于 2026-11-02 移除。

新 Hub 的原生授权、Mosh、Spoke 和边界测试见 `tests/oci-hub/README.md`。管理员公钥维护由 `admin-ssh-keys` 共享 role 承担。

所有 Terraform/Ansible 检查在已批准验证 Sandbox 中执行，不携带生产 Vault/BWS/状态；个人 Claude 登录不属于自动验证。
