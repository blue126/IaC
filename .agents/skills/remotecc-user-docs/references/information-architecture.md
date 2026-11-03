# /docs 信息架构（草案）

状态：草案，2026-11-03。托管方案已定：Hugo + OINK 构建静态页面，由现有 apply-site Worker 在 `cc.willfan.me/docs/` 下发布（Worker 尚未接入）。

## 实现约定

- **内容存放**：`remotecc/docs/`（独立私有 Git），Hugo + OINK 站点。页面在 `content/<分组>/<slug>.md`，分组为 `start`、`guides`、`reference`、`concepts`，顺序由 front matter 的 `weight` 决定，写法见该目录的 README。
- **构建**：在 `remotecc/docs` 运行 `hugo`，输出到 `public/docs/`，计划由 apply-site Worker 作为静态资源发布（尚未接入）。视觉风格与主站统一（配色、字体、直角、顶栏），来源是 `remotecc/design/tokens.json`。
- **访问权限**：公开，不要求登录。因此本 skill 的安全规则必须严格执行。
- **入口**：首页和「我的工作区」顶部导航（宽屏）、所有页面页脚。「我的工作区」的帮助区和 Claude 登录提示链接到对应页面，等正文写好后再加。

## 页面清单

| 路径 | 标题 | 类型 | 回答的问题 | 主要事实来源 |
| --- | --- | --- | --- | --- |
| `/docs/` | 文档 | 索引 | 我该看哪一页？ | 本文件 |
| `/docs/start/getting-started/` | 从申请到第一次登录 | 教程 | 第一次用，完整走一遍 | `text.json` 的 notes/apply/status；workspace-onboarding |
| `/docs/guides/download-bundle/` | 下载设备接入包 | 操作指南 | 当前这台设备的包去哪里下、包丢了怎么重新下 | `worker.js` 中 `/me` 与 bundle 路由；`text.json` status.bundle |
| `/docs/guides/connect/` | 连接工作区 | 操作指南 | 怎么用 mosh / ssh 登录 | `text.json` status.login_command；workspace-onboarding |
| `/docs/guides/transfer-files/` | 在本机和工作区之间传文件 | 操作指南 | 不同大小的文件分别怎么传 | workspace-onboarding（SSH 配置）；oci-hub 流量额度规则 |
| `/docs/guides/claude-login/` | 在工作区里登录 Claude | 操作指南 | 第一次运行 claude 前要做什么 | `text.json` status.claude_login |
| `/docs/guides/devices-and-renewal/` | 换设备与续期 | 操作指南 | 换电脑、加一台设备、快到期了怎么办 | `text.json` contact、status.expiry_*；admin-handbook（只取员工可感知结果） |
| `/docs/reference/workspace/` | 工作区规格与限额 | 参考 | 配置、流量、各种时限是多少 | `text.json` spec/notes；`worker.js` 中验证码与会话时效 |
| `/docs/reference/troubleshooting/` | 常见问题 | 参考 | 某个现象是什么原因、怎么办 | `worker.js` 错误码 + `text.json` errors；管理员反馈的高频问题 |
| `/docs/concepts/network-and-traffic/` | 网络与流量 | 原理说明 | 哪些流量算进 5 GB，哪些不算 | `ansible/roles/oci-hub`（额度在 OCI Hub 执行）；管理员确认（2026-11-03）：工作区出网走 VM 默认路由经 PVE，不经隧道 |
| `/docs/concepts/how-it-works/` | 工作区如何接入 | 原理说明 | 为什么要 VPN、为什么只能在 VM 里登录 Claude | workspace-onboarding；`docs/guides/employee-claude-workspace.md`（需核实） |

## 页面分工

同一件事只在一页讲完，其他页链接过去：

- **设备包**：download-bundle 只讲当前设备的包在哪里下、包丢了怎么重新下；换电脑、加设备、续期都归 devices-and-renewal。
- **流量**：transfer-files 只给操作做法；哪些流量计入额度、为什么这样传省流量，归 network-and-traffic，transfer-files 链接过去。
- **数值**：时限、额度只在 workspace 写全，其他页引用。

## 页面要点（起草前逐条核实）

- **getting-started**：申请（邮箱验证码、勾选「开始之前」）→ 等待开通邮件 → 「我的工作区」邮箱验证码登录 → 下载设备接入包 → 把邮件里的一句话提示交给本机 AI 助手 → `mosh alice-vm`（示例主机名，以「我的工作区」显示为准）→ 链接到 claude-login。结尾给出“做到这里说明成功”的标志。
- **download-bundle**：只写登录后在「我的工作区」下载：不限次数，设备包保留到设备退役或被新包替换（apply-site e3fc0c2，story 5.17）。包内含私钥，不转发、不放共享目录，只供本设备。不提邮件下载链接：当前开通邮件已不带链接（2026-11-03 核实）。换电脑、加设备链接到 devices-and-renewal。
- **connect**：登录命令以「我的工作区」显示为准；mosh 与 ssh 的区别只写员工需要的部分；连接失败先检查 VPN，链接到 troubleshooting。
- **claude-login**：先在 VM 里运行 `workspace-login`，在本机浏览器打开接入时给出的桌面地址，核对证书指纹，在画面里的 Firefox 登录，授权码贴回终端。开头就警告：不要先在 VM 里直接运行 `claude`。
- **transfer-files**：按文件大小分两种做法，只写怎么做，额度原理链接到 network-and-traffic。
  - 小文件和代码：直接在本机和工作区之间同步。代码优先用 GitHub 等 Git 托管（本机 push、工作区 pull，两端都走各自的互联网，不计额度）；零散小文件用 rsync / scp / sftp 经 SSH 传，走隧道、计入 5 GB，但量小影响不大。用 SSH 上的 rsync 即可，不必另起 rsyncd 服务。
  - 大文件：用 Google Drive、OneDrive 等网盘中转。本机上传、工作区下载，两段都走互联网，不计入额度。工作区没有图形界面时用 rclone 等命令行工具，或在工作区的远程桌面浏览器里下载。
  - 能直接从网上获取的（`git clone`、`curl`、包管理器），直接在工作区里下，不要经本机中转。
- **devices-and-renewal**：换设备、加设备、续期、重新发送设备包都联系管理员；说明「我的工作区」里到期日的含义（北京时间）。
- **workspace**：2 vCPU / 8 GB / 50 GB / 每月 5 GB 双向流量；流量超额暂停、次月自动恢复；状态每小时更新；验证码 10 分钟有效；登录 2 小时有效。全部数值以代码和 `text.json` 当时的值为准。
- **troubleshooting**：按现象组织（收不到验证码、未找到工作区、连不上、桌面地址打不开、流量用完、证书提示不安全），每条给“原因 → 怎么办”。
- **network-and-traffic**：讲清楚两条路径。① 本机 ↔ 工作区：经 WireGuard 隧道和 OCI Hub，按用户统计双向流量，每自然月 5 GB，超额暂停接入，次月自动恢复。② 工作区 ↔ 互联网：走工作区自己的默认路由出网，不经过隧道，不消耗账号的 5 GB 额度（管理员确认，2026-11-03）。只写“不消耗额度”，不承诺带宽或“不限速”。附一张简图。mosh/ssh 交互本身也走隧道、计入额度，但通常很小。
- **how-it-works**：WireGuard 只路由工作入口，本机其他流量不变；Claude 个人账号只在 VM 内登录的理由；服务是 Beta、单人维护，Claude 账号由员工自理（引用首页「开始之前」，不重复整段）。
