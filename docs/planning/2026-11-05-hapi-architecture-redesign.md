# HAPI 架构调整方案

状态：方案已由用户确认，实现另行授权。基于 `origin/main` 的 `3dce31d` 和主检出下的管理代码（只读）。本方案没有登录 VM500、执行器或 Cloudflare 核实现场，需要现场确认的项目列在第 7 节。架构约束见 spine 的 AD-2、AD-10、AD-14、AD-16、AD-20、AD-22、AD-23、AD-24。

## 1. 结论

- **IaC 只管“机器能跑 HAPI”**：VM、网络、软件包、系统用户、systemd 单元、Tunnel。
- **应用代码移到私有仓库的 `hapi-control/`**，打成版本包，用新命令 `wsctl hapi-release` 发到 VM500。切换是一次软链接替换，失败自动切回。
- **名单由执行器推送**：`wsctl enforce`（每 5 分钟）和 `wsctl hapi-sync` 经 SSH 把名单交给 VM500 的 `hapi-ctl apply`，VM500 在本机生成路由、两份 Nginx 配置和防火墙规则。
- **日常路径不再经过 Ansible**。网站不用改，也不新增接口和令牌。
- **到期后拒绝 HAPI 登录**：只停 route，Runner 凭据不动。没有单独的 HAPI 开关。

起初的方向是 VM500 自己拉名单。讨论中取消了人工开关和紧急封禁，到期也只停 route，拉取的主要好处随之消失，所以改为推送。鉴权服务继续读本机文件。

## 2. 现状

日常路径：

```text
wsctl hapi-sync → hub-hapi.py sync()
  ├ catalog()：读 D1，不新鲜就报 HAPI_CATALOG_UNAVAILABLE 停止
  ├ desired()：读 BWS 令牌
  ├ pve_grants()：PVE 9443 双向授权
  ├ registry()：临时 inventory + 加密变量 → ansible-playbook hapi-registry.yml
  │     hapi-registry.py 写 config.json、tokens/、credentials.json、agents.json、nft
  │     同时顺带发布 hapi-auth.py、Kasm 客户端、登录页、两份 Nginx 配置
  └ access()：Cloudflare Access 邮箱策略
```

问题的根源：

1. **同一批文件有两个写入方**。`hapi-registry` 写全部动态文件，`hapi-control-plane` 也写 `config.json`、令牌和控制面 Nginx，`hapi-shared-hub` 也写 `credentials.json`、`agents.json` 和 Hub 传输 Nginx。后两个不带私有变量运行时，会用空列表覆盖路由。
2. **发版混在名单同步里**。改一行登录页要走完整个 `hapi-sync`，发布顺序靠任务排列保证，于是有了 `92c1683`、`a620f00` 这类修复。
3. **VM500 没有公开 inventory**。公开 inventory 里没有 `hapi_control_plane` 这个组，也没有 issuer、audience 等变量；日常用的组只存在于 `hub-hapi.py` 临时生成的文件里。所以 `deploy-hapi-control-plane.yml` 没有私有 inventory 就跑不了。

代码里还有两个现有缺口，这次一并解决：

- **到期员工仍能登录 HAPI**。AD-16 要求到期停用，但代码没有实现：`enforce` 只关 VM，路由一直保留到退役。共享 Hub 在 VM500 上，所以到期员工仍看得到 Hub 里的会话记录。
- **退役时的 `hapi-sync` 失败只报告**，路由会留在 VM500。新设计里 `enforce` 每 5 分钟推送一次名单，5 分钟内自动下线。

## 3. 分界线

判断标准：**换一名员工或改一行页面时要不要动它**。不用动的是基础设施；要动的就不属于 IaC。这和“容器归仓库，容器里的业务不归仓库”是同一条线。

| 内容 | 归属 | 变化时走哪条路 |
|---|---|---|
| VM500 本身、网络、磁盘（`terraform/remotecc/employee-access.tf`） | IaC / Terraform | PR |
| 软件包、系统用户、目录、`systemd` 单元、`trust.json`（issuer、audience、origin、Hub 监听地址；`hapi-ctl` 据此生成 `config.json` 中的同名字段） | IaC / `hapi-control-plane`（瘦身后） | PR + `--check --diff` |
| Hub 用户、单元、二进制、`hub.env`、签名密钥、`hapi-hub-config.py`（留在 `/usr/local/lib`，Hub 单元不变） | IaC / `hapi-shared-hub`（瘦身后） | 同上 |
| Tunnel 连接器 | IaC / `hapi-ingress`（不变） | 同上 |
| 员工 VM 上的 Runner 等 | IaC / `hapi` role（不变，随开户） | 不变 |
| `hapi-auth.py`、`hapi-stream-guard.py`、登录页、Kasm 客户端、Nginx 模板（含 `authorize.inc`）和生成逻辑、`hapi-registry.py`（改名 `hapi-reconcile.py`）、`hapi-ctl` | 私有 `hapi-control/` | `wsctl hapi-release` |
| 员工名单、到期日 | D1 | `enforce`、`hapi-sync` 推送 |
| 令牌、Hub 凭据 | BWS | `hapi-sync` 推送 |
| PVE 9443 授权、Access 邮箱策略 | 执行器 | `hapi-sync` |

