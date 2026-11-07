# 跨 epic 共享决策（架构输入）

本表列出多个 epic 必须一致的决定。下表事实以 `aad7d3d` 为准，lifecycle epic 8–12 完成后要按当时的代码重核（D19）。归属都是架构 spine；架构定稿后，采用它的 epic 在 References 引用对应章节。这里只陈述事实和待决内容，不做选择。

| 编号 | 待决内容 | 采用的 epic | 已知事实 |
| --- | --- | --- | --- |
| A1 | 仓库布局，含旧方案子目录名 `IaC` 是否继续用 | 1、2、3、4 | S0 定为现有私有仓库；旧 story 的子目录名未获批准 |
| A2 | RemoteCC 取得共享模块和角色的方式 | 1、3 | S6、S7 留 IaC；`oci-hub` role 调用 `caddy`（`ansible/roles/oci-hub/tasks/main.yml:141`） |
| A3 | 校验载体，以及是否增加 GitHub 私有远端 | 1、3、4 | S11 要求等效校验；私有远端问题暂缓（D7） |
| A4 | 凭据路径 | 1、2、3 | S9 定为全部进 BWS `remotecc`；L5 只有静态结论。AD-31 让 Portal 密钥和配对令牌先进 Ansible Vault，epic 3 再迁到 BWS（D18），凭据改动需单独授权 |
| A5 | 切换方式和回退：整体切换或分批 | 1、2 | 切分按整体切换假设，改为分批时重切 epic 2 |
| A6 | 搬迁基线 | 1、2、3、4 | 过渡期写入已定：epic 1 最后一次同步到 epic 2 完成之间暂停 RemoteCC 改动（D17）。执行器 IaC 在 `1f74169`，落后 `aad7d3d` 17 个 commit；S2–S4 路径有 10 处差异，含 `oci-hub` role 和 `deploy-oci-hub.yml`。AD-30 落地后防火墙代码只由 `oci-hub`、`oci-hub-pve` 两个 role 下发，不再有两个来源写 Hub 主机同一文件 |
| A7 | IaC 保留的接口：`oci-hub.tf`、ingress 变量文件、`cloud-init-ubuntu.yml`，以及 AD-32 的 Hub 备份策略和实例保护 | 1、3、4 | `tests/oci-hub/prepare-ingress-terraform.py` 复制 `terraform/oci/oci-hub.tf`；ingress 变量文件是 CI-only AD-14 的 shared path；`remotecc_ops` 经模块默认值使用 `terraform/proxmox/cloud-init-snippet.tf` 管理的 snippet |
| A8 | 管理通道 | 1、5 | 首选 PVE API 加 QEMU Guest Agent（D12），可行性待 spike；epic 1 搬迁 `admin-ssh-keys`，epic 5 退役 |

| A9 | 修订 AD-25、AD-30、AD-31：它们写的 IaC、`/srv/iac`、`iac.git` 和 Ansible Vault 是独立前的过渡状态，终态是 Hub 服务带走、密钥进 BWS（D18）；AD-25 的静态参数变量文件放哪也要定 | 1、2、3 | 架构负责人修订，lifecycle 的 story 不因此改动 |

## 架构还需核对

- `deploy-remotecc-ops.yml`、`deploy-hapi-control-plane.yml`、`deploy-hapi-shared-hub.yml` 的运行位置，它们决定 epic 2 的切换范围是否足够。
- `oci_hub_mosh_gateway` 等主机组的 inventory 来源，它决定 `ansible/inventory/oci/hosts.yml` 由 epic 1 还是 epic 3 处理。
- CI-only 架构 Deferred 一节写着 `terraform/modules` 和共享角色随后也迁走，并把 `iac-remotecc` 迁到独立 HCP organization 列为 token 隔离路线。S6、S7 和本 initiative 的 Boundaries 与前者不同，后者不在范围内；R10 需要更新这段说明。
