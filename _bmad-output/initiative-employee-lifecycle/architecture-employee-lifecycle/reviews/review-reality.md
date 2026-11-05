# 现实核对审核：HAPI 架构 spine 更新

- 日期：2026-11-05
- 对象：`architecture-employee-lifecycle.md` 的 AD-2（HAPI 行）、AD-16、AD-20、AD-22、AD-23；落地方案 `docs/planning/2026-11-05-hapi-architecture-redesign.md`
- 基线：worktree `claude/hapi-architecture-ae7c42`（`3dce31d`）与主检出下的 `remotecc/wsctl/`（`ea80548`）

## 结论

**方向成立，但不能按现文进入实现。** 到期只停 route、推送名单、first-login 绑定保留这些核心判断都得到代码证实。问题在发布与迁移的机制层：有 3 处高严重度问题（迁移步骤自相矛盾、“无变化不重载”推翻现有保护、“一次切换”把多步操作写成原子操作），另有几处“IaC 只管 X”的边界没有和现有代码核对。

## 核对范围与边界

- 已读：两份文档，`ansible/roles/hapi-{registry,control-plane,shared-hub,ingress}`，`scripts/hapi-shared-hub/overlay`，`tests/hapi-workspace`，`hub-hapi.py`、`hub-enforce.py`、`hub-expiry.py`、`hub-terminal.py`、`hub-retire.py`、`hub-onboard.py`、`wsctl`、`wsctl-secrets.py`（只看锁相关部分）、`semaphore/wsctl.sh`，以及管理员手册的相关段落。
- 网页：nginx 官方 control 与 core module 文档、systemd.unit 手册、Cloudflare Access 会话管理文档、KasmVNC GitHub Releases。
- 没有做：未连接 VM500、执行器或 Cloudflare，未读 `settings.json`、BWS、vault。未下载 Kasm 安装包，只发了 HEAD 请求，因此 sha256 和包内文件名没有复核。下文的“代码证实”只代表仓库现状，不代表线上一致。

## 发现

严重程度：**高** = 按现文实施会出故障或无法执行；**中** = 决定建立在未核实或错误的事实上，需改文档或补设计；**低** = 表述不准或小缺口。

### 高

#### H1. 迁移 P1–P3 自相矛盾，P2 没有可执行的部署路径

位置：方案第 8 节、第 4 节目录结构。

1. **P2 无法部署。** 第 8 节要求 P5 之前不能运行 `deploy-hapi-control-plane.yml` 和 `deploy-hapi-shared-hub.yml`，又要求从 P2 起 `hapi-sync` 直接拒绝。但 P2 要“IaC 把三个单元和 Nginx 指向 `current`”。单元只由这两个 playbook 写（`hapi-registry` 只额外写 transport 单元），所以 P2 没有合法的写入路径。
2. **P2 的 Nginx 没有写入方。** 控制面 Nginx 由 `hapi-registry` 按线上路由渲染。`hapi-control-plane` 不带私有路由时渲染的是空路由文件。P2 时 `hapi-registry` 已被封，`hapi-ctl apply` 要到 P3 才接管。
3. **P1 与 P3 的“零差异”不能同时成立。** P1 比对的是当前线上（`alias /usr/local/lib/...`），P2 之后路径变成 `/opt/hapi-control/current/...`。生成器要么有两种路径模式，要么 P1 的比对必须排除路径。方案没有说明。
4. **“代码与线上字节相同”和目录结构冲突。** `hapi-auth.py:413` 读的是 `Path(__file__).parent / 'hapi-login-portal/index.html'`，方案的发布目录却叫 `portal/`。第 4 节的目录清单也漏了 `hapi-hub-config.py`，而第 3 节和 P2 都要求它在 `current` 下。
5. **P2 的员工影响写少了。** 角色的 Hub 单元模板变化会触发 `Restart shared HAPI Hub`。`hapi-hub-transport` 带 `Requires=hapi-shared-hub.service`，会一起重启，Runner 的 9443 连接也会断。方案只写了“鉴权重启一次”。

