# 架构 spine 审核报告：HAPI 更新（2026-11-05）

- **对象**：`architecture-employee-lifecycle.md` 的 AD-2（HAPI 行）、AD-16、AD-20、AD-22、AD-23；`docs/planning/2026-11-05-hapi-architecture-redesign.md`（下称“方案”）
- **对照**：`ansible/roles/hapi-*`；私有 `remotecc/wsctl/` 的 `hub-hapi.py`、`hub-enforce.py`、`hub-expiry.py`、`hub-retire.py`，以及为核实调用关系读的 `wsctl`、`wsctl-secrets.py`（只看锁逻辑）、`oci-hub-admin.py`、`hub-status.py`、`hub-publish.py`、`hub-terminal.py`、`services/oci-hub/executor.py`
- **边界**：只读，没有连接线上。没有读 settings.json、BWS、vault 或凭据，所以 `access_enabled`、`static_routes` 的实际取值、VM500 现场状态都没有核实。

## 结论

**有条件通过：方向对，上一层的分歧（谁写 VM500、发版和名单混在一起）确实修好了；但新设计把分歧下移到了四个接缝上，spine 还没定规则，应先改 spine 再进实现。**

这四个接缝是：发版时谁重新生成配置（F1）、`wsctl` 与 `hapi-ctl` 版本错位（F2）、“派生文件”里没有上游的部分（F3）、“没变化就退出”破坏自愈（F4）。另外 AD-10 没有跟着改（F5），它正是你要求重点看的冲突之一。

| 严重程度 | 数量 | 编号 |
|---|---|---|
| 高 | 4 | F1–F4 |
| 中 | 7 | F5–F11 |
| 低 | 9 | F12–F20 |

## 按清单判断

| 检查项 | 判断 | 说明 |
|---|---|---|
| 是否修好下一层真实分歧点 | 大部分 | 写入方唯一、发版与名单分离、到期判断落到 `enforce`，这三点都对准了真实问题。新分歧见 F1–F4 |
| 每条 AD 的 Rule 可执行且能防住所述分歧 | 部分 | AD-23 防不住“路由与 Nginx 指纹错配”（F4）；AD-22 只管文件格式，不管调用协议（F2）；AD-20 的 Prevents 与 Rule 自相矛盾（F6）；AD-16 的“只有一份实现”言过其实（F7） |
| Deferred 里没有能让两单元分歧的事项 | 基本是 | 现有条目都不会造成分歧。问题是应该列入而没列：VM500 重建与备份（F3）。“网站上的员工状态查询”与 AD-21 矛盾，属于旧账（F20） |
| 不与现有代码矛盾 | 部分 | 未实现部分不算矛盾。真矛盾有：`pve_grants()` 走 Ansible（F12）、`trust.json` 无人读取（F3）、退役时 HAPI 在 catalog 之后（F5）、到期重复实现（F7） |
| 新 AD 不与其他 AD 冲突 | 部分 | AD-1：轻度冲突（F9）；AD-3：可以调和，但需一句话（F15）；AD-10：有冲突（F5）；AD-12：无冲突，但 AD-23 应写明为什么不需要 generation（见“已核实没问题”） |
| 部署、环境、运维维度没有整块缺失 | 否 | 缺两块：VM500 重建/首次部署（F3）；HAPI 状态的可观测性（F10） |

## 已核实没问题

这些是我原本怀疑、对照代码后排除的，不需要再改：

