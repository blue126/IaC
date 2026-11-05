- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-executor-platform/tickets/story-ws-executor-vm-tailscale-plan.md`
  summary: 将 pve0 上未纳管的 VM 114 home-assistant、115 funasr、118 hindsight 导入 Terraform，每台先确认 plan 零改动再写 state。
  evidence: 2026-10-31 story 1.1 复核 VMID 时发现 115 被未纳管的 funasr 占用；用户同意三台一起 import，但不并入 1.1。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-executor-platform/tickets/story-ws-executor-vm-tailscale-plan.md`
  summary: 拆除 employee-workspace.tf 的 terraform_data.employee_retirement 墓碑，改为退役即从清单删除 + "已用槽位"列表的输入校验（VMID/nic_slot/地址永不回收），并入 epic 4 的 retire 设计。
  evidence: 2026-10-31 用户同意：墓碑自 #183 合并后从未 apply，重复了 plan SHA 审批的防线，且在 state 中留下永久不可删对象；1.1 apply 用 -target 排除它。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-executor-platform/tickets/story-ws-executor-vm-tailscale-plan.md`
  summary: proxmox-vm 模块默认 cicustom 片段 cloud-init-ubuntu.yml 覆盖 Proxmox 生成的 hostname，使用默认片段的 VM（如 mcp-gateway VM109）主机名都是模板名 ubuntu-24；应在片段或模块层修正。
  evidence: 2026-10-31 ws-executor 部署后 hostname 为 ubuntu-24，qm cloudinit dump 显示 hostname 为 ws-executor；VM109 同样为 ubuntu-24，cicustom=null 的 netbox 正常。ws-executor 已在 playbook 内单独修正。

- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-paid-through-enforcement/tickets/story-paid-through-oci-expired-plan.md`
  summary: 员工带着 expired 离开 paid_through 快照（改标 no_expiry、退役、删字段）时，OCI 不再移除其设备上的 expired；2.4 与 epic 4 在移出快照前须先推一次未来日期（或改为记录"曾由 timer 加过"的集合）。
  evidence: reconcile 只在 employee in paid 时拥有 expired（services/oci-hub/executor.py reconcile 设备分支），冻结意图要求快照外员工不处理。

- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-paid-through-enforcement/tickets/story-wsctl-renew-plan.md`
  summary: wsctl renew 改写整份 catalog，使计划与执行之间（或中途续跑）的其他员工开户因 HUB_TERMINAL_CATALOG_CHANGED 被拒，需重新 plan。
  evidence: hub-terminal.py _apply 对整份 catalog 做哈希比对（约 461 行）并以 catalog_after 整份保存；只忽略 paid_through 需同时在保存时合并当前 paid_through，否则会覆盖续费结果。

- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-apply-site/tickets/story-untitled-4-plan.md`
  summary: 执行器上 catalog 的设备 bundle_request / public_metadata_file 仍是 Mac 路径（/Users/weierfu/...），epic 1 迁移未改写；reissue 只用 bundle_output_dir 不受影响，但依赖这些字段的旧路径会失败。
  evidence: 2026-11-01 实测 control 设备 bundle_request 为 /Users/weierfu/Projects/IaC/remotecc/employee-data/oci-hub/runtime/migrate-vm502-20261030/desktop-bundle-request.json。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-apply-site/tickets/story-untitled-4-plan.md`
  summary: "下载满 3 次后 410 且内容清空"只由单元测试覆盖，未在线上实测（测试链接的验证码发送额度不足）。
  evidence: 下次真实交付时用一次 3 次下载补测。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-apply-site/tickets/story-cc-willfan-me-wsctl-request-plan.md`
  summary: cc.willfan.me 未做国内网络实测（用户暂缓）；验证码邮件从 Gmail 进了垃圾箱（新发信域名），需观察送达率。
  evidence: epic 3 Done when 要求国内网络可打开；2026-11-01 用户反馈验证码邮件进 spam。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-apply-site/tickets/story-untitled-plan.md`
  summary: BWS 机器账号按用户选择 B 同时可见 default 与 EmployeeWorkspace-OCIHub（检查已放宽为必须含 Hub、不得含旧项目）；如需更强隔离，可改为两个令牌（b4e4b04 已支持 bws_materialize.token_file）。
  evidence: hub-bws-store.py preflight（ca45a19）。

