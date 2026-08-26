# OINK documentation site / OINK 文档站

This removable presentation layer mounts the repository `docs/` directory without copying it. It publishes HTML, local search, Mermaid diagrams, page-level Markdown alternates, and `/llms.txt`. It has no production credentials and does not determine whether documentation claims are accurate.

本展示层直接挂载仓库 `docs/`，不复制正文；它发布 HTML、本地搜索、Mermaid、逐页 Markdown alternate 和 `/llms.txt`。构建不持有生产凭据，也不负责判定文档事实是否准确。

## Local build / 本地构建

Required versions / 固定版本：

- Hugo Extended `v0.165.0`
- Go `1.25.0`
- OINK `v0.7.0` (pinned in `go.mod`)

```bash
hugo version && go version && hugo mod graph
hugo --cleanDestinationDir --gc --minify --environment production \
  --printPathWarnings --panicOnWarning \
  --baseURL 'https://blue126.github.io/IaC/'
BASE_URL='https://blue126.github.io/IaC/'
test -s public/index.html
test -s public/index.md
test -s public/llms.txt
test -s public/docs/designs/homelab-iac-architecture/index.html
test -s public/docs/designs/homelab-iac-architecture/index.md
grep -Fq "rel=canonical href=${BASE_URL}docs/designs/homelab-iac-architecture/" public/docs/designs/homelab-iac-architecture/index.html
grep -Fq "rel=alternate type=text/markdown href=${BASE_URL}docs/designs/homelab-iac-architecture/index.md" public/docs/designs/homelab-iac-architecture/index.html
grep -Fxq '# Homelab IaC 系统架构文档' public/docs/designs/homelab-iac-architecture/index.md
grep -Fq '本文档描述 Homelab Infrastructure as Code 项目的完整系统架构' public/docs/designs/homelab-iac-architecture/index.md
grep -Fq "${BASE_URL}docs/designs/homelab-iac-architecture/index.md" public/llms.txt
grep -Fq 'td-diagram--mermaid' public/docs/designs/cicd-architecture/index.html
grep -Fq 'mermaid-' public/docs/designs/cicd-architecture/index.html
shopt -s nullglob
search_indexes=(public/offline-search-index.*.json)
test "${#search_indexes[@]}" -eq 1
test -s "${search_indexes[0]}"
grep -Fq '"title":"Documentation / 文档"' "${search_indexes[0]}"
grep -Fq '"ref":"/IaC/docs/"' "${search_indexes[0]}"
```

For an interactive preview / 交互式预览：

```bash
hugo server --baseURL http://localhost:1313/IaC/ --appendPort=false
```

If `hugo version` does not contain both `v0.165.0` and `+extended`, install the matching Extended release from [Hugo releases](https://github.com/gohugoio/hugo/releases/tag/v0.165.0). Install Go `1.25.0` from [go.dev](https://go.dev/dl/). The checks intentionally fail instead of accepting another toolchain.

如果 `hugo version` 未同时包含 `v0.165.0` 与 `+extended`，请从上述 Hugo release 安装匹配的 Extended 包；Go 必须为 `1.25.0`。检查会主动拒绝其他工具链。

## Upgrade / 升级

1. Review the target OINK release notes and its `hugo.yaml` module constraint.
2. Update the OINK version in `go.mod`, run `go mod download github.com/pgsty/oink@<version>`, and inspect `go.sum`.
3. Review the relative Markdown link hook against the new release.
4. Run every command above and inspect the smoke outputs before publishing.

升级时先阅读 OINK release notes，再更新 `go.mod`，并用 `go mod download` 更新校验和。必须复查相对 Markdown 链接 hook，并完整运行构建与 smoke checks。

## Removal / 删除

Delete `hugo.yaml`, `go.mod`, `go.sum`, `docs-site/`, and `.github/workflows/docs-pages.yml`; then revert only the OINK entries in `.gitignore` and `README.md`. Do not change `docs/`, Jenkins, Terraform, Ansible, inventory, or the original document layout.

删除上述站点文件，并只还原 `.gitignore` 与 `README.md` 中的 OINK 条目，即可恢复试点前状态；无需改动 `docs/`、Jenkins、Terraform、Ansible 或 inventory。