- **到期能切断连接。** `StreamManager.watch` 每 0.25 秒用 `check_lease` 复查，要求 `route['enabled']` 且指纹相同（`hapi-stream-guard.py`、`hapi-auth.py:253`），不依赖 Nginx 重载。`config.json` 一替换，现有 WebSocket 就断。
- **到期不释放 first-login 绑定。** `subject()` 用全部路由（含 `enabled: false`）判断绑定是否有效（`hapi-auth.py` 中 `current = {...}`）。前提是路由留在列表里，所以“到期只改 enabled、不删路由”这条必须守住。
- **enforce 与 hapi-sync 的顺序。** 执行器上 `wsctl` 持有全局运行锁（`wsctl.lock`，`wsctl-secrets.py`），覆盖所有动作。所以不存在 AD-12 要防的乱序，AD-23 不带 `generation` 是成立的。建议在 AD-23 写明这一点，否则下个读者会以为漏了（F13）。
- **推送方向。** 符合 AD-4；`hapi-ctl` 只被调用，VM500 没有新增外联。
- **AD-9、AD-12。** 不受影响，WireGuard 路径没有被 HAPI 改动波及。
- **方案的 §2 现状描述** 和代码一致：`render()` 写死 `enabled: True`，`enforce` 不碰 HAPI，`hapi-control-plane` 和 `hapi-shared-hub` 确实都写动态文件。

## 高

### F1 — 发版和回滚“重新生成配置”不在 AD-23 的唯一入口里

**位置**：AD-22、AD-23；方案 §4 “批准：切换软链接 → 重新生成配置 → 重载 Nginx”、§5。

AD-23 规定派生文件只由 `hapi-ctl apply` 写入，输入走 stdin，调用前必须通过 `require_fresh_catalog`，读不到台账就不写。但发版、回滚和**自动切回**都要用新模板重新生成两份 Nginx，它们手里没有名单。两个实现者会这样分歧：

- 甲让 `hapi-release` 也读台账再调 `apply`。这样 D1 故障时不能发版，更严重的是**健康检查失败后的自动切回也写不了 Nginx**。
- 乙在 VM500 上加一个不带 stdin、从现有 `config.json` 重新生成的入口。这样 AD-23 的“唯一入口”和“输入走 stdin”就不再成立。

自动切回还有一个次生问题：切回时的 Nginx 是否按旧模板重新生成，spine 没写。

**建议**：AD-23 明确 `hapi-ctl` 有两种写模式，共用一把 `flock`：`apply`（带名单，要 `require_fresh_catalog`）和 `rerender`（不带名单，只用线上路由快照和 `current` 的模板重新生成，不改名单，不需要台账）。发版、回滚、自动切回一律走 `rerender`，且在 `wsctl` 运行锁内执行。

### F2 — `wsctl` 和 `hapi-ctl` 分两条路部署，调用协议没有兼容规则

**位置**：AD-22 “新版本必须能读上一版的动态文件”；方案 §4 “一次提交能改完接口两端”。

AD-22 只管动态文件格式，没管 stdin 协议。而两端的上线时机不同：

- `git push remotecc-ops` 后，执行器上的 `wsctl` **立即**生效，不经批准。
- VM500 的 `hapi-ctl` 要等 `hapi-release` 批准后才变。

所以一次提交改了接口两端，在 push 和 release 之间，每 5 分钟的 `enforce` 都在用新 payload 调旧 `hapi-ctl`。回滚同样会造成反向错位，而 AD-22 说“回滚只换代码”。最坏情况是旧版本把未知字段静默忽略，而不是报错。方案那句话反而会让人放心地这样改。

**建议**：stdin 带 `schema` 版本号，未知版本拒绝；`hapi-ctl` 必须同时接受当前版和上一版；规定上线顺序为先 `hapi-release` 后更新 `wsctl`；回滚前检查执行器发送的版本在目标版本的接受范围内。写进 AD-22。

### F3 — “派生文件”里有没有上游的内容，VM500 无法从零重建

**位置**：AD-2 HAPI 行、AD-22 “IaC 只管……`trust.json`”、AD-23；方案 §3、§7。

AD-2 把这批文件全部定义成派生文件，但现有 `hapi-registry.py` 的做法是**在现有文件上改**，下面这些内容只存在于文件本身：

