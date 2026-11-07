---
title: 'RemoteCC 与 IaC 共生依赖调查'
type: codebase
ask: '研究现有依赖，为后续独立项目规划提供事实'
repository: 'https://github.com/blue126/IaC'
commit: 'aad7d3d9edc453c409a63d56f9bdd6e7b9c3f3c9'
branch: 'agent/mary-analyst/ed2c5ec15285'
status: complete
validation: normal
claims: {"verified": 35}
created: '2026-11-07'
updated: '2026-11-07'
---

# RemoteCC 与 IaC 共生依赖调查

本文供 will 和后续规划人员核对固定提交的代码关系，不提出迁移设计，也不能作为可直接执行的删除清单。Terraform 已有独立 workspace，但共享模块、Ansible、执行器和 CI 仍连接两个仓库；对应证据按六个问题列出。私有实现细节另存受限证据包（对应第 4–6 问），不进入公开 IaC。

引用格式为“仓库内路径:行号（符号或最近标题）@ 提交”；括号内容不是分支名。

## Questions

1. 代码、文档和运行数据在哪里？
2. Terraform 与 state 如何关联？
3. 哪些 Ansible 与脚本接口相连？
4. 入口与执行器如何绑定代码根？
5. 测试与 CI 如何覆盖？
6. 现有边界及旧迁移记录如何形成？

问题集与独立研究归属（不挂入现有 initiative）已由 will 在 Issue 评论确认。文件预算为每个问题 15 个文件，历史预算为 10 个提交，验证级别为 normal。本轮由同一宿主依次执行 locator、analyzer、historian、verifier；没有独立子代理，研究防火墙未生效，即研究者未与任务意图区分到独立上下文。代码只取固定 Git 对象；不读取员工数据、凭据值或线上 state，不运行业务代码。

## 1. 代码、文档和运行数据在哪里？

布局文档把 apply-site、employee-miniprogram、hapi-control、wsctl 列为同一个私有 RemoteCC 仓库的组件，employee-data 与 hapi-data 为不入 Git 的运行数据。 `docs/architecture/remotecc-layout.md:8-16 (RemoteCC) @ aad7d3d`

公开 IaC 的忽略规则排除整个 remotecc 目录。 `.gitignore:36 (remotecc) @ aad7d3d`

文档说明私有仓库远端为执行器上的 remotecc.git、无 GitHub 远端，提交和分支独立于 IaC；这不是本轮对远端服务状态的核验。 `docs/architecture/remotecc-layout.md:19-25 (main) @ aad7d3d`

## 2. Terraform 与 state 如何关联？

RemoteCC root 绑定 HCP organization homelab-roseville / workspace iac-remotecc。 `terraform/remotecc/versions.tf:1-8 (terraform) @ aad7d3d`

公开布局文档另列模板 Terraform 源码 template-build-source 与数据目录 template-build 中的 state；本轮未读取该 state。 `docs/architecture/remotecc-layout.md:41 (state) @ aad7d3d`

内部 Proxmox root 的 workspace 名称为 iac-proxmox-lab。 `terraform/proxmox/versions.tf:1-8 (terraform) @ aad7d3d`

RemoteCC README 把员工 VM、VM500、员工模板及 remotecc-ops 列为 RemoteCC root 的资源，声明 local execution、由执行器上的 wsctl 驱动，名册为非 Git 运行数据。 `terraform/remotecc/README.md:1-7 (Infrastructure) @ aad7d3d`

员工 VM 模块仍从相邻 ../modules/proxmox-vm 引入，因此 workspace 分开不等于模块源码独立。 `terraform/remotecc/oci-hub-workspace.tf:54-57 (oci_hub_workspace) @ aad7d3d`

remotecc-ops 同样引用相邻的 proxmox-vm 模块。 `terraform/remotecc/remotecc-ops.tf:1-2 (source) @ aad7d3d`

RemoteCC 动态 inventory 指向相对路径 ../terraform/remotecc。 `ansible/inventory/terraform-remotecc.yml:1-2 (project_path) @ aad7d3d`