Hub 二进制和校验器这轮不动：Hub 有状态，带迁移和签名门禁，很少升级，迁走收益小、风险大。这样 Hub 单元不用改，迁移也不会重启 Hub。

Cloudflare 目前没有 Terraform 资源，Access 应用和 Tunnel 是手工配置的。把它们纳入 Terraform 是另一件事，本方案不做。

瘦身后，`hapi-control-plane` 和 `hapi-shared-hub` 不再写任何路由、令牌或名单文件，第 2 节的覆盖风险随之消失。`hapi-registry` 角色和 playbook 删除。公开仓库需要补上 VM500 的 inventory 和非机密变量，否则基础设施部分依然跑不起来。

## 4. 应用代码的版本与发布

### 放在哪

放现有私有仓库里，不新建仓库：Mac 上是 `~/Projects/IaC/remotecc/hapi-control/`，与 `wsctl/`、`apply-site/` 同级；推送到执行器后检出到 `/srv/remotecc/hapi-control`；VM500 上只有发布出来的 `/opt/hapi-control/`，没有 Git。理由：

- 符合“业务逻辑不进 IaC”的既定边界。
- `hapi-sync` 和 `hapi-ctl` 在同一个仓库，一次提交能改完接口两端。

代价是失去 GitHub CI 和 PR 流程。替代做法与网站代码相同：Mac 上跑测试，`--plan-only` 时在 VM500 上做 `nginx -t` 和 `--check`，需要时用 Codex 审 diff。`tests/hapi-workspace/` 中相关测试随代码迁移，`test-proxy.py` 目前依赖 Ansible 模板，要改成调用新的 Python 生成器。

### 版本和目录

```text
/opt/hapi-control/
  releases/<git短哈希>/   # hapi-auth.py、hapi-stream-guard.py、hapi-reconcile.py、hapi-ctl、
                          # hapi-login-portal/、kasm/、templates/、manifest.json（文件 sha256、支持的 schema）
  current -> releases/<git短哈希>
```

- 版本号就是 Git 提交，不另设语义版本。这和 Hub 现有的 `/opt/hapi-shared-hub/<sha256>/` 做法一致。
- Kasm 客户端打包时从固定地址下载、校验 sha256、解出静态文件。现在升级要同时改角色和 Nginx 模板里的多处，之后收拢到一处。
- 不做 deb 包或容器：一台机器、几个文件，压缩包足够，也不用装新东西。

### 发布

沿用 `apply-site` 的模式，由人触发，不自动发布。这里加一个 `wsctl` 动作，因为它能直接复用 SSH 密钥物化、运行锁和“计划 → 批准”。不并入 `hapi-sync`：`hapi-sync` 会在开户和退役里自动运行，并进去就等于代码会被悄悄发布。

```bash
git push remotecc-ops HEAD:main                              # 部署到执行器：wsctl 立即更新，VM500 不变
sudo /srv/remotecc/wsctl/wsctl hapi-release --plan-only      # 在执行器上运行
sudo /srv/remotecc/wsctl/wsctl hapi-release --approve <SHA>
```

1. 计划：打包，上传到 `releases/` 的暂存目录，校验 sha256，用候选代码生成配置，跑 `nginx -t`（以 `hapi-proxy` 身份）和 `hapi-auth.py --check`，输出线上版本、目标版本、配置差异、是否需要重启鉴权服务。线上不变。这一步取代了 dry run，且只有这一条路径，不会再出现“改错角色”。
2. 批准：VM500 上的 `hapi-ctl activate` 持锁完成：渲染并校验候选配置 → 切换软链接 → 替换配置 → 重载 Nginx → 如有需要重启鉴权服务 → 健康检查。审批 SHA 覆盖版本和包内容，不覆盖名单，所以期间的到期或续费不会让批准失效。
3. 健康检查失败时，在同一把锁内切回上一版。健康检查指两个服务运行中、`hapi-auth.py --check` 通过、未带身份访问本机入口得到 403 而不是 5xx。