建议：把 P2 拆成可执行的步骤，写明由谁、用什么命令写单元和 Nginx（例如一次性的迁移 playbook，只写单元，只做 `daemon-reload`）；P1 的比对规则写明路径差异如何处理；发布目录保留 `hapi-login-portal/` 这个名字，或者把 `hapi-auth.py` 的改动单独列为一次版本；清单补上 `hapi-hub-config.py`。

#### H2. “结果没变就直接退出，不重载”推翻了现有的一条保护

位置：方案第 5 节；AD-23“防止路由与 Nginx 指纹错配”。

`hapi-registry/tasks/main.yml` 的注释写明了为什么每次都重载：“a run whose reload failed leaves the file already written, and the next run must still load it”。`hapi-registry.py` 对防火墙也是同样的处理。

按新规则：文件已替换但重载失败后，下一轮比较发现文件没变，就永远不再重载。由于 `config.json` 被鉴权进程实时读取，而 Nginx 里的 `$http_x_hapi_expected_route` 是配置中写死的指纹，该员工的请求会一直返回 409，直到下一次无关变更。到期和续费都会改 `enabled`，也都会改指纹，所以这条路径是日常路径，不是罕见路径。

另外，`nginx -s reload` 只是发信号。nginx 文档说明坏配置时 master 回滚并继续运行旧配置，没有说明发送方能拿到结果；角色注释也记录了“keeps the old routes and still reports success”。

建议：替换文件前写一个“待重载”标记，重载确认成功后才清除；`hapi-ctl` 看到标记就算文件没变也要重载。不要简单地改成每轮重载，那样每 5 分钟留下一批带长连接的旧 worker（见 M6）。

#### H3. AD-22 的“一次切换全部内容”是把多步操作写成了原子操作，`hapi-release` 还破坏 AD-23 的唯一写入口

位置：AD-22、AD-23；方案第 4 节“批准”和“页面、客户端和路由在同一次切换里一起生效”。

1. **软链接只切换磁盘文件。** 方案自己的顺序就是切换 → 重新生成配置 → 重载 Nginx → 重启鉴权。其间存在页面已新、Nginx 还旧的窗口，而这正是 `92c1683`、`a620f00` 修过的那类问题。方案称不再需要新旧路由并存兜底，这个结论没有依据。旧 worker 也会继续处理已打开的连接。
2. **鉴权进程不随软链接切换。** `hapi-stream-guard.py` 和主代码只在启动时加载。页面倒是每次请求都读，而且只有 `ExecStart` 使用不解析的 `current/` 路径时，只改页面的版本才能免重启生效。这个依赖没有写进文档。
3. **“重新生成配置”与 AD-23 冲突。** AD-23 规定派生文件“只由 `hapi-ctl apply` 写入”，输入是名单，调用前必须通过 `require_fresh_catalog`。`hapi-release` 和回滚要重写两份 Nginx 配置，却没有名单输入。这就需要第二个写入模式，或者发布也要读台账并受 D1 可用性约束。两份文档都没有定义。
4. **`flock` 的文件位置未定义。** 锁文件如果放在 `current` 下或版本目录内，新旧版本拿到的就不是同一把锁，必须放在版本目录之外（如 `/run/lock/`），发布切换也要持有它。执行器侧的 `wsctl.lock` 能串行 `enforce` 和 `hapi-release`，但绕过 `wsctl` 的手动运行不受它保护，而那正是方案说 `flock` 要防的场景。
5. **自动回滚依赖的健康检查没有定义。** 现有 `/health` 只返回 `{"status":"prototype","public_ready":false}`，不含版本；verify 只检查匿名 403 和监听端口。`nginx -s reload` 在新 worker 就绪前就返回，配置错误时也没有 `error_log`（两份配置都是 `/dev/null`）。这样的检查在重载失败时大概率仍然通过，发现不了版本未生效，也发现不了已登录路径坏掉。
6. **`Requires=` 的联动没写。** `hapi-control-proxy` 带 `Requires=hapi-control-auth.service`，systemd 手册写明对方被显式重启时本单元也会重启。所以重启鉴权等于完全重启 Nginx，不是“重载 Nginx，再重启鉴权”两个独立步骤。结论（连接会断）不变，但回滚必须覆盖这条路径：鉴权起不来时代理也起不来，整个入口离线。

