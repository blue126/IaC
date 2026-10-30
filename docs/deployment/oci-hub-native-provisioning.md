# OCI Hub 原生 Mosh 开户

本入口位于私有 `remotecc/employee-admin/onboard.sh`。新方案使用独立 BWS 项目、Portal 账本和 PVE VNet；不经过 VM500。SSH、SFTP 与 Mosh 会话在员工 VM 内终止。

## 管理员操作

```bash
./onboard.sh --profile oci-hub provision --email alice@example.com
# 可选规格（核心数 / MiB / GiB）
./onboard.sh --profile oci-hub provision --email alice@example.com --cores 4 --memory-mib 8192 --disk-gib 80
./onboard.sh --profile oci-hub apply REQUEST.json APPROVAL_SHA256
./onboard.sh --profile oci-hub registry
./onboard.sh --profile oci-hub online
./onboard.sh --profile oci-hub export --device alice
```

`provision` 输出请求文件和精确审批 SHA，不执行创建。默认规格来自已配置资源池（当前2核 host、8GiB、50GiB、pve2-ssd、模板9001）；已有员工复用自己的 VM，不隐式调整规格。同一设备复用原密钥/地址；新设备使用 `--device` 指定独立 ID。纯数字邮箱用户名加 `user` 前缀，其余不加 `ed-`。碰撞时停止并说明冲突。

工具复用既有冷创建流程：PVE 独立子网及 hook → 受保护停机 VM → 受信任 QGA 核对/启动和 SSH 主机公钥 → 独立 BWS 记录 → VM 原生授权与 Spoke/Mosh → Portal 登记及配额 → 本地包。新模板克隆的 vendor-data 与 provider 生成的用户/主机名配置并存，不覆盖管理员 cloud-init 公钥。没有管理端点网络授权时停止，不扩大 Sandbox 网络范围。

曾由管理员停用的现有用户/工作区不会因普通重跑自动恢复；明确恢复时生成带 `--restore-existing` 的新计划。它只恢复本人用户和工作区，不恢复其他已撤销设备。用户/设备/工作区、计划及交付都绑定 `oci-hub` profile。

## 查询与交付

`registry` 读取 Terraform、PVE、Portal 和新后端台账；`online` 额外观察 WG 握手与目标 VM 的 SSH TCP/Mosh UDP 监听。近期握手或 UDP 监听不等于真人在线；查询错误显示未知，不能当作无人使用。此查询只覆盖新后端，旧后端仍用 `--profile existing online`。

本地包之后继续既有 `plan DELIVERY.json` / `deliver DELIVERY.json SHA256`，复用 Temp.sh POST 上传/下载校验及 Microsoft Mail.Send。请求需指定 profile、device_id、recipient、bundle_dir、run_dir、notify；只批准上传不代表批准发信。邮件使用当前模板，先展示收件人、真实链接与提示词，获准后发送。加密邮件缓存按原通道管理，不复制明文令牌。

VM509 本次专项验收由用户跳过：仅对其正式试点设备记录受保护的 `acceptance_waived` 与授权引用；身份、归属、主机公钥、包哈希与停用状态仍检查。其他未豁免设备继续要求原有验收记录。不得把跳过说成通过。

## 网络与旧后端退役

OCI 仅员工 WG UDP51824 接受任意 IPv4 动态来源；VM Spoke UDP51825 仍限家中公网。Mosh 端口位于 overlay 内，不公开到 Internet；管理端口策略独立。每用户5GB双向自然月额度及禁用原因仍在 OCI 执行。

2026-10-30 用户确认旧入口无人使用并授权后，VM500 六个旧员工入口服务已停用并屏蔽；VM500 主机作为 HAPI 控制面保留，管理 SSH、自身主机防护及历史凭据保留；员工网络隔离由 PVE 边界承担。默认/explicit existing 写入入口无条件拒绝；所有活动工作区通过 --profile oci-hub 维护。VM501 为 demo，VM502 为本人测试，VM509 底层地址已调到 10.236.9.2。见 [迁移与退役记录](2026-10-30-demo-test-hub-retirement.md)。当前无需再次执行用户已跳过的专项验收。

