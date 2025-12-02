# Ubuntu Template 更新指南：添加 QEMU Guest Agent

## 背景
QEMU Guest Agent 是 Proxmox 与虚拟机通信的关键组件，应该在模板中预装，而不是在每个 VM 部署时安装。

## 操作步骤

### 方法一：更新现有模板（推荐）

1. **转换模板为 VM**
   ```bash
   # 在 Proxmox 节点上执行
   qm template <TEMPLATE_ID> --revert
   ```

2. **启动 VM 并登录**
   ```bash
   qm start <TEMPLATE_ID>
   # 通过 Web Console 或 SSH 登录
   ```

3. **安装 qemu-guest-agent**
   ```bash
   sudo apt update
   sudo apt install -y qemu-guest-agent
   sudo systemctl enable qemu-guest-agent
   sudo systemctl start qemu-guest-agent
   ```

4. **清理并关闭**
   ```bash
   # 清理日志和临时文件
   sudo cloud-init clean
   sudo rm -rf /var/lib/cloud/instances/*
   sudo truncate -s 0 /etc/machine-id
   sudo rm /var/lib/dbus/machine-id
   sudo ln -s /etc/machine-id /var/lib/dbus/machine-id
   
   # 清理历史
   history -c
   sudo poweroff
   ```

5. **转换回模板**
   ```bash
   qm template <TEMPLATE_ID>
   ```

### 方法二：使用 Cloud-Init 安装（临时方案）

如果暂时无法更新模板，可以在 cloud-init snippet 中添加：

```yaml
#cloud-config
packages:
  - qemu-guest-agent

runcmd:
  - systemctl enable qemu-guest-agent
  - systemctl start qemu-guest-agent
```

## 验证

创建新 VM 后，检查 agent 状态：
```bash
# 在 VM 内
systemctl status qemu-guest-agent

# 在 Proxmox 节点上
qm agent <VMID> ping
```

## 后续清理

模板更新后，可以从各个 Ansible role 中移除 qemu-guest-agent 的安装步骤。
