# 员工环境验证

使用已有 Python3 + Jinja2 + PyYAML 执行 `python3 tests/employee-workspace/test-offline.py`。测试采用独立 alice/bob 夹具，不读实际 inventory/Vault/state，不安装依赖。`fixture.json` 的地址、公钥均为测试值，不可部署。

这些是离线程序和模板测试，不是 SSH/内核网络验证。渲染输出可用于获准 Sandbox 的以下检查：

```bash
python3 tests/employee-workspace/render-fixtures.py /tmp/employee-workspace-check
sudo nft --check --file /tmp/employee-workspace-check/nftables.conf
sudo nft --check --file /tmp/employee-workspace-check/pve-nftables.conf
sudo sshd -T -f /tmp/employee-workspace-check/sshd-config
```

`sshd -T` 需要已有 host key 和 `/run/sshd`；只在隔离测试环境提供测试密钥。nft检查需要合适的内核/capability，失败须保留真实结果，不能标通过。不要在宿主装工具、修改宿主防火墙或访问现网。

Sandbox 的 Ansible syntax/lint 必须指定 `tests/ci/fixtures/ansible.cfg`、`tests/employee-workspace/inventory.yml` 和 `ANSIBLE_ROLES_PATH`，分别检查 deploy/disable playbook。这个 inventory 位于生产 inventory 目录之外，因此不会自动继承生产 Vault。Terraform 只复制本次两个 root 文件和启动 hook到临时目录，使用 bpg/proxmox=0.70.0、ansible/ansible~>1.3.0 的独立 provider 声明；`init -backend=false` 使用已有安装缓存，不连接 HCP。空变量 plan 只允许在 mock provider 或无生产凭据的隔离环境执行，不能把根目录所有既有服务纳入新资源测试。

`test-network.py --run-isolated-netns` 可在获准 Linux Sandbox 内以 root 执行。它创建带随机前缀、与真实网络断开的 PVE bridge/网关/员工/设备/模拟公网 namespaces，加载真实渲染规则，以真实 TCP 服务的正向对照检查互访、维护路径、公网回流、MAC伪装、设备直连和停用后的拒绝。结束时仅删除本次创建的 namespaces 和测试进程，不修改主命名空间防火墙/接口。需要现有 iproute2/nftables/Jinja2/PyYAML；不安装依赖。已覆盖真实 IPv6 TCP、源IP/MAC伪装、VLAN帧的正反对照、PVE主机input/output、网卡重命名前后维护连接及已建立外连的停用。该实验不覆盖真实 WireGuard 握手，也不取代现场 CAP 验收。

## 获准环境的独立预期矩阵

| 实验 | 正向对照 | 拒绝预期/停用预期 |
|---|---|---|
| alice laptop / spare / bob 两段SSH | 各自本人VM，sudo和真实命令成功 | 请求其他目标、任意入口命令、未知账户均失败 |
| SFTP | 以各自身份写入本人测试目录，另一设备读回 | 入口 shell/legacy SCP/rsync 不能执行；bob不能读alice文件 |
| SSH builtin forwarding | 本人终端持续可用 | `-L/-R/-D/-W/-w`、StreamLocal、agent/X11拒绝；改客机sshd后仍拒绝 |
| host key | 正确预核验 key 可连 | 改VM key后入口失败，不接受新key；缺映射也失败 |
| VM网络 | 公网TCP和明确公网DNS正常 | 他人VM/设备/私网/受保护公网/家庭公网回流均拒绝 |
| 二层与来源 | 固定MAC/IP经独占bridge可达公网 | 改IP/MAC、ARP伪装、VLAN、IPv6与访问PVE bridge主机均不增加权限 |
| 管理维护 | 明确维护源可连网关及VM SSH | WireGuard设备和员工VM不能访问管理面；网关本机代理/DNS拒绝 |
| 撤alice laptop | alice spare、bob保持现有SSH/SFTP | laptop已有SSH/SFTP及WG失效，新连接拒绝 |
| 停alice | bob业务和管理正常 | alice已存公网测试TCP断开、所有入口失效；PVE stopped/onboot=0，scsi0配置及磁盘仍保留 |
| 既有业务 | 变更前WAN/DNS/DHCP/qnetd/代理/管理均可用 | 变更后上述正向对照仍可用 |

