# 架构 spine 对手审核：HAPI 更新

- **日期：** 2026-11-05
- **对象：** `architecture-employee-lifecycle.md` 的 AD-2 HAPI 行、AD-16、AD-20、AD-22、AD-23
- **落地方案：** `docs/planning/2026-11-05-hapi-architecture-redesign.md`（下称“方案”）
- **依据：** 只读静态阅读 `ansible/roles/hapi-*`、`remotecc/wsctl/` 下的 `hub-*.py`、`wsctl`、`wsctl-secrets.py`、`oci-hub-admin.py`
- **未做：** 没有连接线上系统，没有读 settings、BWS、vault 或凭据，没有运行任何代码。下文的时序都是从代码和文字推出来的，没有现场复现。
- **审核通道：** `docs/agent/bmad-review-routing.md` 的 R0 要求架构一致性 adversarial 走 PAL reviewer。本次是调用方直接派给 Claude 的，没有经过 PAL，不能算作 PAL 跨模型审核。

## 结论

**spine 这次更新把“谁能写”定清楚了，但没定“写什么、按什么顺序写、发布时怎么写”，不建议按现在的文字开工。** 下一层单元逐条遵守 AD，仍能做出互不兼容的结果。共 12 对冲突：2 严重、5 高、5 中，另有若干低风险项。方向（推送、派生、发版与名单分离）不需要推翻，新增 AD-24（名单契约）和 AD-25（VM500 静态配置与启动顺序），再收紧 AD-2、5、10、14、16、20、22、23 即可。

| # | 严重度 | 冲突的两个单元 | 类型 | 要改的 AD |
|---|---|---|---|---|
| F1 | 严重 | `hapi-release` × `hapi-ctl apply` | 状态变更路径、发布并发 | AD-22、AD-23 |
| F2 | 严重 | `wsctl`（git push 即生效）× VM500 上的 `hapi-ctl` | 共享数据形状、发布并发 | AD-24（新）、AD-22 |
| F3 | 高 | IaC `trust.json` × `hapi-ctl` 的 `config.json` | 一个实体两个所有者 | AD-25（新）、AD-2 |
| F4 | 高 | IaC 角色 × `hapi-ctl`：静态路由、防火墙基础规则、首次启动 | 实体没有所有者 | AD-25（新）、AD-2 |
| F5 | 高 | `enforce` × `hapi-sync` | 共享数据形状 | AD-24（新）、AD-23 |
| F6 | 高 | `hapi-ctl` 的“无变化退出” × Nginx/防火墙重载 | 状态变更路径 | AD-23 |
| F7 | 高 | `enforce` × `hapi-ctl` 全量校验 | 共享数据形状 | AD-5、AD-16、AD-23 |
| F8 | 中 | 上一轮孤儿 `apply` × 下一轮 `apply` | 名单同步并发 | AD-24（新）、AD-16 |
| F9 | 中 | `retire` × `hapi-sync` × `enforce` | 状态变更路径 | AD-10、AD-14 |
| F10 | 中 | `hapi-sync` × 管理员手工改 Access | 一个实体两个所有者 | AD-2、AD-20 |
| F11 | 中 | 按 AD-2 读文件的单元 × `require_fresh_catalog` | 一个实体两个所有者 | AD-2、AD-13、AD-23 |
| F12 | 中 | `hapi-release` × `hapi-shared-hub`、`hapi-control-plane` | 一个实体两个所有者 | AD-22 |

---

## F1 严重：发布要重写派生文件，而 AD-23 不允许它写

**两个单元。** `wsctl hapi-release` 遵守 AD-22：切 `current`，方案第 98 行接着“重新生成配置 → 重载 Nginx”。`hapi-ctl apply` 遵守 AD-23：两份 Nginx 配置“只由 `hapi-ctl apply` 写入”，输入走 stdin，调用前必须通过 `require_fresh_catalog`，用 `flock` 串行。

**合规却不兼容的两种实现。**

- 实现 A：发布时调用 `apply` 并送名单。D1 读不到时就不能发布，也不能回滚，健康检查失败后的自动切回也会失败。这与“回滚只换代码”和 AD-22 的自动切回相矛盾。
- 实现 B：发布时本地从现有 `config.json` 重新渲染。D1 不可用时可行，但它是 AD-23 没有列出的第二条写入路径，不走 `require_fresh_catalog`，AD-23 也没有要求它拿同一把 `flock`。

实现 B 的时序：

```text
t0  enforce 的 apply 持锁，读 current/templates（版本 A）
t1  hapi-release 切 current -> 版本 B（不在 flock 内）
t2  apply 继续读 current/ 下的生成器或模板，得到 A、B 混合结果
t3  release 用 t0 之前的 config.json 渲染 Nginx，apply 写入新 config.json
    → config.json 与 Nginx 不是同一份路由快照，变更路由的指纹不一致，桥接 server 返回 409
```

