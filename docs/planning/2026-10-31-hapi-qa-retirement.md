# HAPI 双 QA VM 回收与收尾

状态：2026-10-31按用户明确批准完成VM9101／9102及关联测试配置回收。原测试代码和验收证据保留，VM500／VM502的现网服务、个人登录与证书巡检保持正常。

## Terraform 归属与销毁

两台VM由原独立本地Terraform state管理，位于任务工作树的`remotecc/hapi-data/pve2-dual-20261030-5hxafyl5/terraform.tfstate`。state lineage为`f45bae48-38cd-478e-bc4b-331f2abe37b8`，销毁前原始serial为7；原始state和主检出副本摘要一致，受管资源仅有两个`module.workspace` VM。

| VMID | 名称 | 配置 | 结果 |
|---|---|---|---|
| 9101 | hapi-test-alice | 2 vCPU、2GiB内存、20GiB系统盘与Cloud-Init卷 | 已销毁，卷路径确认不存在 |
| 9102 | hapi-test-bob | 2 vCPU、2GiB内存、20GiB系统盘与Cloud-Init卷 | 已销毁，卷路径确认不存在 |

先通过Terraform执行只有两处`protection: true -> false`的原地更新，计划SHA256为`5a0cb9597dcf3a04e8fd059b4db41ed4995edac6b06afcba7b474abe007c3eb8`。随后审阅并应用只包含这两个VM的destroy plan，SHA256为`aabb4cc5c967264b062f8a6747ee451ac3300d8d00d385a74bb4bae17f9df90b`。

Terraform返回`0 added, 0 changed, 2 destroyed`；同一lineage的最终serial为15，受管资源为0。未使用`state rm`或绕过state的VM删除。Ansible清理脚本在收到Terraform销毁回执、确认VM与磁盘已不存在后，才移除关联配置。

主检出对应state已同步，旧测试输入`workspaces`清空，最终Terraform plan没有受管资源操作。原配置／state／计划保留审计，旧测试目录有`RETIRED.json`，不得重放历史QA部署。

## 关联配置清理

- BWS固定凭据登记中的`test_alice`／`test_bob`禁用并提升凭据代次，回读一致；VM502凭据值及权限不变。历史测试叶证书秘密保留审计，现网接入映射已删除。
- VM500移除两个QA agent映射及对应的两条9443源地址例外。只对传输Nginx执行平滑reload，共享Hub未重启。
- pve2只删除`hapi_9101`／`hapi_9102`两个bridge表；活动测试清单及回执移入受限归档。原WireGuard／OCI策略摘要保持一致。
- pve2的`hapi-health`定时器、service及专用文件移除，旧HAPI网络加载unit停用；通用脚本、真实`vmbr0`及基础模板9000保留。
- 内容摘要匹配且没有其他VM引用的QA Cloud-Init snippet归档后移除；两个QA地址的SSH信任记录、待发布测试身份提案撤出活动配置。
- 新的v3运行Vault仅保留VM502 worker叶身份，当前服务索引在主检出`hapi-data/credentials/service-runtime.json`。旧Vault及提案保留为历史材料。
- 后续开户默认不启用30秒运行期网络巡检；网络边界与启动前校验继续保留。正式员工运维监控另行确定。

## 验收

确认两台VM、各自磁盘、两张ACL表及pve2巡检均已消失，基础模板9000保留。VM500生产认证成功，两个QA凭据被拒；VM502新建mTLS连接成功。原会话／机器／消息仍在，数据库中没有QA业务数据。

前后11项既有服务的状态、PID及重启计数一致；VM500／VM502各4项证书／CRL检查及定时器正常。关联清理重复执行，VM500和pve2均`changed=0`。私有执行器17项和绑定5项回归通过，包括默认不启用运行期巡检。

回执、日志和完整元数据保存在主检出`remotecc/hapi-data/operations/20261031-qa-retirement/`；宿主侧归档分别在VM500的`/var/lib/hapi-qa-retirement-20261031/`和pve2的`/var/lib/hapi-network/retired-qa-20261031/`。没有Cloudflare变更或新员工发布。

QA回收执行阶段没有同时创建Git提交或推送；公开实现及本记录随后已经[PR #201](https://github.com/blue126/IaC/pull/201)完整CI与审核后合入`main`。新员工完整交付及个人首次授权仍需在当前员工流程中独立验收，不能把QA回收当作已完成完整开户。
