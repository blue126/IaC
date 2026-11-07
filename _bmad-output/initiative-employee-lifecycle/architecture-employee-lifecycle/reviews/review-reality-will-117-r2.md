# 现实核对审核：WILL-117 第二轮

> 2026-11-07 对 WILL-117 第二轮改动的 reality 审核，以同模型子代理方式运行，不是跨模型审核。

- 对象：`architecture-employee-lifecycle.md` 相对 `04c7378` 的未提交改动，即 AD-2 私钥行、AD-3、AD-5、AD-8、AD-10、AD-13、AD-17、AD-18、AD-21、AD-27 和 Deferred R2 行
- 视角：改动文字里的每条事实断言，是否经过现状核对，而不是凭印象断言
- 更早的断言已在 `review-reality-will-117.md`、`review-reality.md` 核对过，本次不重做
- AD-27 的新句是目标设计，只核对它们与 Worker 的 generation 行为是否矛盾

## 结论

**改动文字的事实大多与 fe3f25e 相符，但不能按现文定稿：AD-8 新句依赖的 AD-12 enforce 推送在代码里不存在，也没有票据，而且 AD-21、AD-27 的新句各有与现状不符的地方。**

共 0 个 critical、1 个 high、4 个 medium、4 个 low。

## 核对方式与边界

- **私有代码版本：** 全部用 `git -C remotecc show fe3f25e:<path>` 读取，没有读工作区。行号都指 fe3f25e。
- **网页：** 本轮没有联网。改动文字没有新增版本号或外部产品事实，D1 的平台事实沿用上一轮的来源。
- **未碰：** `employee-data`、`hapi-data`、SSH、任何凭据、任何线上系统。
- **清单外：** 为核对 generation 和命令入口，还读了 fe3f25e 的 `apply-site/migrations/0012`、`0014`，并搜索了 `apply-site/test-worker.mjs` 和 `wsctl/wsctl`。这些文件都不含凭据，下文的结论不依赖它们。

下文 `spine` 指被审文件，`worker.js`、`schema.sql` 在 `apply-site/` 下，无路径的 `.py` 文件在 `remotecc/wsctl/` 下，`executor.py` 指 `wsctl/services/oci-hub/executor.py`，`手册` 指 `wsctl/docs/admin-handbook.md`，`ticket` 指 `git show 8ad1acc:_bmad-output/backlog/story-no-expiry-clears-expired.md`。

## Critical

无。

## High

### H1. AD-8 新句指向的 AD-12 推送不存在，到期前打标的员工也可能断开

**断言：** `spine:140`：“控制台改标记要等下一次快照推送才到 OCI（AD-12）”。`spine:164`：“`enforce` 发现 catalog generation 变化时也推送”。`spine:140` 的例外只覆盖“已带 `expired` 的员工”。

**现状：**

- `hub-enforce.py` 唯一的推送是 HAPI 的 `enforce_push`（`hub-enforce.py:46`），不推快照。
- 快照只在 renew、initialize、开户、退役和手动 `wsctl expiry` 时推送（`hub-expiry.py:115,138`、`hub-terminal.py:687`、`hub-retire.py:293`、`oci-hub-admin.py:409`）。
- `wsctl expiry` 没有定时（`ansible/roles/semaphore/files/semaphore-bootstrap.py:46`）。代码注释也写着要等下一次 renew 或 `wsctl expiry`（`hub-expiry.py:80-81`、`hub-terminal.py:685`）。
- 这条推送只有 `.memlog.md:222` 的决定。本分支和 8ad1acc 的票据里都没有对应条目。
- `spine:238` 只把 AD-25 至 AD-32 标为目标状态，AD-12 没有标，读者会当成现状。

**后果：** “下一次”没有上限。除了上一轮 H1 的场景，还多一个场景，AD-8 的例外没有覆盖：

1. 管理员在到期前打标。VM 和 HAPI 立刻按标记处理（`hub-enforce.py:54-55`、`hub-hapi.py:55`）。
2. 到 `paid_through` 之前没有任何推送，OCI 还拿着旧日期，timer 加上 `expired`，WireGuard 断开（`executor.py:168-174`）。
3. 下一次推送把员工移出快照，`expired` 就此留下（`executor.py:168-170`）。网站发布 `NO_EXPIRY`（`hub-publish.py:42`）。

ticket 的 Verify 要求“一个 timer 周期内 `expired` 被移除”。控制台打标到不了 OCI，就做不到这一点，ticket 没写这个依赖。

**修复方向：** 给 AD-12 的 enforce 推送开票，并写进 ticket 的依赖，同时把 AD-12 标成目标状态。落地前在 AD-8 写明：控制台打标后立刻运行 `wsctl expiry`（手册:97 写明不需要审批）。

