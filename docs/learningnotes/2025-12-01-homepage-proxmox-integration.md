# 学习笔记：Homepage Proxmox 集成配置指南 (2025-12-01)

## 1. 背景
在完成 Homepage 的 LXC 部署后，下一步是配置 Proxmox VE 的集成，以便在仪表板上显示 PVE 节点状态以及各个 VM/LXC 的资源使用情况。

## 2. 遇到的问题

### 2.1 "Invalid URL" 错误
*   **现象**: 在 `proxmox.yaml` 中配置 `host` 和 `port` 后，Homepage 日志报错 "Invalid URL"。
*   **原因**: Homepage 的 `proxmox.yaml` 配置需要完整的 URL (包含协议 `https://` 和端口)，而不仅仅是主机名。
*   **错误配置**:
    ```yaml
    pve0:
      host: 192.168.1.50
      port: 8006
    ```
*   **正确配置**:
    ```yaml
    pve0:
      url: https://192.168.1.50:8006
    ```

### 2.2 "API Error" 与认证方式
*   **现象**: 即使 URL 正确，服务或 Widget 显示 "API Error" 或 "Unknown"。
*   **原因**:
    1.  **认证方式**: 推荐使用 API Token (`token` + `secret`) 而非用户名密码。
    2.  **Key 匹配**: `proxmox.yaml` 中的 Key (如 `pve0`) 必须与 `services.yaml` 中的 `proxmoxNode` 值完全一致。
    3.  **Widget 配置**: 如果在 `services.yaml` 中使用 `widget` 块定义 Proxmox 节点，它可能不会自动继承 `proxmox.yaml` 的配置，需要显式指定或确保引用正确。

### 2.3 变量命名混乱
*   **现象**: Ansible Inventory 中使用了通用的 `proxmox_api_user`，导致在扩展多节点 (pve1, pve2) 时命名冲突或语义不清。
*   **解决**: 统一变量命名规范，使用 `proxmox_<node>_api_<type>` 格式，如 `proxmox_pve0_api_user`。

## 3. 正确配置总结

### 3.1 `proxmox.yaml` (Ansible Template)
```yaml
pve0:  # 节点名称，必须唯一且与 service 中引用一致
  url: https://192.168.1.50:8006
  token: {{ proxmox_pve0_api_user }}  # 格式: user@pam!tokenid
  secret: {{ proxmox_pve0_api_password }}
  insecure: true  # 如果没有有效证书

pve1:
  url: https://192.168.1.51:8006
  token: {{ proxmox_pve1_api_user }}
  secret: {{ proxmox_pve1_api_password }}
  insecure: true
```

### 3.2 `services.yaml` (Service Integration)
用于显示单个 VM 或 LXC 的状态。**注意**: 这种方式在卡片底部显示状态按钮，而非嵌入式图表。

```yaml
- MyService:
    ...
    proxmoxNode: pve0  # 对应 proxmox.yaml 中的 key
    proxmoxVMID: 100   # VM 或 LXC 的 ID
    proxmoxType: qemu  # qemu (VM) 或 lxc (容器)
```

### 3.3 `services.yaml` (Proxmox Node Widget)
用于显示整个 PVE 节点的资源使用情况 (CPU/RAM/Disk)。

```yaml
- Proxmox VE:
    ...
    widget:
      type: proxmox
      url: https://192.168.1.50:8006
      username: {{ proxmox_pve0_api_user }}
      password: {{ proxmox_pve0_api_password }}
      node: pve0
      insecure: true
```

## 4. 关键教训
1.  **文档阅读**: 仔细阅读官方文档关于 Configuration Key 的说明，特别是 `url` vs `host`，以及认证参数的名称。
2.  **变量规范**: 在 IaC (Infrastructure as Code) 中，变量命名应具有前瞻性，预留扩展空间 (如支持多节点)，避免后期重构。
3.  **服务 vs Widget**: 理解 Homepage 中 "Service Integration" (通过属性关联) 和 "Widget" (独立组件) 的区别。