建议：AD-22 改写为“文件一次切换，服务按定义的顺序生效”，并定义过渡窗口的兼容规则（保留旧路由一个版本）；AD-23 增加 `hapi-ctl render` 这类不带名单、只从本机已有快照重建的模式，或者明确发布也调用 `apply`；定义健康检查：至少比对 `manifest.json` 的版本标记、确认新 worker 已加载、鉴权和代理都在运行。

### 中

#### M1. IaC 边界有四处没有和现有代码核对

位置：AD-22“IaC 只管 VM、软件包、系统用户、单元、`trust.json`、Tunnel 和 Hub 二进制”，方案第 3 节。

1. **`trust.json` 没有任何代码读取。** `git grep` 显示它只被角色写入，用途是触发重启。`hapi-auth.py` 的 `load_config()` 从 `config.json` 取 issuer、audience 和 origin，`render()` 只是 `{**config}` 原样保留。按 AD-22 改 `trust.json` 没有效果，而 `config.json` 又被 AD-23 禁止 IaC 写入。
2. **冷启动是循环依赖。** `hapi-registry.py` 启动时要读已有的 `config.json`、`credentials.json`、`agents.json` 和 nft 文件；`hapi-control-auth` 的 `ExecStartPre` 也要 `config.json`。而 IaC 不再写这些文件，`hapi-ctl` 又要先有版本。VM500 重建时没有初始化路径。方案和 spine 都没有重建顺序。
3. **`employee-firewall` 单元和 `/etc/employee-access.nft` 在公开仓库里没有属主。** 角色和 playbook 里除 `hapi-registry` 外没有写入方，文档引用的 `deploy-employee-mosh-pilot.yml` 已不存在。第 3 节的 IaC 清单里也没有它。
4. **Hub 角色瘦身后仍需要秘密。** 第 3 节把 `hub.env` 和签名密钥留在 IaC，`hub.env` 含 `CLI_API_TOKEN`，二者都来自 BWS，还需要控制端的 `hapi_shared_hub_artifact`。“补上 inventory 和非机密变量”解决不了问题，基础设施部分仍要靠私有运行时 Vault 才能跑。

另外，`hapi-hub-config.py` 的 `migration`、`jwt` 子命令是 Hub 单元的启动门禁。把它移到私有发布后，IaC 的 Hub 单元反过来依赖私有版本，回滚代码也可能影响 Hub 启动。AD-22 的清单里没有这个文件，只有方案有。建议把 `migration`、`jwt` 校验留在 IaC。

#### M2. “最多 5 分钟”只在锁空闲时成立

位置：AD-16，方案第 5 节，Consistency Conventions 的“关机在 5 分钟内生效”。

`wsctl` 的锁默认等待 1800 秒（`WSCTL_LOCK_WAIT`），超时报 `WSCTL_BUSY`。`provision`、`retire`、新增的 `hapi-release` 都持有同一把锁，`--plan-only` 也一样。长任务期间，到期拒绝和退役兜底都可能远超 5 分钟。“5 分钟内自动下线”是推断，不是保证。

建议：改成“下一次 `enforce` 成功时生效，通常 5 分钟内”，并说明长任务会推迟它。

#### M3. `enforce` 自动化放大了两种原本只在手动路径出现的失败

位置：AD-23，方案第 5 节“因此不需要名单校验以外的新保护”。

1. **“名单校验”没有定义，空名单能通过。** `catalog()` 只校验 dict 和 `profile`，`require_fresh_catalog` 只看 `source == 'd1'`。D1 返回合法但空的 `employees` 时，`enforce` 每 5 分钟都会自动删除所有非静态路由，`subject()` 还会在下次登录时清掉 first-login 绑定。之前这只在人工 `hapi-sync` 时才会发生。方案第 11 节放弃缩减保护的理由是“只剩一个通道”，这解决的是并发，没有解决输入错误。
2. **一个重复邮箱阻塞全体。** `hapi-registry.py` 遇到重复邮箱直接退出（`One HAPI route per email`），`load_config` 也拒绝重复。而 `hub-expiry.py` 的注释写着“Several employees may share one administrator mailbox”，与 AD-5“邮箱是唯一外部标识”不一致。在新路径上这会让每一轮推送都失败，所有人的到期拒绝都不生效。关机仍然继续，所以问题不容易被发现。

