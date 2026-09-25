# n8n 升级 MOP（Homelab / Agent 版）

> 给 agent 执行、用户审核的六步操作单。文档审核不等于授权升级；取得一次明确的执行授权后，按约定范围连续完成，不逐步重复询问。
>
> 本操作单只升级 n8n 运行时及其必要的 Node.js 依赖；不顺带迁移到 Docker、不变更 LXC 规格、不管理既有 systemd drop-in，也不发布或激活任何 workflow。

## 1. 确认版本和现场

当前已验证基线：`pve0` 上 LXC VMID **106**，n8n 通过全局 npm 包和 systemd 运行；2026-09-15 升级后为 Node.js **24.21.0**、npm **11.19.0**、n8n **2.39.5**。历史上数据位于 `/root/.n8n`，但每次执行必须以现场为准。

执行前，agent 必须确认：

- 当前 n8n、Node.js、npm 的实际版本及全局 n8n 可执行文件路径；`latest`、`next`、beta、RC 都不能代表本次批准的目标版本。
- 当前版本到目标版本之间的官方升级说明、数据库迁移、Node.js 支持范围以及社区节点兼容性；若要求分段升级或引入新的系统依赖，先停止并说明。
- 实际 systemd unit、所有 drop-in、`EnvironmentFile` 的**文件路径和变量名**；不得打印文件内容或凭据。
- 实际 `N8N_USER_FOLDER`、数据库后端和数据路径。未配置外部数据库时通常为 SQLite，但不能未经核对就假设。
- 剩余空间、当前服务状态以及是否有 in-flight execution。发现 execution 时按本次授权决定立即中断或等待；不能在不说明影响的情况下停止服务。
- 当前 workflow 的 published/active 状态和 ID 清单，只用于审计，绝不作为升级结束时自动恢复的输入。

下面命令只能记录版本和状态摘要：

```bash
node --version
```

```bash
npm --version
```

```bash
n8n --version
```

```bash
systemctl show n8n -p ActiveState -p MainPID -p EnvironmentFiles -p FragmentPath -p DropInPaths
```

## 2. 一次确认执行范围

向用户说明：**当前版本 → 目标精确版本、Node.js 变更（如需要）、预计停机时间、本地恢复副本位置、workflow 将全部保持未发布，以及失败后的恢复边界**。

本机本地恢复副本不能抵御 LXC 丢失；当前 PBS 不可用时，不能把它表述为整机备份或灾难恢复点。数据库发生迁移后，恢复旧二进制需要与匹配的旧数据库状态一起恢复。恢复数据、启动恢复副本、提交和推送均为独立授权边界。

不要运行完整 `deploy-n8n.yml` 作为一次性升级入口：它还会执行 `common` 和 `tailscale`，超出本次应用升级范围。

## 3. 冻结 workflow 并建立恢复副本

1. 停止并 mask `n8n.service`，确认端口 5678 不再监听。若授权要求立即处理 in-flight execution，停止服务会中断它们。
2. 服务保持停止时，按当前 n8n major 使用官方 CLI 取消发布全部 workflow。n8n 2.x 使用：

```bash
n8n unpublish:workflow --all
```

3. 通过实际数据库后端的只读查询或其他独立读方法，断言 active/published workflow 数量均为 **0**。失败、命令不支持或无法独立确认时，保持服务 `masked + stopped`，不继续也不启动。
4. 建立时间戳唯一、权限受限的本地恢复目录，保存完整实际 n8n 状态目录、systemd unit 和相关 drop-in。必须覆盖配置、数据库、加密密钥与安装的社区节点；不写入 Git、不打印凭据、不覆盖旧副本。
5. 比较归档内容并记录校验和、目录路径、旧版本和完成时间。归档或校验失败时停止升级。

## 4. 安装固定版本

保持服务停止，按目标 release 的 Node.js 要求更新 NodeSource 仓库和 Node.js。仅使用精确的 Node.js 和 n8n 版本，不使用浮动版本或移动标签。

```bash
npm install --global n8n@<approved-version>
```

安装后先检查实际可执行文件和版本，不启动服务：

```bash
n8n --version
```

**SQLite 异常排障分支（非正常升级步骤）：** 仅当升级后 n8n 明确报 SQLite 驱动无法加载时，先确定全局 n8n 实际解析的 `sqlite3` 路径；再定向重建该模块：

```bash
npm rebuild --global sqlite3 --allow-scripts=sqlite3 --foreground-scripts
```

随后仅加载实际 n8n 解析的 SQLite 模块来验证。不要为正常升级执行此步骤，不要批量或永久放行其他 npm install scripts，也不要在 `/root` 目录随意安装一份不被全局 n8n 使用的 sqlite3。

安装失败、版本不匹配、或服务尚未启动就发现数据库状态异常时，保持服务停止。只有能确认目标版本从未接触持久状态时，才可在原授权范围内重装已记录的旧精确版本；否则进入第 6 节恢复边界。

## 5. 受控启动与非触发性验证

只有同时满足“目标版本精确匹配、本地恢复副本存在、workflow active/published 均为 0”时，才解除 mask 并启动服务。

最低验证项目：

- systemd 为 `active/running`，端口 5678 可连接，`/healthz/readiness` 返回 HTTP 200。
- Node.js 与 n8n CLI 版本精确等于批准目标。
- 启动日志没有数据库迁移失败、凭据解密错误或反复重启；记录 Python task runner、社区节点等未在本次范围内的告警，但不顺带安装/修复。
- 启动后再次独立检查 workflow，active/published 数量仍严格为 **0**，execution 数量没有意外增加。
- 可以登录查看 workflow、execution 历史和凭据元数据，但**不运行 workflow、不发送 webhook、不恢复计划任务或外部触发**。

观察约 10 分钟。任何 workflow 意外变为 published/active、服务反复重启、readiness 失败或数据库异常时，立即 stop + mask，保留日志，不反复重试。

## 6. 失败处理和结束汇报

- **新版本尚未接触持久状态：** 只有确认旧精确 npm 包与旧数据库仍匹配时，才可以恢复旧包；启动前仍要确认 workflow 未发布。
- **数据库已迁移或状态不明：** 禁止让旧 n8n 直接读取已迁移数据库。保留日志和本地副本；恢复本地数据或整台 LXC 都需要单独明确授权，恢复副本不能与原实例使用相同 IP 同时上线。
- **结束摘要：** 旧版本 → 新版本、本地恢复副本路径、workflow=0 的三次断言、服务/readiness/观察结果、未验证项和已知告警。不要把“未运行 workflow”写成业务流程已验证。

参考：[Immich Upgrade MOP](immich-upgrade-mop.md) · [n8n CLI 文档](https://docs.n8n.io/deploy/host-n8n/configure-n8n/use-the-command-line) · [仓库规则](../../AGENTS.md)
