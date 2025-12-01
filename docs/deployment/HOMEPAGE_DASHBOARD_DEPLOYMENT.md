# Homepage Dashboard 部署指南

**日期**: 2025-12-01  
**目标**: 通过 IaC 自动化方式在 Proxmox LXC 中部署 Homepage dashboard,提供统一的服务仪表板

---

## 一、部署需求

- **主机名**: homepage
- **IP 地址**: 192.168.1.103
- **资源配置**: 2 核 CPU / 4GB 内存 / 2GB Swap
- **存储**: 4GB rootfs
- **服务端口**: 3000
- **访问方式**: HTTP (http://192.168.1.103:3000)
- **安装方式**: pnpm 源代码构建

---

## 二、实施步骤

### 1. Terraform 创建 LXC 容器
**文件**: `terraform/proxmox/homepage.tf`

```hcl
module "homepage" {
  source = "../modules/proxmox-lxc"
  
  lxc_name       = "homepage"
  target_node    = "pve0"
  vmid           = 103
  ostemplate     = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
  cores          = 2      # 构建需要
  memory         = 4096   # 4GB - Next.js 构建必需
  swap           = 2048
  rootfs_storage = "msinvme1tpool"
  rootfs_size    = "4G"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.103/24"
  gateway        = "192.168.1.1"
  unprivileged   = true
  features       = ["nesting=1"]
  ostype         = "debian"
  
  sshkeys        = var.sshkeys
}

output "homepage_ip" {
  value = module.homepage.lxc_ip
}
```

**执行**:
```bash
cd terraform/proxmox
terraform plan
terraform apply
```

**重要**: 内存必须设置为 4GB,低于此值会导致 `pnpm build` 过程卡死。

### 2. 创建 Ansible Inventory
**文件**: `ansible/inventory/pve-lxc/homepage.yml`

```yaml
---
homepage:
  hosts:
    homepage-node:
      ansible_host: 192.168.1.103
      # Homepage dashboard configuration
      homepage_port: 3000
```

**文件**: `ansible/inventory/hosts.yml` (更新)

在 `pve_lxc` 组下添加:
```yaml
pve_lxc:
  children:
    anki:
    homepage:  # 新增
```

### 3. 创建 Ansible Role
**目录结构**:
```
ansible/roles/homepage/
├── defaults/main.yml      # 默认变量
├── tasks/main.yml         # 安装任务
├── templates/
│   └── homepage.service.j2  # systemd 服务
└── handlers/main.yml      # 服务重启处理器
```

#### defaults/main.yml
```yaml
---
homepage_version: "main"
homepage_install_dir: /opt/homepage
homepage_user: homepage
homepage_group: homepage
homepage_port: 3000
homepage_allowed_hosts: "{{ ansible_host }}:{{ homepage_port }}"
nodejs_version: "18"
```

#### tasks/main.yml (关键步骤)
```yaml
---
# 1. 安装 Node.js
- name: Add NodeSource repository
  # ... NodeSource 仓库配置

- name: Install Node.js
  apt:
    name: nodejs
    state: present

# 2. 安装 pnpm
- name: Install pnpm globally
  command: npm install -g pnpm

# 3. 创建用户
- name: Create homepage system user
  user:
    name: "{{ homepage_user }}"
    system: yes

# 4. 克隆源代码
- name: Clone Homepage repository
  shell: git clone https://github.com/gethomepage/homepage.git {{ homepage_install_dir }}
  when: not git_repo.stat.exists

# 5. 设置权限
- name: Set ownership
  file:
    path: "{{ homepage_install_dir }}"
    owner: "{{ homepage_user }}"
    group: "{{ homepage_group }}"
    recurse: yes

# 6. 安装依赖
- name: Install dependencies
  command: pnpm install
  args:
    chdir: "{{ homepage_install_dir }}"
  become_user: "{{ homepage_user }}"

# 7. 构建应用 (最耗时的步骤)
- name: Build Homepage
  command: pnpm build
  args:
    chdir: "{{ homepage_install_dir }}"
  become_user: "{{ homepage_user }}"

# 8. 部署 systemd 服务
- name: Deploy systemd service
  template:
    src: homepage.service.j2
    dest: /etc/systemd/system/homepage.service

# 9. 启动服务
- name: Enable and start service
  systemd:
    name: homepage
    enabled: yes
    state: started
    daemon_reload: yes
```

#### templates/homepage.service.j2
```ini
[Unit]
Description=Homepage Dashboard
After=network.target

[Service]
Type=simple
User={{ homepage_user }}
Group={{ homepage_group }}
WorkingDirectory={{ homepage_install_dir }}
Environment="HOMEPAGE_ALLOWED_HOSTS={{ homepage_allowed_hosts }}"
Environment="NODE_ENV=production"
ExecStart=/usr/bin/pnpm start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 4. 创建部署 Playbook
**文件**: `ansible/playbooks/deploy-homepage.yml`

```yaml
---
# Deploy Homepage dashboard
- name: Deploy Homepage
  hosts: homepage
  roles:
    - homepage
  
  post_tasks:
    - name: Verify Homepage is running
      uri:
        url: "http://{{ ansible_host }}:{{ homepage_port }}"
        status_code: 200
      register: homepage_status
    
    - name: Display deployment summary
      debug:
        msg:
          - "Homepage deployment completed successfully!"
          - "Access URL: http://{{ ansible_host }}:{{ homepage_port }}"
          - "Installation directory: /opt/homepage"
```

**执行**:
```bash
cd ansible
ansible-playbook playbooks/deploy-homepage.yml
```

**预计耗时**: 约15-20分钟 (主要是 pnpm build 步骤)

---

## 三、遇到的问题与解决

### 问题 1: 部署卡死在 Build 步骤
**现象**: `pnpm build` 任务执行后无任何输出,等待 15+ 分钟无响应。

**诊断**:
```bash
# 在 Proxmox UI 中查看容器 → 内存使用率 100%
# 或通过命令:
pct exec 103 -- free -h
```

**原因**: 初始配置 1GB 内存不足以支持 Next.js 构建过程。

**解决**: 
1. 取消正在运行的 playbook (Ctrl+C)
2. 修改 `terraform/proxmox/homepage.tf`:
   ```hcl
   memory = 4096  # 从 1024 改为 4096
   cores  = 2     # 从 1 改为 2
   ```
3. 应用更改: `terraform apply`
4. 重启容器: `ansible homepage -m shell -a "reboot"`
5. 重新运行部署

### 问题 2: sudo: not found
**现象**:
```
MODULE FAILURE: /bin/sh: 1: sudo: not found
```

**原因**: Debian LXC 最小化安装不包含 sudo。

**解决**: 
- 移除 playbook 中的 `become: yes` (LXC 已经使用 root 登录)
- 或安装 sudo: `ansible homepage -m apt -a "name=sudo state=present"`

### 问题 3: Git ownership error
**现象**:
```
fatal: detected dubious ownership in repository at '/opt/homepage'
```

**原因**: Git 安全检查,目录所有者与操作用户不匹配。

**解决**: 
采用两步法:
1. 以 root 克隆仓库
2. 然后 `chown` 给 homepage 用户

```yaml
- name: Clone as root
  shell: git clone ...

- name: Fix ownership
  file:
    path: /opt/homepage
    owner: homepage
    recurse: yes
```

### 问题 4: SSH host key 变化
**现象**: 重新创建容器后 SSH 连接被拒绝。

**解决**:
```bash
ssh-keygen -f '/home/will/.ssh/known_hosts' -R '192.168.1.103'
```

---

## 四、关键配置总结

### 资源配置
```
CPU:    2 核
内存:   4GB (构建必需)
Swap:   2GB
存储:   4GB
```

**重要**: 内存不能低于 4GB,否则 Next.js 构建会失败或卡死。

### 服务管理
```bash
# 查看状态
systemctl status homepage

# 查看日志
journalctl -u homepage -f

# 重启服务
systemctl restart homepage
```

### 端口
- **3000**: Homepage HTTP 服务

---

## 五、验证结果

### 服务状态
```bash
● homepage.service - Homepage Dashboard
   Active: active (running)
   Memory: 141.1M
   Main PID: 3310
```

### HTTP 测试
```bash
curl -I http://192.168.1.103:3000
# HTTP/1.1 200 OK
```

### 访问地址
- **浏览器访问**: http://192.168.1.103:3000
- **功能**: 仪表板配置界面

---

## 六、文件清单

新增文件:
```
terraform/proxmox/homepage.tf                  # LXC 创建配置
ansible/inventory/pve-lxc/homepage.yml         # Inventory 配置
ansible/roles/homepage/defaults/main.yml       # 默认变量
ansible/roles/homepage/tasks/main.yml          # 安装任务
ansible/roles/homepage/templates/homepage.service.j2  # systemd 服务
ansible/roles/homepage/handlers/main.yml       # 处理器
ansible/playbooks/deploy-homepage.yml          # 部署 playbook
```

修改文件:
```
ansible/inventory/hosts.yml                    # 添加 homepage 到 pve_lxc 组
```

---

## 七、配置 Homepage

### 1. 配置文件位置
```
/opt/homepage/config/
├── settings.yaml    # 全局设置
├── services.yaml    # 服务配置
├── widgets.yaml     # 小组件
└── bookmarks.yaml   # 书签
```

### 2. 添加服务示例

编辑 `/opt/homepage/config/services.yaml`:
```yaml
- Infrastructure:
    - Proxmox:
        icon: proxmox.png
        href: https://192.168.1.10:8006
        description: Proxmox VE 管理界面

    - Netbox:
        icon: netbox.png
        href: http://192.168.1.104:8000
        description: 基础设施管理

- Applications:
    - Immich:
        icon: immich.png
        href: http://192.168.1.101:2283
        description: 照片管理

    - Samba:
        icon: samba.png
        href: smb://192.168.1.102/sambashare
        description: 文件共享

    - Anki Sync:
        icon: anki.png
        href: http://192.168.1.100:8080
        description: Anki 同步服务器
```

### 3. 重启服务使配置生效
```bash
ansible homepage -m shell -a "systemctl restart homepage"
```

---

## 八、最佳实践

### 1. 资源规划
- **构建时**: 4GB RAM, 2 CPU
- **运行时**: 可考虑降低到 1GB RAM, 1 CPU (需通过 Terraform 调整)
- **建议**: 保持 4GB,以备将来重新构建

### 2. 备份策略
重要目录:
```
/opt/homepage/config/  # 配置文件
/opt/homepage/.next/   # 构建产物 (可重建)
```

备份命令:
```bash
ansible homepage -m archive -a "path=/opt/homepage/config dest=/tmp/homepage-config.tar.gz"
```

### 3. 更新流程
```bash
# 1. 更新代码
ansible homepage -m shell -a "cd /opt/homepage && git pull"

# 2. 重新构建
ansible homepage -m shell -a "cd /opt/homepage && pnpm install && pnpm build" -u homepage

# 3. 重启服务
ansible homepage -m shell -a "systemctl restart homepage"
```

### 4. 安全考虑
当前配置为 homelab 内网使用,生产环境建议:
- 添加反向代理 (Nginx/Traefik)
- 启用 HTTPS
- 配置身份认证
- 限制访问 IP 范围

---

## 九、故障排查

### 服务无法启动
```bash
# 查看详细日志
journalctl -u homepage -xe

# 检查配置文件
cd /opt/homepage && pnpm start
```

### 构建失败
```bash
# 检查内存
free -h

# 检查磁盘空间
df -h

# 清理重新构建
cd /opt/homepage
rm -rf .next node_modules
pnpm install
pnpm build
```

### 无法访问
```bash
# 检查端口监听
ss -tlnp | grep 3000

# 检查防火墙 (通常 LXC 无防火墙)
iptables -L -n
```

---

## 十、后续操作

### 集成到 NetBox
```bash
# 添加 LXC 到 NetBox inventory
# 创建设备记录
# 关联 IP 地址和服务
```

### 配置反向代理 (可选)
使用 Nginx 提供 HTTPS 访问:
```nginx
server {
    listen 443 ssl;
    server_name dashboard.local;
    
    location / {
        proxy_pass http://192.168.1.103:3000;
        proxy_set_header Host $host;
    }
}
```

### 提交到 Git
```bash
git add .
git commit -m "Add Homepage dashboard deployment

- Create LXC container via Terraform (103, 192.168.1.103)
- Deploy Homepage from source using pnpm
- Configure systemd service for auto-start
- Set memory to 4GB for Next.js builds
- Add to pve-lxc inventory group"

git push origin master
```

---

## 十一、参考资料

- [Homepage 官方文档](https://gethomepage.dev/)
- [Homepage 源代码安装](https://gethomepage.dev/installation/source/)
- [pnpm 文档](https://pnpm.io/)
- Learning Notes: `docs/learningnotes/2025-12-01-homepage-lxc-deployment.md`
