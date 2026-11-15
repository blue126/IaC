# 员工电脑改用用户态 WireGuard 代理：可行性评估

状态：已被 2026-11-15 的锻造结论取代。纯用户态代理不采用，改为“特权守护进程 + TUI”的 remotecc 客户端，见 `_bmad-output/forge-userspace-wireguard-agent/forge-userspace-wireguard-agent.md`。本文保留作为原型实测记录。原状态：调研结论，待用户决定。日期：2026-11-14。依据：workspace-onboarding `main` 的 `057c809`（1.6.0）、IaC `origin/main` 的 `0a53f1e`、主检出下管理代码 `remotecc/wsctl/hub-bundle.py`（只读）、本机原型实测，以及第 9 节列出的外部资料（2026-11-14 查阅）。没有连生产 Hub，没有用真实设备包或员工密钥，没有改 workspace-onboarding。

## 1. 结论：有条件做

**可以做到 bootstrap 里所有和 WireGuard 有关的动作都不需要 sudo 或 UAC。** 做法是自己写一个小 Go 程序（下称“代理”），用 wireguard-go 加 gVisor netstack 在用户态跑 WireGuard，不建网卡、不改路由，只在 `127.0.0.1` 上开端口转发。原型已在本机验证：SSH、SFTP、原版 `mosh <别名>`、TLS pin 核对、无 sudo 换线路、代理重启后 Mosh 会话自动恢复，全部通过。

条件（任何一条不满足就不上线）：

1. **Windows 普通用户实测通过**：代理的 UDP 套接字会触发防火墙弹窗；Windows 11 的 Smart App Control 会拦截未签名程序。两者都要在真实的 Windows 10/11 普通账号上试过，必要时给 exe 做代码签名（见第 7 节风险 1、2）。
2. **VM 端 nginx 放行 `127.0.0.1` 来源的 Host/Origin**：现在 `desktop.conf.j2` 只接受 Host 为 overlay IP，浏览器改走本地端口后会被 403。这是一处 Ansible 模板改动，要对全部员工 VM 下发。
3. **迁移时换发新的设备密钥**：同一把 peer 密钥不能同时在旧隧道和新代理里跑。换新密钥后旧隧道自然失效，迁移本身也不需要 sudo（见第 6 节）。

不需要改的：Hub、配额、ACL、Portal、设备包 manifest 格式、wsctl 生成设备包的代码。

剩下必须提权的只有和 WireGuard 无关的事：Linux 上用 apt 装 mosh，Windows 上在 WSL 里装 mosh。macOS 上 Homebrew 装 mosh 本来就不需要 sudo。

工作量约 15–20 人日（第 6 节）。建议先做第 8 节的阶段 0：两三天的 Windows 实测加 VM nginx 改动，过了再投入正式开发。

另一条已提给用户的思路（setup 时装开机自启，verify 不用 sudo）仍然需要首次 sudo/UAC，而且只解决重启后不会自动恢复的问题。本方案一次解决全部提权，代价是我们要维护一个自己的二进制。两者不冲突；如果条件 1 在 Windows 上过不了，可以只在 macOS/Linux 上用代理，Windows 继续用官方隧道服务，再用那条思路补开机自启。

## 2. 技术选型

| 方案 | 许可证 | 维护状况（2026-11-14） | SSH | 浏览器 8443 | Mosh UDP 段 | 预编译平台 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **自写 Go 代理**（wireguard-go + netstack） | MIT + Apache-2.0（gVisor） | wireguard-go 主分支 2026-10-24 仍有提交 | ✓ | ✓ | ✓ 整段转发 | 自己交叉编译，6 个目标原型均已编出 | **采用** |
| wireproxy（windtf/wireproxy，原 octeep、whyvl） | ISC | v1.1.3（2026-07-16），基本一人维护；UDP 会话竞态的修复 2026-09 才合并，还没发版 | ✓ `STDIOTunnel` / `TCPClientTunnel` | ✓ | 只有单端口 `UDPProxyTunnel`（v1.1.1 起），要转一段端口得写 1001 节配置或在 VM 上固定 mosh 端口 | 无 Windows arm64 | 可作备选和参考实现 |
| onetun（aramperes） | MIT | v0.3.10（2024-12），基本停更 | ✓ | ✓ | UDP 自称“完全实验性”，端口复用时会丢包或串包 | 无 macOS x86_64、无 Windows arm64 | 不采用 |
| Tailscale userspace / tsnet | BSD-3 | 活跃 | — | — | — | — | 必须接 Tailscale 或 Headscale 控制面，不能直接连 WG Portal 管理的 peer，不适用 |
| sing-box WireGuard 出站 | GPL-3.0+ | 活跃 | ✓ | ✓ | ✓ | 全平台 | 功能多出一大截，GPL 对改版再分发有约束，不采用 |

