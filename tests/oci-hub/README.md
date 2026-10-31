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

Ansible 使用 `tests/ci/fixtures/ansible.cfg`、`tests/oci-hub/inventory.yml` 和明确 roles 路径进行 lint/syntax；不运行 deploy/publish 流水线。网络测试创建唯一命名的 namespace/veth/bridge，结束时只移除本次 namespace；正向验证本人 TCP22/TCP8443 可达、PVE 保留私有源地址的纯路由，负向验证跨用户、管理端口、Hub input、PVE 伪造源、受保护 OCI 服务与 IPv6。移除 ACL 后再验证拒启和负向对照的连通性。内核缺少 VLAN 支持时明确打印 `NOT RUN`，不将该场景标通过。此测试不使用真实 WireGuard peer，不证明 cryptokey routing、Portal 恢复、PVE SDN Apply 或真实桌面已通过。

私有管理员工程：在仅源码副本生成合成 settings 后运行现有相关测试、`test-oci-hub.py` 与 `test-hub-store-artifact.py`。源码 artifact 只含 `services/oci-hub/{portal,ledger,executor}.py` 和 SHA256 清单，解包前验证固定文件集合、常规文件类型和校验值；禁止整目录同步到 OCI。

公开客户端独立 checkout 最新 `origin/main`（已包含 PR #1 的 v2 支持及 PR #2 的迁移指引），运行 `python3 tests/test_bootstrap.py -v`。新增 v2 同设备 ID 状态隔离、native SSH 参数、严格 profile/字段以及 Unix 合成目标 TLS pin；现有 Windows CI 执行 v1/v2 check/setup 契约，Windows TLS/真实 WireGuard 仍需独立环境验收。

R8 增补 `management_access` 合同：只允许明确远端来源 `/32` + 已分配 VMID 的 uplink 转发 TCP22；缺省无 grant 保持拒绝。离线测试覆盖来源/目标校验和控制端 `--require-management-vmid` 部署前门控；真实 netns 覆盖管理员 TCP22 端口及回包、非管理员/其他端口/其他 VM 拒绝、跨工作区拒绝、VM 主动访问管理端拒绝、无 grant 拒绝。PVE 本机管理不受支持，input 没有广泛 established 放行。

## 无 GA2 的 Mosh 试点增量

以上命令均在已有授权的验证 Sandbox 内执行，不携带生产凭据。`test-native-authorization.py` 运行实际 Ansible 任务，验证原生公钥协调、重跑幂等、逐设备撤销、空清单及无效/旧授权的拒绝；`test-native-mosh.py` 运行已渲染启动器的参数测试，不创建真实 Mosh 会话或密钥。

`test-network.py` 另检查隧道内 UDP 往返、同 VM 两设备端口隔离、跨 VM/Hub input 拒绝，以及已有 UDP conntrack 下撤销 Mosh grant 后立即阻断、保留其他设备及 SSH。这使用 veth 模拟 WG 接口，仍不代表实际 WireGuard 或 Mosh 协议验收。

`python3 tests/oci-hub/prepare-ingress-terraform.py` 输出只含 OCI NSG 的临时 root。在其中运行 `terraform init -backend=false -input=false`、`terraform validate`、`terraform test`；固定 OCI provider 8.3.0，测试使用 mock provider，检查直连源、旧 GA 源兼容、歧义来源和过宽网段拒绝，不读取 OCI 凭据、不 apply。

`test-mosh-boundary-play.py` 在独立 namespace 执行实际 Ansible 策略任务，核对前驱 SHA、不变的候选字节、真实 nft 原子加载、路由和恢复重跑。旧 `test-existing-spoke-egress.py` 属于被替代的 VM500 过渡试验，已移至管理员私有执行历史，不属于当前独立 Hub 提交或执行入口。以上检查均不接触宿主或真实网关规则。

私有管理员源码还新增 `test-hub-mosh.py`；显式用 `IAC_TEST_ROOT` 指向无凭据 IaC 源码副本后执行。它校验现有 VM 只读绑定、无 Terraform apply、源代码/输入/执行目标/inventory 变更拒绝、两网关审批、中断恢复、错误 Ansible host 不推进，以及终端候选包、独立 Mosh 验收与邮件模板。测试不会访问真实 BWS、上传或发信。


2026-10-30 原生终端收口：私有 test-hub-mosh.py 已改为独立 VM 原生开户测试，覆盖邮箱/规格、旧身份复用、设备地址及端口分配、所有权冲突、动态来源边界、受保护冷创建复用和修订计划路径；不再要求 VM500 两网关过渡。当前云入口 mock 测试7项包含显式 dynamic 仅开放用户 UDP51824、拒绝放宽 Spoke 来源。用户跳过的专项验收另记 acceptance_waived，不与上述测试通过混同。

## 桌面信任说明的离线合成演练

```bash
python3 tests/oci-hub/test-desktop-trust.py -v
```

此入口只需现有 Python 标准库与 OpenSSL，无需 Ansible、网络、sudo 或系统信任导入。沿用 Story8 的 `TemporaryDirectory` + OpenSSL 合成证书方式与 `198.18.53.0/24` 合成地址，在临时目录生成两套 CA、正确及错误 IP SAN 的叶证书；私钥仅在该目录存在，测试结束清理，不交付、不进入 Git。入口不读取真实设备包、inventory、profile、Vault、BWS 或生产证书。

