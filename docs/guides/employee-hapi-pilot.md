# VM502 HAPI 单人试点

本试点仅覆盖 `employee-control`（VM502）的 `employee` 用户。浏览器在本地编辑输入；Hub、Runner、Claude Agent SDK、Claude 进程与凭据均位于 VM。先由本人通过 `workspace-login` 登录，再实测订阅能否用于 HAPI 远程请求；`workspace-login --check` 只检查安装，不代表登录成功。登录或订阅失败即停止请求，由本人处理 VM 登录，不能切换计费方式。

入口固定为 `https://hapi-test.willfan.me`，经专用 Cloudflare Named Tunnel、HTTP/2 连接 VM 的 `127.0.0.1:3006`。HAPI 以令牌认证，无邮件验证码。该令牌代表本人的完整 VM 执行权限，不能交给其他人。试点使用默认审批模式；新建 Claude 会话时确认界面为 `default`，不选择自动批准或绕过审批。

## 安装与配置

HAPI 固定使用官方 v0.33.2 `hapi-linux-x64-baseline.tar.gz`，SHA256 为 `45d843d700e656cf3a9db4b0df7c4c1b174fd334fe8194ea73b3bbc78c564290`，同时与该版本官方 `checksums.txt` 和 GitHub release asset digest 核对。独立 cloudflared 二进制固定为 2026.10.5，避免改变 VM 上其他服务的软件。

三个独立 systemd unit 为 `employee-hapi-hub`、`employee-hapi-runner`、`employee-hapi-tunnel`。Hub/Runner 使用 `User=employee`、`HOME=/home/employee`、`UMask=0077`；Runner 使用前台 `start-sync` 和 `HAPI_RUNNER_SUPERVISED=1`。Tunnel 通过 root 读取 `0600` 的 token file。HAPI 数据保存在 `/home/employee/.hapi`，运行环境文件在 `/etc/employee-hapi/hapi.env`，属主 root、权限 `0600`。令牌不会放在命令行、库存默认值或 Git 文件中。

Hub/Runner 的 stdout/stderr 分别追加到 `.hapi/logs/hub-service.log` 和 `runner-service.log`，属主 employee、权限 `0600`，不进入 journal。官方 Hub 在生成新令牌和公共 relay 配对时会打印含 token 的内容；本配置固定提供环境令牌并禁用 relay，同时仍隔离服务输出。日志只能在本人 VM 私下诊断，不回显到共享报告。

`--no-relay` 禁用公共 relay，`HAPI_DISABLE_PEER_TOOLS=1` 禁用 peer tools；Telegram、Server酱、iOS 和 Android 推送已关闭。v0.33.2 没有全局禁用 Web Push 的环境开关，专用 Tunnel 将 `/api/push/.*` 返回 403，阻止公网浏览器登记订阅。浏览器通知保持未授权，试点期间不在网页启用通知；新安装没有现存 Web Push 订阅。试点不修改 Claude 配置。

所有 Ansible 命令从任务 Docker Sandbox 的仓库 `ansible/` 目录执行，Sandbox 名称为 `iac-codex-vm502-hapi-pilot-direct-v130`。私有 EmployeeWorkspace BWS 工作流生成临时加密 runtime extra-vars；HAPI 维护须显式使用正式管理员工具的 `bws-store.py compose-vault OUTPUT --include-hapi`，提供 `vault_employee_hapi_api_token`，第二阶段另提供 `vault_employee_hapi_tunnel_token`。普通员工开户仍使用 `onboard.sh`，不会读取或注入 HAPI 服务令牌。不得仅带全局 IaC Vault 执行员工部署，不把 BWS machine token 复制到 VM。下文 `/tmp/employee-hapi-runtime.yml` 代表该私有流程输出，实际路径以本次输出为准。