建议：定义最低保护，例如整份名单为空或比例骤降时拒绝并告警（合法退役走 `hapi-sync`）；明确重复邮箱怎么处理；`ENFORCE_HAPI_PUSH_FAILED` 要进管理员摘要。

#### M4. `enforce` 名单的协议字段不完整

位置：方案第 5 节接口表，AD-23。

- 名单字段是 `id`、`email`、`vmid`、`enabled`，但现有 `hapi-registry` 要 `address`。地址规则 `10.236.<VMID-500>.2` 在 `hub-hapi.workspace_address()`，要么传 `address`，要么在 VM500 再实现一遍。
- 退役失败后，`enforce` 只回收 route。没写清楚 `credentials.json`、`agents.json`、Hub 传输 map 和防火墙规则是否同步回收。如果 `agents.json` 留下旧行，VMID 和地址又已回收（AD-10），要等下一次 `hapi-sync` 才能修正。
- `hub-expiry.expired()` 遇到无效 `paid_through` 的行为没定义。`hub-enforce` 现在是记 `ENFORCE_PAID_THROUGH_INVALID` 后跳过；提取后必须说明 HAPI 这边是报错、拒绝还是沿用。

#### M5. AD-10 的退役顺序与代码和方案不符

AD-10 写“接入（Portal 身份、HAPI Access 放行与 route/credential/agent）→ Terraform VM → BWS → R2 → catalog”。`hub-retire.py` 实际是 catalog 行删掉之后才跑 `hapi-sync`，因为 `sync` 以 catalog 为输入。方案第 5 节的故障表也依赖这个顺序。AD-10 不在本次更新范围，但它和 AD-23 共同定义退役，需要同步改。

#### M6. 平滑重载的长连接后果没写

“只做平滑重载，不断线”本身被 nginx 文档证实：旧 worker 保留已有连接，处理完才退出。但模板没有 `worker_shutdown_timeout`（nginx 文档的默认值为空），远程画面代理的读超时是 1800 秒。每次到期或续费都会触发重载，旧 worker 可能堆积。它们不再接收新连接，所以不影响正确性。

建议：明确接受这一点，或者设置 `worker_shutdown_timeout`（设置后长连接会在超时后被切断，要和“不断线”的说法一起权衡）。

#### M7. “Kasm 升级收拢到一处”不成立

位置：方案第 4 节。

Web 客户端可以收到 `hapi-control/`，但服务端版本钉在 IaC 的多处：`kasmvnc/tasks/packages.yml`、`presentation.yml`、`prepare-employee-desktop.yml`、`employee-workspace/files/desktop-service.py`（都校验 `1.5.0-1`）。移走之后，客户端和服务端变成跨仓库的一对版本，且没有任何门禁保证一致。

上游已发布 1.5.1 和 1.5.2（Releases 页面显示 10 月 24 日），1.5.2 为最新，所以这对版本将来确实会动。现固定的 v1.5.0 资产 URL 仍然有效（HEAD 200，2,653,112 字节）。

建议：改写为“客户端升级收拢到一处，但要与 IaC 的服务端版本配对”，并在 `hapi-release --plan-only` 里检查配对。Stack 表也应补上 KasmVNC 1.5.0 和 Hub 二进制。

#### M8. “规则只有一份”的范围写大了

AD-16 写“‘是否到期’只有一份实现（`hub-expiry`）”。实际上 OCI timer 有自己的判断（AD-9，`services/oci-hub/executor.py` 存快照并在 OCI 上判定），`hub-status.paid_through()` 也单独解析日期。准确的说法是“执行器上 `enforce` 与 `hapi-sync` 共用一份”。这正是 `enforced()` 注释里说的范围，但它是 OCI 快照与电源控制的共用规则，不是全部的比较逻辑。

### 低

