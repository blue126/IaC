# Samba VM 部署总结

**日期**: 2025-11-26  
**目标**: 通过 IaC 自动化方式创建 Samba Server VM，为局域网提供文件共享服务

---

## 一、部署需求

- **主机名**: samba
- **IP 地址**: 192.168.1.102
- **资源配置**: 1 核 CPU / 512MB 内存
- **共享目录**: /root/samba
- **共享名称**: sambashare
- **访问方式**: 匿名访问（guest ok）
- **存储**: ZFS zvol（与 Immich VM 相同方式）

---

## 二、实施步骤

### 1. 创建 Inventory 配置
**文件**: `inventory/vms/samba.yml`

关键变量（最终版本，已标准化）：
- VM 基础配置：vmid, hostname, ip, netmask
- 资源分配：cores (1), memory (512)
- Samba 配置：samba_share_dir, samba_share_name, samba_guest_ok

注：Ansible 连接、cloud-init、网络配置等共同变量已提取到 `group_vars/application_vms.yml`

### 2. 创建 Samba 配置模板
**文件**: `templates/samba/smb.conf.j2`

配置要点：
- workgroup: WORKGROUP
- security: user + map to guest = Bad User（允许匿名访问）
- 共享段落：path, browseable, writable, guest ok, create mask 0777

### 3. 创建部署 Playbook
**文件**: `playbooks/deploy-samba.yml`

三段式架构：
- **Play 1 - Proxmox VM 创建**:
  - 克隆模板（vm_template_id: 9000，从 group_vars 读取）
  - 配置 CPU/内存（1核/512MB）
  - 配置 cloud-init 网络（静态 IP 192.168.1.102）
  - 配置 cloud-init 认证（vm_ciuser/vm_cipassword，从 group_vars 读取）
  - 挂载 cloud-init snippet
  - 启动 VM

- **Play 2 - 系统初始化**:
  - 等待 SSH 可达
  - 更新 apt 缓存
  - 安装 acl（Ansible become 依赖）

- **Play 3 - Samba 部署**:
  - 安装 samba 和 samba-common-bin
  - 创建共享目录 /root/samba（777 权限，nobody:nogroup）
  - 备份原始 smb.conf
  - 部署自定义 smb.conf
  - 启动并启用 smbd/nmbd 服务

### 4. cloud-init snippet 版本控制
**文件**: `files/cloud-init/ubuntu-password.yml`

将 Proxmox 上的 cloud-init snippet 拉取到代码库，便于版本管理和跨环境复用。

---

## 三、遇到的问题与解决

### 问题 1: 变量一致性（初步发现）
**现象**: 新创建的 samba.yml 使用了 `template_id` 字段，但 immich.yml 缺少此字段。

**原因**: 变量命名不统一，需要规范化。

**初步解决**: 
- 为 immich.yml 添加 `template_id: 9000`
- 修改 deploy-immich.yml，将 `{{ vm_template_id }}` 改为 `{{ template_id }}`，从 hostvars 读取

**最终解决**（重构后）:
- 将 `template_id` 统一为 `vm_template_id`，提取到 `group_vars/application_vms.yml`
- 所有 VM 配置变量标准化：vmid, hostname, cores, memory, ip, netmask
- 共同配置（认证、网络、模板）统一管理在 group_vars

### 问题 2: SSH 认证失败（用户名错误）
**现象**: 
```
fatal: [samba-node]: UNREACHABLE! => changed=false 
msg: root@192.168.1.102: Permission denied (publickey,password).
```

**原因**: inventory 缺少 Ansible SSH 连接变量（ansible_user, ansible_ssh_pass 等）。

**解决**: 参考 immich.yml，为 samba.yml 添加：
```yaml
ansible_user: ubuntu
ansible_ssh_pass: ubuntu
ansible_become_password: ubuntu
ansible_ssh_common_args: '-o PreferredAuthentications=password'
```

### 问题 3: SSH 认证失败（密码错误）
**现象**: 
```
Invalid/incorrect username/password. Skipping remaining 3 retries to prevent account lockout
```

**原因**: samba.yml 配置了 `ciuser: ciuser` 和 `cipassword: Admin123...`，但 cloud-init snippet 硬编码了 `ubuntu:ubuntu`，两者不匹配。

**根本原因**: cloud-init snippet 未版本控制，内容未知。

**解决**: 
1. 从 Proxmox 拉取 cloud-init snippet 内容：
   ```bash
   ansible pve0 -m shell -a "cat /var/lib/vz/snippets/ubuntu-password.yml"
   ```
