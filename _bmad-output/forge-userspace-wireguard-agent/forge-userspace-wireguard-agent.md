# Forged idea：remotecc 员工客户端（特权守护进程 + TUI）

目的：让员工安装和日常使用都尽量容易。安装时授权一次可以接受；日常使用不再提权。

## 决定

- **形态**：`remotecc` = 特权守护进程 + TUI，一个二进制。守护进程内嵌 wireguard-go，自己管理系统网卡和 /32 路由，不依赖 wireguard-tools、wg-quick 或 bash 4。访问方式（10.234.0.2、desktop_url、VM nginx、ssh 配置）全部不变。
- **仓库**：
  - 新建公开仓库 `remotecc-client`，放 Go 代码、OSI 许可证、发布流水线和 Releases。
  - 另建 `homebrew-tap`。
  - workspace-onboarding 过渡期间继续负责新员工接入。
  - 私有 remotecc 不变。两边只靠三样东西衔接：设备包 schema、Releases 格式、写死在客户端里的验签公钥。
- **平台**：第一期 Mac、Linux、Windows 一起做，最后只保留这一条接入路径。
- **安装**：不再需要 bootstrap。首次分发以 Homebrew tap 为主，curl 一行脚本兜底，Windows 用 PowerShell 一行命令。`sudo remotecc install <设备包>` 是唯一一次提权，它负责校验设备包、安装守护进程、写 ssh 配置、运行 verify。README 只告诉 Agent 运行哪几步。
- **本机提权防线**：
  - 守护进程只运行 root 拥有、员工不可写的那份副本。安装时复制到 root 目录，不能直接跑 Cellar 或下载目录里的文件。
  - 控制通道只认安装时记录的员工身份，只接受白名单命令：status、up/down、route、check-update/apply-update，客户端不能传路径或二进制进来。
  - 私钥只放在 root 目录。root 守护进程不解析员工提交的文件。
- **重新安装**：换发设备包或换登录账号，都按重新安装处理，再授权一次。
- **日常入口**：运行 TUI `remotecc`，回车即用 mosh 进入工作区。同一屏可以看状态、换线路、确认更新、打开 VM 桌面。`mosh/ssh <id>-vm` 仍可直接用。
- **更新**：
  - 默认自动检查并下载，安装前由员工确认；也可以关掉自动检查，改为手动检查。
  - 签名私钥放在 GitHub Actions secret 里，验证公钥写死在二进制中，守护进程自己下载并验签。
  - 本地自动回退：保留上一个版本，更新后自检（隧道起来、能握手），失败就自动换回旧版并在 TUI 提示。
- **Windows 签名**：先不签名上线。PowerShell 分发下来的文件不带网络来源标记，SmartScreen 一般不弹；`remotecc install` 检测到 Smart App Control 开着时，提示员工关掉。同时把客户端拆到公开仓库开源（OSI 许可证、CI 构建、全员开启双因素认证），申请 SignPath Foundation 的免费签名，批下来后切换成签名版。
- **迁移**：wsctl 签发新设备包（新密钥）→ `sudo remotecc install` 拆掉旧系统隧道、装上新隧道、运行 verify → 通过后在 Hub 撤销旧密钥。

## 否决

- **完全免 sudo 的用户态代理（最初的想法）**：一次授权可以接受之后，它为了免授权要付出的代价都不值得，包括 127.0.0.1 转发、改 VM nginx、证书名称不匹配、mosh 整段端口转发。
- **Docker**：在 Mac 上和用户态代理有同样的访问方式代价，还要额外装 Docker Desktop 并常驻一个虚拟机。
- **用 Homebrew tap 负责更新**：要靠员工手动 `brew upgrade`。tap 只负责首次送达。
- **静默自动更新**：改为安装前由员工确认。
- **在 /me 页面下载 CLI**：没有 Apple 签名，会被 Gatekeeper 拦。
- **付费 Windows 签名**：太贵。微软云签名是按月订阅（约 10 美元/月），而且个人资格可能已经暂停；传统代码签名证书每年要几百美元。
- **沿用旧私钥迁移 / 让员工手动卸载旧隧道**：前者要解析三种平台的旧配置，而且旧私钥已经在磁盘上放了很久；后者等于让员工做两次。

## 仍未解决的风险

- **GitHub 或 CI 被攻破**，攻击者可以很快把恶意版本推给所有员工。缓解办法是把签名 job 放进需要人工审批的受保护 Environment，并且只对受保护的 tag 签名。这需要单独授权。
- **员工端前置依赖仍要提权**：没装 Homebrew 的 Mac 要先装 Homebrew，Linux 和 Windows 还要安装 mosh。
- **SignPath 申请**：条款要求项目先以待签名的形式发布过，而且可执行程序要有“可验证的声誉”。只服务少数员工的新客户端短期内很难满足，不签名的时期可能会很长。审核也不一定批；批下来后，Windows 上显示的发布者是 SignPath Foundation，不是我们。在那之前，开着 Smart App Control 的员工必须一直关着它。
- **测试覆盖不到员工环境的差异**。本地自动回退兜住了“更新后起不来”这一种情况，其他差异仍没有覆盖。
