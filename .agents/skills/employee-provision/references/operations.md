# 运行与恢复

管理员在宿主的规范 employee-admin 目录调用 onboard.sh，直接在宿主执行。申请 JSON 与其中的 bundle_dir/run_dir 都是宿主路径，直接使用 export 输出的值。实际执行遵循仓库 AGENTS.md；不为了恢复扩大管理网络、换凭据或安装依赖。

## 计划和动作

已开始但未完成的运行具有持久串行约束，包括本地已写意图但请求尚未送达服务器的情况。HUB_TERMINAL_OTHER_RUN_RECOVERY_REQUIRED 会给出 run_dir：先恢复该目录对应的原请求，再规划/执行其他员工；不能换设备ID绕过。未执行草案可以同时存在，执行前依赖变化时重新plan。服务检查已完成且当前catalog已登记该设备configured时，配置事务不再阻塞其他开户；设备包生成失败交给export重试，已有配额/管理禁用保持原状。

- 输入、源码、配置及依赖未变：返回同一审批计划。
- 未执行计划的 catalog/BWS/generation/Terraform 状态改变：重新 plan 生成新审批，旧计划留历史，复用已预留的标识/地址；规格、模板、公钥等取当前默认值和显式spec。同员工纠正未执行草案的device ID时，新计划取代旧草案，旧审批失效。
- 部分执行：保留原 VMID、地址及 BWS 身份，沿历史链保留原创建证明，核对原 Terraform 目标和 hook；多次重新plan也不能丢失这份证明。能证明归属才继续原步骤；HUB_TERMINAL_RECOVERY_* 表示需核对原运行记录，不删除 checkpoint 或重新开户。
- 子创建流程透传的 HUB_CREATE_RECOVERY_APPROVAL_CHANGED / INTENT_INVALID 表示原审批或归档证明无法核实，保留记录并人工核对；OUTSIDE_MACHINE_CORRECTION / SCOPE_CHANGED 表示候选变更超出原目标或管理范围，审阅差异后再规划，不强行执行或删检查点。无关基础设施 state 更新由新的定向修正计划重新绑定；原 VM 归属、属性、hook 和原审批输入仍严格校验。
- 登记与启用动作在外部调用前保存公共请求及摘要；重试使用原 action ID 和 generation。HUB_REGISTRATION_INTENT_CHANGED / ACTION_ID_CONFLICT 不可通过改请求或删OCI动作记录绕过。
- OCI_HUB_ADMIN_FAILED 表示未取得受信错误码，不等于可重试网络错误。先检查受保护日志，不清检查点。已知错误码会安全输出，不打印凭据或任意stderr。HUB_ADMIN_BUSY 表示另一个管理员操作持有锁，等待其结束，不删锁。

## 交付

export 的 delivery_request 草稿绑定设备/收件人/包路径，默认 notify=false、purpose=onboarding。上传、邮件预览/发信分别 plan 和批准；host_mail_preview 是可在宿主查看的私有HTML。邮件主题与预览正文纳入审批，变化后重新 plan。

uploading/notifying 表示可能已有外部副作用，停止核对，不自动重传或重发。uploaded 表示已取得链接，可重试下载校验而不重新上传。verified 表示可以生成发信预览。completed 重跑复用原回执，不把它当作新邮件。API202仅表示接口接受。HTTP5xx、限次、404/403和传输错误返回不同安全码；404/403本身不证明时间过期。上传5xx仍可能有外部副作用，保留uploading并停止；发信传输异常保留notifying，不重发。

DELIVERY_PURPOSE_REVIEW_REQUIRED 表示历史未发回执没有用途信息：明确purpose后重新plan；已完成的旧回执保持原样。MAIL_PREVIEW_CHANGED_REPLAN_REQUIRED 表示模板/内容改变，重新生成预览和审批。

确需重新交付时先取得该员工/设备的授权，复用原包，使用新的回执子目录生成新计划，不覆盖旧回执。过期、下载次数限制与HTTP5xx分别报告。Temp.sh不可用时等待用户决定渠道；附件补发是一次授权，不扩展成普遍默认。

## 验收和完成

acceptance REQUEST.json 仅输出绑定包的必要检查、pending记录模板及已登记记录的校验结果。校验读取宿主 settings.json 的 oci_hub.e2e_verification；证据/记录路径须是宿主上归管理员所有、mode0600 的私有路径。禁止复制整份设置或输出凭据来“修复”。独立验证人员按批准的测试方案提供日志/JSON证据，补齐时间、哈希和通过项，管理员审阅后登记保护记录的路径/哈希及批准引用。没有证据的项保持pending，不伪造passed。

验收记录最长有效1小时，并绑定当时全局mapping_generation及网络策略；其他登记使其失效时重新核对subject和独立证据，不能只改旧记录时间。验收与特定设备的用户豁免都是独立授权；已批准豁免保留，不能迁给另一设备。管理员verify/online只报告服务侧观察，员工bootstrap和VM内个人Claude认证另行确认。Git定义同步是单独收尾阶段。

## 历史共享同步

不带profile的login/auth-status用于微软Mail.Send授权；registry是旧台账历史；recover仅回收旧共享同步日志。它们不是OCI业务恢复入口，不从旧同步副本覆盖Hub账本，不恢复旧VM500接入或已删除角色。
