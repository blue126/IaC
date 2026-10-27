# Hindsight 运维指南（pve0 LXC 118）

**2026-10-26现行位置**：同一LXC118已整体冷恢复到pve0（`192.168.1.50`），当前rootfs为 `vmdata:subvol-118-disk-0`（24GiB）。服务IP/API/MCP/控制台、`/opt/hindsight/`目录、原CID/镜像/三个bind及原登录不变，仍手工管理。当前PVE命令在pve0执行；本文明确标注2026-10-10/19的pve1记录保留历史含义。原 source 已退配置，其旧盘已按用户批准清单删除，不能再按旧源启动或回退；正式证据及 PBS 恢复点保留。

本次T0/T1均创建即protected、精确verify与目标读回通过；目标running/onboot1，单机观察实际1810.083秒、31轮原业务检查全部通过，整体24–48小时观察已按用户决定退出本线程职责。118已加入pve0原PBS snapshot作业 `69f0f583-9878-40b2-bd3a-ee6253ef0842`，enabled仍为0；完整前后对象核对确认其他配置及另一作业不变，未触发备份。本次按原实例整体冷备份恢复，未做逻辑导出/导入、重建数据库、下载镜像/模型或重新登录。详见[迁移执行记录](../../_bmad-output/plan-proxmox-consolidation-execution.md)。

**2026-10-19 原说明（历史保留）**

**更新日期**：2026-10-19；**状态**：现行。Hindsight 已于 2026-10-10 从网关搬到 pve1 上的 LXC 118（`192.168.1.118`），Claude Code、Codex、CodeBuddy 已切换到新地址；网关上的旧部署已由用户删除。网页控制台**没有登录**（后端地址已修好，第 10 节）。当天下午万兆交换机故障造成过崩溃重启，已加离线模式和持久模型缓存（第 8.2 节、第 11 节）。Hermes 已接入（第 13 节）。2026-10-19 起嵌入模型是多语言的 `BAAI/bge-m3`，重排走回退链 Mac 上的 eeANE → Voyage → 本地 mmarco（第 8.2 节、第 16 节）。备份由运维方另行规划，本文只记录逻辑导出的方法。架构、网络与未验证边界见 [Hindsight 共享记忆服务架构](../architecture/hindsight-memory-architecture.md)。

> 本文是操作参考，不构成对任何变更的授权。会改变 LXC、容器或客户端状态的步骤（启停、快照回滚、升级、轮换 key、重做 Codex 登录、改端口或防火墙、导出与导入、修改 `compose.yaml`）须先得到用户明确同意；只读检查可以直接执行。pve0 是 Proxmox 集群节点，其上的 `pct`、防火墙和存储操作影响同机的其他来宾，网关承担家庭路由和 PVE 见证，二者的变更都须事先获得明确授权。
>
> 全程不要打印密钥：不要 `cat .env`，不要读取或贴出 `codex/auth.json`，不要运行不带 `--format` 的 `docker inspect` 或 `docker exec … env`，它们会输出环境变量，包括 key。**`docker compose config` 会把 env_file 里的值展开打印出来，其中包含 API key**；语法检查只能用 `docker compose config --quiet`，不要不带 `--quiet` 运行。

## 1. 位置与目录结构

服务当前运行在 pve0（`192.168.1.50`）上的 LXC 118（hostname `hindsight`，`192.168.1.118`），LXC 里用 Docker Compose 管理一个容器 `hindsight`。登录方式：`ssh root@192.168.1.118`（用户已有的公钥，免密），或者在 pve0 上 `pct enter 118`。

部署目录 `/opt/hindsight/`（2026-10-10 核对）：

| 路径 | 作用 | 权限 | 说明 |
|---|---|---|---|
| `compose.yaml` | 服务定义，Compose 项目名 `hindsight`；`network_mode: host`、端口、重排线程数、离线模式、日志轮转等设置 | 644 root | 不含密钥，**不要把 key 写进它**；改动后用 `docker compose up -d` 生效 |
| `.env` | 密钥变量：`HINDSIGHT_API_TENANT_API_KEY`、`HINDSIGHT_CP_DATAPLANE_API_KEY`（两个必须一致），以及重排用的 `HINDSIGHT_API_RERANKER_COHERE_API_KEY`（Mac 上 eeANE 的 key）和 `HINDSIGHT_API_RERANKER_1_LITELLM_SDK_API_KEY`（Voyage） | 600 root | key 只放这里；值不入库、不打印 |
| `data/` | 内置 Postgres（pg0）的数据目录，挂载到容器 `/home/hindsight/.pg0` | 755，属主 UID/GID 1000 | 运行中的数据库目录；不要直接做文件级拷贝当备份 |
| `codex/` | 这台机器自己的 Codex 登录，挂载到容器 `/home/hindsight/.codex`（读写） | 700，属主 1000:1000 | 里面的 `auth.json`（600，1000:1000）是登录凭据，不入库、不打印、不拷到别处 |
| `hf-cache/` | 嵌入与重排模型的缓存，挂载到容器 `/home/hindsight/.cache/huggingface`（约 5 GB：嵌入 bge-m3（约 4.3 GB，含两份权重格式）、回退重排 mmarco-mMiniLMv2-L12，以及不再使用的 bge-small-en-v1.5 和 MiniLM-L6） | 755，属主 UID/GID 1000 | 离线模式依赖它；不要删除或移动，换模型的步骤见第 8.2 节 |

