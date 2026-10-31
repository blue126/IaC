# HAPI 独立管理员入口与运行绑定

HAPI 私有源码正式存放在主检出的`~/Projects/IaC/remotecc/hapi-admin/`，运行数据在同级`hapi-data/`。源码独立本地Git管理，运行区不入Git；任务工作树副本用于开发。原工作树材料已逐文件SHA256校验复制并保留，历史回执不改写为新计划。

正式入口：

```bash
python3 ~/Projects/IaC/remotecc/hapi-admin/hapi-entry.py doctor
```

入口读取`hapi-data/admin-binding.json`，校验HAPI独立profile、固定源码／数据目录、IaC工作树和Sandbox。宿主只分发命令，Terraform／Ansible和台账操作在绑定Sandbox执行，不做双向复制／回收，因此同一SQLite台账和锁始终位于同一实际目录。源码挂载只读，运行数据挂载可写；不挂载WireGuard业务登记。

当前绑定Sandbox为`iac-codex-hapi-provision-direct-v130`，由本任务IaC工作树及`.sandbox-kit`建立。`doctor`只检查执行环境和源码摘要，不创建台账、申请或资源。已验证宿主入口进入该Sandbox、正式源码不能以写方式打开、运行目录可读写且没有创建员工登记。

## 输入与审批

已有命令为`request`、`plan-infra`、`apply-infra`和`status`。真实执行前读取私有README及`--help`，准备独立的profile、分配池、最小化PVE快照和管理员管理通道。真实输入必须位于获批挂载中；不能把挂载就绪当作已经批准具体VM、凭据写入或公开身份发布。

计划固定单VM、网络清单、独立state、实际执行源码／Ansible配置、SSH信任材料与saved plan摘要。PVE密码使用Terraform >=1.10的ephemeral变量，经私有环境注入。当前计划默认不启用运行期网络巡检，边界校验及启动前门禁继续保留；生产监控方式另行确定，相应角色代码仍参与审批摘要。旧计划需要重新生成与审批。

`apply-infra`仍只完成基础设施，不设置`services_ready`、`route_enabled`或`public_entry_ready`。完整服务安装、BWS/PKI与租户登记、Cloudflare真实身份绑定、路由启用、个人首次授权和交付仍须独立闭环与验收。两台网络测试VM不自动认领为员工资产。

## 存储与恢复

- 原工作树的HAPI材料保留为迁移前材料，不继续建立第二份活动登记。
- 主检出运行区的`storage-migration-20261031.json`记录原文件摘要及复制校验；源码／运行数据目录均为0700。
- BWS仍是服务秘密权威来源。本机profile只调整token文件路径，保持token及秘密值不变；原profile另行保留。管理员token不交给VM500或员工VM。
- 主检出的公开main没有接收本任务源码；正式入口显式绑定任务工作树。将来更换IaC目录、Sandbox或state路径需要单独迁移计划，不能直接删除当前工作树。

5项绑定回归、17项基础设施执行器回归及正式`doctor`／挂载验证通过。上述不替代真实新增员工的完整开户验收。

QA VM9101／9102已按原Terraform state完成销毁，相关记录见[回收记录](../planning/2026-10-31-hapi-qa-retirement.md)。当前服务运行索引为`hapi-data/credentials/service-runtime.json`，指向仅保留VM502 worker的v3运行Vault；旧QA提案、Vault及计划只作历史证据，不重新执行。
