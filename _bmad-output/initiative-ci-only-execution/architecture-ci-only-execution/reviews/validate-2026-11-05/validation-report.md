# CI-Only 架构 Spine 验证报告

**结论：** 不通过，spine 应保持 draft。lint 干净，主线覆盖 R1–R10，但有 3 个 critical 和 9 组 high 问题，其中 OCI hub 归属与 ticket 的 Done-when 直接冲突。

原始发现 48 项（rubric 15、consistency 17、reality 16），合并后 12 组阻断项和 12 项中等问题。低优先级项见三份原文。

## 审核记录

- **审核对象：** docs/architecture/ci-only-execution-architecture.md（worktree 未提交版本，基于 f42cb7e）
- **SHA-256：** d682a5b0df689497f56ec57d68bcf92bd69029670a69a6a569e58dde489b5e3b
- **lint_spine.py：** 通过，0 项
- **architecture-rubric：** PAL clink，claude-opus-5-5，rc=0，无权限拒绝，原文完整，15 项，$1.82（标价估算）
- **architecture-consistency：** PAL clink，claude-opus-5-5，rc=0，无权限拒绝，原文完整，17 项，$1.54（标价估算）
- **技术现实核验：** 原生联网子代理，16 项
- **跨模型：** 否。已批准的 reviewer 只有 claude-opus-5-5，与本会话同模型，这是独立会话评审，不是跨模型评审

## 需要你决定

- **D1 terraform/oci 里那两条 OCI 防火墙规则归谁？** 已修正：建议留在 terraform/oci，由 Jenkins 持有，并把 AD-14 的 OCI hub 收窄为主机上的 hub 服务。Terraform 只管 UDP 51824/51825 两条云防火墙规则，terraform/remotecc 没有 OCI provider，wsctl 也不写这份配置，迁走不划算。
- **D2 Jenkins restore 后丢失备份点之后的审批记录，是否接受？** 已修正：建议接受并写成已知风险，不新增审计存储。这符合你此前的决定，HCP 也保留 state 版本历史。
- **D3 Jenkins 升级排在什么时候？** 已修正：AD-13 仍排第一，升级放在 CT110 接管真实部署凭据之前。升级要重启 controller，受 AD-11 的 watchdog 门禁约束；2.580.2 与插件锁的兼容性未验证。
- **D4 HCP 是 Free 时 AD-5 怎么改？** 你判断是 Free，未在 HCP 上核实。Free 没有 teams，按 root 限权和只读 plan 的最小权限检查都要改写，建议先确认再更新 AD-5。

## 阻断项

### B1 [critical] OCI hub 有两个 owner

AD-14 禁止 Jenkins 碰 OCI hub，AD-4 又把含 hub NSG 和规则的 terraform/oci 交给 Jenkins，ticket 还要求 Jenkins 对该 root 完成 apply。

- 证据：terraform/oci/oci-hub.tf:27-52（已核对）
- 来源：F-01, ACR-01
- 处理：收窄 AD-14 的 OCI hub 定义，见 D1（实际只有两条规则，无活跃的第二写者）

### B2 [critical] control-plane 没有合法执行路径

owner 枚举放不下 CT107/CT110 的 playbook；terraform/proxmox 的 saved plan 还能替换正在运行它的 CT110；cloudflared 和 Gitea 同住 CT107，移交后没有写入路径。

- 证据：scripts/jenkins/transaction.py:108-111（已核对）
- 来源：ACR-02, F-06
- 处理：增加 control-plane owner，plan 触及时 fail closed

### B3 [critical] watermark 没有 owner

last_verified_sha 只写了 stored durably。存储位置、写入者、单调性、maintenance 是否推进、restore 后怎么办都未定义，这是“不丢变更”保证的核心。

- 证据：AD-6；controller-admission.py:212-220
- 来源：ACR-03, F-04
- 处理：定唯一存储和写入者，只沿 main 祖先前进

### B4 [high] 锁模型自相矛盾

全局锁是否穿过人工审批未定义；bounded queue 与 never refusal 在队列满时冲突；verify 失败后锁按字面永不释放；force-unlock 指哪把锁不明；admission TTL 60 秒撑不过排队。现有 runner 忙时直接拒绝。

- 证据：job-runner.py:118-121, 280-284（已核对）
- 来源：F-03, ACR-04, ACR-05, ACR-06
- 处理：作为一组重写，分开修会再次冲突

### B5 [high] main 的 push 触发大概率走不通

GitHubPushTrigger 靠轮询判断变更。Jenkinsfile-peer 没有 checkout，指南规定轻量 SCM job，首次构建之后的 push 会被静默丢弃。spine 只写了 may，没有定机制。

- 证据：Jenkinsfile-peer（已核对无 checkout）；docs/guides/jenkins-agent-bootstrap.md:29。线上 job 的实际取值未核实
- 来源：Reality H1
- 处理：定死 non-lightweight 或换触发器

### B6 [high] AD-13 的验收和隧道规则都有漏洞

简单 POST 在没配 secret 时也返回 400，探针会误判通过；探针须带 X-GitHub-Event: ping 和非空 JSON。带 X-Jenkins-Validation 的 POST 绕过验签返回 200。线上隧道未锚定，/x/github-webhook/ 能到达 Jenkins；restore 后也不复检。

- 证据：host_vars/jenkins.yml:14（已核对）；插件 master 分支源码，未在线上 POST 验证
- 来源：Reality H3, H4, ACR-14
- 处理：改探针定义，把隧道锚定列入首个变更

### B7 [high] Jenkins 版本落后于安全修复

BOM 和线上都是 2.568.3，2026-10-28 公告修复版本是 2.580.2；script-security、pipeline-groovy-lib 也在 2026-09-16 公告范围内。控制器将持有部署凭据，且有公网入口。

