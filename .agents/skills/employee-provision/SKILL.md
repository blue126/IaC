---
name: employee-provision
description: "本 IaC 项目的员工工作区开户/provisioning、员工 VM 创建、设备接入包生成与交付、恢复及开户流程维护。自动复用私有管理员入口；不用于一般基础设施 VM 或员工电脑 bootstrap。"
---

# 员工工作区 Provisioning

本 skill 仅在所属 IaC 项目内按上下文自动加载，不作为用户级全局 skill 安装。

规范入口是 IaC 主 checkout 的 `remotecc/employee-admin/onboard.sh`。管理员源码属于该目录的独立私有 Git；相邻 `remotecc/employee-data/` 保存实际配置、申请、状态、设备包和回执，不进入任一源码仓库。公开 IaC 只存项目 skill 与基础设施定义；公开 workspace-onboarding 只承载员工客户端。不要复制管理员源码或私有数据到这两个公开仓库。

先检查当前 checkout 的 `remotecc/employee-admin/`。若临时 worktree 中不存在，用 `git worktree list --porcelain` 定位同一 IaC 仓库已有的主 checkout，查找其规范目录；不要在临时 worktree 创建第二份管理员仓库或运行数据。定位后将代码目录记为 `ADMIN_ROOT`、相邻数据目录记为 `DATA_ROOT`。旧 `~/Projects/employee-workspace-admin` 仅是兼容链接。

先读取 `$ADMIN_ROOT/README.md`。需要恢复、迁移或处理交付故障时，再读 [运行与恢复](references/operations.md)。不要重新实现 Terraform/Ansible 编排。

## 自动识别与既有入口

- 员工工作区开户/provisioning、设备包生成与交付、恢复，以及相关流程的修改或审阅，都应自动加载本 skill；一般基础设施 VM 操作、员工电脑 bootstrap 不属于此范围。
- 先读取私有管理员项目 README 与现有入口。沿用 `onboard.sh` 的输入、审批、身份复用和交付契约；新增 profile 应扩展已有流程，不另造独立开户引擎。
- 区分工程讨论与实际操作：讨论、设计、代码修改或审阅时只加载既有运行约定，不自动执行 preflight、读取真实凭据或为员工开户。用户要求实际操作时，再按下文执行。
- 已显式选择 BMad 等工作流时，保留其顺序与检查点，本 skill 提供员工 provisioning 的现有入口和技术约束。
- 自动加载不代表授权 apply、轮换凭据、上传、发信或 Git 操作；继续遵守本次会话的具体授权。后端尚未接通既有输入契约时，报告具体缺口，不能用临时旁路替代。

## 输入与已有决定

- 用户默认只提供邮箱。把仅含 `recipient` 的申请保存到 `$DATA_ROOT/requests/`；工具将邮箱 `@` 前的用户名同时作为 employee_id 和默认 device_id；若用户名全部为数字，只在这种情况下加 `user` 前缀（例如 123456@example.com → user123456），其他合法用户名不加 ed- 等前缀，不要求用户重复填写 ID。已有登记保留原 ID，内部旧三字段申请继续兼容。名字不符合系统账号格式或与别的邮箱/系统账号碰撞时，说明具体冲突，不擅自改名或合并身份。
- 先核对已有申请和登记：同一员工复用本人 VM，同一设备复用原身份；新设备分配独立身份和地址。不要再次泛问“新员工还是新设备”，不要为重跑轮换密钥。
- 新交付只用 Temp.sh；微软账号只用于 Mail.Send，不使用 OneDrive。首次发信前通过 onboard.sh login 完成管理员邮件授权，不要求员工注册账号。
- 员工设备和网关接入私钥保存在独立的 Bitwarden Secrets Manager `EmployeeWorkspace` 项目：每台设备一条 Secret，网关 WireGuard 私钥另有一条；旧汇总 Secret 已退役。仅访问该项目的 `employee-workspace-admin` 机器账号负责读取和写入。BWS 令牌位于私有数据目录（代码目录保留兼容链接），只在管理员执行端与批准的部署 Sandbox 使用；不得打印、发送或放入公开仓库。全局 IaC Vault 不再存放员工密钥；员工 Ansible 运行时由 `onboard.sh` 临时合成加密 Vault。
- 默认沿用已配置的独立 pve2、CPU host、已发布的干净预装模板，以及员工 sudo 权限。隔离由网关和 PVE 侧执行，不通过员工 sudo 黑名单实现。
- 员工不需要 GitHub 账号；个人 Claude 登录由员工在本人 VM 内完成，不进入模板、计划或设备包。