AD-23 列在 Prevents 里的“路由与 Nginx 指纹错配”正是这个结果。

**“一次切换全部内容”本身不成立。** `current` 换掉的只有 `current` 下的文件。三层生效时间不同：

| 层 | 生效时刻 |
|---|---|
| 页面、Kasm 静态文件（`hapi-auth.py:413` 用 `__file__` 相对路径读页面） | 切软链接的瞬间 |
| `/etc/.../nginx.conf`（路由、CSP、location） | 重渲染并重载后 |
| 运行中的 `hapi-auth` | 重启后 |

新页面配旧 Nginx、旧鉴权的窗口依然存在，这就是 AD-22 要防止的“页面、客户端和路由分步生效”。自动切回同样是三步，只切软链接会留下“新 Nginx + 旧 current”。

**审批哈希也没定。** AD-1 规定“计划、输入或代码变化即拒绝”。方案第 97 行的计划输出含“配置差异”。如果 SHA 覆盖配置差异，那么计划与批准之间 `enforce` 的任何一次到期或续费都会使批准失效；如果不覆盖，AD 里又没有写明。

**建议修改文字。**

> **AD-23（替换第一句）** AD-2 列出的 VM500 派生文件只由 `hapi-ctl` 写入。它有两个写入子命令，共用同一把 `flock`：`apply`（送来名单，重算路由和全部派生文件）和 `activate <版本>`（不接收名单，用目标版本的生成器和现有 `config.json` 重新渲染 Nginx）。`require_fresh_catalog` 只约束 `apply`；`activate` 不改路由，也就不需要台账，D1 不可用时仍可发布和回滚。`hapi-ctl` 启动时解析一次 `current` 的真实路径，本次运行全程只用该版本目录。
>
> **AD-22（替换“`current` 软链接一次切换全部内容”一句）** `hapi-ctl activate` 持锁完成全部步骤：先用目标版本渲染候选配置并校验，再切软链接、替换配置、重载 Nginx，版本含 Python 改动时重启鉴权。健康检查也在持锁期间完成，失败时在同一把锁内用上一版执行相同步骤切回。切换过程中页面、Nginx 和鉴权进程可能短暂不一致，所以相邻两个版本必须能这样共存；不能共存的改动分两次发布。发布审批的 SHA 只覆盖版本、`manifest.json` 和候选模板，不覆盖名单和路由差异，名单变化不使批准失效。

---

## F2 严重：`wsctl` 和 `hapi-ctl` 的版本不同步，且没有协议版本

**两个单元。** 执行器上的 `wsctl`，和 VM500 上 `current` 里的 `hapi-ctl`。两者在同一个私有仓库，方案把这当作优点（第 70 行“一次提交能改完接口两端”）。

**冲突。** 方案第 92 行写 `git push remotecc-ops HEAD:main`，“此时线上不变”。这句话对 VM500 成立，对执行器不成立：`wsctl` 随这次 push 部署，5 分钟内 `enforce` 就会用新代码调用旧的 `hapi-ctl`。两端要等人工执行 `hapi-release` 才一致，而 AD-22 明确要求发布由人触发。回滚的方向更危险：`--rollback` 换回旧 `hapi-ctl`，`wsctl` 仍是新的。

AD-22 的兼容条款只管“动态文件”，不管 stdin 协议，而且只说了“新版本能读上一版”。

**最坏情况。** 回滚到 P4 之前的版本。旧的 `render()` 把 `enabled` 写死为 `true`（`hapi-registry.py:28`），不认识的字段直接忽略。每一轮 `enforce` 都送 `enabled: false`，旧 `hapi-ctl` 都写回 `true`，全部到期员工恢复登录，命令却报成功。

`--rollback <版本>` 允许回到最近 5 个版本中任何一个，可以跨过“改格式分两次发布”的边界。另外，`hub-onboard.py:132-133` 的审批哈希目前绑定 `hapi-registry`；代码迁走后，一份已批准的 `provision` 计划不再受 `hapi-control/` 变化的约束。

**建议修改文字。**

> **AD-24 — `hapi-ctl` 名单契约（新增，第一部分）**
> **Binds:** `hapi-ctl`、`wsctl enforce`、`wsctl hapi-sync`、`wsctl hapi-release`
> **Prevents:** 执行器与 VM500 代码版本不同步时静默写错；回滚恢复到期员工
> **Rule:** stdin 载荷带 `schema` 整数。`hapi-ctl` 只接受自己声明支持的 `schema` 范围，遇到未知 `schema` 或未知字段一律以 `HAPI_CTL_SCHEMA_UNSUPPORTED` 拒绝，不写任何文件。`wsctl` 只发送上一版和当前版都支持的 `schema`。要改协议时：先发布同时支持新旧 `schema` 的 `hapi-ctl`，再部署发送新 `schema` 的 `wsctl`。`manifest.json` 声明该版本支持的 `schema` 和动态文件格式，`hapi-release --rollback` 在计划阶段拒绝不支持当前 `wsctl` 或当前动态文件的版本。`--plan-only` 输出线上 `hapi-ctl` 与执行器 `wsctl` 的 `schema` 是否匹配。
>
> **AD-22（补一句）** 向执行器 `git push` 会立刻改变 `wsctl` 的行为，不算“线上不变”。

