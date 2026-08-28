# 架构说明

这份文档解释这套 devcontainer **为什么**长这样 —— 每个决定背后踩过什么坑、
放弃了什么。想直接跑起来或者把它改成你自己的项目,看 [README.md](README.md)。

单个脚本头部的注释解释它自己在做什么,这里解释它们之间的关系和取舍。

---

## 一、这套配置解决的问题

三件事:

1. **依赖隔离**。terraform / ansible / python 及其一整串传递依赖不装进 macOS,
   版本冲突和残留都关在容器里。
2. **容器作为安全边界**。coding agent 在容器里跑,能碰到的只有挂进去的东西。
3. **界面留在宿主机**。TUI、桌面 app、以及**看得见的浏览器**都在 Mac 上,
   容器里只有 server 和工具链。

第三条是大部分复杂度的来源。容器里的 agent 需要用浏览器,而容器里的浏览器
是看不见的 —— 所以浏览器留在宿主机,agent 通过 MCP 反向驱动它。

---

## 二、三条设计原则

### 原则 1:分清"创建期固化"和"工具执行"

`devcontainer.json` 里的字段分两类,搞混会浪费大量时间:

| 类别 | 字段 | 什么时候生效 |
|---|---|---|
| 创建期固化 | `runArgs` `mounts` `containerEnv` `workspaceMount` | 只在**创建容器**时,改了必须重建 |
| 工具执行 | 生命周期钩子 `remoteEnv` `customizations` | 由 devcontainer CLI 执行 |

推论:`docker start` **不触发任何钩子**,因为钩子是 CLI 执行的,不是 Docker 的概念。
所以启动一律用 `devcontainer up`。

### 原则 2:脚本不能依赖"被谁调用"

服务会把自己的 PATH 交给它执行的每一条命令。生命周期钩子拿到的是探测过的
PATH,裸 `docker exec` 拿到的是容器裸 PATH —— 后者里没有 `~/.local/bin`,
agent 就找不到 ansible。所以 `setup-agents.sh --serve` 自己声明 PATH,不看调用者脸色。

### 原则 3:跨边界时,路径要么完全一致,要么完全不共享

OpenCode Desktop 跑在宿主机,发送的是宿主路径;server 存的是 `realPath()`
解析后的结果。软链会被解析掉,两边永远对不上。详见第五节的同路径挂载。

---

## 三、拓扑

```
  宿主机 (macOS)                          dev container
  ──────────────                          ─────────────
  OpenCode Desktop  ──── :4096 ────────►  opencode serve
  可见的 Chrome  ◄──  playwright-mcp
                        (:8931)  ◄────────  agent (MCP client)
```

两个服务全部只绑 `127.0.0.1`。容器通过 Docker Desktop 的 `host.docker.internal`
反向到达宿主机,所以**没有任何端口暴露到局域网**。

---

## 四、文件清单

| 文件 | 跑在哪 | 什么时候 |
|---|---|---|
| `Dockerfile` | 构建时 | 镜像层:apt 源替换 + 系统包 |
| `devcontainer.json` | — | 配置本身 |
| `host-setup.sh` | **宿主** | `initializeCommand`,每次启动 |
| `setup-agents.sh --install` | 容器 | `postCreateCommand`,仅创建时 |
| `setup-project.sh` | 容器 | `postCreateCommand`,仅创建时 ⚙️ |
| `setup-agents.sh --serve` | 容器 | `postStartCommand`,每次启动 |
| `.generated/` | — | 生成物,不入库 |
| `devcontainer-lock.json` | — | feature 版本锁,自动维护 |

---

## 五、配置逐项说明

### Dockerfile

只做两件事:换 apt 源,装系统包。

换源那段有一条**独立的 `grep` 断言**,替换没生效就让构建直接失败 ——
不要用 `; true` 结尾,那会把"一个文件都没换成功"一起吞掉。三个上游都要换:
arm64 走 `ports.ubuntu.com`,x86_64 主源走 `archive.ubuntu.com` 而安全更新走独立的
`security.ubuntu.com`,漏掉最后一个不会报错,只是慢得莫名其妙。

系统包放这里而不是 `setup-project.sh`:它们不随工作区内容变化,进了镜像层就能被缓存,
容器重建不必再等一次 `apt-get update` —— 那是创建期最慢的一步。

`libonig-dev` 看不出来但必需:`requirements.txt` → `ansible-dev-tools` →
`ansible-navigator` → `onigurumacffi`,arm64 没有预编译 wheel,pip 要现场编译它的
cffi 扩展。删掉它失败会发生在 pip 编译期,报错离根因很远。

### runArgs

只有一条:

```jsonc
"--publish=127.0.0.1:4096:4096"
```