目录里没有 `models/`（重排模型从 `hf-cache/` 加载）和 `backup/`。改 `compose.yaml` 前会留下 `compose.yaml.bak-<时间>`（644 root），验证无误后可以删除。Mac 上的客户端 key 存放在 `~/.hindsight/coding-agent.json` 和 `~/.hindsight/gateway-api-key`（都是 600；后者文件名里的 gateway 是历史遗留）。客户端配置见架构文档的[客户端切换记录](../architecture/hindsight-memory-architecture.md#部署与迁移记录)。

## 2. 健康检查与日常状态（只读）

在 LXC 里执行（`ssh root@192.168.1.118`）；局域网内的 Mac 访问同一地址也可以。

```bash
cd /opt/hindsight

# Container state and image
docker ps --filter name=hindsight --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

# Listeners: expect 0.0.0.0:9077 (API/MCP) and 0.0.0.0:19077 (console); host networking, no port mapping
ss -ltn | grep -E ':(9077|19077)\b'

# Liveness: expect HTTP 200 with "status":"healthy" and "database":"connected"
curl -s -m 8 -w '\nhttp=%{http_code}\n' http://192.168.1.118:9077/health

# Running version: expect "api_version":"0.10.2"
curl -s -m 8 -w '\nhttp=%{http_code}\n' http://192.168.1.118:9077/version

# Auth is enforced on the API: a request without a key must return 401
curl -s -m 8 -o /dev/null -w 'http=%{http_code}\n' http://192.168.1.118:9077/v1/default/banks

# Restart and OOM history (non-sensitive fields only)
docker inspect --format 'oom={{.State.OOMKilled}} restarts={{.RestartCount}} exit={{.State.ExitCode}} started={{.State.StartedAt}}' hindsight

# Codex login: the startup verification line (matching line only; logs can contain memory content)
docker logs hindsight 2>&1 | grep "Codex LLM verified" | tail -1

# Resource use and headroom
docker stats --no-stream hindsight
free -m
df -h /
```

在 pve0 上看 LXC 本身：`pct status 118`、`pct config 118`（只读）。

容器没有配置 Docker 健康检查，`docker ps` 不会显示 healthy，以 `/health` 为准。`/health` 正常只说明进程和数据库连接正常，不证明 LLM 路径可用；LLM 路径看启动日志里的 `Codex LLM verified: gpt-6-luna`，或者做一次带 key 的写入或 reflect（会产生一次 LLM 调用，需用户同意）。

**性能基线（调优记录）**：真实召回约 7~8.4 秒，reflect 约 5 秒，容器内存约 1.1~1.4 GiB（2026-10-10 核对为 1.43 GiB）；客户端 hooks 的超时是 30 秒。耗时明显高于基线时按第 11 节排查。

**带 key 的检查（在 Mac 上）**。下面的函数把 key 通过 stdin 交给 curl，key 不出现在命令行参数和 shell 历史里；后文的导出、导入都用它：

```bash
# Reads the key from its file; the key never appears in argv or history
hs_curl() {
  printf 'header = "Authorization: Bearer %s"\n' "$(cat ~/.hindsight/gateway-api-key)" \
    | curl -sS -m 30 -K - "$@"
}

# Expect http=200; 401 means the key does not match
hs_curl -o /dev/null -w 'http=%{http_code}\n' http://192.168.1.118:9077/v1/default/banks
```

除 `/health` 和 `/version` 外，9077 上的所有接口（含 MCP）都要 `Authorization: Bearer <key>`；19077 上的网页控制台没有登录（第 10 节）。

查看日志：`docker logs --since 10m --tail 100 hindsight`。日志里有 bank 名和召回查询文本，粘贴到聊天、工单或仓库之前先脱敏。日志没有轮转上限（第 11 节）。

## 3. 启动、停止与重启

容器层（在 LXC 的 `/opt/hindsight` 下），均需用户同意：

| 目的 | 命令 | 说明 |
|---|---|---|
| 创建或重建并启动 | `docker compose up -d` | 修改 `compose.yaml` 或 `.env` 后用它让改动生效 |
| 重启 | `docker compose restart` | 不会应用 `compose.yaml` 或 `.env` 的改动；换了 `codex/auth.json` 之后用它（第 7 节） |
| 停止 | `docker compose stop` | 保留容器与数据；`restart: unless-stopped` 下，手动停止后 Docker 重启时也不会自动拉起 |
| 再启动 | `docker compose start` | |

**2026-10-26已验证的正常维护停写**：先只阻止本CT原eth0/.118的tcp9077/19077新连接（独占comment的临时INPUT NEW规则，保留ESTABLISHED/SSH/其他端口），本机用原私有key通道逐页核全bank pending/processing均0，确认原在途请求自然结束；随后使用下列原生停止请求。原镜像的TERM trap有自己的30秒清理，Docker默认10秒截止不足；`--timeout -1`只取消Docker的SIGKILL截止，不改变镜像内部逻辑或restart policy。

```bash
# Inside the current CT118, after original requests and async operations have drained.
docker stop --signal SIGTERM --timeout -1 hindsight
/opt/hindsight/data/installation/18.1.0/bin/pg_controldata /opt/hindsight/data/instances/hindsight/data
```

实际验收同时核对wrapper `All services stopped cleanly`、API `Embedded PostgreSQL stopped`、PG control状态 `shut down`/postmaster.pid不存在、容器exit0/OOMfalse/无restart及无signal9。不能仅以CLI0或镜像内部超时强杀称正常停写。仅撤本次精确INPUT规则并读回原链后sync/正常停CT；恢复使用原 `docker compose -f /opt/hindsight/compose.yaml start`，不up/pull/recreate。此方法已在本次source、隔离target和T1停写实际通过，未改StopSignal/StopTimeout/镜像脚本或持久防火墙。

LXC 层（在 pve0 上）见第 4 节。LXC 配置了 `onboot: 1`，Docker 服务是 enabled，容器是 `restart: unless-stopped`，pve0 或 LXC 重启后预期按原策略恢复；本次维护因应用已manual-stop，三次启动都显式compose start，未独立演练不经manual-stop的自动恢复。

服务不可用期间，客户端的 hooks 和 MCP 会静默跳过，Agent 本身照常可用，但这段时间既不召回，也不写回记忆；网页控制台也随容器一起不可用。客户端已经切换到这里，所以停机会直接影响 Claude Code、Codex、CodeBuddy 的日常使用：提前通知，并选在没有会话进行的时候。启动后约 30 秒 `/health` 才返回 200（部署记录）。

不要使用 `docker compose down -v`、`docker rm -f`、`docker system prune`，也不要删除或移动运行中的 `data/` 和 `codex/`。

## 4. LXC 管理（pve0）

在 pve0 上执行（`ssh root@192.168.1.50`）。这些操作影响整个 LXC，以及（对资源类操作）同机的其他来宾。

```bash
pct status 118                  # running / stopped
pct config 118                  # read-only: cores, memory, net0, rootfs, features
pct enter 118                   # root shell inside the LXC (same as ssh root@192.168.1.118)

pct shutdown 118                # clean shutdown; Docker stops the container first
pct start 118
pct stop 118                    # forced stop, last resort
```

**快照**。当前rootfs为vmdata的ZFS子卷；本次迁移未新增升级快照或执行rollback。以下仍是另行维护时的参考：

```bash
pct snapshot 118 before-upgrade
pct listsnapshot 118
pct rollback 118 before-upgrade     # reverts the whole rootfs, including every memory written since the snapshot
pct delsnapshot 118 before-upgrade
```

快照是存储层的快照，不是文件级拷贝；它给出的是崩溃一致的状态，恢复没有演练过。`pct rollback` 会把整个 rootfs（包括 `data/` 和 `codex/`）回到快照时刻，之后写入的记忆会丢，除非先做逻辑导出（第 9 节）。快照和 LXC 在同一个存储上，不是异地副本。

**备份**。本次T0/T1已由原PBS/root namespace保护并verify，见顶部；118已加入顶部所列原pve0作业，enabled仍为0，其他配置不变。此前2026-10-10的100–109列表属于历史，不能作为当前范围。任何覆盖整个 LXC 的备份都会带上 `.env`（key）和 `codex/auth.json`（Codex 登录）。

**调整资源**（2026-10-10 实测：`pct set 118 --cores 6` 不需要重启 LXC，容器重建后线程数生效）：

```bash
pct set 118 --cores 6           # The node CPU is shared with its other guests
pct set 118 --memory 6144       # MiB; keep the container's mem_limit below this
pct resize 118 rootfs +8G       # grow the 24G rootfs
```

改核数后，同步把 `/opt/hindsight/compose.yaml` 里的 `OMP_NUM_THREADS` 和 `MKL_NUM_THREADS` 改成同样的数，`docker compose config --quiet`，再 `docker compose up -d`；线程数大于可用核数会被限流，反而更慢。改内存后同步 `mem_limit`。召回会因此快多少没有测过；pve0 上的 `funasr` 等来宾也在用 CPU 和内存，先看 `free -m` 和 `uptime`。

不要 `pct destroy 118`：它会连同 `data/` 一起销毁。

## 5. 升级与回滚

这里的升级指换 Hindsight 镜像 tag。升级只改 `image:`，不运行 Ansible，也不使用 `latest`。执行前需要用户明确同意。LXC 内的系统更新（`apt`，包括 `docker.io`）是另一回事：先 `pct snapshot`，因为 runc 等组件的变化可能让容器起不来（第 11 节）。

1. **确认版本和现场。** 记录当前 `api_version`（第 2 节）和镜像身份：

   ```bash
   docker image inspect --format '{{.Id}} {{index .RepoDigests 0}}' ghcr.io/vectorize-io/hindsight:0.10.2
   ```

   阅读当前版本到目标版本之间的上游发布说明（数据库迁移、归档格式兼容、环境变量变化，尤其是 `openai-codex` 提供方和 `HINDSIGHT_API_RERANKER_LOCAL_*` 等设置是否仍被支持）；需要分段升级或新增依赖时先停下说明。确认 `df -h /` 有余量，并选在没有会话进行的时候。
2. **先留退路。** 在 pve0 上 `pct snapshot 118 before-<tag>`；再按[第 9 节](#9-逻辑导出与跨主机迁移)把每个 bank 导出，核对每个 ZIP 非空、数量与 bank 列表一致。没有可用的导出就不升级。
3. **保存旧配置。** `cp -p compose.yaml compose.yaml.bak-$(date +%Y%m%d)`；`.env` 和 `codex/` 不动。验证通过、确认不再需要回退后可以删除这个备份。
4. **改 tag 并拉取。** 把 `compose.yaml` 的 `image:` 改成批准的**具体版本**，其他设置（`network_mode: host`、端口变量、线程数、两个挂载）原样保留；用 `docker compose config --quiet` 做语法检查（不带 `--quiet` 会打印 key），然后先执行 `docker compose pull`。拉取失败就停下，不要继续 `up`。
5. **启动并验证。** `docker compose up -d`；等 `/health` 返回 200，`/version` 的 `api_version` 等于目标版本，日志里再次出现 `Codex LLM verified`；用带 key 的请求确认 bank 数量与升级前一致，再做一次召回，耗时应与基线（约 7~8.4 秒）相当；观察日志（注意脱敏）和 `docker stats` 约 10 分钟，确认没有反复重启、`OOMKilled` 为 false。
6. **更新文档。** 把新 tag 和任何改动的设置同步到[架构文档](../architecture/hindsight-memory-architecture.md)的部署事实和本文示例。

**回滚。**

- 新版本尚未改动数据库（启动即失败、迁移未开始）：把 `image:` 改回旧 tag，`docker compose up -d`，再按第 5 步验证。
- 新版本已经迁移数据库或状态不明：**不要让旧版本直接读取已迁移的 `data/`**（上游是否保证向下兼容未核实）。停止容器，把 `data/` 整体改名保留，例如 `mv data data.failed-$(date +%Y%m%d)`，新建属主 UID/GID 1000 的空 `data/`，用旧 tag 启动，再用升级前的导出按第 9 节恢复。
- 或者在 pve0 上 `pct rollback 118 before-<tag>`：整个 rootfs 回到快照时刻，升级之后写入的记忆会丢。
- 这些路径都没有演练过，需要用户同意。跨版本的导出归档需要版本兼容；升级前先看上游发布说明。

## 6. 轮换 API key

适用于 key 泄露、怀疑泄露或例行更换。轮换期间客户端会收到 401，直到同步新 key，所以需要用户明确同意并提前通知。key 只放在 `.env`（600，属主 root），不要写进 `compose.yaml`。下面的写法让新值只存在于 shell 变量和文件里，不回显、不进命令行参数。

当前 key 出现在这些位置，轮换时都要同步：LXC 的 `/opt/hindsight/.env`（两个变量）、Mac 的 `~/.hindsight/coding-agent.json`（Claude Code 与 Codex 共用）、Mac 的 `~/.hindsight/gateway-api-key`、CodeBuddy 各项目的 MCP 认证头（当前 4 个：IaC、hermes、mcpgateway、llm-ops）；Multica 的任务读同一份 HOME 下的配置，随之更新；Hermes 记忆插件的 `HINDSIGHT_API_KEY` 接入之后才需要。网关上旧部署的 `.env` 里还是旧 key，保留它作回退的话要一并考虑。

1. 在 LXC 里备份当前 `.env`，并生成新值：

   ```bash
   cd /opt/hindsight
   umask 077
   cp -p .env ".env.bak-$(date +%Y%m%d)"
   # Two UUIDs without dashes make 64 hex characters
   new_key="$(tr -d '-' < /proc/sys/kernel/random/uuid)$(tr -d '-' < /proc/sys/kernel/random/uuid)"
   ```
2. 用 shell 内建的 `printf`（内建命令不会把值放进进程参数）重写 `.env` 里的两个变量，**两者必须一致**（网页控制台设计上用 `HINDSIGHT_CP_DATAPLANE_API_KEY` 调用 API，它和 API key 不一致，控制台就会失效）：

   ```bash
   grep -v -E '^(HINDSIGHT_API_TENANT_API_KEY|HINDSIGHT_CP_DATAPLANE_API_KEY)=' .env > .env.new
   printf 'HINDSIGHT_API_TENANT_API_KEY=%s\nHINDSIGHT_CP_DATAPLANE_API_KEY=%s\n' "$new_key" "$new_key" >> .env.new
   mv .env.new .env
   unset new_key
   stat -c '%a %U:%G %n' .env     # expect: 600 root:root .env
   ```
3. `docker compose up -d` 重建容器，再用下面的命令确认容器真的重建了（`StartedAt` 变成新时间）；没有重建时改用 `docker compose up -d --force-recreate`：

   ```bash
   docker inspect --format '{{.State.StartedAt}}' hindsight
   ```

   等 `/health` 返回 200。
4. 同步 Mac 上的 key 文件。下面的命令在 Mac 上执行，值直接从 LXC 写进本地文件，不会显示在终端（文件保持无结尾换行、权限 600）：

   ```bash
   ( umask 077; ssh root@192.168.1.118 "sed -n 's/^HINDSIGHT_API_TENANT_API_KEY=//p' /opt/hindsight/.env" \
       | tr -d '\n' > ~/.hindsight/gateway-api-key.new )
   # Replace the old key file only if the new one is non-empty (a failed ssh must not wipe it)
   test -s ~/.hindsight/gateway-api-key.new \
     && mv ~/.hindsight/gateway-api-key.new ~/.hindsight/gateway-api-key
   ```

   再把新 key 换进 `~/.hindsight/coding-agent.json`，以及 CodeBuddy 各项目的 MCP 认证头（当前 4 个：IaC、hermes、mcpgateway、llm-ops）（编辑配置时不要回显 key）。漏改的客户端会收到 401，表现为拿不到记忆（具体表现取决于客户端）。
5. 验证：不带 key 和带旧 key 都应返回 401，带新 key 返回 200（第 2 节的 `hs_curl`）；各客户端再用自己的一次召回或写回事件确认（切换时就是这样验证的）。确认无误后删除 LXC 里的 `.env.bak-*`（里面是旧 key）。

## 7. Codex 登录的建立与续期

Hindsight 通过内置的 `openai-codex` 提供方访问 Codex 服务，凭据是这台机器自己的 `/opt/hindsight/codex/auth.json`（挂载为容器内的 `/home/hindsight/.codex`，读写）。令牌的刷新由 Hindsight 自己负责，所以这个目录必须可写，属主必须是容器用户的 UID 1000（目录 700，文件 600）。

**原则**：每台机器要有自己的登录。不要拷贝别处正在使用的 `auth.json`（包括 Mac 上自己的 Codex 登录、网关上 `codex-proxy` 的那份）：拷贝出来的登录在刷新令牌轮换后会失效，只有真正在用的那一份会被更新。

**什么时候需要重做**：启动日志里没有 `Codex LLM verified: gpt-6-luna` 这一行，或者写入、归纳、反思开始报认证类错误（具体错误文本没有记录），而 `/health` 仍然正常。

**步骤**（需要用户在浏览器里批准一次设备码，所以不能由 agent 单独完成；不要把令牌内容写进任何地方）：

```bash
# On the Mac: use a throwaway CODEX_HOME so the Mac's own Codex login is neither touched nor copied
tmp="$(mktemp -d)"
CODEX_HOME="$tmp" codex login --device-auth      # the user approves the device code in the browser once

# Install the fresh login on the LXC: mode 600, owner UID 1000 (the container user)
ssh root@192.168.1.118 'umask 077; cat > /opt/hindsight/codex/auth.json.new' < "$tmp/auth.json"
ssh root@192.168.1.118 'chown 1000:1000 /opt/hindsight/codex/auth.json.new && mv /opt/hindsight/codex/auth.json.new /opt/hindsight/codex/auth.json'

# No copy of the login stays on the Mac
rm -rf "$tmp"

# Restart the container and look for the verification line (matching line only)
ssh root@192.168.1.118 'cd /opt/hindsight && docker compose restart && sleep 20 && docker logs --since 2m hindsight 2>&1 | grep "Codex LLM verified"'
```

首次建立的做法（部署记录）：在 Mac 上用临时 `CODEX_HOME` 执行 `codex login --device-auth`，生成的 `auth.json` 放到 LXC，Mac 上的临时副本已删除。上面的命令是据此写出的步骤，没有在这台机器上原样执行过；换登录用的是 `restart`，没有测过是否需要 `up -d --force-recreate`。

## 8. 资源与性能

### 8.1 资源配置（2026-10-19源端记录）

| 层 | 当前配置 | 说明 |
|---|---|---|
| LXC 118 | `cores: 6`（2026-10-10 前是 4）、`memory: 8192`（2026-10-19 前是 4096）、`swap: 512`、rootfs 24G、`cpuunits: 1024` | 调整办法见第 4 节 |
| 容器 | `mem_limit: 6g`（2026-10-19 前是 3g）、`shm_size: 1g` | 没有 `cpus`、`cpu_shares`、`oom_score_adj`（那是网关上为保护其他服务设置的）；bge-m3 比原来的嵌入模型多占约 2.3 GiB；线上实测约 3.3 GiB（2026-10-19 迁移后的 `docker stats`，bge-m3 和常驻的 mmarco 都已加载） |
| pve1 | 6 核 6 线程，内存 32 GB，可用约 8 GB，swap 8 GiB | 同机还有 funasr（12 GiB）、home-assistant、PDM、openbao-testbed×2 和 fileserver LXC；`Windows11`（配置 16 GiB）已停止 |

### 8.2 召回与重排

2026-10-19 起的设置。选型、对比数据和淘汰原因见[重排与嵌入第二轮评估](../architecture/hindsight-rerank-embedding-evaluation-2026-10-19.md)（第一轮见[多语言重排模型评估](../architecture/hindsight-multilingual-reranker-evaluation.md)）。

**嵌入**：`HINDSIGHT_API_EMBEDDINGS_LOCAL_MODEL: BAAI/bge-m3`（1024 维，在 LXC 的 CPU 上每次查询约 80 毫秒）。它的 `max_seq_length` 在模型缓存里从默认的 8192 改成了 1024：文件是 `hf-cache/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181/sentence_bert_config.json`（原来是指向 blob 的符号链接，现在是普通文件）。不要改回 8192：给很长的心智模型生成向量时单进程要 6～7.6 GB，2026-10-19 导入时被 OOM 杀掉过两次。换嵌入模型必须重建全部向量，步骤见第 9 节。

**重排回退链**（`compose.yaml`，从上到下依次尝试）：

| 成员 | 设置 | 说明 |
|---|---|---|
| 0：Mac 上的 eeANE | `HINDSIGHT_API_RERANKER_PROVIDER: cohere`、`..._COHERE_BASE_URL: http://192.168.1.10:18090/v1/rerank`（完整的重排地址）、`..._COHERE_MODEL: bge-m3`、`..._COHERE_TIMEOUT: "5"`；key 是 `.env` 里的 `HINDSIGHT_API_RERANKER_COHERE_API_KEY` | bge-reranker-v2-m3 跑在 Mac 的神经网络引擎上，100 条候选约 2.3 秒。超时按阶段计算（连接、每次读取各 5 秒）；Mac 关机或离开局域网时约 3 秒连接失败，然后交给成员 1。服务的运维见第 16 节 |
| 1：Voyage | `HINDSIGHT_API_RERANKER_1_PROVIDER: litellm-sdk`、`..._1_LITELLM_SDK_MODEL: voyage/rerank-3-lite`；key 是 `.env` 里的 `HINDSIGHT_API_RERANKER_1_LITELLM_SDK_API_KEY` | 约 0.4～0.7 秒；会把候选原文发到 Voyage（美国）。litellm-sdk 重排不使用自己的 TIMEOUT 设置（0.10.2），所以用全局的 `REQUEST_TIMEOUT: "3"` 限制；本机只有这个成员用 litellm |
| 2：本地 mmarco | `HINDSIGHT_API_RERANKER_2_PROVIDER: local`、`..._2_LOCAL_MODEL: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`、`..._2_LOCAL_BUCKET_BATCHING: "true"`、`..._2_LOCAL_MAX_CONCURRENT: "1"` | 100 条候选约 3 秒，常驻内存 |

其他相关设置：

| 设置 | 值 | 作用 |
|---|---|---|
| `HINDSIGHT_API_RERANKER_RETRY_BUDGET` | `"1"` | 远程重排失败后最多再重试 1 秒，避免拖过 Hermes 的 8 秒上限 |
| `HINDSIGHT_API_RERANKER_MAX_CANDIDATES_LOW` | `"100"` | `budget: low`（所有自动召回）最多重排 100 条候选；`mid`/`high` 仍是默认的 300 |
| `OMP_NUM_THREADS`、`MKL_NUM_THREADS` | `6` | 与 LXC 的核数一致 |
| `HF_HUB_OFFLINE`、`TRANSFORMERS_OFFLINE` | `"1"` | 启动时不访问 HuggingFace，只用本地缓存（2026-10-10 起） |

注意：

- **按序号的成员不继承主配置**：第 n 个成员的每项设置都要带 `_n_` 前缀单独写，包括 key。调整回退链的顺序时，`.env` 里 key 的变量名也要跟着改。
- **离线模式与模型缓存**：缓存缺失会让容器起不来，不要删除或移动 `hf-cache/`（起因见第 11 节、架构文档的[事故记录](../architecture/hindsight-memory-architecture.md#网络依赖与已知事故)）。要放入新模型（需用户同意），先在一次性容器里下载到临时缓存（第 8.3 节），再把 `hub/models--<组织>--<模型>` 目录 `cp -a` 进 `hf-cache/hub/` 并 `chown -R 1000:1000`，然后改 `compose.yaml`、`docker compose up -d`。
- **实测记录（2026-10-19）**：客户端参数（`types=[observation]`、`budget=low`、`max_tokens=2000`）下，召回走 Mac 时端到端约 1.8～4 秒，走 Voyage 时约 0.6～0.9 秒；Mac 关机时约 3.5 秒后由 Voyage 完成。

### 8.3 做实验的约束

不要在 LXC 里做会瞬间占用大量内存或 CPU 的实验：它和生产容器共用同一个 8 GiB 的 LXC，实验失控可能触发 LXC 内的内存耗尽，把 Hindsight 一起带走。确实要做，用带 `--memory` 和 `--oom-score-adj` 限制的一次性容器（需用户同意）。这个 LXC 里 `docker run` 同样需要 `--network host`（第 11 节），下面的写法没有在 LXC 里实测：

```bash
# Throwaway experiment container: hard memory cap, first in line for the OOM killer.
# Keep --memory well below the LXC's free memory (check free -m first) and use small batches.
# 1g is enough for small models only: torch + transformers imports take ~0.4 GB, so a 118M-param
# reranker needs ~2g (mmarco peaked at 1.7 GB) and bge-reranker-v2-m3 ~3g (2026-10-10 measurements).
# Loading bge-m3 embeddings next to an import needs ~3.5g; an import of a bank with very long mental models
# OOM-killed at the 8 GiB LXC limit before max_seq_length was capped (2026-10-19).
docker run --rm --network host --memory 1g --memory-swap 1g --oom-score-adj 1000 --cpus 2 \
  --entrypoint python ghcr.io/vectorize-io/hindsight:0.10.2 \
  -c '<small test script>'
```

## 9. 逻辑导出与跨主机迁移

备份由运维方另行规划，本文只记录逻辑导出的方法。

**为什么不拷贝 `data/`**：它是运行中的 Postgres 数据目录，文件级拷贝（`cp`、`tar`、rsync、在线读取的备份）不保证崩溃一致性。逻辑导出由服务自己按 bank 产出 ZIP。LXC 上没有 `backup/` 目录；导出文件放在 Mac 上受保护的目录里（本次迁移用的是 `~/.hindsight-backup-20261007-130513/bank-exports/`，目录 700、文件 600）。

**接口与用法**。下面的请求格式来自迁移时的实际操作（迁移记录）；其余参数和字段含义以本版本的 API 参考和[上游 0.10.1 说明](https://hindsight.vectorize.io/blog/2026/09/22/move-a-memory-bank)为准。命令在 Mac 上运行，`hs_curl` 见第 2 节：

| 操作 | 请求 | 要点 |
|---|---|---|
| 导出 | `POST /v1/default/banks/{bank_id}/transfer/export?include_data=true&include_bank_config=true&include_history=false` | 异步，返回 `operation_id`；轮询 `GET …/operations/{operation_id}`（同一 bank 路径下）直到完成，再从结果里的 `result_metadata.download_url` 下载 ZIP |
| 导入 | `POST /v1/default/banks/{已存在的任意库}/transfer/import?mode=restore&target_bank_id=<新库id>` | multipart，字段名 `file`。路径里的库必须已存在，只用来承载这次操作；真正的目标库由 `target_bank_id` 指定，**必须不存在** |

- **引导库**：因为路径里的库必须已存在，导入前先 `PUT /v1/default/banks/<临时库名>` 建一个临时引导库，导完再把它删掉（请求体和删除方法以 API 参考为准）。
- **范围**：`include_data`（默认开）、`include_bank_config`（默认开）、`include_history`（默认关）。导入取“请求范围”和“归档内容”的交集，请求了归档里没有的内容是静默无操作，所以导入后要核对。
- **成本**：导入在目标端重新向量化，不调用 LLM、不消耗额度。在这个 LXC 上一个库约 25~30 秒（N100 上要 2~3 分钟）。上游说明没有归档大小上限和任务超时，处理大库时留意 `docker stats`（容器上限 3 GiB）。
- `bank_id` 形如 `coding-agent::<项目名>`，放进 URL 时按需编码。

**导出（需用户同意）**

```bash
base='http://192.168.1.118:9077/v1/default/banks'
bank='coding-agent::<project>'    # placeholder: use a real bank id

# 1) Start the export; the response carries operation_id
hs_curl -X POST "${base}/${bank}/transfer/export?include_data=true&include_bank_config=true&include_history=false"

# 2) Poll the operation until it reports completion
hs_curl "${base}/${bank}/operations/<operation_id>"

# 3) Download result_metadata.download_url into a private directory (a later -m overrides the default 30s)
mkdir -p -m 700 ~/<private-export-dir>
( umask 077; hs_curl -m 600 -o ~/<private-export-dir>/"export-$(date +%Y%m%d).zip" "<download_url>" )
```

导出文件含记忆内容且没有加密：目录 700、文件 600。记录 bank、操作 ID、ZIP 字节数和耗时。

**导入与恢复（需用户同意）**。迁移和灾难恢复用同一套步骤：

```bash
# 1) Create a bootstrap bank; it only hosts the operation (request body: see the API reference)
hs_curl -X PUT "${base}/<bootstrap-bank>"

# 2) Import the ZIP into a NEW bank; the target must not exist
hs_curl -m 600 -X POST "${base}/<bootstrap-bank>/transfer/import?mode=restore&target_bank_id=<new-bank-id>" \
  -F 'file=@/path/to/export.zip'

# 3) Poll the returned operation_id until it completes, then verify and delete the bootstrap bank
```

1. **先试跑**：先导入一个临时目标库，核对无误后删除，再导入真正的目标库（Mac 到网关那次就是这样做的）。
2. **核对**：目标库的文档数和事实/观察数与源一致；用几条固定查询在源和目标上各召回一次，比较前 5 名。
3. **目标库已存在时 `restore` 会被拒绝**：换一个 bank id，或在确认其内容可丢弃并获得同意后删除再导入。`merge` 模式按文档粒度合并、不会对事实去重，重复导入同一归档会产生重叠的观察，不要把它当作幂等的恢复手段。
4. **演练**：从网关迁到这个 LXC 已经把导出、导入、核对跑通（见下），但没有对新机器自己的导出文件做过恢复演练。

**本次迁移的做法（网关到 LXC 118，2026-10-10，迁移记录）**

1. 在网关（`http://192.168.1.1:9077`）上对 `coding-agent::hermes` 和 `coding-agent::IaC` 各做一次导出，下载到 Mac 的 `~/.hindsight-backup-20261007-130513/bank-exports/`：`gateway-hermes-to-pve1.zip`（3.7 MB）和 `gateway-IaC-to-pve1.zip`（1.9 MB）。两台主机用同一个 key，所以同一个 `hs_curl` 可以访问两边。
2. 在 LXC（`http://192.168.1.118:9077`）上建临时引导库，用 `mode=restore&target_bank_id=...` 导入；hermes 约 30 秒，IaC 约 25 秒。
3. 核对：hermes 422 条/18 个文档，IaC 420 条/7 个文档，文档和知识页都完全一致；后台整理收敛后 hermes 433 条/19 个文档，IaC 420 条/7 个文档。
4. 把客户端地址改到新机器，各做一次读写验证，确认新写入只进新机器、旧网关没有收到新文档；然后在网关上 `docker compose stop` 旧部署。


**换嵌入模型（`hindsight-admin`，2026-10-19 换 bge-m3 的做法）**

维度变化时 Hindsight 拒绝启动（数据库里的向量维度与模型不符），只能导出、清空、用新模型导入。容器里自带命令行工具 `hindsight-admin`，比 HTTP 接口方便：`export-bank -b <库> -o <zip> --include-history`、`import-bank --archive <zip>`。导入时用当前配置的嵌入模型重新生成向量，不调用 LLM。

1. **演练**（服务照常运行）：用 `docker exec hindsight hindsight-admin export-bank …` 导出一个小库，再在一次性容器里用单独的 pg0 实例（例如 `HINDSIGHT_API_DATABASE_URL=pg0://importtest:55432`，数据目录挂到临时目录，属主 1000）和 `HINDSIGHT_API_LLM_PROVIDER=mock` 试导入，测速度并用召回核对。这份导出只用于演练，不用于正式迁移。
2. **进入维护窗口**：通知用户在迁移期间不要使用 Hermes 和编码 agent（服务停止后客户端的写入会直接失败，不会排队补写）；确认各库 `GET /v1/default/banks/{bank_id}/stats` 的 `pending_operations` 为 0，即后台整理已经完成。
3. **停服务**：`docker compose stop`。从这里开始到第 7 步验证结束，数据库不会再有任何写入。
4. **在服务停止时做最终导出**：逐库运行 `docker compose run --rm --no-deps -v <导出目录>:/exports --entrypoint hindsight-admin hindsight export-bank -b <库> -o /exports/<库>.zip --include-history`（导出目录属主 1000，之后 `chmod 700`，并复制一份到 Mac）。把每个库导出时输出的文档、事实、观察数量记下来，作为第 7 步的核对基准。
5. 把 `data/` 改名保留作回滚（不要删）；建新的空 `data/`（属主 1000:1000）；把新模型放进 `hf-cache/`；改 `compose.yaml`（模型、必要时调 `mem_limit`）。
6. **在服务停止时**逐库导入：`docker compose run --rm --no-deps -v <导出目录>:/archives:ro --entrypoint hindsight-admin hindsight import-bank --archive /archives/<库>.zip --include-history`。服务开着时客户端可能先把空库建出来，导致导入被拒。
7. `docker compose up -d`，核对每个库的数量与第 4 步的基准一致，再用客户端参数召回几次；验证通过后结束维护窗口。
8. 回滚：停服务，换回原来的 `data/` 和 `compose.yaml.bak-<时间>`，`docker compose up -d`。

注意（2026-10-19 实测）：

- 全部 10 个库约 5000 条，导入用了约 45 分钟；单库 35 秒～11 分钟。
- 2026-10-19 实际是在服务停止前约 2 分钟做的最终导出（`docker exec`），中间有一个短暂的写入窗口；上面的步骤改为停服后再导出，以消除这个窗口。`docker compose run` 方式的导出与导入用的是同一套启动流程（导入已实测），但导出这一步本身没有实测过。
- 导入会给每条记忆分配**新的 ID**，也**不恢复操作历史**（审计日志、LLM 请求记录）。
- 心智模型的正文可能有十几万字符；嵌入模型的最大长度过大时，导入会在心智模型这一步被 OOM 杀掉，而且被杀的进程不留错误信息（看 pve1 的 `journalctl -k` 才能确认）。先把 `max_seq_length` 限制好（第 8.2 节）。
- 服务运行时也可以单独补导入一个库：一次性容器设 `HINDSIGHT_API_DATABASE_URL` 指向线上数据库 `postgresql://…@127.0.0.1:5432/hindsight`（连接串在容器里用 `hindsight_api.pg0.resolve_database_url("pg0")` 取得，写进权限 600 的 env 文件，不要打印），加 `--memory` 上限，不会和线上的 pg0 抢数据目录。目标库必须不存在，删除库需要用户同意。

## 10. 网页控制台

- **地址与功能**：`http://192.168.1.118:19077/`（页面标题 Hindsight Control Plane），用来查看库、事实、知识页等（部署记录）。它只用来查看和操作记忆数据；镜像里没有 Mac 上 hindsight-embed 那种带配置向导的“控制中心”，容器配置只能改 `compose.yaml`。
- **没有登录，这是已知风险**：控制台自己不做认证，设计上它在服务端用 `HINDSIGHT_CP_DATAPLANE_API_KEY`（与 API key 同值，在 `.env`）调用 API，所以 9077 上的 key 认证对经由 19077 的访问不起作用。2026-10-10 在这个 LXC 上核对过：不带任何 key 请求 `/api/banks` 返回 HTTP 200 并列出库。这个 LXC 监听 `0.0.0.0`，PVE 防火墙没有生效的规则（`pve-firewall status` 为 disabled），所以局域网内任何设备都能打开这个页面。
- **后端地址（2026-10-10 已修复）**：此前控制台日志是 `[Control Plane] Connecting to dataplane at: http://localhost:8888` 加 `ECONNREFUSED`，`/api/banks` 返回 502——控制台的数据面地址缺省是 8888，而 API 在 9077。现在 `compose.yaml` 里设了 `HINDSIGHT_CP_DATAPLANE_API_URL: http://127.0.0.1:9077`（变量名经生效验证），重建容器后 `/api/banks` 返回 200 并列出 `coding-agent::hermes` 和 `coding-agent::IaC`，数据没有受损。修好之后控制台恢复了“无登录即可读写记忆”的性质，是否收紧见下。

```bash
# Read-only checks (status codes only; do not print the response body)
curl -s -m 8 -o /dev/null -w 'console / http=%{http_code}\n' http://192.168.1.118:19077/            # 307
curl -s -m 8 -o /dev/null -w 'console /api/banks http=%{http_code}\n' http://192.168.1.118:19077/api/banks   # 200: lists the banks without any key
```

**收紧办法（由用户决定，未实施，需用户同意）**

host 网络下不能再用 `ports: 127.0.0.1:19077:9999` 这种写法，可选的办法有两种：

1. **只监听 `127.0.0.1`，用 SSH 隧道访问**：先查清本版本控制台的监听地址设置（本文没有核实具体变量名），改成回环地址后重建容器；之后在 Mac 上 `ssh -N -L 19077:127.0.0.1:19077 root@192.168.1.118`，浏览器打开 `http://127.0.0.1:19077/`，Ctrl-C 关闭隧道。隧道只改变访问方式，不改变控制台没有登录的事实。
2. **用 PVE 防火墙限制来源**：LXC 的 `net0` 已有 `firewall=1`，但要让规则生效，需要先启用数据中心防火墙，再给 LXC 118 写入站规则，只放行需要的来源访问 19077。这是整个集群范围的改动，写规则时必须同时放行 22（SSH）和 9077（客户端），并确认不会切断对 pve0 管理界面和 SSH 的访问，否则会把自己和客户端锁在外面。没有实测。

重建容器期间约 30 秒记忆服务不可用（第 3 节）。收紧之后，从另一台局域网设备访问 `http://192.168.1.118:19077/` 应该连接失败（`curl` 的 `%{http_code}` 为 `000`）。

## 11. 排障

| 现象 | 检查 | 处理 |
|---|---|---|
| 请求返回 401 | 不带 key 返回 401 是预期；用 `hs_curl` 带 key 仍是 401，说明客户端的 key 与 LXC `.env` 中的 `HINDSIGHT_API_TENANT_API_KEY` 不一致 | 按第 6 节同步 key；不要把 key 回显到终端或贴出来 |
| 不小心把 key 打印到了终端、聊天或日志 | 想想是哪条命令：`docker compose config`（没带 `--quiet`）、`cat .env`、`docker inspect`（没带 `--format`）、`docker exec … env` 都会输出；`codex/auth.json` 被贴出同理 | 按泄露处理：key 按第 6 节轮换，Codex 登录按第 7 节重做，并清掉终端滚动缓冲和对应日志 |
| 容器创建失败，报 `open sysctl net.ipv4.ip_unprivileged_port_start file: reopen fd 8: permission denied` | `compose.yaml` 里是否还有 `network_mode: host`；是否被改成了默认桥接网络、加了 `ports:` 或自定义 `networks:`；一次性的 `docker run` 是否漏了 `--network host` | 这是非特权 LXC 里 runc 1.3.4 的限制：容器必须用 host 网络。恢复 `network_mode: host`，删掉 `ports:` 和 `networks:`，端口只通过 `HINDSIGHT_API_PORT` 和 `HINDSIGHT_CP_PORT` 设置 |
| 写入、归纳或反思失败，但 `/health` 正常 | 第 2 节的启动日志里是否有 `Codex LLM verified`；LXC 能否访问互联网；`HINDSIGHT_API_LLM_PROVIDER`、`HINDSIGHT_API_LLM_MODEL` 是否还在 `compose.yaml` | Codex 登录失效就按第 7 节重做；不要从别处拷贝 `auth.json` |
| recall 明显变慢（远高于 7~8.4 秒），或客户端 hooks 超时（30 秒） | `docker stats` 看是否有导入等重负载；`uptime` 和 `free -m` 看 LXC 是否被挤占；pve0 上 `uptime` 和 `qm list` 看同机来宾的负载；`compose.yaml` 里的线程数是否与核数一致 | 负载来自导入就等它结束；线程数与核数不一致就改回一致（第 4 节）；pve0 整体繁忙时与用户商量错峰或调整核数 |
| 网页控制台能打开但读不到数据（502） | 日志里是否又出现 `localhost:8888` 与 `ECONNREFUSED`；`compose.yaml` 里 `HINDSIGHT_CP_DATAPLANE_API_URL` 是否还在、是否指向 `http://127.0.0.1:9077`；API（9077）自己是否健康 | 变量丢了就恢复它并 `docker compose up -d`；API 不健康先按下面几行处理 |
| 局域网内其他设备能打开控制台 | `ss -ltn` 看 19077 是否监听在 `0.0.0.0` | 这是当前设计，风险见第 10 节 |
| 容器日志占用空间增长 | `docker inspect --format '{{.HostConfig.LogConfig.Config}}' hindsight` 应显示 `max-file:5 max-size:20m`；`df -h /` | 日志已按 20 MB × 5 个文件轮转；选项丢了就把 `logging` 恢复到 `compose.yaml` 后重建。日志含记忆内容，清理前注意 |
| `/health` 迟迟不是 200 | `docker logs --tail 50 hindsight`（注意脱敏）；首次启动约 30 秒，升级后的迁移可能更久 | 先等待；日志里有数据库错误时保留日志，不要删除或移动 `data/` |
| 容器反复重启，日志里有 `huggingface_hub` 和 `RuntimeError: Cannot send a request, as the client has been closed` | `docker inspect --format '{{.RestartCount}}' hindsight`；`compose.yaml` 里是否还有 `HF_HUB_OFFLINE: "1"` 和 `./hf-cache` 挂载；`ls /opt/hindsight/hf-cache/hub` 是否有两个 `models--` 目录 | 这是启动时联网检查模型失败（2026-10-10 网络故障时发生过）。恢复离线变量和缓存挂载后 `docker compose up -d`；缓存丢了就按第 8.2 节临时关闭离线开关、确认网络通畅，下载一次后再恢复 |
| 到 LXC、pve0、pve1 的延迟高或丢包，但网关 `.1` 正常 | Mac 上同时 `ping 192.168.1.1` 和 `ping 192.168.1.51`；在 pve1 上 `ping` pve0 和网关；网关上 `dmesg \| grep 'eth2: NIC Link'`、`cat /sys/class/net/eth2/carrier_changes` | pve 之间正常而到网关异常，说明故障在网关 `eth2` 与万兆交换机这段（2026-10-10 的事故，用户重启交换机后恢复），先查交换机，不要动 LXC。详见架构文档的[网络依赖与已知事故](../architecture/hindsight-memory-architecture.md#网络依赖与已知事故) |
| LXC 连不上 | 在 pve0 上 `pct status 118`；`ip -br addr`（用 `pct enter 118`）看 `192.168.1.118/24`；Mac 上 `ping 192.168.1.118` | LXC 没起来就 `pct start 118`（需要用户同意）；起来了仍不通就看 pve0 的 `vmbr1` 和网关 |
| Mac 上 Agent 没有记忆但也不报错 | Mac 是否在局域网、能否访问 `192.168.1.118:9077`；客户端配置是否指向新地址；key 是否一致（第 6 节） | 离开局域网时 hooks 和 MCP 静默跳过，不影响 Agent 本身；回到局域网即恢复。局域网内也连不上时先按上面“延迟高或丢包”一行检查网络 |
| 导入被拒绝，或提示库已存在、库不存在 | 路径里的引导库是否存在（必须已存在）；`target_bank_id` 指定的库是否已经存在（必须不存在） | 见第 9 节：先建引导库，目标库换名或在获得同意后删除 |
| 容器反复重启，或 `OOMKilled` 为 true | `docker inspect` 的状态字段、`docker stats`、LXC 的 `free -m`；pve0 上 `journalctl -k \| grep -i oom` | 容器上限 6 GiB，LXC 总共 8 GiB：减少并发和大批量操作；确认 bge-m3 的 `max_seq_length` 仍是 1024（第 8.2 节）；需要更多内存就按第 4 节调整 LXC，再调整 `mem_limit` |
| 召回比平时慢 2～3 秒，或日志里有 `Reranker member 0 (cohere) failed` | Mac 是否开机、在不在局域网、能否访问 `http://192.168.1.10:18090/health`；Mac 上的 LaunchAgent 状态（第 16 节） | Mac 不在线时自动由 Voyage 完成，不影响使用；Mac 在线仍失败就按第 16 节检查 eeANE |
| 日志里有 `Reranker member 1 (litellm-sdk) failed` | Voyage 的 key 是否还在 `.env` 里（变量名带 `_1_`）；LXC 能否访问互联网 | 第 1、2 号成员都失败时由 mmarco 完成，召回仍可用 |
| 磁盘空间告警 | `df -h /`；`du -sh /opt/hindsight/*` | 先清理过期的升级备份文件；`data/` 和 `codex/` 不要动 |

## 12. 旧部署与网关环境

2026-10-09 至 2026-10-10 Hindsight 部署在网关（`192.168.1.1`）上，2026-10-10 搬走，随后用户自己删除了旧部署。背景和教训见架构文档的[经验教训](../architecture/hindsight-memory-architecture.md#网关旧部署与经验教训)。

- **现状（2026-10-10 核对）**：网关上没有 `/mnt/data/hindsight/`、`hindsight` 容器和 Hindsight 镜像；`codex-proxy` 等其他服务仍在运行。
- **没有回退路径**：旧部署已删除。出问题时的恢复手段是 LXC 上的逻辑导出和 Mac 上的导出文件（第 9 节）。不要把服务放回网关：N100 上重排要 66~68 秒，且内存紧张（见架构文档）。
- **网关的 BusyBox 环境**：iStoreOS 的 BusyBox 比较精简。2026-10-09 核对：`od`、`nohup`、`nproc`、`python3`、`jq`、`diff`、`rsync`、`ss`、`lsof` 均不存在；`netstat`、`openssl`、`curl`、`wget`、`sed`、`grep`、`stat`、`tr`、`cmp`、`unzip`、`tar`、`gzip`、`sha256sum`、`scp` 可用，`printf` 和 `echo` 是 shell 内建。查看监听端口用 `netstat -ltn`；没有 `nohup` 时后台任务写成 `(trap "" HUP; cmd > log 2>&1 < /dev/null &)`；生成随机值用 `/proc/sys/kernel/random/uuid`。2026-10-10 补充：有 `brctl`、`ethtool`、`tcpdump`，没有 `paste`、`bc`、`tc`；`/tmp/hosts` 是个目录。
- **网关的资源**：N100 约 7.9 GB 内存且没有 swap。在网关上做任何占内存的实验之前先看 `MemAvailable` 和 `hermes` 容器的占用，否则可能再次触发整机内存耗尽（见架构文档）。

## 13. Hermes 记忆插件

设计和原因见架构文档的[Hermes 接入](../architecture/hindsight-memory-architecture.md#hermes-接入)。改动前的配置备份：Mac `~/.hindsight-backup-20261007-130513/hermes-pre-hindsight-20261010-215347/`，网关 `/mnt/data/hermes/backup-pre-hindsight-20261010-223902/`。

**文件位置**（`<home>` 是 profile 的 `$HERMES_HOME`：Mac 上 default 为 `~/.hermes`，其他为 `~/.hermes/profiles/<名字>`；网关容器里 default 为 `/opt/data`，homelab-admin 为 `/opt/data/profiles/homelab-admin`）：

- `<home>/hindsight/config.json`：插件配置，600，含 API key（网关上属主必须是 10000:10000）。
- `<home>/plugins/hindsight/`：插件副本；Mac 开发类 profile 的副本里有 `__init__.py.orig`（打补丁前的原文件）。
- `<home>/config.yaml` 的 `memory.provider: hindsight`。

**检查（只读）**

```bash
hermes -p dev memory status          # Provider: hindsight / Status: available
# Which bank a dev-class profile picks: run from inside a repository and look for the template line
cd ~/Projects/IaC && hermes -p dev chat -v --oneshot -q "Reply OK." < /dev/null 2>&1 | grep -E "Hindsight bank|Recall: returned|timed out|sync_turn"
# Gateway container
ssh root@192.168.1.1 'docker exec hermes hermes -p homelab-admin memory status | grep Status'
```

一次 `chat -q` 测试也会被读写类 profile（default、advisor、homelab-admin）写进库，测完按会话 ID 删除对应文档（`DELETE /v1/default/banks/<库>/documents/<会话 ID>`），并检查 Hermes 自带的 `MEMORY.md` 是否被写入了测试内容。

**本地补丁**（Mac 上 dev、analyst、reviewer、orchestrator 的 `<home>/plugins/hindsight/__init__.py`）：

```diff
--- __init__.py.orig	2026-10-10 21:54:09
+++ __init__.py	2026-10-10 22:25:53
@@ -1051,6 +1051,11 @@
         self._config = cfg = _load_config()
         for name in _SESSION_KWARGS:
             setattr(self, f"_{name}", str(kwargs.get(name) or "").strip())
+        # LOCAL PATCH (homelab): Hermes hands `cwd` only from the TUI; kanban workers and the classic
+        # CLI start inside their workspace but pass nothing. Fall back to TERMINAL_CWD (set by kanban
+        # dispatch), then the process cwd, so bank_id_template {project} can resolve.
+        if not self._cwd:
+            self._cwd = (os.environ.get("TERMINAL_CWD") or os.getcwd() or "").strip()
         self._turn_index = self._last_retained_turn_count = 0
         self._session_turns = []
         self._mode = cfg.get("mode", "cloud")
@@ -1742,6 +1747,9 @@
         Removals are not retained."""
         if action not in ("add", "replace") or not content or self._shutting_down.is_set():
             return
+        # LOCAL PATCH (homelab): a read-only profile (auto_retain=false) must not write either.
+        if not getattr(self, "_auto_retain", True):
+            return
         item = self._build_retain_kwargs(
             content,
             context=f"Hermes built-in {target} memory entry",
```

重装或 `hermes plugins update hindsight` 会覆盖补丁。重打办法：在每个开发类 profile 的插件目录里 `cp -p __init__.py __init__.py.orig`，再按上面的 diff 加入两段 `LOCAL PATCH (homelab)` 代码（或用 `patch` 套用上面的 diff），然后用上面的检查命令确认在仓库里能选到 `coding-agent::<仓库名>`。上游合入等效改动后就不再需要这个补丁。

**重启**：Mac 上各 profile 的 gateway 由 default 的多路复用进程承载，`hermes -p <名字> gateway restart` 即可，重启 default 会让所有 profile 的消息通道断开几秒。网关容器里的 gateway 是 s6 监管的前台进程，`hermes gateway restart` 不生效；确需重启时只能重启容器（`docker restart hermes`），会影响 counselor、voice 和 hermes-webui，需用户同意。

**新增 profile 或全面开启项目**：开发类 profile 复制同样的插件、补丁和配置即可；全面开启时开发类不用改配置。读写类 profile 用固定 `bank_id`，并设置 `retain_source` 标明来源。 **注意：从网关 default 复制出来的新 profile 会连 `hindsight/config.json` 一起继承 default 的库和来源标签**（2026-10-14 的 telos 就是这样），复制后要改成它自己的 `bank_id` 和 `retain_source`，并先用 `PUT /v1/default/banks/<库名>` 建库、设好提取说明。

**排障**

| 现象 | 检查 | 处理 |
|---|---|---|
| `memory status` 显示 not available | 网关上看 `config.json` 的属主是否是 10000:10000；`mode` 是否为 `local_external` | `chown -R 10000:10000 <home>/hindsight` |
| 开发类 profile 在仓库里没有项目记忆 | 带 `-v` 运行看 `Hindsight bank` 行：是 `coding-agent::` 说明没拿到目录（补丁丢了），是 `coding-agent::<仓库名>` 但 `Recall: returned 0` 说明该库还不存在 | 重打补丁；库不存在属正常 |
| 日志里 `prefetch timed out after 8.0s` | 服务端 `docker logs` 里 `[RECALL HTTP]` 的耗时；pve0 是否繁忙 | 第 8 节的提速办法；不要提高召回预算 |

## 14. 给新项目启用 Hindsight

启用范围由 Mac 上的客户端配置决定，服务端不需要改动；没有图形界面。2026-10-11 时启用的项目：IaC、hermes、mcpgateway、llm-ops（llm-ops 于当天加入）。改配置前先备份（之前的备份在 `~/.hindsight-backup-20261007-130513/`）。

1. **Claude Code 与 Codex**：把仓库的绝对路径加进 `~/.hindsight/coding-agent.json` 的 `optInPaths`（文件 600，含 key，编辑时不要回显）。全面开启时把 `optInOnly` 改成 `false`，之后任何 git 仓库都自动生效。库名按 `bankIdTemplate` 生成：`coding-agent::<仓库文件夹名>`，worktree 归到主仓库名下；库在第一次写入时自动建立。Multica 读同一份配置，自动跟随。
2. **CodeBuddy**：MCP 地址里写死了库名，每个项目都要单独加，在项目目录里运行（命令从文件读 key，不要手动粘贴）：

   ```bash
   codebuddy mcp add -s local -t http hindsight "http://192.168.1.118:9077/mcp/coding-agent::<项目名>/" -H "Authorization: Bearer $(cat ~/.hindsight/gateway-api-key)"
   codebuddy mcp list | grep hindsight     # expect: ✓ Connected
   ```

3. **Hermes**：不用改。开发类 profile 按所在仓库自动找 `coding-agent::<仓库名>`，库建好之前查到的是空结果，不报错。

## 15. 计划中、尚未实施的操作

Hermes 已接入（第 13 节），网关容器的 gateway 进程未重启，消息通道的第一条消息需要在日志里确认；网页控制台后端已修好，是否收紧访问（第 10 节）由用户决定；万兆交换机和网关 `eth2` 链路故障的根因未确认（第 11 节）。前置条件和状态见架构文档的[实施状态与待办](../architecture/hindsight-memory-architecture.md#实施状态与待办)。这些操作开始之前，本文相应章节需要补充实际步骤和验证结果；状态变化后也要回写。

## 16. Mac 上的重排服务（eeANE，2026-10-19 起）

重排回退链的第 0 号成员。它在用户的 MacBook Air（M4）上运行 [eeANE](https://github.com/xhighhongo41/eeANE) 1.7.0，把 `BAAI/bge-reranker-v2-m3` 编译成 Core ML 模型跑在神经网络引擎上，对外提供兼容 Cohere/Infinity 的 `/v1/rerank`。eeANE 是 GPL-3.0 的个人项目，安装前审阅过源码。

| 项目 | 位置或设置 |
|---|---|
| 地址 | `192.168.1.10:18090`（网关 DHCP 静态分配 `macbook_air`，绑定 Mac 的硬件 Wi-Fi 地址；家里网络的“私有 Wi-Fi 地址”已关闭，否则静态分配会失效） |
| 程序 | `~/.local/share/eeane/venv`（独立的 Python 3.12 环境，只装了 `eeane==1.7.0`，不含编译工具） |
| 模型 | `~/.local/share/eeane/compiled/bge-m3/`：批大小 1，档位 128/192/256/320/384/512，每档约 1.1 GB；另有一个占位用的小嵌入模型（eeANE 要求至少配置一个嵌入模型才能启动，按需加载，平时不占内存） |
| 配置 | `~/.config/eeane/eeane.toml`（600）：`host = "0.0.0.0"`、`port = 18090`、`api_key`（随机生成，同一个值在 LXC `.env` 的 `HINDSIGHT_API_RERANKER_COHERE_API_KEY`）、重排模型 `load_policy = "resident"`、显式列出各档位的路径 |
| 自启动 | LaunchAgent `~/Library/LaunchAgents/local.eeane.reranker.plist`（`RunAtLoad`、`KeepAlive`） |
| 日志 | `~/Library/Logs/eeane.log`（每次请求一行：条数、各档位分布、耗时） |
| 资源 | 常驻约 0.5 GB 内存；冷加载约 27 秒，所以设为常驻 |

```bash
# Health (no key needed): expect "loaded": true for bge-m3
curl -s http://127.0.0.1:18090/health
# Service state and restart
launchctl print gui/$(id -u)/local.eeane.reranker | grep -E 'state|pid|last exit'
launchctl kickstart -k gui/$(id -u)/local.eeane.reranker
# Recent requests: inputs per request, bucket mix, elapsed_ms
grep 'POST /v1/rerank inputs' ~/Library/Logs/eeane.log | tail -5
```

- **从 LXC 验证**：不带 key 请求 `/v1/rerank` 应返回 401；带 key 的验证不要把 key 写进命令行历史（从文件或标准输入读取）。
- **轮换 key**：生成新值，同时改 Mac 的 `eeane.toml` 和 LXC 的 `.env`，然后 `launchctl kickstart -k …` 并在 LXC 上 `docker compose up -d`。
- **停用**（需用户同意）：`launchctl bootout gui/$(id -u)/local.eeane.reranker`；Hindsight 会自动退到 Voyage。要彻底去掉，把 `compose.yaml` 里第 0 号成员删掉、把 Voyage 和 mmarco 的序号前移（`.env` 里 Voyage key 的变量名也要改），再 `docker compose up -d`。
- **重新编译或换档位**：编译需要 `eeane[compile]`（含 torch 2.7、transformers 4.57）和原始模型权重，在临时环境里做：`eeane compile <模型目录> --kind reranker --buckets 128,192,256,320,384,512 --out-dir <目录>`。注意：
  - macOS 27 起神经网络引擎单个模型上限 1 GiB，eeANE 1.7.0 会自动拆分。
  - 不要编译批大小大于 1 的重排模型，eeANE 的服务端只按 1 条喂给重排模型，批量版会报形状不符。
  - 删掉某个档位后，缓存记录里仍登记着它，服务会拒绝启动，所以配置里要显式列出 `[models.artifacts]`。