state 刷新脚本默认包含 proxmox、remotecc、oci，并把 state pull 的结果写入各 root 的 terraform.tfstate。 `scripts/refresh-terraform-state.sh:11-40 (STATE_FILE) @ aad7d3d`

secrets bridge 把 Proxmox 的生成凭据文件复制到 RemoteCC root；这说明 Proxmox 与 RemoteCC 共享凭据输入路径，不证明任何凭据当前有效。 `scripts/get-secrets.sh:47-48 (PROJECT_ROOT) @ aad7d3d`

## 3. 哪些 Ansible 与脚本接口相连？

OCI Hub workspace 部署入口直接使用 oci-hub-spoke 与 employee-workspace 角色。 `ansible/playbooks/deploy-oci-hub-workspace.yml:24-29 (roles) @ aad7d3d`

employee-workspace 再调用 admin-ssh-keys 维护管理员访问。 `ansible/roles/employee-workspace/tasks/main.yml:19-24 (admin-ssh-keys) @ aad7d3d`

桌面 playbook 使用 kasmvnc，并在 provision 阶段 include hapi；hapi 不是另一套员工 VM。 `ansible/playbooks/prepare-employee-desktop.yml:2-19 (hapi) @ aad7d3d`

执行器部署同时调用 common、ubuntu-vm、tailscale、host-firewall、remotecc-ops-runtime、semaphore，存在通用主机角色依赖。 `ansible/playbooks/deploy-remotecc-ops.yml:50-56 (roles) @ aad7d3d`

终端 playbook 从 playbook_dir 的两级父目录读取 boundary.py 和 pve-sdn.py。 `ansible/playbooks/deploy-oci-hub-terminal.yml:26-48 (src) @ aad7d3d`

HAPI 独立安装入口调用 hapi 角色。 `ansible/playbooks/deploy-employee-hapi.yml:3-8 (roles) @ aad7d3d`

控制面部署入口调用 hapi-control-plane。 `ansible/playbooks/deploy-hapi-control-plane.yml:2-6 (roles) @ aad7d3d`

共享 Hub 部署入口调用 hapi-shared-hub。 `ansible/playbooks/deploy-hapi-shared-hub.yml:2-6 (roles) @ aad7d3d`

OCI Hub 部署入口作用于 oci 主机组并调用 oci-hub。 `ansible/playbooks/deploy-oci-hub.yml:2-6 (roles) @ aad7d3d`

oci-hub-pve 角色从 playbook_dir 的两级父目录读取 boundary.py 与 pve-sdn.py。 `ansible/roles/oci-hub-pve/tasks/main.yml:17-87 (src) @ aad7d3d`

router 入口直接调用 oci-hub-pve。 `ansible/playbooks/configure-oci-hub-router.yml:2-6 (oci-hub-pve) @ aad7d3d`

Mosh 边界入口渲染和复制同一个相对路径 boundary.py。 `ansible/playbooks/configure-oci-hub-mosh-boundary.yml:7-37 (argv) @ aad7d3d`

## 4. 入口与执行器如何绑定代码根？

公开 IaC 中的执行器默认配置同时声明 /srv/remotecc 和 /srv/iac 两个 checkout；只有 remotecc 条目声明 /run/wsctl.lock。这是配置声明，未现场验证部署状态。 `ansible/roles/remotecc-ops-runtime/defaults/main.yml:12-27 (remotecc_ops_repositories) @ aad7d3d`

公开 Ansible 配置把 roles、collections 和 .vault_pass 解析为相对于所在 Ansible 树的资源，迁离代码根不能自动带走这些运行材料。 `ansible/ansible.cfg:6-10 (roles_path) @ aad7d3d`

公开接口文档明确：源码复制不等于配置和数据绑定复制；执行器上的 IaC 根由受保护配置决定。私有入口的精确解析与拒绝条件见独立受限证据包。 `docs/architecture/remotecc-layout.md:27-39 (Worktree) @ aad7d3d`

## 5. 测试与 CI 如何覆盖？

CI classifier 将共享模块变化关联到四个 root，并将 tests/oci-hub 的变化关联到 RemoteCC root。 `scripts/ci/classify-pr.sh:50-70 (terraform_remotecc) @ aad7d3d`