正例核对 CA 的 DER SHA256（同时与 OpenSSL X.509 指纹交叉核对）、OpenSSL 服务端证书链验证、签名证书解码出的 IP SAN 与所分配 HTTPS overlay 根 URL。反例分别核对错误 CA、错误参考指纹、错误 SAN、另一目标 URL、缺失 CA、缺失独立来源/指纹、HTTP、旧 VM500 共享 URL，以及旧路径、loopback 和后端端口；这三种情况均以 `assigned-target-url-mismatch` 拒绝。测试内规则仅演练[设备信任说明](../../docs/guides/employee-browser-lifecycle.md)，不作为运行时 API，也不改变客户端协议。

全部通过仅证明合成说明核验，不代表真实 WireGuard、浏览器信任、设备撤销或本人 UAT 通过。真实设备、OS/浏览器及独立指纹渠道未提供时，指南中的记录仍保持“未确认”。


## Story10 隔离真实桌面协议演练

`test-desktop-network.py` 只在管理员批准且依赖预装的 Linux root 环境运行；默认只读预检，显式 `--execute` 才创建资源。固定私有 helper 摘要后仅复用其 Marionette 与受限瞬态 unit 工具，不调用历史 execute/preflight，不复制私有源码到公开 Git。

```bash
sudo python3 tests/oci-hub/test-desktop-network.py \
  --repo /tmp/vm502-story10-source-20261031 \
  --helper /tmp/vm502-story10-source-20261031/private/desktop-vertical.py \
  --helper-sha256 73d701ef560d9ce447fccd5c8d4f4f4c2d9fcc604f1973349de0c7859eb0baf2 \
  --run-root /run/vm502-story10-verify-20261031
# 同一命令追加 --execute 才执行；重跑必须使用新目录，禁止覆盖旧证据。
```

`--repo` 的载荷根目录须保留现有 `source-manifest.json`，包含固定 `baseline`、载荷 `revision`、六个公共输入的 `files` SHA256 和 `helper_sha256`；预检读取基线并核对输入，不新增参数。预检记录 ip/nft/systemd 及桌面工具版本、runtime/evidence 路径和任务 namespace/unit/veth/X display 写入范围。`/etc/oci-hub` 与 Firefox distribution 必须是已存在的非符号链接目录，用作只读材料挂载点，测试不会创建它们。

需预装 Python/Jinja2、systemd、iproute2、nftables、OpenSSL、nginx、KasmVNC、XFCE、Firefox、xauth、xprop、dbus 及非 root 的 employee 账号；还需 namespace/veth/nft/mount 能力。预检不安装软件，不调用现网桌面。能力不足时实际执行失败，不能将该项当作通过。瞬态 unit 最长 240 秒，使用空 HOME/XDG/GNUPGHOME/profile、ProtectHome 和只读挂载的合成 Firefox 信任与代理材料。

复用 `test-network.py` 的 Hub/users/workspace 拓扑与实际 boundary apply/verify；veth 模拟 WG 接口。当前 `desktop.conf.j2` 原样渲染，TLS 终止在目标合成 overlay `10.234.0.2:8443`，上游验证 `localhost:8444` 的独立 CA 与身份。真实 Firefox 不跳过证书验证，经 KasmVNC/XFCE/后端 Firefox 验证 HTTPS、WSS101、canvas、实际键盘往返，以及重连后保留输入。

矩阵包含错误来源、另一目标、前端 CA/IP SAN、Host/Origin、API/WSS 越权、后端直连、对实际 TLS8443 入口发送明文 HTTP、上游 CA/身份错误。每行记录实际结果、预期、动作与 TCP/离线/真实协议证据层级。离线旧 URL 保留实际说明校验正例；每个上游故障修改前立即保存实际 HTTPS 正例。helper 固定请求的 `acceptInsecureCerts=False` 记录为请求策略，不冒称能力 RPC 观察。每项保留正向对照。旧共享 URL 仅作离线输入拒绝，绝不连接 VM500。外部隔离与就绪的完整矩阵仍须独立运行 `test-network.py`；该旧入口验证 TCP22/TCP8443 和 UDP，不能称为 SSH/TLS 协议通过。禁用 forwarding 或移除策略时 verify 拒绝就绪，不能由此推断已有流量均阻断。

输出位于 `<run-root>-evidence/result.json` 和两张合成画面；只保留输入 SHA256、工具版本、各项实际结果、证据层级、资源收尾及非任务网络/服务元数据摘要。已知合成密码及 Basic 标记只在内存中与有界 HTTP 响应、合成前后端 DOM、结果和任务日志缓冲比较，仅输出检查次数及秘密不存在的布尔结果，发现泄露即失败；不向命令行或证据写入标记，不使用 OCR。密码、私钥、认证头、临时 profile 与运行日志只在任务运行根存在，收尾移除。非任务元数据不一致或收尾失败会使结果失败；执行前后的 namespace/服务需由执行者核对。公开源码不包含私有 helper。必需项失败、缺失或 NOT RUN 时整体不得称通过。

实际 OCI WireGuard peer、真实设备信任/独立 CA 渠道、现场撤销维护、Story12 本人 OAuth/中国网络 UAT 均未由本入口验证，必须保留为未执行。离线 `test-offline.py` / `test-desktop-trust.py`、TCP 夹具和本入口的真实桌面证据分别记录，不能相加替代现场验收。