真实测试还须核对源 [verification.md](https://github.com/blue126/IaC/blob/751f7b6da8c4bf92cfa62c8fc77f7c61626ce146/_bmad-output/specs/spec-employee-claude-workspace/verification.md) 的CAP-2本人订阅/泄漏、CAP-4 VM内浏览器/澳洲出口、CAP-5真实中国网络/并发及Q-6凭据与保留盘许可。纯离线测试对这些项没有通过结论。

## 可重放的 Terraform 与 SSH 检查

在获准 Sandbox 中执行 `python3 tests/employee-workspace/prepare-terraform.py` 会打印全新的临时 root 路径，只复制本次资源、hook模板及固定版本providers声明。进入该目录，清除相关 provider/HCP 环境凭据并设置 `TF_CLI_CONFIG_FILE=/dev/null`，执行 `terraform init -backend=false -input=false`、`terraform validate` 和 `terraform test -json -verbose > /tmp/startup-tests.jsonl`。最后用 `check-startup-plans.py /tmp/startup-tests.jsonl` 检查实际计划中的状态。`startup.tftest.hcl` 使用mock providers，不连接PVE/HCP；七个场景包括空配置、boundary未就绪、ready、disabled、分配持久槽位、增员稳定性及拒绝槽位重分配。前者零资源，后面三个场景实际started/on_boot分别为false/true/false，disabled的NIC断开。

`sudo /opt/iac-venv/bin/python3 tests/employee-workspace/test-ssh.py --run-isolated-ssh` 使用无外联network namespace和临时Unix设备账户、测试密钥运行真实OpenSSH/SFTP。测试使用生成的入口配置及相同dispatcher逻辑，只替换测试路径/监听端口；StrictModes保持开启。负向用例共用loopback来源，测试daemon单独关闭PerSourcePenalties，避免用例间惩罚限流。临时资料放在root所有的/run目录，结束删除测试账户/密钥/目录，不接触部署密钥。

SSH矩阵覆盖固定交互入口、命令注入/未知身份拒绝、SFTP往返、L/R/D/W和远端StreamLocal转发拒绝（客机允许转发）、host key变化、映射缺失、已有SSH/SFTP撤销、另一设备会话及重连保留。它不证明实际WireGuard握手、PVE API hook执行、X11/agent/tun全部通道或真实员工OAuth；这些范围须另作现场证据，不能据隔离测试宣称全部CAP完成。

## 2026-10-21 独立 Sandbox 证据

`iac-employee-claude-verify-direct-v130` 中已执行：20项离线测试、4个Terraform mock场景及实际计划状态断言、26项真实SSH/SFTP检查、35项真实网络检查，均退出0。两个playbook syntax通过；全部新增角色及playbook的ansible-lint覆盖25个文件，0failure/0warning；nft两份配置和sshd有效配置检查通过。Terraform验证只使用临时无后端副本及mock providers，没有生产连接。

原始日志保留在该Sandbox `/tmp/employee-workspace-verify/`：`offline-final.log`、`employee-claude-terraform-tests.jsonl`、`startup-assertions.jsonl`、`ansible-lint-all-affected.log`、`ssh-final.jsonl`、`network-final-expanded.jsonl` 和 `sshd-effective-final.txt`。首次测试发现的夹具问题及修复过程保留在会话记录；SFTP本地客户端等待stdin的初始超时另留 `ssh-before-idle-client-probe.*`。最终SFTP撤销验证是对原会话再次尝试上传并证明失败且文件未生成，不把客户端UI未退出等同于服务端会话仍有效。

Sandbox没有 `/dev/net/tun`，所以 `ssh -w` 服务端拒绝**未实测**；没有把客户端缺TUN的失败算通过。有效配置明确显示 `permittunnel no`、`disableforwarding yes`，以及TCP/StreamLocal/agent/X11各项为no。真实PVE启动hook执行、WireGuard握手和现场CAP/OAuth仍待获准部署后验证。


## 评审修复后的补充验证

`nic_slot` 是永久登记字段，从 1 连续递增；字母序更早的新员工使用下一个槽位。`terraform test` 的 apply 仅操作 mock provider。`test-disk-protection.py <临时root> <Terraform JSON日志>` 将 mock 状态写入临时 root，以 `-refresh=false` 检查 destroy、强制 replacement 和 VMID 改动；三者都必须因员工 VM 自身 `prevent_destroy` 失败。必须在断网 namespace 及无生产环境凭据下运行，脚本不调用 apply。

SSH 测试执行实际 workspace authorization 任务，跨 play 从 gateway 注册结果生成 Alice/Bob 授权，包含有效、跳过及 Bob 项，并实测 `from=` 限制。撤设备执行真实 `revoke.yml`，仅将文件目的地移入临时目录，检查旧 SSH/SFTP 失效且另一设备保留。

网络测试新增两种 128 KiB/600 MTU 传输：网关本地产生 PMTU 错误、上游私网路由器返回 related ICMP；新建私网访问仍拒绝。执行生产 firewall controller 检查内核表缺失/漂移、未挂接普通链、加载失败关闭转发及 PVE 不改 routing。停员工执行实际 Ansible disable 任务，`qm` 故意返回42后检查旧公网流已断、Bob仍通；常规部署任务重载不变策略，既有连接保留。

Sandbox 没有实际 systemd/PVE：网络夹具以 `systemctl` shim 调用生产 controller 和真实 nft，`qm` 是失败替身，WireGuard peer同步是空操作；任务顺序和 nft/Ansible 模块未替换。不能据此宣称真实 PVE 停机/保盘、systemd依赖传播或 WireGuard 握手已现场通过。

`sudo /opt/iac-venv/bin/python3 tests/employee-workspace/test-runtime.py --run-isolated-runtime` 在断网 namespace 验证私钥缺失/损坏/重复时无秘密输出、实际 Ansible预检失败前 changed=0，以及实际共享 WireGuard 同步任务 的 Address 变更和不变重跑。接口使用测试 veth，peer同步使用 stub，不宣称握手验证。


本轮最终证据仍位于 `iac-employee-claude-verify-direct-v130:/tmp/employee-workspace-verify/`：`offline-round1.log`（20项）、`ssh-round1.jsonl`（34项）、`network-round1.jsonl`（49项）、`runtime-round1.jsonl`（9项）、`tf-round1-tests.jsonl`（7个mock场景）、`startup-round1.jsonl`（3组状态）、`disk-round1.jsonl`（正常计划正向对照及3类破坏性计划拒绝）、`tf-round1-validate.log`、`lint-round1.log`（28文件，0failure/0warning）、`units-round1.log`（两份systemd单元静态解析）。实际停用任务的 `qm` 故意失败输出保存于 `disable-actual-ansible-round1.log`；该失败是验证条件，随后真实网络断言均通过。两个playbook syntax、Terraform格式及Python AST/新增文件空白检查通过。原始此前失败不作为通过证据，最终文件只记录修复后的结果。

所有结果仍限定独立Sandbox代码验证。没有生产部署、真实PVE API停机/保盘与hook启动、WireGuard握手、真实OAuth、现场CAP-5或跨节点通过结论。


## 本轮修复的定向证据与父侧重放

本轮日志仍在同一Sandbox的 `/tmp/employee-workspace-verify/`：`offline-round2.log`（24项）、`runtime-round2.jsonl`（18项）、`ssh-round2.jsonl`（48项）、`network-round2.jsonl`（58项）、`tf-round2-tests.jsonl`（17个mock场景）、`startup-round2.jsonl`（3组状态）、`disk-round2.jsonl`（正常计划与3类拒绝）、`lint-round2.log`（两个修改角色，29文件，0failure/0warning）。故障注入日志为 `disable-pve-failure-round2.log`、`disable-gw-failure-round2.log`、`disable-actual-ansible-round2.log`。SSH/network/runtime的同名 `.stderr` 保存错误输出；最终运行为空。

本轮仅执行修改文件对应的检查。以下完整相关验证命令交父侧执行；创建新的无后端Terraform目录，并复用已验证的本地provider镜像 `/tmp/employee-terraform-z9wtf6a4/proxmox/.terraform/providers`（bpg/proxmox 0.70.0、ansible/ansible 1.3.0，linux_arm64），不下载providers、不读取生产inventory/Vault/state。若该临时镜像已消失，应先核对原有缓存位置，不改成生产root初始化。

```bash
sbx exec iac-employee-claude-verify-direct-v130 bash -lc "$(cat <<'SH'
set -euo pipefail
cd /Users/weierfu/.codex/worktrees/employee-claude-architecture/IaC
export ANSIBLE_CONFIG=tests/ci/fixtures/ansible.cfg
export ANSIBLE_ROLES_PATH=ansible/roles
VERIFY_DIR=/tmp/employee-workspace-verify-final
mkdir -p "$VERIFY_DIR"
python3 tests/employee-workspace/test-offline.py > "$VERIFY_DIR/offline.log" 2>&1
terraform fmt -check terraform/proxmox/employee-access.tf terraform/proxmox/employee-workspace.tf tests/employee-workspace/startup.tftest.hcl
ansible-playbook -i tests/employee-workspace/inventory.yml ansible/playbooks/deploy-employee-workspace.yml --syntax-check > "$VERIFY_DIR/deploy-syntax.log" 2>&1
ansible-playbook -i tests/employee-workspace/inventory.yml ansible/playbooks/disable-employee-workspace.yml --syntax-check > "$VERIFY_DIR/disable-syntax.log" 2>&1
ansible-lint --offline ansible/roles/employee-access ansible/roles/employee-workspace ansible/playbooks/deploy-employee-workspace.yml ansible/playbooks/disable-employee-workspace.yml > "$VERIFY_DIR/lint.log" 2>&1
python3 tests/employee-workspace/render-fixtures.py "$VERIFY_DIR/rendered"
sudo unshare --net nft --check --file "$VERIFY_DIR/rendered/nftables.conf"
sudo unshare --net nft --check --file "$VERIFY_DIR/rendered/pve-nftables.conf"
sudo mkdir -p /run/sshd
sudo sshd -T -f "$VERIFY_DIR/rendered/sshd-config" > "$VERIFY_DIR/sshd-effective.txt"
python3 - <<'PY'
import os, pathlib, subprocess, jinja2
out = pathlib.Path("/tmp/employee-workspace-verify-final")
root = subprocess.check_output(["python3", "tests/employee-workspace/prepare-terraform.py"], text=True).strip()
(out / "terraform-root").write_text(root)
mirror = "/tmp/employee-terraform-z9wtf6a4/proxmox/.terraform/providers"
assert pathlib.Path(mirror).is_dir()
env = {key: value for key, value in os.environ.items() if not key.startswith(("TF_", "TFC_", "PROXMOX_"))}
env["TF_CLI_CONFIG_FILE"] = "/dev/null"
for log, args in [("terraform-init.log", ["init", "-backend=false", "-input=false", "-plugin-dir=" + mirror]), ("terraform-validate.log", ["validate"]), ("terraform-tests.jsonl", ["test", "-json", "-verbose"])]:
    with (out / log).open("w") as stream:
        subprocess.run(["terraform"] + args, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
source = pathlib.Path("ansible/roles/employee-access/templates/firewall.service.j2").read_text()
for name, routing in [("gateway", True), ("pve", False)]:
    (out / (name + "-firewall.service")).write_text(jinja2.Environment(trim_blocks=True).from_string(source).render(employee_firewall_routing=routing))
PY
sudo systemd-analyze verify "$VERIFY_DIR/gateway-firewall.service" "$VERIFY_DIR/pve-firewall.service" > "$VERIFY_DIR/units.log" 2>&1
python3 tests/employee-workspace/check-startup-plans.py "$VERIFY_DIR/terraform-tests.jsonl" > "$VERIFY_DIR/startup.jsonl"
sudo unshare --net /opt/iac-venv/bin/python3 tests/employee-workspace/test-disk-protection.py "$(cat "$VERIFY_DIR/terraform-root")" "$VERIFY_DIR/terraform-tests.jsonl" > "$VERIFY_DIR/disk.jsonl" 2> "$VERIFY_DIR/disk.stderr"
sudo /opt/iac-venv/bin/python3 tests/employee-workspace/test-runtime.py --run-isolated-runtime > "$VERIFY_DIR/runtime.jsonl" 2> "$VERIFY_DIR/runtime.stderr"
sudo /opt/iac-venv/bin/python3 tests/employee-workspace/test-ssh.py --run-isolated-ssh > "$VERIFY_DIR/ssh.jsonl" 2> "$VERIFY_DIR/ssh.stderr"
sudo /opt/iac-venv/bin/python3 tests/employee-workspace/test-network.py --run-isolated-netns > "$VERIFY_DIR/network.jsonl" 2> "$VERIFY_DIR/network.stderr"
SH
)"
```

WireGuard采用共享 `tasks/sync-wireguard.yml`，原同步handler已移除；历史日志和历史数量保留。实际systemd boot、PVE停机/保盘和WireGuard握手仍未现场验证。


## 根代理最终复跑

最终完整相关验证位于 `iac-employee-claude-verify-direct-v130:/tmp/employee-workspace-verify-parent-final/`：离线24、runtime18、SSH/SFTP48、network58、Terraform mock17、3组启动状态、4个磁盘计划正反对照全部通过；全部新增角色和两个playbook的lint覆盖31文件（0failure/0warning），两份syntax、fmt/validate、nft/sshd有效配置及systemd静态检查通过。JSON逐条预期/实际已核对；三个运行实验stderr为空。复跑没有访问生产系统。

Sandbox重启后/run/sshd可能不存在；上面的重放命令已补创建该临时运行目录。该缺目录曾使父侧第一次sshd检查退出255；补齐后继续尚未完成的检查，未重复已有通过项。实际PVE、systemd启动、WireGuard握手、TUN通道及OAuth的验证限制仍如上文。


## 单窗口登录助手回归

在已经安装tmux的获准Linux环境中，以非root用户执行`python3 tests/employee-workspace/test-login.py -v`。测试使用真实PTY和独立tmux服务器、合成Claude/浏览器程序及一次性HOME目录，不联网、不使用真实账号或令牌。覆盖链接自动交付、已有订阅复用、同窗授权码输入、取消及SIGTERM清理、保留其他tmux会话、非法目标、CLI失败和不覆盖其他凭据来源。另行获准的真实连通检查使用空白配置及实际CLI/浏览器，只打开匿名授权页后取消；两类检查都不替代本人OAuth验收。

### 图形授权修复后的验证范围（2026-10-22）

test-login.py 的合成浏览器改为图形 supervisor 替身，仍使用真实 PTY/tmux；9 项覆盖通过。生产组件的匿名验收另外实际验证 WireGuard → 固定映射网关 → WebSocket/RFB 的点击与键盘输入，并在 Firefox DOM 核对未提交的测试文字；验证异源拒绝、已有／新连接撤销、跨员工带正对照隔离，以及完成测试后的后端关闭。真实 native CLI 的空配置启动／取消验证确认无遗留自有进程。这些部署验收不属于离线 PR 验证，须有目标环境授权，详细证据见 employee-workspace-deployment.md；不代表真实个人 OAuth 或中国侧用户验收完成。

### 日常浏览器生命周期追加

日常浏览器获得独立 systemd 生命周期后，test-login.py 的 9 项回归验证授权结束保留浏览器，合成服务进程仅在测试 teardown 清理。已授权 control 部署验收以独立空 HOME 实际运行服务／Firefox／WireGuard，验证重复启动、同实例新标签、真实输入及重连、native Claude 复用与取消保留、显式停止关闭后端、profile 留存和重启共 12 项。详见部署记录的日常浏览器章节；未使用个人账号，不替代本人 OAuth 验收。

## Mosh 及退役审查回归

`test-offline.py` 包含 Mosh 端口范围/重叠/悬空设备预检、停用时的 fail-closed 渲染、断联网路超时的受限传递、扩展规则顺序和存在扩展时的 NAT 漂移拒绝。所有输入为合成数据。

Terraform mock 场景新增默认不启动、只有 start_ready 仍不启动，以及退役标记保留。运行 `terraform test -json -verbose` 后，将其日志传给 `test-disk-protection.py`；该脚本只把 mock 状态写入临时 root，并以 `-refresh=false` 验证已存在 VM 的退役仍受保护、清除退役标记无法意外新建空白 VM。不要对生产 root 或真实 state 使用此脚本。

Mosh 的完整 Verify 不因 OCI/浏览器中继配置存在而降级；真实中继 drop-in 的规则写入顺序和 reload 行为仍由对应任务验证，部署前应确认接口一致。

`python3 tests/employee-workspace/test-mosh-verify.py` 在临时本地 inventory 中执行真实 Verify play，仅替换控制器状态、二进制路径和内核状态读取依赖。它证明中继存在时仍做全量检查、NAT 漂移会失败、旧控制器会失败，以及空/全停用名单不要求 Mosh 二进制；不连接真实网关、不调用 sudo 或读取部署凭据。
