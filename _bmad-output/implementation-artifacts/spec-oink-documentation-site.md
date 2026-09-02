---
title: 'OINK documentation site pilot / OINK 文档站试点'
type: 'feature'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 0
baseline_commit: '701ea6e9bc69dc5a09ceb4994f5913189081bbb8'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 仓库的 94 篇 Markdown 只能从 Git 源码浏览，缺少统一导航、本地搜索、自动发布和 Agent 可直接消费的输出。

**Approach:** 增加一个最小、可独立删除的 OINK/Hugo 展示层；构建时从 `docs/` 生成仅补充标题的临时 overlay，源文档保持不变，并发布 HTML、逐页 Markdown 与根 `llms.txt`。

## Boundaries & Constraints

**Always:** 固定 OINK `v0.7.0`、Hugo Extended `v0.165.0` 和 CI Go 版本；适配 `/IaC/` 子路径；保留现有 Markdown 源文件和 GitHub 阅读体验；Pages build 不持有生产凭据；记录本地预览、升级和删除步骤。

**Ask First:** 修改任何现有 `docs/` 正文或元数据、启用外部分析/AI 跳转、访问生产 API/Vault、改用其他部署平台或扩大自动化范围时暂停确认。

**Never:** 不移动或批量改写文档；不引入 Node/npm 项目依赖；不提交 `public/`、缓存或生成后的 Markdown；不维护 `gh-pages`；不修改 Jenkins、Terraform、Ansible 或 inventory；不实现 metadata Schema、文档准确性门禁、collector、reconciliation、AI gardening、自动 PR/merge 或生产回写。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 本地构建 | 固定 Hugo Extended、Go、OINK module | 现有 `docs/` 可导航、搜索，Mermaid 可渲染 | 版本或 module 不符时构建失败并由 README 给出安装方式 |
| Agent 输出 | 普通文档页与首页 | 页面生成 `index.md` 和 alternate；根生成非空 `llms.txt` | smoke check 缺任一关键输出即失败 |
| Pages 项目站 | GitHub Pages 动态 base URL | CSS、搜索、canonical、链接和 Agent URL 保留 `/IaC/` | PR 只构建；仅 `master`/手动触发 deploy job |

</frozen-after-approval>

## Code Map

- `docs/` -- 94 篇现有内容；本次只读，通过 Hugo mount 复用。
- `README.md:184-191` -- 增加文档站和本地预览入口。
- `Jenkinsfile:5-9,36-49` -- Jenkins 持有生产凭据且跳过 docs-only 变更；只读隔离证据。
- `hugo.yaml`, `go.mod`, `go.sum` -- 新站点配置、完整 outputs、mounts 和固定 OINK module。
- `docs-site/` -- 只存放站点首页、窄范围模板和中英文本地运维说明。
- `docs-site/scripts/prepare-content.py` -- 从原文首个 H1 推导 OINK title，输出到被忽略的临时目录。
- `.github/workflows/docs-pages.yml` -- 独立 build/deploy 权限、artifact 和 Pages 发布。

## Tasks & Acceptance

**Execution:**
- [x] `hugo.yaml`, `go.mod`, `go.sum` -- 配置 OINK、Goldmark、搜索、Mermaid、HTML/RSS/print/markdown/LLMS outputs 及 `docs` mount。
- [x] `docs-site/content/`, `docs-site/data/`, `docs-site/scripts/prepare-content.py`, `docs-site/layouts/_markup/render-link.html`, `docs-site/README.md` -- 增加 landing、临时标题 overlay、链接适配和运维说明。
- [x] `.github/workflows/docs-pages.yml` -- 固定工具版本，PR 仅构建，deploy job 单独使用 `pages: write`/`id-token: write`。
- [x] `.gitignore`, `README.md` -- 忽略 Hugo 产物并增加站点入口，不改变现有工程命令或文档正文。
- [x] 构建 smoke check -- 验证首页、普通 HTML/Markdown、alternate、`llms.txt`、搜索、Mermaid 和 `/IaC/` base path。

**Acceptance Criteria:**
- Given 固定工具链，when 执行严格生产构建和 smoke check，then 现有内容、搜索、Mermaid、`/IaC/` 路径及 Agent 输出可用。
- Given 任一普通文档页，when Hugo 完成构建，then 同时存在 HTML、Markdown 镜像及指向镜像的 alternate 元数据。
- Given PR、`master` push 和手动触发，when workflow 运行，then PR 仅构建，发布权限只存在于独立 deploy job，且无生产凭据。
- Given 删除站点新增文件并还原 README/.gitignore 两处小改动，when 检查仓库，then `docs/` 与现有 Jenkins/IaC 行为保持原样。

## Spec Change Log

## Design Notes

Hugo 项目根保持为仓库根；构建脚本把 `docs/` 转为被忽略的 `.hugo-content/docs`，只提升首个 H1 为 title，并由 module mount 发布。OINK 是纯展示层，不承担文档真实性判断；AI 文档治理研究保留为后续独立项目。

## Verification

**Commands:**
- `hugo version && go version && hugo mod graph` -- 显示固定 Hugo Extended、Go 和 OINK 版本。
- `python3 docs-site/scripts/prepare-content.py` -- 生成带导航标题的临时 content overlay，不修改 `docs/`。
- `hugo --cleanDestinationDir --gc --minify --environment production --printPathWarnings --panicOnWarning --baseURL 'https://blue126.github.io/IaC/'` -- 严格构建成功。
- `test -s public/llms.txt && test -s public/docs/designs/homelab-iac-architecture/index.html && test -s public/docs/designs/homelab-iac-architecture/index.md` -- 关键输出存在且非空。
- `git diff --check` -- 无补丁格式错误。

**Manual checks (if no CLI):**
- 用 `hugo server` 检查桌面/移动端导航、搜索、深浅主题、中文、代码块和 Mermaid。
- 在 GitHub 设置中确认 Pages source 为 GitHub Actions；首次发布后复查 URL、Markdown 菜单和 `llms.txt`。

## Suggested Review Order

**站点骨架 / Site skeleton**

- 从输出矩阵与 mounts 理解最小无复制展示层。
  [`hugo.yaml:37`](../../hugo.yaml#L37)

- 首页明确 OINK 只负责浏览与 Agent 输出。
  [`_index.md:1`](../../docs-site/content/_index.md#L1)

**发布边界 / Publication boundary**

- PR 只构建，发布权限隔离到 deploy job。
  [`docs-pages.yml:30`](../../.github/workflows/docs-pages.yml#L30)

- 精确 smoke checks 保护 Pages 子路径和 Agent 输出。
  [`docs-pages.yml:64`](../../.github/workflows/docs-pages.yml#L64)

**兼容与运维 / Compatibility and operations**

- Link hook 复用 Hugo 页面并保留 query/fragment。
  [`render-link.html:1`](../../docs-site/layouts/_markup/render-link.html#L1)

- Build overlay 从原文 H1 提供侧栏和浏览器标题。
  [`prepare-content.py:1`](../../docs-site/scripts/prepare-content.py#L1)

- 固定版本、本地预览、升级与删除步骤集中维护。
  [`README.md:7`](../../docs-site/README.md#L7)

- 根 README 只增加站点入口，保持原项目工作流。
  [`README.md:184`](../../README.md#L184)
