# OINK/Hugo 准确内容集成摘要

截至 2026-08-26。

## 明确 claims（事实）

1. **版本边界。** OINK 最新发布为 v0.7.0（2026-08-25），模块声明 Hugo `min: 0.160.1`、`extended: true`；Hugo 最新发布为 v0.165.0（2026-08-12）。但 Hugo 自 v0.153.2 起不再执行 Extended 检查，因此必须由 CI 显式安装/验证 OINK 要求的二进制，不能依赖模块拒绝标准版。[1][2][3]
2. **机器可读输出。** OINK 可在构建期生成逐页 `index.md`、`rel="alternate" type="text/markdown"` 与每语言 `llms.txt`；Markdown 是源码路径并展开 shortcode，浏览器运行时图表只保留围栏源码。`llms.txt` 不是 robots/sitemap，也不是正式 Web 标准；v2 提案还建议用 `rel="describedby"`，OINK 当前明确只保证 `.md` 与 `llms.txt` 两个表面。[4][5]
3. **配置冲突。** OINK 称页面 front matter 的 `outputs` 会整体替换，Hugo 2026-08-23 官方文档却称页面级 `outputs` 会追加到项目配置；故不能把 OINK 的 `[HTML]` opt-out 当作已证实行为，须在锁定版本上做 golden build。项目配置的 page-kind 数组仍应完整列出 HTML/RSS/print/markdown，避免默认输出漂移。[4][6]
4. **生成方式边界。** 普通 data template 只把 `data/` 或 data mount 中的 JSON/TOML/YAML/XML供模板读取；真正从记录创建 Page 要用 v0.126.0 引入的 `_content.gotmpl` content adapter。adapter 执行时 `Site` 尚未完整初始化，页面路径碰撞因并发而结果不定；mount 只是把目录叠入 Hugo 统一文件系统，项目配置为某组件新增 mount 会移除该组件默认 mount。Render hook 仅改 Markdown 元素转换，cascade 仅向后代补 front matter，二者都不创建独立页面。[7][8][9]
5. **Pages 集成。** GitHub Pages 对任意静态生成器采用自定义 Actions 构建、上传、部署制品，并不提供“当前 Hugo 运行时”；官方 starter 截至访问日仍固定 Hugo Extended 0.128.0，低于 OINK 下限。应复制后自行固定 Hugo/Go/OINK，提交 `go.sum`，而非跟随 starter 或 `latest`。[10][3]

## 推论与建议

- **隔离生产凭据：** AI/确定性生成放在独立、受审查 workflow，输出经 schema、链接、敏感信息扫描后提交或作为不可变输入；Pages/Hugo build 只读该输入，并设 `HUGO_SECURITY_HTTP_URLS=none`。不要在 Hugo adapter/template 中调用生产 API。若生成必须访问云资源，用 OIDC 短期令牌、environment approval 和最小权限；绝不在 `pull_request_target` 中检出不可信代码后暴露 secrets。[11][12]
- **provenance：** 每页 front matter 记录 `generated_by`、工具/模型版本、prompt/config hash、源 URL/源 revision、`generated_at`、reviewer、content hash；另生成站点级 manifest，把输出 hash 绑定到 git SHA/workflow run。公开制品可附 GitHub artifact attestation；这证明“何处、何时、如何构建”，不证明内容事实正确。[13]
- **首选顺序：** 可审阅且需追责的 AI 文档优先“预生成并提交”；大量确定性、本地、非敏感数据可用 content adapter；跨仓库已生成 Markdown 用 content mount；data template 用于共享展示数据；render hook/cascade 仅做表现和默认元数据。

## 局限

未找到 OINK 对任意 AI provenance schema 的原生支持；上述字段是架构建议。`outputs` 冲突及 v0.165.0 对 OINK v0.7.0 的完整兼容性没有独立测试报告，本摘要不把它们标为已验证。

## 来源

[1] PGSTY/OINK, release v0.7.0, 2026-08-25, accessed 2026-08-26, https://github.com/pgsty/oink/releases/tag/v0.7.0  
[2] Hugo Authors, Hugo v0.165.0 release, 2026-08-12, accessed 2026-08-26, https://github.com/gohugoio/hugo/releases/tag/v0.165.0  
[3] Hugo Authors, “Configure modules”, updated 2026-06-18, accessed 2026-08-26, https://gohugo.io/configuration/module/  
[4] PGSTY/OINK, “Agent 支持”, updated 2026-08-25, accessed 2026-08-26, https://oink.pgsty.com/zh/docs/customize/agents/  
[5] Answer.AI/Jeremy Howard, “The /llms.txt file, v2”, published 2024-09-03, updated 2026-08-10, accessed 2026-08-26, https://github.com/AnswerDotAI/llms-txt  
[6] Hugo Authors, “Configure outputs”, updated 2026-08-23, accessed 2026-08-26, https://gohugo.io/configuration/outputs/  
[7] Hugo Authors, “Content adapters”, updated 2026-07-07; Hugo v0.126.0 release, 2024-05-14, accessed 2026-08-26, https://gohugo.io/content-management/content-adapters/ ; https://github.com/gohugoio/hugo/releases/tag/v0.126.0  
[8] Hugo Authors, “hugo.Data” and “Configure modules”, updated 2026-06-18, accessed 2026-08-26, https://gohugo.io/functions/hugo/data/ ; https://gohugo.io/configuration/module/  
[9] Hugo Authors, “Render hooks: Introduction”, updated 2026-06-18; “Configure cascade”, updated 2026-07-27, accessed 2026-08-26, https://gohugo.io/render-hooks/introduction/ ; https://gohugo.io/configuration/cascade/  
[10] GitHub, “Using custom workflows with GitHub Pages” (date unavailable), and actions/starter-workflows `pages/hugo.yml` (date unavailable), accessed 2026-08-26, https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages ; https://github.com/actions/starter-workflows/blob/main/pages/hugo.yml  
[11] Hugo Authors, “Security model”, updated 2026-07-03; “Configure security”, updated 2026-06-18, accessed 2026-08-26, https://gohugo.io/about/security/ ; https://gohugo.io/configuration/security/  
[12] GitHub, “Secure use reference” and “Using secrets in GitHub Actions” (dates unavailable), accessed 2026-08-26, https://docs.github.com/en/actions/reference/security/secure-use ; https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets  
[13] GitHub, “Using artifact attestations to establish provenance for builds” (date unavailable); SLSA/Linux Foundation, “Provenance”, v1.2 approved (date unavailable), accessed 2026-08-26, https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations ; https://slsa.dev/spec/v1.2/provenance
