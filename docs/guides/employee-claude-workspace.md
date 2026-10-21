# 员工 Claude Code 工作环境：实施与验收

本实现对应 [SPEC](../../_bmad-output/specs/spec-employee-claude-workspace/SPEC.md)、[访问契约](../../_bmad-output/specs/spec-employee-claude-workspace/access-and-isolation.md) 和 [验收矩阵](../../_bmad-output/specs/spec-employee-claude-workspace/verification.md)。代码生成、离线测试不代表部署或 CAP 验收通过。当前采用单节点、每人一个持久 VM、外置受管 SSH 入口；WireGuard 是待实测的自建接入候选。

## 网络与身份

每位员工拥有一个无物理端口、无 PVE 主机地址的内部 bridge，桥内只有本人 VM 单 NIC 和网关的专属 NIC。每台员工 VM 的 PVE pre-start hook 会启动并核验本人 bridge 的外部边界；边界不存在或员工禁用则拒绝该 VM 启动，不修改全局 `pve-guests.service`，不阻断无关 VM 自启。PVE 的 `bridge employee_boundary` 表按每人桥上的 guest/gateway tap、源 MAC/IP 限制二层帧，只允许 IPv4 和面向本网关的 ARP；阻断访问 PVE 本机、VLAN、IPv6及其他端口。网关 `inet employee_access` 按入接口限制 IPv4，禁止设备转发、VM 互访、私网、Tailscale、明确受保护地址和家庭公网回流。公网开发流量经网关 NAT 和澳洲 WAN 出站。所有 DNS 都使用明确的公网解析器，无内部 DNS 例外。两层都只更新各自专属 nft 表，不清空全局规则。

网关通过 MAC 匹配稳定接口名；每位员工登记永久 `nic_slot`，从 1 连续分配，新员工追加下一个槽位，不按姓名排序。Terraform 保存创建时槽位、节点、bridge、地址、gateway、MAC及DNS，并拒绝不支持的原位网络变更；磁盘容量仅接受正整数GiB的 `G` 格式（例如 `50G`），不能用 `1T` 或省略单位；网关 NIC、emp 接口和 PVE tap 都按槽位生成。停用员工保留 roster 和槽位。增员后核对新增 NIC/tap 和规则，完成实测后开放设备授权。任何员工 VM 迁移到另一 PVE 节点都超出当前单节点设计，不能直接 live migrate 后宣称隔离仍成立。

员工设备只进入 WireGuard，再访问网关 WireGuard 地址的专属 sshd。每台设备一个 `ed-*` 系统账户、一把设备 SSH 公钥、一个 WireGuard 公钥和唯一地址；私钥留在设备。入口 `ForceCommand` 根据服务端文件选择固定本人 VM，内层 SSH 使用独立系统密钥和预核验 host key。只接受空命令（交互终端）或精确的 `employee-sftp` 子系统命令；普通 `ssh host command`、旧版 SCP、rsync 等任意命令模式拒绝。现代 SFTP 客户端请求 `sftp` 子系统时，入口 sshd 将它映射为 `employee-sftp`，内层请求客机 `sftp`。公司入口不提供自由 shell/sudo，不接收用户环境，禁 SSH 内置转发、隧道、escape、代理和连接复用。

员工仍有 VM 内完整 sudo。修改客机 sshd 不改变入口映射或 VM 外规则。允许正常公网开发连接意味着员工可能建立第三方应用层中继；本实现不宣称识别全部中继或阻止 sudo 替换凭据。

管理员 sshd 只绑定网关 uplink 地址，防火墙只允许显式维护源访问固定 uplink IP；该管理规则在员工接口与 WireGuard 拒绝规则之后，且不依赖 uplink 的旧/新接口名，因此首次 netplan 重命名前后新建管理 SSH 均可用；网关关闭 Ubuntu SSH socket activation，避免 wildcard socket 占用专属入口。维护源可经已批准静态路由通过网关访问个人 VM 的 SSH。不得给员工维护来源地址或管理员密钥。不得把一般员工 VPN 网段登记为维护来源。

