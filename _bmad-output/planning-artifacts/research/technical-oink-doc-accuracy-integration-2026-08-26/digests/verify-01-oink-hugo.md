# Fresh-context verification: OINK/Hugo

核验截止日期：2026-08-26

证据计数规则：同一内容 publisher 的 release、文档、源码和线上站点只算一个独立来源组；GitHub 仅作为托管平台，不把其托管的不同项目误算为 GitHub 自身的多份独立证据。

## Claim A

- **ref:** A — OINK v0.7.0/Hugo Extended 版本边界
- **status:** verified
- **claim:** 截至核验日，OINK 最新 release 是 v0.7.0（2026-08-25），其模块配置声明 Hugo `min: 0.160.1`、`extended: true`；Hugo 最新 release 是 v0.165.0（2026-08-12）。Hugo v0.153.2 起不再执行模块的 Extended edition 检查，因此若把 OINK 声明的 Extended 要求当作消费方契约，CI 必须自行固定并检查所装二进制，不能依赖 Hugo 模块兼容性检查拒绝 standard edition。
- **独立来源:** PGSTY/OINK（一个 publisher 组）：v0.7.0 release 与该 tag 的 `hugo.yaml`；Hugo Authors（一个 publisher 组）：v0.165.0 release、v0.153.2 release、模块配置文档及移除检查的 commit；RepoRank（独立 publisher，仅作二手交叉佐证，不承担版本事实的主要证明）。
- **理由:** OINK v0.7.0 release 页面给出 8 月 25 日发布日期；tag `v0.7.0` 的 `hugo.yaml` 明确含 `module.hugoVersion.min: 0.160.1` 和 `extended: true`。Hugo v0.165.0 release 页面标记为 Latest 并给出 8 月 12 日发布日期。Hugo v0.153.2 release 明列 “modules: Remove extended edition check”，对应 commit `a94a941` 从 `HugoVersion.IsValid` 删除 `v.Extended && !hugo.IsExtended` 判断；模块文档也明确称 v0.153.2 及以后禁用该检查。这里验证的是 OINK 的声明边界和 Hugo 不再强制它；没有独立兼容性测试证明 standard edition 一定会使 OINK 构建失败。
- **置信度:** 0.98（高）
- **sources:**
  - https://github.com/pgsty/oink/releases/tag/v0.7.0
  - https://raw.githubusercontent.com/pgsty/oink/v0.7.0/hugo.yaml
  - https://github.com/gohugoio/hugo/releases/tag/v0.165.0
  - https://github.com/gohugoio/hugo/releases/tag/v0.153.2
  - https://github.com/gohugoio/hugo/commit/a94a941fe3464d3997fd4f74f5cf9bc781bbc4aa
  - https://gohugo.io/configuration/module/
  - https://reporank.net/en/repo/pgsty-oink.html

## Claim B

- **ref:** B — 逐页 Markdown 与 `llms.txt` 能力
- **status:** verified
- **claim:** OINK v0.7.0 能在 Hugo 构建期按消费站显式选择的 output kinds 生成页面 `index.md`、HTML 中的 `rel="alternate" type="text/markdown"`，以及每语言的 `llms.txt`。Markdown 模板使用 `.RenderShortcodes`，会展开有对应 Markdown 渲染形态的 shortcode；仅由浏览器 JavaScript 绘制的图表不会变成静态图，而保留机器可读源码。`llms.txt` 是社区提案，不替代 robots.txt 或 sitemap，也不是 IETF/W3C 正式 Web 标准。
- **独立来源:** PGSTY/OINK（一个 publisher 组）：v0.7.0 模板源码及线上构建产物；Hugo Authors（一个 publisher 组）：内置 `markdown` output format 定义和 output 选择实现；Answer.AI/Jeremy Howard（一个 publisher 组）：`llms.txt` v2 提案；Pavel Nasovich（独立 publisher）：截至 2026-08-04 的 Hugo/llms.txt 技术复核。
- **理由:** OINK tag 中 `layouts/all.md` 直接调用 `.RenderShortcodes`，`layouts/index.llms.txt` 从当前 language site/home 及页面树生成索引；线上 `/zh/docs/customize/agents/index.md`、`/zh/llms.txt` 均可取回，HTML `<head>` 实际含指向该 Markdown 页的 alternate link。Hugo 的内置 `markdown` format 定义为 `baseName: index`、`mediaType: text/markdown`、`rel: alternate`。Answer.AI v2 原文称其为 proposal，并明确 `llms.txt` 与 robots/sitemap 用途不同，同时建议 `alternate` 指向 Markdown、`describedby` 指向覆盖该页的 `llms.txt`。
- **限定:** “逐页”不是主题无条件强制开启；消费站必须在相应 `home`、`page`、`section` 等 kind 的 `outputs` 中显式选择 `markdown`，并在 `home` 中选择 `LLMS`。未选中的 kind/page 不会生成该表面。
- **置信度:** 0.97（高）
- **sources:**
  - https://raw.githubusercontent.com/pgsty/oink/v0.7.0/layouts/all.md
  - https://raw.githubusercontent.com/pgsty/oink/v0.7.0/layouts/index.llms.txt
  - https://oink.pgsty.com/zh/docs/customize/agents/index.md
  - https://oink.pgsty.com/zh/llms.txt
  - https://oink.pgsty.com/zh/docs/customize/agents/
  - https://gohugo.io/configuration/output-formats/
  - https://llmstxt.org/
  - https://forcewake.me/llms-txt-hugo-module-guide/

