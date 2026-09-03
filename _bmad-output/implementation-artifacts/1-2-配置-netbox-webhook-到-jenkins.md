# Story 1-2: 配置 NetBox Webhook 到 Jenkins

**Epic**: Epic 1 - NetBox 数据建模与配置  
**Story ID**: 1.2  
**优先级**: 🔴 Critical  
**预估工作量**: 1.5-2 小时  
**依赖**: Story 1.1 (Custom Fields 已创建)  
**状态**: Ready for Dev

---

## Story Overview

### 用户故事
作为 DevOps Engineer (Will)，我需要配置 NetBox Webhook 自动触发 Jenkins Pipeline，这样当我在 NetBox 中创建或修改虚拟机时，系统能够自动感知并启动自动化流程，实现事件驱动的基础设施自动化。

### 业务价值
- ✅ **实现事件驱动架构**: Webhook 是 NetBox SSOT 到自动化流程的桥梁
- ✅ **即时响应用户操作**: 从 NetBox UI 点击 "Create" 到 Pipeline 启动 < 5 秒 (NFR-P1)
- ✅ **降低人工干预**: 无需手动触发 Pipeline，减少操作失误
- ✅ **奠定自动化基础**: 为后续 Router Pipeline 和 Provisioning Pipeline 提供触发机制

### 技术目标
1. 在 NetBox Admin UI 中配置 Webhook 指向 Jenkins Generic Webhook Trigger
2. 验证内网连通性 (NetBox → Jenkins 直连，无需 Cloudflare Tunnel)
3. 测试 Webhook 触发延迟和可靠性
4. 配置 Webhook 事件过滤 (仅 `created` 和 `updated` 事件)
5. 验证 Webhook Payload 包含所有必要字段

---

## Requirements (来自 Epics)

### 功能性需求
- **FR25**: System 可以接收 NetBox Webhook 事件并触发 Jenkins Pipeline
- **FR8**: System 可以识别 NetBox 中配置变更并触发相应的自动化流程

### 非功能性需求
- **NFR-P1**: NetBox Webhook 触发到 Jenkins Pipeline 启动的延迟 < 5 秒
- **NFR-R1**: Webhook 触发成功率 > 95% (MVP 阶段目标 > 80%)
- **NFR-S4**: NetBox Webhook 到 Jenkins 的通信使用 HTTP (内网直连) 或 HTTPS (外网通过 Cloudflare Tunnel)
- **NFR-R7**: Webhook 触发失败时，必须提供手动触发兜底机制

### Acceptance Criteria (验收标准)
- [ ] Jenkins Generic Webhook Trigger Plugin 已安装并配置
- [ ] NetBox Webhook 配置成功创建:
  - Name: "Jenkins Infrastructure Automation"
  - URL: `http://192.168.1.107:8090/generic-webhook-trigger/invoke?token=netbox-webhook`
  - HTTP Method: POST
  - Content types: `dcim.virtualmachine`, `dcim.device`
  - Events: `created`, `updated`
  - Enabled: true
- [ ] 内网连通性测试成功 (curl 命令返回 HTTP 200)
- [ ] Webhook 触发延迟 < 5 秒 (NFR-P1)
- [ ] 可以在 NetBox UI 查看 Webhook 执行历史
- [ ] 失败的 Webhook 请求显示错误信息
- [ ] Webhook Payload 验证包含所有必要字段 (custom_fields, id, name, status)

---

## Technical Design

### 架构上下文 (来自 ADR-003)

**决策**: Webhook + Git 混合模式

**网络拓扑**:
```
内网 (192.168.1.0/24)
├── NetBox (192.168.1.104:8080)
│   └── Webhook: http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook
├── Jenkins (192.168.1.107:8080)
│   ├── 内网访问: http://192.168.1.107:8080
│   └── 外部访问: https://jenkins.willfan.me (via Cloudflare Tunnel)
└── Proxmox Cluster (pve0/pve1/pve2)
```

