# 现实核对审核：WILL-117 更新

> 2026-11-07 对 WILL-117 更新的 reality 审核，以同模型子代理方式运行，不是跨模型审核。

- 对象：`architecture-employee-lifecycle.md` 的 AD-5、AD-8、AD-17 和 AD-21 一句（工作区未提交的 diff，基线 `c5cc34f`）
- 视角：改动文字里的每条事实断言，是否经过现状或网页核对，而不是凭印象断言
- 其余内容已在 `review-reality.md` 核对过，本次不重做

## 结论

**新文字的绝大多数事实与 fe3f25e 的代码相符，但不能按现文定稿：AD-8 的“不断开”对已到期后才打标的员工不成立（这是 `deferred-work.md` 里的已知推迟项），而且 spine 其他绑定文字仍保留被本次更新推翻的说法。**

共 0 个 critical、2 个 high、2 个 medium、8 个 low。

## 核对方式与边界

- **私有代码版本：** `remotecc` 工作区在 fe3f25e 之上有今晚的未提交改动（`deliver-temp.py`、`hub-onboard.py`、`hub-remind.py`、`oci-hub-admin.py` 和两个测试）。所以本审核用 `git archive fe3f25e` 导出清单内文件后再读，行号都指 fe3f25e。这些改动没有碰 `apply-site`、`hub-enforce.py`、`hub-expiry.py`、`hub-publish.py`，不影响下面的结论。
- **`workspace-onboarding` 版本：** 本地 `main` 是 `ca2ce71`（1.0.0），落后远端 32 个提交，不能代表已发布版本。本审核读本地已有的 `origin/main` 引用 `8b149dc`（1.3.0）。
- **网页：** Cloudflare D1 官方文档，来源见文末。对线上只发了一次 GET，见“无法核实的断言”。
- **未碰：** `employee-data`、`hapi-data`、SSH、任何凭据、任何线上写入。
- **清单外：** 列目录时多读了 `apply-site/wrangler.toml`，不在给定清单内。它不含凭据，本审核也没有用它作证据；R2 的结论来自 `worker.js` 的 `env` 绑定和手册。`wsctl/services/oci-hub/`、`wsctl/templates/`、`employee-miniprogram` 不在清单内，没有读。

下文 `spine` 指被审文件，`worker.js` 指 `apply-site/worker.js`，无路径的 `.py` 文件在 `remotecc/wsctl/` 下，`手册` 指 `wsctl/docs/admin-handbook.md`。

## Critical

无。

## High

### H1. AD-8 的“不断开”对已到期后才打标的员工不成立

**断言：** `spine:136`：“`no_expiry` ……管理员可在 D1 控制台改”，“标记优先于任何 `paid_through` 值：……不提醒、不断开、不关机”。

**现状：** 一名已到期、OCI 上已有 `expired` 的员工被打标后，WireGuard 仍然断开，而且系统显示一切正常。原因有三层：

1. **控制台改动不会传到 OCI。** AD-12（`spine:160`）写“`enforce` 发现 catalog generation 变化时也推送”，但代码里没有这条路径。
   - `hub-enforce.py` 全文不调用 `push`。
   - 全部调用点只有 `hub-expiry.py:115`（renew）、`hub-expiry.py:138`（initialize）、`hub-retire.py:293`、`hub-terminal.py:687` 和 `oci-hub-admin.py:409`（`wsctl expiry`）。
   - `wsctl expiry` 没有模板和定时（手册:227；`ansible/roles/semaphore/files/semaphore-bootstrap.py:46`）。
   - `.memlog.md:222` 记录的是 spine 上的决定，不是代码改动。这本身不是 spine 的错，但 AD-8 把它当成已有事实来用。