选自写的理由：

- **底层就是 wireproxy 用的同两个库**，自写部分只有配置读取、端口转发、单实例锁、状态接口，原型约 450 行。
- **能直接满足 bootstrap 的需要**：从设备包读配置、`status` 输出握手时间和收发字节（给 verify 用）、`endpoint` 命令在线换线路（给 route 用）、Mosh 整段 UDP 转发。wireproxy 要做到这些得改配置文件再重启，状态也只能从它的 metrics 接口读。
- **wireproxy 当作退路**：如果不想维护自己的代码，可以用 wireproxy 加 VM 端固定 mosh 端口，代价是 verify、route 的体验变差，Windows arm64 也要自己编。

平台和签名：

- **静态二进制**：原型用 `CGO_ENABLED=0 go build -trimpath -ldflags='-s -w'` 编出了 darwin/arm64、darwin/amd64、linux/amd64、linux/arm64、windows/amd64、windows/arm64，每个 6.6–7.3 MB，Linux 版是 statically linked。
- **macOS Gatekeeper**：用 curl 或 git 拿到的文件不带 `com.apple.quarantine`，Gatekeeper 和公证检查不会触发（XProtect 仍会扫描）。Apple Silicon 要求至少有 ad-hoc 签名，Go 链接器会自动加；原型 `codesign -dv` 显示 `flags=0x20002(adhoc,linker-signed)`。不需要 Apple 开发者账号。
- **Windows SmartScreen**：SmartScreen 看的是 Mark-of-the-Web，`git clone` 和 `Invoke-WebRequest` 都不加这个标记，所以通常不弹。真正的风险是 Windows 11 的 Smart App Control（会拦截云端无法判断的未签名程序，不管来源）和 Defender 对 Go 程序的误报（Go 官方 FAQ 承认这很常见）。

## 3. 常驻方式

**单实例。** 代理启动时对状态目录里的锁文件加排他锁（Unix 用 `flock`，Windows 用 `LockFileEx`），拿不到锁就以 `AGENT_ALREADY_RUNNING` 退出。原型实测：第二个进程返回退出码 3。WireGuard 本地端口用随机端口，所以锁是防止重复的唯一手段。原型里还踩到一个坑：锁文件句柄被 Go 垃圾回收关掉后锁就丢了，必须一直持有引用。

**同一台电脑上 Windows 和 WSL 是两套系统，锁管不到对方。** bootstrap 在 WSL 里运行时要检测 `WSL_DISTRO_NAME` 并拒绝安装代理，否则同一把密钥会在两个地方并发。

| 平台 | 自启方式 | 是否要提权 |
| --- | --- | --- |
| macOS | `~/Library/LaunchAgents/<label>.plist`，`launchctl bootstrap gui/$UID` 加载，`KeepAlive=true` | 不需要。macOS 13 起会弹“已添加后台项目”通知，并出现在“登录项”里，员工可以手动关掉；用 MDM 管理的电脑可能限制登录项 |
| Linux | `~/.config/systemd/user/<name>.service`，`systemctl --user enable --now` | 不需要。桌面用户登录时启动；`loginctl enable-linger` 给自己开也不用 root（polkit 默认 `set-self-linger` 为 yes），但员工电脑一般不需要 |
| Windows | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 写一个隐藏窗口的启动命令；或者用当前用户的计划任务，登录时触发 | Run 键和启动文件夹不需要管理员；计划任务不能带最高权限，未实测 |