```bash
ansible-playbook playbooks/deploy-employee-hapi.yml --syntax-check
ansible-lint -c ../.ansible-lint playbooks/deploy-employee-hapi.yml roles/employee-hapi

# First deploy through the VM management channel, with no public entry.
ansible-playbook playbooks/deploy-employee-hapi.yml \
  -e @/tmp/employee-hapi-runtime.yml
```

首轮预期：Hub/Runner active，Tunnel inactive/disabled；端口只监听 `127.0.0.1:3006`；无令牌、错误令牌与错误 JWT 均返回 401/403，正确令牌可获取会话列表、在线 Runner 和 SSE 连接事件。协议检查失败会关闭专用 Tunnel 并令 playbook 失败。

管理通道检查通过后，先查询 Cloudflare 上完整域名的所有记录。域名已占用则停止，不接管记录。创建仅用于本试点的 Named Tunnel；远程配置按顺序匹配 `hapi-test.willfan.me` 的 `^/api/push/.* → http_status:403`、该域名其余路径 `→ http://127.0.0.1:3006`、最终 `http_status:404`，然后创建指向专用 tunnel ID 的 proxied CNAME。Tunnel token 写入 BWS 后，由私有流程重新生成 runtime extra-vars。

```bash
# Enable only after the dedicated remote Tunnel configuration and DNS exist.
ansible-playbook playbooks/deploy-employee-hapi.yml \
  -e @/tmp/employee-hapi-runtime.yml -e employee_hapi_tunnel_enabled=true

ansible-playbook playbooks/deploy-employee-hapi.yml --tags verify \
  -e @/tmp/employee-hapi-runtime.yml
```

上线预期：三个 unit active，3006 仍只在 loopback；公网有效/无效认证和 SSE 检查通过，已认证的 `/api/push/vapid-public-key` 仍返回 403。若公网检查失败，playbook 停止并禁用 Tunnel。验证不会发起模型请求或自动批准工具。

验证器显式发送 `Mozilla/5.0 (compatible; EmployeeHapiVerifier/1.0)` User-Agent，以兼容 Cloudflare Browser Integrity Check 对 Python urllib 默认标识的限制；Cloudflare 保护和所有认证状态码断言保持启用，有效令牌收到 403 仍判失败。

同一配置再次执行部署命令，预期 `changed=0`。正在执行的任务期间不要重启或重新配置 Runner；systemd 停止 Runner 会停止其会话子进程。

## VM502 登录助手热修复

VM502 的查看地址现为 `http://127.0.0.1:16081/vnc.html#autoconnect=1&resize=scale&reconnect=0`。它依赖当前管理员电脑已经建立的 SSH 通道，只供管理员临时协助，须在该电脑打开；它不是员工公网登录入口。配置仅调整 VM502 的 `viewer_url` 和访问说明，保留原 `bind_address`；其他员工继续使用既有配置和 WireGuard 默认说明。

`workspace-login` 将 `claude auth login` 的 stdout/stderr 写入本次私有运行目录的 `0600` 日志，不再把原始 OAuth 链接或查询串转发到终端。VM opener 仍收到完整原链接，登录在 VM Firefox 内完成；若页面提供授权码，回原终端粘贴后按回车。终端只显示 VM 查看入口、操作和登录结果提示，本次流程结束或取消后清理私有运行目录。已登录短路、取消、超时和日常浏览器保留行为继续有效。

已启动的旧助手不会因复制文件而改变行为，须本人先退出旧 `workspace-login`，再重跑。热修复不自动取消当前授权会话。

在本任务 Sandbox 的 `ansible/` 目录，用管理员准备的精确 VM502 静态 inventory 执行：

```bash
ansible-playbook -i /tmp/employee-hapi-inventory.yml \
  playbooks/deploy-employee-hapi.yml --tags hapi_login_helper
```

