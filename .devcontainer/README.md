# devcontainer 上手

**工具链跑在容器里,界面跑在宿主机上。**

terraform / ansible / python 和一整串传递依赖都关在容器里,不装进 macOS。
coding agent 也跑在容器里,能碰到的只有明确挂进去的东西。但 TUI、桌面 app、
以及**你看得见的那个浏览器**留在 Mac 上 —— agent 通过 MCP 反向驱动它们。

```
  宿主机 (macOS)                          dev container
  ──────────────                          ─────────────
  OpenCode Desktop  ──── :4096 ────────►  opencode serve
  可见的 Chrome  ◄──  playwright-mcp
                        (:8931)  ◄────────  agent
```

**它不是什么**:不是一个"打开就能用"的通用开发容器。它假设你在 macOS 上、
用 Docker Desktop、并且在宿主机上已经配好了 Codex / Claude Code / opencode。
容器**继承**你宿主的这些配置,不自己建一套。

---

## 1. 前置条件

整段粘进终端,缺什么它会直接报出来:

```bash
fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "  ✓ $1"; else echo "  ✗ $1"; fail=1; fi; }

echo "宿主机工具"
check "Docker 在跑"            'docker info'
check "devcontainer CLI"       'command -v devcontainer'
check "jq"                     'command -v jq'
check "codex CLI"              'command -v codex'
check "Google Chrome"          'test -d "/Applications/Google Chrome.app"'

echo "宿主机配置（容器会从这里派生）"
check "~/.codex/config.toml"                 'test -f ~/.codex/config.toml'
check "~/.claude.json"                       'test -f ~/.claude.json'
check "~/.config/opencode/opencode.json"     'test -f ~/.config/opencode/opencode.json'
check "opencode 配好了 playwright"           'jq -e ".mcp.playwright" ~/.config/opencode/opencode.json'

[ $fail -eq 0 ] && echo "全部通过。" || echo "上面打 ✗ 的先补齐，否则容器起不来。"
```

这些检查是**故意做成硬失败**的 —— 配置派生不出来的话,容器就算起来了 agent 也是
半残的,不如当场报错。

> `devcontainer` CLI 装完之后记得开个新终端,不然 PATH 里没有它。

---

## 2. 跑起来

```bash
devcontainer up --workspace-folder .
```

顺利的话你会看到(节选):

```
host-setup: agent configs generated in .devcontainer/.generated/
host-setup: playwright-mcp starting on 8931 (log: /var/folders/.../playwright-mcp-host.log)
...
setup-agents: agents installed
setup-project: project toolchain ready
setup-agents: opencode serve listening on 0.0.0.0:4096 (log: ...)
```

进容器:

```bash
devcontainer exec --workspace-folder . bash
```

> ⚠️ 不要用 `docker start` —— 它**不触发任何生命周期钩子**,容器会起来但
> opencode server 不会,agent 配置也不会刷新。一律用 `devcontainer up`。

---

## 3. 让它变成你的项目

所有需要改的地方都打了 `⚙️ PROJECT` 标记,一条命令列全:

```bash
grep -rn "⚙️" .devcontainer/
```

| 文件 | 改什么 | 不改会怎样 |
|---|---|---|
| `devcontainer.json` `name` | 项目名 | 只是显示名不对 |
| `devcontainer.json` `features` | terraform / python → 换成你的技术栈 | 装了用不上的东西 |
| `devcontainer.json` `mounts` | **`iac-home` → 你自己的卷名** | **两个项目共用一个家目录,pip 包和 agent 会话全串在一起** |
| `Dockerfile` | `mirror.aarnet.edu.au` → 就近镜像 | apt 慢 |
| `Dockerfile` | `libonig-dev`(ansible 特有)、`bubblewrap`(Codex 特有) | 装了用不上的包 |
| `setup-project.sh` | **整个文件重写** —— 这里放你项目的工具链 | 装了别人项目的依赖 |
| `setup-agents.sh` / `host-setup.sh` | 删掉你不用的 agent | 装/配了你不用的 agent |

那张表里加粗的两行是真会咬人的,其余最多是浪费。

### 加挂载的时候

`mounts` 里每加一条宿主 bind,都要同步加进 `setup-agents.sh` 里 chown 的
prune 列表 —— 否则那条 `chown` 可能去动一个 bind mount,配上 `set -e` 会让整个
创建过程失败。脚本里有 `⚠️ Keep this list in step with` 提示。

---

## 4. 验证装对了

```bash
# ① 宿主的两个服务都在，且都只绑 127.0.0.1
lsof -nP -iTCP:8931 -sTCP:LISTEN; lsof -nP -iTCP:4096 -sTCP:LISTEN
#   期望：两行，地址都是 127.0.0.1:<port>

# ② 容器里的 agent 配置指向宿主，而不是容器自己的 loopback
devcontainer exec --workspace-folder . \
  grep -c host.docker.internal /home/vscode/.codex/config.toml
#   期望：1（Playwright）。得到 0 → 见故障 ③

# ③ 容器能回连宿主的 Playwright
devcontainer exec --workspace-folder . \
  curl -s -o /dev/null -w '%{http_code}\n' http://host.docker.internal:8931/mcp
#   期望：400 或 405（说明连上了）。000 → 宿主 playwright 没起
```

---

## 5. 常见故障

**① `devcontainer: command not found`**
CLI 装在 `~/.devcontainers/bin`,而你的终端会话比 `.zshrc` 那行配置旧。
`source ~/.zshrc` 或开个新 tab。

**② opencode 桌面 app 连不上 / 看不到会话**
先确认 server 活着:`lsof -nP -iTCP:4096 -sTCP:LISTEN`。
没活的话手动拉起(`docker start` 不会做这件事):

```bash
devcontainer exec --workspace-folder . bash .devcontainer/setup-agents.sh --serve
```

app 里要连的是 `http://127.0.0.1:4096`,不是 `localhost` —— Docker 只发布 IPv4,
`localhost` 可能先解析到 `::1`。

**③ 改了配置但容器里没变化**
`.devcontainer/.generated/` 下那几个文件是**单文件 bind mount**,Docker 绑的是
容器启动那一刻的 inode。如果有什么东西**替换**了文件(而不是原地改写),挂载会
静默脱钩,容器会一直读旧内容且不报错。

先重跑一次生成(它保证不换 inode):

```bash
bash .devcontainer/host-setup.sh
```

再用上面验证 ② 检查。还是不对就说明当前容器绑的已经是孤儿 inode,只能重建:

```bash
devcontainer up --workspace-folder . --remove-existing-container
```

`--remove-existing-container` 会让创建期的脚本整套重跑,比较慢。只在
`mounts` 变了、`Dockerfile` 变了、或者踩了这一条的时候才用。

---

## 6. 想知道为什么

上面每一条"照做"的背后都有一段踩坑史 —— inode 挂载、`realPath` 语义、
feature 的构建顺序、`forwardPorts` 为什么是死配置、为什么故意不装
`docker-outside-of-docker`。全在 **[ARCHITECTURE.md](ARCHITECTURE.md)**。

改这套配置之前请先读它。