切换过程中页面、Nginx 和鉴权进程可能短暂不一致，所以相邻两个版本必须能共存，不能共存的改动分两次发布。`activate` 不需要名单，D1 不可用时也能发布和回滚。

协议变更的顺序：先发布兼容新旧 `schema` 的 `hapi-ctl`，再推送新 `wsctl`。

**重启的影响**：所有浏览器流量都经过鉴权进程内的 stream guard，CSRF 密钥和 stream lease 也在进程内存里。所以改了 Python 的版本重启时，所有在线员工的 WebSocket 会断开几秒后重连。Runner 走 9443 的 Hub 传输，不受影响。只改页面或 Nginx 的版本只做平滑重载，不断线。

### 回滚

`wsctl hapi-release --rollback <版本>`，走同样的计划和批准，VM500 保留最近 5 个版本。回滚只换代码，不动名单、令牌和 SQLite；目标版本不支持当前 `schema` 时在计划阶段拒绝。约束：新版本必须能和上一版共用同一格式的 `config.json`，要改格式就分两次发布，和网站迁移规则相同。

## 5. 员工名单怎么送到 VM500

### 接口

VM500 上只有一个写入入口：

```text
sudo /opt/hapi-control/current/hapi-ctl apply    # stdin 传 JSON，不落盘
```

| 调用方 | 时机 | 内容 |
|---|---|---|
| `wsctl enforce` | 每 5 分钟 | 名单，不送空名单 |
| `wsctl hapi-sync` | 开户、退役、每日、手动 | 名单 + 全部令牌 |

载荷固定为 `{schema, static_ids, employees: [{id, email, address, enabled}], tokens?}`，只由 `hub-hapi.roster()` 构建，它不访问 BWS。`hapi-ctl` 遇到不支持的 `schema` 或未知字段直接拒绝。

`hapi-ctl apply` 内部就是现有的 `hapi-registry.py` 逻辑，再接手原来 Ansible 做的 Nginx 生成和重载：

- 结果没变就直接退出，不重载。替换前写 `/run/hapi-control/pending`，重载全部成功才清除；标记存在时即使内容没变也要重载，保留现有“上次重载失败下次补上”的保护。
- `config.json` 格式不变，鉴权代码不用改。要改一处：`render()` 现在把 `enabled` 写死为 `true`，要改成取名单的值。路由指纹覆盖整条路由，所以 `config.json` 和 Nginx 必须从同一份路由快照生成。
- 候选文件全部校验通过后才替换，`nginx -t` 通过才重载。
- 名单里有但本机没有令牌的员工不生成路由，新员工在令牌送达前不会出现半成品。
- 只有带令牌的调用才回收令牌：既不在令牌列表、也不在名单、也不在 `static_ids` 里的 ID 才删。`enforce` 永远不删令牌。
- VM502 的处理和现在相同：执行器的 `static_routes` 不变，继续随调用传 `static_ids`，静态路由保持原样。
- `apply` 和 `activate` 共用一把 `flock`（`/run/hapi-control/lock`），等待最多 30 秒，防止发版和名单推送撞车。`wsctl` 的运行锁也会串行执行器上的命令。
- `enforce` 的推送限时 60 秒，失败不影响关机。

### 到期判断

规则只有一份：把 `hub-enforce.py` 里的比较提取成 `hub-expiry.expired(row, now)`，`enforce` 和 `hapi-sync` 都调用它。`enforced(row)` 为真且当前时间晚于 `paid_through` 时，`enabled` 为 `false`。

- 下一次成功的 `enforce` 拒绝登录并切断连接，与 VM 关机同一轮，通常 5 分钟内。`wsctl` 运行锁被长任务占用时会推迟。
- 续费后同样在下一次成功的 `enforce` 恢复，与 VM 开机同一轮。
- 需要紧急停用某人时，管理员手工关闭其 VM，`enforce` 不会把手工关闭的 VM 开回来。此时员工仍能打开 HAPI 页面和 Hub 里的会话记录，但 VM 上做不了事。
- 到期不释放 first-login 绑定，续费后仍是同一身份。
- Runner 凭据不动。VM 已关机，Runner 离线。
- 名单推送失败不影响关机，记为 `ENFORCE_HAPI_PUSH_FAILED`，下一轮重试。

### 故障时

