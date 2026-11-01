# 现有 VM 的 OCI Hub Mosh 试点

本文件已被[新建 VM509 的独立试点](mosh-oci-hub-vm509.md)替代，只保留历史审计；不要执行这里的旧申请。

2026-10-30 已完成独立 BWS 项目及 OCI Hub 首次初始化。用户撤回“经 VM500 出网”的过渡安排，要求新路径从首次验收起独立。当前 `attach-mosh` 代码及其已生成审批仍依赖 VM500，不能继续执行；须先按[修订设计](../architecture/mosh-oci-hub-transition.md)补齐独立 PVE 网络、原 VM 第二网卡、路由及联合 hook，再生成新计划。VM502 未完成接入，端到端验收未通过。

以下字段和步骤保留为原过渡实现的历史契约，不是新独立路径的可执行部署指引。不要运行下列旧 apply 命令。

## 既有入口与申请

在规范私有管理员目录使用原 `onboard.sh`，独立 `oci-hub` profile 下增加 `operation=attach-mosh`。这是现有 VM 的终端试点，不调用“创建 Hub VM”的 Terraform apply。首轮仅接入一个 VM 的一台设备；发现该 VM 已有其他新方案设备时拒绝不完整 roster，避免覆盖其授权。

私有申请示例，不包含密钥：

```json
{"profile":"oci-hub","recipient":"alice@example.test","operation":"attach-mosh"}
```

邮箱派生 ID 规则不变；已有明确的 employee_id/device_id 可以显式保留。不要把示例邮箱、地址或 VMID 当成实际分配。

```bash
bash ./onboard.sh --profile oci-hub plan requests/alice-hub-mosh.json
# 审阅实际输出后，使用此次批准的精确摘要：
bash ./onboard.sh --profile oci-hub apply requests/alice-hub-mosh.json APPROVED_SHA256
```

以上为管理员入口的命令模板，必须从私有项目执行；实际操作使用绑定本次 IaC worktree 的批准 Sandbox。不得直接运行 playbook 替代入口或审批。

## 部署前需要准备的私有配置

- OCI Hub 已按 [Hub 部署契约](oci-hub-workspace-prototype.md) 上线：Portal、执行器、月账和两个 WG 接口可验证，使用独立 BWS 项目。此入口不会自动创建云主机、BWS 项目或放宽云网络权限。
- OCI NSG/安全列表须已按独立批准范围允许测试设备实际来源到 UDP 51824，以及家中工作区出口到 UDP 51825。接入动作追加的是 Hub 本机策略，不会自动修改云 NSG；只改本机规则不代表云端口已可达。
- 对已有 OCI 主机，`oci_hub_ingress.existing_nsg_id` 可指定已经绑定的 NSG，只追加两类精确来源规则，不改变 VNIC 或原规则；省略时仍创建独立 NSG，须另行审批绑定。不要创建未绑定的 NSG 后就宣布端口可达。私有计划与认证变量留在 employee-data，HCP 继续保存基础设施 state。
- `settings.oci_hub.mosh_attachments[employee_id]` 保存该设备的预配置分配：recipient、device_id、workspace.overlay、runtime_bws_record、public_vars、registration_request、bundle_request，以及设备实际公网 `/32` 的 device_public_source。
- `existing_vm` 必须精确包含 resource_address、vmid、node、hostname、inventory_host；resource_address 指向原 `proxmox_virtual_environment_vm.employee_workspace[employee_id]`，node 为 pve2，VM 已运行且 SSH host pin 已独立确认。
- `mosh_inventory` 包含唯一 `oci_hub_mosh_pilot` 目标、`oci_hub_mosh_gateway` 中的 OCI 主机以及原 `employee_access` 网关。`mosh_hub_inventory_host`、`mosh_existing_gateway_inventory_host` 精确指定两个网关的 inventory host；`ssh_target` 和 `mosh_existing_gateway_ssh_target` 是已经严格配置主机校验的管理 SSH 目标。禁止整个 LAN 默认放行。
- public_vars 中显式绑定 employee_workspace_profile=existing、employee_workspace_user=employee、employee_workspace_id、employee_workspace_hub_parallel_access=true、oci_hub_mosh_target_host、oci_hub_mosh_employee_id、oci_hub_mosh_expected_hostname、oci_hub_mosh_attach_authorized=true。提供 VM Spoke overlay、设备 `/32` 列表、OCI endpoint 的 UDP 51825 和已核对的 Hub 公钥。
- `oci_hub_workspace_devices` 是本次单设备的 address/ssh_public_key；它必须与新方案 BWS 设备 SSH 私钥派生的公钥一致。VM WG 公钥也必须与 BWS 私钥和登记请求一致。安装 Mosh/WireGuard 必须额外批准 `oci_hub_mosh_install_authorized=true`，默认只检查已安装运行时。

配置仍采用既有 Hub 后端的预分配方式；不会根据一个邮箱自动猜测 VM、overlay、BWS 记录或主机身份。这里只说明字段契约，真实资料留在 `remotecc/employee-data/`。

## 计划与应用行为

计划读取 Terraform state 核对原 VMID、节点、主机名和运行状态，并通过 `ansible_host.employee_access[0]` 的网络映射核对 VM500 的物理接口、VM IP 和禁用状态。只读获取两个网关的现有策略，生成追加候选：

