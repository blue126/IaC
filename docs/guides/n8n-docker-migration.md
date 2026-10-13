# n8n Docker Migration

本指南把当前由 IaC 管理的 n8n LXC（`pve0` / VMID `106` / `192.168.1.106`）从全局 npm + systemd 迁移到同一 LXC 内的 Docker Compose。Terraform 继续管理现有 LXC；Ansible 负责应用运行时切换。

## 设计边界

- 不新建 VM，也不改变当前 LXC 的地址、VMID、CPU 或内存。
- `terraform/proxmox/n8n.tf` 已提供 Docker-in-LXC 所需的 `nesting=1`；现场还存在 `keyctl=1`，迁移前必须保留该 LXC 特性。
- Docker 使用 host network override。非特权 LXC 中，host network 避免嵌套网络的 sysctl 限制；Caddy 继续访问 `192.168.1.106:5678`。
- n8n 应用源码来自 `blue126/n8n-rental`，版本由 `ansible/inventory/host_vars/n8n.yml` 的 `n8n_app_ref` 固定。
- 迁移前先归档 `/root/.n8n`；Ansible 不覆盖旧目录，只把副本放入 `/opt/n8n-rental/n8n-data`。

## 执行入口

在 IaC 仓库的 `ansible/` 目录执行：

```bash
ansible-playbook playbooks/deploy-n8n.yml --limit n8n
```

Deploy play 会按以下顺序工作：

1. 安装 Docker Engine 和 Compose 插件。
2. 校验旧的 `/root/.n8n/config` 存在，并 checkout 固定的 `n8n-rental` 版本。
3. 停止并 mask 旧 `n8n.service`，创建 `/root/n8n-pre-docker-migration.tgz`（如尚不存在）。
4. 复制完整 `.n8n` 到 `n8n-data`，保留 SQLite、凭证、加密配置和社区节点；同时复制既有 scraper cache。
5. 保留旧环境文件中的 `HERMES_WEBHOOK_SECRET`，写入 Compose 所需的非敏感配置，并生成 LXC host-network override。
6. 校验合并后的 Compose 配置、构建固定版本镜像、启动容器并等待 `/healthz/readiness`。

随后 Verify play 会确认 Docker active、旧 systemd 服务不再 active、Compose 中的 `n8n` 服务正在运行、容器内版本为 `2.39.5`，以及 readiness endpoint 返回 200。

## 失败与回滚

Ansible 的切换 block 在 Compose 构建或健康检查失败时会自动执行 `docker compose down`，解除 mask 并恢复旧 systemd 服务。若需要人工回滚：

```bash
cd /opt/n8n-rental
docker compose down
systemctl unmask n8n
systemctl enable --now n8n
```

不要删除 `/root/n8n-pre-docker-migration.tgz`、`/root/.n8n` 或 `/opt/n8n-rental/n8n-data`。如果 Docker 版本已经迁移了 SQLite schema，恢复前必须先保留现有副本并单独确认兼容性。

## 验收

- `docker compose ps` 显示 `n8n` running/healthy。
- `https://n8n.willfan.me` 可以登录原有 owner 账号。
- Google OAuth、Header Auth、`n8n-nodes-md-to-docs` 和工作流仍然存在。
- 手动运行一次租房工作流，确认 Sheets/Docs 输出。
- 确认 `Australia/Sydney` 调度时间和 Caddy → `192.168.1.106:5678` 反向代理均正常。
- 至少一次成功验证后，再决定是否重新启用日常 Schedule Trigger。

本次代码变更只提供 IaC 和验证入口，不自动执行 Terraform apply、Ansible deploy 或生产切换。
