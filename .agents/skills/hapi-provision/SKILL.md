---
name: hapi-provision
description: "管理、开发和审阅本 IaC 项目独立的 HAPI/Cloudflare 员工 VM 开户流程；核对真实执行绑定、基础设施与应用就绪、统一身份入口和首次 Claude 网页授权。不用于 WireGuard employee-provision、一般云主机测速或单纯维护现有 VM502。"
---

# HAPI 员工网页工作区开户

本 skill 为项目本地、显式调用入口。先读[开户设计及就绪契约](../../../docs/architecture/hapi-workspace-provisioning.md)和[管理员运行绑定](../../../docs/guides/hapi-admin-runtime.md)。HAPI 与 WireGuard 的 `employee-provision`／`onboard.sh` 使用独立执行器、登记、state、BWS授权及交付；不把本流程作为旧入口的 profile。

## 当前能力与真实入口

VM500已运行统一入口、身份网关、单个HAPI Hub应用服务（VM500）和会话数据库；VM502保留原Runner、Claude及localhost3006兼容代理。既有用户已确认统一入口可用。这不等于新员工完整开户或全新VM首次Claude授权已验收。

正式私有源码位于主检出的`~/Projects/IaC/remotecc/hapi-admin/`，运行数据在同级`hapi-data/`。先读私有README，再使用真实入口核对帮助和执行绑定：

```bash
python3 ~/Projects/IaC/remotecc/hapi-admin/hapi-entry.py --help
python3 ~/Projects/IaC/remotecc/hapi-admin/hapi-entry.py doctor
```

`doctor`不创建员工登记。入口按`admin-binding.json`选择IaC工作树、只读管理员源码、可写独立数据目录及指定Sandbox；所有台账和Terraform／Ansible操作通过该入口分发，不在宿主直接运行受管Ansible，不切换到另一个worktree的数据副本。

当前命令为`doctor`、`request`、`plan-infra`、`apply-infra`、`status`，具体参数以真实`--help`和README为准。基础设施阶段有申请／预留、单VM计划、原state归属校验、启动门禁、执行回读及故障恢复；完成状态仅为`infrastructure_ready`。真实profile、分配池和管理通道仍需精确绑定与授权。

应用安装、服务秘密／PKI、租户发布、Cloudflare首次subject绑定、入口启用、员工交付及完整生命周期尚未串成已验收后端。不得把`execution_context_ready`或`infrastructure_ready`报告成`services_ready`／`public_entry_ready`。收到完整开户请求时，说明实际缺少的阶段，继续准备已授权材料，不虚构不存在的命令。

## 应用开户候选代码

应用阶段候选实现见[应用开户说明](../../../docs/guides/hapi-application-onboarding.md)。`plan-app`、`apply-app`、`complete-app`目前只存在任务工作树的私有开发副本，未同步到正式入口、未部署，不能从正式命令帮助中假定它们可用。

用户选择暂不安装新Sandbox的BWS SDK。缺少固定版本SDK时，执行器必须在外部写入前停止；不得绕用旧Sandbox、复制旧虚拟环境或自行安装。重新计划保留同一申请已验证的身份与原票据；无证明的过期票据只能经新计划审批替换，不交付失效链接。审批校验在申请锁和VM500发布锁内完成，状态更新绑定当前plan ID。`awaiting_identity`表示应用服务已验证，但本人身份尚未完成确认、路由仍关闭。`identity_verified`表示已取得真实身份证明、等待启用；此时交付材料不再附带首次身份链接。首次启用失败后的禁用路由，仅在申请标记、VM绑定和原证明全部匹配时允许重新计划；其他归属及已ready后的恢复不接管。`route_enabled`只表示VM500登记和私有服务回读通过；公网路径验收完成前，`public_entry_ready`保持false。

应用登记由独立管理员执行器管理。存在应用登记后，普通共享Hub／控制面角色必须在任何写入前拒绝用静态Vault覆盖；当前运行Vault仅是既有VM502基线快照，不能充当后续员工的完整登记来源。HAPI防火墙例外存入独立文件，由明确支持该扩展的防火墙控制器加载和校验，不改写WireGuard基础规则文件。开户仅校验已部署共享防火墙控制器的批准摘要，不替换该控制器；版本不符须先由其原角色或独立迁移计划发布。HAPI扩展失败不得关闭已经通过校验的WireGuard基础转发。

## 申请、计划与资源归属

