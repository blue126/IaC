# Q2

RemoteCC root 绑定 HCP organization homelab-roseville / workspace iac-remotecc。 `terraform/remotecc/versions.tf:1-8 (terraform) @ aad7d3d`

公开布局文档另列模板 Terraform 源码 template-build-source 与数据目录 template-build 中的 state；本轮未读取该 state。 `docs/architecture/remotecc-layout.md:41 (state) @ aad7d3d`

内部 Proxmox root 的 workspace 名称为 iac-proxmox-lab。 `terraform/proxmox/versions.tf:1-8 (terraform) @ aad7d3d`

RemoteCC README 把员工 VM、VM500、员工模板及 remotecc-ops 列为该 root 的资源，声明 local execution、由执行器 wsctl 驱动，名册为非 Git 运行数据。 `terraform/remotecc/README.md:1-7 (Infrastructure) @ aad7d3d`

员工 VM 模块仍从相邻 ../modules/proxmox-vm 引入，因此 workspace 分开不等于模块源码独立。 `terraform/remotecc/oci-hub-workspace.tf:54-57 (oci_hub_workspace) @ aad7d3d`

remotecc-ops 同样引用相邻的 proxmox-vm 模块。 `terraform/remotecc/remotecc-ops.tf:1-2 (source) @ aad7d3d`

RemoteCC 动态 inventory 指向相对路径 ../terraform/remotecc。 `ansible/inventory/terraform-remotecc.yml:1-2 (project_path) @ aad7d3d`

state 刷新脚本默认包含 proxmox、remotecc、oci，并把 state pull 的结果写入各 root 的 terraform.tfstate。 `scripts/refresh-terraform-state.sh:11-40 (STATE_FILE) @ aad7d3d`

secrets bridge 把 Proxmox 的生成凭据文件复制到 RemoteCC root；这说明共享凭据输入路径，不证明任何凭据当前有效。 `scripts/get-secrets.sh:47-48 (PROJECT_ROOT) @ aad7d3d`

上述为已检查范围；不是整个仓库的反向依赖穷举。全部按 load-bearing 进入验证。