员工客户端 v2 原生 Mosh 已通过公开 workspace-onboarding PR #1 合并至 main（三平台 CI 通过）；设备包上传和邮件仍按独立授权执行。


## Portal 浏览器管理入口

2026-10-30 已部署 **https://wgportal.willfan.me/**，无需本地 SSH 转发或员工 VPN。Cloudflare DNS 的 A 记录直接指向 OCI，现有 Caddy 负责公网 HTTPS/证书，反代到 `127.0.0.1:8888`；Portal 后端端口仍不公开。Portal 使用已有管理员认证，未另外新增 Access 应用。

账号为 `admin@wgportal.local`，密码在 BWS 项目 `EmployeeWorkspace-OCIHub` 的 `OCI_HUB_PORTAL_ADMIN_V1` 记录 `secrets.admin_password`；不要将密码或 API token 贴入文档、聊天或 URL。界面可查看接口、设备及流量；启用/停用可以直接在 Portal 操作；开户、VM/地址分配及增额继续使用管理员入口，两者共用 Portal 接入状态。

维护使用 `ansible/playbooks/configure-oci-hub-portal-public.yml`，只配置既有 Caddy/Portal，不安装软件；`oci_hub_portal_external_url` 在 OCI 主机变量中持久化，完整 Portal 模板也使用此变量。运行前使用已批准的 OCI 管理 inventory 与严格主机公钥校验，按仓库约定在 Sandbox 执行。

上线核对：公网 TLS 校验成功、登录页 HTTP200、未登录 `/api/v1/interface/all` 返回401，Portal 后端仅监听127.0.0.1:8888，Portal/配额 timer active，既有 proxy.willfan.me 返回200。没有重置用户、接口、密钥或账本。


## Portal 单一状态源更新

2026-10-30 已部署。使用 `ansible/playbooks/update-oci-hub-authority.yml` 和私有工程现有 pack-oci-hub.py 的精确三文件 artifact 更新，不安装依赖、不重启 Portal 或 WG。任务暂停配额 timer、等待当前采样结束，持执行器锁备份月账、Portal 数据库和旧代码，随后通过 adopt_portal_state 审计迁移并恢复 timer。

本轮恢复材料在 OCI 的 `/var/lib/oci-hub/backups/portal-authority-20261030T070540761092Z/`，root 专用。不要用旧代码直接打开已迁移的新账本：identities.reasons 已移除；需要回退时必须核对匹配的代码/账本备份及更新后用量、Portal 人工操作，不覆盖这些新数据。

计量疑点由阻断改为审计估算；迁移保留原始样本、原月账，只补记尚未计入的可观测最低增量。已计入的重建样本不重复累加。`query` 输出 state_authority=wg-portal，reasons 由 Portal 现场返回。达到额度仍阻断所有本人设备；页面启用不替代增额。

实际验证：原生 Portal API 停用/启用测试设备后执行采样及等待多个 timer 周期，状态保持；rtt509-cpe 最终保持启用。正式设备和历史月账保留。专项安全/恢复验收仍按用户要求跳过，不把此次功能回归说成完整专项验收。

VM500 现仅保留 net0；旧 gateway 网卡/路由/NAT已清理，其防火墙只保护 HAPI 主机本身。维护勿再使用旧 gateway controller 的 --routing 模式，见 [VM500 清理](2026-10-30-vm500-legacy-nic-cleanup.md)。

旧 employee-access role、六个组合入口和 parallel 授权分支已移除。仍使用的管理员公钥维护由 admin-ssh-keys 提供，PVE 永久退役 guard 由 retired-workspace-boundary 提供；共享 snippets 和 Terraform 永久分配不删除。