| 内容 | 代码依据 | 问题 |
|---|---|---|
| `origin`、`issuer`、`audience`、`shared_hub` | `render()` 第 36 行 `{**config, 'routes': routes}` | 见下方 `trust.json` |
| VM502 的路由、凭据、agent | `render()` 第 27 行起按 `static_ids` 保留 | 输入只有 ID，没有内容 |
| nft 里 worker 以外的规则 | `firewall()` 第 45 行保留 | 仓库没有任何角色管理 `/etc/employee-access.nft` 的基础规则和 `employee-firewall` 单元（全文搜索只有 `hapi-registry.py` 引用） |

**`trust.json` 是个具体的矛盾。** AD-22 和方案把它作为 IaC 管理的信任锚，但代码里没有任何地方读它：现有角色写它只是为了触发重启，`hapi-auth.py` 读的是 `config.json` 的这几个字段。瘦身后 IaC 不再写 `config.json`，那么 issuer 或 audience 变化时谁把它送进 `config.json`？`hapi-auth` 的 `current_config()` 发现字段与内存不一致时对所有人返回 Denied，所以这一步还要和重启排序。

**重建是整块缺失的。** 依赖是个圈：单元要 `current` 才能启动，`hapi-release` 的健康检查要服务在跑，`apply` 要现有的 `config.json`、`credentials.json`、`agents.json`、nft 才能运行。Hub 校验还要求 `credentials` 至少 1 条。另外 `bindings`（`/var/lib/hapi-control-plane/`）和 Hub 的 `hapi.db` 是有状态的，spine 和方案都没写备份或丢失后的后果。

**建议**：

1. AD-2 把这批文件改成“名单部分派生，其余部分有明确所有者”：把 origin、issuer、audience、`shared_hub` 都归 `trust.json`，由 `hapi-ctl` 合并进 `config.json`，并写明 trust 变更的顺序；静态路由的完整内容要么进私有 settings，要么在 AD-2 明说“VM500 本地权威，不可重建”。
2. nft 基础规则和 `employee-firewall` 单元归入 IaC，列入方案 §3。
3. 加一节首次部署/重建顺序，例如 Terraform → IaC 角色 → 首次 release（不做服务健康检查）→ `hapi-sync` → 启动服务。如果这轮不做，就列入 Deferred 并写明“VM500 丢失时需人工恢复”。

### F4 — “结果没变就退出”让失败的重载永远不再重试

**位置**：方案 §5 “结果没变就直接退出，不重载”；AD-23 Prevents “路由与 Nginx 指纹错配”；AD-16 “下一轮重试”。

现有代码特意相反，并写明了原因：

- `hapi-registry/tasks/main.yml:115`：“Reloaded on every run, not only on change: a run whose reload failed leaves the file already written, and the next run must still load it.”
- `hapi-registry.py:107`：防火墙同样每次都重载。

新设计的故障路径是：替换文件成功 → Nginx 重载失败或进程被杀 → 下一轮比较文件发现“没变” → 直接退出，且一直如此。后果是线上 Nginx 里的指纹和 `config.json` 不一致。路由指纹覆盖 `enabled`（`hapi-auth.py:224`、`nginx.conf.j2:23`），所以**续费员工恢复后所有桥接请求返回 409**，新员工的 upstream 不存在。这正是 AD-23 声称要防的错配，而且没人看得到，因为 `apply` 报的是“无变化”。

**建议**：AD-23 加一条后置条件。替换前写 `pending` 标记，重载和验证都成功才清除；只有“文件相同且没有 `pending`”才算无变化。方案 §5 同步改。

## 中

### F5 — AD-10 的删除顺序与新设计冲突，退役残留无人收敛

**位置**：AD-10 “接入（Portal 身份、HAPI Access 放行与 route/credential/agent）→ Terraform VM → BWS → R2 → catalog”。

