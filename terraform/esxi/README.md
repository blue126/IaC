# ESXi（已退役）

2026-09-21 用户确认 ESXi 宿主已退役，原 T7910 已改为独立 Proxmox 节点 pve2。

此目录与 `../modules/esxi-vm/` 仅保留历史配置及 state 对账依据，不是活动部署入口。根模块目前只保留 vSphere data sources，不包含活动 VM 资源声明。不要对退役主机执行 plan/apply，也不要把该 workspace 的旧 inventory 重新注入 Ansible。

仓库已停用 ESXi inventory、Jenkins 路由/初始化/state 拉取及默认校验根选择。外部 Jenkins `ESXi-Provisioning` job、NetBox 平台选项和 HCP `iac-esxi-lab` workspace/state 未删除或修改；是否归档或清理须另行授权。保留代码不代表 state 已清空，也不授权 destroy 或 state rm。