### `outputs` 语义冲突裁决

- **conflict_ref:** B-outputs
- **conflict_status:** overturned（推翻 Hugo 文档页的 “appends” 断言，也推翻原 digest 将 OINK 的替换语义视为未证实的保留意见）
- **裁决:** Hugo v0.165.0 的实际实现中，页面 front matter `outputs` **替换**该 page kind 的项目级输出集合，不是追加。故 `outputs: [HTML]` 确实可移除该页的 Markdown 输出；项目配置中某个 kind 的数组也应完整保留所需的 HTML/RSS/print/markdown。
- **证据:** 2026-08-23 更新的 Hugo “Configure outputs” 文档写着 “appends to, rather than replaces”，但 v0.165.0 tag 的 `PageConfigLate.Compile` 将 front matter names 直接赋给 `ConfiguredOutputFormats`，`pageState.outputFormats()` 检测到它后直接返回该集合，否则才回退到 kind 配置。更直接的是同一 tag 的 `TestContentAdapterOutputsIssue13689`：项目配置 `page = ['html','json']`，页面 front matter 仅写 `html`，测试明确断言 `index.json` 不存在。源码、控制流与可执行集成测试一致，文档句子是错误文档，而不是行为变更。OINK 的“整体替换”说明与 Hugo v0.165.0 实现一致。
- **置信度:** 0.99（很高）
- **sources:**
  - https://gohugo.io/configuration/outputs/
  - https://raw.githubusercontent.com/gohugoio/hugo/v0.165.0/resources/page/pagemeta/page_frontmatter.go
  - https://raw.githubusercontent.com/gohugoio/hugo/v0.165.0/hugolib/page__meta.go
  - https://raw.githubusercontent.com/gohugoio/hugo/v0.165.0/hugolib/pagesfromdata/pagesfromgotmpl_integration_test.go

## Claim C

- **ref:** C — Pages build 与持有生产凭据的生成流程隔离
- **status:** verified
- **claim:** GitHub Pages/Hugo 的纯构建应与需要生产 API 或云资源凭据的内容生成流程建立权限和制品边界。Pages build 只消费已审查、不可变或内容寻址的输入，并只获得构建所需的读取/制品上传权限；生产凭据只授予专用生成 job/workflow，优先使用受保护 environment 与短期 OIDC 凭据。
- **独立来源:** GitHub（一个 publisher 组）：Pages custom workflow、`deploy-pages` 与 Actions secure-use 文档；OpenSSF（独立 publisher）：Open Source Project Security Baseline；OWASP（独立 publisher）：CI/CD Security Cheat Sheet；NIST（独立 publisher）：SSDF SP 800-218。
- **理由:** GitHub Pages 官方流程天然支持 build job 上传 artifact、独立 deploy job 仅消费 artifact，并要求 deploy job 单独声明 `pages: write`、`id-token: write` 和 environment。GitHub secure-use 要求最小权限，警告 privileged workflow 不得检出并执行不可信 PR 代码，并建议 OIDC 短期凭据。OpenSSF OSPS-BR-01.03 要求处理不可信代码快照的 pipeline 阻止访问 privileged CI/CD credentials/assets；OSPS-AC-04 要求每个 task/job 最小权限。OWASP 进一步要求不同敏感级别 pipeline 尽量不共享凭据。NIST SSDF PO.5.1 要求分离和保护各开发环境及生产环境。由此，“隔离”是多方安全基线支持的设计结论，不只是偏好。
- **限定:** 隔离不强制必须拆成两个 workflow 文件；独立 job、独立权限、environment gate、不可变 artifact 和无共享生产 secret 也可形成有效边界。反之，仅拆文件但共享同一生产 secret 或可变工作目录不构成充分隔离。Pages deploy 自身需要 GitHub Pages/OIDC 权限，这不等于允许 Hugo build 或内容模板获得业务生产凭据。
- **置信度:** 0.96（高）
- **sources:**
  - https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
  - https://github.com/actions/deploy-pages/blob/main/README.md
  - https://docs.github.com/en/actions/reference/security/secure-use
  - https://baseline.openssf.org/versions/devel.html
  - https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html
  - https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf

## 状态摘要

| Ref | Status | Confidence |
|---|---|---:|
| A | verified | 0.98 |
| B | verified | 0.97 |
| C | verified | 0.96 |

关键附带裁决：`B-outputs` = **overturned**；Hugo v0.165.0 页面级 `outputs` 的真实语义是替换，官方配置文档的“追加”句子与同版本源码及测试冲突。