| 场景 | 行为 |
|---|---|
| 正常退役 | `retire` 里的 `hapi-sync` 立即推送 |
| 退役时 `hapi-sync` 失败 | 下一轮 `enforce` 推送名单，路由 5 分钟内下线。令牌、PVE 授权和 Access 邮箱由每日 `hapi-sync` 清理；已下线的路由使这些残留无法用于登录 |
| D1 不可读 | `enforce` 和 `hapi-sync` 都按现有规则停止，名单冻结：在册员工照常使用，新变化暂不生效 |
| 执行器宕机 | 同样冻结，到期判断推迟，VM 关机也一样推迟 |
| VM500 不可达 | 推送失败并报告，恢复后下一轮补上 |

原有的 `require_fresh_catalog` 继续有效：执行器读不到新鲜台账就不写 VM500，因此不需要名单校验以外的新保护。

## 6. `hapi-sync` 之后做什么

```text
wsctl hapi-sync（开户、退役时运行，Semaphore 每日一次）
  ├ catalog + require_fresh_catalog   # 不变
  ├ pve_grants()                      # 不变
  ├ ssh VM500 sudo hapi-ctl apply     # 取代 ansible-playbook hapi-registry.yml
  └ access()                          # 不变
```

- **PVE 9443**：不变，留在执行器，因为需要 PVE 权限，而且只在开户和退役时变化。
- **Cloudflare Access**：不变，留在执行器，因为令牌有 Access 编辑权限，不能放 VM500。Access 只是外层，真正的撤销在 VM500：Access 策略改了，已签发的 JWT 不会失效，而路由下线会立刻拒绝。

## 7. 需要现场确认的事项（P0）

| 事项 | 为什么重要 | 如果不成立 |
|---|---|---|
| Hub 是否热加载 `credentials.json` | `hapi-registry` 写完后不重启 Hub 却能用，推断是热加载，但二进制我没验证 | 新员工令牌生效方式要调整 |
| 执行器到 VM500 的 SSH sudo 能否直接跑 `hapi-ctl` | 现在经 Ansible `become`，应当可以 | 需调整 sudo 规则 |
| VM500 的 Python 版本和现有依赖 | 生成器不能引入新软件包，Nginx 模板要改成纯 Python 生成 | 调整实现 |
| 当前有哪些员工已到期 | P4 生效时他们会立即被拒绝登录 | 先续费或通知 |
| `oci_hub.hapi.access_enabled` 和 `static_routes` 的实际值 | 执行器上的 settings 没有读过 | 调整迁移细节 |

## 8. 迁移步骤

每一步都单独授权。P2 到 P3 之间冻结开户和退役，`wsctl` 先发一个让 `hapi-sync` 直接拒绝的版本，开户、退役里的自动调用也一样，否则旧同步会绕过新路径重写配置。

| 步骤 | 内容 | 员工影响 | 回滚 |
|---|---|---|---|
| P0 现场核实 | 只读确认第 7 节各项；清点未完成的 `provision` 计划，P2 改角色后它们的审批哈希失效，要先做完或重新批准 | 无 | 无需 |
| P1 影子比对 | 建 `hapi-control/`，发布到 `/opt/hapi-control`，服务不切换。用 `hapi-ctl apply --check` 比对线上文件，除代码路径外差异必须为零 | 无 | 删目录 |
| P2 切换代码路径 | 合并瘦身后的 IaC 角色（不再写动态文件），先 `--check --diff` 再运行，把鉴权单元指向 `current`；再用 `hapi-ctl activate` 写入指向 `current` 的 Nginx。代码内容与线上相同。从此两个 deploy playbook 不会再覆盖路由 | 鉴权重启一次，在线 WebSocket 断开几秒后重连，建议放在没人在线的时段。Hub 不重启 | Git 回退角色重新运行，旧文件保留到 P5 |
| P3 接管写入 | `hapi-sync` 改走 `hapi-ctl apply`，此时 `enabled` 恒为 `true`。首次运行必须是“无变化”，这是等价性的证明。解除冻结 | 无 | settings 切回旧路径（保留开关到 P5） |
| P4 到期生效 | `enforce` 开始推送，`enabled` 按到期计算 | 已到期员工被拒绝登录 | `enabled` 改回恒为 `true` |
| P5 验收清理 | VM502 全流程登录，用测试员工走一次增删和到期续费。观察一周后删 `hapi-registry`、更新文档，确认全部引用已切换后再删 `/usr/local/lib` 下的旧应用文件（`hapi-hub-config.py` 保留） | 无 | Git 回退 + 重新发布 |