**不要用 `forwardPorts`** —— devcontainer CLI 解析它但从不实现
(devcontainers/cli#22,2022 年至今未修),写了不报错,就是不生效。

绑 `127.0.0.1` 而不是裸 `4096`,否则端口会开到局域网上。

### features

terraform / python / github-cli / node。

**没有任何 coding agent 在这个列表里** —— 它们统一在 `setup-agents.sh` 里,
用各家官方安装脚本装,理由见下一节。

**`docker-outside-of-docker` 是故意不用的。** 它会把宿主的
`/var/run/docker.sock` 挂进来,于是容器里的任何东西都能完全控制 Mac 的
Docker daemon —— 一条 `docker run --privileged -v /:/host` 就是宿主 root。
这跟第一节第 2 条("容器作为安全边界")直接冲突:agent 本该只能碰到挂进去的东西。

而且这个洞是**沉默**的 —— socket 是 feature 自己挂的,不出现在 `mounts` 数组里,
只读 `devcontainer.json` 看不出来。

本仓库确实用不到它:

| 用到 docker 的地方 | 实际在哪执行 |
|---|---|
| `community.docker.*`(rustdesk / anki-api / deepseek-v4 等 role) | **目标主机**,ansible 走 SSH 过去 |
| `scripts/deepseek-v4-*-build.sh` | **llm-server**,脚本头写着 "Usage on the guest" |
要在容器里看宿主容器的话,在宿主终端上敲就行,不值得为此常开这个口子。

### 为什么 agent 不用 feature、也不进 Dockerfile

三个 agent 都用厂商自己的安装脚本:

```
codex     curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh
claude    curl -fsSL https://claude.ai/install.sh | bash
opencode  curl -fsSL https://opencode.ai/install | bash
```

落点分别是 `~/.local/bin`(前两个,已经是 PATH 第一位)和 `~/.opencode/bin`。
**三个都在 `$HOME` 下,也就是 iac-home volume 上,跨容器重建存活。**

这同时解释了为什么不能进 Dockerfile:构建镜像时家目录 volume 还没挂上。
(顺带一提,即便想用 npm 装也进不了 Dockerfile —— feature 是叠在构建完的镜像
**之上**的,`Dockerfile 层 → common-utils → node → python → ...`,
Dockerfile 跑的时候还没有 node。)

不用 feature 的理由:一个脚本用同一种方式装所有 agent,好过"这个用官方 feature、
那个用第三方 feature、还有一个用脚本"。而且厂商脚本装的是厂商当下在发的东西,
不是某个 feature 作者重新打包的版本。

版本**故意不钉**。这些 agent 一周发好几次,而且自己会在运行时更新,
在这里钉版本换来的可复现性,第一次启动就被丢掉了。

opencode 额外在 `postStartCommand` 里再跑一次同一个安装脚本 ——
`--install` 只在建容器时跑,而宿主的桌面 app 会自更新,不每次启动对一下
server 就会落后于 client。安装脚本在已是最新时直接退出,代价是一次版本检查。

### mounts

```jsonc
"source=iac-home,target=/home/vscode,type=volume"
```

家目录用**命名 volume**,不是宿主 bind。理由:`pip install --user`、
agent 的缓存和会话、`~/.local/bin` 里的 ansible 全在这里,几个 GB 级别的
小文件。走 bind 挂到 macOS 上会很慢,而且没有必要 —— 这些都是容器内产物。
注意这个 volume **跨容器重建存活**,所以往家目录写配置的脚本要想清楚:
无条件 `cat > ~/.foo/config` 会把你后来手改的内容悄悄冲掉,而且哪天删掉那段代码,
已经写出去的文件也不会自己消失。

宿主 bind 只挂真正需要共享的:

| 挂载 | 为什么 |
|---|---|
| `~/.ssh` (readonly) | git 推送用宿主的 key,容器里不放私钥副本 |
| `~/.claude` | 认证、记忆、会话历史,宿主容器共用一份 |
| `~/.codex` | 同上 |
| `.generated/*` | 三个单文件覆盖,见第六节 |
| `~/.local/share/opencode/auth.json` | opencode 的 provider 凭据；使用宿主标准路径以兼容 worktree |

#### 同路径挂载

`mounts` 的最后一条是个 WORKAROUND:

```jsonc
"source=${localWorkspaceFolder},target=${localWorkspaceFolder},type=bind"
```

同一个 checkout 挂第二次,挂在它**在宿主机上的那个路径**,于是
`/workspaces/IaC` 和 `/Users/<you>/Projects/IaC` 都是这个仓库。

原因是原则 3:OpenCode Desktop 发送宿主路径,server 存 `realPath()` 结果。
软链会被解析成 `/workspaces/IaC`,存进去的和 app 要的对不上,app 就列不出任何会话。
bind mount 没有东西可解析,读写才一致。等 app 支持浏览远程 server 的文件系统之后
可以去掉(anomalyco/opencode#44150、#44216)。

### containerEnv

只有一个,很克制:

- `HOST_WORKSPACE_FOLDER` —— `setup-agents.sh` 用它算 Claude Code 的历史目录名

**三个坑**:

1. `${containerEnv:VAR}` 只在 `remoteEnv` 里展开,在 `containerEnv` 里会被原样
   写进去。曾经因此把 PATH 写成字面量 `${containerEnv:PATH}`,容器起不来,
   报错是 `sleep: not found`。
2. `remoteEnv` 里的 PATH 是**替换**,不是追加。设了它 `ansible-galaxy` 就找不到了。
3. `containerEnv` 里引用宿主未设置的变量,拿到的是**空字符串**,不是"未设置"。
   `OPENCODE_SERVER_PASSWORD` 因此会启用一个空密码的 basic auth ——
   比不启用更糟。`setup-agents.sh` 里专门 `unset` 掉它。

### 生命周期钩子

```
initializeCommand   宿主   每次启动  ← host-setup.sh（生成配置 + 拉起 playwright）
   ↓ 容器创建 / 启动
onCreateCommand     容器   仅创建时  (未使用)
updateContentCommand 容器  仅创建时  (未使用)
postCreateCommand   容器   仅创建时  ← setup-agents.sh --install && setup-project.sh
postStartCommand    容器   每次启动  ← setup-agents.sh --serve
postAttachCommand   容器   每次接入  (未使用)
```

### 为什么 postCreateCommand 用 `&&` 而不是对象形式

这三个钩子字段都接受**对象形式**,但对象形式的语义是**并行执行**:

```jsonc
// 会并行 —— 这里不能用
"postCreateCommand": {
  "agents":  "... setup-agents.sh --install",
  "project": "... setup-project.sh"
}
```

`setup-agents.sh --install` 里那条 `chown` 要遍历整个 `/home/vscode`,而
`setup-project.sh` 正在往 `~/.local` 里写 pip 包 —— 并行就是竞态。所以用
`&&` 串起来,顺序是确定的:

```jsonc
"postCreateCommand": "/bin/bash .devcontainer/setup-agents.sh --install && /bin/bash .devcontainer/setup-project.sh"
```

`postStartCommand` 起常驻服务时必须 `setsid`,光 `nohup` 不够 ——
某些 devcontainer CLI 版本在生命周期命令收尾时会清理该 exec 的进程组,
`nohup` 只挡 SIGHUP,挡不住组信号。

### customizations

**注释掉了,没有删。** 今天没有任何东西读它:工具链在容器里,界面在宿主机,
容器里的 `.vscode-server` 从 2026-08-06 起没被碰过。里面三个硬编码路径在停用时
都还是对的,要回 VS Code 直接取消注释即可 —— 不然容器里没有 terraform / ansible
的语言支持,Ansible 扩展也找不到解释器和 ansible-lint。

---

## 六、三个 agent 的配置从哪来

宿主配置是**唯一事实来源**。`host-setup.sh` 从它派生出容器视图,
只重写"跨边界会失效"的部分,再用**文件级 bind mount** 精确覆盖过去。

| Agent | 共享的部分(目录 bind) | 被覆盖的部分(文件 bind) |
|---|---|---|
| Claude Code | `~/.claude`(认证/记忆/缓存) | `~/.claude.json` |
| Codex | `~/.codex`(认证/会话/skills) | `~/.codex/config.toml` |
| opencode | — | `~/.config/opencode/opencode.json` |

Codex 那一行是这套做法最清楚的例子:整个 `~/.codex` 目录共享,唯独 `config.toml`
被生成版盖住。auth、history、oauth lock 全都还是宿主那份。

被重写的只有 **`127.0.0.1:8931` → `host.docker.internal:8931`**(Playwright)。
opencode 宿主侧
  那条是 `type: local` + `npx`,没有 url 可改,整条替换成 remote。

三个 agent 都在**全局配置**层面处理完,新项目不写任何项目级文件也能用。

---

## 七、Playwright MCP 在哪里运行

Playwright MCP 运行在宿主机并只监听 `127.0.0.1:8931`，这样它可以驱动可见的
Chrome。容器内的客户端通过 `host.docker.internal:8931` 访问它；详见
`host-setup.sh` 第 2 节。

---

## 八、前置条件

清单和可粘贴的检查脚本在 [README.md](README.md#1-前置条件),不在这里重复。

这里只说**为什么这些检查是硬失败**:`host-setup.sh` 在宿主缺 `jq`、缺 `codex`、
或者 Playwright 配置不完整时会直接 `exit 1`,连带让容器起不来。这是有意的 ——
配置派生不出来的话,容器起来了 agent 也是半残的:MCP 全连不上、浏览器驱动不了,
而这些失败在 agent 那边表现成莫名其妙的工具报错,离根因很远。当场失败便宜得多。

## 九、已知取舍与坑

### 1. 文件级 bind mount 绑的是 inode,不是路径

Docker 在容器启动时把文件挂载绑到当时那个 inode。`perl -i`、`mv`、以及大多数
CLI 的"原子写"都是**替换文件**(新 inode),挂载会**静默脱钩** ——
容器继续读旧内容,不报任何错。

所以 `host-setup.sh` 里的 `publish()` 一律用 `cat tmp > dst`
截断原地写。改这个脚本时别把它换成 `mv`。同理 `setup-agents.sh` 里的 auth.json
是 `install` 复制而不是 symlink。

目录级挂载没有这个问题(每次访问按路径解析)。

### 2. `.generated/` 里有宿主的完整 `.claude.json`

67KB,含 `oauthAccount`、`userID`、`machineID` 和全部项目历史。已经
gitignore、权限 0600。但它现在躺在仓库目录里,容器里任何 agent glob 工作区都会
扫到,备份工具也会。风险不高(`~/.claude` 本来就挂进来了),但心里要有数。

### 3. 三个 agent 都是 `curl | bash` 装的

这是明确的取舍:换来的是"厂商发什么就装什么"和跨重建存活,代价是每次建容器都
从三个厂商域名取脚本并执行。三个域名(`chatgpt.com`、`claude.ai`、`opencode.ai`)
都是各自厂商的主域,但这确实比装一个钉死版本的 npm 包要宽。
Claude Code 的安装脚本还会在 `~/.claude/downloads` 里暂存下载 —— 那是宿主
bind mount,Linux 构建会短暂落在 macOS 的 Claude 目录里,装完它自己删掉。

### 4. 家目录 volume 跨重建存活

删容器不删 volume 的话,`pip install --user` 的产物、agent 缓存、以及**脚本
曾经写进去后来不再写的文件**都还在。清理配置时记得手动删容器里那一份。

### 5. `--remove-existing-container` 很慢

它会让 `postCreateCommand` 整套重跑。只在必须时用 —— `mounts` 变了、
Dockerfile 变了、或者踩了坑 1 需要重新绑 inode。

---

## 十、起来之后逐条验证

```bash
# 1. 两个宿主服务在不在（都应该只绑 127.0.0.1）
lsof -nP -iTCP:8931 -sTCP:LISTEN
lsof -nP -iTCP:4096 -sTCP:LISTEN

# 2. 生成的配置是不是真的被改写了
grep -E 'url = ' .devcontainer/.generated/codex/config.toml
jq -c '.mcp.playwright' .devcontainer/.generated/opencode/opencode.json

# 3. 容器里看到的是不是同一份（不一致就是踩了坑 1，需要重建容器）
devcontainer exec --workspace-folder . \
  grep -c host.docker.internal /home/vscode/.codex/config.toml

# 4. 容器能不能回连宿主的 Playwright 服务
devcontainer exec --workspace-folder . \
  curl -s -o /dev/null -w '%{http_code}\n' http://host.docker.internal:8931/mcp

# 5. 同路径挂载是不是同一份文件（两个 inode 应该相同）
devcontainer exec --workspace-folder . \
  stat -c %i /workspaces/IaC/AGENTS.md "${PWD}/AGENTS.md"

# 6. 服务的 PATH 是否完整（agent 会继承它，缺了就找不到 ansible）
devcontainer exec --workspace-folder . bash -c \
  'tr "\0" "\n" < /proc/$(pgrep -f "opencode serve" | head -1)/environ | grep ^PATH='
```

第 6 条用 `/proc/<pid>/environ` 而不是 `bash -lc echo $PATH` —— 后者是新开的
login shell,PATH 和服务进程的未必相同。

---

## 十一、常用命令

```bash
# 启动 / 接入
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . bash

# 重新生成 agent 配置（容器在跑也能生效，见坑 1）
bash .devcontainer/host-setup.sh

# 完整重建（mounts 或 Dockerfile 改了才需要）
devcontainer up --workspace-folder . --remove-existing-container

# 停止，保留一切
docker stop $(docker ps -q --filter "label=devcontainer.local_folder=$PWD")

# 连家目录一起删（⚠️ pip user 安装、agent 缓存、会话全没）
docker volume rm iac-home
```
