# 下一步行动 - Story 1.2 测试

## 📋 当前状态

✅ **已完成**:
1. NetBox Webhook 配置 (ID: 2, 端口已修正为 8080)
2. NetBox Event Rule 配置 (ID: 1, NetBox 4.x 架构)
3. Jenkins 容器验证 (VMID 107, 正在运行)
4. Generic Webhook Trigger 插件验证 (已安装)
5. 测试 Jenkinsfile 创建 (`Jenkinsfile-webhook-router-test`)
6. 测试脚本创建 (`scripts/test-webhook-payload.sh`)
7. 配置指南文档 (`docs/jenkins-webhook-router-setup.md`)

---

## 🎯 下一步: 配置 Jenkins Pipeline Job

### Option A: 通过 Jenkins UI 配置 (推荐)

按照指南操作: `docs/jenkins-webhook-router-setup.md`

**快速步骤**:
1. 访问 http://192.168.1.107:8080
2. New Item → `Webhook-Router-Test` (Pipeline)
3. Pipeline from SCM → Git
4. Script Path: `Jenkinsfile-webhook-router-test`
5. Save

### Option B: 使用 Jenkins CLI (高级)

```bash
# 需要先下载 jenkins-cli.jar 并配置凭据
# 暂不推荐，UI 配置更直观
```

---

## 🧪 测试流程

### 1. 手动测试 (curl)

```bash
cd /workspaces/IaC

# 发送测试 webhook
bash scripts/test-webhook-payload.sh

# 预期: HTTP 200, Pipeline triggered
```

### 2. NetBox UI 测试

1. 登录 NetBox: http://192.168.1.104:8080/admin/
2. 创建测试 VM: `test-webhook-trigger-001`
3. 填充 Custom Fields (infrastructure_platform: proxmox)
4. 保存并观察 Jenkins Pipeline 自动触发

### 3. 验证结果

- [ ] Webhook 触发成功 (HTTP 200)
- [ ] Jenkins 日志显示正确的 Payload 解析
- [ ] `infrastructure_platform` 正确提取
- [ ] 路由决策逻辑正确 (打印 "Would trigger: Proxmox-Provisioning")
- [ ] 触发延迟 < 5 秒

---

## 📊 验收 Story 1.2

完成测试后，检查验收标准:

- [ ] Webhook 配置完成
- [ ] Event Rule 配置完成
- [ ] Pipeline Job 创建完成
- [ ] 端到端触发成功
- [ ] Payload 解析验证通过
- [ ] 触发延迟符合 NFR-P1 (< 5 秒)
- [ ] NetBox Event Rule 执行历史显示成功

**全部完成后**:
- 更新 `sprint-status.yaml`: `1.2 → done`
- 创建学习笔记 (NetBox 4.x 架构变化)
- 继续 Story 1.3 或 Story 2.1

---

## 🔄 后续 Story 预览

### Story 1.3: 在 NetBox 中创建虚拟机配置
- 创建至少 1 个生产 VM
- 配置所有 Custom Fields
- 验证 Webhook 自动触发

### Story 2.1: 创建 Jenkins Router Pipeline (生产版)
- 基于测试 Pipeline 创建生产版本
- 实现实际的 `build job:` 调用
- 触发 Proxmox-Provisioning Pipeline

### Story 3.3: Proxmox Provisioning Pipeline
- 从现有 Jenkinsfile 迁移逻辑
- 集成 NetBox API 读取配置
- 实现 Terraform 动态资源生成
- 状态回写到 NetBox

---

## 📁 关键文件

**新创建**:
- `/workspaces/IaC/Jenkinsfile-webhook-router-test`
- `/workspaces/IaC/docs/jenkins-webhook-router-setup.md`
- `/workspaces/IaC/scripts/test-webhook-payload.sh`
- `/workspaces/IaC/_bmad-output/implementation-artifacts/1-2-implementation-progress.md`

**现有重要文件**:
- `/workspaces/IaC/Jenkinsfile` (生产 Pipeline, 保持不变)
- `/workspaces/IaC/_bmad-output/planning-artifacts/architecture.md` (ADR-003)
- `/workspaces/IaC/_bmad-output/implementation-artifacts/sprint-status.yaml`

---

## ❓需要帮助？

如果遇到问题，参考:
- 配置指南: `docs/jenkins-webhook-router-setup.md` (故障排查章节)
- 实施进度: `_bmad-output/implementation-artifacts/1-2-implementation-progress.md`
- Story 文档: `_bmad-output/implementation-artifacts/1-2-配置-netbox-webhook-到-jenkins.md`

---

**Ready to test!** 🚀

按照 `docs/jenkins-webhook-router-setup.md` 配置 Jenkins Job，然后运行测试。