- 这个顺序**现在就不成立**：`hub-retire.py` 里 `hapi-sync` 在所有 catalog 删除之后（第 287 行）。在新设计里也不可能成立，因为 HAPI 是从 catalog 派生的，员工还在册就无法下线路由。方案 §5 写的也是 catalog 后推送。照 AD-10 实现的人会给 `hapi-ctl` 加排除列表，照方案实现的人不会。AD-10 这次没有更新。
- 方案说退役 `hapi-sync` 失败后残留“留到下次 `hapi-sync`”，维护文档说手动再跑。但 AD-10 的 Prevents 是遗留孤儿资源，而 AD-14 的孤儿定义只有 VM 和 catalog，Access 邮箱残留不在其中，没有任何东西会提醒。代码里重跑 `retire-apply` 会重试，方案没提这个更好的路径。
- `hapi.db` 里该员工 namespace 的会话不在删除清单。`employee_id` 由邮箱派生，同邮箱再开户会看到旧会话，“退役不备份、数据永久删除”的说法也不完全对。

**建议**：AD-10 改为“Portal → Terraform → BWS → R2 → catalog → `hapi-sync` 收敛 HAPI → 快照”，并写明失败时重跑 `retire` 的同一批准；AD-14 孤儿资源加 “Access 或 VM500 有而 catalog 无”；Hub namespace 数据要么进删除清单，要么写明保留。

### F6 — AD-20 的 Prevents 与 Rule 矛盾；紧急手段没有写进 spine

**位置**：AD-20、AD-2 “HAPI 身份放行”行、`.memlog.md` 2026-11-05。

- Prevents 写着防“一种方式到期**或停用**时另一种仍可进入”，Rule 写的是“员工在册且未到期就能用”。人工停用或 `quota_exhausted` 的员工，WireGuard 被断而 HAPI 照常能进。这时网站显示 `PAUSED`/`DISABLED`（`hub-publish.py`），HAPI 却通。用户决定的是取消**单独**的 HAPI 开关，但“整人停用是否连带 HAPI”没有回答过，配额能否经 HAPI 绕过也是一个业务问题。
- memlog 记录的决定是紧急情况用“Cloudflare Access 移除或 VM 关机”，spine 没写。这和 AD-2 “只由执行器经 Cloudflare API 写入”矛盾，而且 `access()` 是全量覆盖，下一次开户的 `hapi-sync` 会把手工移除的邮箱加回来。

**建议**：Prevents 去掉“或停用”，Rule 加一句“Portal 人工和配额原因只影响 WireGuard，不影响 HAPI”（请用户确认）；AD-20 写明紧急手段及其持续时间（到下次 `hapi-sync` 为止），AD-2 留出这个例外。

### F7 — “是否到期只有一份实现”言过其实，坏数据的处理没定义

**位置**：AD-16；方案 §5 到期判断。

至少还有这些比较：`hub-status.lifecycle`（`now>stamp`）、`hub-status.paid_through`、`hub-remind`、OCI `executor.py`（`stamp>paid[employee]`）。OCI 的那份无法合并，spine 自己也在 AD-9 里要求它存在。

更实际的分歧在 `paid_through` 无效时：`enforce` 现在是跳过这一行并记 `ENFORCE_PAID_THROUGH_INVALID`，`hub-status` 是抛错。`expired(row, now)` 怎么处理没写：

- 抛错：`hapi-sync` 整体失败。
- 返回 False：放行。
- 把这一行从名单里跳过：路由被删，绑定被释放。

而且 `hapi-ctl apply` 是整份替换，名单里一行不合格就全体不更新。`hub-expiry.py:85` 的注释说“多名员工可能共用一个管理员邮箱”，而 `hapi-registry.py` 和 `load_config` 都拒绝重复邮箱。所以一行坏数据会让**所有人**的到期都冻结，频率从开户退役时变成每 5 分钟。

**建议**：AD-16 改成“执行器侧只有一份，`hub-status` 也调用它；OCI 按 AD-8 独立比较”；写明无效值的语义（建议 `enabled: false` 并报告，不从名单移除）；重复邮箱的处理要和 AD-5 一起定。

### F8 — 迁移 P2 按方案自身规定无法执行

**位置**：方案 §8。

