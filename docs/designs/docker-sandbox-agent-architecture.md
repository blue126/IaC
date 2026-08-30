# Docker Sandbox Agent Architecture

## 1. 目标

本设计定义 IaC 仓库中 Codex、BMad、Docker Sandbox、MCP 和项目指令的职责边界。目标是让新 worktree 与 clone 自动获得项目 BMad runtime，避免宿主个人 skills 污染 Sandbox，并让 BMad 成为唯一 workflow owner。

## 2. 职责模型

| 层 | 来源 | 职责 |
|---|---|---|
| Codex system skills | Codex agent template | OpenAI 内建能力 |
| 项目 skills | `.agents/skills/` | BMad planning、implementation、review workflow |
| 项目指令 | `AGENTS.md` | 仓库事实、技术规范、环境能力、安全边界 |
| Codex 项目配置 | `.codex/config.toml` | sandbox-local Playwright MCP |
| Sandbox Kit | `.sandbox-kit/` | 软件、网络、环境变量、Chromium 和 wrapper |
| 设计文档 | `docs/designs/` | 原理、拓扑、迁移和故障排查；不注入 prompt |

`AGENTS.md` 不定义 task decomposition、checkpoint、实现顺序、验证策略或 Git/PR lifecycle。BMad workflow 决定这些步骤；workflow ownership 不等于授权，未明确批准的 commit、push、merge、deployment 或其他外部写入仍必须停止。

## 3. Skills 拓扑

Docker Sandboxes 可以把宿主 persistent skills store 挂载进 microVM。IaC Codex Sandbox 在创建时使用：

```bash
sbx run --name iac-codex --no-share-skills codex . --kit ./.sandbox-kit
```

`--no-share-skills` 只关闭 Docker 的宿主共享 store，不删除 Codex system skills，也不影响仓库 `.agents/skills/`。该设置在 Sandbox 创建时固定；重新连接现有 Sandbox 不会改变 mount。

`.agents/` 和 `_bmad/` 纳入 Git，使 linked worktree、普通 clone 和 Docker clone 都能获得同一 BMad 版本。以下内容继续忽略：

- `_bmad-output/`
- `_bmad/render/` 中的生成快照
- `_bmad/config.user.toml`
- `_bmad/**/config.user.yaml`
- `_bmad/custom/*.user.toml`

## 4. Codex 配置与 project trust

Codex 从可信项目加载 `.codex/config.toml`：

```toml
[mcp_servers.playwright]
command = "iac-playwright-mcp"
required = true
```

新 Sandbox 首次启动时必须将 IaC 项目标记为 trusted。Untrusted project 会跳过项目 `.codex/` 层，因此 MCP 缺失时不得退回冗长 CLI override 或假定配置已加载；应先修复 trust，再运行：

```toml
[projects."/absolute/path/to/IaC"]
trust_level = "trusted"
```

该 entry 位于 Sandbox 的 `$CODEX_HOME/config.toml`。Docker adapter 可能在重建时重写它，因此每个新实例都要重新验收。

```bash
codex mcp list
```

`required = true` 使本地 Playwright 初始化失败成为显式启动错误，避免静默退化到 Docker MCP gateway 中同名或相似工具。

## 5. Playwright MCP 数据流

```text
Codex
  → project .codex/config.toml
  → iac-playwright-mcp (stdio)
  → Kit resolves chromium.executablePath() and creates /usr/local/bin/iac-chromium
  → playwright-mcp --headless --isolated --executable-path <chromium>
  → Chromium in the same Sandbox microVM
```

`.sandbox-kit/files/home/.local/bin/iac-playwright-mcp` 提供 wrapper；`.sandbox-kit/spec.yaml` 安装固定版本 Playwright MCP 与 Chromium。项目配置只选择入口，不复制安装逻辑。

## 6. 运行拓扑

### Direct mode from main checkout

- workspace 与 gitignored 文件直接挂载。
- Sandbox 内 Git 可用。
- 仓库不得保存 SSH 私钥。

### Direct mode from host linked worktree

- 文件编辑与本地验证可用。
- Docker 可能无法解析指向外部 common Git directory 的 `.git` pointer，因此 Sandbox 内 Git 可能不可用。
- 不复制或挂载 common Git directory；需要 Git 时由宿主侧处理能力边界。

### Clone mode

- Sandbox 内有私有 Git clone。
- gitignored Vault、Terraform secrets 和个人 BMad 配置不存在。
- 只从 `/run/sandbox/source` 复制任务明确需要的 secret 文件，且不输出内容。

## 7. 凭据边界

- SSH：使用宿主转发的 SSH agent；运行 Ansible 前验证 `ssh-add -L`。
- Vault：direct mode 使用工作区现有 gitignored 文件；clone mode 按需复制。
- OCI：仅在任务需要时挂载已存在的 `${HOME}/.oci:ro`；目录缺失时停止，不创建空目录或搜索替代私钥。
- BMad：团队 runtime 纳入 Git，`config.user.toml` 与 `*.user.toml` 永不跟踪。

## 8. 现有 Sandbox 迁移

`iac-codex` 已创建时，不能原地应用 `--no-share-skills`。先运行 `sbx ls`；若固定名称已存在，使用新名称（例如 `iac-codex-bmad`）创建测试 Sandbox。验证 skills、trust 和 MCP 后，再单独请求删除或替换旧实例。不得自动删除旧实例或其内部 session/state。

## 9. 验收

```bash
sbx kit validate ./.sandbox-kit
sbx kit inspect ./.sandbox-kit --json
git check-ignore -v _bmad/config.user.toml _bmad/custom/config.user.toml
```

在新 Codex Sandbox 中确认：

1. IaC project 已 trusted。
2. `codex mcp list` 显示 required local `playwright`，命令为 `iac-playwright-mcp`。
3. `mount | grep agent-skills` 没有输出；`codex debug prompt-input noop` 包含 Codex system skill marker 与项目 BMad skill marker。
4. BMad workflow 激活时没有第二套通用 checkpoint、worktree 或交付流程。

## 10. 参考

- [Codex AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codex config basics](https://learn.chatgpt.com/docs/config-file/config-basic)
- [Codex config reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Docker Sandboxes usage](https://docs.docker.com/ai/sandboxes/usage/)
- [Docker host worktree Git boundary](https://docs.docker.com/ai/sandboxes/workflows/git/)