该热修复使用 `never` tag，仅在显式指定 `--tags hapi_login_helper` 时执行；普通 HAPI 部署和 `--tags verify` 均不写入临时查看入口。它只更新两份助手和查看配置，不读取 HAPI 令牌，不重启 HAPI、Runner 或个人浏览器，不修改 Cloudflare 或网关。完成后本人重跑 `workspace-login`，核对显示的临时入口及管理员通道依赖说明。运行 `python3 tests/employee-workspace/test-login.py` 可在已有 tmux 的批准环境中使用隔离 HOME、真实 tmux/PTY 和合成 CLI，检查原始授权 URL 不外泄、VM opener 参数保留、手动验证码、取消/失败与旧流程兼容。

## 固定检查命令与记录

以下命令通过 VM 管理通道执行，不使用员工 SSH 端口转发：

```bash
sudo systemctl is-active employee-hapi-hub employee-hapi-runner employee-hapi-tunnel
sudo ss -H -ltn 'sport = :3006'
sudo python3 /usr/local/lib/employee-hapi-verify.py
sudo python3 /usr/local/lib/employee-hapi-verify.py https://hapi-test.willfan.me
sudo systemctl show employee-hapi-hub employee-hapi-runner employee-hapi-tunnel \
  --property=Id,MemoryCurrent,MemoryPeak
ps -eo user,pid,ppid,rss,comm --sort=-rss
```

记录日期、客户端网络、浏览器、HAPI/Claude 版本、unit 状态、认证返回码、SSE 结果、幂等 recap。记录空闲和任务期间各服务进程及 Claude 子进程的 `RSS`（KiB），并记录 systemd cgroup 的 `MemoryCurrent`/`MemoryPeak`（字节）；两者指标含义不同，不混写成 RSS。不要把令牌、JWT、浏览器登录存储、Claude 凭据或含凭据的环境输出贴进报告。

协议验证器只证明认证、Runner 注册、SSE 建连和重新加载会话列表。它不能证明真实模型请求、长任务完成或中文输入体验；下面各项必须单独记录。

## 真人验收

1. 本人通过现有员工入口执行 `workspace-login` 完成 VM 登录。用浏览器打开试点域名，以 BWS 中本人试点令牌登录，保持浏览器通知未授权。新建 Claude 会话，目录为 `/home/employee`，确认审批模式 `default`。
2. 在中国浏览器连续一分钟进行输入、退格和中文组词，先不提交。记录是否丢字、重复、组词中断及本人对跟手程度的结论；再单独记录提交到首个响应的耗时。Cloudflare 不保证降低 RTT；中国 Linux `192.168.8.1` 的 HTTP 测量不能代替真人体感。
3. 发起一次最小真实请求。记录成功/失败、会话 ID、模型和时间；管理通道用上面的 `ps` 查看 employee 的 HAPI/Claude 子进程，必要时用 `sudo ss -tpn` 记录 VM 模型出站。本人确认凭据来自 VM 登录；远程模式包含 Agent SDK，不能仅根据 Claude CLI 已登录推定订阅兼容。失败立即停止，不换 API Key 或计费方式。
4. 在独立 `/home/employee/hapi-pilot-check` 目录请求一次需要审批的写入：向新建 `approval-once.txt` 追加一行。若该操作被现有权限直接允许，则改用确实出现审批对话框的无害操作，不能把直接执行算通过。审批出现后等待五分钟，通过管理通道确认目标仍不存在；点击批准一次后，确认目标只写入一次。记录审批前后时间和文件结果。
5. 发起明确获准的两分钟任务，例如先批准 `sleep 120` 再写入专用 `completed.txt` 标记。在任务开始后关闭网页，三分钟后重开。确认完成标记存在，原会话和记录恢复；留存时间、会话 ID、完成标记及结果。此项失败应保留证据，不能以 API 会话列表重新加载成功代替。
6. 在真人任务期间和空闲时分别采样 RSS；核对无效令牌拒绝、重复部署 `changed=0`，完成验收表。未完成项记为“待本人验收”，不能预填通过。

