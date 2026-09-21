# PNetLab 在独立 pve2 上的部署前置检查

**日期**：2026-09-21  
**标签**：PNetLab、Proxmox VE、pve2、nested virtualization、IaC

## 背景

原 T7910 已转换为独立 Proxmox VE 节点 `pve2`，管理地址为 `192.168.1.52`，不属于 pve0/pve1 的 corosync 集群。PNetLab 不应覆盖现有 Containerlab VM108，而应运行在 pve2 上新建的专用 Ubuntu 26.04 虚拟机中。

## 地址分配的教训

最初候选 `.104` 虽然在 pve2 不存在，但会响应 ICMP；该地址已被 pve0 的 NetBox VM 使用。因此独立 PVE 的 VMID 可以复用，但同一 LAN 上的 IP 不能复用。

候选 `192.168.1.250` 在 pve2 的邻居表中没有 MAC、两次 ICMP 也无响应，但这不足以证明地址空闲。Terraform apply 前仍必须核对路由器 DHCP/static lease 与 NetBox，避免静态地址和睡眠设备冲突。

## PNetLab appliance 边界

PNetLab 安装器不是普通应用安装器。它会接管 Docker、网络、Cloud-Init network ownership、systemd-networkd 和 SSH，并默认重启。因此策略为：

1. Terraform 只创建专用 VM 与 Cloud-Init 引导；
2. Ansible 校验外部 bundle 的 SHA-256 后，以 `--no-reboot` 执行安装；
3. Ansible 接管 `pnet0` 的静态管理地址并恢复 SSH hardening；
4. 重启必须单独授权，随后独立验证 KVM、QGA、网络与 PNetLab 服务。

bundle 不提交 Git；仓库只保存文本 SHA-256 manifest。该 manifest 证明部署输入未被本地意外替换，**不能证明供应方 provenance**。

## Q&A

**Q：为什么 PNetLab 要使用 `cpu_type = host`？**  
A：嵌套 QEMU/KVM 需要 guest 看见 VMX/SVM。`host` CPU 模型与 pve2 已启用的 `kvm_intel nested=Y` 共同构成前提；部署后仍需在 guest 中验证 `/dev/kvm` 并运行最小 KVM smoke test。

**Q：为什么不用 pve0/pve1 的默认 `vmbr1` 和 `vmdata`？**  
A：pve2 是独立节点，现场管理桥为 `vmbr0`，可用池为 `mainpool`、`local`、`local-lvm`。复用集群默认值会把 VM 放到不存在或错误的存储/网络。

**Q：为什么初始不设置 `on_boot=true`？**  
A：PNetLab 首次安装会重写 guest 网络。先完成受控重启与静态网络验收，再单独决定开机自启，避免宿主重启后出现无法管理的 appliance。

**Q：为什么 Linux root 密码没有在安装后轮换？**  
A：操作者明确接受 installer 设置的本地弱密码。Ansible 仍禁用 root SSH、密码 SSH 和 keyboard-interactive，因此该风险限于 PVE 控制台/本地访问；PNetLab UI 与 MySQL 的默认凭据也尚未被声明为已安全轮换。后续若要改变这一决定，必须使用受支持的凭据轮换流程并重新验收。

**Q：安装器的几个 warning 是否都代表故障？**  
A：不全是。旧的 `pnet-console-mux` unit 因缺少 `telnetlib3` 被 mask，但当前 `pnet-telnet-bridge` 已在 8022 提供替代 console 服务，8023/8024/8025 的 shell/http/labstate bridge 也正常；无需启动旧 unit。AI/MCP 依赖是可选能力，未启用不影响 PNetLab 核心功能；image catalog 的 401 是未登录 API 的预期响应。安装器中针对旧 QEMU/版本的自检 warning 与当前 `qemu-system-x86` 10.2.1 组合不一致，按实际服务状态验收，不修改供应商脚本。

**Q：PNetLab 的 AI/MCP 功能是什么？**  
A：这是 PNetLab 的可选 AI Lab Builder/MCP 集成：通过 dashboard 启用后，为实验拓扑提供 MCP/HTTP 服务，并可接入 Anthropic/OpenAI 等 provider 执行 AI 辅助的拓扑构建或操作。它不是 PNetLab 核心 Web UI、设备 console、Docker 节点或网络桥接的依赖；未配置 provider 时保持禁用即可。
