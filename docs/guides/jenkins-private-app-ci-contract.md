# 私有 n8n 作业的 peer 接入契约

此文件交给授权的应用所有者执行。本库不保存私有 Jenkinsfile、发布 helper 或 inline 修复 bundle。应用入口保持旧配置，直到所有者交回调度、凭据范围和完整清理证据；`ci/agent-jobs.yml` 中两个应用入口默认未启用。

已核实输入来自本任务先前对 CT107 的只读元数据调查：

| 对象 | 固定版本/摘要 |
| --- | --- |
| n8n-rental main | `a1fd564534a7ec991b5b7fb0c0a13e71bad3fe8a` |
| 原 Jenkinsfile SHA256 | `d892389ccd4d5f71b17dd390159032a39dc9e4f87fe3f042f619c0f3c42f0166` |
| ci/deploy-model-maintenance.sh SHA256 | `6041616a290f72e1c141646d3b8cf1badc47391510674a7779c84813279d4706` |
| inline validation script SHA256 | `faf60182d107aea9ac2185495d6b0f546c25c589b85fbf56b40c4f736b786b13` |
| inline bundle SHA256 | `dc24da1c7fdc60d5b3950c2d5f49bc60184163dc4eec1d86efa79d3cc10208ba` |
| repair commit | `662b89f160cdee4554e614264a181ab05bd7e101` |

validation 作业保留原 bundle 和测试 SHA；它的输入不是 main。测试体仍需应用所有者审计，本记录不等于代码审核结论。

所有者的补丁必须只调整 CI 身份、runner、锁和清理：

1. 将发布与 validation 的 node 都改为 `iac-apps`，每个 node 一 executor。remoting 上仅运行受保护的 `runner-client.py`；checkout、Python、rsync、SSH、clasp 和任意应用代码均进入 root runner 的 transient job unit。
2. 给两个作业分别配置固定 profile `apps-publish`、`apps-validation`，禁止任意 ref/命令/环境参数。发布保留 main SHA；validation 保留原 repair SHA 和 bundle 摘要。profile 的 executable 固定为本库 root-owned `job-entry.py`，它先执行 `isolation-probe.py` 并等待 root 准入，再分派到所有者提供的 `/opt/jenkins-agent/apps/publish.py` 或 `validation.py`。两个包装器必须 root-owned，源码摘要写入公共 trust policy 的 `application_wrappers`，lease/审批校验沿用 `transaction.py` 的签名契约。profile 默认关闭。
3. 继续使用锁定 Node `22.23.3`、clasp `2.4.2` 和 `ci/agent-toolchain.lock.json` 中的完整 npm 锁。调用预装 `clasp`，Google stage 的运行时 `npx --yes` 改为预装路径。依赖只从已验证的离线 kit 提供。
4. 保留现有发布逻辑：本地 Python、rsync、SSH；Docker 在 CT106 执行。CT110 禁止安装 Docker 或接入 Docker/socket。Gitea SCM 只读身份与 CT106 发布身份分别保存。
5. 发布 scope 与 IaC `deploy-n8n.yml` 同时声明 `service:n8n-rental`。三个 Unix 身份在任何秘密绑定前共用 peer 全局锁；锁覆盖计划、发布、验证和清理。
6. 发布 SSH 与 Google clasp 凭据分别由 root admission 的对应批准 stage 发放；validation 不接收发布秘密。应用 stage 的签名授权由所有者接入受信 controller 服务，不能将作业自报 stage 或 Boolean 当授权。本库 admission 仅接受实际 Jenkins input 中 `APPS-PUBLISH-<digest>` 或 `APPS-GOOGLE-<digest>` 的 `iac-approvers` 审批；未接入这些输入与签名校验的作业无法取到秘密。
7. 每次 run 独立 HOME/TMPDIR/workspace。使用相同 root cleanup 顺序；abort、失联、二次运行、清理残留均需验收。任何残留隔离 node，流水线不能清 quarantine。

交回证据须包含：补丁 commit、原/新入口版本、两个固定 executable 的源码摘要和审核记录；scope/网络与凭据版本；实际 node、非 root UID、cgroup、namespace；发布与 validation 的成功/abort/重连清理；Node/clasp 版本；与 IaC 的并发互斥；实际 CT106 发布及 Google stage 的分别授权、结果。保留应用源码和 bundle 在所属私有仓库。缺任一应用验收证据时 controller 不能归零。

## validation repair 对象准备

应用所有者必须在受信 bare source 中准备原 repair commit `662b89f160cdee4554e614264a181ab05bd7e101`。从所属私有配置还原原 bundle，在私有环境核对 bundle SHA256 `dc24da1c7fdc60d5b3950c2d5f49bc60184163dc4eec1d86efa79d3cc10208ba`，执行 Git bundle verify 后导入专用 reviewed ref；不得把 bundle 或应用源码复制进本库。确认 `git cat-file -e <repair-sha>^{commit}`，并计算 `git ls-tree -r --full-tree <repair-sha>` 原始输出的 SHA256。把 `application_inputs.repair_sha` 与 `application_inputs.repair_tree_sha256` 写入 root-owned apps-validation profile，连同 wrapper 摘要交回审核。admission 明确检查对象存在、固定 repair SHA 与 tree 摘要；缺失或不符直接拒绝，不回退 main。
