# Jenkins Webhook Router Pipeline 配置指南

**Story**: 1.2 配置 NetBox Webhook 到 Jenkins  
**Pipeline**: Webhook-Router-Test (测试用)  
**目标**: 验证 NetBox Webhook 触发和 Payload 解析

---

## 前置条件

- ✅ Jenkins 已部署 (http://192.168.1.107:8080)
- ✅ Generic Webhook Trigger 插件已安装
- ✅ NetBox Webhook 已配置 (Webhook ID: 2)
- ✅ NetBox Event Rule 已配置 (Event Rule ID: 1)
- ✅ Git 仓库包含 `Jenkinsfile-webhook-router-test`

---

## Step 1: 在 Jenkins 创建 Pipeline Job

### 1.1 登录 Jenkins

```bash
# 访问 Jenkins UI
open http://192.168.1.107:8080

# 或使用 SSH 端口转发（如果从外部访问）
ssh -L 8080:192.168.1.107:8080 your-jump-host
```

### 1.2 创建新 Pipeline

1. 点击 **New Item** (左侧菜单)
2. 输入名称: `Webhook-Router-Test`
3. 选择类型: **Pipeline**
4. 点击 **OK**

---

## Step 2: 配置 Pipeline

### 2.1 General 配置

- **Description** (可选):
  ```
  Test Router Pipeline for NetBox Webhook Integration (Story 1.2)
  Validates webhook trigger, payload parsing, and routing logic.
  Does NOT execute actual deployments.
  ```

- **Discard old builds**:
  - ✅ 勾选
  - Strategy: Log Rotation
  - Max # of builds to keep: `20`

### 2.2 Pipeline 配置

**Definition**: `Pipeline script from SCM`

**SCM**: `Git`

**Repository URL**: 填写你的 IaC 仓库 URL
```
例如: https://github.com/your-username/IaC.git
或: git@github.com:your-username/IaC.git
```

**Credentials** (如果是私有仓库):
- 点击 **Add** → **Jenkins**
- Kind: SSH Username with private key 或 Username with password
- 保存后选择对应凭据

**Branches to build**:
- Branch Specifier: `*/main` (或你的工作分支)

**Script Path**:
```
Jenkinsfile-webhook-router-test
```

### 2.3 保存配置

点击 **Save** 保存配置

---

## Step 3: 验证配置

### 3.1 测试 Git 拉取

1. 进入 Job 页面: `http://192.168.1.107:8080/job/Webhook-Router-Test/`
2. 点击 **Build Now** (手动触发一次)
3. 观察 Console Output:
   - ✅ Git clone 成功
   - ✅ 找到 `Jenkinsfile-webhook-router-test`
   - ⚠️  可能因为没有 webhook payload 而失败（正常）

### 3.2 检查 Webhook Trigger 配置

1. 进入 Job 配置: 点击 **Configure**
2. 滚动到 **Build Triggers** 部分
3. 应该看到 **Generic Webhook Trigger** (由 Jenkinsfile 自动配置)
   - Token: `netbox-webhook`
   - Variable extractions: 定义了多个 JSONPath 变量

**注意**: Generic Webhook Trigger 配置在 **Jenkinsfile 中定义**，不在 UI 中配置

---

## Step 4: 测试 Webhook 触发

### 4.1 使用测试脚本触发

```bash
cd /workspaces/IaC

# 运行 webhook 测试脚本
bash scripts/jenkins/test-webhook-payload.sh
```

**预期输出**:
```
HTTP Status Code: 200
✅ SUCCESS: Webhook triggered successfully
   Jenkins should have started a Pipeline build
   Check: http://192.168.1.107:8080/job/Webhook-Router-Test/
```

### 4.2 在 Jenkins 查看执行结果

1. 访问: http://192.168.1.107:8080/job/Webhook-Router-Test/
2. 确认最新构建已触发 (Build #1, #2, ...)
3. 点击构建号 → **Console Output**

**预期日志**:
```
==========================================
      NetBox Webhook Triggered           
==========================================
Event Type     : object_created
Model          : virtualmachine
Object ID      : 999
Object Name    : test-webhook-vm
Object Status  : planned
Triggered By   : admin
Request ID     : test-webhook-xxxxxxxxxx
==========================================

Custom Fields (Story 1.1):
  infrastructure_platform: proxmox
  automation_level       : requires_approval
  proxmox_node           : pve0
  proxmox_vmid           : 201
  ansible_groups         : ["pve_lxc", "tailscale"]
  playbook_name          : N/A
==========================================

✅ Payload validation passed
   All required fields are present

==========================================
      Router Decision Logic               
==========================================
Platform        : proxmox
Automation Level: requires_approval
Event Type      : object_created

🔀 Route Target: Proxmox-Provisioning Pipeline
   Description: Terraform Proxmox VM/LXC provisioning + Ansible deployment
   Next Step  : Would trigger job 'Proxmox-Provisioning'
   Parameters :
     - NETBOX_VM_ID      : 999
     - AUTOMATION_LEVEL  : requires_approval
     - PROXMOX_NODE      : pve0
     - PROXMOX_VMID      : 201

ℹ️  Automation Level: requires_approval
   → In production, Terraform Apply would PAUSE for manual approval
==========================================

✅ Webhook Router Test completed successfully
```

---

## Step 5: 测量触发延迟

### 5.1 记录时间戳

```bash
# 记录发送时间
START=$(date +%s)

# 发送 webhook
bash scripts/jenkins/test-webhook-payload.sh

# 获取 Jenkins 构建开始时间 (需要 jq)
BUILD_START=$(curl -s http://192.168.1.107:8080/job/Webhook-Router-Test/lastBuild/api/json | jq '.timestamp / 1000')

# 计算延迟
LATENCY=$((BUILD_START - START))
echo "Webhook Trigger Latency: ${LATENCY} seconds"
```

**验收标准**: NFR-P1 要求延迟 < 5 秒

---

## Step 6: 测试 NetBox UI 实际触发

### 6.1 在 NetBox 创建测试 VM

1. 登录 NetBox: http://192.168.1.104:8080/admin/
2. 导航: **Virtualization** → **Virtual Machines** → **Add**
3. 填写配置:
   - **Name**: `test-webhook-trigger-001`
   - **Status**: `Planned`
   - **Cluster**: 选择 Proxmox Cluster
   - **vCPUs**: `1`
   - **Memory (MB)**: `512`
   - **Disk (GB)**: `8`

4. 填写 Custom Fields (Story 1.1):
   - **infrastructure_platform**: `proxmox`
   - **automation_level**: `requires_approval`
   - **proxmox_node**: `pve0`
   - **proxmox_vmid**: `300` (选一个未使用的 ID)

5. 点击 **Create**

### 6.2 观察 Jenkins Pipeline 触发

1. **立即切换到 Jenkins UI**:
   - http://192.168.1.107:8080/job/Webhook-Router-Test/

2. **确认构建自动触发**:
   - 应该在 5 秒内看到新构建 (Build #N)

3. **查看 Console Output**:
   - 确认 `netbox_object_name` 是 `test-webhook-trigger-001`
   - 确认 `infrastructure_platform` 是 `proxmox`

### 6.3 查看 NetBox Event Rule 执行历史

1. 在 NetBox UI，导航: **System** → **Event Rules**
2. 点击 **Trigger Jenkins on VM/Device Create/Update**
3. 在详情页底部查看执行历史
4. 确认最新触发显示:
   - ✅ HTTP Status: 200
   - ✅ Response Time: < 2 秒
   - ✅ Timestamp: 刚才创建 VM 的时间

---

## 故障排查

### 问题 1: Webhook 返回 403 Forbidden

**原因**: 没有配置对应 token 的 Pipeline Job

**解决**:
1. 确认 Jenkins Job 名称是 `Webhook-Router-Test`
2. 确认 Job 已保存并运行过至少一次 (Build Now)
3. 确认 Jenkinsfile 中 `token: 'netbox-webhook'` 配置正确

### 问题 2: Webhook 返回 404 Not Found

**原因**: Generic Webhook Trigger 插件未安装

**解决**:
```
Jenkins → Manage Jenkins → Manage Plugins → Available
搜索: Generic Webhook Trigger
安装插件并重启 Jenkins
```

### 问题 3: Pipeline 失败 - "Missing custom_fields.xxx"

**原因**: NetBox Payload 不包含 Custom Fields

**解决**:
1. 确认 Story 1.1 的 Custom Fields 已创建
2. 在 NetBox VM 编辑页面，确认 Custom Fields 有值
3. 重新保存 VM 触发 Webhook

### 问题 4: Git clone 失败

**原因**: Jenkins 无法访问 Git 仓库

**解决**:
- 检查仓库 URL 是否正确
- 检查 SSH 密钥或用户名密码凭据
- 测试 Jenkins 服务器网络连通性:
  ```bash
  ssh root@192.168.1.107
  git ls-remote <your-repo-url>
  ```

### 问题 5: 触发延迟 > 5 秒

**可能原因**:
- Jenkins 负载过高
- Git clone 慢（仓库过大）
- 网络延迟

**优化建议**:
- 使用 Lightweight Checkout (Git Plugin 选项)
- 增加 Jenkins agent 资源
- 检查网络质量

---

## 验收标准检查清单

### Story 1.2 完成标准

- [ ] Jenkins Generic Webhook Trigger Plugin 已安装
- [ ] NetBox Webhook 配置成功 (ID: 2, URL 使用端口 8080)
- [ ] NetBox Event Rule 配置成功 (ID: 1)
- [ ] Jenkins Pipeline Job `Webhook-Router-Test` 创建完成
- [ ] Webhook 触发测试成功 (HTTP 200)
- [ ] Pipeline 日志显示正确的 Payload 解析
- [ ] 触发延迟 < 5 秒 (NFR-P1)
- [ ] NetBox UI 创建 VM 能够自动触发 Pipeline
- [ ] Event Rule 执行历史显示成功交付

---

## 下一步: Story 2.1

完成 Story 1.2 后，继续开发 **生产 Router Pipeline** (Story 2.1):

1. 创建 `Jenkinsfile-webhook-router` (生产版本)
2. 添加实际的 `build job:` 调用
3. 实现平台类型验证和错误处理
4. 配置失败通知机制

---

## 相关文档

- **Story 文档**: `/workspaces/IaC/_bmad-output/implementation-artifacts/1-2-配置-netbox-webhook-到-jenkins.md`
- **实施进度**: `/workspaces/IaC/_bmad-output/implementation-artifacts/1-2-implementation-progress.md`
- **Custom Fields 参考**: `/workspaces/IaC/docs/netbox-custom-fields-reference.md`
- **测试脚本**: `/workspaces/IaC/scripts/jenkins/test-webhook-payload.sh`

---

**最后更新**: 2026-02-09  
**版本**: 1.0
