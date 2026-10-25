# n8n Docker Migration

本指南把当前由 IaC 管理的 n8n LXC（`pve0` / VMID `106` / `192.168.1.106`）从全局 npm + systemd 迁移到同一 LXC 内的 Docker Compose。Terraform 继续管理现有 LXC；Ansible 负责应用运行时切换。

## 设计边界

- 不新建 VM，也不改变当前 LXC 的地址、VMID、CPU 或内存。
- `terraform/proxmox/n8n.tf` 已提供 Docker-in-LXC 所需的 `nesting=1`；现场还存在 `keyctl=1`，迁移前必须保留该 LXC 特性。
- Docker 使用 host network override。非特权 LXC 中，host network 避免嵌套网络的 sysctl 限制；Caddy 继续访问 `192.168.1.106:5678`。
- n8n 应用源码来自 `blue126/n8n-rental`，版本由 `ansible/inventory/host_vars/n8n.yml` 的 `n8n_app_ref` 固定。
- 旧 systemd 服务在 staging 阶段保持运行；候选 Docker 实例使用空数据目录、loopback 备用端口 `5680`（task broker 使用 `5681`；`5679` 被旧 n8n 的 task broker 占用），不会接收生产流量。
- staging 设置 `N8N_DISABLE_PRODUCTION_MAIN_PROCESS=true`；该设置用于关闭 production webhooks，候选实例同时使用空数据目录，不加载生产 workflow。详见 [n8n environment variables](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/endpoints/)。
- 只有候选镜像和 runtime 健康后才进入短暂 cutover；Ansible 不覆盖旧目录，只把副本放入 `/opt/n8n-rental/n8n-data`。
- staging 前检查根盘至少保留 3,000,000,000 bytes；不足时直接退出，不停止 n8n。当前现场只剩约 1.6G，必须先清理或扩容。

## 执行入口

在 IaC 仓库的 `ansible/` 目录执行：

```bash
ansible-playbook playbooks/deploy-n8n.yml --limit n8n
```

Deploy play 会按以下顺序工作：

1. 安装 Docker Engine 和 Compose 插件。
2. 校验旧的 `/root/.n8n/config`、磁盘余量，并 checkout 固定的 `n8n-rental` 版本。
3. 保留旧环境文件中的 `HERMES_WEBHOOK_SECRET`，生成 staging Compose 配置；候选实例使用空数据目录、`127.0.0.1:5680`，task broker 移到 `5681`，并设置 `N8N_DISABLE_PRODUCTION_MAIN_PROCESS=true`。
4. 在旧 systemd n8n 仍监听 `5678` 时，完成 Docker pull/build、启动候选实例并等待 `5680/healthz/readiness`；失败时只清理候选实例，旧服务不受影响。
5. 候选验证通过后才停止并 disable 旧 `n8n.service`，并把 unit 文件改名为 `/etc/systemd/system/n8n.service.pre-docker`（systemd 不允许 mask 直接位于 `/etc/systemd/system` 的真实 unit 文件，改名同样能防止重启拉起且完全可逆），创建 `/root/n8n-pre-docker-migration.tgz`（如尚不存在），复制完整 `.n8n` 到 `n8n-data`，并复制既有 scraper cache。
6. 将 Compose 切到生产端口 `5678` 和真实数据目录；复用已构建镜像启动，不在停机窗口再次 pull/build。

随后 Verify play 会确认 Docker active、旧 systemd 服务不再 active、Compose 中的 `n8n` 服务正在运行、容器内版本为 `2.39.5`，以及生产 readiness endpoint 返回 200。

## 失败与回滚

staging 构建或健康检查失败时，旧 systemd 从未停止。只有真实 cutover 失败时，Ansible 才会执行 `docker compose down`、把 unit 文件改回原名并恢复旧 systemd 服务。若需要人工回滚：

```bash
cd /opt/n8n-rental
docker compose down
mv /etc/systemd/system/n8n.service.pre-docker /etc/systemd/system/n8n.service
systemctl daemon-reload
systemctl enable --now n8n
```

> 迁移验收通过后（2026-10-25），旧 npm 全局安装 `n8n` 已按单独授权从 LXC 移除。此后的手工回滚在 `systemctl enable --now n8n` 之前需要先重装运行时：`npm install -g n8n@2.39.5`。数据回滚路径（`/root/n8n-pre-docker-migration.tgz` 与 `/root/.n8n`）不受影响。

不要删除 `/root/n8n-pre-docker-migration.tgz`、`/root/.n8n` 或 `/opt/n8n-rental/n8n-data`。如果 Docker 版本已经迁移了 SQLite schema，恢复前必须先保留现有副本并单独确认兼容性。

## 验收

- `docker compose ps` 显示 `n8n` running/healthy。
- `https://n8n.willfan.me` 可以登录原有 owner 账号。
- Google OAuth、Header Auth、`n8n-nodes-md-to-docs` 和工作流仍然存在。
- 手动运行一次租房工作流，确认 Sheets/Docs 输出。
- 确认 `Australia/Sydney` 调度时间和 Caddy → `192.168.1.106:5678` 反向代理均正常。
- 至少一次成功验证后，再决定是否重新启用日常 Schedule Trigger。

本次代码变更只提供 IaC 和验证入口，不自动执行 Terraform apply、Ansible deploy 或生产切换。