§8 开头说 P5 之前 `deploy-hapi-control-plane.yml` 和 `deploy-hapi-shared-hub.yml` 不能运行，因为它们还写动态文件。但 P2 要求“IaC 把鉴权、代理、Hub 三个单元和 Nginx 指向 `current`”，这只能靠这两个 playbook，而且 §2 说它们没有公开 inventory 跑不起来（核实：`ansible/inventory` 下确实没有 `hapi_control_plane`）。此外：

- Nginx 配置按 AD-22 已是私有内容，不该由 IaC 改。
- P2 要求“代码与线上字节相同”，但 `hapi-auth.py:413` 写死了 `hapi-login-portal/` 相对路径，而方案的发布目录叫 `portal/`。
- `hapi-registry` 里写死 `/usr/local/lib/...`，P3 回滚开关回到旧路径时，写的是单元已不再读取的位置。

**建议**：把瘦身拆到 P2 之前，或者给 P2 写一个只改单元的一次性 playbook；发布目录沿用 `hapi-login-portal/`，保证 P2 真的字节相同。

### F9 — `enforce` 成了无人值守的全量删除通道，防缩减被过早排除

**位置**：AD-1、AD-23；方案 §5 “不需要名单校验以外的新保护”、§11。

§11 说“缩减保护”因改为推送而不成立，但这个风险反而变大了：以前只有开户和退役时运行，现在每 5 分钟运行，无人批准。`require_fresh_catalog` 只证明读到了 D1，不证明内容合理。`catalog()` 对 `generation>0` 的回复只校验 `profile`，网站迁移出错返回空或截断的 `employees` 也能通过，此时全部员工的路由会被删除。`enforce` 不删令牌，下一轮能恢复，但 Hub 在这期间全员不可用。

和 AD-1 的关系：AD-1 要求创建或删除资源要走计划批准，`enforce` 删路由和 `hapi-sync`（`wsctl` 里走默认分支，无确认）都是例外，spine 没有写明。

**建议**：AD-1 写明“派生文件收敛不算创建或删除资源”。AD-23 加一条便宜的底线：`enforce` 的名单为空，或一次移除超过 1–2 条时拒绝并报告，由带令牌的 `hapi-sync` 处理大幅变化。这不会挡住合法退役。

### F10 — HAPI 没有可观测性

**位置**：AD-14、AD-3（`wsctl status`）、AD-16、AD-23。

新设计里有三种静默失效：名单冻结、推送持续失败、执行器宕机。它们都让到期员工继续用 HAPI，而 VM500 只有 `enabled` 布尔值，没有自己的到期判断（OCI 那边至少有快照）。用户已接受这个取舍，但目前能发现问题的只有 Semaphore 任务变红：

- `wsctl status` 和 AD-14 的每日摘要都不读 VM500：没有线上版本、上次 apply 时间、catalog 与路由的差异。
- 健康检查没有定义。`/health` 只是 `load_config`（`hapi-auth.py`），认证路径在 VM500 本地测不到，登录页坏了也能通过，而 AD-22 依赖它自动切回。
- 运行锁默认等待 1800 秒，`provision` 或 `retire` 运行时，“5 分钟内生效”不成立。

**建议**：加只读的 `hapi-ctl status`（版本、最后成功时间、路由摘要），接入 `wsctl status` 和每日摘要，连续失败超过阈值就标红；AD-22 列出健康检查的最小清单；Conventions 的“5 分钟内”加上“无长任务占锁时”。

### F11 — `enforce` 调用的语义和字段还差一层

**位置**：AD-23、方案 §5。