控制接口用只有本人能访问的 Unix 套接字（权限 `0700`），不开 TCP 控制端口。Windows 10 1803 起支持 AF_UNIX，Go 1.12 起支持。注意 macOS 套接字路径上限是 104 字节，原型第一次就因路径太长失败，正式实现要放在短路径下。

## 4. 三种访问方式

### 4.1 SSH 和 SFTP：改 HostName，不用 ProxyCommand

推荐的 `ssh_config`（原型实测 variant A）：

```text
Host oci-hub-alice alice-vm
    HostName 127.0.0.1
    Port 22022                 # 代理在本机转发到 <gateway>:22
    HostKeyAlias 10.234.0.2    # 仍按设备包里的 known_hosts 核对 VM 主机密钥
    UserKnownHostsFile ".../known_hosts"
    StrictHostKeyChecking yes
    ...（其余选项和现在一样）
```

- 员工继续用 `ssh alice-vm`、`sftp alice-vm`、`mosh alice-vm`，用法不变。
- known_hosts 文件不用改：`HostKeyAlias` 让 ssh 用 `10.234.0.2` 去查主机密钥，host pin 照样生效。

**为什么不用 ProxyCommand：** `ssh -o ProxyCommand='wgagent nc <sock> %h %p'` 原型也测通了（variant B），但它和原版 mosh 不兼容。mosh 包装器默认的 `proxy` 模式会用命令行 `-o ProxyCommand=mosh --fake-proxy -- %h %p` 覆盖配置文件里的 ProxyCommand（本机 mosh 1.4.0 脚本第 407 行），fake-proxy 会直接 TCP 连 `%h`，也就是 `10.234.0.2`，而没有网卡时这个地址连不上。改成 HostName 指向 127.0.0.1 后，fake-proxy 连的是代理的本地端口，并把 `127.0.0.1` 报给 mosh-client，Mosh 就能经代理走通。ProxyCommand 可以留作 ssh 的备用入口，但不能作为主要方案。

### 4.2 Mosh：代理转发整段 UDP 端口，不需要启动器

- 代理在 `127.0.0.1:60000–61000` 上每个端口各开一个 UDP 套接字，转发到 VM 的同号端口。
- mosh-server 照常在 VM 上从 60000 往上挑空闲端口，报给客户端；mosh-client 往 `127.0.0.1:<该端口>` 发包，代理送进隧道。
- **VM 端不用改，mosh 也不用固定端口，员工直接 `mosh alice-vm`。**

原型实测命令（“VM”是本机 sshd 加 mosh-server，只绑 `::1`；客户端只能经 `127.0.0.1` 进隧道才连得上，所以通了就证明走的是隧道）：

```bash
mosh --server=/opt/homebrew/bin/mosh-server --ssh='ssh -F ssh_config' alice-vm -- /bin/sh
# 结果：会话里写入的 WRAPPER_VIA_TUNNEL_42 落盘；lsof 显示 mosh-client → 127.0.0.1:60001，mosh-server 只监听 [::1]:60001
```

`--server` 只是因为测试机上非交互 ssh 的 PATH 里没有 Homebrew；真实 VM 上的 `/usr/bin/mosh-server` 不需要这个参数。

代价和注意：

- **资源**：1001 个套接字。原型在这种配置下 RSS 约 11 MB，打开约 1015 个文件描述符。Go 启动时会把软上限自动抬到硬上限，launchd 默认的 256 不构成问题，正式版仍要在 LaunchAgent 里显式设置 `SoftResourceLimits`。
- **端口冲突**：本机已经有程序占用 `127.0.0.1` 的 60000 段时（比如本机自己跑 mosh-server），代理会启动失败，需要报明确的错误码。真遇到可以改成只转发较小的段，同时在 VM 端用 mosh-server 包装脚本加 `-p 60000:60099` 限定范围。
- **只适用 mosh 的默认 `proxy` 模式。** `--experimental-remote-ip=remote` 会让客户端连 VM 自己的地址，那样走不通。
- **Windows**：
  - MobaXterm 的 Mosh 只要把主机和端口指向 `127.0.0.1:22022`，原理上能用，但没有实测。
  - WSL2 默认是 NAT 网络模式，WSL 里访问不到 Windows 的 `127.0.0.1`，要么改用 mirrored 模式（Windows 11 22H2+），要么让代理额外监听 WSL 虚拟网卡（这又会碰到防火墙）。所以 Windows 上的 Mosh 方案要按第 8 节阶段 0 实测后再定，WSL 方式可能要降级。