方案第 92 行的注释要同步改掉。

---

## F3 高：issuer、audience、origin 有两个所有者，其中一个没人读

**两个单元。** 瘦身后的 `hapi-control-plane` 按 AD-22 管 `trust.json`。`hapi-ctl` 按 AD-23 写 `config.json`，方案第 127 行要求“`config.json` 格式不变，鉴权代码不用改”。

**事实。** `trust.json` 只有角色写入（`hapi-control-plane/tasks/main.yml:94-103`），仓库里没有任何代码读它，它只是个触发鉴权重启的文件。鉴权的 issuer、audience、origin 全部来自 `config.json`（`hapi-auth.py:193-194`）。`render()` 用 `{**config, 'routes': routes}` 把这些字段原样带过去。

**两种合规实现的结果。**

- `hapi-ctl` 保持原样带过去：IaC 的 PR 改 audience，`--check --diff` 显示 changed，鉴权重启，然后什么都没变，继续用旧 audience。
- `hapi-ctl` 改为合并 `trust.json`：`hapi-auth` 的 `current_config()` 发现与启动时的值不同就抛 `Denied`（`hapi-auth.py:205-209`）。Stream guard 的 `watch()` 捕获到异常后切断**所有**在线流（`hapi-stream-guard.py` 的 `reconcile`/`watch`）。IaC 改了 `trust.json` 之后，只要 `enforce` 先于鉴权重启跑到，全部员工都会被拒绝。

同类的值还有几个。`shared_hub` 决定 Nginx 走 Hub 还是直连，目前只在 `config.json` 里，角色默认值是 `false`。Hub 监听地址同时存在于三处：`hub_address`（stdin，来自 settings 的 `control_address`）、IaC 变量 `hapi_shared_hub_bind_address`、`hapi` 角色的 `hapi_control_address`。Hub origin 也在 `hub.env` 和 `config.json` 里各有一份。

**建议修改文字。**

> **AD-25 — VM500 的静态配置与启动顺序（新增，第一部分）**
> **Binds:** `hapi-control-plane`、`hapi-shared-hub`、`hapi-ctl`、`hapi-auth`
> **Prevents:** 同一个信任值有两个来源；改信任值时切断全部在线流
> **Rule:** `trust.json` 是 issuer、audience、origin、`shared_hub`、Hub 监听地址的唯一来源，由 IaC 写入。`hapi-ctl` 每次运行都从 `trust.json` 读取这些值写进 `config.json`，stdin 不再携带 `hub_address`。IaC 改 `trust.json` 只写文件，不重启鉴权；改动经下一次 `hapi-ctl activate` 同时写入 `config.json` 并重启鉴权，两者在同一把锁内完成。`config.json` 里的这些字段不是事实，只是副本。

AD-2 的 HAPI 行要同时补一行：`VM500 信任配置 | IaC trust.json | config.json 是派生副本`。

---

## F4 高：“派生文件”里有派生不出来的内容，VM500 重建不了

**两个单元。** AD-23 说“IaC 角色不写这些文件”，AD-2 说它们全是派生文件。`hapi-ctl` 的算法却是读上一次的输出，再改一部分（`hapi-registry.py:74-76`）。

下面这些内容在执行器的输入里没有，只存在于被“派生”的文件本身：

| 内容 | 现在在哪 | 执行器能否重新给出 |
|---|---|---|
| VM502 的 route（含固定 `subject`）、credential、agent、token | 只在 VM500 上，`static_ids` 只有 ID | 不能 |
| `config.json` 的顶层字段 | 只在 `config.json` | 不能（见 F3） |
| `/etc/employee-access.nft` 的非 worker 规则（如 SSH） | `firewall()` 原样保留；仓库里没有写入这个文件的任务。`docs/deployment/2026-10-30-vm500-legacy-nic-cleanup.md` 第 20 行说长期配置由独立的 HAPI 工作负责 | 不能 |

**后果。**