## 部署输入与顺序

本次交付实现及独立 Sandbox 验证。真正安装、部署、写凭据或变更网络前仍须另行授权。

1. 核实 Q-4／Q-5：PVE 节点和 provider 指向同一集群；VMID、bridge、子网、MAC 无冲突；现有 PVE nft/防火墙规则与新表共同生效；所有家庭公网 IP、受保护服务及 NAT 回流路径已列出；明确维护源和恢复管理路径。bridge provider 会应用节点待生效网络配置，先处理其他 pending 网络更改，不能直接套用示例地址。当前资源使用默认 PVE provider；独立 pve2 必须先明确 provider 绑定再部署，不能仅填写 node=pve2。
2. 使用干净、无员工令牌/浏览器状态/设备私钥的 Ubuntu cloud-init 模板，核实 SSH host keys 每次克隆独立生成。网关模板不得预启用路由、额外 NIC、代理服务或 cloudflared。确认既有备份作业是否自动纳入新 VMID，Q-6 未确定前不配置个人凭据。
3. 填写 `terraform/proxmox/employee-access.tf` 和 `employee-workspace.tf` 的输入。默认 `employee_access=null`、`employee_workspaces={}`，不会创建任何员工资源；不改旧服务输入。下面只说明数据形状，地址和 VMID 必须现场分配：