2. **即使推送了，也清不掉 `expired`。** `hub-expiry.py:42-43` 把带标记的员工排除出快照，而 OCI 只处理快照内的员工。
   - `test-oci-hub.py:277-282` 断言快照外员工保留 `expired`。
   - `_bmad-output/initiative-employee-lifecycle/deferred-work.md:12-13` 明确写着：员工带着 `expired` 离开快照（“改标 no_expiry、退役、删字段”）时，OCI 不再移除，“移出快照前须先推一次未来日期”。
   - 这个推迟项至今没有落地：`hub-expiry.py`、`hub-retire.py`、`hub-enforce.py` 都没有这种预推送。
   - spine 和 memlog 都没有提到它。
3. **出了问题看不见，正常路径也走不通。** `hub-status.py:23` 让 `no_expiry` 优先于所有原因，`hub-publish.py:42` 发布 `NO_EXPIRY`，网站显示“长期有效”，`wsctl renew` 又被 `hub-expiry.py:111` 拒绝。

**后果：** 管理员给一名已到期员工打标后，VM 和 HAPI 会在 5 分钟内恢复（`hub-enforce.py:52-54`、`hub-hapi.py:55`），但 Mosh 走的 WireGuard 不恢复，网站却显示正常。文档里没有恢复步骤。从代码推断，能走通的绕行是先去标、`renew`、等 OCI reconcile，再打标，这一点没有实测。

**修复方向：** 不改代码的话，AD-8 至少要写明这个限制，并在 AD-12 或 Deferred 里带上 `deferred-work.md` 这一条。要让“不断开”成立，需要二选一：移出快照前先推未来日期，或按 `deferred-work.md` 的建议记录“曾由 timer 加过”的集合。同时要把 AD-12 的 `enforce` 推送真正做出来。另外 AD-12 的“全体员工”（`spine:160`）也与 `hub-expiry.py:42-43` 不符，快照只含 `enforced` 的员工。

**状态：** 已确认。依据是代码、测试和 `deferred-work.md` 的记录，`executor.py` 源码本身不在清单内，没有读。线上目前有没有这种员工未知。

### H2. spine 其他绑定文字仍在说被本次更新推翻的事

本次只改了 AD-17 和 AD-21 的一句，以下文字没跟上，其中前三条与 AD-17 正面冲突：

| 位置 | 现文 | 现状 |
| --- | --- | --- |
| `spine:196`（AD-18） | “设备包始终经邮件链接到网站下载（AD-17）” | 邮件没有下载链接：`deliver-temp.py:297-322`、`test-temp-delivery.py:132`；Worker 没有 `/d/` 路由，落到 `worker.js:2011` 的 404 |
| `spine:79`（私钥行） | “只在运行时物化；设备包在 R2 中临时存放” | 设备包存 D1 到退役（`schema.sql:48`、`worker.js:1220-1227`）；执行器磁盘也常驻一份，`reissue` 依赖它（`oci-hub-admin.py:245-247`） |
| `spine:445`（Deferred R2） | “设备包约 1.6 KB 且即删” | “即删”已不成立，而这正是当初选 D1 的理由之一 |
| `spine:188`、`23`、`35`、`307`、`327`、`421` | 把 R2 写成在用组件 | Worker 的 `env` 绑定里没有 R2 或 bucket，只有 `env.DB`；手册:16 写 Worker + D1 |
| `spine:130`（AD-7） | “设备包下载邮件” | 邮件只是通知 |
| `spine:166`（AD-13） | “设备包下载页” | 手册:381：“网站也不再提供公开下载页” |

**后果：** AD-18 是绑定规则，实现者照它做就会把链接加回来。`spine:79` 是全文唯一描述私钥位置的地方，读它的人会以为私钥不落盘。

**状态：** 已确认。

## Medium

### M1. AD-17“私钥随包在 D1 保存到同一时点”低估了实际留存

**断言：** `spine:190`。

**现状：** 活动表里的行确实在那个时点删除（`worker.js:1220-1234`、`hub-retire.py:242-245`），但这句话作为“私钥留存多久”的说明不完整：