- 不带令牌的 `apply` 怎么处理 `credentials.json`、`agents.json`、nft 没写。方案只说路由和 `tokens/`。`credentials.json` 里的 token 要从哪里读？退役后 `enforce` 是否同时删除凭据、agent 和 9443 规则？“5 分钟内下线”是否只指路由？
- `hub-hapi.desired()` 会调用 `ensure_hapi_token`（要 BWS，还可能写），`enforce` 不能复用，需要一个不碰 BWS 的名单函数。
- 方案的名单字段是 `vmid`，现有接口是 `address`，`workspace_address` 在执行器里。如果地址在 VM500 计算，`/30` 规则就有两份。
- 现在的格式校验在 `hapi-registry/tasks/main.yml` 的 assert 里（id、email、address、token，以及 id 不能是静态 ID），角色删除后要进 `hapi-ctl`。三处的 id 长度上限也不同（28、32、64）。

**建议**：在 AD-23 或方案 §5 写清 payload 的 schema、每种调用对四类文件的影响，并保留 `address` 由执行器计算。

## 低

- **F12 “日常路径不调用 Ansible”不准确。** `pve_grants()` 经 `play_boundary` 调 `ansible-playbook`（`hub-hapi.py:63`、`hub-retire.py:131`），方案 §6 又写“不变”。AD-23、方案 §1、维护文档都要改成“写 VM500 不调用 Ansible”，否则有人会去重写它。
- **F13 AD-23 的 `flock` 说明不够。** 应写明 `wsctl` 运行锁是顺序保证（所以不需要 generation），`flock` 只防手动运行；`hapi-release` 必须在同一把锁内。
- **F14 静态路由员工不受到期约束。** `static_ids` 的路由保持原样，员工若有 `paid_through`，VM 会关但 route 仍开，与 AD-20 “同时生效”不符。应规定静态路由员工必须 `no_expiry`。
- **F15 AD-3 需一句话。** `enabled: false` 字面上是持久化的“已到期”。应说明它和 Portal 的 `expired` 一样是投影，不是状态来源。
- **F16 AD-2 与其他章节的旧账。** AD-2 说员工事实归 `catalog.json`，但 README、`hub-terminal.py` 和方案都以 D1 为准，AD-23 的“台账”因此含义不明。BWS 项目名 `EmployeeWorkspace-OCIHub`、`terraform/proxmox/...` 路径、Structural Seed 的 `employee-admin/` 也都过时。
- **F17 Conventions 和图没跟上。** 命令名没有 `enforce`；确认行没有 `hapi-release`、`hapi-sync`；依赖图没有执行器到 Cloudflare Access 的写入。
- **F18 AD-22 的范围比方案窄。** “IaC 只管”的列表漏了目录、`hub.env`、签名密钥。`authorize.inc` 现在归 IaC 角色，却和 Nginx 模板紧耦合，两边都没提到。计划阶段已写 VM500 暂存目录，和 AD-1 “先计划后写”略有出入；批准哈希不应覆盖随名单变化的配置差异，否则 `enforce` 会让批准失效。
- **F19 `access_enabled` 开关。** `hub-hapi.py:139` 在该开关关闭时不写 Access，“员工在册且未到期就能用”就不成立。应列入方案 §7 核实，或写进 AD-20。另外到期员工看到的是原始 403，AD-21 的统一文案没有覆盖。
- **F20 边缘项。** 退役失败后 `tokens/<id>` 残留，同邮箱再开户时 `enforce` 可能用旧令牌生成路由（下次 `hapi-sync` 修复）。Deferred 的“网站上的员工状态查询”与 AD-21 矛盾，不在本次范围。方案 §7 的 Hub 热加载仍是 P0 未知项，但到期路径不碰 `credentials.json`，只影响新员工，风险比表面小。

## 建议处理顺序

1. 改 spine：AD-23（F1、F4、F9、F11、F13）、AD-22（F2、F18）、AD-2（F3、F16）、AD-10（F5）、AD-20（F6）、AD-16（F7）。
2. 请用户决定两件事：人工和配额停用是否连带 HAPI（F6）；VM500 重建这轮做还是进 Deferred（F3）。
3. 改方案：§5（F4、F11）、§8 的 P2（F8）、§11 的缩减保护（F9）。
4. F12–F20 随手修，不阻塞。
