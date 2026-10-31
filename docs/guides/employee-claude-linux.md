# Linux 员工工作环境上手指引

> 新设备优先使用管理员分配的员工专属 Bootstrap 私有项目。当前 pilot 交付为 [workspace-onboarding](https://github.com/blue126/workspace-onboarding)，含该用户设备包和实际配置单；不要给其他员工共享此身份。下文保留旧手工包流程作为兼容回退。

以下以Ubuntu／Debian为例。流程是“解压本设备接入包 → 启用WireGuard → 运行连接脚本”。

## 管理员给你什么

管理员为这台设备预配一个接入包，你无需生成密钥或提交公钥。每台设备使用独立的包；第二台电脑需另行开通。

交付时管理员会给你：设备账号、分配的VM主机名、接入包编号，以及通过独立渠道确认的下载包SHA256。包内包含WireGuard配置、SSH连接凭据、入口身份校验文件和连接脚本。它属于公司接入凭据，请保存在仅本人可读的本机目录，不转发给他人或放进共享目录、Git。

接入包由管理员填入本设备的实际入口和身份配置，确认开通后按本文连接。

接入包中的WireGuard只路由工作入口，本机浏览器和其他本地应用仍走本机网络。个人Claude账号不在接入包中，由你本人在澳洲VM内登录。

## 1. 准备客户端

获得本机软件安装许可后执行：

```bash
sudo apt update
sudo apt install wireguard openssh-client
```

其他发行版按[WireGuard官方安装页](https://www.wireguard.com/install/)使用本发行版包管理器。

## 2. 安装本设备配置

下载管理员私密交付的包，用`sha256sum 接入包.zip`核对摘要与独立提供的值，再解压到仅本人使用的目录。包内密钥已生成并登记，无需提交公钥。

本机终端进入解压目录，先检查是否有同名隧道：

```bash
sudo test -e /etc/wireguard/employee.conf && printf '已有同名配置，请先联系管理员，不覆盖\n'
```

若已存在，请先联系管理员；确认不存在后安装并启用：

```bash
sudo install -d -m 700 /etc/wireguard
sudo install -m 600 ./employee.conf /etc/wireguard/employee.conf
sudo wg-quick up employee
```

## 3. 打开工作终端

在接入包目录执行：

```bash
bash ./connect.sh
```

脚本设置本机私钥文件权限并使用包内固定配置连接，入口身份由`known_hosts`自动校验。成功后直接进入你的VM。身份校验失败时联系管理员，不关闭校验。

如连接超时，执行`sudo wg show employee latest-handshakes`查看最近握手。先触发SSH请求再看；一直没有握手时反馈管理员，不导出或发送完整配置。
## 进入后做第一次检查

下面命令在**远端 VM 的交互终端**执行：

```bash
whoami
hostname
sudo -n true
claude --version
mkdir -p ~/work/acceptance
printf 'workspace check\n' > ~/work/acceptance/persistence.txt
cat ~/work/acceptance/persistence.txt
```

预期账号是 `employee`，主机名与交付卡一致，sudo 命令成功，Claude 显示版本。你拥有该 VM 的 sudo，可自行安装项目依赖和工具；项目可放在 `~/work`。退出 SSH 后重新进入，确认该文件仍在。

首次试用时，请完成一个自己的小任务：上传或克隆项目、安装依赖、修改代码、执行项目检查，并取回交付文件。记录回显卡顿、传输体验、掉线及重新连接情况。请勿把“能够登录”单独视为完成用户验收。

## 使用 VM 浏览器

在远端终端运行：

```bash
workspace-browser start
```

保持 WireGuard 开启，从就绪后的 `workspace-browser start` 或 `workspace-browser status` 输出取得自己的 `https://<目标 VM overlay IPv4>:8443/` 根 URL。设备经 OCI Hub 访问所分配 VM，TLS 在目标 VM 终止，叶证书 IP SAN 必须匹配该 overlay IP。首次连接先完成[桌面入口与设备信任核验](employee-browser-lifecycle.md)，再在本机浏览器打开命令输出的 URL；未知分配地址时联系管理员，不猜地址、不追加旧路径、不改用 HTTP 或旧共享入口。Firefox 在你的澳洲 VM 上运行，可在画面内输入网址、操作网站或访问 VM 内的开发网页。需要时允许本机浏览器访问此私网地址。完成 HTTPS/CA 核验且没有证书警告后，页面首次一直加载时可刷新重试；遇到证书警告时停止并联系管理员。VM500 保留 HAPI 控制面；HAPI 接入不要求执行本项桌面信任步骤。

| 远端命令 | 用途 |
| --- | --- |
| `workspace-browser start` | 启动；已运行时直接显示画面地址，不重复开一套浏览器 |
| `workspace-browser status` | 查看运行状态和画面地址 |
| `workspace-browser open https://example.com` | 在同一浏览器新标签中打开网页 |
| `workspace-browser stop` | 关闭浏览器和 VM 图形后端，保留个人配置及已保存登录态 |

关闭本机网页、SSH 断开或暂时停用 WireGuard，VM 浏览器会继续运行。重新连接 WireGuard 后刷新上方地址即可继续；无需重新启动浏览器。浏览器没有 30 分钟运行上限，画面连接空闲断开时可刷新重连。不用时请运行 `workspace-browser stop`。

Cookie、历史记录、个人设置和下载文件留在自己的 VM。下载文件可通过 SFTP 取回；本机与 VM 之间的剪贴板操作按当前桌面界面提示进行。VM 重启后需要重新运行 start；恢复哪些标签由 Firefox 设置决定。不要把画面访问地址理解为可绕过 WireGuard 的公网入口。

## Claude 登录与使用

在远端 `employee@employee-...` 终端执行一次：

```bash
workspace-login
```

助手先检查已保存的 Claude 订阅登录；有效时直接显示状态。需要授权时，自动启动或复用同一个 VM 浏览器，并在新标签打开当次授权页，终端会显示私网画面地址：

使用就绪后的 `workspace-browser start` 或 `workspace-browser status` 输出的同一目标 HTTPS 根 URL；首次打开前按[设备信任说明](employee-browser-lifecycle.md)核验公开 CA 与目标 IP SAN。

保持 WireGuard 开启，并保留这个 SSH 终端。在本机浏览器打开已核验的命令输出地址。你看到的 Firefox 实际运行在自己的澳洲 VM；在这个画面内点击邮箱框、输入、完成邮件／SSO／验证码和授权同意。本机浏览器只显示远端画面。无需安装 VNC 客户端，也无需复制 CLI 的 OAuth 链接到本机。

网页画面太大或需要粘贴时，按当前桌面界面的缩放与剪贴板提示操作；先点击远端输入框再输入。若 Firefox 页面显示一段授权码，复制该码并按当前 SSH 终端中的官方提示粘贴；不要发给管理员或 Agent。

看到终端“Claude 登录成功”后，在远端执行：

```bash
claude auth status --text
cd ~/work/acceptance
claude
```

自行核对本人账号、预期订阅和认证来源，只反馈是否正确。在 Claude 中完成一个不含秘密的小代码任务。之后普通 SSH 重连直接运行 `claude`，无需重复登录。

- 取消整个流程：在 SSH 终端按 `Ctrl+B`，松开后按 `d`。助手会取消本次 Claude 授权；日常浏览器继续保留。关闭浏览器使用 workspace-browser stop，不会删除已保存凭据。
- 成功、取消、终端断开或超过 30 分钟后，结束的是本次 Claude 授权流程，日常浏览器会继续运行。可以手工关闭不再使用的授权标签；不用浏览器时请运行 workspace-browser stop。
- 网页无法连接：先确认 WireGuard、SSH 均正常，并运行 workspace-browser status 确认浏览器已启动；必要时运行 workspace-browser start，再刷新页面。
- 提示已有登录流程：返回原窗口完成或取消。提示已有旧 Browsh 时，在旧浏览器按 `Ctrl+Q` 退出后重试。
- 提示其他认证来源：自行检查 `claude auth status --text`。助手不会覆盖 API key 或外部令牌配置。
- 邮件、SSO、人机验证或授权失败：反馈发生步骤和错误文字，隐藏个人信息。不要发送验证码、令牌、完整 OAuth 链接或浏览器会话。

登录态和专用 Firefox 配置保存在个人 VM；普通 SSH 重连不会清除它们。真实账号授权和任务响应仍须由本人验收。公司提供基础 Claude Code、VM 内授权浏览器及助手；项目工具和依赖由员工自主管理。

## 日常限制与断线

入口支持交互 SSH 和 SFTP。连接后可在 VM 内正常执行命令；`ssh 入口账号@入口IP 命令` 这种远程命令形式会被拒绝，旧版 SCP、rsync、SSH 端口转发、ProxyJump，以及依赖这些能力的 Remote SSH 工具不作为本阶段使用方式。文件请按本文使用 SFTP。

工作完成后，在远端输入 `exit` 退出 SSH，再按下文停用 WireGuard。重新连接后项目文件和配置仍在；普通 SSH 断线不保证前台程序继续运行。若项目已有需要，可在远端使用 tmux 管理长任务。

## 遇到问题时反馈什么

| 现象 | 你可以先检查 | 发给管理员的信息 |
|---|---|---|
| WireGuard 激活但 SSH 超时 | 触发一次 SSH 后看最近握手时间；核对 Endpoint；换另一条获准网络对照 | 时间与时区、网络类型、最近握手时间、有无收发流量 |
| `Permission denied (publickey)` | 是否打开本设备的原始接入包，文件是否被移动或删除 | 设备账号、接入包编号、完整错误文字 |
| SSH 主机指纹变化 | 暂停连接并联系管理员核对 | 主机地址和提示；不要自行删除 known_hosts 或关闭校验 |
| `Access denied.` | 是否在 SSH 命令后追加了远程命令；设备是否已撤销 | 设备账号、所用命令（隐藏个人路径即可）、发生时间 |
| 进入了错误 VM | 对比 hostname 与交付卡，退出并联系管理员 | 实际和预期主机名 |
| 卡顿或掉线 | 记录时段、当前网络和可重复操作 | 回显延迟、是否可重连、同一小文件的传输耗时 |
| Claude 未登录或登录失败 | 确认是在远端 VM，按 VM 内授权步骤检查 | 版本、认证来源、错误文字；隐藏个人信息和凭据 |

不要发送私钥、完整 WireGuard 配置、验证码、令牌或浏览器会话。设备丢失时立即报告设备账号，管理员将撤销其受管接入和活动会话；新设备需要重新登记。


## 上传和下载

另开本机终端，进入同一接入包目录执行：

```bash
bash ./sftp.sh
```

在`sftp>`中执行，本机路径按实际替换：

```text
pwd
lcd /home/YOUR-LINUX-USER/Downloads
cd work/acceptance
put sample.txt
get persistence.txt persistence-from-vm.txt
bye
```

先在本机准备不含秘密的`sample.txt`。`lcd`指本机，`cd`指VM。下载后检查内容。结束后在本机执行：

```bash
sudo wg-quick down employee
```

## 参考

[WireGuard官方安装页](https://www.wireguard.com/install/)、[快速开始](https://www.wireguard.com/quickstart/)、[Claude CLI参考](https://code.claude.com/docs/en/cli-reference)。