- D1 的 Time Travel 始终开启，保留 30 天（Workers Paid）或 7 天（Free）。文档把“误执行 `DELETE`”列为恢复场景，由此推断删除后的 BLOB 在窗口内还能恢复。这一步是推断，文档没有逐字这样说。
- 加密由 Cloudflare 托管密钥（“Encryption keys are managed by Cloudflare”），所以有 D1 权限的账号身份都能读到明文私钥。
- `hub-retire.py` 不碰 `bundle_output_dir`，执行器本地的 `device-bundle.zip` 在退役后仍在。手册:141 写“退役：删除 VM 和设备包”，也容易读成全部删除。这一点来自代码，没有读 `employee-data` 实地确认。

**影响有限：** 退役会删 Portal 身份和 BWS 记录，留下的密钥大概率已失效。但“被同设备的新包替换”不一定换密钥，这时旧包里的私钥仍有效。

**修复方向：** 把这句改成明确的留存说明，列出 D1 活动表、Time Travel 窗口和执行器本地副本。账户是 Free 还是 Paid 需要确认。

**状态：** 平台事实已确认，“删除后可恢复”是推断。

### M2. “状态副本的 `paid_through` 为空”机制写错，并与 AD-21 冲突

**断言：** `spine:136`，以及 AD-5 新增的“网站……由 `employee_id` 拼出”（`spine:118`）。

**现状：** 自 story 5.27 起，副本对**所有**员工都不带 `paid_through`、`hostname`、`devices`（`hub-publish.py:84-86`；`worker.js:1463-1467`）。真正让带标记员工的到期日为空的，是 Worker 读取时的叠加：`worker.js:1403`。`.memlog.md` 里“`hub-publish` sends NO_EXPIRY with empty paid_through”同样不准确，`state()` 算出的 `paid` 在 `build()` 里被丢弃。

由此带来两个问题：

- **与相邻句矛盾：** AD-21 紧挨被改句的下一句写“状态只来自执行器推送的副本……网站与小程序不自行推导”（`spine:214`），但 `worker.js:1388-1408` 直接读 `employees` 表并拼出别名。AD-5 的新文字反而写对了，于是两条 AD 互相矛盾。
- **有一个实际缺陷：** 控制台给 EXPIRED 员工打标后，Worker 立刻返回空的 `paid_through`，而 `state` 要等下一次发布（每小时第 15 分）才变。这段时间 `fill(state.text, {})`（`worker.js:1821`、`worker.js:470-472`）会把 `worker.js:283` 的 `{date}` 占位符原样显示给员工，最长约 1 小时。

**修复方向：** AD-8 改写为“网站按 catalog 读取，带标记时不显示到期日”；AD-21 改写为状态来自副本，到期日、别名和设备来自 D1 catalog。uniCloud 那一侧的字段不在本次核对范围内。

**状态：** 已确认（代码）。`{date}` 现象是读代码推出的，没有实跑。

## Low