- 默认输入是邮箱；只在HAPI登记中派生或核定稳定ID。规格、干净模板、VMID／IP／MAC、网络边界、state和秘密引用进入精确计划；不猜空闲资源。
- 同一邮箱在WireGuard登记存在不代表可共用VM、密钥或state。底层VM模块和公共角色可以复用，资源所有权须独立核对。
- 沿已实现阶段执行，保存意图、精确资源ID和回读结果；结果不明先查实际对象与state，不重复创建、轮换或发送。代码、输入或归属变化后重新计划。
- Terraform管理的VM使用原state生成精确变更／destroy plan；核对lineage、资源地址及VM身份。不用`qm destroy`或`state rm`绕过其管理关系。个人认证异常不触发销毁／重建。
- QA VM9101／9102已在2026-10-31按原Terraform state回收，见[回收记录](../../../docs/planning/2026-10-31-hapi-qa-retirement.md)。旧提案、Vault和计划只作证据，不作为新员工槽位或可重放输入。需要完整验收时通过新流程从干净模板按需创建。

## HAPI Hub（VM500）、身份与凭据边界

VM500承担Cloudflare Tunnel终结、统一网页／登录引导、身份网关、共享Hub和数据库。员工VM运行Runner、Claude、个人浏览器及受限登录执行／画面服务，使用原批准默认路由；不在每台员工VM部署Hub，不把VM500作为开发流量的通用出口。

统一`hapi.willfan.me`以受验证Access身份绑定固定namespace和本人VM。浏览器完成一次Cloudflare登录后自动建立HAPI短期会话，不再要求HAPI基础token登录；个人Claude授权在缺失或过期时由本人完成。客户端邮箱头、VMID、机器ID及namespace后缀不能扩大权限；HTTP、SSE、Socket.IO、RPC与RFB均遵循同一归属和撤销要求。

当前服务配置索引在私有`hapi-data/credentials/service-runtime.json`；它描述既有VM502基线，新增应用登记按上文的独立执行器管理，不重放旧Vault覆盖。BWS独立`HapiWorkspace`管理服务凭据，员工／Runner凭据固定绑定namespace并可撤销。共享Hub签名密钥只物化到VM500；CA签发权限及BWS管理员token留在管理员环境。浏览器不接收长期基础token，员工VM不接收Tunnel token、共享签名密钥或其他员工凭据。

现有统一入口和VM502的任务、项目、个人认证保持原归属，不因新开户重启或迁移。VM500的WireGuard历史配置属于独立迁移范围，不在HAPI开户中接管、复用业务登记或擅自移除。

## Claude登录与验收

首次登录复用`claude-login-agent`／`workspace-login`及固定API。来源核对包含本地`bf4e5bd`和`claude-login-agent/source-provenance.json`；页面和noVNC在控制面，真实tmux／PTY、Firefox／RFB及个人授权在本人VM。按[设计第6节](../../../docs/architecture/hapi-workspace-provisioning.md)验证同源、CSRF／Origin、mTLS和身份归属，不另实现OAuth或放宽校验。

不主动开始本人授权；授权码只瞬时转发，不写日志、缓存或重试队列。重试先读取VM的登录状态，保留已有授权和日常浏览器；不登出VM502制造测试条件。登录过期不表示VM需要重建，未开启授权时`viewer_ready=false`可为正常状态。

分别记录基础设施、应用服务、身份发布、本人Claude授权和员工验收，邮件受理也单独记录。完整验收覆盖两身份分别进入本人VM、首次授权、日常使用和停用／恢复；现有用户可用、合成测试和网络隔离通过不能替代这些证据。

## 运维与交付

VM外边界在首次启动前核验，员工sudo不能修改宿主隔离规则。运行期30秒网络巡检当前默认不启用；VM500／VM502证书／CRL到期检查继续运行，见[运维说明](../../../docs/guides/hapi-operations.md)。巡检不等于自动续期、备份或恢复演练。

交付统一网址及首次登录说明，不生成WireGuard设备包。申请、计划、状态、凭据和个人资料留在私有运行区；公开IaC仅保存通用代码与契约。沿已有精确授权推进；部署、凭据变更、邮件和删除遵守项目外部写入边界，不因skill调用扩大授权。

后续阶段落地后同步本skill的真实帮助、能力范围与验证证据。保持显式调用策略，不把候选代码或基础设施就绪升级为完整开户承诺。