P5 之后再做一步 **P6：VM502 转为普通员工 VM**。用户不需要保留 Hub 里 `vm502` 名下的旧会话，所以 VM502 改用员工 ID，重新配置其 Runner 和令牌，然后删除 `static_routes`、`static_ids` 和所有相关例外。放在最后，是因为 P1 到 P3 靠“结果和现在完全相同”证明没改坏。员工影响：只有 VM502 的旧会话不再可见。回滚：恢复 `static_routes` 和原 Runner 配置。

旧 noVNC 路由的清理由原 session 负责，改的是同一批文件。最好在 P1 之前完成；如果来不及，等 P3 之后作为第一次 `hapi-release` 发布，这样也顺便演练一遍发布和回滚。

## 9. 落地时要改的文档

真实部署路径按新路径写，和实现一起提交：

- 完整说明写进 `remotecc/wsctl/README.md`，并更新管理员手册 3.15 和第 6 节。
- `hapi-control-plane` 和 `hapi-shared-hub` 各加一行指向说明。原定的 `hapi-registry` 角色会被删除，指向改放在 `hapi-shared-hub`。
- 更新 `docs/guides/hapi-unified-entry.md`、`docs/architecture/remotecc-layout.md`，以及 `AGENTS.md` 中关于 `hapi-sync` 的描述。
- `hub-onboard.py` 里审批哈希引用了 `hapi-registry`，一并改掉。

## 10. 用户决定

- 到期后拒绝 HAPI 登录，只停 route，Runner 凭据不动。
- 没有单独的 HAPI 开关，也没有紧急封禁。
- 名单由执行器推送。拉不到台账时名单冻结，不拒绝员工。
- `hapi-ctl` 留在 VM500：执行器决定名单，VM500 负责把配置改好。
- VM502 转为普通员工 VM，不保留 Hub 里的旧会话。
- 紧急停用某人时直接关 VM。
- VM500 损坏时靠 VM 级备份恢复，从零重建是备用方案，这轮不做。
- 维护说明面向将来的自己，放 `docs/architecture/`，必须有图，不做幻灯片。

## 11. Codex 审核处理（2026-11-05）

审核针对的是拉取版本，共 9 条。

| 条目 | 处理 |
|---|---|
| `enabled` 写死、旧写入入口、`hapi-hub-config.py` 路径、first-login 绑定 | 采纳，已写入上文 |
| 缩减保护挡住合法退役、拉取推送并发、令牌回收协议 | 改为推送后不再成立：只剩一个通道，令牌和名单一次送达 |
| VM502 映射 | 不再成立：`static_routes` 不搬家 |
| 员工人数上限 | 不采纳：它把名单的时间上限误读成人数上限，256 人远高于当前 8 台 VM |

## 12. 架构评审处理（2026-11-05）

spine 过了格式检查和三份独立评审（规则、现实核对、对抗）。

| 问题 | 处理 |
|---|---|
| 发版要重写 Nginx，却不在唯一写入口内 | 加 `hapi-ctl activate`，与 `apply` 共锁 |
| `wsctl` 和 `hapi-ctl` 版本错位 | 新增 AD-24：`schema`、发布顺序、回滚检查 |
| 无变化就退出会丢掉重载重试 | 加 `pending` 标记 |
| 两种名单形状、VM502 令牌被删 | 只保留 `roster()`；回收时排除 `static_ids` |
| “一次切换全部内容”是推断 | 改写切换过程，要求相邻版本共存 |
| 迁移步骤自相矛盾 | P2 先合并瘦身角色，明确部署命令和比对规则 |
| `hapi-hub-config.py` 归属不清 | 留在 IaC，Hub 单元不用改 |
| `trust.json` 无人读取 | `hapi-ctl` 据此生成 `config.json` |
| AD-10 顺序、残留无人清理 | 改删除顺序，加每日 `hapi-sync` |
| 合法空名单误删路由 | `enforce` 不送空名单 |
| 取消紧急封禁的理由不成立 | Access 手改会被覆盖，也不影响已签发 JWT。用户决定：紧急时直接关 VM |

不采纳：

- **单行隔离和共用邮箱**：网站的 `catalogDocument` 已拒绝重复邮箱，D1 里不会有共用邮箱。坏数据让台账读取失败时按冻结处理。
- **`generation` 排序保护**：只剩一个写入方，`wsctl` 运行锁已串行。
- **VM500 从零重建**：不在本轮范围，列入 Deferred。VM502 改走普通路径已由用户决定，放在 P6。

限制：规则和对抗评审按 `docs/agent/bmad-review-routing.md` 本应走 PAL 跨模型通道，这个 session 没有 PAL 工具，实际由 Claude 子代理完成，不算跨模型审核。