- **重建 VM500 或任一文件损坏后：** `CONFIG.read_text()` 直接抛异常，`apply` 永远失败。IaC 又被禁止写这些文件，没有任何单元能创建第一份。
- **首次启动死锁：** IaC 把单元指向 `current`（`ExecStart`、`ExecStartPre --check`），但 `current` 要等 `hapi-release` 才有，`hapi-release` 的计划又要在 VM500 上用现有 `config.json` 跑 `nginx -t` 和 `--check`。角色的 `state: started` 在新机器上会失败。
- **空名单过不了校验：** `agents`、`credentials` 校验要求至少 1 行（`hapi-hub-config.py`），静态行丢失后，没有员工的新机器无法完成第一次 `apply`。

AD-2 把这些当派生文件，实际上静态路由是一个没有所有者的事实。

**建议修改文字。**

> **AD-25（第二部分）** 静态路由是事实，所有者是执行器 settings 的 `hapi.static_routes`，内容包含 `workspace_id`、`email`、`subject`、`address`、`namespace`；令牌放 BWS。`hapi-sync` 把它们和员工一起送到 VM500，`apply` 不再从已有文件读取任何路由。`employee-access.nft` 的基础规则由 IaC 写到单独文件，`hapi-ctl` 生成完整规则集时读取该文件，自己只拥有 worker 规则。
> 空白 VM500 的启动顺序固定为：IaC 建立用户、目录、`trust.json` 和单元（此时单元不启动）→ `wsctl hapi-release --bootstrap` 写入第一个版本 → `wsctl hapi-sync` 生成全部派生文件 → 启动单元。`hapi-ctl` 在派生文件缺失时按空状态生成，不报错。IaC 角色不依赖 `current` 存在。验收时必须在空白 VM 上走一遍这个顺序。

如果不想把 VM502 的 `subject` 放进 settings，也可以让它走普通员工路径并取消 `static_ids`。这是更干净的方向，但会影响 AD-23 里 VM502“保持原样”的决定，需要用户确认。

---

## F5 高：`enforce` 和 `hapi-sync` 送的“名单”不是同一种东西

**两个单元。** AD-23 只说“`enforce` 只送名单，`hapi-sync` 送名单和令牌”，没有定义名单。AD-16 只要求“是否到期”共用一份实现，没有要求名单共用一份构建函数。

**它们实际上做不到共用现有函数。** `hub-hapi.desired()` 每行都调 `ensure_hapi_token`，这个函数会读 BWS，缺令牌时还会**写 BWS**，记录缺失时抛异常。`enforce` 不能带上这些依赖，否则 BWS 故障会让到期推送失败，并让定时任务获得写 BWS 的路径。所以实现者一定会另写一个，两个构建函数就此分叉。

**已经能看到的形状差异。**

| 字段 | `hapi-sync` 现状 | 方案中的 `enforce` | 后果 |
|---|---|---|---|
| 地址 | `address`（执行器算） | `vmid`（方案第 121 行） | VM500 要复制 `10.236.<VMID-500>.2` 规则，或者两种调用得到不同 `backend_address` |
| 静态员工 | 过滤掉（`hub-hapi.py:76`） | 没写 | `enforce` 不过滤时，只因为本机没有该 ID 的令牌才没生成第二条 route；令牌一旦存在，同一邮箱两条 route，整份校验失败 |
| `static_ids`、`hub_address` | 带 | 方案第 131 行说随调用传，表里没列 | `enforce` 漏传时 `render()` 报错或清掉静态路由 |
| `enabled` | 现状没有 | 有 | 两边都要算 |
| 本机令牌 | stdin | 不带 | `credentials.json` 每行必须有 `token`，`enforce` 时只能从本机取，而本机有两份：`tokens/<id>` 和 `credentials.json` |

**VM502 的令牌会被删。** 方案第 130 行的回收规则是“既不在令牌列表、也不在名单里的 ID 才删”。VM502 是静态路由，不在 `entries` 里，也就不在这两个列表里，照字面实现，下一次 `hapi-sync` 就会删掉 `tokens/vm502`。之后 `exchange()` 读不到令牌，owner 的登录返回 503。现有代码的判断是“不在任何 route 里”（`hapi-registry.py:110-113`），方案改写时丢掉了静态这一层。

**建议修改文字。**

> **AD-24（第二部分）** 名单只由 `hub-hapi.roster(cat, settings, now)` 构建，`enforce` 和 `hapi-sync` 都调用它，它不访问 BWS。每行固定为 `{id, email, address, enabled}`，`address` 在执行器算好，已过滤静态员工。载荷固定为 `{schema, as_of, catalog_generation, static_ids, employees, tokens?}`，`tokens` 是 `{id: token}`，只有 `hapi-sync` 带。VM500 不计算地址，也不判断到期。
>
> **AD-23（替换令牌相关句子）** `tokens/<id>` 是 VM500 上令牌的唯一本机来源，`credentials.json` 从它生成。名单中没有 `tokens/<id>` 的员工不生成 route、credential、agent 和防火墙规则。只有带 `tokens` 的调用才回收令牌：既不在 `tokens`、也不在名单、也不在 `static_ids` 里的文件才删除。