**状态：** 已确认，依据是读代码，没有实跑。线上部署版本未核。

## Medium

### M1. AD-21 新句让“与 uniCloud 相同的字段”自相矛盾

**断言：** `spine:218`：“运行状态只来自执行器推送的副本（与 uniCloud 相同的字段）……网站的到期日、登录别名和设备列表不在副本里，读 D1 catalog”。

**现状：** 后半句是对的，副本只有 `email`、`state`、`workspace`、`spec`、`traffic`、`updated_at`（`hub-publish.py:84-86`；`epic-miniprogram-entry/tickets/tickets.toml:324`）。但括号留了下来，两句合起来就是 uniCloud 副本也没有到期日。

这与以下文字冲突：

- `spine:24`、`spine:73`、`spine:200` 都要求小程序显示到期日。
- `spine:200` 写云数据库只存申请、验证码哈希和状态副本，小程序读不到 D1。

现状里也没有这个对照物：私有代码中与小程序相关的内容只有 `worker.js:247` 一条文案，小程序已在 2026-11-02 延后（`tickets.toml:48`）。所以“接收方拒绝不更大的值”对 uniCloud 也没有实现可核。

**修复方向：** 删掉括号，或写明 uniCloud 副本比网站副本多带 `paid_through`。小程序暂缓的事实也应写出。

**状态：** 已确认。当前没有运行影响。

### M2. AD-27 的前提与 Worker 的 generation 行为有两处不符

**断言：** `spine:256`：“影响配对的写入都要让 `generation` 前进，所以相同 generation 的配对内容必须相同”，“拒绝更旧的响应”。

**相符的部分：** executor 的 PUT 严格加一（`worker.js:1593,1603`），控制台 UPDATE 经触发器加一（`schema.sql:98`），批内事务保证内容和 generation 一起变。

**不符 1：控制台 INSERT 和 DELETE 不动 generation。** 触发器只有 `AFTER UPDATE`（`schema.sql:98`）。

- 手册:324 只允许编辑列，没有写禁止删行。在控制台删掉一行时，配对内容变了，generation 不变。
- 按 AD-27，`firewall.py` 之后每次拉取都失败，这个状态一直持续到下一次写入。
- 不能简单加 `AFTER INSERT/DELETE` 触发器：`putCatalog` 自身就是 DELETE 加 INSERT（`worker.js:1605-1609`），generation 会多跳，响应里的 `next` 也不再准确（`worker.js:1617`）。

**不符 2：generation 只在同一个 D1 库内单调。** `catalog_meta` 没有行时读到 0（`worker.js:1567`），下一次 PUT 写成 1（`worker.js:1593,1600`）。

- `wsctl catalog-sync` 正是手册写的 D1 故障恢复入口（手册:325，`hub-terminal.py:108-112`）。D1 回滚到旧时间点也会让 generation 倒退，这一点是推断。
- 恢复后 `firewall.py` 会拒绝所有响应，直到 generation 追上旧值。这段时间新员工连不上，已退役的配对留在 set 里。
- spine 没有这条恢复路径，全文没有 `catalog-sync` 和 Time Travel。作为对比，快照的 generation 取 OCI 已接受值加一（`hub-expiry.py:53-55`），不受这个问题影响。

**实现提醒（不是矛盾）：** 现有 `getCatalog` 分两次读 `catalog_meta` 和 `employees`（`worker.js:1566,1568`），不是一致快照，配对接口不能照抄。

**修复方向：** 写明控制台不得增删行，或设计不影响 PUT 的触发方式。再给 `firewall.py` 的已接受 generation 定一条 D1 恢复后的重置步骤。

**状态：** 代码事实已确认，后果是推断，`firewall.py` 的新逻辑还不存在。

### M3. 执行器本地设备包没有生命周期，退役后还在，再开户大概率失败

**断言：** `spine:79`、`spine:194`：“执行器本地另留一份供 `wsctl reissue` 使用”。用途写对了（`oci-hub-admin.py:245-247`）。但 AD-17 接着说“设备包与 VM 同寿命”，AD-10 写“同一邮箱退役后再开户按新申请处理”（`spine:152`）。

**现状：** `bundle_output_dir` 只在 `oci-hub-admin.py:177,245` 使用，`device-bundle.zip` 也只出现在 `oci-hub-admin.py`、`deliver-temp.py` 和 `hub-bundle.py`，`hub-retire.py` 两者都不碰。AD-10 的删除清单也没有这一份。`.memlog.md` 已记下这份副本比退役活得久，spine 没写。

**后果：**

