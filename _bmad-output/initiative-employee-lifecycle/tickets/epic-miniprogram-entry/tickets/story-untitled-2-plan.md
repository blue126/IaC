---
title: '网站改用新设计与文案源'
type: 'feature'
ticket: '2'
created: '2026-11-02'
status: 'done'
baseline_revision: 'af3f3eaffeea0da804284af6858fdc384667764a'
route: 'full'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 申请网站 cc.willfan.me 仍是旧的蓝色卡片样式，文案写死在 `worker.js` 里，与 5.1 定稿的设计和 `text.json` 不一致。

**Approach:** 按 `remotecc/design/canvas/project/` 的设计稿重写首页、申请页和设备包下载页的 HTML/CSS（手机优先，桌面加宽），所有面向员工的文字（含验证码邮件）改从 `text.json` 读取，颜色等从 `tokens.json` 读取。`worker.js` 仍是可直接上传的单文件：一个同步脚本把两份 JSON 嵌入 `worker.js` 中的标记区，测试检查嵌入内容与设计源一致。接口、限频、验证码、下载计数等行为不变。

**Decision (2026-11-02 用户):** 1) Geist / Geist Mono 由网站自托管：用 geist@1.9.0 的两个可变字体（`Geist-Variable.woff2`、`GeistMono-Variable.woff2`，OFL，已校验 jsDelivr 哈希并存于 `remotecc/design/fonts/`），同步脚本以 base64 嵌入，Worker 在 `/fonts/<文件名>` 返回，长期缓存；中文仍走系统黑体。2) 拆成 `/`（首页）与 `/apply`（申请页），首页按钮跳到申请页。3) 导航暂不显示"我的工作区"，5.3 再加。

## Boundaries & Constraints

**Always:** 页面结构与样式以设计稿为准（直角、1px 分隔线、中性主按钮、绿色只用于小标签/状态点/终端提示符；桌面控件 40px、手机 44px）；深色为主，系统为浅色时用浅色 token；中文走系统黑体，不加载任何外部字体或 CDN（Geist 只从本站 `/fonts/` 取，`font-display: swap`）；保留现有元素 id、表单字段名、Turnstile 渲染条件与前端逻辑；页面上的每一段员工可见文字都来自嵌入的 TEXT；网站不出现小程序引导、收费字样。

**Never:** 不改任何 API、D1 结构、限频与下载规则；不引入 npm 依赖或构建工具链；不做登录与"我的工作区"（5.3）；不调用 Cloudflare、Resend；不 commit、不部署（另行授权）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 首页 | GET / | 新设计首页：品牌、主标题、连接示例、规格信息条、申请须知 4 条、提交申请入口 | — |
| 申请页 | GET /apply | 新设计表单：邮箱、验证码+获取按钮、姓名、手机号、Turnstile、提交 | 错误提示文字来自 TEXT.apply.errors |
| 字体 | GET /fonts/Geist-Variable.woff2、/fonts/GeistMono-Variable.woff2 | 200，`font/woff2`，`cache-control: public, max-age=31536000, immutable`，字节与设计源一致 | 其他 /fonts/ 路径 404；非 GET/HEAD 405 |
| 下载页（有效） | GET /d/<token> | 新设计：剩余次数、有效期（北京时间）、验证码发送至掩码邮箱、下载按钮 | — |
| 下载页（失效） | 过期/用完/未知 token | 410，新设计的"链接已失效"页 | — |
| 验证码邮件 | /api/code、/d/<token>/code | 主题与正文来自 TEXT.mail，`{code}` 被替换 | 行为不变 |
| 文案漂移 | text.json 改了但未同步 | 测试失败并提示运行同步脚本 | — |

</frozen-after-approval>

## Code Map

私有代码 `/Users/weierfu/Projects/IaC/remotecc/apply-site/`（独立 git，main，干净，HEAD af3f3ea）；部署历来是主会话经 Cloudflare MCP 上传单个 `worker.js`，所以不能依赖打包器或 JSON import。