### 4.3 VM 浏览器入口

`desktop_url` 改成 `https://127.0.0.1:18443/`，由代理转发到 `<gateway>:8443`。

- **证书 pin 不受影响。** pin 是证书 DER 的 SHA-256，和连接地址无关。原型里 `openssl s_client -connect 127.0.0.1:18443` 拿到的证书指纹与原证书一致（TLS_PIN_OK）。verify 只要把连接地址换掉。
- **浏览器会多一种警告。** 证书 SAN 是 `IP:10.234.0.2`，现在已经因为自签名报“不受信任”，改走本地端口后还会报“名称不匹配”。原型里用该证书作 CA 的严格 curl 验证失败（exit 60），说明确实是两层问题。员工照样点“继续访问”，README 里“证书提示是正常的”这句话仍然成立，但措辞要改，因为错误类型不同了。也可以在 VM 证书里加 `IP:127.0.0.1` 的 SAN，消掉名称不匹配，但证书和 pin 都会变，要换发设备包，收益不大，不建议。
- **VM 端必须改 nginx**（`ansible/roles/oci-hub-spoke/templates/desktop.conf.j2`）。现在第 8–9 行要求 `$host` 等于 overlay IP、`Origin` 等于 `https://<overlay>:8443`，否则 403。要加上 `127.0.0.1` 和 `https://127.0.0.1:18443`，端口在所有设备上固定。Origin 校验仍然保留，用来防跨站 WebSocket 劫持。
- **暴露面基本不变。** 本机任何进程都能连 `127.0.0.1:18443`。但今天的系统隧道下，本机任何进程本来就能连 `10.234.0.2:8443`；浏览器里的网页访问 10.x 和 127.0.0.1 也同样受 Private Network Access 限制。

## 5. 与现有约束的兼容

| 约束 | 结果 | 说明 |
| --- | --- | --- |
| Hub 按 peer 计配额和记账 | 不变 | 同一把设备密钥、同一个 `/32` 源地址，Hub 看到的内层包完全一样；keepalive 仍是 15 秒 |
| 设备停用、超额停用 | 不变 | Portal 停用 peer 后握手失败，代理 `status` 显示握手过期，verify 报对应错误 |
| 跨员工隔离 | 不变 | 由 Hub ACL 和 PVE 负责。代理只允许连设备包里的那个 `/32`（原型 `dialVM` 限制），只是多一层防护，不算边界 |
| VM `authorized_keys` 的 `from=设备 /32` | 不变 | netstack 发出的内层源地址就是设备地址 |
| 换线路 `route` | 改，而且更好 | 不用 sudo，通过控制套接字在线切换（原型 `ENDPOINT` 实测生效）。有一点必须补上：wireguard-go 的配置接口只接受 `IP:端口`（原型实测传域名报 `ParseAddr` 错误），所以加速线路的域名要由代理自己解析，握手失败时还要重新解析，至少做到和 wg-quick 启动时解析一次同等的效果。保存线路的文件和与设备包核对的逻辑可以保留 |
| verify：TLS pin、SSH 身份、本人 VM、VM sudo/CLI、SFTP 往返、Claude 登录 | 不变 | 只把连接地址换成本地端口 |
| verify：隧道归属、握手时间 | 改 | 不再用 `sudo wg show`，改为代理 `status`（原型输出公钥、peer、Endpoint、握手秒数、收发字节），不需要 sudo |
| verify：路由冲突 `ROUTE_CONFLICT` | 去掉 | 没有系统路由，不会再和公司 VPN 抢 `10.234.0.x` 的路由；外层 UDP 照常走系统默认出口 |
| 重启后恢复 | 改善 | 登录时由 LaunchAgent / systemd user / Run 键自动拉起，不再需要 connect |
| 系统任何程序都能直接访问 `10.234.0.2` | 失去 | 只剩代理转发的 22、8443、60000–61000。ssh 系的工具（scp、rsync、VS Code Remote-SSH）都读 `ssh_config`，不受影响；ping 和直接用 IP 的工具不能用 |
| 吞吐 | 足够 | 原型在本机两端都是 netstack 的情况下，经 SSH 传 200 MB 用了 2.5 秒（约 80 MB/s），远高于需要 |
| 断网、换网后 Mosh 恢复 | 不变 | 原型在 Mosh 会话中途杀掉代理再重启，会话继续可用（重启前后写入的 p1、p2、p3 都落盘） |

