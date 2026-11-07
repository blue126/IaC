# Q3

workspace 部署直接使用 oci-hub-spoke 与 employee-workspace。 `ansible/playbooks/deploy-oci-hub-workspace.yml:24-29 (roles) @ aad7d3d`

employee-workspace 再调用 admin-ssh-keys 维护管理员访问。 `ansible/roles/employee-workspace/tasks/main.yml:19-24 (admin-ssh-keys) @ aad7d3d`

桌面 playbook 使用 kasmvnc，并在 provision 阶段 include hapi；hapi 不是另一套员工 VM。 `ansible/playbooks/prepare-employee-desktop.yml:2-19 (hapi) @ aad7d3d`

执行器部署同时调用 common、ubuntu-vm、tailscale、host-firewall、remotecc-ops-runtime、semaphore，存在通用主机角色依赖。 `ansible/playbooks/deploy-remotecc-ops.yml:50-56 (roles) @ aad7d3d`

终端 playbook 从 playbook_dir 的两级父目录读取 boundary.py 和 pve-sdn.py。 `ansible/playbooks/deploy-oci-hub-terminal.yml:26-48 (src) @ aad7d3d`

HAPI 独立安装入口调用 hapi role。 `ansible/playbooks/deploy-employee-hapi.yml:3-8 (roles) @ aad7d3d`

控制面部署入口调用 hapi-control-plane。 `ansible/playbooks/deploy-hapi-control-plane.yml:2-6 (roles) @ aad7d3d`

共享 Hub 部署入口调用 hapi-shared-hub。 `ansible/playbooks/deploy-hapi-shared-hub.yml:2-6 (roles) @ aad7d3d`

OCI Hub 部署入口作用于 oci 主机组并调用 oci-hub。 `ansible/playbooks/deploy-oci-hub.yml:2-6 (roles) @ aad7d3d`

oci-hub-pve 角色从 playbook_dir 的两级父目录读取 boundary.py 与 pve-sdn.py。 `ansible/roles/oci-hub-pve/tasks/main.yml:17-87 (src) @ aad7d3d`

router 入口直接调用 oci-hub-pve。 `ansible/playbooks/configure-oci-hub-router.yml:2-6 (oci-hub-pve) @ aad7d3d`

Mosh 边界入口渲染和复制同一个相对路径 boundary.py。 `ansible/playbooks/configure-oci-hub-mosh-boundary.yml:7-37 (argv) @ aad7d3d`

上述为已检查范围；不是整个仓库的反向依赖穷举。全部按 load-bearing 进入验证。
