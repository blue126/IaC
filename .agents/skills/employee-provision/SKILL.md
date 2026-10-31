---
name: employee-provision
description: "本 IaC 项目的员工工作区开户/provisioning、员工 VM 创建、设备接入包生成与交付、恢复及开户流程维护。自动复用私有管理员入口；不用于一般基础设施 VM 或员工电脑 bootstrap。"
---

# 员工工作区 Provisioning

本 skill 仅在所属 IaC 项目内自动匹配员工开户、新设备、设备包交付和相关流程维护；不用于一般基础设施 VM 或员工电脑 bootstrap。讨论和代码审阅只加载上下文，不自动读取凭据或执行真实操作。显式 BMad 工作流保持原有顺序。

## 规范入口和边界

复用主 checkout 的 `remotecc/employee-admin/onboard.sh`，先读其 README。临时 worktree 中没有该目录时，用 `git worktree list --porcelain` 定位同一仓库的主 checkout，不创建第二份管理员工程。源码属于独立私有 Git；相邻 `employee-data` 保存配置、申请、状态、设备包和回执，不进入源码 Git。旧 `~/Projects/employee-workspace-admin` 只是兼容链接。公开 IaC 保存基础设施和本 skill；公开 workspace-onboarding 保存员工客户端，均不存放私有包或管理员源码。

活动操作固定使用 `onboard.sh --profile oci-hub`。一般从管理员宿主调用，由既有桥接在配置的 Sandbox 中运行；实际工作树、凭据和管理网络按仓库 AGENTS.md 核对。TUI 占用可令 sbx exec 挂起；网络未放行或依赖缺失时停止并取得相应授权，不换路绕过。API/同步失败不是员工离线。

加载 skill 不代表授权 apply、安装包、改网络、写凭据、上传、发信或 Git 操作。审批按具体计划和阶段执行，已有明确授权不重复询问。后端缺少某步骤时报告缺口，不另建开户引擎或使用临时旁路。

## 输入和身份

- 默认只需要邮箱，用 `provision --email EMAIL` 生成合法 JSON 申请和计划；不要手写缺 profile 的 recipient-only 请求。邮箱 @ 前部分作为默认员工/设备 ID，仅全数字时加 `user`，其余不加 ed-。已有登记保留原 ID；非法名字或碰撞明确报错，不猜新名字。
- 同员工复用 VM，同设备复用身份和密钥。明确新增电脑时传 `--device NEWID`；同邮箱对应多个工作区时用 `--employee-id ID` 指定已有归属。已知上下文不要重复询问；无法判断是否新增设备时只澄清必要的设备信息。
- 新 VM 可选 `--cores N --memory-mib N --disk-gib N`；默认规格取现有资源池（当前2核 host、8GiB、50GiB、pve2）。已有 VM 规格不同会拒绝隐式调整，改规格另做精确计划，不重新开户。
- 新方案凭据使用独立 BWS 项目 EmployeeWorkspace-OCIHub 和专用机器账号，按接口/用户/工作区/设备角色保存；旧 EmployeeWorkspace 仅保留历史。项目绑定以受保护配置为准，不硬编码旧机器账号名。SSH 私钥/BWS 令牌不放 OCI、公开源码或聊天；批准操作物化临时加密 Vault，退出清理。

## 从申请到交付