| 验收项 | 结果 | 证据/本人结论 |
|---|---|---|
| 中文输入与交互体验 | 用户整体接受 | 用户确认“效果不错”；未留一分钟逐项记录 |
| 首响应延迟（单独记录） | 未单独测量 | 用户整体体验已接受 |
| VM 真实 Claude 请求/订阅复用 | 已观察到成功回复 | 本人 VM 登录后的 Opus5.5 会话 |
| 五分钟后审批且仅执行一次 | 未单独留证 | 用户整体体验已接受 |
| 关闭三分钟后恢复两分钟任务 | 未单独留证 | 用户整体体验已接受 |
| 有效/无效令牌与 SSE | 已通过 | 本机与公网，Web Push 403 |
| 重跑部署幂等 | 已通过 | ok=30，changed=0，failed=0 |
| 空闲/任务峰值 RSS | 任务峰值待采样 | 已记录服务 cgroup 数据，未混作 RSS |

## 回滚

先关闭公网入口，再停止 VM 服务。仅操作本次记录的专用 Tunnel ID、DNS record ID 和 BWS Secret ID；先核对它们确属本试点。Cloudflare 禁用或删除专用 DNS/Tunnel，使公网不再可用；然后在 VM 执行：

```bash
sudo systemctl disable --now employee-hapi-tunnel
sudo systemctl disable --now employee-hapi-runner employee-hapi-hub
sudo ss -H -ltn 'sport = :3006'
```

预期三个 unit inactive/disabled、3006 无监听、公网入口不可达。撤销 BWS 试点 token（Tunnel token 同时随专用 Tunnel 撤销）。已获回滚资源删除授权后，才删除专用 unit、`/etc/employee-hapi`、`/opt/employee-hapi/v0.33.2`、本角色安装的两个 `/usr/local/bin` 链接/二进制和 `/usr/local/lib/employee-hapi-verify.py`，再 `systemctl daemon-reload`。不要删除共享 cloudflared 或其他 Tunnel。

保留试点报告、会话证据、本人 `.claude` 和工作文件。`.hapi` 含试点历史及持久化令牌；停服后保留为本人私有证据，若要清除需先明确批准具体路径。最后重新核对原员工 SSH 和 `workspace-login --check` 正常；真实登录状态仍由本人确认。

## 依据

- [v0.33.2 官方发布和校验值](https://github.com/tiann/hapi/releases/tag/v0.33.2)
- [固定版本源码：Runner 命令](https://github.com/tiann/hapi/blob/v0.33.2/cli/src/commands/runner.ts)
- [固定版本源码：Hub 认证](https://github.com/tiann/hapi/blob/v0.33.2/hub/src/web/routes/auth.ts)
- [固定版本源码：配置与推送开关](https://github.com/tiann/hapi/blob/v0.33.2/hub/src/configuration.ts)
- [官方部署说明：Named Tunnel、HTTP/2、后台进程](https://hapi.run/docs/guide/deployment)
- [官方集成说明：Claude 远程模式](https://hapi.run/docs/guide/agents)

## 2026-10-29 部署结果

入口已启用，专用 Tunnel 状态 healthy；本机/公网协议检查通过，重复部署 changed=0。中国 Linux 节点三次打开页面均为 HTTP 200，首字节约 2.03–2.50 秒；不能据此推定输入体感或模型响应速度。

用户于 2026-10-29 确认“效果不错，可以认为验收成功”，本次 VM502 单人试点整体用户验收通过。已观察到本人 VM 登录后的真实 Claude 回复。上表保留逐项检查的证据状态；五分钟审批、关页恢复和任务峰值尚无独立计时/采样记录，不预填通过。HAPI 网页登录使用独立试点令牌，个人 Claude 授权留在 VM 内。本次已获三组本地提交授权，提交记录以 Git 历史为准；远端推送与 PR 另行授权。

代码 Quick 审核发现的服务漏检及监听失败未关闭入口问题已修复；隔离故障分支和实机验证通过，实机复核 ok=11、changed=0、failed=0。单人试点按用户决定验收通过；首次登录仍使用当前管理员电脑临时查看通道，员工正式接入不在本次范围内。
