# Immich 升级 MOP（Homelab / Agent 版）

> 给 agent 执行、用户审核的六步操作单。文档审核不等于授权升级；取得一次明确的执行授权后，按约定范围连续完成，不逐步重复询问。
>
> 仅升级 Immich 应用栈，不顺带升级系统、Docker、网络或 VM 规格。不安装新工具，不删除数据或卷；需要恢复数据或扩大范围时再征求授权。

## 1. 确认版本和现场

仓库基线：`pve0` 上 VMID **101**，地址 `192.168.1.101`，Compose 目录 `/opt/immich`，媒体目录 `/opt/immich/library`，数据库目录 `/opt/immich/postgres`。**执行前核对现场，不把这些路径或服务名当成已验证事实。**

agent 先确认：

- 当前实际运行版本和拟升级的具体 release；`release` 标签不能代表当前版本。
- 当前版本到目标版本之间的官方升级说明。涉及 PostgreSQL 大版本、向量扩展或必须分段升级时，先说明特殊步骤，不按普通升级直接跳过。
- 实际 Compose 服务、挂载和剩余空间；数据库、媒体、外部图库是否都在拟用备份范围内。
- VM、Proxmox/PBS 的访问方式已可用，没有其他人或 agent 同时变更此栈。

在目标 VM 执行，只记录必要摘要，不打印完整 `.env`、容器环境变量或凭据：

```bash
docker compose --project-directory /opt/immich ps -a
```

```bash
docker compose --project-directory /opt/immich images
```

```bash
df -h /opt/immich
```

## 2. 一次确认执行范围

向用户简短说明：**当前版本 → 目标版本、预计停机时间（包含备份耗时）、备份位置、失败时恢复整台 VM 的方案**。确认允许执行配置备份、停服、VM 备份、版本配置更新、拉取启动以及测试上传。

未做过恢复演练就明确告知，不声称“保证可恢复”；用户接受这一剩余风险即可，不要求每次升级都演练。已有授权明确覆盖这些动作时，不再重复申请。

本次默认采用 **直接 Docker Compose 升级 + 整机备份恢复**，不运行完整的 `deploy-immich.yml`：它还会执行 `common`、`tailscale` 和 `docker`，超出本次范围。提交、推送和数据恢复仍分别遵守仓库授权规则。

## 3. 建立一个可靠的恢复点

1. 暂停客户端自动上传，等待当前上传结束。把实际 Compose 文件、`.env` 和使用中的覆盖配置保存到本次独有的私有备份目录（目录 `0700`、文件 `0600`）；不要覆盖旧备份，也不要提交这些文件。
2. 在 VM 内停止整个 Immich Compose 栈（包括数据库），确认服务都已停止且没有新的写入：

```bash
docker compose --project-directory /opt/immich stop
```

3. 通过现有 Proxmox/PBS 入口对 **VM 101** 做一次备份，整个备份期间保持栈停止。确认任务成功、恢复点可见，并覆盖实际数据库、媒体和配置所在的磁盘；外部挂载或排除备份的磁盘不能默认算在内。
4. 记录恢复点标识和完成时间。备份失败或数据覆盖不全就停止升级；若要改用其他备份方式，先与用户确认。未变更配置、未拉取镜像时，可在原授权范围内启动原栈恢复服务，并报告备份失败。

**完整 VM 备份足够时，不强制额外做数据库 dump。** 如果确需额外 dump，按对应版本的官方方式，在数据库运行、应用写入停止时生成；必须检查 dump 命令退出码，失败的 `.partial` 文件不能算有效备份，非空和哈希也不能证明可恢复。

## 4. 落地固定版本并升级

备份成功后，保持栈停止，按以下顺序操作：

1. 从目标 release 获取匹配的官方 Compose 文件，检查与现有配置的差异，保留实际存储路径和本地必要配置。若出现第 1 步未预计的数据库迁移、挂载变化或新增依赖，先停止并说明。
2. 将目标 Compose 落地到 `/opt/immich/docker-compose.yml`，将实际 `.env` 的 `IMMICH_VERSION` 改为批准的具体版本，不改数据库凭据；同时核对覆盖文件是否仍兼容。
3. 在任务工作树的 [Immich host vars](../../ansible/inventory/host_vars/immich.yml) 对齐 `immich_version` 和目标 release 的 `immich_compose_source`，避免后续 Ansible 再覆盖为 `release` / `latest`。不自动提交或推送。
4. 核对有效镜像清单确实是本次批准的版本组合，再拉取和启动：

```bash
docker compose --project-directory /opt/immich config --images
```

```bash
docker compose --project-directory /opt/immich pull && docker compose --project-directory /opt/immich up -d
```

**拉取失败绝不能继续启动。** 保存失败输出，不盲目重试；整个升级期间不执行 `down -v`、卷删除或镜像清理。

## 5. 验证基本可用，再恢复日常使用

在目标 VM 查看容器和本次启动日志；日志只回报脱敏摘要：

```bash
docker compose --project-directory /opt/immich ps -a
```

```bash
docker compose --project-directory /opt/immich logs --since 10m --tail 100
```

检查四件事即可：

- 预期服务已运行，有健康检查的服务健康，没有反复重启或数据库迁移错误；实际应用版本与目标一致。
- 常用入口（仓库记录为 `https://immich.willfan.me`，以实际使用为准）能登录。
- 几张既有照片能打开；用一张非敏感测试照片验证上传、缩略图和读取。测试完成后保留或按明确授权清理，仅操作本次测试文件。
- 就绪后观察约 **10 分钟**，无新异常，再恢复客户端自动上传。迁移仍在推进就看日志并汇报延长停机，不因达到十分钟便强杀迁移。

其他入口、独立 Redis 检查、机器学习任务和 Homepage 不作为每次升级的必检项，相关组件变更或异常时再查。缺少登录/测试条件时，请用户完成对应检查并记录结果，不把“未验证”写成成功。

Ansible 验证是可选补充，使用时只运行 `--tags verify --limit immich`，且先确认验证 play 适配当前版本。Ansible 只在已有 Docker Sandbox 中执行，确认其仓库版本和主机匹配；`no hosts matched` 不是通过，按仓库规则刷新 Terraform state 后重验。验证 play 自身出错要修 playbook，不用临时命令绕过后宣称通过。

## 6. 失败处理和结束汇报

- **先停下并保存证据**：备份失败、拉取失败、迁移错误、持续重启或照片读写失败时，停止后续步骤，保留旧配置和恢复点，不删数据、不反复重启碰运气。
- **尚未启动新版本**：只有确认原容器及其旧镜像仍完整时，才可在原授权范围内恢复配套的旧 Compose / `.env` 并启动原容器。拉取可能已改变移动标签，不能仅恢复 `release` 配置后再次 `up` 并称为回滚；无法确认就报告，不猜测。
- **已经迁移或状态不明**：不要让旧镜像读取已迁移的数据库。向用户说明恢复点和可能丢失的新增数据，取得恢复授权后，按现有 VM 恢复流程还原整机；避免恢复副本和原机同时以相同 IP 上线。数据库与媒体必须来自匹配的恢复状态。
- **结束只汇报一条摘要**：旧版本 → 新版本、恢复点、照片读取/上传结果、是否恢复日常使用，以及未验证项或后续事项。恢复后同样重复第 5 步的基本验证。不自动清理备份或提交代码。

参考：[仓库规则](../../AGENTS.md) · [现有部署指南（旧命令需核对）](immich-deployment.md) · [官方升级说明](https://docs.immich.app/install/upgrading) · [官方备份与恢复](https://docs.immich.app/administration/backup-and-restore)
