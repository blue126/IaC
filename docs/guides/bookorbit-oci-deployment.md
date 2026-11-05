# OCI BookOrbit 部署

BookOrbit v3.3.0 部署在现有 `ubuntu@159.13.46.201`，公网入口为
`https://bookorbit.willfan.me`。应用只绑定 `127.0.0.1:3000`，PostgreSQL 不发布端口。
两个容器及所有持久化数据由 `/opt/bookorbit/docker-compose.yml` 管理。

该服务已于 2026-10-08 部署上线，本文同时是重跑、备份和恢复的操作依据。部署仅通过 SSH 使用已有 Docker、Compose 和 Caddy，不调用 OCI API。
首次管理员由用户在设置页创建；服务器验收不代建个人账号，也不包含 PDF 客户端同步兼容性。

## 固定版本与上游接口

| 容器 | 固定镜像 |
| --- | --- |
| `bookorbit-app` | `ghcr.io/bookorbit/bookorbit:3.3.0@sha256:4c2a1b957a3c8aeb9f59bb27a7d8efb18fa42c758afed3dcfc62620c5bcd1831` |
| `bookorbit-db` | `pgvector/pgvector:pg18@sha256:2358fcba361ed2233a5ed81b5fe4ca779ccb304120ce531a3bf51c0ed7e2bc11` |

镜像清单的 ARM64 可用性已经过规格阶段确认。应用保留上游的只读根文件系统、`/tmp` tmpfs、
`no-new-privileges`、capability 限制及由入口脚本降权至 `PUID/PGID` 的行为。
角色不会覆盖容器的 `user`，否则入口脚本可能无法准备数据目录。

