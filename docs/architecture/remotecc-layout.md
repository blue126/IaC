# RemoteCC 管理员代码与私有运行数据

主检出`~/Projects/IaC/remotecc/`保留管理员源码及本机私有材料，公开IaC的Git忽略整个目录。员工工作区写操作和权威运行数据已迁至ws-executor：源码位于`/srv/remotecc/employee-admin`，数据位于`/srv/remotecc/employee-data`；Mac上的员工运行副本只读且可能过期。HAPI的`hapi-data`仍保存独立服务运维材料，不因员工执行器迁移而自动搬运或合并。

员工当前操作以[执行器上的wsctl约定](../deployment/oci-hub-native-provisioning.md)为准。独立HAPI开户方案已撤回，`hapi-admin`早期原型及`hapi-data`运维材料继续保留，历史绑定见[HAPI管理员运行绑定](../guides/hapi-admin-runtime.md)。HAPI与WireGuard面向同一员工VM；旧独立执行器不能重新用于开户。现有服务部署不等于新员工完整交付已验收。

```text
IaC/remotecc/
├── employee-admin/   # 独立私有 Git：管理员源码开发副本
├── employee-data/    # Mac 员工运行副本：只读、可能过期
├── hapi-admin/       # 撤回的独立 HAPI 开户原型：历史源码
└── hapi-data/        # 不入 Git：HAPI 服务运维材料与回执
```

## 版本与 main 的关系

- 私有代码使用独立的本地 Git；当前没有 GitHub 远端。它的提交和分支与公开 IaC 无关。
- `employee-data/` 不进入任何 Git，继续使用私有备份。设备密钥的权威来源仍是 BWS；本地机器令牌和加密授权缓存保留在数据目录。
- 公开 IaC 只提交忽略规则、接口约定和本说明。这些文件通过正常 PR 合入 `main`。
- 私有文件无需“合并回 IaC main”：实体已经位于主检出下，切换或清理 linked worktree 不会移动它。不得为同步私有内容而临时提交到公开分支。
- 合并忽略规则前，本机共享的 `.git/info/exclude` 已提供同样保护。`.worktreeinclude` 显式列出 `remotecc/employee-admin/` 中的源文件，排除运行数据和私有仓库的 Git 元数据。

## Worktree 中的管理员代码

从主检出创建新 worktree 时，可以按 `.worktreeinclude` 携带管理员源文件。Codex 跳过源符号链接，因此配置、密钥和运行数据的兼容链接不会作为文件副本复制。历史HAPI工作树曾使用迁移时建立的共享`remotecc`链接；该记录不表示新的HAPI独立绑定已复用WireGuard运行区。

源文件可用不代表该worktree已配置成独立的provisioning环境。执行器源码、权威运行数据、IaC代码根、工具链和授权须按当前入口绑定；旧Sandbox同步锁与journal随已删除的existing流程一并退役。员工写操作在ws-executor执行，IaC工作目录约定为`/srv/iac`；具体绑定由执行器上的受保护配置决定，不因Mac所在目录改变而切换。HAPI历史独立绑定不自动改指向当前员工入口。复制源码不代表已取得运行绑定或操作授权。

## 入口与兼容路径

正式员工入口是执行器上的`/srv/remotecc/employee-admin/wsctl`，经Semaphore模板或已批准的执行器管理通道运行；部署布局见[ws-executor说明](../deployment/2026-10-31-ws-executor.md)。旧的`onboard.sh`、`onboard-host.py`及`existing`入口已于2026-11-04删除。

代码目录中保留受控的数据链接，因此已有的 `settings.json`、`state/`、`runs/`、`requests/` 等路径仍可使用。`runtime-layout.py` 按 `remotecc-layout.json` 补齐缺失链接；遇到已有普通文件或错误链接时停止，不覆盖数据。

Mac已配置`write_executor`，写命令返回`WSCTL_WRITES_ON_EXECUTOR`，不得在宿主直接运行`oci-hub-admin.py`来绕过。员工与IaC代码可经各自的`ws-executor` Git远端送入执行器；推送是部署写入，需单独授权。员工、设备、密钥和交付身份不因代码目录变化而重建；下一次实际写操作仍须核对源码、计划及审批。

历史诊断材料位于数据目录的 `deployment/`；模板 state 留在数据目录的 `template-build/`，模板 Terraform 源码单独保存在代码目录的 `template-build-source/`。

## 验证与保留

迁移保留完整的迁移前目录备份、文件哈希及运行记录。凭据、设备包、申请和模板 state 必须校验字节一致；不要将它们当成缓存清理。

检查时使用 `git check-ignore remotecc/` 确认外层忽略规则，使用私有目录内的 Git 查看代码状态。初始化本地仓库不等于已创建提交；提交、推送及任何真实开户仍分别需要授权。