---

## F6 高：“结果没变就退出”破坏了现有的重载重试

**两个单元。** 方案第 126 行：“结果没变就直接退出，不重载。绝大多数 `enforce` 都是这样。” 现有代码特意相反：`hapi-registry/tasks/main.yml:115-116` 注释写明每次都重载，因为“上次写了文件但重载失败，下次必须还能加载”；`hapi-registry.py:106-108` 对防火墙也是这样处理。

**时序。**

```text
t0  员工 A 续费，apply 把 config.json 的 enabled 改为 true（指纹变了）
t1  systemctl reload hapi-control-proxy 失败，或 SSH 断开、进程被杀
t2  下一轮 enforce：候选文件与磁盘一致 → “无变化”退出
t3  之后每一轮都一样：guard 送新指纹，Nginx 还是旧指纹，桥接 server 永远返回 409
```

AD-23 的“全部校验通过才替换”管不到替换之后的步骤。结果是员工已付费，路由“已启用”，HAPI 一直不可用，而且 `enforce` 每轮都报成功，直到名单下一次变化才顺带修好。防火墙有同样的问题：文件已换但未加载，新员工的 Runner 连不上 9443。

**建议修改文字。**

> **AD-23（补充）** “无变化”的判断同时比较文件内容和已加载状态。`hapi-ctl` 把两份 Nginx 配置和防火墙规则各自的 sha256 写到 `/run/hapi-control/loaded.json`，只在对应的 `nginx -t` 和重载或 `nft` 加载都成功后才写；文件哈希与它不符、或它不存在（重启后）时必须重新加载。替换顺序固定为令牌 → Hub 文件 → `config.json` → Nginx 与防火墙加载。重载失败时 `apply` 以 `HAPI_CTL_RELOAD_FAILED` 退出，下一轮重试，不回滚已替换的文件。

---

## F7 高：一行坏数据冻结全体的到期处理

**两个单元。** `enforce` 遵守 AD-16：失败就“下一轮重试”。`hapi-ctl` 遵守 AD-23：“全部校验通过才替换”。

**冲突。** 现在全量校验只在开户和退役时跑，以后每 5 分钟跑一次，任何一行不合法都会让整份名单被拒绝。下一轮数据还是一样，重试永远不会成功，并且没有任何机制把它和网络抖动区分开：

- 新到期的员工一直能登录，已续费的员工一直进不去，所有人都受影响。
- 这期间 `enforce` 的关机继续，形成 AD-16 明确接受的“推送失败”状态，但 AD-16 假定它是暂时的。

**这种数据不是假想的。** AD-5 说邮箱是唯一标识，但执行器代码明确支持共用邮箱：`hub-expiry.py:85` 注释“Several employees may share one administrator mailbox”，`test-hub-expiry.py:131` 有专门的测试。而 `hapi-registry.py:71-73` 遇到重复邮箱就 `SystemExit`，`load_config` 也拒绝重复（`hapi-auth.py:174-180`）。其他能触发的还有：大写邮箱（`hapi-auth.py:162`）、ID 超长（`hub-enforce` 不校验，`hapi-auth` 限 32 字符）。原来挡这些的 Ansible assert（`hapi-registry/tasks/main.yml:2-13`）随角色删除后要有新的归宿。

**到期判断还差一种结果。** 方案要提取 `hub-expiry.expired(row, now)`，这是布尔函数，但 `hub-enforce.py:54-58` 有第三种结果：`paid_through` 无法解析时报 `ENFORCE_PAID_THROUGH_INVALID` 并跳过。提取后要么返回 `False`（坏数据的员工等于永不到期），要么抛异常（一行坏数据使整份名单构建失败，又回到上面的问题）。两种实现都符合 AD-16 的文字。`hub-status.py:29-30` 也有一份自己的比较，“只有一份实现”目前并不成立。

**建议修改文字。**

> **AD-5（补一句）** HAPI 要求一个邮箱只对应一名员工。共用邮箱的员工可以留在 catalog 里，但 `roster()` 不为他们生成 route，并在结果中报告 `HAPI_EMAIL_SHARED`。
>
> **AD-16（替换“是否到期”一句）** 到期判断只有 `hub-expiry.state(row, now)` 一份实现，返回 `exempt`、`active`、`expired`、`invalid`，`enforce`、`hapi-sync`、`hub-status` 共用。`invalid` 的员工不关机、不开机，其 route 保持上次已应用的 `enabled`。
>
> **AD-23（补充）** 校验分两层。整体不合法（`schema`、结构、Nginx 测试失败）时不写任何文件。单行不合法时只隔离该行：该行保持上次已应用的状态，其他行正常生效，结果里用 `rejected` 列出。`rejected` 非空时 `enforce` 报告失败，并写入 `wsctl status` 与每日摘要（AD-14）。