- **L1. 第 2 节“用空列表覆盖路由”部分失实。** `hapi-shared-hub` 有 `hapi_shared_hub_agents | length > 0` 和 credentials 非空断言，无法写空列表。`hapi-control-plane` 没有私有变量时会先在 issuer、audience、VMID 断言上失败，只有这些都给了而路由没给才会覆盖。“两个写入方”这个根因成立，具体后果写过了。
- **L2. “VM500 没有公开 inventory”不准确。** `terraform/remotecc/employee-access.tf` 的 `ansible_host` 已把它放进 `employee_access` 组，缺的是 `hapi_control_plane` 组和变量。
- **L3. 第 7 节两项可以从“推断”升级。** `tenantAuth.ts` 的 `credentials()` 每次鉴权都重新读文件，所以 Hub 热加载有源码证据，`test-shared-hub-auth.mjs` 也用了替换文件的模式；剩余待证的只是线上二进制是否由该 overlay 构建。另外，`hub-hapi.registry()` 的临时 inventory 没有 become 密码，说明现有 sudo 是免密的；`terminal.ssh()` 已支持 `stdin`，`read_policy` 已有 `sudo -n` 先例。P0 仍要现场确认。
- **L4. 只写了 `hapi-proxy` 身份的 `nginx -t`。** 第二份配置要用 `hapi-hub` 身份和 `-p /run/hapi-hub-transport/`。现有 transport 校验用的是 root，角色注释指出 root 运行会把临时路径交给默认 nginx 用户，新生成器不要沿用。
- **L5. 测试迁移范围被低估。** 不只 `test-proxy.py`：`test-auth.py`、`test-registry.py`、`test-hub-data.py`、`workspace-browser.mjs` 都绑定角色路径。`test-proxy.py` 同时引用留在 IaC 的 `hapi` 角色文件，迁走后要跨仓库取文件。
- **L6. “失去 GitHub CI”的代价写大了。** `scripts/ci/validate-repository.sh` 和 `.github` 里没有找到运行 `tests/hapi-workspace` 的入口，这些测试看起来一直是手动运行的。实际失去的是 lint、语法检查和 PR 流程。
- **L7. `authorize.inc` 没有归属。** 它是 `nginx.conf` 硬编码 include 的控制面模板，既不在 AD-2 的派生文件列表，也不在 AD-22 的清单里。
- **L8. `wsctl` 接入点没列全。** `hapi-release` 要改 `wsctl` 的三个列表（usage、动作校验、写动作）和 `wsctl-confirm.py` 的映射。要走 Semaphore 还要改 `semaphore/wsctl.sh`（`apply-site` 目前不在那里）。AD-1 说 Semaphore 用 `--approve`，方案只写了 `sudo` 命令行，要说明 `hapi-release` 是否有 Semaphore 模板。
- **L9. 命令名表缺 `enforce`。** Consistency Conventions 的命令名没有 `enforce`，AD-23 却绑定它。
- **L10. `access_enabled` 未体现。** `hub-hapi.sync()` 只在 `access_enabled` 为真时写 Access，注释说员工“被告知后”才放行。AD-20 写“开户时默认都启用”，方案写 `access()` 不变。这个开关的线上值没看（`settings.json` 不在授权范围），要确认二者是否一致。

## 已证实的内容

