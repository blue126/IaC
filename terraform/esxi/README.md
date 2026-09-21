# ESXi（已退役）

2026-09-21 用户确认 ESXi 宿主已退役，原 T7910 已改为独立 Proxmox 节点 pve2。

此目录与 `../modules/esxi-vm/` 仅保留历史配置及 state 对账依据，不是活动部署入口。根模块目前只保留 vSphere data sources，不包含活动 VM 资源声明。不要对退役主机执行 plan/apply，也不要把该 workspace 的旧 inventory 重新注入 Ansible。

仓库已停用 ESXi inventory、Jenkins 路由/初始化/state 拉取及默认校验根选择。2026-09-21 经用户授权，HCP `homelab-roseville/iac-esxi-lab`（`ws-t6bu7szNM7Uc1kse`）已删除；删除前 state serial15 仅含四个 data source，没有 managed resource、活动 run、remote-state consumer 或入站/出站 run trigger。删除返回204，随后按ID与名称查询均为404。未运行terraform destroy，未操作实机。

最终state已用当前Ansible Vault密码加密、解密校验通过，并交付用户保存：`iac-esxi-lab-state-15.tfstate.vault`，SHA-256为 `a58876c52d13ff5e13882f97424b39f981c63815e3b8e59a849a0a9423d0c689`。备份不包含HCP历史版本全集；workspace删除前已明确告知历史状态会一并删除。

此目录的cloud backend绑定已移除，避免init误建回旧workspace。外部Jenkins `ESXi-Provisioning` job和NetBox平台选项未修改，仍须另行决定。