- retired: 2026-11-01 "执行器上 catalog 的设备 bundle_request / public_metadata_file 仍是 Mac 路径" — 已将 14 处前缀 /Users/weierfu/Projects/IaC/remotecc 改为 /srv/remotecc（备份 catalog.json.pre-path-fix），wsctl status 正常，快照 generation 17。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-reminders-and-retirement/tickets/story-wsctl-retire-plan.md`
  summary: 退役不删除 PVE SDN 对象（`oh<vmid>` vnet 与其 /30 subnet 留在 pve2）；资源可回收后，若 vmid 与子网被拆开分给不同员工，新建 subnet 可能因 zone+CIDR 冲突失败，需人工清理或让 oci-hub-pve 角色支持删除。
  evidence: 2026-11-02 用户选 B（资源可回收）；pve-sdn.py 只创建不删除。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-reminders-and-retirement/tickets/story-wsctl-retire-plan.md`
  summary: 非交互开户不可用：开户运行目录按含运行时凭据路径的 settings 计算，`wsctl provision --approve` 每次重新计划 SHA 都不同，跨两次 wsctl 调用找不到运行目录；Semaphore 无法开户。
  evidence: 2026-11-01 cc44 实测 WSCTL_APPROVAL_MISMATCH / FileNotFoundError state.json。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-reminders-and-retirement/tickets/story-wsctl-retire-plan.md`
  summary: 开户在设备包等待端到端验证（awaiting_e2e_verification）时返回结果取 `result['verification']` 抛 KeyError，各步骤已完成但命令以错误结束。
  evidence: hub-terminal.py `_apply` 返回语句；2026-11-02 cc44 实测。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-reminders-and-retirement/tickets/story-wsctl-retire-plan.md`
  summary: 现有 8 台员工 VM 的 authorized_keys 与 roster `admin_public_keys` 均不含执行器公钥（ws-executor），执行器无法登录这些 VM；需逐台补钥并同步 roster。
  evidence: 2026-11-02 cc44 配置步骤 Permission denied；新 VM 默认授权已加执行器公钥（settings.json.pre-executor-admin-key）。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-reminders-and-retirement/tickets/story-wsctl-retire-plan.md`
  summary: 4b30d2c（runtime vault 加密去掉继承 vault id）未经评审直接提交以解除实测阻塞，需补一次评审。
  evidence: employee-admin 4b30d2c。

- retired: 2026-11-02 "现有 8 台员工 VM 的 authorized_keys 与 roster admin_public_keys 均不含执行器公钥" — 记录有误：当时只查了 roster，未查 VM。实际 8 台 VM 的 authorized_keys 均已含 ws-executor，执行器 SSH 登录 8 台全部成功；仅 roster 的 admin_public_keys 登记未包含，不影响登录。

- retired: 2026-11-02 "开户在设备包等待端到端验证时返回结果取 result['verification'] 抛 KeyError" — 已修复（employee-admin 7fa91d2），结果新增 verification 字段显示设备包状态；评审 Pass 3 通过。
- retired: 2026-11-02 "4b30d2c 未经评审直接提交" — 已补评审（Pass 3），按 medium 意见改为带标签的 runtime vault id（7fa91d2）。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-miniprogram-entry/tickets/story-untitled-3-plan.md`
  summary: PUT /admin/status 用单个 D1 batch 写入 2+N 条语句，员工数增长后可能触及 D1 每次调用的查询上限（免费版 50）。
  evidence: maybe-false（未验证，若成立为 medium）；需查 D1 文档确认 batch 内每条语句是否单独计入上限，以及账户套餐；当前 8 名员工不受影响。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-miniprogram-entry/tickets/story-mosh-id-vm-plan.md`
  summary: 已开户 VM 尚未获得 oci-hub-mosh 的 sshd SetEnv（MOSH_SERVER_NETWORK_TMOUT）drop-in；需要一个对全部现有 VM 重跑 terminal_configure 的执行器命令。
  evidence: terminal_configure 只在开户时由 hub-terminal 按员工生成 inventory 运行；现有 VM 用系统 mosh-server 时没有网络超时，断线会话会一直保留（不影响 mosh <别名> 可用）。
- source_plan: none
  summary: 执行器 /srv/iac 的发布 hook 只 checkout 不跑 `terraform init`；IaC 改动模块来源（如 n8n 迁移）后，执行器上依赖 Terraform 状态的 wsctl 命令（status 等）会报 HUB_CHECKPOINT_COMMAND_FAILED，直到手动 init。
  evidence: 2026-11-02 UTC 04:00 起 `wsctl status` 每次失败；诊断为 `terraform state pull` 报 "Module source has changed"（n8n.tf）；在执行器上以 wsctl 凭据跑 `terraform init` 后恢复。应在 iac.git post-receive hook 或 wsctl 调用前自动 init。
- source_plan: `_bmad-output/initiative-employee-lifecycle/tickets/epic-miniprogram-entry/tickets/story-mosh-id-vm-plan.md`
  summary: oci-hub-mosh role 的 rescue 把写 drop-in 失败也报成"sshd -t 校验失败"。
  evidence: PR #220 Claude Review 非阻断发现 `oci-hub-mosh-sshd-rescue-message-misattribution`；需区分 template 失败与 sshd -t 失败。
- source_plan: none
  summary: OCI Hub 边界代码变更时重新验证跨员工隔离（6 项隔离检查），做成自动化探测。
  evidence: 2026-11-03 按用户决定移除逐设备包的验收门槛（employee-admin verify_end_to_end 改为 not_required）；隔离改在边界代码变更时验证。
- retired: 2026-11-04 "执行器 /srv/iac 的发布 hook 只 checkout 不跑 terraform init" — 已修复：wsctl 每次运行前比对 .tf 与 lock 文件哈希并自动 init，新根未初始化时也会 init（employee-admin 73f4cae）。
- retired: 2026-11-04 "已开户 VM 尚未获得 oci-hub-mosh 的 sshd SetEnv（MOSH_SERVER_NETWORK_TMOUT）drop-in" — 用户决定不做：只是断线会话多占一点内存，不影响使用。
- retired: 2026-11-05 "oci-hub-mosh role 的 rescue 把写 drop-in 失败也报成 sshd -t 校验失败" — 已修复（IaC PR #250）。
- source_plan: none
  summary: 员工文档站 cc.willfan.me/docs 尚未接入 apply-site，已写好的快速开始、HAPI 等页面员工看不到；transfer-files 页仍是“正在编写”。
  evidence: remotecc/docs/README.md 写明“计划由 apply-site Worker 发布，尚未接入”；用户 2026-11-05 决定在单独会话处理。
- source_plan: none
  summary: sync-deferred-work.py 默认读 _bmad-output/implementation-artifacts/deferred-work.md，本 initiative 的清单在 initiative-employee-lifecycle/deferred-work.md；默认路径下脚本报 ledger not found，需用 --ledger 或调整默认路径。
  evidence: 2026-11-05 运行 --dry-run 报 "deferred-sync: blocked: ledger not found"。
