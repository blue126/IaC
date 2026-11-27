# n8n Docker Runtime: LXC → VM

本次迁移已完成：n8n 从 `pve0` 上的 LXC 迁移到 QEMU VM，同时保留原 VMID、IP 和 CPU/RAM 规格。

## 当前状态

- Proxmox 节点：`pve0`
- VMID：`106`
- 地址：`192.168.1.106/24`，网关 `192.168.1.1`
- 运行时：Ubuntu 24.04 QEMU VM + Docker Compose
- 规格：2 vCPU、4G RAM、20G `vmdata` 系统盘
- 网络：`vmbr1`，VirtIO 网卡
- n8n：`2.39.5`，容器策略 `unless-stopped`
- 运行目录：`/opt/n8n`；Compose 项目名 `n8n`，容器名 `n8n`，镜像 `n8n-local:<版本>`
- Caddy 上游保持 `192.168.1.106:5678`

临时 staging VM 使用过 `VMID 119 / 192.168.1.119`，最终验收后已删除。原 LXC `VMID 106` 已停止并销毁；迁移前快照已上传到 PBS，不能依赖本地回滚包。
PBS 快照标识为 `ct/106/2026-11-01T13:36:25Z`；本地回滚包已按要求删除。

## IaC 基线

- `terraform/proxmox/n8n.tf` 使用 `modules/proxmox-vm`，目标为 VMID 106。
- 现有 VM 已导入 HCP Terraform state；导入前移除了已销毁的 LXC state，导入地址为 `pve0/106`。
- n8n 的现有 Cloud-Init drive、磁盘 discard、CPU 类型、内存 balloon 和网卡防火墙设置已与实机对齐，避免后续 plan 触发 VM replacement。
- `ansible/inventory/host_vars/n8n.yml` 将 n8n 放入 `pve_vms`，并启用既有 Docker runtime 模式。
- Ansible 的 VM 模式只校验并启动现有 Compose，不执行旧 LXC/systemd cutover。

## 运行目录改名（n8n-rental → n8n）

这台 n8n 跑着全部工作流，不只是租房项目，所以运行时统一改叫 n8n。工作流和 `docker-compose.yml`、`Dockerfile`、`Jenkinsfile` 仍由 n8n-rental 仓库管理；IaC 的 override 模板固定顶层 `name: n8n`、`container_name: n8n` 和 `image: n8n-local:${N8N_VERSION}`。

从 `/opt/n8n-rental` 迁到 `/opt/n8n` 是一次性手工操作，不写进 playbook。旧目录、旧容器和旧镜像标签保留作回退。

前提：n8n-rental 仓库的 Jenkinsfile 发布目录已改为 `/opt/n8n` 并合并；切换和回退期间不要触发 n8n-rental 的 Jenkins 发布，否则它会往停用的目录发布并启动 Compose，与运行中的栈争用 5678。

在 VM 上（`ubuntu` + sudo）：

```bash
# 1. Stop (not down) the old stack so its container stays for rollback
cd /opt/n8n-rental && sudo docker compose stop
# 2. Back up the SQLite database; n8n runs it in WAL mode
cd /opt/n8n-rental/n8n-data && sudo tar -czf /opt/n8n-rental/n8n-db-before-rename.tgz database.sqlite*
# 3. Copy the whole runtime and compare every data file
sudo cp -a /opt/n8n-rental /opt/n8n
sudo rm /opt/n8n/n8n-db-before-rename.tgz
diff <(cd /opt/n8n-rental && sudo find n8n-data data -type f -exec sha256sum {} + | sort -k2) \
     <(cd /opt/n8n && sudo find n8n-data data -type f -exec sha256sum {} + | sort -k2) && echo copy-ok
# 4. Reuse the existing image under the new name (full tag; no rebuild)
sudo docker image tag n8n-rental-n8n:2.39.5 n8n-local:2.39.5
```

`copy-ok` 出现后，在管理机上只跑 `n8n` role（见下方执行记录；不要跑完整 `deploy-n8n.yml`，它还会执行 `common` 和 `tailscale`）：它把 `.env` 的数据目录改为 `/opt/n8n/...`、渲染 override 并启动新栈。启动后用 `sudo docker compose config` 确认项目名是 `n8n`、数据卷宿主机路径在 `/opt/n8n` 下，再跑 `--tags verify` 并确认工作流数量和迁移前一致。

手工回退：

```bash
cd /opt/n8n && sudo docker compose stop
cd /opt/n8n-rental && sudo docker compose start
```

