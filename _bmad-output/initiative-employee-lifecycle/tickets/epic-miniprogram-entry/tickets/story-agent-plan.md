---
title: '接入指引重写与交付邮件改版'
type: 'feature'
ticket: '22'
created: '2026-11-02'
status: 'done'
baseline_revision: 'workspace-onboarding 73357d7; employee-admin 4d06ca9fe8e7d3d0a1322bbe15cd2d87b51fdbc2'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: ''
review_source: ''
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** workspace-onboarding 的 README、AGENTS.md 与 docs 混着试点期、桌面/noVNC、旧网关、v1 入口等旧说法，员工的 Agent 读不出一条清晰流程；交付邮件只有一段长提示词与注意事项，没有问候、预期说明，也没有提到 `mosh <员工ID>-vm`。

**Approach:** 把 workspace-onboarding 收敛为一份 README 作为唯一的 Agent 引导（删除 AGENTS.md），流程为：收邮件 → 下载并校验设备包 → setup → `mosh <员工ID>-vm`；交付/重发邮件改为有排版的三段：问候与感谢、预期说明、一句话让 Agent 按 GitHub README 完成接入。

**Decision (2026-11-02 用户):** 提示词与脚本留在 GitHub（让员工看到全貌）；删除 AGENTS.md，README 为唯一说明；邮件三段：①问候并感谢 ②预期说明——个人项目、费用只覆盖电费、只提供 VM、需要用户自己会配置 VM、不承诺可用性、没有客服团队（只有管理员一人维护）、不负责任何与 Claude 账号有关的事情（注册、订阅、登录、账号受限等由用户自行处理）、有问题发邮件到 hello@willfan.me、best effort 支持（与申请页条款同一文案；只出现在邮件与申请页，README 只负责帮用户完成接入，不放预期说明）③一句话让 Agent 帮用户完成接入；发信已统一经网站 /admin/mail（5.21）。

**Decision (2026-11-03 用户, 邮件只给起点与终点):** 邮件中提示词之后紧接一句"接入完成后，在终端运行 mosh {员工ID}-vm 即可登录。"，两者之间不放任何其他内容（不提网站下载、不提有效期、不提链接）；中间过程全部由 Agent 依 README 引导用户。

**Decision (2026-11-03 用户, 下载方式 A):** 邮件不放下载链接与 SHA256；Agent 读完 README 后引导用户登录 cc.willfan.me「我的工作区」自行下载设备接入包（登录用邮箱验证码），并问清文件位置（默认 ~/Downloads），用页面显示的 SHA256 校验后继续；Agent 必须向用户强调设备包的下载有效期（以页面显示为准，过期需邮件联系管理员重发），并强调妥善保管私钥（包内含 WireGuard 与 SSH 私钥：不要转发、上传、提交到仓库或贴进聊天；Agent 自身不得输出私钥内容）。网站「我的工作区」设备包卡片已显示 SHA256（apply-site 本次提交）。下一条 Decision 中"邮件单独列出下载链接与 SHA256"一句被本条取代。

**Decision (2026-11-03 用户, 提示词与 README 分工):** 邮件中给 Agent 的提示词只有一句话，只引导到 GitHub 项目（如"请阅读 https://github.com/blue126/workspace-onboarding 的 README.md，帮我完成 RemoteCC 工作区接入"），不含下载链接、SHA256 或步骤；README 全部面向 Agent，写明：先向用户索取邮件中的下载链接与外层 ZIP SHA256、两步验证码下载（需要时向用户索取 6 位验证码）、校验、setup、遇到系统授权交给用户、完成后告诉用户 `mosh <员工ID>-vm`。邮件在一句话之外单独列出下载链接与 SHA256 供用户复制给 Agent。

**Decision (2026-11-02 用户, Claude 登录):** 保持现有规定——不在本机浏览器打开 Claude 授权链接、不在本机登录个人 Claude；在 VM 内用 `workspace-login` 于 VM 浏览器完成；终端 VM 没有可达的 VM 浏览器入口时，先发邮件联系管理员开通。

## Boundaries & Constraints

**Always:** 先发布 GitHub 文档，再部署引用它的邮件；邮件只用内联样式与系统字体，颜色取 design/tokens.json 浅色；保留下载流程原样（两步 POST 验证码、外层 ZIP SHA256、3 天 3 次）；Windows 经 WSL 的路径保留；预期说明文案来自 design/text.json 的单一来源；附纯文本部分。