2. 发现 snippet 硬编码 `ubuntu:ubuntu`
3. 将 samba.yml 的认证信息统一为 `ubuntu:ubuntu`（与 cloud-init 一致）
4. 将 snippet 内容保存到 `files/cloud-init/ubuntu-password.yml` 进行版本控制

**后续优化**（变量重构时）：
- 认证信息（ansible_user, ansible_ssh_pass, vm_ciuser, vm_cipassword）统一提取到 `group_vars/application_vms.yml`
- 所有应用 VM 共享相同认证配置，确保一致性

### 问题 4: SSH host key 冲突
**现象**: 
```
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

**原因**: 旧 VM 102 被删除重建，但 SSH known_hosts 保留了旧指纹。

**解决**: 
```bash
ssh-keygen -f '/home/will/.ssh/known_hosts' -R '192.168.1.102'
```

### 问题 5: Ansible 模板路径错误
**现象**: 
```
Could not find or access 'templates/samba/smb.conf.j2'
Searched in: /home/will/IaC/playbooks/templates/templates/samba/smb.conf.j2
```

**原因**: Ansible 从 playbook 所在目录（playbooks/）开始查找模板，但模板实际在项目根目录的 templates/。

**解决**: 修改 template 任务的 src 路径：
```yaml
src: ../templates/samba/smb.conf.j2  # 使用相对路径
```

### 问题 6: Windows 客户端无权限访问共享
**现象**: Windows 访问 `\\192.168.1.102\sambashare` 提示"没有权限"。

**原因**: 共享目录 /root/samba 虽设置 777 权限，但父目录 /root 默认权限 700，Samba guest 用户（nobody）无法遍历。

**解决**: 调整 /root 目录权限：
```bash
chmod 755 /root
```

**说明**: 
- /root 目录默认权限 700（drwx------），其他用户无法访问
- 即使子目录 /root/samba 是 777，Samba 匿名用户也无法到达
- 修改 /root 为 755（drwxr-xr-x），允许遍历但不允许写入
- 更优方案是将共享目录移到 /srv 或 /mnt 等公共路径

---

## 四、关键配置总结

### Samba 配置（smb.conf）
```ini
[global]
   workgroup = WORKGROUP
   security = user
   map to guest = Bad User    # 将无效用户映射为 guest

[sambashare]
   path = /root/samba
   browseable = yes
   writable = yes
   guest ok = yes             # 允许匿名访问
   create mask = 0777         # 新建文件权限
   directory mask = 0777      # 新建目录权限
```

### 目录权限
```bash
/root                  # 755 (drwxr-xr-x)  允许遍历
/root/samba            # 777 (drwxrwxrwx)  完全开放，nobody:nogroup
```

### Samba 服务
- smbd: SMB/CIFS 协议守护进程（端口 445/139）
- nmbd: NetBIOS 名称服务守护进程（端口 137/138）

---

## 五、验证结果

### 服务状态
```bash
● smbd.service - Samba SMB Daemon
   Active: active (running)
   Status: "smbd: ready to serve connections..."
```

### 端口监听
```bash
tcp    LISTEN   0.0.0.0:139    # NetBIOS Session Service
tcp    LISTEN   0.0.0.0:445    # Microsoft-DS (SMB over TCP)
```

### 共享目录
```bash
drwxrwxrwx 2 nobody nogroup 4096 /root/samba
```

### 客户端访问
- **Windows**: `\\192.168.1.102\sambashare`
- **Linux**: `smb://192.168.1.102/sambashare`
- **macOS**: `smb://192.168.1.102/sambashare`

无需用户名密码，匿名可读写。

---

## 六、文件清单

新增/修改的文件：
```
inventory/vms/samba.yml                    # Samba VM 配置（标准化变量命名）
inventory/group_vars/application_vms.yml   # 应用 VM 共同配置（新增）
playbooks/deploy-samba.yml                 # 部署 playbook（使用 group_vars）
templates/samba/smb.conf.j2                # Samba 配置模板
files/cloud-init/ubuntu-password.yml       # cloud-init snippet（版本控制）
```

修改的文件：
```
inventory/vms/immich.yml                   # 标准化变量命名（去除 immich_vm_* 前缀）
inventory/hosts.yml                        # 添加 application_vms 组定义
playbooks/deploy-immich.yml                # 更新变量引用，使用 group_vars
```

---

## 七、经验总结