- **L1. `paid_through` “恒为”月末不是硬约束（`spine:136`）。** 还存在“既无值也无标记”的行：`hub-expiry.py:20-23` 不执行到期，`hub-status.py` 显示 `active`，`hub-publish.py:51` 却发布 `NO_EXPIRY`，同一员工两处说法不同。控制台清空 `paid_through` 就能造出这种行，且不受标记约束。memlog 记录了这一点，spine 没写。Worker 也不校验是否月末（`worker.js:1510`）。
- **L2. “开户不写 `paid_through`”只对已带标记的行成立（`spine:136`）。** `hub-terminal.py:696-700` 确实如此，但 `provision` 没有打标入口，`no_expiry` 在 `hub-terminal.py` 里只出现在这个函数。新员工开户必定写入 `paid_through`，之后打标才产生“残留值”，也就是 H1 的前提。
- **L3. AD-17 的 Binds 漏了 `wsctl deliver`（`spine:188`、`spine:288`）。** 首次上传和开通邮件都由 `deliver` 完成（手册 3.3），`provision` 不发信（`semaphore-bootstrap.py:28`）。“开通……只是通知”所说的命令其实是 `deliver`。
- **L4. AD-5 “别名不存储”不严格（`spine:118`）。** `deliver-temp.py:144` 把 `vm_login` 写进 `identity`，再经 `:227` 落入回执，只是没有读取方；今晚的未提交改动仍保留这一行。邮件的别名也不是由 `employee_id` 拼出，而是从回执的 `vm_hostname` 反推（`deliver-temp.py:291-295`），取不到时退回字面量 `<你的 ID>-vm`（`:318`）。另外 manifest 里有个同名不同义的 `ssh_alias`，值是 `oci-hub-<device_id>`（`hub-bundle.py:38-39`）。
- **L5. “换 R2 只改封装”略过于乐观（`spine:190`、`spine:445`）。** `worker.js:1301`、`1657`、`1672` 三处都查 `bundles.data IS NOT NULL`，在封装之外。换 R2 后 `data` 为空，这三处会报不可用。`worker.js:1215-1216` 的注释也同样过于乐观。
- **L6. “点名强制退役”的入口没有文档（`spine:136`）。** `--force` 的代码路径是通的（`oci-hub-admin.py:369`、`hub-retire.py:78-81`、`wsctl-confirm.py:19`，未实跑），但手册 3.9 和 `wsctl` 帮助都没写，Semaphore 模板也没有这个字段（`semaphore-bootstrap.py:37-38`）。手册:346 还写 `retire`、`renew` 没有模板，与这个脚本不符。
- **L7. `no_expiry` 在 spine 里只出现在 `:136`。** AD-3 状态图（`spine:96-106`）、AD-10（`spine:148`）、AD-16（`spine:184`）都没有带上这条例外，读者要靠 AD-8 自己覆盖它们。
- **L8. 残留与 memlog 一致，另有一处提醒。** `wsctl:13` 的 “with a new link”、`worker.js:338-339` 的验证码文案、`deliver-temp.py` 的 Temp.sh 分支都确认存在；`worker.js:305-335` 还有 memlog 没列的旧文案（“下载满 {max} 次”），也已不用。本地 `workspace-onboarding` 的 `main` 过旧，按工作区去读会得出“没有别名逻辑”的错误结论。

## 已核实的断言

