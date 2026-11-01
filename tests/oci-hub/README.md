# OCI Hub 隔离原型验证

仅使用合成地址、密钥、临时 SQLite 与 backend-free Terraform root。不得复制真实 `settings.json`、Vault、BWS 令牌、requests/runs/state/bundles 到验证环境。

```bash
python3 tests/oci-hub/test-offline.py -v
python3 tests/oci-hub/test-native-authorization.py
python3 tests/oci-hub/test-native-mosh.py
sudo /opt/iac-venv/bin/python3 tests/oci-hub/test-spoke-reconcile.py
python3 tests/oci-hub/prepare-terraform.py
# 在输出的临时 root 中运行；provider 固定 bpg 0.70.0，不加载 HCP。
terraform init -backend=false -input=false
terraform validate
terraform test
sudo python3 tests/oci-hub/test-network.py
sudo /opt/iac-venv/bin/python3 tests/oci-hub/test-mosh-boundary-play.py
```

Ansible 使用 `tests/ci/fixtures/ansible.cfg`、`tests/oci-hub/inventory.yml` 和明确 roles 路径进行 lint/syntax；不运行 deploy/publish 流水线。网络测试创建唯一命名的 namespace/veth/bridge，结束时只移除本次 namespace；正向验证本人 SSH/HTTPS、PVE 保留私有源地址的纯路由，负向验证跨用户、管理端口、Hub input、PVE 伪造源、受保护 OCI 服务与 IPv6。移除 ACL 后再验证拒启和负向对照的连通性。内核缺少 VLAN 支持时明确打印 `NOT RUN`，不将该场景标通过。此测试不使用真实 WireGuard peer，不证明 cryptokey routing、Portal 恢复、PVE SDN Apply 或真实桌面已通过。

私有管理员工程：在仅源码副本生成合成 settings 后运行现有相关测试、`test-oci-hub.py` 与 `test-hub-store-artifact.py`。源码 artifact 只含 `services/oci-hub/{portal,ledger,executor}.py` 和 SHA256 清单，解包前验证固定文件集合、常规文件类型和校验值；禁止整目录同步到 OCI。

公开客户端独立 checkout 最新 `origin/main`（已包含 PR #1 的 v2 支持及 PR #2 的迁移指引），运行 `python3 tests/test_bootstrap.py -v`。新增 v2 同设备 ID 状态隔离、native SSH 参数、严格 profile/字段以及 Unix 合成目标 TLS pin；现有 Windows CI 执行 v1/v2 check/setup 契约，Windows TLS/真实 WireGuard 仍需独立环境验收。

R8 增补 `management_access` 合同：只允许明确远端来源 `/32` + 已分配 VMID 的 uplink 转发 TCP22；缺省无 grant 保持拒绝。离线测试覆盖来源/目标校验和控制端 `--require-management-vmid` 部署前门控；真实 netns 覆盖管理员 SSH 端口及回包、非管理员/其他端口/其他 VM 拒绝、跨工作区拒绝、VM 主动访问管理端拒绝、无 grant 拒绝。PVE 本机管理不受支持，input 没有广泛 established 放行。

## 无 GA2 的 Mosh 试点增量

以上命令均在已有授权的验证 Sandbox 内执行，不携带生产凭据。`test-native-authorization.py` 运行实际 Ansible 任务，验证原生公钥协调、重跑幂等、逐设备撤销、空清单及无效/旧授权的拒绝；`test-native-mosh.py` 运行已渲染启动器的参数测试，不创建真实 Mosh 会话或密钥。

`test-network.py` 另检查隧道内 UDP 往返、同 VM 两设备端口隔离、跨 VM/Hub input 拒绝，以及已有 UDP conntrack 下撤销 Mosh grant 后立即阻断、保留其他设备及 SSH。这使用 veth 模拟 WG 接口，仍不代表实际 WireGuard 或 Mosh 协议验收。

`python3 tests/oci-hub/prepare-ingress-terraform.py` 输出只含 OCI NSG 的临时 root。在其中运行 `terraform init -backend=false -input=false`、`terraform validate`、`terraform test`；固定 OCI provider 8.3.0，测试使用 mock provider，检查直连源、旧 GA 源兼容、歧义来源和过宽网段拒绝，不读取 OCI 凭据、不 apply。

`test-mosh-boundary-play.py` 在独立 namespace 执行实际 Ansible 策略任务，核对前驱 SHA、不变的候选字节、真实 nft 原子加载、路由和恢复重跑。旧 `test-existing-spoke-egress.py` 属于被替代的 VM500 过渡试验，已移至管理员私有执行历史，不属于当前独立 Hub 提交或执行入口。以上检查均不接触宿主或真实网关规则。

私有管理员源码还新增 `test-hub-mosh.py`；显式用 `IAC_TEST_ROOT` 指向无凭据 IaC 源码副本后执行。它校验现有 VM 只读绑定、无 Terraform apply、源代码/输入/执行目标/inventory 变更拒绝、两网关审批、中断恢复、错误 Ansible host 不推进，以及终端候选包、独立 Mosh 验收与邮件模板。测试不会访问真实 BWS、上传或发信。


2026-10-30 原生终端收口：私有 test-hub-mosh.py 已改为独立 VM 原生开户测试，覆盖邮箱/规格、旧身份复用、设备地址及端口分配、所有权冲突、动态来源边界、受保护冷创建复用和修订计划路径；不再要求 VM500 两网关过渡。当前云入口 mock 测试7项包含显式 dynamic 仅开放用户 UDP51824、拒绝放宽 Spoke 来源。用户跳过的专项验收另记 acceptance_waived，不与上述测试通过混同。