```hcl
employee_access = {
  node               = "pve0"
  pve_inventory_host = "pve0"
  vmid               = 500
  template_id        = 9000
  storage_pool       = "local-zfs"
  uplink_bridge      = "vmbr1"
  uplink_address     = "192.168.50.2/24"
  uplink_gateway     = "192.168.50.1"
  uplink_mac         = "02:00:00:00:00:01"
  dns_server         = "1.1.1.1"
  admin_public_keys  = ["ssh-ed25519 REPLACE_WITH_ADMIN_PUBLIC_KEY"]
  boundary_ready     = false # Set true only after the boundary-only Ansible step.
  snippet_datastore  = "local" # Must already support snippets.
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

4. 首次保持 `boundary_ready=false`，经获准 Terraform plan/apply 创建网关及停机的员工 VM，并绑定可执行 pre-start hook。用专属 inventory 执行 `deploy-employee-workspace.yml --tags boundary`，只在 PVE 部署边界；随后设置 `boundary_ready=true` 并再次经获准 apply 启动员工 VM。任何后续启动均由本 VM hook 检查本人 guest/gateway tap 的 input/forward/output 拒绝规则及 base chain 的 family/type/hook/priority；缺失或服务失败只拒绝该 VM。snippet datastore 必须事先支持 snippets，不能自动修改既有 storage 配置。审阅 plan 中磁盘/NIC/bridge 变更，不能允许 replacement/destroy 个人 VM。员工使用专属 VM resource，自身具有 `prevent_destroy`；删除、VMID 改动或显式 replacement 计划会失败，新桥和网关也受保护。不得通过移除整个资源声明或生命周期保护绕过保盘要求。员工停用使用 `disabled=true`，不删除 map 条目；无论 boundary_ready 如何，员工 NIC 断开、started=false 及 on_boot=false 会保留磁盘，并使后续 Terraform apply 继续保持停机。
5. 通过管理通道独立核实每台 VM 的 Ed25519 host key，填入网关 `employee_access_host_keys`，不能使用未经比对的 `ssh-keyscan` 自动信任。改变 host key 后旧连接会失败，先调查原因再按管理流程更新。填写 Ansible `host_vars/employee-access.yml`，设备和节点信息来自专属 Terraform inventory；PVE 节点须已有可用管理 inventory：

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

系统第二段 SSH 私钥采用 Vault 中的 `vault_employee_access_private_keys` 字典（按设备账户索引），网关 WireGuard 私钥采用 `vault_employee_access_wireguard_private_key`；角色 defaults 只作间接引用，部署任务 `no_log`。修改受管主机前，控制端以已有 Ansible Python/cryptography 和 ssh-keygen 检查必需私钥可解析且唯一；缺失或损坏时先失败，不更改账户或边界。管理员按既有 Vault 流程配置系统密钥，不将秘密放在 Terraform、Cloud-Init、示例、命令行或 Git 明文中。员工 OAuth 凭据不放在此 Vault。已有 `admin_public_keys` 经Terraform专属inventory传入两个角色，持续替换既有管理员账户的完整公钥集合；更换后旧公钥失效，不新增管理员用户。设备及host公钥在修改前解析真实Ed25519 wire格式；首次boundary校验不要求尚未生成的VM host keys。网关只从私钥导出公钥供 workspace 授权；密钥文件每设备独立、账户只读，父目录及 dispatcher 为 root 管理。

6. 在 `employee_workspaces` 组配置经核实的官方 native Claude 二进制 URL 和 SHA-256：`employee_workspace_claude_binary_url`、`employee_workspace_claude_sha256`。这是部署输入，不使用漂移的 installer 管道。公司提供 `/usr/local/bin/claude`，员工可自行管理工具和依赖。基础包包含 git/curl/sudo/SSH/Python/tmux/unzip；不自动安装未经验证的 OAuth 浏览器。
7. 获准运行 `deploy-employee-workspace.yml`。先配置 PVE 二层边界，再启动网关防火墙、固定接口、WireGuard 和专属 SSH，最后部署 workspace 账户/工具/公司第二段公钥。管理机器需对员工子网有经网关的明确路由；不能用员工入口承载任意 Ansible 命令。新工作环境尚未验收前，不把设备配置交付员工。网关 sysctl 默认关闭路由；专属 firewall controller 每次先关闭转发，以单个 nft 事务重建本任务表，成功记录实际内核策略后才打开转发。启动或重载失败保持关闭；PVE 使用无路由模式，不修改宿主 routing。正常部署重载防火墙，避免重启停止依赖它的 SSH 服务。`--tags verify` 比较当前内核表、应用时记录和配置摘要，缺失或漂移即失败；这不替代 CAP 实测。必要的 related ICMP 错误按连接状态放行，支持公网 PMTU，新建受保护目标连接仍拒绝。WireGuard 地址改变时更新实际接口地址，只有 peers 改变时保留地址。部署和停用均执行共享同步任务，即使配置文件未变化也重试实际状态协调。员工 firewall 在标准 nftables.service 之后加载，保留标准服务和PVE既有规则；这里只检查启动顺序配置，不宣称Sandbox实际boot已测。
8. 员工 WireGuard 客户端 `AllowedIPs` 仅设置网关 WireGuard 地址 `/32`，Endpoint 指向获准的家庭入口 UDP 51820；不开放个人 VM 公网端口。示例连接为 `ssh ed-alice-laptop@10.230.0.1`、`sftp ed-alice-laptop@10.230.0.1`，客户端先核实网关 host key。转为正式入口前按实际中国工作网络验证。

家庭 WAN 动态变化时，应先更新并验证所有回流目标；旧地址列表不构成持续防回流保证。公网服务的其他入口、代理地址和任何上游 DNAT 路径也必须列入受保护目标，未知项不能验收通过。IPv6当前全部阻断；若以后启用须单独扩展设计和验收。

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

先确定 Q-6 个人凭据、浏览器会话以及快照/备份副本许可、访问和留存。员工本人必须在澳洲 VM 内实际完成浏览器登录/同意，并核对实际 Claude 账号、本人订阅、认证来源和正常请求出口。可先试验 Browsh + headless Firefox 作为纯终端候选；未证实兼容之前不得宣称授权可用。邮件/SSO/二次验证/回调均纳入实测。如果必须图形入口，交用户决定范围变更；不得转成员工本地浏览器打开 URL 或私自开放 VNC/RDP。

排查 API key/环境变量是否抢占本人订阅时只报告存在性及认证来源，不输出秘密。更换/到期后重新登录同样按流程验收；不实现防 sudo 替换令牌的机制。Git、Terraform 输入/state、Cloud-Init、模板、日志、命令历史、其他 VM、排错材料均检查泄漏；只报告是否存在秘密。

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
