# 员工 Claude Code 工作环境：实施与验收

> 历史说明：本页中的旧 VM500 gateway 部署入口已退役并移除。当前开户与维护以 [OCI Hub 原生入口](../deployment/oci-hub-native-provisioning.md) 为准，不执行旧脚本；早期规划内容仅供追溯。


本实现对应 [SPEC](https://github.com/blue126/IaC/blob/751f7b6da8c4bf92cfa62c8fc77f7c61626ce146/_bmad-output/specs/spec-employee-claude-workspace/SPEC.md)、[访问契约](https://github.com/blue126/IaC/blob/751f7b6da8c4bf92cfa62c8fc77f7c61626ce146/_bmad-output/specs/spec-employee-claude-workspace/access-and-isolation.md) 和 [验收矩阵](https://github.com/blue126/IaC/blob/751f7b6da8c4bf92cfa62c8fc77f7c61626ce146/_bmad-output/specs/spec-employee-claude-workspace/verification.md)。代码生成、离线测试不代表部署或 CAP 验收通过。当前采用单节点、每人一个持久 VM、外置受管 SSH 入口；WireGuard 是待实测的自建接入候选。

## Terraform 模块与 provider

`terraform/modules/proxmox-vm/` 是 VM 结构模块：按模板名称查找并克隆 VM，按输入设置 CPU、内存、磁盘、单张网卡与 Cloud-Init。`proxmox.pve2` 是同一个 `bpg/proxmox` provider 的配置别名，负责连接独立 pve2 和提供 API/SSH 身份；它既不是另一种 VM 模块，也不是另一个 Terraform state。

员工网关和个人 VM 目前直接声明为 `proxmox_virtual_environment_vm`。网关需要按永久槽位生成多张隔离网卡；个人 VM 还需要专属 bridge、vendor-data、启动 hook、边界就绪前停机及 `prevent_destroy`。通用模块当前没有这些输入与生命周期约束。将既有资源改为模块调用会改变 Terraform state 地址，须先扩展模块、安排 state 迁移，并通过计划证明个人 VM/磁盘没有替换或删除；不能只改 HCL 调用形式。

现有默认 provider 与 `proxmox.root` 指向 pve0/pve1 集群；员工资源现在统一使用已有的 `proxmox.pve2`，以独立 pve2 的 API token 认证，并通过已核实的 SSH agent 登录。原 `proxmox.employee` 使用同一端点但改用 `root@pam`；只读 ACL 核对显示 pve2 token 拥有员工节点、snippets 存储和 VM 所需权限。定向 Terraform 计划的资源变更数为零；应用后 state 中六个员工 Proxmox 资源均绑定到 `proxmox.pve2`，原别名已移除。未借此调整 token 权限或 VM 配置。provider 选择与是否复用 VM 模块是两个独立决定。

`proxmox.pve2.ssh.username` 显式指定 `root`，用于 PVE 节点文件等管理操作的既有 SSH agent 身份；API 继续使用原 token，不改成 `root@pam` 密码认证。SSH 用户配置作用于该 provider 的所有消费者，包括现有 container-lab 与 PBS 资源，不能将它描述为仅影响员工 VM。本轮沿用统一 `pve2` provider，不引入新的员工别名。

## 网络与身份

每位员工拥有一个无物理端口、无 PVE 主机地址的内部 bridge，桥内只有本人 VM 单 NIC 和网关的专属 NIC。每台员工 VM 的 PVE pre-start hook 会启动并核验本人 bridge 的外部边界；边界不存在或员工禁用则拒绝该 VM 启动，不修改全局 `pve-guests.service`，不阻断无关 VM 自启。PVE 的 `bridge employee_boundary` 表按每人桥上的 guest/gateway tap、源 MAC/IP 限制二层帧，只允许 IPv4 和面向本网关的 ARP；阻断访问 PVE 本机、VLAN、IPv6及其他端口。网关 `inet employee_access` 按入接口限制 IPv4，禁止设备转发、VM 互访、私网、Tailscale、明确受保护地址和家庭公网回流。公网开发流量经网关 NAT 和澳洲 WAN 出站。所有 DNS 都使用明确的公网解析器，无内部 DNS 例外。两层都只更新各自专属 nft 表，不清空全局规则。

网关通过 MAC 匹配稳定接口名；每位员工登记永久 `nic_slot`，从 1 连续分配，新员工追加下一个槽位，不按姓名排序。Terraform 保存创建时槽位、节点、bridge、地址、gateway、MAC及DNS，并拒绝不支持的原位网络变更；磁盘容量仅接受正整数GiB的 `G` 格式（例如 `50G`），不能用 `1T` 或省略单位；网关 NIC、emp 接口和 PVE tap 都按槽位生成。停用员工保留 roster 和槽位。增员后核对新增 NIC/tap 和规则，完成实测后开放设备授权。任何员工 VM 迁移到另一 PVE 节点都超出当前单节点设计，不能直接 live migrate 后宣称隔离仍成立。

员工设备只进入 WireGuard，再访问网关 WireGuard 地址的专属 sshd。每台设备一个 `ed-*` 系统账户、一把设备 SSH 公钥、一个 WireGuard 公钥和唯一地址；私钥留在设备。入口 `ForceCommand` 根据服务端文件选择固定本人 VM，内层 SSH 使用独立系统密钥和预核验 host key。只接受空命令（交互终端）或精确的 `employee-sftp` 子系统命令；普通 `ssh host command`、旧版 SCP、rsync 等任意命令模式拒绝。现代 SFTP 客户端请求 `sftp` 子系统时，入口 sshd 将它映射为 `employee-sftp`，内层请求客机 `sftp`。公司入口不提供自由 shell/sudo，不接收用户环境，禁 SSH 内置转发、隧道、escape、代理和连接复用。

员工仍有 VM 内完整 sudo。修改客机 sshd 不改变入口映射或 VM 外规则。允许正常公网开发连接意味着员工可能建立第三方应用层中继；本实现不宣称识别全部中继或阻止 sudo 替换凭据。

管理员 sshd 只绑定网关 uplink 地址，防火墙只允许显式维护源访问固定 uplink IP；该管理规则在员工接口与 WireGuard 拒绝规则之后，且不依赖 uplink 的旧/新接口名，因此首次 netplan 重命名前后新建管理 SSH 均可用；网关关闭 Ubuntu SSH socket activation，避免 wildcard socket 占用专属入口。维护源可经已批准静态路由通过网关访问个人 VM 的 SSH。不得给员工维护来源地址或管理员密钥。不得把一般员工 VPN 网段登记为维护来源。

## 部署输入与顺序

本次交付实现及独立 Sandbox 验证。真正安装、部署、写凭据或变更网络前仍须另行授权。

1. 核实 Q-4／Q-5：PVE 节点和 provider 指向同一集群；VMID、bridge、子网、MAC 无冲突；现有 PVE nft/防火墙规则与新表共同生效；所有家庭公网 IP、受保护服务及 NAT 回流路径已列出；明确维护源和恢复管理路径。bridge provider 会应用节点待生效网络配置，先处理其他 pending 网络更改，不能直接套用示例地址。当前员工资源使用专用 employee provider，API以root@pam认证到独立pve2，SSH也限定该节点；既有集群与pve2 token providers不变。启动hook和可执行snippet需要这一管理认证。
2. 先以prepare-employee-pve.yml校验固定Ubuntu26.04镜像摘要并创建本任务专用employee-snippets存储，不修改既有storage。Terraform创建从未启动的干净模板；每次克隆的vendor-data安装qemu-guest-agent，核实SSH host keys独立生成。模板不含员工令牌、浏览器状态或设备私钥。网关模板不得预启用路由、额外 NIC、代理服务或 cloudflared。确认既有备份作业是否自动纳入新 VMID，Q-6 未确定前不配置个人凭据。
3. 填写 `terraform/proxmox/employee-access.tf` 和 `employee-workspace.tf` 的输入。默认 `employee_access=null`、`employee_workspaces={}`，不会创建任何员工资源；不改旧服务输入。下面只说明数据形状，地址和 VMID 必须现场分配：

```hcl
employee_access = {
  node               = "pve2"
  pve_inventory_host = "pve2"
  vmid               = 500
  template_id        = 9000
  storage_pool       = "mainpool"
  uplink_bridge      = "vmbr0"
  uplink_address     = "192.168.50.2/24"
  uplink_gateway     = "192.168.50.1"
  uplink_mac         = "02:00:00:00:00:01"
  dns_server         = "1.1.1.1"
  admin_public_keys  = ["ssh-ed25519 REPLACE_WITH_ADMIN_PUBLIC_KEY"]
  boundary_ready     = false # Set true only after the boundary-only Ansible step.
  snippet_datastore  = "employee-snippets" # Prepared by the dedicated playbook.
}
employee_workspaces = {
  alice = {
    nic_slot    = 1
    vmid        = 501
    bridge      = "vmbr501"
    address     = "10.231.1.2/30"
    gateway     = "10.231.1.1"
    mac_address = "02:00:00:00:01:02"
    gateway_mac = "02:00:00:00:01:01"
    disabled    = false
  }
}
```

4. 初次部署须保持 `boundary_ready=false`；为既有网关增加员工时，候选工作区默认 `start_ready=false, hook_bound=false`，两个字段均为保守默认值。Terraform 先创建停机、`on_boot=false` 的员工 VM，并上传该 VM 的可执行 pre-start hook。PVE API token 不能设置 root-only 的 `hookscript` 字段；私有管理员流程随后通过既有 PVE 管理 SSH 执行 `bind-workspace-hook.yml`，核对 VMID、名称、隔离网桥、停机状态、禁用自启动以及 root 所有的 hook 文件，仅绑定该 VM 的 hook。该步骤失败即中止，不扩大通用 provider 的 API 身份。Terraform 对既有 `hook_script_file_id` 使用 `ignore_changes`，上传文件仍为 VM 的显式依赖。

   独立核对实际绑定完成后，私有管理员流程才可设置 `hook_bound=true`；该字段是管理员确认，不能由客户端自报。随后用专属 inventory 执行 `bootstrap-employee-workspace.yml`，部署 PVE 边界与受控公网出口，并登记本人网段路由；边界验证成功后，才通过单独校验的首次启动计划设置 `start_ready=true`。只有全局边界就绪、hook 已确认、工作区就绪且未禁用时，`started/on_boot` 才能为真。任何后续启动均由该 VM hook 检查本人 guest/gateway tap 的 input/forward/output 拒绝规则及 base chain 的 family/type/hook/priority；缺失或服务失败只拒绝该 VM。snippet datastore 必须事先支持 snippets，不能自动修改既有 storage 配置。审阅计划中的磁盘、NIC 和 bridge 变更，日常开户不得替换或删除个人 VM。

   员工 VM、永久槽位和隔离桥保留 `prevent_destroy`。日常停用使用 `disabled=true`，不删除 map 条目；NIC 断开、`started=false` 和 `on_boot=false` 会保留磁盘。只有获明确永久删除授权时，才使用 `retired=true, disabled=true, start_ready=false, hook_bound=false`，从 VM、hook 和动态主机清单中退役该记录，并单独验证仅涉及指定目标的删除计划；永久网络槽位与桥继续保留。正式配置不移除默认删除保护。仍在 state 中的 VM 会阻止普通退役 plan，这是保护生效；管理员必须先备份 state 与配置，再按已批准的专属退役流程处理指定 VM，不能仅靠 `state rm` 把仍存在的 VM 留成无人管理的资源。退役后保留带 `prevent_destroy` 的 `employee_retirement` 标记；清除 `retired` 会试图删除此标记并被阻止，避免重建同 VMID 的空白 VM。

5. 通过PVE控制面guest-agent读取公钥（例如qm guest exec读取/etc/ssh/ssh_host_ed25519_key.pub），独立核实每台VM的Ed25519 host key，填入网关 `employee_access_host_keys`，不能使用未经比对的 `ssh-keyscan` 自动信任。改变 host key 后旧连接会失败，先调查原因再按管理流程更新。填写 Ansible `host_vars/employee-access.yml`，设备和节点信息来自专属 Terraform inventory；PVE 节点须已有可用管理 inventory：

```yaml
employee_access_wireguard_address: 10.230.0.1/24
employee_access_maintenance_sources: [192.168.50.10/32]
employee_access_protected_ipv4: [203.0.113.0/28] # Replace with actual protected public services.
employee_access_home_public_ipv4: [198.51.100.20/32] # Replace with every actual WAN/hairpin address.
employee_access_host_keys:
  alice: ssh-ed25519 REPLACE_WITH_VERIFIED_VM_HOST_KEY
employee_access_devices:
  ed-alice-laptop:
    employee: alice
    enabled: true
    address: 10.230.0.2
    ssh_public_key: ssh-ed25519 REPLACE_WITH_DEVICE_PUBLIC_KEY
    wireguard_public_key: REPLACE_WITH_DEVICE_WIREGUARD_PUBLIC_KEY
```

系统第二段 SSH 私钥采用 `vault_employee_access_private_keys` 字典（按设备账户索引），网关 WireGuard 私钥采用 `vault_employee_access_wireguard_private_key`。这四组员工接入私钥现由私有管理员项目在 Bitwarden Secrets Manager 的 `EmployeeWorkspace` 项目管理；`onboard.sh` 在运行时把它们与 IaC Vault 合成为临时加密 Vault，角色 defaults 仍只作间接引用，部署任务 `no_log`。修改受管主机前，控制端以已有 Ansible Python/cryptography 和 ssh-keygen 检查必需私钥可解析且唯一；缺失或损坏时先失败，不更改账户或边界。不要把员工私钥放回全局 Vault、Terraform、Cloud-Init、示例或 Git 明文。员工 OAuth 凭据不由管理员托管。已有 `admin_public_keys` 经Terraform专属inventory传入两个角色，持续替换既有管理员账户的完整公钥集合；更换后旧公钥失效，不新增管理员用户。设备及host公钥在修改前解析真实Ed25519 wire格式；首次boundary校验不要求尚未生成的VM host keys。网关只从私钥导出公钥供 workspace 授权；密钥文件每设备独立、账户只读，父目录及 dispatcher 为 root 管理。

CPU约定：员工VM、网关和干净模板均显式设置`cpu.type = "host"`，保持本仓库通用VM模块的既有默认。变更运行VM的CPU型号会触发重新启动，须安排验收或工作中断窗口；检查配置与实际运行CPU均已生效，不能只看Terraform源码。

6. 在 `employee_workspaces` 组配置经核实的官方 native Claude 二进制 URL 和 SHA-256：`employee_workspace_claude_binary_url`、`employee_workspace_claude_sha256`。这是部署输入，不使用漂移的 installer 管道。公司提供 `/usr/local/bin/claude`，员工可自行管理工具和依赖。基础包包含git/curl/sudo/SSH/Python/tmux/unzip，以及用于VM内授权的Firefox及日常图形查看组件；其他项目工具仍由员工管理。浏览器安装由employee-workspace角色维护，新建员工VM随部署自动配置，可用employee_browser标签仅更新该项。
7. 获准运行 `deploy-employee-workspace.yml`。先配置 PVE 二层边界，再启动网关防火墙、固定接口、WireGuard 和专属 SSH，最后部署 workspace 账户/工具/公司第二段公钥。管理机器需对员工子网有经网关的明确路由；不能用员工入口承载任意 Ansible 命令。新工作环境尚未验收前，不把设备配置交付员工。网关 sysctl 默认关闭路由；专属 firewall controller 每次先关闭转发，以单个 nft 事务重建本任务表，成功记录实际内核策略后才打开转发。启动或重载失败保持关闭；PVE 使用无路由模式，不修改宿主 routing。正常部署重载防火墙，避免重启停止依赖它的 SSH 服务。`--tags verify` 比较当前内核表、应用时记录和配置摘要，缺失或漂移即失败；这不替代 CAP 实测。必要的 related ICMP 错误按连接状态放行，支持公网 PMTU，新建受保护目标连接仍拒绝。WireGuard 地址改变时更新实际接口地址，只有 peers 改变时保留地址。部署和停用均执行共享同步任务，即使配置文件未变化也重试实际状态协调。员工 firewall 在标准 nftables.service 之后加载，保留标准服务和PVE既有规则；这里只检查启动顺序配置，不宣称Sandbox实际boot已测。
8. 员工 WireGuard 客户端 `AllowedIPs` 仅设置网关 WireGuard 地址 `/32`，Endpoint 指向获准的家庭入口 UDP 51820；不开放个人 VM 公网端口。示例连接为 `ssh ed-alice-laptop@10.230.0.1`、`sftp ed-alice-laptop@10.230.0.1`，客户端先核实网关 host key。转为正式入口前按实际中国工作网络验证。

家庭 WAN 动态变化时，应先更新并验证所有回流目标；旧地址列表不构成持续防回流保证。公网服务的其他入口、代理地址和任何上游 DNAT 路径也必须列入受保护目标，未知项不能验收通过。IPv6当前全部阻断；若以后启用须单独扩展设计和验收。


## 员工接入包

用户已选择管理员预配每设备接入包。员工不再手工生成或提交SSH/WireGuard公钥；管理员为每台设备分别准备公司SSH、WireGuard身份并登记公钥，接入包包含本设备私钥、固定配置、预核验入口known_hosts及连接脚本。包视为凭据，通过用户指定的私密渠道交付，不进入Git或普通日志。个人Claude凭据不在包内。

设备客户端私钥分别存于 BWS 中的 `vault_employee_access_client_private_keys` 与 `vault_employee_access_client_wireguard_private_keys`；它们不同于网关到 VM 第二段使用的 `vault_employee_access_private_keys`。保留每设备单独撤销能力。

- [Windows员工指引](employee-claude-windows.md)
- [macOS员工指引](employee-claude-macos.md)
- [Linux员工指引](employee-claude-linux.md)

## 撤设备与停员工

撤设备先在 Ansible 权威 roster 设置 `enabled: false`，再运行：

```bash
ansible-playbook playbooks/disable-employee-workspace.yml \
  -e employee_disable_kind=device -e employee_disable_id=ed-alice-laptop
```

角色清空设备入口公钥、终止该设备 UID 的进程（含内层 SSH）、删除系统私钥和映射，随后同步 WireGuard peers。其他设备保持。正常 deploy 同样会处理删除的设备和修改后的映射；仍建议保留禁用设备记录便于核对。下一次 workspace deploy 会去掉客机中的对应公司第二段公钥；立即撤销依靠入口私钥/身份撤销及外部接入规则，不要求信任员工可修改的客机。设备级撤销不终止员工自建第三方连接。

停员工先在 Terraform roster 设置 `disabled: true`，并让执行停用的 inventory 反映相同 networks JSON（例如在当前获准部署的 host_vars 以同结构明确覆盖；不能仅编辑 tfvars 后继续读取旧 state）。再运行：

```bash
ansible-playbook playbooks/disable-employee-workspace.yml \
  -e employee_disable_kind=employee -e employee_disable_id=alice
```

先加载并每次重载禁用员工的网关 drop 规则，再应用 PVE bridge 拒绝，切断既有连接，再从入口撤销全部登记设备并在 PVE 执行 `qm set --onboot 0` 和 `qm stop`；不依赖客户机配合，不执行 destroy/unlink/purge。即使 qm 命令失败，外部网络拒绝仍保留。Verify 检查公司设备无剩余进程、VM stopped、磁盘仍配置且禁止自动启动。之后经授权 Terraform apply 将 NIC disconnected、started=false 和 on_boot=false 状态与权威配置对齐。中途失败时保持已经生效的撤销，重跑相同操作；不得通过重新启用访问解决失败。重新启用必须重新获得员工上线授权并重验。

保留盘视为可能含有效令牌及浏览器会话的敏感资产。使用 PVE 存储权限限制管理员访问，按 Q-6 记录谁可读、备份副本、保留期限及交付许可；不自动挂载、清除、转交或复用。停止 VM 不等于撤销外部 OAuth 令牌，残留客机密钥文件也不意味着外部入口仍有效。

## OAuth 与旧入口

先确定 Q-6 个人凭据、浏览器会话以及快照/备份副本许可、访问和留存。员工本人必须在澳洲 VM 内实际完成浏览器登录/同意，并核对实际 Claude 账号、本人订阅、认证来源和正常请求出口。2026-10-22 用户已批准图形授权例外：所有员工 VM 通过 workspace-browser 独立启动原生 Firefox、Xvfb、Openbox、loopback x11vnc 和 websockify；workspace-login 自动启动或复用这个浏览器。仅通过现有 WireGuard 私网网关 http://10.230.0.1:8443/vnc.html 查看，网关按登记设备固定映射目标；不允许任意目标或公网/LAN VNC。本人邮件、SSO、二次验证与真实任务仍需实际验收。

排查 API key/环境变量是否抢占本人订阅时只报告存在性及认证来源，不输出秘密。更换/到期后重新登录同样按流程验收；不实现防 sudo 替换令牌的机制。Git、Terraform 输入/state、Cloud-Init、模板、日志、命令历史、其他 VM、排错材料均检查泄漏；只报告是否存在秘密。

所有员工 VM（含后续新建）由 employee-workspace 角色统一安装 Firefox 和图形授权助手，模板中不预置浏览器配置或登录态。Browsh 的真实输入失败，不再用作个人授权入口。运行 workspace-login 后在本机浏览器打开助手显示的私网画面地址；本机仅传递远端画面和输入，真实 OAuth 在澳洲 VM 内进行。助手以私有 tmux 保留官方 CLI 终端，成功后核对实际订阅认证来源；取消、完成、终端断线或 30 分钟上限只结束本次 Claude 授权，日常浏览器继续保留；显式 workspace-browser stop 才关闭图形进程及 6081/5901 监听，个人专用 Firefox profile 留在 VM。

正式上线前核对旧试用 VM、Cloudflare Access 应用/路由、连接器位置和存续状态。逐项退役或纳入当前受管入口、隔离和出口要求；共享连接器不得整机停用。旧入口未知时不能用新入口通过替代处置。

## 验证与证据

`tests/employee-workspace/test-offline.py` 测试固定映射、未知命令和注入拒绝、SFTP分派、输入一致性、规则渲染、撤销和停用保盘调用。它只验证程序/模板契约，不模拟真实内核或 SSH 握手。`render-fixtures.py <临时目录>` 生成非秘密配置供隔离 Sandbox 执行 `nft --check` 和 `sshd -T`。检查环境须已有对应工具；脚本不安装依赖。

```bash
python3 tests/employee-workspace/test-offline.py
python3 tests/employee-workspace/render-fixtures.py /tmp/employee-workspace-check
# Sandbox only, with installed providers and no cloud/backend credentials:
terraform fmt -check terraform/proxmox/employee-access.tf terraform/proxmox/employee-workspace.tf
# Run syntax checks using a fixture inventory outside production inventory ancestry:
ANSIBLE_CONFIG=tests/ci/fixtures/ansible.cfg \
ANSIBLE_ROLES_PATH=ansible/roles \
ansible-playbook -i tests/employee-workspace/inventory.yml \
  ansible/playbooks/deploy-employee-workspace.yml --syntax-check
```

Terraform无后端校验在独立临时目录通过测试准备脚本只复制员工专属资源、hook模板和匹配 provider 版本声明；不读取生产 `.tfvars`、state、Vault 或后台凭据，不运行根配置 init 后触发 HCP。缺 provider 缓存则先获得下载/安装授权。完整检查命令及实测清单见 [测试说明](../../tests/employee-workspace/README.md)。

现场验收必须分别保存允许和拒绝的证据，拒绝项用明确管理侧正向对照或规则计数证明，不能以目标停机充当隔离。至少覆盖：本人终端/SFTP/sudo；未知/撤销设备；任意入口命令与各类转发；客机改 sshd 后重试；直连VM；他人VM/设备；伪装IP/MAC/ARP/VLAN/IPv6；家庭/PVE/Tailscale/CN Proxy/网关管理面；家庭公网回流；正常公网依赖/Claude；撤设备杀原会话且保留另一设备；停员工切断预存外连且保盘；既有WAN/DNS/DHCP/qnetd/个人代理/维护。单节点不宣称跨节点通过。CAP-2/4/5真实账号和工作任务均留到现场，不伪造离线结果。

## 当前契约与历史差异

本轮明确员工拥有 sudo，工具和依赖由员工自主；受管入口禁止内置 SSH 转发，正常公网开发允许，VM 外拒绝受保护目标；OAuth 按VM内真实流程验收。早期“不承诺root”、全面应用层中继杜绝和防sudo替换令牌推定已退役。现行 SPEC/access/verification 已同步这些决定，历史 sources 保留历史语义，不据其恢复旧约束。


单命令助手由employee-workspace角色的tasks/login.yml维护，可用workspace_login标签仅更新。助手不调用setup-token，不向管理员交付个人令牌；认证只由本人完成，已有其他认证来源时停止而不覆盖。临时tmux使用独立私有socket、零滚动历史和仅含流程状态的临时文件，退出只结束自身会话。CLI的BROWSER打开请求已用空白临时配置实测，当前原生2.1.304使用claude.com/cai/oauth/authorize；助手校验已知官方授权主机/路径，拒绝其他目标。真实本人OAuth仍为现场验收，不以模拟测试替代。

### 日常浏览器与授权入口的部署及撤销

首次完整部署已包含此入口。单独更新使用 `ansible-playbook playbooks/deploy-employee-auth.yml`（在 Sandbox 内，指定已审批 inventory）；该 playbook 的 Deploy 与 Verify 分开。组件来源为 Ubuntu 已配置仓库及既有 Mozilla 原生 Firefox。网关 nginx 使用独立 systemd 服务和独立配置，不启动默认 80/443 网站，只监听 WireGuard 地址 8443；画面 HTTP/WebSocket 位于现有加密 WireGuard 隧道内。拒绝错误 Host、异源 WebSocket、未知设备和自选后端参数，关闭访问日志。

VM 以 employee 身份运行，X11 不监听 TCP，VNC 仅 loopback 5901；后端 HTTP/WebSocket 仅在该 VM 内部地址 6081，网关只增加该端口的窄向出站及已建立回包。设备不能直接路由到 VM。员工 sudo 能修改自己 VM，VM 外隔离与网关固定映射继续有效。

设备／员工撤销时，受管停用流程先更新 viewer 映射并重启独立 viewer 服务，终止其既有 WebSocket，再撤销 WG／SSH；员工停用另从 VM 外断网停机、保盘。映射变更会使当前所有授权画面短暂断开，SSH 不受该 viewer 重启影响。维护时不读取个人 browser profile，不截图或记录个人授权画面；只用空配置公开页面验证 UI。

### 2026-10-22：独立日常浏览器

用户在图形授权上线后明确同意扩展为日常 VM 浏览器。新增 `workspace-browser start/status/open/stop`；`employee-browser.service` 以 employee 身份在独立 D-Bus 会话中管理原有 Firefox/profile 和显示组件，生命周期独立于 SSH 与 Claude 授权。重复 start 返回同一实例；open 在同一实例新标签打开网页；查看网页关闭／断线后重开现有私网地址可继续。浏览器无固定 30 分钟运行上限，网关空闲 WebSocket 断开后可重连。

默认不启用开机自启动、不由部署任务主动启动或重启个人会话。VM 重启后员工自行 start；标签恢复由 Firefox 设置决定。原授权期间启动的旧临时浏览器仍须先完成或取消旧流程，再迁移到独立服务；部署不强杀个人浏览器。安装服务加载 unit，但不重启仍在使用的个人会话。

公司不额外安装 IDE 或用户项目工具；本次复用已有 WireGuard 端口、固定映射及撤销策略，无网关配置或路由器变化。员工可在 VM 浏览器内访问 VM 自身开发网页，下载保存在 VM，沿用 SFTP 取回。个人 OAuth 和真实任务的验收继续由本人完成。

## Mosh 终端试点

Mosh 复用既有员工网关及设备到本人 VM 的固定 SSH 绑定。`employee_access_mosh_devices` 为设备保留不重叠的 UDP 范围；在任何部署变更之前统一检查账号引用、整数端口、边界和范围冲突。停用设备可以保留其配置和范围，实际规则与策略只发布到启用的设备及工作区。防火墙只允许该设备 WireGuard 地址访问自己的范围，dispatcher 只接受受限启动格式，不执行任意远端命令。默认空映射不安装或验证 Mosh 二进制，SSH/SFTP 继续可用。

紧急停用不应被悬空或坏 Mosh 条目阻断：该入口继续严格核对基础网络，渲染时跳过不存在的设备和非法 Mosh 范围，先封禁目标员工流量。普通 deploy 与 Mosh 专项 deploy 遇到这些错误则必须在改动网关之前失败。

`deploy-employee-mosh-pilot.yml` 的 Deploy 先安装与源码匹配的完整防火墙控制器，再配置策略；Verify 先检查远端控制器 SHA256 与本工作区一致，无论是否存在旧中继配置，都执行 `employee-firewall.py verify --routing`。该检查覆盖策略哈希、内核 filter/NAT 表和路由状态，不能降级成几条规则的文本匹配。仅传 `--tags verify` 会验证已部署状态，不替代控制器升级。

变更端口范围或回收 Mosh 权限时，仅终止该受管设备账号的 `mosh-server`，不为 Mosh-only 变更执行全账号 `pkill`。工作区/设备的完整撤销仍沿用原有 SSH/WG 撤销路径。默认网络断联回收时间为 604800 秒（7 天），可用 `employee_access_mosh_network_timeout` 调整为 60 秒至 30 天；它不是用户未敲键盘的空闲超时。旧三字段策略兼容此默认值；新增超时字段的首次迁移可能终止该设备的旧 Mosh 会话，须安排部署窗口。首次从未连接的会话仍遵循 Mosh 自身的 60 秒等待规则。参考 [Mosh 服务端手册](https://github.com/mobile-shell/mosh/blob/master/man/mosh-server.1)。

### 中继保留与后续 GA 复用

当前 Mosh 试用路径是员工设备经既有 WireGuard 接入家中网关，再进入本人 VM。现有中继相关 roles、Terraform、测试和测量记录应保留在原任务中，后续 GA 可以复用其隧道、路由与边界逻辑；Mosh 的源码整理不导入 Hub-and-Spoke、香港入口或 HAPI 的专属实现。

共用网关有中继规则时仍须完整核验。控制器只识别已批准的 `employee-oci-home-ssh`、`employee-oci-home-browser` 精确规则，并要求它们位于基础 `ct state invalid drop` 之后；不允许靠“发现配置文件”跳过检查。中继任务负责其写入规则的内容、位置与 reload 契约；本轮不重排或删除其实现。旧部署若把放行规则插在 invalid 拒绝之前，新核验会报错，须由中继任务对齐后再上线。

未来接 GA 时，须按入口承载方式确认 WireGuard/Mosh 的 UDP 路径和 SSH 握手，而不能把现有 TCP SSH 中继视为已经支持完整 Mosh。用相同设备、VM 和方法对照直连与 GA/中继的 SSH 命令往返、传输和真人终端体验，覆盖不同运营商与高峰时段；历史线路收益不替代新路径验收。

### 部署前接口确认

本分支为已登记、已绑定 hook 的 VM 补录 `hook_bound=true`，历史退役记录则保持 false；上线前仍须通过 PVE 实际配置逐台核对。私有开户流程位置调整另行处理，本轮未复制或修改该源码；部署本分支前，必须由该任务确认新建候选默认 false、绑定与边界验证后再分别写入 hook 确认和启动就绪。历史退役标记的首次登记也须在专属计划中核对。

员工客户端安装和体验步骤以公开 `workspace-onboarding` 的 README、AGENTS 和 `docs/mosh.md` 为准；管理员交付材料留在私有工程。中国侧实际体验仍待验收，不把服务端握手或本地体验写成中国网络验收通过。