- 含 SSH 和 WireGuard 私钥的 zip（`hub-bundle.py:46`）在退役后仍留在执行器上。
- 同一邮箱再开户时，`employee_id` 和默认 `device_id` 都由邮箱前缀得出（`hub-onboard.py:24-26`），目录相同。新密钥让字节不同，`hub-bundle.write` 抛 `HUB_DELIVERY_CONFLICT`（`hub-bundle.py:62-67`）。这时 catalog 和 `hapi-sync` 已经完成（`hub-terminal.py:679-690`），开户卡在最后一步。

**修复方向：** 让 `retire` 删除 `bundle_output_dir/oci-hub/<device>`，并列入 AD-10。不改代码的话，spine 要写明这份的留存时间和手工清理。

**状态：** 第一条已确认（代码），实地文件未看。第二条是读代码推出的，没有实跑。

### M4. AD-10 同一行还写着 R2，其他 R2 残留也与新的 Deferred 行矛盾

**断言：** `spine:449`：“需要放大文件时再开通 R2”。`spine:192` 把 Binds 从 R2 改成了 D1。

**现状：** Worker 确实没有 R2（手册:16 写 Worker + D1；`worker.js` 的存取全走 `env.DB`）。但下列文字仍把 R2 写成在用组件：

| 位置 | 现文 |
| --- | --- |
| `spine:152`（AD-10，本次改动行） | 清单已改成“网站设备包”，删除顺序还是“BWS → R2 → catalog” |
| `spine:23`、`35`、`331` | “Worker + D1 + R2” |
| `spine:311` | “Cloudflare Workers + D1 + R2 + Turnstile” |
| `spine:425` | “设备包下载 \| 申请网站、R2” |

代码里的实际顺序是 BWS、网站设备包、catalog（`hub-retire.py:281-284`）。另外 `spine:134`（AD-7）的“设备包下载邮件”也没跟上，邮件只是通知。

**修复方向：** 这六处统一改成 D1 或“网站设备包”。

**状态：** 已确认。这是上一轮 H2 的剩余部分，AD-10 那处是新发现。

## Low

- **L1. ticket 路径在本分支不存在（`spine:140`）。** 文件只在 8ad1acc，该提交不在 `origin/main`，也不包含 `04c7378`。本分支的 `_bmad-output/backlog/` 里没有它，所以只合并 spine 时这条引用是断的。另外，如果修复放在 OCI 一侧，`spine:146`（AD-9）的“快照里没有的员工不做任何处理”也要改，而 AD-8 只说删除例外。
- **L2. “`no_expiry` 优先于其他一切事实”只对生命周期判定成立（`spine:94`）。**
  - VM 缺失时 `hub-status` 先给 `orphan`（`hub-status.py:52-56`）。
  - 配额照常断开带标记的员工（`executor.py:165-174`）。
  - 这时网站仍发布 `NO_EXPIRY`，不显示暂停或停用（`hub-publish.py:41-42`）。
  - 这个映射在 `hub-publish`，而 AD-8 的 Binds 这次去掉了“状态副本”（`spine:138`）。
- **L3. `不到期 --> 正常` 的终点不全（`spine:108`）。**
  - 残留过去日期时会落到已到期或可退役（`hub-status.py:25-26`）。
  - 2026-11-01 初始化的两行没有 `paid_through`（`hub-expiry.py:133-134`），去标后正是 AD-8 说的“数据缺失”行。
  - 这种行 `hub-status` 显示 `active`，网站发布 `NO_EXPIRY`（`hub-publish.py:49-51`），提醒只进 `skipped`（`hub-remind.py:87`），管理员摘要也不列（`hub-remind.py:174`）。
  - 所以“不是第二种豁免”只是定义，系统行为和豁免一样，也没有告警。去标时要同时写日期。
- **L4. AD-13 改动行的相邻文字不准（`spine:170`，这句本次没改）。**
  - “管理接口……只提供”漏了 `PUT /admin/status`、`POST /admin/mail` 和 `GET /admin/bundles/<token>`（`worker.js:1983-1990,2005-2009`），而 AD-21 新句正依赖前者。
  - “读取下载记录”没有路由，`bundle_downloads` 在 Worker 里只有写入（`worker.js:1245`）。
  - 改动后的“D1 存……”也没列状态副本（`schema.sql:73-84`）。

## 已核实的断言