- 证据：ci/toolchain-bom.yml:6（已核对）；线上响应头
- 来源：Reality H2
- 处理：需要你决定，见 D3

### B8 [high] inventory 契约不完整

目录型 inventory 还会加载 bare_metal 和 terraform-remotecc.yml，Jenkins 可能依赖 RemoteCC state；site.yml 等宽目标 playbook 可解析到 RemoteCC 主机。

- 证据：ansible/ansible.cfg:6；ansible/inventory/（已核对文件存在）
- 来源：F-02, ACR-10
- 处理：列全来源，排除 remotecc，加主机 allow-list

### B9 [high] OCI 和多 root 事务没有形状

多 root 时审批是一条还是多条、部分失败怎么算、只读 plan 是否支持 OCI、peer 到 OCI 的身份都未定义。现有实现写死 proxmox。

- 证据：transaction.py:176, 211, 222；Jenkinsfile-plan:9
- 来源：F-08, ACR-07
- 处理：每 root 独立 manifest 和审批

### B10 [high] 凭据有两套存储面

runner 只绑定根文件里的版本化 secret，OCI key 却定为 UI 上传的 Jenkins credential；JCasC 接管时可能清掉 UI 凭据（JENKINS-64079，未实测）。

- 证据：controller-admission.py:119-123；job-runner.py:185-197
- 来源：ACR-08, Reality M3
- 处理：按 ID 声明唯一存储和写入者；保留 OCI key 走 Jenkins 的决定时要补绑定路径

### B11 [high] controller restore 会抹掉审计记录

Jenkins 构建记录是唯一审计存储，restore 替换整个 home，备份点之后的审批人和 mutation 记录会消失；AD-9 事件恰好发生在 Jenkins 不可用时。

- 证据：controller-maintenance.py:179-188, 314-315, 345-346
- 来源：ACR-09, F-14
- 处理：需要你决定，见 D2

### B12 [high] --check --diff 不是只读

AD-1 把它列为本地只读操作，但 ansible/ 下有 89 处 check_mode: false/no，这些任务在 --check 下照常执行。本地禁写靠流程约束是你的决定，这里不重议，只修正“只读”的说法。

- 证据：grep 已核对 89 处；未逐条判断是否有写入
- 来源：F-05
- 处理：审计这些任务，或收窄允许的 playbook 清单

## 中等问题

- **F-07：** 现存 Notion 同步这条外部写入路径没有决定
- **F-09：** 环境策略、容量、quarantine 运维、CT110 丢失、凭据轮换、CI 外部告警均未决定或推迟
- **F-10, Reality M2：** Job DSL 等插件不在 BOM，JCasC 模板没有 Mailer 和 webhook secret
- **F-11：** AD-12 靠下游 job 不存在来防变更，router 仍会转发
- **F-12：** “确认另一侧空闲”不留记录；AD-9 的 preferably 不可判定
- **F-13：** shared 变更在两个执行面上生效时间不同，没有跨面记录
- **ACR-11：** owner、handoff 状态分散在两个注册表
- **ACR-12：** maintenance 可在旧 SHA 上回退 main
- **ACR-13：** state backup 被 cleanup 删除后 recovery 无料可用
- **ACR-15：** apps lane 与 main lane 在 CT106 上没有共同 lock key
- **Reality M4：** ansible-core 2.19 本月 EOL，升级被 Python 3.11 和 cloud.terraform 卡住
- **Reality M5, M6：** transaction.py 没有 -lock-timeout；local 模式下 terraform-version 不起作用，lineage 须读原始 state

## 分诊说明

- F-05 说“否决决定在决策文件中找不到”：reviewer 没拿到 memlog，memlog 里有你 2026-11-05 的决定，所以这不是决策缺失。但 decisions-2026-11-05.md 确实没同步，建议补上。
- ACR 评审开头写“4 medium、3 low”，正文实际是 5 medium、2 low，本报告按正文计。
- ACR-08 的 JCasC 行为和 Reality M3 都来自公开 issue，没有在 configuration-as-code 2117 上实测。
- ACR-06 建议全局锁穿过审批，这会让一次待审批事务阻塞 plan 和 apps，只是候选方案，不是结论。

## 未覆盖与偏差

- X6 预检：失败。run_preflight.py 报 6 项 FAIL：缺少 PAL 的 _bmad/custom TOML，它们在 59503b1（2026-10-25）被删除。所以本次是按你的指令手动调用 PAL；实际调用和 reviewer 隔离参数已在 clink 返回里核对。
- PAL 服务绑定的是主 checkout 的描述文件，不是这个 worktree 的独立实例；source 是从 worktree 复制的跟踪文件，审核版本正确，但不符合 X2“每 worktree 独立实例”的字面要求。
- _bmad/custom 没有 bmad-architecture 的 TOML 覆盖，PAL 路由是按你这次的指令手动走的，不是配置驱动。
- source 排除了 vault.yml、两个 terraform.auto.tfvars、_bmad-output、remotecc/、.claude/、.agents/。
- 两个 PAL reviewer 都说明未读部分文件，rubric 未读 jenkins-agent-bootstrap.md，consistency 未读 docs/planning 下的 peer 文档。
- 线上 job 配置、security realm、SMTP、HCP 版本均未核实；没有向 webhook 发 POST，-lock-timeout 和 JCasC 重载未实测。
- 联网核验子代理超出了我的简报：对 jenkins.willfan.me 发了 4 个匿名 GET，并在沙箱外用 gh api 读了仓库 hooks 和 rulesets。都是只读，没有写入。

## 原文

- review-pal-rubric.md
- review-pal-consistency.md
- review-reality.md
