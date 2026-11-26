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

`copy-ok` 出现后，在管理机上跑 `deploy-n8n.yml --limit n8n`：它把 `.env` 的数据目录改为 `/opt/n8n/...`、渲染 override 并启动新栈。启动后用 `sudo docker compose config` 确认项目名是 `n8n`、数据卷宿主机路径在 `/opt/n8n` 下，再跑 `--tags verify` 并确认工作流数量和迁移前一致。

手工回退：

```bash
cd /opt/n8n && sudo docker compose stop
cd /opt/n8n-rental && sudo docker compose start
```

回退后旧栈用的是迁移那一刻的数据；新栈期间的改动只在 `/opt/n8n/n8n-data` 里。回退期间不要重跑 `deploy-n8n.yml`，也不要触发 n8n-rental 发布，它们都会启动 `/opt/n8n` 的新栈。

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