| AD | 断言 | 证据 |
| --- | --- | --- |
| AD-2 | 设备包含私钥，D1 存一份，到退役或被替换 | `hub-bundle.py:46`，`schema.sql:41-50`，`worker.js:1220-1227`，`hub-retire.py:242-246,283` |
| AD-2、17 | 执行器本地留一份供 `reissue` 使用 | `oci-hub-admin.py:245-248`，手册:212 |
| AD-3 | 优先级：不到期、可退役、已到期、已停用、正常 | `hub-status.py:21-28` |
| AD-3 | 已到期打标后 `expired` 不自动清除 | `executor.py:168-175`，`test-oci-hub.py:277-282` |
| AD-3 | 带标记员工可点名强制退役 | `hub-retire.py:78-82`，`oci-hub-admin.py:369,488`（未实跑） |
| AD-5 | 邮件由 `vm_hostname` 推出别名 | `deliver-temp.py:291-295,318` |
| AD-5 | 网站由 `employee_id` 拼出，`hostname` 字段是别名 | `worker.js:1405` |
| AD-5 | manifest 的 `ssh_alias` 是 `oci-hub-<device_id>` | `hub-bundle.py:39` |
| AD-8 | 开户入口不打标，新员工先有 `paid_through` | `hub-terminal.py:678,696-703` |
| AD-8 | HAPI 也用同一条判定 | `hub-hapi.py:55`，`hub-expiry.py:36-39` |
| AD-8 | 既无日期也无标记的行不到期 | `hub-expiry.py:20-23`，`hub-enforce.py:52-55` |
| AD-8 | 网站读 catalog 时不显示到期日 | `worker.js:1403` |
| AD-8 | `renew` 后等 timer 移除 `expired` | `executor.py:168-175,607`，`ansible/roles/oci-hub/templates/oci-hub-quota.timer.j2:6`（5 秒），手册:221 |
| AD-8 | 2026-11-01 由 `wsctl expiry --initialize` 初始化 | `epic-paid-through-enforcement/tickets/story-no-expiry-init-plan.md:76`，`oci-hub-admin.py:357,402-405`，`hub-expiry.py:118-138`；2026-11-04 的上线记录与此一致（`tickets.toml:324`） |
| AD-8 | 例外随 ticket 上线后删除 | ticket 的 Notes（路径问题见 L1） |
| AD-10 | 退役清单含网站设备包 | `hub-retire.py:108-110,242-246` |
| AD-13 | 除设备包内私钥外，D1 不存凭据 | `worker.js:1549-1560` 拒绝凭据字段；验证码和令牌只存哈希（`schema.sql:31-35,44-50,65-69`）；包内私钥只有 `client-key`、`wg.key`（`hub-bundle.py:46`） |
| AD-17 | 邮箱被攻破即可取得设备私钥 | 验证码登录后下载，无第二因素（`worker.js:1411-1425,1665-1681`） |
| AD-17 | 2026-11-02 用户选 B | `epic-miniprogram-entry/tickets/tickets.toml:204`，用语一致 |
| AD-17 | `deliver` 负责上传 | 手册:182，`worker.js:1258-1279` |
| AD-18 | 小程序只提示到网站下载 | `worker.js:247` 的文案（小程序本身见 M1） |
| AD-21 | 到期日、别名、设备不在副本里，读 catalog | `hub-publish.py:84-86`，`worker.js:1387-1407,1463-1472` |
| AD-21 | 副本整份替换，拒绝不更大的 generation | `worker.js:1620-1652`，`hub-publish.py:114`，手册:394 |
| AD-27 | PUT 和控制台 UPDATE 让 generation 前进 | `worker.js:1593,1603`，`schema.sql:98`（例外见 M2） |
| Deferred | Worker 上限 64 KiB | `worker.js:22,1267,1269`，手册:391 |
| Deferred | 换 R2 还要改读取 `bundles.data` 的查询 | `worker.js:1301,1657,1672` |

## 无法核实的断言

- **线上是否与 fe3f25e 一致：** 执行器和 Worker 的部署版本没读。
- **触发器线上是否存在：** `employees_console_edit` 据记录是手工应用的，线上没有实查。
- **初始化的线上结果：** 只看到 2026-11-01、2026-11-04 的工单记录，没有看当前 D1。
- **当前有没有既无日期也无标记的行，或 H1 描述的员工：** 需要读 D1 或 `wsctl status`，本次未运行。
- **“设备包很小”的实际大小：** 设备包在 `employee-data` 下，没有实测。包内只有 4 个小文件，离 64 KiB 上限很远。
- **执行器本地设备包的实地情况：** 目录在 `employee-data` 一侧，没有读。M3 依据代码，`.memlog.md` 也写着未在主机确认。
- **`HUB_DELIVERY_CONFLICT` 这条路径：** 读代码推出，没有实跑。
- **D1 回滚后 generation 倒退：** 依据 Time Travel 的语义推断，没有实测。
- **uniCloud 副本格式：** 没有实现可核，只有 spine 和工单文字。
- **bootstrap 推出别名：** `workspace-onboarding` 不在本轮来源内，沿用上一轮的核对。
- **用户决定的原文：** 2026-11-02 的选 B 只看到工单 notes。2026-11-07 的决定只看到 memlog 和 ticket 的转述。