## 6. 迁移成本

### workspace-onboarding

| 文件 | 改动 | 估计 |
| --- | --- | --- |
| 新增 `agent/`（Go 源码）和 CI 发布流程 | 读设备包配置、单实例、控制套接字、TCP 和 UDP 转发、`status`、`endpoint`（含域名解析）、三平台自启的安装和卸载辅助、单元测试；GitHub Actions 交叉编译，生成 SHA-256 并固定在仓库里，bootstrap 下载后先核对哈希再运行；Windows 视阶段 0 结果决定是否签名 | 5–7 天 |
| `scripts/unix.sh`（773 行） | 删掉 wg-quick 相关的全部逻辑（`client_ready` 探测、`run_wg_quick`、`resolve_tunnel_interface`、`owned_tunnel`、`tunnel_route_state`、`check_new_tunnel_route`、`start_tunnel`、disconnect 和 route 的 sudo 分支、verify 的握手检查），大约 250 行，改成安装代理、写 LaunchAgent 或 systemd user 单元、调用 `status` 和 `endpoint`；`write_configs` 生成新的 `ssh_config`；`require_tunnel_admin` 只在 Linux apt 装 mosh 时保留 | 2–3 天 |
| `scripts/windows.ps1`（600 行）、`bootstrap.ps1` | 去掉 MSI 下载和签名校验、`/installtunnelservice`、`Admin()` 检查，加 HKCU Run 键；参数不变 | 2 天 |
| `docs/` | README 去掉 sudo、UAC 两行和管理员窗口说明；改 `system-authorization.md`、`mosh.md`（Windows/WSL 部分按阶段 0 结果重写）、`route.md`（不再需要 sudo）、`verification.md`、`troubleshooting.md`（新增 `AGENT_*` 错误码，删掉路由冲突相关） | 1–1.5 天 |
| `tests/test_bootstrap.py`（1265 行） | 把模拟 sudo 和 wg 的用例换成模拟代理 | 2 天 |
| 三平台试点（含 Windows 普通账号） | | 2 天 |

### 其他

- **设备包 manifest：不用改。** 现有字段（`wg.key`、`wireguard_address`、`wireguard_public_key`、`wireguard_endpoint`、`ssh_gateway`、`known_hosts`、`tls_certificate_sha256`）已经足够代理使用。`desktop_url` 字段保持 overlay 地址，由 bootstrap 本地换算出 `https://127.0.0.1:18443/`，这样 `hub-bundle.py` 的校验不用动，`schema_version` 和 `tool_version` 也不用升。
- **wsctl：生成设备包的代码不用改。** 迁移靠现有的换发功能（新密钥、新 peer）。`hub-bundle.py` 里设备包 README 的说明文字可以顺手更新，不是必须。
- **IaC：** `oci-hub-spoke` 的 `desktop.conf.j2` 放行 `127.0.0.1:18443`，下发到所有员工 VM，约半天加上线时间。

合计约 15–20 人日。

### 新旧并存与平滑过渡

- **同一把密钥绝不能两边同时跑。** 推荐的迁移方式：管理员先换发设备包（新密钥），员工用新版 bootstrap 跑 `setup`，装的是代理。旧 peer 在 Portal 里随换发失效，旧隧道就算还开着也握不了手。
- **旧隧道开着不影响代理。** 旧隧道只占 `10.234.0.x/32` 的系统路由，代理的外层 UDP 发往 Hub 的公网地址，不经过它；代理访问 VM 也不走系统路由。所以迁移不需要先跑一次 sudo `disconnect`。macOS/Linux 的 wg-quick 隧道下次重启就没了。Windows 的隧道服务会一直留着，但已经失效，卸载要 UAC，可以作为可选的清理步骤告诉员工。
- **bootstrap 版本**：发 2.0.0。`setup` 发现旧的 wg-quick 安装时归档旧状态目录（复用现有的 REISSUE 归档逻辑）。旧代码路径保留一个版本，用 `--tunnel=system` 打开，作为出问题时的回退，确认稳定后删除。
- **VM nginx 先上线。** 同时接受 overlay IP 和 127.0.0.1，新旧客户端都能用浏览器入口。