---

## F8 中：`flock` 只保证互斥，不保证顺序，推送也没有超时

**两个单元。** 上一轮 `enforce` 留在 VM500 上的 `apply`，和下一轮的 `apply`。

**事实。** `h.run` 没有超时（`hub-onboard.py:75-76`）。`ssh` 的 `ServerAliveInterval` 只能发现网络断开，远端等 `flock` 或等 `systemctl reload` 时连接是活的。

**第一种情况：卡住。** 远端 `apply` 卡在 `flock` 或重载上，`enforce` 就卡在 SSH 上，一直持有执行器的 `wsctl.lock`。这一轮的关机不会发生，其他 `wsctl` 排队直到 1800 秒后报 `WSCTL_BUSY`。AD-16 说“名单推送失败不阻止关机”，但卡住不算失败。

**第二种情况：加上超时之后。** 超时杀掉 SSH 客户端，远端进程不一定退出。`wsctl.lock` 释放，下一轮的推送或 `hapi-release` 随后开始，孤儿进程排在后面拿到 `flock`，把旧名单写回：

```text
t0  enforce N：员工 A 已到期，名单 A=false，SSH 超时，远端还在等锁
t1  管理员 renew A
t2  enforce N+1：名单 A=true，先拿到锁，写入
t3  孤儿 N 拿到锁，写回 A=false
```

这种情况下一轮能自愈，所以是中等。但 AD-12 为 OCI 快照解决的是同一个问题，AD-23 没有照做。只用 D1 的 `generation` 不够：到期是时间变化，catalog 不变。

**建议修改文字。**

> **AD-24（第三部分）** `hapi-ctl` 记录已接受的 `(catalog_generation, as_of)`，拒绝不大于它的载荷（`HAPI_CTL_STALE`），不写任何文件。`hapi-ctl` 等锁最多 30 秒，超时报 `HAPI_CTL_BUSY`。
>
> **AD-16（补一句）** 名单推送整体限时 60 秒，超时按推送失败处理，继续本轮关机与开机。

`as_of` 与 `now` 都取自同一轮 `enforce`，且 `as_of` 用执行器时钟，VM500 只比较不换算。

---

## F9 中：AD-10 的删除顺序做不到，失败后的残留也没人清

**三个单元。** `retire` 遵守 AD-10，“接入（Portal 身份、HAPI Access 放行与 route/credential/agent）→ Terraform VM → BWS → R2 → catalog”。`hapi-sync` 和 `enforce` 遵守 AD-20、AD-23，从 catalog 派生。

**冲突。** 只要 catalog 里还有这名员工，派生结果就包含他的 route。所以 HAPI 清理不可能排在 catalog 之前。现有代码确实放在最后（`hub-retire.py:286-290`），只有文字是错的。如果下一层按 AD-10 字面实现，提前调用一次带排除项的 `hapi-sync`，中断后下一轮 `enforce` 会把 route 加回来。

**中断窗口。** 退役中断在 BWS 删除之后、catalog 删除之前时：

- `desired()` 对这行抛 `HUB_BWS_HAPI_RECORD_MISSING`，或者 boundary 已删时 `pve_grants` 抛 `HAPI_WORKSPACE_NOT_ALLOCATED`。整个 `hapi-sync` 对所有员工失败，新员工开户也拿不到 route，直到退役续跑完成。
- 强制退役（`--force`）的在册员工 route 仍是 `enabled: true`，指向已销毁的 VM。

**失败后的残留。** 方案第 149 行接受“令牌、PVE 授权和 Access 邮箱留到下次 `hapi-sync` 清理”，但 `hapi-sync` 只在开户、退役和手动时运行，AD-14 的孤儿资源也不包括 HAPI。Access 里留着已退役的邮箱，可以一直没人发现。

同一邮箱再开户（AD-10 允许）时，残留令牌造成一个具体问题：`ensure_hapi_token` 在新 BWS 记录里生成新令牌，新 VM 的 Runner 用新令牌。如果开户的 `hapi-sync` 失败（失败只报告），`enforce` 名单里有这个 ID，本机又有旧令牌，就会生成 route，其 credential 是旧令牌。AD-23 “本机没有令牌不生成路由”的防护在这里失效，正好产生它要防止的半成品。

**建议修改文字。**

> **AD-10（替换删除顺序一句）** 删除顺序：Portal 身份 → Terraform VM → Hub/PVE boundary → BWS → R2 → catalog → `hapi-sync`（route、credential、agent、令牌、Access 放行随 catalog 派生）→ 推送快照。强制退役在第一步之前先把该员工从 `roster()` 的输出中排除，并执行一次 `hapi-ctl apply`；排除项记入运行记录，`enforce` 读取未完成退役的排除项，防止中断后 route 回来。`desired()` 遇到正在退役的员工时跳过，不让整次同步失败。
>
> **AD-14（补充）** Semaphore 每日运行一次 `wsctl hapi-sync`。孤儿资源增加：VM500 上有令牌而 catalog 无员工、Access 有邮箱而 catalog 无员工、`hapi-ctl` 最后一次已接受的 `as_of` 距今超过 30 分钟。

