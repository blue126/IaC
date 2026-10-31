# RemoteCC 管理员代码与私有运行数据

主检出 `~/Projects/IaC/remotecc/` 保存管理员代码基线和本机唯一的活动运行数据。公开 IaC 的 Git 忽略整个目录；linked worktree 可引用代码基线，也可携带源文件用于开发，但申请、凭据和检查点保持共享。

```text
IaC/remotecc/
├── employee-admin/   # 独立本地 Git：管理员入口、测试和说明
└── employee-data/    # 不入 Git：配置、凭据、申请、包和运行状态
```

## 版本与 main 的关系

- 私有代码使用独立的本地 Git；当前没有 GitHub 远端。它的提交和分支与公开 IaC 无关。
- `employee-data/` 不进入任何 Git，继续使用私有备份。设备密钥的权威来源仍是 BWS；本地机器令牌和加密授权缓存保留在数据目录。
- 公开 IaC 只提交忽略规则、接口约定和本说明。这些文件通过正常 PR 合入 `main`。
- 私有文件无需“合并回 IaC main”：实体已经位于主检出下，切换或清理 linked worktree 不会移动它。不得为同步私有内容而临时提交到公开分支。
- 合并忽略规则前，本机共享的 `.git/info/exclude` 已提供同样保护。`.worktreeinclude` 显式列出 `remotecc/employee-admin/` 中的源文件，排除运行数据和私有仓库的 Git 元数据。

## Worktree 中的管理员代码

从主检出创建新 worktree 时，可以按 `.worktreeinclude` 携带管理员源文件。Codex 跳过源符号链接，因此配置、密钥和运行数据的兼容链接不会作为文件副本复制。当前 HAPI worktree 仍使用迁移时建立的共享 `remotecc` 链接；修改复制清单不会追溯替换它。

源文件可用不代表该 worktree 已配置成独立的 provisioning 环境。共享数据、外层锁、同步 journal、IaC 代码根和 Sandbox 必须显式绑定后才能执行；不要直接运行缺少绑定的源文件副本。生产入口按 `settings.json.iac_root` 使用 IaC 主检出，不会因所在目录改变而切换。完整的逐 worktree 执行绑定尚未实现，本次复制清单不改变这一点。

## 入口与兼容路径

正式入口为 `~/Projects/IaC/remotecc/employee-admin/onboard.sh`。旧的 `~/Projects/employee-workspace-admin` 保留兼容链接，指向新代码目录。

代码目录中保留受控的数据链接，因此已有的 `settings.json`、`state/`、`runs/`、`requests/` 等路径仍可使用。`runtime-layout.py` 按 `remotecc-layout.json` 补齐缺失链接；遇到已有普通文件或错误链接时停止，不覆盖数据。

`settings.json.iac_root` 绑定 IaC 主检出 `~/Projects/IaC`；`--profile oci-hub` 在宿主直接执行，使用主检出 `.venv` 的 uv 工具链。员工、设备、密钥或交付记录不随之改变。代码变化后，下一次实际 apply 仍须重新生成并批准计划。

## Sandbox 同步与恢复（仅已退役的 existing 入口）

`onboard.sh` 的 `login`、`auth-status`、`registry`、`recover` 仍经 `onboard-host.py`：

1. 取得原有管理员锁，并核对同步 journal，未回收状态继续阻止新操作。
2. 代码只从宿主发送到 Sandbox，发送时排除代码仓库的 `.git/`。
3. 运行数据独立同步；命令成功、失败或中断后只回收数据，不从 Sandbox 回写管理员源码。
4. 回收排除宿主锁和模板源码链接，并验证归档路径与数据指纹；异常时保留 pending 状态供 `onboard.sh recover` 处理。

外层锁和同步 journal 是 RemoteCC 根目录下的本机控制信息，不进入 Git。历史诊断材料位于数据目录的 `deployment/`；模板 state 留在数据目录的 `template-build/`，模板 Terraform 源码单独保存在代码目录的 `template-build-source/`。

## 验证与保留

迁移保留完整的迁移前目录备份、文件哈希及运行记录。凭据、设备包、申请和模板 state 必须校验字节一致；不要将它们当成缓存清理。

检查时使用 `git check-ignore remotecc/` 确认外层忽略规则，使用私有目录内的 Git 查看代码状态。初始化本地仓库不等于已创建提交；提交、推送及任何真实开户仍分别需要授权。