1. VM500 增加该物理 VM → OCI 公网 IP 的 UDP 51825 原始方向与已建立回包例外。保留完整原策略/NAT及原 OCI SSH/浏览器扩展，例外位于对应受保护目标拒绝规则前；禁用的 VM 没有可插入的活动边界，不被旧例外重新放行。
2. OCI 保留其他设备映射，追加本设备 → 本 VM 的 Mosh UDP 范围，并保留已有 SSH 22。设备公网来源只追加经批准的 `/32`，不删其他来源、不开放公网 Mosh 端口。

审批摘要绑定申请、源代码、完整 Terraform state 指纹、既有 VM、inventory、执行目标、两个策略候选、登记与设备包输入。任何变化需要重新核对；不会通过 Terraform apply 创建、重建、扩容或替换原 VM。

应用依次协调 VM500 例外、OCI ACL、VM Spoke/native Mosh/并行 SSH 授权、Portal 登记和仅新身份启用，再做服务检查和候选包生成。Ansible 返回 0 但没有实际执行指定 host 的 recap 时，不推进检查点或启用 peer。重跑只恢复缺失阶段；策略漂移或身份冲突时停止，不盲目重建。

VM500 例外由原完整 firewall controller 管理；systemd drop-in 在普通基线重载后重加例外，完整 verify 同时检查其字段与位置。清空例外清单可撤销其访问，原 VM 禁用仍生效。逐设备或配额撤销的安全边界是 OCI ACL/peer；不对共享 employee 用户整体 pkill。已失去网络的 Mosh 进程按 7 天网络断连超时回收，不新增另一套进程管理服务。

## 设备包、验收和交付

仍为严格 v2 `profile=oci-hub`，终端包使用 `access_mode=mosh` 与 `mosh_ports="START:END"`，允许原 `employee-*` 主机名，不包含 desktop_url/tls_certificate_sha256。旧桌面 v2 和 v1 包按原约定验证；不同模式的字段不能混用。

公开客户端候选代码从包读取 native Mosh 入口 `workspace-mosh`、设备端口和独立 alias。macOS/Linux 的 `bootstrap.sh mosh` 要求本人交互终端；Windows 原生完成 VPN/SSH/SFTP，Mosh 在 WSL 使用同一设备新方案 SSH 配置，禁止第二套 WSL VPN。终端 verify 不探测桌面，但也不冒充 Mosh 人工验收。

候选包只有经过独立批准的真实验收后才能交付。Mosh 模式的验收保留 via_hub、native_ssh、ssh_host_pin、跨员工/管理/横向/工作区主动连接拒绝，另需 native_mosh、mosh_port_isolation、mosh_revocation、old_access_preserved；不要求 TLS/desktop_wss。证据仍绑定真实映射代次、策略、包内外摘要，不能由客户端自报替代。

Temp.sh 上传和微软通知继续分别按既有交付范围审批；邮件使用终端模式模板，最上方给出含实际链接的加粗 Agent 提示词，明确跳过 Claude 登录。没有实际验收时输出 awaiting_e2e_verification，保持上传/通知阻止。

## 已验证范围

源码验证见 [tests/oci-hub](../../tests/oci-hub/README.md) 和私有 `test-hub-mosh.py`。覆盖原 VM 不变、摘要/输入/执行目标变更拒绝、中断恢复、错误 host 不推进、设备包与独立验收、实际 Ansible/nft 策略事务，以及旧网关 OCI 例外的精确流向、重载、禁用和撤销。

这些检查不证明真实 WG 握手、Mosh 体验、中国网络延迟或 Windows/WSL 已验收。公开客户端尚需按批准范围发布，才能让员工通过 GitHub 获取此次能力。

## 2026-10-30 首次初始化记录

- 新建独立 EmployeeWorkspace-OCIHub 项目和仅对该项目读写的机器账号；六条独立记录保存 Portal、两接口、用户、工作区和设备凭据，原项目保持隔离。机器令牌及加密运行时变量仅保存在私有数据目录。
- 使用固定摘要的 Portal v2.3.1 ARM64，在真实 OCI 主机的临时网络命名空间先验证 API、接口/路由、禁用后登记、启用和撤销；随后通过部署 playbook 初始化正式 Hub。
- 正式部署 recap 为 failed=0/unreachable=0；边界与路由校验、Portal 和配额定时器检查通过。原有 WG 接口保留，两个新接口初始化完成，未登记或启用员工设备。
- 云端仅在既有绑定 NSG 添加批准的来源到两个新 WG 端口；Terraform 精确计划及 apply 均为 2 added、0 changed、0 destroyed。主机已有 INPUT 末尾拒绝规则前添加带独立标记的精确放行，隔离测试确认保留原规则。
- 原 VM502 接入计划已获批并尝试执行，但停在 VM500 例外校验，检查点未推进；VM500 已写入本次 controller、例外配置和 systemd drop-in，须纳入后续精确撤回清单。尚未配置 VM502 Spoke、登记或启用员工设备。随后用户要求移除 VM500 依赖，旧计划撤回，不能继续恢复 apply。
