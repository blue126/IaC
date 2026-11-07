# 范围候选：带走或留在 IaC

依据：公开 IaC `aad7d3d` 的静态扫描和研究报告 Q1–Q6。“决定”列是 will 的决定，见 `decisions-2026-11-07.md`；待定的行不算范围。调用方只扫到 playbook 和 role tasks，未覆盖模板和动态 include，移出前仍须按 R8 逐项复核。

| 编号 | 单元 | 事实 | 建议 | 决定 |
| --- | --- | --- | --- | --- |
| S0 | 独立项目的归宿 | 私有 `remotecc` 仓库已承载 apply-site、hapi-control、wsctl 等组件，远端只在执行器上（layout） | 用现有私有仓库，不新建 | 按建议（D6） |
| S1 | `terraform/remotecc` 与 HCP workspace `iac-remotecc` | 独立 root 和 state，由 wsctl 驱动（Q2） | 带走 | 按建议（D6） |
| S2 | RemoteCC 专属 Ansible：roles `employee-workspace`、`oci-hub-spoke`、`oci-hub-mosh`、`oci-hub-pve`、`hapi`、`hapi-control-plane`、`hapi-shared-hub`、`hapi-ingress`、`remotecc-ops-runtime`（改名见 D14）；对应 playbook；inventory `terraform-remotecc.yml`；group_vars `employee_workspaces`、`hapi_control_plane`、`oci_hub_workspaces`；host_vars `remotecc-ops` | 扫描只见 RemoteCC 调用方 | 带走 | 按建议（D6） |
| S3 | `scripts/oci-hub/`、HAPI 脚本、`tests/oci-hub/`、`tests/hapi-workspace/`、`tests/employee-workspace/` | `tests/oci-hub` 的 ingress 夹具复制 `terraform/oci/oci-hub.tf`，受 S5 影响（Q5） | 带走 | 按建议（D6） |
| S4 | OCI Hub 服务：role `oci-hub`、`deploy-oci-hub.yml` | 跑在与 anki、bookorbit 共用的 OCI 主机上，并调用 `caddy` role | 服务带走，主机留 IaC | 按建议（D6） |
| S5 | `terraform/oci/oci-hub.tf` 与 `oci-hub-ingress.auto.tfvars.json` | 属于 `iac-oci` root，引用同一 VCN 和 NSG | 留 IaC，作为 RemoteCC 使用的接口 | 按建议（D6） |
| S6 | `terraform/modules/proxmox-vm` | proxmox root 6 处、remotecc root 2 处调用，经相邻路径引用（Q2） | 模块留 IaC；RemoteCC 不再用相邻路径，取得方式交架构 | 按建议（D6） |
| S7 | 通用 roles `common`、`tailscale`、`ubuntu-vm` | `common` 与 `tailscale` 各有十余个 playbook 调用；`ubuntu-vm` 另有 `deploy-container-lab.yml` | 留 IaC；RemoteCC 取得方式交架构 | 按建议（D6） |
| S8a | `kasmvnc`、`semaphore` | 名称通用，但扫描只见 RemoteCC 调用方 | 带走，先补模板级反查 | 带走（D6） |
| S8b | `admin-ssh-keys` | 只由 `employee-workspace` 调用；Terraform 建 VM 时也写入同一组公钥，Ansible 以 `ubuntu` 经 SSH 连入员工 VM | 切换时随项目带走，切换后按 R14 退役；替代通道首选 PVE API（D12） | 退役（D9、D12） |
| S8c | `host-firewall` | 只由 `deploy-remotecc-ops.yml` 调用 | 带走，规则不变，并入执行器角色，不再单独成 role | 不单独成 role（D10、D13） |
| S9 | IaC Vault 与 `scripts/get-secrets.sh` 桥接 | Proxmox 凭据文件被复制到 remotecc root（Q2）；员工流程用 BWS 和 IaC Vault 组合运行时 Vault（AGENTS） | RemoteCC 所需凭据全部进 BWS `remotecc`，不再依赖 IaC Vault | 按建议（D6） |
| S10 | 工具链与执行器 `/srv/iac` checkout | 执行器同时声明两个 checkout；`ansible.cfg` 相对解析 roles、collections、`.vault_pass`（Q4） | 独立项目自带工具链；切换后执行器不再需要 `/srv/iac`，下线另行授权 | 按建议（D6） |
| S11 | CI | 公开 IaC 用 GitHub Actions；私有仓库没有 GitHub 远端（Q1、Q5） | 必须有等效校验；是否允许增加 GitHub 私有远端由 will 决定，载体交架构 | 等效校验保留；GitHub 私有远端暂缓（D7） |
| S12 | 文档 | `docs/` 非归档文件有 55 个提及 RemoteCC、wsctl、oci-hub 或 HAPI | 运维和架构文档带走，IaC 只留一页接口说明 | 按建议（D6） |
| S13 | Skills `employee-provision`、`remotecc-user-docs` 与 `AGENTS.md` 的 RemoteCC 段落 | 均绑定当前仓库 | Skills 带走，`AGENTS.md` 改为指向新项目 | 按建议（D6） |
| S14 | BMAD 记录 `initiative-employee-lifecycle` | 位于公开 `_bmad-output/`，含多个 epic | 不动；本 initiative 留在 IaC 直到完成 | 按建议（D6） |
| S15 | 公开 Git 历史 | 已含这些文件的历史版本 | 不重写，列为不做 | 按建议（D6） |