实现依据：[v3.3.0 Compose](https://github.com/bookorbit/bookorbit/blob/v3.3.0/docker-compose.yml)、
[环境变量](https://github.com/bookorbit/bookorbit/blob/v3.3.0/.env.example)、
[容器入口](https://github.com/bookorbit/bookorbit/blob/v3.3.0/server/entrypoint.sh)、
[健康接口](https://github.com/bookorbit/bookorbit/blob/v3.3.0/server/src/modules/health/health.controller.ts)、
[首次设置令牌校验](https://github.com/bookorbit/bookorbit/blob/v3.3.0/server/src/modules/auth/auth.service.ts)。

PostgreSQL 使用官方 PG18 布局：挂载 `/var/lib/postgresql`，实际 `PGDATA` 为 `/var/lib/postgresql/18/docker`。
该调整依据 [PostgreSQL 18 Dockerfile](https://github.com/docker-library/postgres/blob/master/18/trixie/Dockerfile)
与 [官方入口脚本](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh)，避免旧的嵌套 bind 引入匿名父卷。

## DNS 与生产执行记录

使用已授权的 Cloudflare MCP，先读取 `willfan.me` zone 下名称**精确等于**
`bookorbit.willfan.me` 的记录。没有记录时创建以下 A 记录；已有完全一致记录时复用。
若同名记录指向其他地址、是 CNAME 或存在冲突，报告冲突，不覆盖其他目标。

| 字段 | 值 |
| --- | --- |
| 类型 | `A` |
| 名称 | `bookorbit.willfan.me` |
| IPv4 | `159.13.46.201` |
| Cloudflare proxy | `false`，DNS only |
| TTL | 自动 |

创建后通过 MCP 重新读取同名记录，并核对 DNS 解析。Caddy 直接提供 HTTPS，复用现有证书自动签发流程。

| 2026-10-08 执行项 | 结果 |
| --- | --- |
| 隔离假数据验证 | 已通过：模板、权限、重跑、输入拒绝、Compose、Ansible syntax-check 与 lint |
| Cloudflare MCP DNS 配置及复核 | 已创建并复核；记录 ID `1ec874f622cb2839ce95c2e6a119754a`，公共解析 `159.13.46.201`，DNS only |
| 任务分支 Vault 与本地 token 交付 | 已新增 4 项独立密钥；既有值核验未变，token 已交付且为 0600 |
| SSH 部署与只读生产验收 | 通过；两容器 healthy，HTTPS health 与设置页正常，Anki Writer/Proxy health 均 200；最终独立 Verify `ok=17 changed=0 failed=0` |
| 生产幂等重跑 | 通过；BookOrbit 所有任务无变化，容器 ID/启动时间/重启次数和配置指纹均未变；Caddy 仅 6 项临时候选操作 changed |

公网探测由 Mac 直接完成：443 正向对照可连，3000 与 5432 均不可达。浏览器已实际显示 Initial Setup 页面及 Setup token 字段。服务器已确认管理员设置完成（`needsSetup=false`）。

审核修正后，本地完整验证、7 项无网络端口回归、Mac 直接端口探测和只读生产验收全部通过。额外完整重部署因修改后需要重新授权而被自动审批拒绝；最终采用只读验收，运行中的镜像和持久化配置已匹配批准的部署。

## 密钥准备

以下变量已存在于加密的 `ansible/inventory/group_vars/all/vault.yml`，线上数据依赖这些值，常规重跑不要重新生成。
每项是独立的 32 字节随机数，编码为 64 位小写十六进制。
部署角色拒绝缺失、空白、含换行或插值字符、长度不符及互相复用的密钥。

| Vault 变量 | 用途 |
| --- | --- |
| `vault_bookorbit_db_password` | PostgreSQL 用户 `bookorbit` 的密码 |
| `vault_bookorbit_jwt_secret` | JWT 签名 |
| `vault_bookorbit_podcast_encryption_key` | Podcast 凭据加密 |
| `vault_bookorbit_setup_bootstrap_token` | 首次管理员设置保护 |

准备过程不把密钥写入聊天、日志或命令参数。`.vault_pass` 仅用于部署准备与执行；本地验证使用独立假 inventory、假密钥和 Ansible 配置。
角色通过 defaults 间接引用 Vault，远端 `/opt/bookorbit/.env` 属于 `root:root`，权限 `0600`，模板及 token 交付均禁止 diff 和日志输出。

部署时 token 写入执行部署的检出目录下 `ansible/credentials/bookorbit-bootstrap-token`，文件权限 `0600`，目录权限 `0700`。
该路径已被 Git 忽略。重跑时使用同一 Vault 值，不生成或轮换密钥。

## 本地验证

在 macOS 宿主的当前检出根目录运行，先按 `AGENTS.md` 准备 `.venv` 和 `ansible/collections`：

```bash
source .venv/bin/activate
python3 scripts/validate-bookorbit.py
```

脚本仅使用已有工具，不安装依赖、不连接生产、不启动容器，也不读取生产 inventory 或 Vault。所有产物写在被忽略的 `tmp/bookorbit-validation-*`。
它执行真实 Ansible 断言、模板和 token 文件交付任务，验证 `0600`、`--diff` 不泄漏密钥、重复渲染 `changed=0`、内容及修改时间稳定，
并比较交付 token、假 Vault 值与 Compose 应用环境中的 token 完全一致。
缺失密钥、空 token、插值、尾随换行、重复密钥、非法域名、非规范数据路径，以及布尔或小数 UID/GID 都必须失败。
单独执行 `--tags config` 的回归也必须在进入 Caddy 前拒绝非法域名。
文件系统夹具还覆盖空目录、首次启动失败留下的旧空 `pgdata`、旧布局已初始化数据库和新 PG18 布局重跑；
检查父目录可遍历、私有子目录权限与已有 `PG_VERSION` 内容不变，以及旧数据库在写入配置前被拦截。

脚本还运行 `docker compose config --quiet`，验证两个固定镜像、端口、持久化映射和上游权限约束；
使用独立配置运行 `ansible-playbook --syntax-check` 和 `ansible-lint --offline`。
Caddy 失败边界在离线阶段检查候选校验先于发布及 reload，且校验失败不能被忽略。
实际 Caddy 解析、ARM64 容器启动、HTTPS、DNS 和服务健康需要生产部署阶段确认。

## SSH 部署与验收

先确认 `ssh-add -L` 能列出部署所需公钥；`~/.ssh/known_hosts` 必须已包含通过可信来源核验的 `159.13.46.201` host key。
以下环境变量显式开启严格校验，覆盖仓库的默认 SSH 配置。部署需要目标 `159.13.46.201:22`
及三个服务的 HTTPS 网络访问。透明 TCP 代理（例如 Sandbox）会提前接受连接，`wait_for` 无法据此判断目标端口状态。公网端口检查因此由 Mac 直接执行，且先用同一 IP 的 443 端口作为正向对照。
以下命令在 macOS 宿主检出的 `ansible/` 目录执行；在任务 worktree 中运行时，追加指向主检出 `ansible/.vault_pass` 的 `--vault-password-file`：

```bash
ssh-add -L
export ANSIBLE_HOST_KEY_CHECKING=True
export ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=60s -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOME/.ssh/known_hosts"

ansible-playbook -i inventory/oci/hosts.yml \
  --extra-vars @inventory/host_vars/oracle-cloud-ubuntu2404.yml \
  --extra-vars @inventory/group_vars/all/vault.yml \
  playbooks/deploy-bookorbit-oci.yml

ansible-playbook -i inventory/oci/hosts.yml \
  --extra-vars @inventory/host_vars/oracle-cloud-ubuntu2404.yml \
  --extra-vars @inventory/group_vars/all/vault.yml \
  playbooks/deploy-bookorbit-oci.yml --tags verify
```

显式指定 host vars 和 Vault 是因为静态 inventory 在 `inventory/oci/` 子目录，Ansible 不会由该路径自动读取上层的同级变量目录。
上述环境变量同时用于部署和独立 Verify；本 playbook 不安装或替换 SSH、Docker 或 Caddy。

Deploy 创建目录、环境和 Compose 文件，等待两个容器健康；随后只包含 Caddy 的 `reverse-proxy` 任务，
新增 `conf.d/bookorbit.caddy` 站点片段。该复用任务先把现有站点与新站点组装为候选，使用现有 Caddy 校验，成功后才发布和 reload。
Caddy 完整安装角色不会运行。

`--tags verify` 只执行读取操作，检查：

- 两个容器均运行且 health 为 `healthy`，应用只绑定 `127.0.0.1:3000`，数据库无发布端口。
- 两个容器的实际 `Config.Image` 与固定 `tag@digest` 相符，应用 `/books` 和 `/data` 均绑定至配置的数据目录。
- PostgreSQL 只有一个持久化父目录 bind，`PGDATA` 使用 `18/docker`，实际数据目录属于 UID `999`、权限 `0700`。
- 远端 `.env` 为 `root:root`、`0600`，应用配置包含有效 bootstrap token；容器环境不输出到日志。
- `https://bookorbit.willfan.me/api/v1/health` 返回 `200`、`status=ok`、`details.database.status=up`。
- 设置状态接口和 `/setup` 可访问；`needsSetup` 在空数据库时为 `true`，用户初始化后为 `false`。
- `https://ankiwriter.willfan.me/health` 和 `https://proxy.willfan.me/health` 均保持 `200`。

随后在 Mac 的检出根目录运行以下只读生产检查（不经过 Sandbox）：

```bash
python3 scripts/check-bookorbit-public-ports.py --host 159.13.46.201
```

输出必须包含 `control_reachable: true`、两个端口的 `reachable: false` 和 `success: true`，退出码为 0。
该脚本拒绝在 Sandbox 内运行；正向对照连接失败时也会失败，避免把探测器断网误判为端口关闭。
443 对照成功后，目标端口只有连接超时或明确拒绝连接才计为关闭；权限或其他网络错误标记为 `indeterminate` 并非零退出。
结合 playbook 中对容器实际端口映射的断言，完成公网隔离验收。

只读验收确认固定版本中的 token 保护配置和设置入口，不发送创建账号的 POST 请求。
实际无 token/错误 token 的拒绝由上游 `assertSetupToken` 实现；个人管理员创建及登录由用户完成。

首次部署成功后以相同命令重跑。Compose 使用 `pull: missing` 和 `recreate: auto`，配置未变时不会强制拉取或重启。
模板和数据目录应保持稳定；现有 Caddy 任务每次创建、移除临时候选目录，因此 play recap 可仍报告这些临时操作为 changed。
幂等验收需同时确认 BookOrbit 文件未变、Compose 未重建、两个容器的 `StartedAt` 不变，不以整份 recap 的 `changed=0` 作为 Caddy 的要求。

## 首次登录

打开 `https://bookorbit.willfan.me`，空数据库会进入设置页。用本机文本编辑器打开已交付的
`ansible/credentials/bookorbit-bootstrap-token`，把 token 填入设置页的 bootstrap token 字段，
再填写自己的用户名、姓名、邮箱与密码。不要把 token 写入终端输出、聊天或 URL。

设置成功后由用户确认能登录。之后重跑部署会保留账号和数据库，设置状态应变为 `needsSetup=false`。
服务端书库入口为容器内 `/books`；此次不导入现有书库、不调整 KOReader 或 Readwise 配置。

## 持久化与备份

| 宿主路径 | 容器路径 / 用途 |
| --- | --- |
| `/opt/bookorbit/books` | 应用 `/books`，书库 |
| `/opt/bookorbit/data/app` | 应用 `/data`，封面、上传等应用数据 |
| `/opt/bookorbit/data/postgres` | PostgreSQL `/var/lib/postgresql`；`PGDATA` 为其下 `18/docker` |
| `/opt/bookorbit/.env` | 密钥与应用配置 |
| `/opt/bookorbit/docker-compose.yml` | 固定镜像与运行配置 |

书库与应用目录默认由 UID/GID `1000:1000` 使用。PostgreSQL 的挂载父目录权限为 `0755`，
让入口脚本从 root 降权后仍可遍历；真正保存数据库的 `18/docker` 子目录由官方入口脚本设置为 UID `999`、`0700`。
Ansible 不递归修改数据库文件，也不覆盖已有数据目录的所有权。

需要备份时在目标主机的 root shell 中执行以下操作。先停止应用写入，数据库保持运行以执行 `pg_dump`；
备份文件包含密钥，应以 `0600` 保存，并在传出主机前加密。

```bash
(
set -e
cd /opt/bookorbit
umask 077
bookorbit_backup="/opt/bookorbit/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$bookorbit_backup"
trap 'docker compose up -d app' EXIT
docker compose stop app
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$bookorbit_backup/database.dump"
tar -czf "$bookorbit_backup/files.tar.gz" books data/app .env docker-compose.yml
docker compose up -d app
trap - EXIT
)
```

禁止在新目录直接启动备份的 Compose：其中仍含生产项目名、固定 `container_name`、端口和绝对挂载，单改 `-p` 不够。
隔离恢复与切换按以下顺序进行：

1. 将备份解密到空的独立恢复目录，保留 `.env` 的 `0600` 权限，准备匹配的 PostgreSQL 18/pgvector 镜像。
2. 编辑恢复副本：修改顶层项目名，删除或另设全部 `container_name`，将三个宿主 bind 源全部改到恢复目录，
   应用端口改为未占用的回环端口或取消发布；同步调整恢复环境的 `APP_URL`、`CLIENT_URL`。
3. 先运行 `docker compose config --quiet`，再将展开后的 `docker compose config` 输出保存至受保护的 `0600` 文件核对。
   确认项目名、容器名、端口和每个挂载都与生产隔离，且没有指向生产数据目录；展开配置含密钥，不写日志。
4. 仅启动恢复环境的 PostgreSQL，把逻辑备份导入新数据库，再启动恢复应用。
   检查 health 的数据库状态、登录、书库文件和封面，并确认生产容器及现有服务仍正常。
5. 切换前暂停生产应用写入，取得最终备份并更新恢复数据，再次验证完整性。
   停止隔离恢复环境的应用和数据库后，才能让生产部署使用这些数据，避免两个数据库实例访问同一 PGDATA。
6. 保留原生产数据作为回退副本，将生产 `bookorbit_base_dir` 指向已验证的数据目录，核对生产 Compose 的挂载和端口后运行部署 playbook。
   完成 BookOrbit、Anki Writer、Proxy 的健康检查及公网端口检查后再恢复正常使用。

不要将运行中的 PostgreSQL 数据目录直接作为一致性备份，也不要覆盖当前数据库来试验恢复。

## 回退与错误处理

启动或数据库健康失败时保留 `/opt/bookorbit`，修正 role/playbook 后重跑。数据库已经初始化后，不能仅改 `.env`
中的密码来完成轮换；JWT 或 podcast 密钥变化也可能使现有会话或加密数据失效，常规重跑保持原值。

首次部署曾因旧配置把 root 所有的父目录设为 `0700`，导致 postgres 降权后无法创建或访问子目录。
已修正为 PG18 的父目录 bind 与可遍历权限。修复重跑保留旧空 `data/postgres/pgdata` 及原来的匿名卷，
不会主动删除它们；新容器仅使用持久化父目录 bind。如果检测到旧 `pgdata/PG_VERSION`，部署会在写入配置前停止，
要求先制定显式迁移方案，避免切换路径后误建新数据库。

Caddy 候选无效时，任务在发布前失败，当前入口继续运行。修正 BookOrbit 站点输入后重跑配置 play，
不要绕过 `caddy validate` 手工发布候选。

如果需要撤下此次新服务，先 `docker compose stop app postgres`，保留全部数据。
仅将 `/etc/caddy/conf.d/bookorbit.caddy` 移到不匹配 `*.caddy` 的备份路径，验证
`/etc/caddy/managed.Caddyfile` 成功后 reload Caddy；验证失败则移回该片段。
随后复查 Anki Writer 和 Proxy 的 `/health`。不修改其他站点、不删除卷、不执行 `down -v`。

版本回退前保留当前数据和备份，确认数据库迁移的向后兼容性；容器镜像恢复不等于数据库 schema 可以降级。
DNS 回退只处理本次新建且记录 ID 已核实的 BookOrbit 记录，并单独记录执行结果。