| 断言 | 证据 |
|---|---|
| 到期员工现在仍能登录 HAPI | `render()` 写死 `enabled: True`；`hub-enforce.py` 只操作电源 |
| `enabled: false` 后立即拒绝并切断连接 | `identity()` 每次请求读配置并检查 `enabled`；stream guard 每 0.25 秒用 `check_lease` 检查，不通过即切断。所以“切断连接”成立，延迟来自推送周期 |
| 到期不释放 first-login 绑定 | `subject()` 用全部路由（含禁用）判断绑定是否有效，只要 route 保留就不释放 |
| 路由指纹覆盖整条路由 | `route_fingerprint()` 和 Nginx 的 `to_json|hash('sha256')` 都是全量；`enabled` 改变会改指纹 |
| `config.json` 不需改格式，`enabled` 已被校验 | `load_config()` 要求 bool |
| CSRF 密钥和 stream lease 在进程内存 | `secrets.token_bytes(32)`；重启后 `guide.js` 每次请求前重新取 `/_workspace/identity`，登录页不会留着过期 CSRF |
| Runner 走 9443 不受鉴权重启影响 | `hapi-hub-transport` 只依赖 Hub，不依赖鉴权 |
| `flock` 串行可行，有先例 | `wsctl-secrets.py` 用 `fcntl.flock` |
| 软链接方案可用 | systemd 单元和 nginx `alias` 都在运行时按路径解析；模板未设 `disable_symlinks`、`open_file_cache`。实现要用临时链接加 rename，保证替换原子 |
| 发布流程可复用 | `git push remotecc-ops`、post-receive 检出到 `/srv/remotecc`、`--plan-only`/`--approve` 都存在 |
| `require_fresh_catalog`、`HAPI_CATALOG_UNAVAILABLE` 存在，D1 不可读时 `enforce` 与 `hapi-sync` 都停止 | `hub-terminal.py`、`hub-hapi.py`、`hub-enforce.py` |
| `enforce` 每 5 分钟运行 | 管理员手册：`*/5 * * * *`（文档证据，线上未核） |
| 退役时 `hapi-sync` 失败只报告 | `hub-retire.py` 记入 state 后继续 |
| 审批哈希引用 `hapi-registry` | `hub-onboard.py:132-133` |
| Access 改策略不让已有会话失效 | Cloudflare 文档：策略变更不实时重评估，到会话过期才复查 |
| 256 人上限 | `hapi-hub-config.py` 和 `tenantAuth.ts` 都是 256 |
| Kasm 固定版本与资产 | URL 有效；`92c1683`、`a620f00` 内容与方案描述一致 |

## 推断写成事实的地方

| 位置 | 表述 | 实际状态 |
|---|---|---|
| AD-22 | “`current` 软链接一次切换全部内容” | 只有文件是一次切换（H3） |
| 方案第 4 节 | “不再需要靠发布顺序和新旧路由并存兜底” | 未证实，窗口仍在 |
| 方案第 4 节 | “这一步取代了 dry run，且只有这一条路径” | 依赖未定义的渲染模式 |
| AD-23 | “Prevents 路由与 Nginx 指纹错配” | 只能缩小窗口，替换和重载之间仍会 409；H2 不修则可能持续 |
| 方案第 5 节 | “最多 5 分钟” | 受锁影响（M2） |
| 方案第 4 节 | “断开几秒后重连” | Hub Web 客户端的重连行为未核，代码里只确认了登录页 |
| 方案第 5 节 | “不需要名单校验以外的新保护” | 校验未定义（M3） |
| 方案第 4 节 | “收拢到一处” | 只有客户端（M7） |
| 方案第 11 节 | “当前 8 台 VM” | 未核（未读运行数据）；不影响结论 |

## 过时内容

本次更新未改到，但与现状不符，建议顺手修：

- AD-2：员工事实所有者写 `catalog.json`，代码和方案都是 D1 为源、本地文件为快照（`hub-terminal.catalog()`）。这一行与方案第 3 节不一致。
- AD-2：BWS 项目 `EmployeeWorkspace-OCIHub` 已改名 `remotecc`（`AGENTS.md`）。
- AD-1：`onboard.sh` 已于 2026-11-04 删除。
- AD-6：`--request` 在 `wsctl` 里是 `--application`。
- AD-15：`remotecc/hapi-admin` 已不存在。
- Structural Seed 和 frontmatter：`remotecc/employee-admin/` 现在是 `remotecc/wsctl/`；新增的 `hapi-control/` 就排在这个过时目录旁边。

## 建议的处理顺序

1. 改 H1、H2、H3，这三项决定方案能否执行。
2. 在 AD-22、AD-23 里补上 M1（`trust.json`、冷启动、防火墙属主）和 M3（名单保护）。
3. 修正 M2、M7、M8 及“推断写成事实”表中的措辞。
4. 第 7 节 P0 增加：线上 `employee-firewall` 的来源、`access_enabled` 的值、catalog 是否存在重复邮箱、Hub 二进制是否由当前 overlay 构建。
