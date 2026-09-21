# Terraform Infrastructure

This directory contains the Infrastructure as Code (IaC) definitions for the homelab environment.

## Directory Structure

*   **`proxmox/`**:  
    Contains the main configuration for Proxmox resources (VMs, LXC containers).  
    **This is the primary working directory.** All `terraform` commands (init, plan, apply) should be executed here.

*   **`modules/`**:  
    Reusable Terraform modules (e.g., `proxmox-vm`, `proxmox-lxc`). These are consumed by the configurations in `proxmox/`.

*   **`esxi/`**:  
    已退役。仅保留历史代码；默认inventory及仓库CI入口已停用。HCP `iac-esxi-lab` 于2026-09-21经授权备份后删除，cloud绑定已移除，详见 `esxi/README.md`。

*   **`oci/`**:  
    Configuration for Oracle Cloud Infrastructure.

## Known Gaps

* **PBS 已纳入 state，Proxmox workspace 已完成对账。** 2026-09-21完成PBS仅state导入、pbs/pve2 inventory新增和后续授权的默认值归一化。该更新触发旧provider的自动重启并造成服务中断，之后经用户授权停止/启动恢复；服务active、tank healthy、datastore挂载正常。最终完整plan返回0，无资源变更。详见任务规格中的执行与恢复记录；这不是无中断更新。

* **旧 provider 的重启行为。** bpg 0.70.0在agent、boot、keyboard等字段变化时会自行设置rebootRequired；`reboot=false`不是禁止自动重启的总开关。未来此类更新必须按维护操作审阅。

* **独立凭据。** pve2 使用 `vault_proxmox_api_token_id_pve2` / `vault_proxmox_api_token_secret_pve2`，由既有 bridge 生成变量；缺值会阻塞完整 workspace 的 plan，不能用集群 token 替代。pve2/PBS inventory 不设置共享 SSH 密码，需明确提供已批准的 SSH agent/key 或交互密码。未验证 SSH 登录，也未部署主机基线。

* **PCI 写入限制。** bpg 0.70.0 的原始 `hostpci.id` 文档注明不兼容 API token 写入、要求 root 用户密码。当前保留用户选择的 token 与三个原始直通地址；本次只读plan和仅导入state已成功，但不能由此推断PCI写入可用。后续认证或 PCI mapping 变更须单独决定。

* **外部清单未同步。** NetBox 当前仅准备 pve2 设备/网桥/IP 定义，没有 apply 或 live 对账；PBS 的 NetBox VM/IP/service 完整建模仍未覆盖。Homepage 独立 pve2 token 未配置时显示监控未配置，不复用集群凭据。

## How to Run

To apply changes to Proxmox resources:

1.  Navigate to the provider directory:
    ```bash
    cd proxmox
    ```
2.  Initialize Terraform (if not already done):
    ```bash
    terraform init
    ```
3.  Review pending changes:
    ```bash
    terraform plan
    ```
4.  Apply changes:
    ```bash
    terraform apply
    ```