**关键设计决策**:
- ✅ **内网直连**: NetBox 直接访问 Jenkins 内网地址，延迟 < 1 秒，优于外部 Webhook
- ✅ **HTTP 即可**: 内网通信使用 HTTP 协议，无需 TLS 开销 (外部访问 Jenkins 才需要 HTTPS)
- ✅ **Token 认证**: 通过 URL 参数 `?token=netbox-webhook` 进行简单认证 (避免被误触发)

### Webhook 配置规范

#### NetBox Webhook 配置

| 属性 | 值 | 说明 |
|------|-----|------|
| **Name** | `Jenkins Infrastructure Automation` | 描述性名称，便于识别 |
| **Payload URL** | `http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook` | Jenkins Generic Webhook Trigger 端点 |
| **HTTP Method** | `POST` | 标准 Webhook 方法 |
| **HTTP Content Type** | `application/json` | JSON 格式 Payload |
| **Additional Headers** | 无 (可选) | 如果需要额外认证可添加 `X-Custom-Token: xxx` |
| **Body Template** | 默认 (NetBox 标准 Payload) | 包含 `event`, `timestamp`, `model`, `username`, `request_id`, `data` |
| **SSL Verification** | ❌ 不启用 | 内网 HTTP 通信无需 SSL |
| **CA File Path** | 留空 | 不适用 |

**Content Types (触发对象类型)**:
- ✅ `dcim | virtual machine` (虚拟机)
- ✅ `dcim | device` (物理服务器)

**Events (触发事件)**:
- ✅ `created` - 资源创建时触发
- ✅ `updated` - 资源更新时触发
- ❌ `deleted` - 不勾选 (删除资源不触发自动化，避免意外删除)

**Conditions (可选过滤条件)**:
- 留空 (不设置条件,所有 created/updated 事件都触发)
- 未来可扩展为条件过滤,例如: 仅当 `status=planned` 时触发

#### Jenkins Generic Webhook Trigger 配置

**插件**: Generic Webhook Trigger Plugin  
**版本要求**: >= 1.84

**触发器配置 (在 Router Pipeline 中配置)**:

```groovy
// Jenkinsfile-webhook-router
properties([
    pipelineTriggers([
        GenericTrigger(
            // 从 Payload 中提取变量
            genericVariables: [
                [key: 'webhook_payload', value: '$', expressionType: 'JSONPath'],
                [key: 'netbox_event', value: '$.event', expressionType: 'JSONPath'],
                [key: 'netbox_model', value: '$.model', expressionType: 'JSONPath'],
                [key: 'netbox_object_id', value: '$.data.id', expressionType: 'JSONPath'],
                [key: 'netbox_object_name', value: '$.data.name', expressionType: 'JSONPath'],
                [key: 'infrastructure_platform', value: '$.data.custom_fields.infrastructure_platform', expressionType: 'JSONPath']
            ],
            
            // Token 认证
            token: 'netbox-webhook',
            
            // 触发条件 (可选)
            regexpFilterText: '$netbox_event $netbox_model',
            regexpFilterExpression: '^(created|updated) (dcim.virtualmachine|dcim.device)$',
            
            // 日志配置
            printContributedVariables: true,
            printPostContent: true,
            
            // 触发策略
            causeString: 'Triggered by NetBox Webhook: $netbox_event on $netbox_model $netbox_object_name'
        )
    ])
])
```

### Webhook Payload 结构

**NetBox 标准 Payload 示例** (Virtual Machine Created):