## 执行

以下步骤针对既有 `existing` 流程。新 `oci-hub` 使用同一入口的 `--profile oci-hub` 分派，并先读取本项目 `docs/deployment/oci-hub-workspace-prototype.md`；其分配、登记和候选包输入仍需预配置。不得将缺少配置的新方案静默落入 existing，或借用原 BWS 项目与设备身份。

1. 读取 settings.json，确认它绑定的 IaC 工作树存在且属于本次任务。检查 `python3 "$ADMIN_ROOT/bws-store.py" check` 能读取专用项目；失败就停止，不改用旧 Vault 或生成新身份。所有 Terraform/Ansible 操作均由私有 `onboard.sh` 送入已配置的 Docker Sandbox；不在宿主机安装它们，不自动扩大网络权限。
2. 对指定申请运行 `bash "$ADMIN_ROOT/onboard.sh" preflight REQUEST.yml`，再运行 `plan REQUEST.yml`。仅展示目标 VM/模板、资源变更、设备归属、接收邮箱和精确计划 SHA；不打印候选私钥或完整 plan。
3. 没有当前有效授权时，请管理员批准该精确计划，以及上传设备包到 Temp.sh 并向指定邮箱发送微软通知邮件的动作。已有本次精确计划及这些动作的授权时直接继续，不重复询问。源码、配置或计划变化后重新 plan。
4. 运行 `apply REQUEST.yml APPROVAL_SHA256`。它负责 Terraform 资源创建、Ansible 隔离与环境配置、导出、Temp.sh 上传校验和微软邮件通知。不得跳过审批散列、用全量 apply 代替目标计划，或靠 CLI 临时绕过失败的 playbook。
5. 检查点更新会自动刷新私有 WORKSPACES.md 和 workspace-registry.json；也可运行 onboard.sh registry。台账由分配、设备和已注册请求生成，邮箱不明不猜测，state/workspace-notes.json 记录管理员用途；VM502/control 是管理员本人保留测试机，不作为清理目标。
6. 根据真实检查点确认交付：VM 服务验证、包哈希、Temp.sh HTTP POST 下载与外层哈希、通知 API 接受；三天保存期只是 Temp.sh 服务政策，不声称验证了精确到期时间。给出实际链接、外层 SHA256 和员工一句话提示词；收件和本机 bootstrap 属于员工验收，不把 API 成功说成收件或个人 Claude 登录成功。

## 正式邮件格式

沿用私有项目 deliver-temp.py 的实际 HTML 模板和 email-template.txt 说明，保持以下已批准格式：

- 把“复制下面整句话给你的 Agent”及完整提示词放在邮件最上方、最显眼的位置；提示词用中文引号“……”包住，整句加粗并放入醒目的引用框。发送前填入实际 Temp.sh 链接，不留占位词。
- 其余信息使用 bullet points：接入包链接、三天保存政策、外层 ZIP SHA256、本机系统授权、VM 内 Claude 登录与禁止事项。不要改回连续的大段文字。
- 明确让员工 Agent 配置本机，由员工本人确认安装、管理员密码及系统弹窗；随后通过 SSH 进入个人 VM，运行 workspace-login，在 VM 的 Firefox 内完成 Claude 登录。
- 将“不要在本地电脑登录或使用个人 Claude 账号，也不要用本地浏览器直接打开 Claude 授权链接”加粗；同时说明本地浏览器可以显示 VM 远程桌面。
- 仅修改模板不会自动重发历史邮件；测试警示仅用于明确获准的测试邮件，不进入正式开户邮件。

## 重跑与停止

- 同一请求先运行 `verify REQUEST.yml` 读取本地检查点；它不是实时 VM/网络验收。已完成的同设备交付复用原包，必要时 `export REQUEST.yml`，不要重新开户或重复发邮件。
- 历史 OneDrive 回执和凭据只保留，不再用于新交付；不自动迁移或给旧员工重发。链接过期需另行批准重新交付，复用原包，不重建 VM。
- 遇到状态同步失败先 `recover`；遇到 uploading/notifying 等结果不明的通知停止核对，不盲目重发，不用网页补救冒充自动化完成。
- 当前任务未授权的生产变更、邮件、提交和推送仍须取得相应授权。创建或安装本 skill 不代表已批准某个员工开户。

员工提示词保持：请按 https://github.com/blue126/workspace-onboarding 的指引，用 HTTP POST 从“实际下载链接”下载本设备接入包，仅解开外层 ZIP 并完成 bootstrap；需要系统授权或个人 Claude 登录时交给我。发送时把实际链接填好。
