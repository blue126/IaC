# Terraform Proxmox Disk & Cloud-Init 故障排查笔记

**日期**: 2025-12-04
**标签**: #Terraform #Proxmox #Cloud-Init #Ansible #Docker #Troubleshooting

## 背景
在实施 "Netbox -> Script -> Terraform" 的自动化流程时，我们遇到了严重的虚拟机故障。新创建的 VM 无法启动，现有的 VM 在变更配置后无法引导，且 Netbox 服务本身也因为重启策略缺失而中断。

## 核心问题与根因分析

### 1. Terraform Proxmox Provider 的 "毁灭性" 磁盘调整
**现象**:
Terraform 试图创建一个 8G 磁盘的 VM，但模板（Clone 源）的磁盘是 20G。
Terraform 执行计划显示：
```hcl
~ disk {
    - size = "20G" -> null
    + size = "8G"
    ...
}
```
**结果**:
Terraform **卸载 (Detach)** 了从模板克隆来的 20G 系统盘（将其标记为 `unused0`），然后**新建**了一个空的 8G 磁盘挂载到 `scsi0`。
因为新盘是空的，没有操作系统，VM 启动后直接进入 UEFI Shell 或黑屏，Cloud-Init 无法运行，QEMU Guest Agent 也无法启动。

**教训**:
*   **Proxmox 只能扩容，不能缩容**：你不能把一个 20G 的盘 "Resize" 成 8G。
*   **Terraform 的行为**：当请求大小 < 现有大小时，Terraform (telmate/proxmox) 会认为你需要一个"新盘"，从而触发 "Detach & Create" 逻辑，而不是报错。这是一个非常危险的行为。
*   **防御性编程**：在生成 Terraform 变量的脚本中，必须检查模板的原始大小，确保 `request_size >= template_size`。

### 2. Cloud-Init 与 QEMU Guest Agent 的依赖链
**现象**:
VM 启动了，但 Terraform 报错 `Error: 500 QEMU guest agent is not running`。
**根因**:
这是一个连锁反应：
1.  磁盘被错误替换为空盘 -> OS 丢失。
2.  OS 丢失 -> Cloud-Init 没法运行。
3.  Cloud-Init 没运行 -> `qemu-guest-agent` 包没被安装/启动（我们的模板依赖 Cloud-Init 动态安装 Agent）。
4.  Agent 没运行 -> Terraform 无法通过 Agent 配置网络或检测状态 -> 超时报错。

### 3. Docker Restart Policy (Ansible 配置漂移)
**现象**:
重启 Netbox VM 后，Netbox 服务没有自动拉起，导致 API 不通，自动化脚本失效。
**根因**:
`docker-compose.yml` 中缺失 `restart: unless-stopped` 或 `restart: always` 策略。
虽然我们在 Ansible Role 的 `tasks/main.yml` 中为 `netbox` 服务加了 override，但**漏掉了** `postgres` 和 `redis` 等基础服务。数据库没起，Netbox 主程序自然也起不来。

**教训**:
*   **全面性**：配置 Restart Policy 时必须覆盖所有依赖服务。
*   **Ansible 幂等性**：修改 Ansible 代码后，必须运行 Playbook 才能生效。手动在服务器上改文件（如 `docker compose up`）只是临时救火，重启后会失效。

### 4. Terraform Lifecycle & Boot Order
**现象**:
VM 经常出现引导顺序错误（试图从网络或光驱启动），或者 Terraform 反复提示 `unused_disk` 变更。
**解决方案**:
*   **显式指定引导顺序**：在 `main.tf` 中设置 `boot = "order=scsi0;ide2;net0"`，强制优先从系统盘启动。
*   **忽略无关变更**：使用 `lifecycle { ignore_changes = [unused_disk, efidisk] }`。Proxmox 在克隆或调整磁盘时经常产生残留的 `unused` 磁盘，或者 EFI 盘的属性漂移，忽略它们可以保持 Terraform 运行的稳定性。

### 5. 脚本中的单位换算陷阱
**现象**:
Terraform 试图创建一个 4TB (4096G) 的磁盘。
**根因**:
Netbox API 返回的 `disk` 字段单位是 **MB** (4096 MB)，但 Terraform 脚本直接把它当 **GB** 用了。
**教训**:
*   **API 对接**：永远要确认 API 返回值的单位（Bytes, MB, GB?）。

## 解决方案总结

1.  **修复脚本 (`fetch_planned_vms.py`)**:
    *   增加逻辑：SSH 到 Proxmox 查询模板的真实磁盘大小。
    *   增加逻辑：`final_size = max(netbox_size, template_size)`，防止缩容导致的磁盘替换。
    *   增加逻辑：`disk_size_gb = vm.disk / 1024`，修复单位错误。

2.  **修复 Terraform (`main.tf`)**:
    *   增加 `boot = "order=scsi0;ide2;net0"`。
    *   增加 `lifecycle` 规则忽略 `unused_disk`。

3.  **修复 Ansible (`deploy-netbox.yml`)**:
    *   在 `docker-compose.override.yml` 中为所有服务（包括 DB）添加 `restart: unless-stopped`。

### 6. Terraform ID Stability & Replacement Loops
**现象**:
当再次运行 Terraform Plan 时，已存在的 VM 显示 `forces replacement`（销毁重建），原因是 `vmid` 从 `102`（现有状态）变成了 `0`（配置值）。
**根因**:
Terraform 的 `proxmox_vm_qemu` 资源中，`vmid` 是一个强制属性。如果配置文件里的 `vmid` 与 State 中的不同，Terraform 会认为需要重建 VM。
**解决方案**:
采用 **"IP Last Octet = VMID"** 的约定。
在生成 Terraform 变量的脚本中加入逻辑：
1.  解析 Netbox 返回的 IP 地址（例如 `192.168.1.102`）。
2.  提取最后一段（`102`）作为 `vmid`。
这样不仅解决了 Terraform 的 ID 漂移问题，还让 VMID 变得有意义且易于管理（看到 IP 就知道 VMID）。

### 7. Handling Terraform Drift (Day 2 Ops)
**现象**:
在没有修改代码的情况下，Terraform Plan 仍然显示很多 "Changes"，例如 `tags: " " -> null`，`format: "raw" -> null`，或者 LXC 的 `description`（被 Ansible 修改过）。
**根因**:
*   **Provider 默认值**: Proxmox Provider 返回的某些字段默认值与 Terraform 预期的 `null` 不一致。
*   **外部修改**: Ansible 等工具修改了资源属性（如 Description），导致 Terraform 想要回滚这些变更。
**解决方案**:
*   **显式定义**: 在代码中显式定义 `format = "raw"`，使其与实际状态一致。
*   **忽略变更**: 使用 `lifecycle { ignore_changes = [tags, description] }` 忽略那些不影响基础设施状态的元数据变更。
**价值**:
保持 Plan 的 "干净" 至关重要。只有当 Plan 显示 "No changes" 时，我们才能确信基础设施处于收敛状态，才能放心地执行下一次变更。

## 结论
今天的故障是一次典型的 "集成地狱" (Integration Hell)。
Netbox（数据源）、Python 脚本（转换逻辑）、Terraform（执行引擎）、Proxmox（基础设施）、Ansible（配置管理）这五个环节中，任何一个环节的微小假设错误（如单位、默认行为、依赖关系）都会导致整个链条的崩塌。
**最宝贵的经验是：不要相信默认行为，显式定义一切（引导顺序、磁盘大小限制、重启策略、VMID 生成规则），并在自动化脚本中加入足够的校验逻辑。**
