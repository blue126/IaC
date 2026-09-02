---
title: 'Technical research: OpenCode remote worktree support'
type: 'technical'
topic: 'OpenCode remote worktree support'
decision: 'Determine whether remote OpenCode Server worktree workflows are natively supported, require a plugin, or should be deferred.'
source: 'native web research'
status: complete
preset: 'quick'
validation: 'normal'
created: '2026-08-25'
updated: '2026-08-25'
claims_verified: 4
claims_unverified: 0
---

# Technical research: OpenCode remote worktree support

**Decision this research serves:** Determine whether remote OpenCode Server worktree workflows are natively supported, require a plugin, or should be deferred.

## Executive Summary

**结论：当前 OpenCode 1.18.21 已有原生 worktree/workspace 支持，远程 Server 场景不以插件为前提。** 它仍是实验功能，默认关闭，产品入口也不一致：Beta Desktop 有 workspace selector，TUI 有隐藏的 `/workspaces` 和 `/warp`，Server 有 `/experimental/workspace` 与 `/experimental/worktree` HTTP API；正式版 Desktop 则根据构建渠道隐藏新会话 workspace selector。[2][3][4][5][6][11][12]

从协议层面看，Beta Desktop 也并非只能连接本地 sidecar。1.18.21 的设置页提供 Servers 管理功能，以及任意 HTTP URL、用户名和密码的输入字段；官方 troubleshooting 文档也明确说明 Desktop 可连接配置的 Server URL。[1][10] 如果某个 Beta 安装包中看不到该入口，更可能是入口位置、布局或该构建出现回归，不能据此推导远程连接能力不存在。

插件可以添加 hooks、tools，并通过 1.18.21 的 TUI plugin API 注册 route、JSX UI、dialog、prompt 和 slot；但公开接口没有 Desktop 组件、菜单或路由注入能力。因此插件能够包装 `git worktree` 或原生 API、甚至构建 TUI 工作流，却不能作为受支持的方法把缺失的 Desktop workspace selector 加回来。[7][13]

推荐先启用原生实验功能并测试远程 Server，不安装插件。只有在原生远程会话同步仍失败、且接受无 Desktop UI 的 agent/TUI 工作流时，再单独审计社区插件。

## Recommendation

1. 暂不安装社区 worktree 插件。
2. 在远程 OpenCode Server 启动环境中设置 `OPENCODE_EXPERIMENTAL_WORKSPACES=1` 并重启。
3. 在 Beta Desktop 进入 Settings → Servers → Add Server，添加 `http://127.0.0.1:4096`。
4. 打开一个可由远程 Server 解析的 Git 路径，再检查新会话中的 `Local / New workspace` 选择器。
5. 作为独立交叉验证，可在同版本 CLI 中设置相同变量后运行 `opencode attach`，检查 `/workspaces` 和 `/warp`。
6. 若原生远程流程仍失败，再进行社区插件源码审计；评估目标应是 session 是否真正绑定 worktree，而不是仅看能否执行 `git worktree add`。

## Native Capability

OpenCode 1.18.21 的发布源码包含以下原生能力：

- `GET/POST /experimental/workspace`：列出和创建 workspace。
- `GET /experimental/workspace/adapter`：列出可用 adapter。
- `DELETE /experimental/workspace/:id`：删除 workspace。
- `POST /experimental/workspace/warp`：把 session 移入或移出 workspace。
- `/experimental/worktree`：用于列出、创建和删除底层 Git worktree 的接口。[11]
- 内置 `WorktreeAdapter`：在 `opencode serve` 所在主机上创建 Git worktree。[4][12]

这里 adapter 的 `target.type: "local"` 意味着“位于 Server 本机文件系统”，不是“必须位于 Desktop 所在的 Mac”。这些接口是正常 HTTP Server 路由，所以远程客户端可以调用；实际 Git 操作和路径解析发生在远程 Server/容器内。[3][4][11]

本项目中运行的 OpenCode 1.18.21 Server 也通过只读请求返回了内置 `worktree` adapter，进一步印证发布源码。

## Plugin Boundary

官方插件 API 允许：

- 注册 custom tools。
- 监听事件和修改 tool execution。
- 通过 TUI plugin API 注册 route、JSX UI、dialog、prompt 和 slot。[13]

当前公开文档和导出的 TUI plugin surface 没有提供 Desktop DOM、SolidJS component、菜单、route 或新会话 selector 注入能力。[7][13] 所以：

- 插件可以提供 `worktree_create/list/remove` 等 agent 工具。
- 插件可以在 TUI 中包装一个命令式工作流。
- 插件不能可靠地补齐正式版 Desktop 的原生 workspace UI。
- 插件若自行切换目录，还必须处理 session、subagent、diff、branch 和事件同步，否则只是创建了 worktree，并没有完整隔离 OpenCode session。

## Feature Gates And Clients

原生能力尚未成为默认稳定功能。官方 CLI 文档将 `OPENCODE_EXPERIMENTAL_WORKSPACES` 标为实验变量。[5]

TUI 在该变量启用后提供：

- `/workspaces`：Manage workspaces。
- `/warp`：Change the workspace for the session。[6]

远程 TUI 客户端需要该实验开关才能显示 `/workspaces` 和启用 `/warp`。Server 的实验 HTTP 路由本身仍会挂载，但完整的 workspace list、sync 和 session routing 行为由该开关控制，因此远程 Server 也应启用它。当前项目只显式启用了 Exa，并未显式启用 `OPENCODE_EXPERIMENTAL_WORKSPACES`，所以此前测试只证明了路由和 adapter 存在，没有验证完整 workspace 模式。