- `worker.js:36-178` `page(env)` -- 首页+申请表合一的 HTML/CSS/内联脚本；脚本里的 `messages` 映射与提示文字改用 TEXT。保留 id：`apply`、`email`、`send-code`、`code`、`name`、`phone`、`submit`、`result`；保留 Turnstile `script`/`widget` 条件渲染与 `addToken`、`resetChallenge`、`countdown`。
- `worker.js:241-251` `sendCodeEmail` / `sendBundleCodeEmail` -- 主题与正文改用 `TEXT.mail.*`（`{code}` 替换），HTML 版沿用现有结构。
- `worker.js:594-631` `downloadPage(title, body)`、`633` `GONE_TEXT`、`749-825` `bundlePage` -- 下载页外壳与内容；保留 `remaining`、`download`、`send-code`、`code`、`download-button`、`result` 及其脚本逻辑。
- `worker.js:866-913` `handle` -- 加 `GET|HEAD /apply`（申请页）与 `GET|HEAD /fonts/<name>`；`/` 改为首页。
- 新增 `sync-design.mjs` -- 读 `../design/text.json`、`../design/tokens.json`、`../design/fonts/*.woff2`，替换 `worker.js` 中 `/* design:begin */ … /* design:end */` 之间的 `const TEXT = …; const TOKENS = …; const FONTS = {name: base64};`；`--check` 只比对不写。
- `test-worker.mjs:297-324、847、1069-1113、1215、1356-1362` -- 断言旧文案（如"纯命令行 Linux 工作区…"、"还可下载 <strong id=\"remaining\">3</strong> 次"）的地方改为断言 TEXT 中的新文案；其余行为测试不动。
- 设计源：`/Users/weierfu/Projects/IaC/remotecc/design/{text.json,tokens.json,canvas/project/Spec,Apply,Download,Web,WebApply.dc.html}`（只读）。

## Tasks & Acceptance

**Execution:**
- [x] `sync-design.mjs` -- 新建同步/校验脚本 -- 保持单文件可上传
- [x] `worker.js` -- 加标记区并运行同步；按设计稿重写首页、申请页、下载页的 HTML/CSS（CSS 变量由 TOKENS 生成，含浅色媒体查询，`@font-face` 指向 `/fonts/`）；页面文字与邮件改用 TEXT；加 `/apply` 与 `/fonts/` 路由；导航不含"我的工作区"
- [x] `test-worker.mjs` -- 更新文案断言；加一条测试：嵌入的 TEXT/TOKENS 与设计源 JSON 深度相等；加一条：页面不含外部字体/CDN 链接与"小程序"字样；加字体路由测试（矩阵"字体"行）；申请相关页面测试改为 GET /apply

**Acceptance Criteria:**
- Given 同步后的 `worker.js`，when 运行 `node --test test-worker.mjs`，then 全部通过。
- Given 手机（390px）与桌面（1280px）宽度，when 打开首页、申请页、下载页，then 布局与对应设计稿一致，无横向滚动。
- Given 系统浅色模式，when 打开页面，then 使用 tokens.json 的 light 配色。

## Implementation Notes

- 标记区导出 `TEXT`、`TOKENS`（供测试深度比对），`FONTS` 为模块内常量；worker.js 约 250 KB（两份字体 base64）。
- text.json 没有的设计稿文字未上页面：桌面申请页左栏的三步列表、"[ 人机验证 ]"占位、"提交成功后/链接失效时"标注。返回链接用 `nav.back`（"规格"），不是设计稿的"首页"。
- 仍为硬编码、不在 TEXT 中的：终端连接示例三行（`TERMINAL_SAMPLE`，命令样例）、有效期后缀 "(UTC+8)"、状态码标签 410/500、`aria-label="主导航"`、拼接用的"，"（BUNDLE_GONE = gone.title + '，' + gone.text）。
- `CODE_CHALLENGE_FAILED` 在前端映射到 `TEXT.apply.errors.APPLY_CHALLENGE_FAILED`；下载页 `BUNDLE_CODE_INVALID` 映射到 `APPLY_CODE_INVALID`。
- 验证码邮件正文按 text.json 变为"…验证码是：{code}"（原为"是 {code}。"），HTML 版按段落生成，验证码放大显示。

