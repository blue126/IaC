# HAPI 内部证书生命周期发布记录

用户批准清单SHA256：`4a705b174ba87a49900b31c591cee3a7724c9fe77f616c294d622e81df26e337`。目标仅为VM500（192.168.1.140）和VM502（10.236.2.2）。本记录描述现网发布和验收，Git提交与合并状态以仓库记录为准。

## 已完成

- 两端受限Unix agent已运行；VM502只在既有9443 mTLS入口追加精确来源限制的PKI操作路径，没有新开放端口。
- VM500专用hapi-pki身份通过systemd credentials取得两套签发密钥；VM502没有签发密钥目录。未复制BWS管理员token或安装SDK。
- 四张叶证书有效至2027-10-31 12:43:15 UTC，CA有效至2031-10-30 12:43:15 UTC，CRL有效至2027-04-29 12:43:15 UTC。各服务及CA公钥摘要与变更前一致，叶私钥不变。
- 初次发布generation为`043663580e2173258c45ea56fb00a40e`。两个方向均完成新证书指纹及HTTP200验证：VM500到登录API、VM502到共享Hub health。
- VM500 timer处于active/waiting，每小时执行，启动后也有首次检查；签发服务是oneshot，成功后inactive且ExecMainStatus=0正常。
- 再次执行健康检查返回ok=true、changed=false。两端实际程序摘要与本工作树一致；公网统一入口返回正常Access重定向302。
- Hub、Runner、身份服务及原有代理保持active，未重启Hub或Runner，不改数据库、Cloudflare或provisioning。

## 现场修正与恢复

1. systemd实际把服务凭据暴露为0440，最初严格0600检查在签发之前拒绝。只为受控credentials目录及预期属组允许0440，仍拒绝其他人可读或组可写；已增加权限回归。
2. 加固环境下runuser/PAM重载失败，已改为先确认固定PID存在、语法校验后直接对现有Nginx master reload；agent不再需要SETUID／SETGID能力。第一次失败留下的generation通过agent对原材料的严格核对后完成回退，再复用同generation续跑，没有覆盖未知材料。
3. 自动检查使用已续期的持久authority状态校验有效期，历史bootstrap CA／CRL仅用于引导和公钥绑定；已覆盖引导CRL过期而运行期材料有效的情况。

上述修正保持同一目标、凭据、身份及发布动作范围；最终源文件摘要随私有验收材料保存。

## 验证与保留边界

20项相关回归通过，包括真实CSR、mTLS、实际Nginx私有路径、权限、幂等、失败回退／续跑及旧Vault覆盖保护；相关lint和语法通过。Sandbox没有systemd-analyze的测试跳过，目标主机实际单元校验已通过。

按用户授权移除过时的side chat挂接执行器、专属角色、测试和文档，并撤销其对共享角色的未发布增量；共享组件及当前生产实现保留，独立HAPI开户继续撤回。用户负责VM500的VM级备份，本次没有建立数据库备份任务。新增撤销或CA密钥换代仍需独立审阅，定时器只续期既有身份与保留既有撤销集合；失败体现在systemd及health.json，目前没有外部消息告警。