| AD | 断言 | 证据 |
| --- | --- | --- |
| AD-5 | PVE VM 名是 `oci-hub-<id>` | `terraform/remotecc/oci-hub-workspace.tf:58` |
| AD-5 | 系统 hostname 保持不变 | `ansible/playbooks/deploy-oci-hub-terminal.yml:66-73`，`hub-terminal.py:623` |
| AD-5 | 2026-11-04 用户决定不改名 | `tickets/epic-miniprogram-entry/tickets/tickets.toml:156`（记录存在，未回溯原始对话） |
| AD-5 | 设备包 `vm_hostname` 仍是 `oci-hub-<id>` | `hub-terminal.py:674`，`hub-bundle.py:28` |
| AD-5 | bootstrap 推出别名写入 SSH 配置 | `origin/main` `scripts/unix.sh:189-190,295`，`scripts/windows.ps1:320,339-340`；设备包字段要求 1.2.0 以上，所以别名有保证 |
| AD-5 | 网站 `hostname` 字段是别名 | `worker.js:1405` |
| AD-8 | 一条判定，快照、关机、提醒共用 | `hub-expiry.py:20-23,42-43`，`hub-enforce.py:52-54`，`hub-remind.py:82-88`；HAPI 也用（`hub-hapi.py:55`） |
| AD-8 | 生命周期显示 `no_expiry` | `hub-status.py:23` |
| AD-8 | `renew` 拒绝、`retire` 不列入 | `hub-expiry.py:111`，`hub-retire.py:79-81` |
| AD-8 | 不提醒、不关机 | `hub-remind.py:85-87`，`hub-enforce.py:52-54`（“不断开”见 H1） |
| AD-8 | 标记存于 catalog，可在控制台改 | `schema.sql:93`，`migrations/0011`、`0012`，手册:324，`worker.js:1519` |
| AD-17 | 存于 D1，put/get/delete 封装 | `schema.sql:48`，`worker.js:1214-1240` |
| AD-17 | D1 能存这个 BLOB | ArrayBuffer 写入为 BLOB，读回为 Array，`new Uint8Array(row.data)` 合用（`worker.js:1239`）；上限 2,000,000 字节，Worker 限 64 KiB（`worker.js:22`） |
| AD-17 | 登录后下载，不限次数 | `worker.js:1665-1682` |
| AD-17 | 只记设备、渠道、时间 | `worker.js:1244-1246`，`schema.sql:87` |
| AD-17 | 邮件不带设备包和链接 | `deliver-temp.py:297-322`，`test-temp-delivery.py:132,352-356` |
| AD-17 | 同设备只留最新一份 | `worker.js:1220-1227`；D1 `batch()` 是事务，失败整体回滚 |
| AD-17 | 退役时删除 | `hub-retire.py:242-245,283`，`worker.js:1282-1293` |
| AD-17 | 包内含私钥，无密码 | `hub-bundle.py:46`，`deliver-temp.py:53-60` |
| AD-17 | `reissue` 重传现有包，不轮换 | `oci-hub-admin.py:239-247`，手册:207 |
| AD-21 | “我的工作区”是唯一下载入口 | `worker.js:1974-1977` 是唯一返回字节的路由；`worker.js:1296-1306` 只返回 sha 和 available |

## 无法核实的断言

- **线上是否与 fe3f25e 一致：** 执行器和 Worker 的部署版本没读。`GET https://cc.willfan.me/d/<全零>` 返回 404，只是弱证据，因为旧版本遇到不存在的令牌也可能如此。
- **OCI 端 reconcile 的源码：** `services/oci-hub/executor.py` 不在清单内。H1 第二层依据测试和 `deferred-work.md`，两者一致。
- **邮件模板原文：** `templates/onboarding.html`、`mail-text.json` 不在清单内。“不带链接”依据 `message()` 传入的字段和测试断言。
- **小程序：** `employee-miniprogram` 不在清单内，“只提示到网站下载”只核到 `worker.js:247` 的文案。
- **D1 账户档位：** 决定 Time Travel 是 7 天还是 30 天，未知。
- **控制台改动能否触发 `employees_console_edit`：** 文档确认控制台可执行 SQL，触发器支持只有间接说法（FAQ 提到 create triggers）。迁移 0014 称 0012 已手工应用，线上没有实查。
- **“约 1.6 KB”：** 设备包在 `employee-data` 下，没有实测。当前格式比 2026-11-01 时多了字段，这个数字可能偏小，但离 64 KiB 上限很远。
- **用户决定的原文：** AD-17 的 2026-11-07 决定引用 WILL-116 评论，本次只看到 memlog 的转述。
- **线上是否已有 H1 描述的员工：** 需要 `wsctl status` 的 `user_block_reasons`，本次未运行。

## 来源

- [D1 Limits](https://developers.cloudflare.com/d1/platform/limits/)
- [D1 Time Travel](https://developers.cloudflare.com/d1/reference/time-travel/)
- [D1 Workers Binding API](https://developers.cloudflare.com/d1/worker-api/)
- [D1 Database (batch)](https://developers.cloudflare.com/d1/worker-api/d1-database/)
- [D1 Data security](https://developers.cloudflare.com/d1/reference/data-security/)
- [D1 Import and export](https://developers.cloudflare.com/d1/best-practices/import-export-data/)（未列出针对 BLOB 列的导出限制）
- [D1 Getting started](https://developers.cloudflare.com/d1/get-started/)
- [D1 FAQ](https://developers.cloudflare.com/d1/reference/faq/)