- 2026-11-02 截图核对（深浅色、1280/390，首页、申请页、下载页、失效页）：修正验证码框占位文字被字距拉开（`input.code::placeholder`）。提交 apply-site f6daed1、design 9c49a70；未部署。

- 2026-11-02 部署：wrangler 4.151.1（全局安装，用户授权）`wrangler deploy`，版本 95922e31-a8e9-4bdd-ace2-2a31e29b278b；部署前核对线上源码与 af3f3ea 逐字节一致；部署后绑定（ADMIN_TOKEN_SHA256、DB、RESEND_API_KEY、TURNSTILE_SECRET、TURNSTILE_SITEKEY）、cron `0 * * * *`、自定义域名 cc.willfan.me、workers.dev 关闭均不变。线上冒烟：/、/apply 200，字体 200 且哈希与设计源一致，失效链接 410，管理接口无令牌 401，/api/code 坏邮箱 400。新增 wrangler.toml（apply-site 5a36d5a）。未在线上走完整申请（会发真实邮件）。

## Plan Change Log

## Review Triage Log

### Pass 1 (quick) — high 0 / medium 1 / low 7 / false 0 / maybe-false 0; rejected 4

| # | Finding | Verdict | Route | Evidence / action |
|---|---------|---------|-------|-------------------|
| 1 | 首页主标题没有设计稿的换行 | low | patch | 设计稿两处都是"一台属于你的<br>远程 Linux。"；text.json 标题加 `\n`，渲染为 `<br>` |
| 2 | 手机首页：顶栏仍有"提交申请"、网格背景缺失、终端 3 行 | low | reject | 顶栏的"我的工作区"按 3A 暂不显示，用申请入口替代是合理取舍；网格与终端行数为纯装饰差异 |
| 3 | 规格条格式与设计不同（"CPU 2 vCPU"重复） | low | patch | 渲染为 `key <b>value</b>`；text.json 加 `spec.bar` 显示串，规格条改用它 |
| 4 | 申请须知标题在桌面独占一行 | low | patch | `.notes strong{display:block}` 与 Web.dc.html 行内不一致；桌面改行内 |
| 5 | 手机申请页顶栏左右顺序与设计相反 | low | reject | 品牌居左在三页一致，属外观取舍，修改需加分支 |
| 6 | 下载页有页脚，设计无 | low | reject | 纯外观差异，页脚无害 |
| 7 | 剩余次数数字未用强调色 | low | patch | Download.dc.html 用 accent，用户已审定该稿；加颜色 |
| 8 | `done_last` 从 TEXT 截取 | low | patch | `indexOf('。')` 为 -1 时变空串；text.json 加 `bundle.done_last` |
| 9 | 员工可见文字仍有写死：`(UTC+8)`、`，` 拼接、终端示例 | medium | patch | 违反 frozen "每一段员工可见文字都来自 TEXT"，矩阵要求北京时间；text.json 加 `bundle.timezone`、`bundle.gone.inline`、`hero.terminal`；数字编号、状态码、"/ 3" 非文案，不改 |
| 10 | 下载页借用申请页的"已发送"提示 | low | patch | 多出"查看垃圾邮件"与掩码邮箱；text.json 加 `bundle.code_sent` |
| 11 | 成功提示用 `replaceChildren` | low | patch | 其余脚本为 ES5；旧内核会抛错且无确认；改为清空后 appendChild |

## Verification

**Commands:**
- `node sync-design.mjs --check` -- expected: 无差异，退出 0
- `node --test test-worker.mjs` -- expected: fail 0

**Manual checks (if no CLI):**
- 本地用 `node` 渲染三个页面写到临时 HTML，用浏览器在 390px 与 1280px 宽度下与设计稿对照截图。
