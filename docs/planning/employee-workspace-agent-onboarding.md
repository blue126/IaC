# 员工工作环境：由本机 Agent 执行的接入仓库方案

状态：已实现并发布到私有仓库，Windows PS5.1／PS7、macOS、Linux CI 全部通过。日期：2026-10-22。

当前交付：[blue126/workspace-onboarding](https://github.com/blue126/workspace-onboarding)，工具 1.0.0，员工专属私有项目，内置当前 ed-pilot-client 设备包和实际配置单。员工取一个项目即可设置。用户明确要求此方式，替代初稿的通用代码／私密包分离方案；其他员工须新建专属私有仓库，不能 fork 含本人密钥的历史。现有手工包保持兼容。实际系统提权、客户端 VPN 与个人账号验收以对应设备证据为准。

## 初稿设计留档（与当前交付冲突的部分已由上述批准变更覆盖）

## 目标体验

员工使用本机已有、具备文件和终端操作能力的 Agent，提供仓库地址、私密接入包的本机路径、管理员独立交付的 SHA256。Agent 阅读项目说明，完成平台识别、依赖准备、接入配置和分层验证。

目标 VM 内的 Claude 不承担本机首次 bootstrap，避免先登录目标 Claude 才能安装接入工具的循环依赖。只有对话能力、无法操作员工设备的云端 Agent 不具备自动安装条件；它可以生成操作说明，但不能报告已配置本机。

员工可直接向自己的 Agent 发送下面的入口提示：

> 请按这个仓库的 README.md 和 AGENTS.md，为当前电脑完成员工工作环境接入。私密设备包在 `<本机文件路径>`，管理员交付的 SHA256 是 `<校验值>`。先检测现有配置，再执行仓库提供的 bootstrap 和验证脚本。系统要求本人授权或进入个人 Claude 授权时交给我操作。不要读取或打印私钥、完整 WireGuard 配置、授权码或令牌，只报告脱敏检查结果。

仓库也提供相同版本的 ZIP，供不具备 Git 或暂时无法读取仓库的设备使用。

## 仓库职责

建议独立 GitHub 仓库名：`workspace-onboarding`。这是候选名称，尚未创建。

| 位置 | 职责 | 数据 |
| --- | --- | --- |
| 当前 IaC 仓库 | 配置 PVE、网关、员工 VM、设备身份、停用及 VM 内登录助手 | 管理端配置和现有加密 Vault |
| 接入工具仓库 | 本机 Agent 说明、跨平台脚本、连接入口、诊断和员工指引 | 通用代码、脱敏示例和格式定义 |
| 私密设备包 | 管理员为这台设备分配的接入数据 | SSH/WireGuard 凭据、主机身份校验和分配信息 |
| 员工本机私有目录 | 保存导入后的接入配置和流程进度 | 仅本设备可读的配置、白名单诊断结果 |
| 员工个人 VM | 持久开发目录和本人 Claude 登录态 | 员工数据，不随客户端仓库复制 |

员工只需要接入工具仓库的读取能力，不需要 IaC、PVE、Vault、Terraform 或管理员账号访问。公司设备身份仍由管理员预配；员工不生成或提交公钥。

仓库可以是私有仓库；若希望员工无需先取得 GitHub 账号/仓库权限，也可以发布仅含通用代码与说明的公共仓库。实际入口、设备名单和私密包不随公开工具发布。可见性应在创建远端仓库时明确，不因本提案自动公开。

## 建议目录

```text
workspace-onboarding/
  README.md                  # 员工的一段入口提示和最少人工步骤
  AGENTS.md                  # 任意本机 Agent 的执行约定
  bootstrap.ps1              # Windows 原生入口
  bootstrap.sh               # macOS/Linux 原生入口
  scripts/
    windows.ps1
    macos.sh
    linux.sh
  schemas/
    bundle-manifest.schema.json
    report.schema.json
  docs/
    manual-windows.md
    manual-macos.md
    manual-linux.md
    troubleshooting.md
  examples/
    bundle-manifest.example.json
  tests/                     # 无真实凭据的合成测试
  .gitignore
```

README 是员工入口，AGENTS 是执行约定，脚本负责可重复的操作和判断，三份平台文档作为人工补救说明。维护一份 Agent 约定；入口提示显式要求读取它，不假定所有 Agent 都会自动发现同一个专用文件。

第一版使用本机已有的 PowerShell 或 Bash，不要求为接入额外安装 Python、Node 或新的包管理器。脚本的具体兼容范围和平台运行条件必须通过对应真实设备验证。

## Agent 与脚本分工

Agent 负责识别平台、选择仓库动作、解释脱敏结果、恢复可重跑步骤和在必要时把控制交还员工。依赖安装、配置导入、权限设置、连接与诊断由版本固定的脚本执行。

AGENTS.md 的关键内容应包括：

- 用户请求接入后，执行既定范围内的本机准备和验证，不逐条重复询问已经授权的步骤。
- 先读取已有状态；缺少什么才安装什么。同名配置不一致、路由冲突或 SSH 主机身份变化时报告具体冲突，不覆盖用户现有 VPN、SSH 配置或私人网络工具。
- 调用仓库脚本，不自行改写 WireGuard 规则、SSH 身份校验或远端入口限制。
- 私密包作为文件路径传给脚本；脚本在本机读取敏感内容，Agent 使用白名单结果，不将完整配置和凭据放进模型上下文。
- 操作系统认证弹窗由本人完成；个人 Claude 授权时将终端/界面控制交还员工，不读取邮箱、验证码、认证文件或记录该过程。
- 本人完成后只复验认证来源及实际任务结果。未验证的阶段保留 pending，不把工具退出码或 VPN 按钮显示为整体验收成功。
- 只有具备当前步骤所需的文件、终端/PTY 或 GUI 能力才执行；缺少能力时返回具体人工动作及恢复检查，不能假设动作已经发生。
- 不自动把诊断结果、设备包或截图提交为 GitHub issue。需要外发故障材料时先给员工看脱敏内容并取得明确授权。

AGENTS 是给 Agent 的约定；敏感输出的删减、参数校验及配置操作范围由脚本实现，不能只依靠提示词。

## 脚本接口

以下为拟定接口，不是当前已经交付的命令。

| 动作 | 行为 | 输出 |
| --- | --- | --- |
| check | 检查系统、依赖、接入包摘要、现有隧道/SSH 配置与冲突 | 当前状态与待做动作，不安装或改配置 |
| setup | 准备缺少的客户端，将指定设备配置安装到本机私有目录，启用受管隧道 | 变更项目和需要本人操作的位置 |
| verify | 检查握手、固定入口、本人 VM、sudo、CLI/助手和 SFTP 往返 | 每项独立结果及失败代码 |
| connect | 使用本设备身份和预核验主机身份，打开带 PTY 的固定工作会话 | 交互终端 |
| disconnect | 断开本项目维护的连接/隧道 | 完成状态，不清除其他网络配置 |

setup 不把 ZIP 内的任意脚本当作管理员命令运行。执行程序来自固定版本的工具仓库，私密包只提供受校验的数据；WireGuard 自定义执行 hook 及危险 SSH 执行指令不作为设备包允许内容。

每次重跑读取真实系统状态，不以进度文件代替握手和连接检查。涉及提权时调用系统正常授权流程，不收集管理员密码。

## 平台实现边界

| 平台 | 预期自动操作 | 需要交还本人时 |
| --- | --- | --- |
| Windows 10/11 | 检查/安装官方 WireGuard 和 OpenSSH；用官方 tunnel service 接口导入指定隧道；配置设备密钥 ACL；执行验证 | UAC/本机管理员认证 |
| macOS | 复用已安装的受支持客户端/CLI；使用官方客户端时由具备 GUI 能力的 Agent 操作导入与启用；执行验证 | App Store/系统 VPN 许可；Agent 没有 GUI 能力时给出准确的导入/激活步骤 |
| Ubuntu/Debian | 用既有包管理器准备 WireGuard/OpenSSH；以受限文件权限安装指定配置；通过 wg-quick 启用并验证 | 系统 sudo 认证 |

Windows 官方提供 `wireguard /installtunnelservice` 服务接口，见[企业使用文档](https://git.zx2c4.com/wireguard-windows/about/docs/enterprise.md)。Linux 可复用官方[wg-quick 方式](https://www.wireguard.com/quickstart/)。macOS 官方提供 App Store 客户端及 CLI 工具安装选项，见[安装页](https://www.wireguard.com/install/)；第一版不能在未取得本机许可时自动安装新包管理器，或把必要的系统界面许可说成已经完成。

其他 Linux 发行版先明确返回不受支持；不由 Agent 临时拼接未经验证的安装流程。

## 设备包格式与迁移

管理员在现有每设备包中补充一个不含秘密的 manifest，描述包格式版本、设备标识、预期 VM、固定 SSH 入口别名、匹配的工具版本及允许文件。实际 SSH/WireGuard 私钥继续放在私密包里。

包摘要从管理员的既有交付渠道取得。包内 manifest 或包内哈希不能单独充当包本身可信的依据。校验通过后才安装/读取其配置，拒绝归档路径穿越、未知可执行 hook 和不匹配的版本。

新工具将连接代码和说明从设备包移到仓库；包内只保留接入数据。现有手工包保持可用，迁移时由管理员按相同身份和密钥重新打包，不让员工重新登记公钥。

设备包与导入配置保存在 Git 工作目录以外的本机私有目录。源码仓库、Release 附件、Issues、CI 日志和普通诊断报告均不包含这些内容；.gitignore 只是辅助保护。

## 兼容当前受管入口

当前堡垒机只支持固定目标的交互 SSH 和专用 SFTP。自动检查必须通过带 PTY、未附远程命令的交互会话执行，再以明确的测试标记解析结果；不能假设 `ssh entry hostname` 可用。SFTP 使用当前专用入口约定。

Agent 需要把 SSH 身份校验和预期 VM 检查作为实际成功条件，不使用 `StrictHostKeyChecking=no` 或未经核对的 ssh-keyscan。也不引入 SSH 转发、ProxyJump 或直连员工 VM 来适配工具。

个人 Claude 首次授权继续在 VM 内执行 `workspace-login`。本机 Agent 打开会话和该助手后，将控制交还本人；本人确认完成后再执行有限的状态检查。具有 sudo 的员工仍自行管理项目依赖和其他工具。

## 验证与报告

建议报告只保留白名单字段，例如：

```json
{
  "schema_version": 1,
  "platform": "windows",
  "package_verified": true,
  "client_ready": true,
  "tunnel_handshake": "passed",
  "ssh_identity": "passed",
  "assigned_vm": "passed",
  "sftp_roundtrip": "passed",
  "claude_auth": "user_action_required",
  "real_task": "pending"
}
```

这里的内容是格式示例，不是真实验收结果。各项证据应独立：

- 隧道启用后触发一次受控入口请求，再核对最近握手和预期路由。
- 通过受管交互会话核对用户名、VM 主机名、sudo、Claude/登录助手。
- SFTP 用独立随机测试文件往返并校验摘要，不读取员工项目；清理时仅移除本次创建且内容匹配的测试文件。
- 本人完成 OAuth 后核对来源；真实项目任务由员工完成并反馈体验。
- Agent 输出“本机接入已配置”和尚需人工完成的具体事项；所有必要项完成后才报告整体验收通过。

失败代码应稳定，例如 `DEPENDENCY_MISSING`、`NEEDS_VPN_PERMISSION`、`NO_RECENT_HANDSHAKE`、`SSH_HOST_KEY_MISMATCH`、`WORKSPACE_ID_MISMATCH`、`CLAUDE_AUTH_USER_PENDING`。默认不导出原始配置、远端终端全文或浏览器截图。

## 第一版交付和验收

第一版交付 README/AGENTS、上述五种本机动作、三平台适配、设备包 manifest、手工补救文档、合成测试和脱敏结果格式。继续复用管理员预配设备身份及服务端 workspace-login。

GitHub CI 只运行无凭据语法/格式/合成测试，不放公司 VPN 或员工 OAuth 凭据，也不把公共 CI runner 连入家庭环境。实际 Windows、macOS、Linux 的提权、VPN 导入/握手、受管会话、SFTP 和个人授权仍在对应获准设备验收，未测平台不标通过。

发布时固定工具版本，并记录兼容的设备包版本。员工取得升级时先比对状态，保留有效身份，不因升级删除个人密钥或替换已有客户端配置。

## 与现有交付的衔接

[现有管理员实施说明](../guides/employee-claude-workspace.md)继续负责服务端；员工三份逐步文档在新仓库落地后转为人工补救文档，由新仓库维护一份权威版本，IaC 通过链接和发布版本引用它们，避免两套指引持续漂移。

下一步实施前需要明确远端仓库归属、名称和可见性；客户端范围沿用Windows、macOS和Ubuntu/Debian。当前只是可审阅的设计，不更改现有路由器、网关、VM配置或个人账号，也不自动创建/推送GitHub仓库。


## 2026-10-22 登录交互实测修正

已收到本人实际使用反馈：Browsh出现空白正文且无法输入。匿名复现发现错位/隐藏导航混入/翻页空白，当前未通过真实表单输入验收。自动URL交付和会话管理的机械验证不等于登录表单可用，因此在授权入口方案完成并实测前，接入Agent只能报告网络接入结果和个人授权待完成，不能将workspace-login开页视为Claude可用。

调整建议见[个人授权入口变更提案](./employee-workspace-browser-auth-change.md)，用户已明确批准仅本人授权期间的图形窗口，已开始部署；实际授权浏览器仍在澳洲VM，本机浏览器仅作WireGuard内远端画面查看器。独立GitHub接入仓库继续是设计草案，尚未创建。

### 已批准的浏览器能力追加

2026-10-22 用户已同意独立日常 VM 浏览器，服务端新增 workspace-browser start/status/open/stop，Claude 登录自动复用。客户端 Agent 可以引导员工在远端启动并在本机打开私网查看地址；网页／SSH 关闭不等于停止 VM 浏览器，需要显式 stop。个人账号登录和敏感页面由本人操作；Agent 不读取或截图个人会话。独立 GitHub 接入仓库仍为设计草案，尚未创建或发布。

## 当前批准与交付范围（2026-10-22）

用户要求做完 bootstrap GitHub 项目，选择 blue126/workspace-onboarding 私有，并明确要求设备包及实际接入配置单内置。独立项目已实现 README/AGENTS、Bash/PowerShell 原生入口、check/setup/verify/connect/sftp/disconnect、严格数据包 schema、三平台文档和合成测试；workspace-login 与日常 workspace-browser 入口均保留。

当前项目只含 ed-pilot-client 原身份，未轮换密钥，没有其他员工、control 或管理员身份。ZIP 未另行加密，GitHub 仓库读取权限等同于使用该公司设备身份的权限，只能授权本人及管理员。此为用户明确批准的私有交付例外，不适用于个人 OAuth、Vault 或跨员工共享。员工以后各用新建专属私有仓库及本人包，不复制此仓库的密钥历史。

员工默认读取项目内 deployment/device-bundle.zip、摘要与实际配置单，无需另找私密文件或生成公钥。CI sparse checkout 排除 deployment，只用合成身份，不连接家庭环境。发布仅在新项目发生，IaC 现有修改仍未提交或推送。

## 首版最终验证

发布提交 ca2ce71a1e618e1c4f3167b4cae831ed69dce01d，工具 1.0.0。[最终 CI](https://github.com/blue126/workspace-onboarding/actions/runs/39737559348) 三个原生 OS job 全部 success；Windows job 同时通过 PS7 与系统 PS5.1。Linux 17 项合成测试；macOS 执行适用的 13 项、跳过 Linux 专属 4 项；Windows 每个 PowerShell 版本执行包校验／导入等适用 8 项、跳过 Unix 专属 9 项。稀疏 checkout 已核对无真实设备包；CI 不访问公司环境。

管理员 Mac 对内置实际包执行只读 check，package_verified/client_ready 均 true；没有在该 Mac 导入或激活目标设备 VPN。系统提权、VPN 客户端真实接入、本人 OAuth 与真实项目依然由分配设备的本人验收，不能把 CI 当作对应设备已配置。独立仓库工作区干净；IaC 的本轮及此前部署改动仍未提交／推送。

## 申请、审批与自动发放追加（2026-10-22）

用户新增要求：员工申请后由管理员批准，CD 自动创建独立环境并发放专属接入项目。客户端首版已经发布，此端到端流程尚未实现。具体方案及现有流水线缺口见 [自动开户方案](./employee-workspace-self-service.md)。

### 员工不需要 GitHub 账号（2026-10-22）

用户已明确员工希望无需 GitHub 账号申请。后续自动开户采用网页申请、管理员一次批准、CD 构建每设备完整项目 ZIP、邮箱验证后私密领取；员工无需注册 GitHub、取得仓库权限或安装 Git。当前已发布的 pilot 私有仓库继续保留，GitHub 用于后台代码维护。门户/邮箱验证/私密领取尚未实现；这是自动开户方案的最新要求，取代后续员工必须取得专属私有 GitHub 仓库权限的设计。详见[自动开户方案](./employee-workspace-self-service.md)。

### 自动开户暂缓实施（2026-10-22）

用户决定保留网页申请、审批和 CD 自动发放方案，计划下周再实施；前期工作量较小，当前继续手动开户及私密交付每设备完整项目。每员工独立 VM、每设备独立身份和现有 bootstrap 能力继续沿用。本记录不安排定时任务或自动部署。