1. `onboard.sh --profile oci-hub provision --email EMAIL` 输出请求路径、资源范围及审批 SHA。核对对象、规格、安装及网络范围，批准后执行 `apply REQUEST.json SHA256`。
2. 已完成设备返回 already_configured（或 configured_blocked），不需要apply，按提示查询/导出；不能将blocked状态当成已恢复。相同输入且依赖未变的未完成计划复用原审批。未执行计划失效时重新 plan 并取得新 SHA；部分执行须复用原资源及检查点；其他已开始的请求存在时，先按错误返回的run_dir恢复其原请求，不交错推进登记generation。归属不明、外部策略变更或凭据缺失时停止，不能换 ID、轮换密钥或删除记录来恢复。见 [运行与恢复](references/operations.md)。
3. apply 的 `configured` 表示服务配置阶段完成；继续看嵌套 bundle/verification 状态。用 `registry` / `verify` 查询服务端状态，用 `online` 额外观察连接；握手或监听不等于真人操作或员工 bootstrap 已完成。
4. `onboard.sh --profile oci-hub export --device DEVICE_ID` 复用原身份导出。输出的 `delivery_request` 是交付草稿，含绑定收件人、Sandbox 包目录与回执目录；不包含上传/发送授权。
5. 验收未完成时，用 `acceptance ACCEPTANCE.json` 获取绑定包和身份的检查清单、pending 模板及现有记录校验结果。独立验收必须来自另行批准的验证与证据，模板和服务检查不算通过。已有特定设备的受保护豁免保留，结果为 acceptance_waived；新设备须独立验收或单独获准豁免，不能推广历史豁免或虚构检查通过。
6. 交付按两阶段进行：`notify:false` 的 JSON 经 plan/批准后上传并校验；再改 `notify:true` 重新 plan，展示收件人、主题和实际 `host_mail_preview`，单独批准后发送。`purpose` 明确为 onboarding、trial 或 migration；Mosh 不等于试点。具体 JSON 与命令见[原生开户](../../../docs/deployment/oci-hub-native-provisioning.md)。
7. Temp.sh 目前是默认上传通道，微软 Mail.Send 是通知通道，不用 OneDrive。HTTP5xx、时间到期和下载次数限制分别报告；三天只是服务政策估计。结果不明时不重传、不重发。渠道故障时保留原包和身份，请用户决定；单次获准附件补发不代表后续默认授权，不自行更换平台。

## 完成条件与员工交接

依次区分：计划已生成、服务已配置、已独立验收/获准豁免可交付、上传已校验、邮件API202接受、员工确认bootstrap、本人在VM内完成Claude认证。管理员 verify、online 或邮件API202均不代表员工已收到或可实际工作。缺某阶段就报告该阶段待办，不统称“全部完成”。

正式邮件把“复制下面整句话给你的 Agent”放最上方，完整提示词用中文引号包住并加粗；正文用 bullet points，包含真实链接或本次明确批准的附件、SHA256、包归属及授权交接。迁移邮件明确使用新包替换旧接入，不只修改 Endpoint；正式开户不带测试/跳过登录/旧包回退指令，trial 才使用试点模板。

让员工 Agent 配置电脑、通过 SSH 进入本人 VM；安装确认、管理员密码和系统弹窗由员工本人完成。个人 Claude 登录在本人 VM 内运行 workspace-login、使用 VM 的 Firefox 完成。**不要在本地电脑登录或使用个人 Claude 账号，不要用本机浏览器直接打开 Claude 授权链接。** 本机浏览器可以显示 VM 远程桌面。终端包没有桌面链接时先确认另行配置的 VM 浏览器入口；缺少入口就报告等待管理员提供，不用本机认证替代。

## 状态、恢复与源码收尾

Portal 的 Disabled/DisabledReason 是接入启停权威；SQLite 保存每用户5GB双向月用量、额度、采样和审计，不恢复旧 reasons 镜像。触额仍阻断，增额/跨月仅清配额原因；普通计数重置不自动封禁。不要在调试结束时擅自停用用户要求保持启用的设备。

`onboard.sh recover` 只用于旧共享授权/历史登记同步日志，不是 Hub 恢复命令。Hub 按原 JSON 重新 plan/apply，使用固定动作和独立检查点；错误码和安全停止规则见 [运行与恢复](references/operations.md)。源码/范围变化使旧审批失效，不能强行重放旧二进制计划。

开户会修改受 Git 跟踪的 VM roster。收尾必须展示这些定义与文档的差异，另行取得提交、PR、合并授权，使源码与共享 state 保持一致；未获授权时明确标记“Git待收尾”，不自动提交、不归档仍被配置引用的工作树。运行数据、私钥、包和真实回执留在 employee-data。

VM500 已退出员工路径，作为 HAPI 控制面保留。VM501为demo、VM502为本人测试；旧 employee-access role及专用入口退役，历史槽位/凭据/VM503保护保留。跨员工隔离由OCI Hub与PVE承担。不要恢复旧网关或改动其他业务。
