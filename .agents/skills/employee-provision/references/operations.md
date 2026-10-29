# 运行与恢复

规范入口是主 checkout 的 `remotecc/employee-admin/onboard.sh`；执行前读取该私有仓库 README。相邻 `remotecc/employee-data/` 保存设置、令牌、申请、回执、包和模板 state，不进入源码 Git。旧 `~/Projects/employee-workspace-admin` 仅是兼容链接。

- 常用命令：`preflight REQUEST.yml`、`plan REQUEST.yml`、`apply REQUEST.yml SHA256`、`verify REQUEST.yml`、`export REQUEST.yml`。
- 邮件一次性授权：`auth-status`、`login`。settings.json 的 microsoft_mail_client_id 复用已注册微软应用；仅请求 Mail.Send 与 offline_access，管理员本人登录；独立加密缓存为 state/microsoft-mail-token.vault。旧 OneDrive 缓存保留，不再调用。
- Temp.sh 交付回执为 runs/<request>/temp-delivery.json；上传前写 uploading，收到链接后写 uploaded，POST 下载核对后写 verified，发信前写 notifying，202 后写 completed。uploading/notifying 结果不明时停止核对，不自动上传或发信。三天失效时间按服务政策估计，不能当成服务器保证。
- 入口复用 settings.json 中已批准的 Sandbox。RemoteCC 代码单向同步到 Sandbox，运行数据单独双向同步；不把 Sandbox 中的旧源码拉回覆盖私有 main。现有挂载、网络规则和 Kit 不随普通操作修改，宿主锁与内层 flock 保持串行。
- 正常或失败执行后都会回收持久状态，并核对运行副本指纹。代码目录旁的私有同步日志 pending=true 表示不可再次推送旧状态；先执行 `recover` 拉回运行副本，核对检查点后重新 plan。不要直接清除 pending 或覆盖 state。
- requests/、runs/、state/、bundles/、deployment/ 和 template-build/ 应纳入私有备份；计划可能含凭据，不能贴出完整内容。模板的 terraform.tfstate/backup 不是缓存，不删除。
- 旧 tmp 目录保留作迁移前快照，不再作为新的入口。不要交替使用新旧入口；迁移前生成的计划作废，必须重新 plan。
- IaC 工作树仍由 settings.json.iac_root 绑定；在它的变更正式整理前，不删除或归档该工作树，也不自动切到缺少这些变更的公开 main。
- 浏览器、个人 Claude OAuth、员工本地 WireGuard CLI 的验收由公开客户端负责，不把它们塞进管理员开户 skill。