**Never:** 不改 bootstrap 行为与设备包格式（除下方 mosh 安装外）；不改下载接口；不在 GitHub 放任何员工数据；不在进行中的开户/交付计划期间部署模板变更（会使其摘要失效）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 新员工交付 | provision/deliver | 邮件：问候 → 预期说明 → 给 Agent 的一句话（README 链接 + 下载链接 + SHA256）→ 有效期与联系方式 | — |
| 重发 | reissue | 同一模板，主题"已重新发送" | — |
| 地址迁移 | purpose=migration | 同一模板 + 接入更新提示条 | — |
| Agent 照 README 执行 | macOS/Linux | 下载→校验→`setup --install-clients`（含 mosh）→`verify`→告诉用户 `mosh <id>-vm` | 失败按 troubleshooting 停下 |
| Windows | PowerShell | README 指向 WSL 小节 | — |

</frozen-after-approval>

## Code Map

workspace-onboarding：`/Users/weierfu/Projects/workspace-onboarding-alias`，新分支 `claude/onboarding-rewrite`（基于 origin/main 73357d7）。实现代理只改两个仓库的代码、测试、文档，不 commit/push，不部署。

- `README.md` -- 重写为单一流程（面向 Agent 与员工），吸收 AGENTS.md 规则 1-10（三文件校验、不展开密钥、授权交给用户、失败即停）。
- `AGENTS.md` -- 删除。
- `docs/download.md`、`docs/verification.md`、`docs/system-authorization.md`、`docs/troubleshooting.md` -- 保留，删去旧网关/noVNC/试用句子。
- `docs/mosh.md` -- 只保留 OCI Hub 终端与 `<id>-vm`、WSL 小节。
- `docs/oci-hub.md`、`docs/after-verify.md`、`docs/manual-*.md` -- 删除或并入 README（after-verify 的三条禁止项并入 README）；`docs/administrator.md` 保留。
- `scripts/unix.sh:83-87,233` -- `--install-clients` 增加 mosh（brew/apt），使 Agent 无需另装；`tests/test_bootstrap.py` 覆盖。
- 测试不读 docs；CI 为两份测试 + `bash -n` + shellcheck + ps1 parse。

employee-admin：`/Users/weierfu/Projects/IaC/remotecc/employee-admin`，新分支 `claude/mail-redesign`（基于 main 4d06ca9）；设计仓库 `/Users/weierfu/Projects/IaC/remotecc/design`（`text.json`）。

- `templates/onboarding.html` -- 重写为三段式外壳（Remote/CC 标题、问候、预期说明、给 Agent 的一句话放在第一个 `<blockquote>`、有效期/SHA256/联系方式列表 `<ul>`）；`deliver-temp.py:270-295` `message()` 保持占位符与 `<ul>` 插入点。
- `templates/expiry-reminder.html` -- 同一外壳与语气。
- `deliver-temp.py:298-307` `mail_subject` -- 默认主题改为"欢迎使用 RemoteCC：你的工作区已准备好"。
- `deliver-temp.py` `send_mail` -- 由 HTML 派生纯文本作为 `text`（不改被哈希的信封）。
- 预期说明文案：`remotecc/design/text.json` 新增 `expectations` 块（5.20 申请页条款也将引用）；邮件模板以占位符注入。
- 测试：`test-temp-delivery.py:32-34,90-118,146,159-165,257-292`、`test-oci-hub.py:693-696,753-762,823-829`、`test-hub-remind.py:61-62` 按新文案更新（保留下载 curl 字符串与"3 天内有效、最多下载 3 次"）。
- 不动：`mosh-trial.html`、`mosh-hub-trial.html`（试用分支），`admin-summary.html`。
- `hub-onboard.py:119` 的 source_hash 含 onboarding.html：部署前确认执行器无进行中的开户计划。

## Tasks & Acceptance

**Execution:**
- [ ] workspace-onboarding：README 重写、删 AGENTS.md 与过时 docs、`--install-clients` 加 mosh + 测试
- [ ] design/text.json：`expectations` 文案
- [ ] employee-admin：模板、主题、纯文本、测试
- [ ] 授权后：workspace-onboarding PR 合并 → 渲染一封预览邮件给用户确认 → 推执行器

**Acceptance Criteria:**
- Given 一台干净的 macOS，when Agent 只读 README 并拿到邮件中的一句话，then 能完成下载、校验、setup 并告诉用户 `mosh <id>-vm`。
- Given 交付邮件，when 在常见客户端（Gmail、iCloud、QQ 邮箱）打开，then 排版正常、三段齐全，纯文本版可读。
- Given 仓库，when 搜索 noVNC、试用、v1 入口、旧网关，then 面向员工的文档中不再出现。

## Implementation Notes

## Plan Change Log

## Review Triage Log

## Verification

**Commands:**
- workspace-onboarding：`python3 -m unittest tests/test_bootstrap.py tests/test_verify_session.py`；`bash -n scripts/unix.sh`；shellcheck -- 通过
- employee-admin：`python3 test-temp-delivery.py`、`test-oci-hub.py`、`test-hub-remind.py` -- 通过

**Manual checks:**
- 渲染 onboarding.html 预览（HTML 与纯文本）交用户确认后再部署。