回退后旧栈用的是迁移那一刻的数据；新栈期间的改动只在 `/opt/n8n/n8n-data` 里。回退期间不要重跑 `deploy-n8n.yml`，也不要触发 n8n-rental 发布，它们都会启动 `/opt/n8n` 的新栈。

### 执行记录（2026-11-26）

- 13:39–13:41 UTC 按上面的步骤切换。切换前 24 个 workflow、10 个 active；`copy-ok` 通过，备份在 `/opt/n8n-rental/n8n-db-before-rename.tgz`。
- 没有跑完整 `deploy-n8n.yml`：在 check mode 下它的 `common` 和 `tailscale` 会改动 106（多加 3 把公钥、sudo 免密、开 IP 转发、重新做 tailscale 认证），这些漂移和本次改名无关。实际只跑了 `n8n` role，用的是一个临时 playbook（`hosts: n8n`、`become: true`、`roles: [n8n]`），然后跑 `deploy-n8n.yml --tags verify`，断言全部通过。
- 切换后：Compose 项目 `n8n`、数据卷在 `/opt/n8n` 下、容器 healthy、readiness 和公网 200、workflow 数量仍是 24/10。
- 没有把 n8n-only playbook 加进仓库：按 `docs/architecture/cicd-architecture.md`，新增的 `ansible/playbooks/deploy-*.yml` 会被 IaC-Homelab-Pipeline 直接加入部署列表。需要时在仓库外临时写一个。
- 旧目录 `/opt/n8n-rental`、已停止的容器 `n8n-rental-n8n-1` 和镜像标签 `n8n-rental-n8n:2.39.5` 仍保留作回退，等首轮定时任务验证后再清理。

### 发布链路现状（2026-11-27）

n8n-rental 合并到 GitHub `main` 后，由合并者把 `origin/main` 快进推送到 Gitea `admin/n8n-rental`（`git push gitea origin/main:refs/heads/main`）。Gitea 上这个仓库已从 pull mirror 转为普通仓库，不再定时拉取 GitHub；转换后用 `gitea admin regenerate hooks` 补装了 git hooks，否则推送不会触发 webhook。

Gitea webhook（id=2，push，分支 `main`）调用 107 上 Jenkins 的 `n8n-rental`（Generic Webhook Trigger）。Jenkins 以 `ubuntu@192.168.1.106` 和 `jenkins@homelab` 公钥（`SHA256:pgAWCRe3BXDYIMpt+VWa+sBLVQ5BAxy5U029FU5ryt8`）发布，`sudo` 执行 rsync 和 Docker。#21、#22 成功；#23 的 n8n 部分成功，`Deploy Apps Script` 因 Jenkins 缺少 `google-apps-script-clasp-auth` 凭据失败。

未纳入 IaC 的手工状态：

- 这把公钥是手工加进 106 `ubuntu` 的 `authorized_keys` 的；107 上 jenkins 用户的 `known_hosts` 也手工更新为 106 当前的主机密钥。
- 如果要纳入 IaC，应放在 `n8n` role 或 `host_vars/n8n.yml`，不要放进 `common`，以免扩大 `common` 在 106 上的漂移。

## 迁移原则

1. 先用临时 VM 验证 Docker 镜像、Compose、数据目录和 readiness。
2. 切换前创建 PBS 备份，并停止旧 n8n Docker，做最后一次数据同步。
3. 释放旧 LXC VMID 106 后，从已验证的 VM 副本创建最终 VMID 106，设置原 IP。
4. 启动 Docker，验证容器、readiness、公网 Caddy 上游和工作流数据。
5. 保留 PBS 备份，直到业务验收完成；本地回滚包已在验收后清理。

## 验证

```bash
cd ansible
ansible-playbook playbooks/deploy-n8n.yml --limit n8n --tags verify
```

应确认：

- Docker service active，Compose n8n running/healthy；
- `http://192.168.1.106:5678/healthz/readiness` 返回 200；
- `https://n8n.willfan.me` 可访问并保留原有 owner、OAuth/Header Auth 和 workflow；
- `AU Rental Search Scout` 的调度、Sheets/Docs 输出正常。

当前迁移已完成运行验证，现有 VM state 也已导入；后续 IaC 变更仍必须先执行 plan，再 apply，不要直接把 VM 资源当作全新 VM 重建。

本次已执行 n8n 定向 Terraform apply，结果为 `0 added, 2 changed, 0 destroyed`；随后定向 plan 为 `No changes`。完整 workspace plan 仍显示与本迁移无关的既有 drift（PNetLab replacement、ws-executor 更新和 employee retirement），本次没有 apply 这些变更。
