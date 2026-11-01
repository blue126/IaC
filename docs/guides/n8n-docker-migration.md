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
- Caddy 上游保持 `192.168.1.106:5678`

临时 staging VM 使用过 `VMID 119 / 192.168.1.119`，最终验收后已删除。原 LXC `VMID 106` 已停止并销毁；迁移前快照已上传到 PBS，不能依赖本地回滚包。

## IaC 基线

- `terraform/proxmox/n8n.tf` 使用 `modules/proxmox-vm`，目标为 VMID 106。
- `ansible/inventory/host_vars/n8n.yml` 将 n8n 放入 `pve_vms`，并启用既有 Docker runtime 模式。
- Ansible 的 VM 模式只校验并启动现有 Compose，不执行旧 LXC/systemd cutover。

## 迁移原则

1. 先用临时 VM 验证 Docker 镜像、Compose、数据目录和 readiness。
2. 切换前创建 PBS 备份，并停止旧 n8n Docker，做最后一次数据同步。
3. 释放旧 LXC VMID 106 后，从已验证的 VM 副本创建最终 VMID 106，设置原 IP。
4. 启动 Docker，验证容器、readiness、公网 Caddy 上游和工作流数据。
5. 保留 PBS 备份，直到业务验收完成；本地回滚包按运维决定清理。

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

当前迁移已完成运行验证；后续 IaC 变更必须先执行 Terraform state import/plan，再 apply，不要直接把 VM 资源当作全新 VM 重建。