---

## F10 中：Cloudflare Access 名义上是所有者，实际上被当作派生物覆盖

**两个单元。** AD-2 把“HAPI 身份放行”的唯一所有者写成 Access 策略，写法和 wg-portal 一样，而 AD-11 规定 Portal 上的手工操作是合法状态。`hub-hapi.access()` 却用 catalog 的邮箱集合整份替换策略（`hub-hapi.py:119-122`）。

**冲突。** memlog 记录的用户决定是“紧急情况用 Cloudflare Access 删除或 VM 关机”，用来替代取消的 `hapi-ctl block`。这个路径有三个问题：

- 管理员手工删掉一个邮箱，下一次任何员工的开户或退役都会把它加回来，不提示。
- 加一条 block 策略更糟：`access()` 抛 `HAPI_ACCESS_FOREIGN_POLICY`（`hub-hapi.py:114-115`），每次 `hapi-sync` 都失败。
- 方案第 167 行自己写了“Access 策略改了，已签发的 JWT 不会失效”。所以这条紧急路径对已登录的人不立即生效，而 route 又没有人工开关。

AD-20 还写着“只在开户时添加、退役时删除”，这与整份替换的实现也不一样。

**建议修改文字。**

> **AD-2（替换 HAPI 身份放行行）** `HAPI 身份放行（邮箱）| 不存储：catalog 派生 | Cloudflare Access 策略是投影，只由 hapi-sync 整份写入；手工修改会被下一次 hapi-sync 覆盖`
>
> **AD-20（替换 Access 一句，并补一句）** Access 放行由 `hapi-sync` 按 catalog 整份同步。没有 HAPI 紧急封禁：Access 手工改动既不持久，也不影响已签发的 JWT。需要立刻处理某名员工时，能做的只有手工关闭其 VM；其 route 要到到期或退役才停用，这期间仍能登录并看到 Hub 里的会话记录。

用户如果希望紧急路径更快，这里需要一个决定；这条建议只是把现有决定的实际效果写准确。

---

## F11 中：spine 说 catalog 在执行器文件里，AD-23 的新鲜度检查针对的却是 D1

**两个单元。** 按 AD-2 第 76 行读 `employee-data/.../catalog.json` 的单元，和按 AD-23 调 `require_fresh_catalog` 的单元。

**事实。** 现状是 D1 为事实来源，本地文件只是快照（`hub-terminal.py:37-41`），方案第 53 行也写“员工名单、到期日 | D1”。但 spine 的 AD-2 把本地文件写成所有者，AD-13 还写着“D1 只存申请内容与下载记录”。AD-23 引用了一个 spine 里没定义的概念。

**冲突。** `require_fresh_catalog` 不看本次读到了什么，只读旁边的 `catalog-source.json`，这个标记是上一次 `catalog()` 调用留下的（`hub-terminal.py:70-79`）。一个按 AD-2 直接读文件的单元，再按 AD-23 调用检查，看到上一轮留下的 `source: d1` 就会通过，用的却是任意旧的快照。

**建议修改文字。**

> **AD-2（替换员工行、`paid_through` 行的位置说明）** catalog 的事实来源是 D1，经 `/admin/catalog` 按 `generation` 比较写入；`catalog.json` 是执行器上的快照，不是所有者。
>
> **AD-13（修改）** D1 存申请内容、下载记录和 catalog，不存凭据。
>
> **AD-23（补一句）** 名单必须来自同一进程内刚刚成功的 `catalog()` 调用，`roster()` 的 `catalog_generation` 取自这次调用的返回值，不直接读快照文件。

---

## F12 中：IaC 与发布的分界线上还有几个文件归属不明

**两个单元。** `hapi-release` 和瘦身后的两个角色。AD-22 的判断标准（“换一名员工或改一行页面时要动的东西”）对下面这些文件给不出唯一答案：

| 文件 | 冲突 |
|---|---|
| `hapi-hub-config.py` | 方案第 52 行归私有发布，第 78 行的版本目录里却没有列它。P2 要把 Hub 三个 `ExecStartPre` 指向 `current`，而角色的 `validate` 和 verify 也用它。新版本改了校验逻辑，发布时 Hub 不重启，健康检查不会发现，下次 Hub 重启才因为拒绝 IaC 写的 `jwt-secret.json` 或迁移标记而起不来。回滚到一个不含它的版本时同样如此 |
| `authorize.inc` | AD-22 说 Nginx 模板归私有，AD-2 的派生文件只列“两份 Nginx 配置”，方案没提。现在它由角色写入，并被 `nginx.conf` 引用。如果留在角色里，Nginx 配置就有两个所有者，两边版本可以错开 |
| `hapi-login-portal/` 路径 | `hapi-auth.py:413` 写死读 `hapi-login-portal/index.html`，方案第 79 行的版本目录叫 `portal/`。P2 又要求“代码与线上字节相同”。二者不能同时成立 |
| Nginx 里的 `/usr/local/lib/...`、`/usr/share/novnc/` | 模板里的路径要改成 `current`。若改成 `releases/<版本>`，则与 AD-22 的切换模型不同 |