Terraform validator 限定 root 允许列表，执行 fmt、init -backend=false、validate；这个脚本不执行 plan/apply。 `scripts/ci/validate-terraform.sh:18-36 (selected_roots) @ aad7d3d`

Ansible validator 使用 CI 专用 inventory/config，撤销 Vault 环境变量，再 lint 与逐 playbook syntax-check；脚本会安装依赖，本轮没有执行该脚本。 `scripts/ci/validate-ansible.sh:27-80 (ANSIBLE_CONFIG) @ aad7d3d`

OCI ingress 测试夹具实际复制 terraform/oci/oci-hub.tf，而不是 RemoteCC root；测试目录名不能直接当作资源归属。 `tests/oci-hub/prepare-ingress-terraform.py:7-11 (root) @ aad7d3d`

HAPI README 明确 tests/hapi-workspace 目录不在 PR 校验内，需手工运行；列出的历史测试通过数不是本轮测试结果。 `tests/hapi-workspace/README.md:35-37 (Kasm网页客户端) @ aad7d3d`

## 6. 现有边界及旧迁移记录如何形成？

旧 story 记录迁往私有 IaC 子目录的提议，2026-11-06 暂缓、未批准；它记录了将子目录命名为 IaC 的决定以及三个待决事项，不能当作已实施事实。 `_bmad-output/backlog/story-remotecc-iac-files-moved-to-private-repo.md:19-37 (Description) @ aad7d3d`

历史补充：`c269b5b "feat(terraform): split the RemoteCC VMs into terraform/remotecc (story 5.19)"` 的 diff 新增 RemoteCC cloud binding；`1d0cda8 "feat(remotecc-ops): deploy RemoteCC from one repository and add Hugo"` 的 diff 将执行器私有组件改为来自同一 remotecc checkout。提交说明中的线上 state 核验不作为本轮实测结果。关联 [PR #249](https://github.com/blue126/IaC/pull/249) 与 [#248](https://github.com/blue126/IaC/pull/248) 说明 root 拆分是为了分离 wsctl 与 Jenkins；[PR #257](https://github.com/blue126/IaC/pull/257) 说明私有仓库合并保持既有 wsctl 路径。已存在布局文档覆盖该边界，本轮不提出重复 ADR。

## Open questions

- **未现场验证**：执行器当前代码 SHA、实际配置、state 内容和 pending approvals 是什么？本轮只验证源码声明，没有运行 wsctl、Terraform、Ansible 或线上 dry run。
- **私有证据边界**：受限证据包包含入口路径、审批哈希与测试父目录依赖；公开文档不携带这些实现细节。接收方须取受限证据包，核对其中的固定私有 SHA，不能假定 worktree 会自动共享这些内容。
- **后续范围决定**：新独立项目的目标涵盖哪些应用、基础设施、工具链、数据与交付流程？旧方案范围是否仍适用，需在后续规划决定；本次研究确认旧方案未获批准。
- **预算边界**：第 3 问已检查主要入口、角色和脚本调用点，未逐个展开全部角色模板和反向消费者；后续事实问题是“拟定迁移清单中的每个角色/脚本 还有哪些非 RemoteCC 调用方？”不能把此报告当作可直接执行的删除清单。
- **测试边界**：入口代码、CI 分类和夹具依赖已经静态核查；未执行现有业务测试，未验证迁移后行为或线上 state 无差异。

## Prior documents

已有输入：`RemoteCC 管理员代码与私有运行数据`、`RemoteCC IaC files live in the private remotecc repository`。未发现同题 research/ADR；不继续或改写 employee-lifecycle、ci-only-execution 的工作流。本轮研究获准修改研究记录，未向已暂停的旧 story 追加 References，以免改动其他任务记录；研究关联保存在本报告和 Issue。

## 验证与交付

验证结果见同目录 `verification.md`，逐题摘要见 `digests/`；报告及 digest 使用同一固定版本。以后运行 `.agents/skills/bmad-deep-recon/scripts/recon_kit.py anchors <报告> --repo <仓库>` 不带 --at 可检查引用文件是否相对基线发生变化。文档排版审核与事实核查分别记录，未执行项不得算通过。
