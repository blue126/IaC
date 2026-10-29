# OCI Hub 隔离原型验证

仅使用合成地址、密钥、临时 SQLite 与 backend-free Terraform root。不得复制真实 `settings.json`、Vault、BWS 令牌、requests/runs/state/bundles 到验证环境。

```bash
python3 tests/oci-hub/test-offline.py -v
python3 tests/oci-hub/prepare-terraform.py
# 在输出的临时 root 中运行；provider 固定 bpg 0.70.0，不加载 HCP。
terraform init -backend=false -input=false
terraform validate
terraform test
sudo python3 tests/oci-hub/test-network.py
```

Ansible 使用 `tests/ci/fixtures/ansible.cfg`、`tests/oci-hub/inventory.yml` 和明确 roles 路径进行 lint/syntax；不运行 deploy/publish 流水线。网络测试创建唯一命名的 namespace/veth/bridge，结束时只移除本次 namespace；正向验证本人 SSH/HTTPS、PVE 保留私有源地址的纯路由，负向验证跨用户、管理端口、Hub input、PVE 伪造源、受保护 OCI 服务与 IPv6。移除 ACL 后再验证拒启和负向对照的连通性。内核缺少 VLAN 支持时明确打印 `NOT RUN`，不将该场景标通过。此测试不使用真实 WireGuard peer，不证明 cryptokey routing、Portal 恢复、PVE SDN Apply 或真实桌面已通过。

私有管理员工程：在仅源码副本生成合成 settings 后运行现有相关测试、`test-oci-hub.py` 与 `test-hub-store-artifact.py`。源码 artifact 只含 `services/oci-hub/{portal,ledger,executor}.py` 和 SHA256 清单，解包前验证固定文件集合、常规文件类型和校验值；禁止整目录同步到 OCI。

公开客户端独立 checkout 基线 `7acfc76ef5b795fa94533b04adfb1b7f3751a0a8`，运行 `python3 tests/test_bootstrap.py -v`。新增 v2 同设备 ID 状态隔离、native SSH 参数、严格 profile/字段以及 Unix 合成目标 TLS pin；现有 Windows CI 执行 v1/v2 check/setup 契约，Windows TLS/真实 WireGuard 仍需独立环境验收。

R8 增补 `management_access` 合同：只允许明确远端来源 `/32` + 已分配 VMID 的 uplink 转发 TCP22；缺省无 grant 保持拒绝。离线测试覆盖来源/目标校验和控制端 `--require-management-vmid` 部署前门控；真实 netns 覆盖管理员 SSH 端口及回包、非管理员/其他端口/其他 VM 拒绝、跨工作区拒绝、VM 主动访问管理端拒绝、无 grant 拒绝。PVE 本机管理不受支持，input 没有广泛 established 放行。