**建议修改文字。**

> **AD-22（补充）** 一个文件只有一个发布路径：只被 Hub 单元和 IaC 使用的校验器（`hapi-hub-config.py` 的 `jwt`、`migration`）随 IaC 发布，放 `/usr/local/lib`；`credentials`、`agents`、`bindings` 校验随 `hapi-control/` 发布。`authorize.inc` 与两份 Nginx 配置同为 `hapi-ctl` 生成的派生文件。发布的健康检查必须运行一次这些单元的全部 `ExecStartPre`，不重启服务也要发现校验不通过。

---

## 低风险项

- **AD-3 没有跟上。** 状态图的“已到期”条件没有 route，`config.json` 的 `enabled: false` 字面上是持久化的到期状态。建议在 AD-3 写明 VM500 的 `enabled` 是派生缓存，不是 `hub-status` 的输入。
- **AD-20 与冻结的决定有出入。** 用户已决定“拉不到台账时名单冻结，不拒绝员工”。此时 OCI 继续断开 WireGuard，HAPI 不动，“到期与续费对两种方式同时生效”不成立。这是已接受的风险，建议在 AD-20 加一句例外，并写明冻结没有时间上限。
- **静态员工到期。** AD-16 要求到期停 route，AD-23 要求静态路由保持原样。静态员工如果不是 `no_expiry`，VM 被关而 route 还开着。建议写明静态员工必须是 `no_expiry`。
- **`hapi-ctl` 的调用方。** AD-23 说只由 `wsctl` 调用，方案第 132 行说 `flock` 防“手动运行”。VM500 上的 sudo 也没有限制到这一个命令。建议二选一，并在 P0 把 sudo 规则列入确认项。
- **AD-2 缺两行。** first-login 绑定的所有者是 `hapi-auth` 的 SQLite；Hub 数据库里按 namespace 存的会话记录没有所有者，退役不清理，同一邮箱再开户后还能看到。AD-10 写“VM 数据永久删除”，读者会以为都删了。
- **P2 到 P5 只靠人记。** 这段时间内运行 `deploy-hapi-control-plane.yml` 仍会用空列表覆盖路由（默认值 `hapi_control_plane_routes: []`），观察期至少一周。建议 P2 就在两个 playbook 开头加一条失败的 assert，而不是只写在文档里。
- **版本清理。** “保留最近 5 个版本”没有写不能删 `current` 和上一版。
- **Consistency Conventions。** 命令名一行没有 `enforce`；确认一行没有 `hapi-release`。
- **范围之外的旧内容。** AD-2 的 BWS 项目名 `EmployeeWorkspace-OCIHub`、Structural Seed 的 `remotecc/employee-admin/` 都已过时（`AGENTS.md` 已是 `remotecc` 项目和 `remotecc/wsctl/`），本次没有改动它们。

## 查过没有问题的点

- 到期时 first-login 绑定不会丢：`enabled: false` 的 route 仍在 `routes` 里，`subject()` 的清理只看 `(workspace, email)`。
- 到期切断是及时的：stream guard 每 0.25 秒检查 `config.json`，不依赖 Nginx 重载。
- D1 不可读时不会用空名单覆盖：`catalog()` 对 `generation` 为 0 或读失败的情况回退快照并置标记，`require_fresh_catalog` 会拒绝。
- 同一执行器上的常规并发由 `wsctl.lock` 串行，`hapi-sync` 和 `enforce` 在正常路径上不会撞车；F1、F8 针对的是这把锁管不到的情况。
- 角色用空变量覆盖路由的风险：瘦身后两个角色不再写动态文件，这个风险确实消失（方案第 61 行）。瘦身之前的窗口见低风险项。

## 需要用户决定的事

1. F4：VM502 继续做静态路由（把 `subject` 放进 settings），还是改走普通员工路径并取消 `static_ids`。
2. F10：接受“没有快速紧急封禁”，还是要一个最小的 route 级紧急手段。之前已决定取消 `hapi-ctl block`，当时的前提（Access 可以当紧急手段）并不成立。
3. F7：共用邮箱的员工今后是否需要 HAPI。需要的话，`hapi-auth` 的“一个邮箱一条 route”要改设计。