Beta Desktop 新会话 selector 的显示条件是“构建渠道不是 `prod` 且当前项目是 Git”；代码不检查 local-server。[2] 远程 HTTP Server 的添加入口位于 Settings 的 Servers 页面；1.18.21 源码会健康检查 URL 后保存连接。[1]

## Remote Maturity

远程 worktree 曾存在缺陷。Issue #12759 报告称，在 1.1.53 中，容器 Server 可以创建 worktree，但远程 Desktop/Web 收不到会话更新，session 还会归入主工作树；该 issue 后来关闭，检索元数据记录显示，1.2.6 已可工作。[8] 这说明远程场景不是设计上禁止，而是实验实现曾不成熟。

Issue #5608 提出 VS Code 式 remote development workspace，其范围远大于“Desktop 连接 `opencode serve` 并让 Server 创建 worktree”；该 issue 后来因长期无活动而被自动关闭，状态为 not planned。该关闭不能解读为维护者正式拒绝该方向。[9] 两者也不能等同。

因此当前状态应描述为：**功能原生、可远程调用且仍处于实验阶段，用户体验的稳定性尚无承诺**。

## Contrary Evidence

- 用户目前在 Beta 中未找到远程 Server 连接入口；这与 1.18.21 官方源码和 troubleshooting 文档冲突。可能原因包括入口位于 Settings → Servers、安装包版本不同或某个 Beta 构建出现回归。需要记录 Beta 的 About 页面中的 version 信息和设置页截图才能定位。
- #12759 证明远程 worktree 历史上会发生 session routing 和 event routing 故障。该 issue 已关闭，但实验接口仍可能回归，因此不能给出稳定性保证。[8]
- #5608 被 inactivity bot 自动关闭，既不能证明近期会实现，也不能证明维护者拒绝了完整 Remote Workspace。[9]

## Open Questions

- 用户安装的 Beta 精确版本号是什么？Settings 中是否存在 Servers 页面？
- `OPENCODE_EXPERIMENTAL_WORKSPACES=1` 启用后，1.18.21 在当前 dual-bind devcontainer 路径下能否完成创建、消息传递和清理？
- 如果原生方案失败，哪个社区插件能正确绑定 session、subagent 和 diff，而不仅是创建目录？由于本轮选择“仅快速确认”，此项未进行源码审计。

## Staleness Map

- Desktop remote Server support: re-check after 2026-09-21.
- Native workspace routes and adapter: re-check after 2026-09-21.
- TUI workspace commands and feature flag: re-check after 2026-09-21.
- Plugin API UI extension surface: re-check after 2026-09-25.
- Earliest re-check: 2026-09-21.

## Source Appendix

| Ref | Evidence | Publisher | Published | Accessed | Confidence |
|---|---|---|---|---|---|
| [1] | [Desktop HTTP Server add/health-check implementation](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/app/src/components/dialog-select-server.tsx) | anomalyco/OpenCode | 2026-08-21 release source | 2026-08-25 | High |
| [2] | [Beta/non-prod + Git workspace selector gate](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/app/src/pages/new-session/new-session-workspace-controller.ts) | anomalyco/OpenCode | 2026-08-21 release source | 2026-08-25 | High |
| [3] | [Experimental workspace HTTP routes](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/server/routes/instance/httpapi/groups/workspace.ts) | anomalyco/OpenCode | 2026-08-21 release source | 2026-08-25 | High |
| [4] | [Built-in WorktreeAdapter](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/control-plane/adapters/worktree.ts) | anomalyco/OpenCode | 2026-08-21 release source | 2026-08-25 | High |
| [5] | [`OPENCODE_EXPERIMENTAL_WORKSPACES` documentation](https://opencode.ai/docs/cli/#experimental) | OpenCode | Updated 2026-08-25 | 2026-08-25 | High |
| [6] | [TUI `/workspaces` command](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/tui/src/app.tsx) and [`/warp`](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/tui/src/component/prompt/index.tsx) | anomalyco/OpenCode | 2026-08-21 release source | 2026-08-25 | High |
| [7] | [Official plugin API](https://opencode.ai/docs/plugins/) | OpenCode | Updated 2026-08-25 | 2026-08-25 | High for documented surface |
| [8] | [Remote worktree bug #12759](https://github.com/anomalyco/opencode/issues/12759) | anomalyco/OpenCode issue tracker | 2026-02-08 | 2026-08-25 | Medium |
| [9] | [Full Remote Workspace request #5608](https://github.com/anomalyco/opencode/issues/5608) | anomalyco/OpenCode issue tracker | 2025-12-16 | 2026-08-25 | Medium |
| [10] | [Desktop custom Server URL troubleshooting](https://opencode.ai/docs/troubleshooting/#fix-server-connection-issues) | OpenCode | Updated 2026-08-25 | 2026-08-25 | High |
| [11] | [Experimental Git worktree HTTP routes](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/server/routes/instance/httpapi/groups/experimental.ts) | anomalyco/OpenCode | 2026-08-21 release source | 2026-08-25 | High |
| [12] | [Built-in adapter registration](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/opencode/src/control-plane/adapters/index.ts) | anomalyco/OpenCode | 2026-08-21 release source | 2026-08-25 | High |
| [13] | [Exported TUI plugin API](https://github.com/anomalyco/opencode/blob/v1.18.21/packages/plugin/src/tui.ts) | anomalyco/OpenCode | 2026-08-21 release source | 2026-08-25 | High |