### 最佳实践
1. **变量命名统一**: 所有 VM inventory 使用相同的变量名（vmid, hostname, cores, memory, ip, netmask）
2. **变量分层管理**: 共同配置提取到 group_vars，差异化配置保留在 host_vars
3. **认证信息对齐**: ansible_user 必须与 cloud-init ciuser 一致
4. **cloud-init 版本控制**: 将 Proxmox snippet 纳入代码库管理（files/cloud-init/），避免黑盒配置
5. **共享目录路径**: 避免使用 /root 等受限目录，推荐 /srv, /mnt, /data 等公共路径
6. **模板相对路径**: Ansible playbook 中使用 ../templates 相对路径引用根目录模板
7. **DRY 原则**: 消除重复配置，单一真实来源，提升可维护性

### 变量结构设计
**Host-specific (host_vars)**:
- VM 基础配置：`vmid`, `hostname`, `ip`, `cores`, `memory`, `netmask`
- 应用特定变量：`immich_app_dir`, `samba_share_dir` 等（保留前缀）

**Shared (group_vars/application_vms.yml)**:
- Ansible 连接：`ansible_user`, `ansible_ssh_pass`, `ansible_become_password`, `ansible_ssh_common_args`
- cloud-init：`vm_ciuser`, `vm_cipassword`, `vm_ssh_pwauth`
- 模板与存储：`vm_template_id`, `vm_storage_pool`
- 网络配置：`vm_gateway`, `vm_dns_servers`, `vm_netmask`

### 待改进
1. **敏感信息管理**: 密码目前明文存储，建议使用 Ansible Vault 加密
2. **共享目录位置**: 考虑迁移到 /srv/samba 等标准路径
3. **zvol 数据盘**: 当前只有系统盘，如需大容量存储，应添加独立数据盘 zvol 挂载
4. **SELinux/AppArmor**: 生产环境需考虑安全策略配置
5. **自动化测试**: 可增加 molecule 或自动化验证脚本

---

## 八、后续操作

### 变量重构（已完成）
为提升可维护性和一致性，已将共同配置提取到 group_vars：

**创建 `inventory/group_vars/application_vms.yml`**：
```yaml
# Ansible 连接配置
ansible_user: ubuntu
ansible_ssh_pass: ubuntu
ansible_become_password: ubuntu
ansible_ssh_common_args: '-o PreferredAuthentications=password'

# cloud-init 配置
vm_ciuser: ubuntu
vm_cipassword: ubuntu
vm_ssh_pwauth: true

# VM 模板与存储
vm_template_id: 9000
vm_storage_pool: vmdata

# 默认网络配置
vm_gateway: 192.168.1.1
vm_dns_servers:
  - 192.168.1.1
vm_netmask: 24
```

**统一变量命名**：
- samba.yml 和 immich.yml 都使用标准命名：`vmid`, `hostname`, `cores`, `memory`, `ip`, `netmask`
- 应用特定变量保留前缀：`immich_*`, `samba_*`
- playbook 变量引用已全部更新

**优势**：
- 消除重复配置（DRY 原则）
- 单一真实来源，易于维护
- 新增 VM 只需定义差异化配置
- 批量修改密码/DNS 等只需改一处

### 扩容存储（如需大容量）
```bash
# 创建数据盘 zvol
zfs create -V 500G vmdata/vm-102-disk-1

# 挂载到 VM
qm set 102 --scsi1 vmdata:vm-102-disk-1

# VM 内格式化并挂载
mkfs.ext4 /dev/sdb
mount /dev/sdb /srv/samba
```

### 调整共享路径
修改 samba.yml：
```yaml
samba_share_dir: /srv/samba  # 更标准的路径
```

重新运行 playbook 即可。

### 提交到 Git
```bash
git add .
git commit -m "Add Samba VM deployment and refactor variables

- Add Samba VM automated deployment with anonymous file sharing
- Create group_vars/application_vms.yml for shared VM configurations
- Standardize variable naming across all VM inventories (vmid, hostname, cores, memory, ip, netmask)
- Extract common configs (Ansible connection, cloud-init, network, template) to group_vars
- Update deploy-immich.yml and deploy-samba.yml to use standardized variables
- Add cloud-init snippet to version control (files/cloud-init/)
- Fix /root directory permissions for Samba guest access
- Complete documentation in SAMBA_VM_DEPLOYMENT.md"

git push origin master
```

---

**总结**: 通过 IaC 方式成功实现 Samba Server 自动化部署，复用了 Immich VM 的模板克隆、cloud-init 配置等机制。主要难点在认证配置对齐和权限调整，已全部解决并总结为最佳实践。