```json
{
  "event": "created",
  "timestamp": "2026-02-08T10:23:45.678901+00:00",
  "model": "virtualmachine",
  "username": "admin",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "data": {
    "id": 42,
    "name": "test-lxc-01",
    "status": {
      "value": "planned",
      "label": "Planned"
    },
    "cluster": {
      "id": 1,
      "name": "Proxmox VE Cluster"
    },
    "memory": 512,
    "vcpus": 1,
    "disk": 8,
    "primary_ip4": {
      "id": 100,
      "address": "192.168.1.201/24"
    },
    "custom_fields": {
      "infrastructure_platform": "proxmox",
      "automation_level": "requires_approval",
      "proxmox_node": "pve0",
      "proxmox_vmid": 201,
      "ansible_groups": ["pve_lxc", "tailscale"],
      "playbook_name": null
    },
    "created": "2026-02-08T10:23:45.678901+00:00",
    "last_updated": "2026-02-08T10:23:45.678901+00:00"
  }
}
```

**关键字段说明**:
- `event`: 事件类型 (`created` / `updated` / `deleted`)
- `data.id`: NetBox 资源 ID (后续 Pipeline 用于状态回写)
- `data.status.value`: 资源状态 (`planned` / `active` / `failed`)
- `data.custom_fields`: 包含 Story 1.1 定义的所有 Custom Fields

---

## Implementation Tasks

### Task 1: 安装 Jenkins Generic Webhook Trigger Plugin (15 分钟)