## 7. 风险

1. **Windows 防火墙弹窗。** wireguard-go 的默认 bind 监听所有接口的 UDP。Microsoft 文档说，普通用户遇到弹窗时无论点什么都会生成阻止入站的规则；按 WFP 的状态过滤原理，主动发出的 UDP 的回包应该仍然放行，但这只是推断，必须实测。如果实测不行，Windows 继续用官方隧道服务。
2. **Smart App Control 和 Defender。** Windows 11 开了 Smart App Control 时会直接拦截未签名的 exe。缓解办法是代码签名，比如 Azure Trusted Signing 或 OV 证书，有年费；企业管理的电脑上 SAC 默认关闭，但 EDR 可能拦截。
3. **macOS 登录项可见、可被关闭。** 员工关掉后代理不会自启，verify 要报明确的错误码，并提示到“登录项”里重新打开。
4. **本地端口冲突**：22022、18443、60000–61000。启动失败时要报出具体占用了哪个端口的错误码。
5. **加速线路域名解析**：见第 5 节。
6. **维护负担。** 代理是我们自己发布的二进制，wireguard-go 和 gVisor 的安全更新要跟进。要有固定的发布流程和哈希核对。
7. **Windows 上 Mosh 走 WSL 的路径**：见 4.2，可能要降级成 MobaXterm 或原生 ssh。
8. **MTU。** 原型用 1280（沿用此前测试的初始值），真实链路上需要再按 `oci-employee-vpn-hub.md` 第 4 节的要求测一次。

## 8. 两种替代方案

**各平台官方 WireGuard App：不采用。**

- macOS App Store 版最后更新是 2023-02，没有命令行，导入隧道要员工在图形界面里点，还会弹系统的“添加 VPN 配置”确认；有报告说在 MDM 管理的 Mac 上普通用户还要输密码。按需连接规则可以解决重启后自动连接，但 Agent 没法脚本化 setup、route、verify。
- Linux 上 NetworkManager 导入建的是系统级连接，polkit 默认 `settings.modify.system` 需要管理员。
- Windows 上普通用户要先由管理员加进 Network Configuration Operators 组并设置 `LimitedOperatorUI`，而且加进去后只能启停，不能导入。
- 三个平台都绕不开首次提权。

**自己做原生 App（macOS NetworkExtension）：不做。**

- 要付费开发者账号（每年 99 美元）、Developer ID 签名和公证，App Store 以外分发只能用系统扩展形式。
- 系统扩展首次加载需要管理员在系统设置里批准，所以“不需要管理员”的目标本身就达不到。
- WireGuardKit 最后更新是 2023-02，还要另做 Windows 和 Linux。
- 投入远大于本方案。

## 9. 原型验证记录

位置：不进本仓库。源码副本已移到新项目 `remotecc-client` 的 `prototype/` 目录。原型是在本机起一对 wireguard-go netstack peer：客户端 `10.235.0.2` 扮员工设备；“VM”端 `10.234.0.2` 把隧道内的 22、8443、60000–61000 转给本机只监听 `::1` 的 sshd、`openssl s_server` 和 mosh-server。所有密钥都是临时生成的，测试结束后进程已全部停止。

