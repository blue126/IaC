# 🛠️ Homelab 可观测性部署方案 (LPG Stack) - IaC 版

**版本:** 2.0 (IaC Refactored)
**目标:** PVE 环境下的集中式监控 (Loki + Prometheus + Grafana)
**架构:** 
*   **服务端**: LXC 容器 + Docker Compose (Loki, Prometheus, Grafana)
*   **客户端**: Systemd Service (Promtail, Node Exporter)
**实施方式:** Terraform (基础设施) + Ansible (配置管理)

---

## 1️⃣ 第一阶段：基础设施 (Terraform)

### 目标
创建一个支持 Docker 运行的 LXC 容器。

### 实施细节
*   **文件**: `terraform/proxmox/monitoring.tf`
*   **资源**: `proxmox_lxc`
*   **关键配置**:
    *   `features`: `nesting=1`, `keyctl=1` (Docker 运行必须)
    *   `memory`: 建议 2GB+ (Loki 和 Java/Grafana 较吃内存)
    *   `disk`: 建议 20GB+ (日志存储)

---

## 2️⃣ 第二阶段：配置管理 (Ansible)

我们将创建三个新的 Ansible Roles 来自动化部署。

### 2.1 Role: `monitoring_server` (服务端)
*   **目标主机**: `monitoring` (LXC)
*   **任务**:
    1.  **安装 Docker**: 使用 `geerlingguy.docker` 或自写 task。
    2.  **创建目录**: `/opt/monitoring/{loki,prometheus,grafana}`。
    3.  **分发配置**:
        *   `docker-compose.yml.j2`: 定义服务编排。
        *   `prometheus.yml.j2`: **动态生成**，遍历 Ansible Inventory 自动添加所有主机为 targets。
        *   `loki-config.yml`: Loki 配置文件。
    4.  **启动服务**: `docker compose up -d`。
*   **变量**:
    *   `grafana_admin_password`: 使用 Ansible Vault 加密。

### 2.2 Role: `node_exporter` (客户端 - 指标)
*   **目标主机**: `all` (所有 PVE 节点, VM, LXC)
*   **任务**:
    1.  下载并解压 `node_exporter` 二进制文件。
    2.  创建 `node_exporter` 用户。
    3.  分发 Systemd Service 文件。
    4.  启动并开机自启。

### 2.3 Role: `promtail` (客户端 - 日志)
*   **目标主机**: `all`
*   **任务**:
    1.  下载并解压 `promtail` 二进制文件。
    2.  分发 `promtail-config.yml.j2`:
        *   **动态配置**: `clients.url` 指向 `monitoring` 主机的 IP。
        *   **标签**: 自动添加 `host={{ inventory_hostname }}` 标签。
    3.  分发 Systemd Service 文件。
    4.  启动并开机自启。

---

## 3️⃣ 第三阶段：整合与验证

### 3.1 Inventory 更新
*   在 `inventory/pve_lxc/monitoring.yml` 中定义监控主机。
*   确保所有受控节点都在 Inventory 中，以便 Prometheus 自动发现。

### 3.2 部署流程
```bash
# 1. 创建 LXC
terraform apply -target module.monitoring

# 2. 部署监控栈
ansible-playbook -i inventory playbooks/deploy-monitoring.yml
```

### 3.3 验证清单
*   [ ] **Grafana**: 访问 `http://<monitoring-ip>:3000`，能登录。
*   [ ] **Prometheus**: 在 Grafana Explore 中能查询到 `up` 指标，且所有节点状态为 1。
*   [ ] **Loki**: 在 Grafana Explore 中能查询到 `{host="..."}` 的日志。
*   [ ] **Homepage**: 将 Grafana 仪表盘集成到 Homepage。