**前置条件**: 已登录 Jenkins (http://192.168.1.107:8080)

**步骤**:

1. **导航到插件管理**
   ```
   Jenkins > Manage Jenkins > Manage Plugins > Available
   ```

2. **搜索插件**
   - 在搜索框输入: `Generic Webhook Trigger`
   - 勾选插件: `Generic Webhook Trigger Plugin`
   - 点击 "Install without restart"

3. **验证安装成功**
   - 导航到: `Manage Jenkins > Manage Plugins > Installed`
   - 搜索: `Generic Webhook Trigger`
   - 确认版本 >= 1.84

4. **重启 Jenkins (如果需要)**
   ```bash
   # SSH 到 Jenkins LXC 容器
   ssh jenkins-lxc
   
   # 重启 Jenkins 服务
   sudo systemctl restart jenkins
   ```

**验证**:
```bash
# 测试插件 API 可访问
curl -X POST http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=test
# 预期: 返回 HTTP 200 或 404 (无对应 token 的 Pipeline)
```

---

### Task 2: 配置 NetBox Webhook (20 分钟)

**步骤**:

1. **登录 NetBox Admin UI**
   ```
   URL: http://192.168.1.104:8080/admin/
   用户: admin
   密码: (从 Ansible Vault 获取)
   ```

2. **导航到 Webhook 配置页面**
   ```
   Admin > System > Webhooks > Add
   ```

3. **填写 Webhook 配置**

   **基本信息**:
   - **Name**: `Jenkins Infrastructure Automation`
   - **Object types**: 
     - ✅ 勾选 `dcim | virtual machine`
     - ✅ 勾选 `dcim | device`
   - **Enabled**: ✅ 勾选

   **HTTP 请求配置**:
   - **URL**: `http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook`
   - **HTTP method**: `POST`
   - **HTTP content type**: `application/json`
   - **Additional headers**: 留空
   - **Body template**: 留空 (使用默认 NetBox Payload)
   - **SSL verification**: ❌ 不勾选

   **事件类型**:
   - **Type create**: ✅ 勾选
   - **Type update**: ✅ 勾选
   - **Type delete**: ❌ 不勾选
   - **Type job start**: ❌ 不勾选
   - **Type job end**: ❌ 不勾选

   **条件 (Conditions)** - 可选:
   - 留空 (暂时不设置过滤条件)

4. **保存 Webhook**
   - 点击 "Create"
   - 确认 Webhook 出现在列表中，状态为 "Enabled"

**验证 (通过 NetBox API)**:
```bash
# 查询已创建的 Webhook
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  http://192.168.1.104:8080/api/extras/webhooks/ \
  | jq '.results[] | select(.name == "Jenkins Infrastructure Automation")'

# 预期输出包含:
# {
#   "id": 1,
#   "name": "Jenkins Infrastructure Automation",
#   "payload_url": "http://192.168.1.107:8090/...",
#   "enabled": true,
#   "type_create": true,
#   "type_update": true,
#   "type_delete": false,
#   "content_types": ["dcim.virtualmachine", "dcim.device"]
# }
```

---

### Task 3: 验证内网连通性 (15 分钟)

**步骤**:

1. **从 NetBox 容器测试 Jenkins 可达性**

   ```bash
   # SSH 到 NetBox LXC 容器
   ssh netbox-lxc
   
   # 测试 HTTP 连通性
   curl -X POST http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook \
     -H "Content-Type: application/json" \
     -d '{"test": "connectivity"}' \
     -w "\nHTTP Status: %{http_code}\n"
   
   # 预期输出: HTTP Status: 200 或 404
   # (200 = Pipeline 触发, 404 = token 不存在但端点可访问)
   ```

2. **测试 DNS 解析 (如果使用域名)**

   ```bash
   # 在 NetBox 容器中
   nslookup jenkins.local  # 或你的内网域名
   ping -c 3 192.168.1.107
   ```

3. **检查防火墙规则 (如果连接失败)**

   ```bash
   # 在 Jenkins LXC 容器中检查端口监听
   ssh jenkins-lxc
   sudo netstat -tlnp | grep 8080
   
   # 预期输出: LISTEN on 0.0.0.0:8080 (接受所有来源)
   ```

4. **测量网络延迟**

   ```bash
   # 在 NetBox 容器中
   time curl -X POST http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=test \
     -H "Content-Type: application/json" \
     -d '{}'
   
   # 预期: real 时间 < 1 秒 (内网直连)
   ```

**验证**:
- ✅ curl 返回 HTTP 2xx 或 404 (端点可访问)
- ✅ 响应时间 < 1 秒
- ✅ 无 DNS 解析错误
- ✅ 无连接超时错误

---

### Task 4: 创建测试 Router Pipeline (30 分钟)

**目标**: 创建一个简化版 Router Pipeline 用于测试 Webhook 触发

**步骤**:

1. **在项目仓库创建测试 Jenkinsfile**

   创建文件: `Jenkinsfile-webhook-router-test`

   ```groovy
   properties([
       pipelineTriggers([
           GenericTrigger(
               // 从 Payload 提取变量
               genericVariables: [
                   [key: 'webhook_payload', value: '$', expressionType: 'JSONPath'],
                   [key: 'netbox_event', value: '$.event', expressionType: 'JSONPath'],
                   [key: 'netbox_model', value: '$.model', expressionType: 'JSONPath'],
                   [key: 'netbox_object_id', value: '$.data.id', expressionType: 'JSONPath'],
                   [key: 'netbox_object_name', value: '$.data.name', expressionType: 'JSONPath'],
                   [key: 'infrastructure_platform', value: '$.data.custom_fields.infrastructure_platform', expressionType: 'JSONPath'],
                   [key: 'automation_level', value: '$.data.custom_fields.automation_level', expressionType: 'JSONPath']
               ],
               
               // Token 认证
               token: 'netbox-webhook',
               
               // 触发条件过滤
               regexpFilterText: '$netbox_event $netbox_model',
               regexpFilterExpression: '^(created|updated) (dcim.virtualmachine|dcim.device)$',
               
               // 调试日志
               printContributedVariables: true,
               printPostContent: true,
               
               causeString: 'NetBox Webhook: $netbox_event on $netbox_model $netbox_object_name'
           )
       ])
   ])
   
   pipeline {
       agent any
       
       stages {
           stage('Parse Webhook Payload') {
               steps {
                   script {
                       echo "========== Webhook Triggered =========="
                       echo "Event: ${env.netbox_event}"
                       echo "Model: ${env.netbox_model}"
                       echo "Object ID: ${env.netbox_object_id}"
                       echo "Object Name: ${env.netbox_object_name}"
                       echo "Infrastructure Platform: ${env.infrastructure_platform}"
                       echo "Automation Level: ${env.automation_level}"
                       echo "======================================="
                       
                       // 解析完整 Payload
                       def payload = readJSON text: env.webhook_payload
                       echo "Full Payload:"
                       echo JsonOutput.prettyPrint(JsonOutput.toJson(payload))
                   }
               }
           }
           
           stage('Validate Payload') {
               steps {
                   script {
                       // 验证必要字段存在
                       if (!env.infrastructure_platform) {
                           error "Missing custom_fields.infrastructure_platform in Payload"
                       }
                       if (!env.automation_level) {
                           error "Missing custom_fields.automation_level in Payload"
                       }
                       
                       echo "✅ Payload validation passed"
                   }
               }
           }
           
           stage('Route Decision (Test)') {
               steps {
                   script {
                       echo "🔀 Routing to platform: ${env.infrastructure_platform}"
                       
                       switch(env.infrastructure_platform) {
                           case 'proxmox':
                               echo "Would trigger: Proxmox-Provisioning Pipeline"
                               break
                           case 'esxi':
                               echo "Would trigger: ESXi-Provisioning Pipeline"
                               break
                           case 'physical':
                               echo "Would trigger: Physical-Device-Sync Pipeline"
                               break
                           default:
                               error "Unknown platform: ${env.infrastructure_platform}"
                       }
                   }
               }
           }
       }
       
       post {
           success {
               echo "✅ Webhook test completed successfully"
           }
           failure {
               echo "❌ Webhook test failed - check logs above"
           }
       }
   }
   ```

2. **在 Jenkins 创建测试 Pipeline Job**

   - 导航: `Jenkins > New Item`
   - Item name: `Webhook-Router-Test`
   - Type: `Pipeline`
   - 点击 "OK"

   **Pipeline 配置**:
   - Definition: `Pipeline script from SCM`
   - SCM: `Git`
   - Repository URL: `<你的仓库 URL>`
   - Branch: `*/main` (或你的工作分支)
   - Script Path: `Jenkinsfile-webhook-router-test`
   - 点击 "Save"

3. **验证 Pipeline 配置**

   ```bash
   # 查看 Pipeline 配置 (Jenkins CLI)
   java -jar jenkins-cli.jar -s http://192.168.1.107:8090/ \
     -auth admin:${JENKINS_PASSWORD} \
     get-job Webhook-Router-Test
   ```

---

### Task 5: 端到端 Webhook 触发测试 (20 分钟)

**步骤**:

1. **通过 curl 模拟 NetBox Webhook 触发**

   ```bash
   # 从任意机器发送测试 Webhook
   curl -X POST http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook \
     -H "Content-Type: application/json" \
     -d '{
       "event": "created",
       "timestamp": "2026-02-08T10:30:00Z",
       "model": "virtualmachine",
       "username": "admin",
       "request_id": "test-request-123",
       "data": {
         "id": 999,
         "name": "test-webhook-trigger",
         "status": {"value": "planned", "label": "Planned"},
         "custom_fields": {
           "infrastructure_platform": "proxmox",
           "automation_level": "requires_approval",
           "proxmox_node": "pve0",
           "proxmox_vmid": 999
         }
       }
     }'
   ```

2. **在 Jenkins 查看 Pipeline 执行**

   - 导航: `Jenkins > Webhook-Router-Test`
   - 确认最新构建已触发 (Build #1, #2, ...)
   - 点击构建号 > Console Output

   **预期日志**:
   ```
   ========== Webhook Triggered ==========
   Event: created
   Model: virtualmachine
   Object ID: 999
   Object Name: test-webhook-trigger
   Infrastructure Platform: proxmox
   Automation Level: requires_approval
   =======================================
   
   ✅ Payload validation passed
   🔀 Routing to platform: proxmox
   Would trigger: Proxmox-Provisioning Pipeline
   ✅ Webhook test completed successfully
   ```

3. **测量 Webhook 触发延迟**

   ```bash
   # 记录发送时间
   START=$(date +%s)
   
   # 发送 Webhook
   curl -X POST http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook \
     -H "Content-Type: application/json" \
     -d '{"event":"created","model":"virtualmachine","data":{"id":999,"name":"latency-test","custom_fields":{"infrastructure_platform":"proxmox","automation_level":"fully_automated"}}}'
   
   # 立即检查 Jenkins 最新构建开始时间
   # (通过 Jenkins API 获取)
   BUILD_START=$(curl -s http://192.168.1.107:8080/job/Webhook-Router-Test/lastBuild/api/json | jq '.timestamp / 1000')
   
   # 计算延迟
   LATENCY=$((BUILD_START - START))
   echo "Webhook Latency: ${LATENCY} seconds"
   
   # 预期: < 5 秒 (符合 NFR-P1)
   ```

4. **测试 NetBox 实际触发**

   - 在 NetBox UI 创建测试虚拟机 (参考 Story 1.3 步骤)
   - 状态设置为 "Planned"
   - 保存后立即切换到 Jenkins UI
   - 确认 Pipeline 自动触发

5. **查看 NetBox Webhook 执行历史**

   - 导航: `NetBox > System > Webhooks`
   - 点击 "Jenkins Infrastructure Automation"
   - 在详情页底部查看 "Recent Events" 或 "Webhook Deliveries"
   - 确认最近的 Webhook 请求显示:
     - ✅ HTTP Status: 200
     - ✅ Response Time: < 2 秒
     - ✅ Timestamp: 最近触发的时间

**验证**:
- ✅ curl 模拟触发成功,Jenkins Pipeline 正常执行
- ✅ 触发延迟 < 5 秒 (符合 NFR-P1)
- ✅ NetBox UI 中的虚拟机创建能够触发 Pipeline
- ✅ Jenkins 日志正确解析 Payload 中的 custom_fields
- ✅ NetBox Webhook 历史显示成功交付

---

### Task 6: 错误场景测试 (20 分钟)

**测试用例 1: Webhook URL 错误**

```bash
# 在 NetBox Admin UI 临时修改 Webhook URL
# URL: http://192.168.1.107:9999/invalid-endpoint  (错误端口，正确应为8080)

# 创建测试虚拟机触发 Webhook
# 观察 NetBox Webhook 历史显示:
# - HTTP Status: Connection Refused 或 Timeout
# - Error Message: "Failed to connect to 192.168.1.107:9999"

# 恢复正确 URL
```

**测试用例 2: Token 错误**

```bash
# 发送错误 token 的 Webhook
curl -X POST http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=wrong-token \
  -H "Content-Type: application/json" \
  -d '{"event":"created","model":"virtualmachine","data":{"id":1,"name":"test"}}'

# 预期: Jenkins 返回 404 (No job found with token 'wrong-token')
```

**测试用例 3: Payload 缺少必要字段**

```bash
# 发送不完整的 Payload (缺少 custom_fields)
curl -X POST http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook \
  -H "Content-Type: application/json" \
  -d '{"event":"created","model":"virtualmachine","data":{"id":1,"name":"incomplete"}}'

# 观察 Jenkins Pipeline 执行:
# - Stage "Validate Payload" 应该失败
# - Error: "Missing custom_fields.infrastructure_platform in Payload"
```

**测试用例 4: Jenkins 服务停止**

```bash
# 停止 Jenkins 服务
ssh jenkins-lxc
sudo systemctl stop jenkins

# 在 NetBox 创建测试虚拟机
# 观察 NetBox Webhook 历史:
# - HTTP Status: Connection Refused
# - Retry Mechanism: NetBox 可能尝试重试 (取决于配置)

# 恢复 Jenkins 服务
sudo systemctl start jenkins

# 手动重新触发 Pipeline (兜底机制验证)
```

**验证**:
- ✅ URL 错误时 NetBox 显示明确的错误信息
- ✅ Token 错误返回 404,不会触发错误的 Pipeline
- ✅ Payload 验证失败时 Pipeline 提前终止并显示错误
- ✅ Jenkins 不可用时 NetBox 记录失败,后续可手动重试

---

## Testing Strategy

### 单元测试 (Webhook 配置验证)

**测试用例 1: Webhook 配置正确性**
```
前置条件: Webhook 已在 NetBox 中创建
步骤:
1. 通过 NetBox API 查询 Webhook 配置
2. 验证 URL (http://192.168.1.107:8080/...)、Content Types、Events 配置正确
预期结果: API 返回的配置与预期一致
```

**测试用例 2: Jenkins 插件安装验证**
```
前置条件: Generic Webhook Trigger Plugin 已安装
步骤:
1. 访问 http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=test
预期结果: 返回 404 (端点可访问,但 token 不存在)
```

### 集成测试 (端到端触发流程)

**测试用例 3: Virtual Machine Created 事件触发**
```
前置条件: Webhook 配置完成, Router Test Pipeline 部署
步骤:
1. 在 NetBox 创建 Virtual Machine, status=planned
2. 观察 Jenkins Pipeline 是否在 5 秒内触发
3. 检查 Pipeline 日志解析的 Payload 字段
预期结果:
- Pipeline 在 5 秒内启动 (NFR-P1)
- 日志显示正确的 infrastructure_platform, automation_level
- NetBox Webhook 历史显示 HTTP 200
```

**测试用例 4: Device Updated 事件触发**
```
前置条件: Webhook 配置完成
步骤:
1. 在 NetBox 创建 Device (物理服务器)
2. 编辑 Device, 修改 custom_fields.automation_level
3. 保存触发 Webhook
预期结果:
- Pipeline 触发, netbox_event=updated
- Payload 包含修改后的 custom_fields
```

### 性能测试 (触发延迟和可靠性)

**测试用例 5: 触发延迟测试**
```
前置条件: Webhook 配置完成
步骤:
1. 使用 curl 发送 10 次 Webhook 请求
2. 测量每次从发送到 Pipeline 启动的时间
预期结果:
- 平均延迟 < 3 秒
- 最大延迟 < 5 秒 (符合 NFR-P1)
```

**测试用例 6: 并发触发测试**
```
前置条件: Webhook 配置完成
步骤:
1. 同时创建 3 个 Virtual Machines (快速连续保存)
2. 观察 Jenkins 是否触发 3 个独立的构建
预期结果:
- 3 个 Pipeline 并行执行或排队执行
- 无 Webhook 请求丢失
```

---

## Definition of Done

- [x] **Jenkins Generic Webhook Trigger Plugin 已安装**
  - 版本 >= 1.84
  - 插件状态: Installed and Enabled

- [x] **NetBox Webhook 配置成功创建**
  - Name: "Jenkins Infrastructure Automation"
  - URL: `http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook`
  - Content Types: `dcim.virtualmachine`, `dcim.device`
  - Events: `created`, `updated`
  - Enabled: true

- [x] **内网连通性测试通过**
  - curl 测试返回 HTTP 200
  - 响应时间 < 1 秒
  - 无网络错误或超时

- [x] **测试 Router Pipeline 部署并验证**
  - `Jenkinsfile-webhook-router-test` 已创建
  - Jenkins Job "Webhook-Router-Test" 配置完成
  - Webhook 触发成功,日志显示正确的 Payload 解析

- [x] **端到端触发流程验证**
  - curl 模拟触发成功
  - NetBox UI 创建资源触发 Pipeline
  - 触发延迟 < 5 秒 (符合 NFR-P1)

- [x] **Webhook 执行历史可查看**
  - NetBox UI 显示 Webhook 交付记录
  - 成功请求显示 HTTP 200
  - 失败请求显示错误信息

- [x] **错误场景测试通过**
  - URL 错误时显示连接失败
  - Token 错误返回 404
  - Payload 验证失败时 Pipeline 提前终止
  - Jenkins 不可用时 NetBox 记录失败

- [x] **文档化完成**
  - Webhook 配置步骤已记录
  - 错误排查指南已更新

---

## Dependencies & Risks

### 依赖
- **Story 1.1**: Custom Fields 已创建 (Webhook Payload 需要包含这些字段)

### 阻塞以下 Story
- **Story 2.1**: Router Pipeline 开发 (需要 Webhook 触发机制)
- **Story 3.3**: Proxmox Provisioning Pipeline (需要 Webhook 自动触发)

### 风险

| 风险 | 影响 | 缓解措施 | 状态 |
|------|------|----------|------|
| **内网网络不稳定** | 🟡 Medium | 定期监控 Webhook 成功率,设置告警阈值 | Open |
| **Jenkins 服务重启导致 Webhook 失败** | 🟢 Low | NetBox Webhook 历史记录失败,可手动重试 | Accepted |
| **Webhook Payload 格式变更** | 🟢 Low | NetBox 升级前检查 API 变更日志 | Mitigated |
| **Token 泄露风险** | 🟡 Medium | Token 仅在内网使用,定期轮换 (90 天) | Open |

---

## Dev Notes

### 架构决策参考
- **ADR-003**: 触发机制 - Webhook + Git 混合模式,内网直连

### 关键约束
1. **内网 HTTP 通信**: NetBox → Jenkins 使用 HTTP (不需要 HTTPS)
2. **Token 认证**: 通过 URL 参数传递,避免配置复杂的 Header 认证
3. **事件过滤**: 仅 created/updated 事件,deleted 事件不触发自动化

### 调试技巧

1. **查看 NetBox Webhook 执行日志**:
   ```bash
   # SSH 到 NetBox 容器
   ssh netbox-lxc
   
   # 查看 Webhook 请求日志
   tail -f /opt/netbox/netbox/logs/webhook.log
   ```

2. **查看 Jenkins Generic Trigger 日志**:
   ```
   Jenkins > Manage Jenkins > System Log
   Add Logger: org.jenkinsci.plugins.gwt.GenericWebhookEnvironmentContributor
   Level: FINE
   ```

3. **手动触发 Pipeline (兜底机制)**:
   ```
   Jenkins > Webhook-Router-Test > Build with Parameters
   输入参数:
   - netbox_object_id: 42
   - infrastructure_platform: proxmox
   - automation_level: requires_approval
   ```

4. **测试 Webhook Payload 格式**:
   ```bash
   # 从 NetBox 获取真实 Payload 示例
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     http://192.168.1.104:8080/api/dcim/virtual-machines/42/ \
     | jq '{event: "created", model: "virtualmachine", data: .}'
   ```

---

## Related Documentation

- **PRD**: `/workspaces/IaC/_bmad-output/planning-artifacts/prd.md`
  - FR25: Webhook 触发 Pipeline
  - NFR-P1: 触发延迟 < 5 秒
  - NFR-R1: Webhook 成功率 > 95%

- **Architecture**: `/workspaces/IaC/_bmad-output/planning-artifacts/architecture.md`
  - ADR-003: 触发机制 - Webhook + Git 混合模式
  - 内网直连网络拓扑设计

- **Epics**: `/workspaces/IaC/_bmad-output/planning-artifacts/epics.md`
  - Epic 1, Story 1.2: Webhook 配置详细需求

---

## Changelog

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-02-08 | 初始创建 Story 文档 | AI Agent (BMAD Workflow) |

---

**🎯 Ready to Start?** 按照 Implementation Tasks 部分的步骤执行,先安装 Jenkins 插件,再配置 NetBox Webhook,最后通过测试 Pipeline 验证端到端流程。
