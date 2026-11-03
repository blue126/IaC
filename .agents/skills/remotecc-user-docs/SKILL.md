---
name: remotecc-user-docs
description: "编写、更新或评审 RemoteCC 员工网站（cc.willfan.me）/docs 板块的用户文档：上手教程、操作指南、参考、原理说明和常见问题。读者是员工，不是管理员。不用于管理员手册、IaC 技术文档、学习笔记或开户操作本身。"
---

# RemoteCC 用户文档

为 `cc.willfan.me/docs` 写面向员工的文档。读者会 Linux 基本操作，没有任何内部背景，通常是遇到问题才来看。每页只回答一类问题，读完能做成一件事或弄懂一件事。

加载本 skill 不代表授权修改 Worker、部署、提交或推送；这些边界按仓库 AGENTS.md 另行确认。

## 工作流程

1. **定位页面**：在[信息架构](references/information-architecture.md)里找到目标页及其 Diátaxis 类型。新增页先更新信息架构，说明它和现有页的区别；不能归入单一类型的内容要拆开。
2. **收集事实**：按下面的事实来源逐条核对，草稿里每条行为性事实（数值、时限、按钮名、命令、步骤顺序）都要能指回来源。来源冲突或查不到时停下来报告，不猜。
3. **按模板起草**：用[页面模板](references/page-templates.md)中对应类型的结构；术语与 `design/text.json` 一致。
4. **安全检查**：逐条过下面的“绝不出现”清单。
5. **读者测试**：按[读者测试](references/reader-test.md)执行，修完发现的缺口再交付。
6. **交付**：页面写在 `remotecc/docs/content/<分组>/<slug>.md`（分组见信息架构）；在 `remotecc/docs` 运行 `hugo --gc`，除 LibSass 弃用警告外不得有其他 WARN 或 ERROR。写文档不改 Worker。给出改动文件、每条事实的来源清单、读者测试结果和未解决的问题。

## 事实来源（优先级从高到低）

1. `remotecc/apply-site/worker.js`：网站实际行为，包括路由、登录时效、下载规则、错误码。
2. `remotecc/design/text.json`：员工在页面上看到的原文，按钮名和提示语以此为准。
3. `remotecc/employee-admin/docs/admin-handbook.md` 与 `wsctl` README：开户、续期、设备、流量额度的后台规则。只取员工可感知的结果，不搬运管理员操作。
4. 公开仓库 [workspace-onboarding](https://github.com/blue126/workspace-onboarding)：员工电脑上 AI 助手实际执行的接入步骤。
5. IaC `docs/guides/employee-*.md`：可能停留在旧流程（例如手工导入 WireGuard），只作背景，事实必须回到 1–4 核实。

`remotecc/` 在主 checkout 中被 Git 忽略；在临时 worktree 里用 `git worktree list --porcelain` 定位主 checkout 读取，不复制。

## 绝不出现

- 任何凭据或其片段：私钥、令牌、密码、验证码样例以外的真实码、证书指纹真实值、SHA256 真实值。
- 员工个人数据：真实邮箱、姓名、员工 ID、主机名、分配的 IP。统一用示例值：员工 ID `alice`、主机名 `alice-vm`、邮箱 `you@example.com`，第一次出现时注明“示例，以「我的工作区」显示为准”。
- 管理员侧细节：执行器、Semaphore、BWS、`wsctl`、Portal、`/admin/*` 路由、内网管理地址、Terraform/Ansible。员工需要知道的只是“联系管理员”。
- 让员工在本机浏览器打开 Claude 授权链接、在本机登录个人 Claude 账号，或绕过 VPN 的做法。
- 未上线的功能（例如小程序）和已撤回的方案。

以上规则同样适用于截图、终端输出、日志、HTML 注释和附件。配图只用示例账号（`alice`、`alice-vm`、`you@example.com`）的页面和终端截取，不截真实员工的「我的工作区」；接入时得到的桌面地址和证书指纹只说“以接入时给出的为准”，不写具体值。

## 写作规则

- 中文，第二人称“你”，短句。一个步骤只做一个动作，动作在前、结果在后。
- 界面元素用页面原文并加引号，例如点击「下载设备接入包」。
- 命令放代码块，个人值用上面的示例值，不用 `<...>` 占位符（复制进 shell 会被当成重定向）；同时给出预期输出或成功标志。
- 站内链接写完整分组路径并以斜杠结尾，例如 `/docs/reference/troubleshooting/`。
- 警告只放在会出错的那一步前面，不集中堆在开头。
- 页面之间链接而不重复：教程链接到操作指南，操作指南链接到参考。
- 时限、额度等数值只在参考页写全，其他页面引用参考页，避免改一处漏一处。