| 测试 | 结果 |
| --- | --- |
| 6 个平台交叉编译 | 通过（darwin、linux、windows 各 arm64 和 amd64）；Windows 版没有运行测试 |
| 单实例锁 | 第二个进程报 `AGENT_ALREADY_RUNNING`，退出码 3 |
| `ssh alice-vm`（HostName 127.0.0.1 + HostKeyAlias） | 通过，host pin 生效 |
| `ssh alice-vm-pc`（ProxyCommand 经 Unix 套接字） | 通过 |
| SFTP 100 KB 往返 | 内容一致 |
| TLS pin 经 127.0.0.1:18443 | 指纹一致；严格校验报名称不匹配（预期内） |
| 200 MB 吞吐 | 2.5 秒 |
| UDP 回显 50 次（1200 字节） | 50/50，中位往返 0.18 ms |
| 原版 `mosh alice-vm` | 通过 |
| Mosh 会话中在线换 Endpoint | 会话不断 |
| Mosh 会话中重启代理 | 会话自动恢复 |
| 在线换线路（无 sudo） | 生效；传域名被 UAPI 拒绝（见第 5 节） |
| 资源占用 | RSS 约 11 MB，约 1015 个文件描述符 |

没有覆盖的：Windows 和 Linux 实机运行、LaunchAgent/systemd/Run 键自启（没有改本机登录项）、睡眠唤醒、真实公网和 NAT 链路、真实 Hub 的 ACL。

外部资料（2026-11-14 查阅）：

- 工具：wireproxy https://github.com/windtf/wireproxy ；onetun https://github.com/aramperes/onetun ；Tailscale userspace https://tailscale.com/kb/1112/userspace-networking ；tsnet https://pkg.go.dev/tailscale.com/tsnet ；wireguard-go https://git.zx2c4.com/wireguard-go ；sing-box https://github.com/SagerNet/sing-box
- macOS：Gatekeeper https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web ；Go 在 darwin/arm64 上的签名 https://github.com/golang/go/issues/42684 ；登录项管理 https://support.apple.com/guide/deployment/manage-login-items-background-tasks-mac-depdca572563/web
- Windows：Smart App Control https://support.microsoft.com/en-us/topic/what-is-smart-app-control-285ea03d-fa88-4d56-882e-6698afdb7003 ；防火墙规则 https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules ；Mark-of-the-Web https://outflank.nl/blog/2020/03/30/mark-of-the-web-from-a-red-teams-perspective/ ；Go FAQ（杀毒误报）https://go.dev/doc/faq
- Linux：logind polkit 策略 https://github.com/systemd/systemd/blob/main/src/login/org.freedesktop.login1.policy ；NetworkManager polkit 策略 https://gitlab.freedesktop.org/NetworkManager/NetworkManager/-/blob/main/data/org.freedesktop.NetworkManager.policy.in
- 官方 App 和原生 App：wireguard-windows 非管理员配置 https://git.zx2c4.com/wireguard-windows/about/docs/adminregistry.md ；NetworkExtension 部署方式 TN3134 https://developer.apple.com/documentation/technotes/tn3134-network-extension-provider-deployment ；系统扩展审批 https://support.apple.com/guide/deployment/system-and-kernel-extensions-in-macos-depa5fb8376f/web

## 10. 建议的分阶段步骤

- **阶段 0（2–3 天，决定做不做）**：
  - 把原型编成正式的小程序。
  - 在 Windows 10 和 Windows 11 的普通账号上实测：防火墙弹窗、点取消后外发 UDP 是否仍通、Smart App Control、Defender、HKCU Run 自启，以及 MobaXterm 和 WSL（NAT 与 mirrored 两种模式）下的 Mosh。
  - 在一台测试 VM 上改 nginx 放行 127.0.0.1，用测试设备包（新建的测试 peer，不用员工的）连真实 Hub，跑一遍 SSH、Mosh、浏览器、verify、route。
  - 出口条件：三平台都不需要提权、Hub 记账正常、浏览器入口可用。
- **阶段 1（约 1 周）**：
  - 完成代理正式版和 CI 发布。
  - workspace-onboarding 2.0.0：unix.sh、windows.ps1、文档、测试。
  - IaC 把 nginx 改动下发到全部员工 VM。
- **阶段 2（约 3 天）**：
  - 一名员工按换发设备包的方式试点，三平台各一台。
  - 观察一周：配额、握手、睡眠唤醒、自启是否被关掉。
- **阶段 3**：
  - 逐个员工换发设备包。
  - 全部迁完后删掉 `--tunnel=system` 回退路径和旧文档。
