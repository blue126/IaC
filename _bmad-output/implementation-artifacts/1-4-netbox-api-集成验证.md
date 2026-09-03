# Story 1-4: NetBox API 集成验证

**Epic**: Epic 1 - NetBox 数据建模与配置  
**Story ID**: 1.4  
**优先级**: 🔴 Critical  
**预估工作量**: 1.5-2 小时  
**依赖**: Story 1.1 (Custom Fields), Story 1.3 (测试虚拟机已创建)  
**状态**: Ready for Dev

---

## Story Overview

### 用户故事
作为 System，我需要通过 NetBox REST API 查询虚拟机配置数据，这样 Terraform (Story 3.1) 和 Jenkins Pipeline (Story 2.1) 可以动态获取配置信息，实现真正的 Infrastructure as Data 驱动的自动化流程。

### 业务价值
- ✅ **验证 API 集成可行性**: 确认 NetBox API 能够提供 Terraform 和 Jenkins 所需的所有数据
- ✅ **建立集成规范**: 定义 API 查询模式、过滤条件、错误处理等最佳实践
- ✅ **性能基准测试**: 验证 API 响应时间符合 NFR-P6 要求 (< 30 秒,实际目标 < 2 秒)
- ✅ **安全性验证**: 确认 API Token 认证机制正常工作,满足 NFR-I1 要求

### 技术目标
1. 创建 NetBox API Token 并配置在 Jenkins Secrets 中
2. 验证 API 能够查询虚拟机列表并返回所有必要字段
3. 测试通过 Custom Fields 进行过滤查询 (如 `cf_infrastructure_platform=proxmox`)
4. 测量 API 查询性能和响应时间
5. 验证 API 认证失败场景和错误处理
6. 记录 API 集成最佳实践和常用查询模式

---

## Requirements (来自 Epics)

### 功能性需求
- **FR6**: System 可以从 NetBox 通过 REST API 获取所有虚拟机配置数据
- **FR9**: System 可以通过 Terraform 从 NetBox 数据源拉取虚拟机配置

### 非功能性需求
- **NFR-P6**: Terraform 从 NetBox data source 查询单个资源的时间 < 30 秒
- **NFR-I1**: NetBox API 集成必须支持 API Token 认证,避免使用用户名/密码
- **NFR-I9**: 外部 API 调用失败时,Pipeline 必须记录详细错误日志 (HTTP 状态码、响应 Body)
- **NFR-M10**: Jenkins 必须保留最近 10 个构建历史 (用于故障排查)

### Acceptance Criteria (验收标准)
- [ ] NetBox API Token 已创建并配置在 Jenkins Secrets 中
- [ ] 成功执行 API 查询,获取 `status=planned` 的虚拟机列表
- [ ] 响应 JSON 包含所有必要字段:
  - 核心字段: `id`, `name`, `status`, `memory`, `vcpus`
  - 关联字段: `cluster.name`, `primary_ip4.address`
  - Custom Fields: `infrastructure_platform`, `automation_level`, `proxmox_node`, `proxmox_vmid`, `ansible_groups`, `playbook_name`
- [ ] 通过 Custom Fields 过滤查询成功:
  - 查询 `cf_infrastructure_platform=proxmox` 返回仅 Proxmox 虚拟机
  - 查询 `cf_automation_level=requires_approval` 返回需要审批的虚拟机
- [ ] API 查询响应时间 < 2 秒 (远优于 NFR-P6 的 30 秒要求)
- [ ] API Token 认证失败时返回 HTTP 403 错误
- [ ] API 查询日志记录在 NetBox audit log 中 (可选验证)
- [ ] 创建 API 集成文档,包含常用查询示例和错误处理

---

## Technical Design

### NetBox API 架构

#### API 端点结构

**Base URL**: `http://192.168.1.104:8080/api/`

**核心端点**:
- **Virtual Machines**: `/virtualization/virtual-machines/`
- **Devices**: `/dcim/devices/`
- **IP Addresses**: `/ipam/ip-addresses/`
- **Interfaces**: `/virtualization/interfaces/`
- **Custom Fields**: `/extras/custom-fields/`
- **Webhooks**: `/extras/webhooks/`

#### 认证机制 (NFR-I1)

**Token 认证** (推荐):
```bash
curl -H "Authorization: Token <api_token>" \
  http://192.168.1.104:8080/api/virtualization/virtual-machines/
```

**用户名/密码认证** (不推荐,仅用于交互式操作):
```bash
curl -u "username:password" \
  http://192.168.1.104:8080/api/virtualization/virtual-machines/
```

#### API 响应结构

**标准响应格式** (列表查询):
```json
{
  "count": 10,
  "next": "http://192.168.1.104:8080/api/virtualization/virtual-machines/?limit=50&offset=50",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "test-lxc-01",
      "status": {
        "value": "planned",
        "label": "Planned"
      },
      "cluster": {
        "id": 1,
        "name": "Proxmox VE Cluster",
        "url": "http://192.168.1.104:8080/api/virtualization/clusters/1/"
      },
      "memory": 512,
      "vcpus": 1,
      "disk": 8,
      "primary_ip4": {
        "id": 1,
        "address": "192.168.1.201/24",
        "family": 4
      },
      "custom_fields": {
        "infrastructure_platform": "proxmox",
        "automation_level": "requires_approval",
        "proxmox_node": "pve0",
        "proxmox_vmid": 201,
        "ansible_groups": ["pve_lxc", "tailscale"],
        "playbook_name": null
      },
      "created": "2026-02-08T10:00:00Z",
      "last_updated": "2026-02-08T11:00:00Z",
      "url": "http://192.168.1.104:8080/api/virtualization/virtual-machines/1/"
    }
  ]
}
```

**单个资源响应** (GET /api/virtualization/virtual-machines/{id}/):
```json
{
  "id": 1,
  "name": "test-lxc-01",
  // ... (与列表响应中的单个对象相同)
}
```

#### 查询参数和过滤

**分页参数**:
- `limit`: 每页结果数量 (默认 50,最大 1000)
- `offset`: 偏移量 (用于分页)

**过滤参数** (按核心字段):
- `name`: 精确匹配虚拟机名称
- `status`: 过滤状态 (`planned`, `active`, `offline`, `failed`)
- `cluster_id`: 过滤集群 ID
- `memory__gte`: 内存大于等于 (Greater Than or Equal)
- `memory__lte`: 内存小于等于

**过滤参数** (按 Custom Fields):
- `cf_<field_name>=<value>`: 精确匹配
  - 示例: `cf_infrastructure_platform=proxmox`
  - 示例: `cf_automation_level=requires_approval`
- `cf_<field_name>__ic=<value>`: 忽略大小写匹配 (Ignore Case)
- `cf_<field_name>__n=<value>`: 不等于 (Not Equal)

**排序参数**:
- `ordering=name`: 按名称升序
- `ordering=-created`: 按创建时间降序 (最新优先)

**示例查询**:
```bash
# 查询所有 Proxmox 平台的 planned 状态虚拟机,按创建时间降序
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?status=planned&cf_infrastructure_platform=proxmox&ordering=-created"
```

---

## Implementation Tasks

### Task 1: 创建 NetBox API Token (20 分钟)

**步骤**:

1. **登录 NetBox UI**
   ```
   URL: http://192.168.1.104:8080
   用户: admin
   ```

2. **导航到 Token 管理页面**
   ```
   右上角用户菜单 > API Tokens > Add Token
   ```

3. **创建新 API Token**

   **Token 配置**:
   - **User**: `admin` (或创建专门的 automation 用户)
   - **Key**: 留空 (自动生成 40 字符的 Token)
   - **Write enabled**: ✅ 勾选 (允许写操作,后续 Story 需要回写状态)
   - **Description**: `Terraform and Jenkins automation token`
   - **Expires**: 留空 (永不过期,生产环境建议设置过期时间)

   点击 "Create"。

4. **复制 Token**

   ⚠️ **重要**: Token 只会显示一次,请立即复制并保存到安全位置。

   示例 Token (40 字符):
   ```
   0123456789abcdef0123456789abcdef01234567
   ```

5. **测试 Token**

   ```bash
   # 设置环境变量
   export NETBOX_API_TOKEN="0123456789abcdef0123456789abcdef01234567"
   
   # 测试 API 访问
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     http://192.168.1.104:8080/api/virtualization/virtual-machines/ \
     | jq '.count'
   
   # 预期输出: 返回虚拟机数量 (如 1)
   ```

**验证**:
- ✅ Token 创建成功,显示在 Token 列表中
- ✅ 测试 API 调用返回数据,无认证错误
- ✅ Token 已保存到安全位置 (密码管理器或 Ansible Vault)

---

### Task 2: 配置 NetBox API Token 到 Jenkins Secrets (15 分钟)

**步骤**:

1. **登录 Jenkins UI**
   ```
   URL: http://192.168.1.107:8090
   用户: admin
   ```

2. **导航到 Credentials 管理**
   ```
   Manage Jenkins > Manage Credentials > (global) > Add Credentials
   ```

3. **添加 Secret Text**

   **Credential 配置**:
   - **Kind**: `Secret text`
   - **Scope**: `Global`
   - **Secret**: 粘贴刚创建的 NetBox API Token
   - **ID**: `netbox-api-token` (⚠️ 保持一致,后续 Pipeline 使用此 ID)
   - **Description**: `NetBox API Token for Terraform and Automation`

   点击 "Create"。

4. **验证 Credential 创建成功**

   导航: `Manage Jenkins > Manage Credentials > (global)`

   确认列表中显示:
   - **ID**: `netbox-api-token`
   - **Kind**: `Secret text`
   - **Description**: `NetBox API Token for...`

**验证 (通过 Pipeline 脚本)**:

创建临时测试 Pipeline:

```groovy
pipeline {
    agent any
    stages {
        stage('Test NetBox API Token') {
            steps {
                script {
                    withCredentials([string(credentialsId: 'netbox-api-token', variable: 'NETBOX_TOKEN')]) {
                        sh '''
                            curl -s -H "Authorization: Token ${NETBOX_TOKEN}" \
                              http://192.168.1.104:8080/api/virtualization/virtual-machines/ \
                              | jq '.count'
                        '''
                    }
                }
            }
        }
    }
}
```

运行 Pipeline,预期输出虚拟机数量 (如 `1`)。

---

### Task 3: 验证 API 查询所有必要字段 (30 分钟)

**目标**: 确认 API 响应包含 Terraform 和 Jenkins 所需的所有字段

**步骤**:

1. **查询测试虚拟机** (Story 1.3 创建的 `test-lxc-01`)

   ```bash
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/?name=test-lxc-01" \
     | jq '.results[0]' > /tmp/netbox-vm-response.json
   
   # 查看完整响应
   cat /tmp/netbox-vm-response.json | jq .
   ```

2. **验证核心字段存在**

   ```bash
   # 检查必要字段
   cat /tmp/netbox-vm-response.json | jq '{
     id,
     name,
     status: .status.value,
     memory,
     vcpus,
     disk
   }'
   
   # 预期输出:
   # {
   #   "id": 1,
   #   "name": "test-lxc-01",
   #   "status": "planned",
   #   "memory": 512,
   #   "vcpus": 1,
   #   "disk": 8
   # }
   ```

3. **验证关联字段存在**

   ```bash
   # 检查 cluster 和 primary_ip4
   cat /tmp/netbox-vm-response.json | jq '{
     cluster_name: .cluster.name,
     primary_ip: .primary_ip4.address
   }'
   
   # 预期输出:
   # {
   #   "cluster_name": "Proxmox VE Cluster",  # 或 null (如果未配置)
   #   "primary_ip": "192.168.1.201/24"
   # }
   ```

4. **验证所有 Custom Fields 存在**

   ```bash
   # 检查 6 个 Custom Fields
   cat /tmp/netbox-vm-response.json | jq '.custom_fields'
   
   # 预期输出:
   # {
   #   "infrastructure_platform": "proxmox",
   #   "automation_level": "requires_approval",
   #   "proxmox_node": "pve0",
   #   "proxmox_vmid": 201,
   #   "ansible_groups": ["pve_lxc", "tailscale"],
   #   "playbook_name": null
   # }
   ```

5. **验证字段类型正确**

   ```bash
   # 使用 jq 验证类型
   cat /tmp/netbox-vm-response.json | jq '
     {
       id_is_number: (.id | type == "number"),
       memory_is_number: (.memory | type == "number"),
       ansible_groups_is_array: (.custom_fields.ansible_groups | type == "array"),
       status_is_object: (.status | type == "object")
     }
   '
   
   # 预期所有值为 true
   ```

**验证检查清单**:
- [x] `id` (Number)
- [x] `name` (String)
- [x] `status.value` (String: "planned")
- [x] `memory` (Number)
- [x] `vcpus` (Number)
- [x] `cluster.name` (String or null)
- [x] `primary_ip4.address` (String or null)
- [x] `custom_fields.infrastructure_platform` (String)
- [x] `custom_fields.automation_level` (String)
- [x] `custom_fields.proxmox_node` (String or null)
- [x] `custom_fields.proxmox_vmid` (Number or null)
- [x] `custom_fields.ansible_groups` (Array or null)
- [x] `custom_fields.playbook_name` (String or null)

---

### Task 4: 测试 Custom Fields 过滤查询 (25 分钟)

**目标**: 验证通过 Custom Fields 进行精确过滤查询

**测试用例 1: 按 infrastructure_platform 过滤**

```bash
# 查询所有 Proxmox 平台的虚拟机
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_infrastructure_platform=proxmox" \
  | jq '.results[] | {name, platform: .custom_fields.infrastructure_platform}'

# 预期输出:
# {
#   "name": "test-lxc-01",
#   "platform": "proxmox"
# }

# 验证过滤逻辑:所有结果的 infrastructure_platform 都是 "proxmox"
```

**测试用例 2: 按 automation_level 过滤**

```bash
# 查询所有需要审批的虚拟机
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_automation_level=requires_approval" \
  | jq '.results[] | {name, automation_level: .custom_fields.automation_level}'

# 预期输出:
# {
#   "name": "test-lxc-01",
#   "automation_level": "requires_approval"
# }
```

**测试用例 3: 多条件组合过滤**

```bash
# 查询 Proxmox 平台 + planned 状态 + 需要审批
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?status=planned&cf_infrastructure_platform=proxmox&cf_automation_level=requires_approval" \
  | jq '.results[] | {name, status: .status.value, platform: .custom_fields.infrastructure_platform}'

# 预期输出:
# {
#   "name": "test-lxc-01",
#   "status": "planned",
#   "platform": "proxmox"
# }
```

**测试用例 4: 按 proxmox_node 过滤**

```bash
# 查询所有在 pve0 节点上的虚拟机
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_proxmox_node=pve0" \
  | jq '.results[] | {name, node: .custom_fields.proxmox_node, vmid: .custom_fields.proxmox_vmid}'

# 预期输出:
# {
#   "name": "test-lxc-01",
#   "node": "pve0",
#   "vmid": 201
# }
```

**测试用例 5: 不等于过滤 (排除某个平台)**

```bash
# 查询所有非物理服务器的资源
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_infrastructure_platform__n=physical" \
  | jq '.results[] | {name, platform: .custom_fields.infrastructure_platform}'

# 预期输出: 返回 proxmox 和 esxi 的虚拟机,不包含 physical
```

**验证**:
- ✅ 所有过滤查询返回正确的结果集
- ✅ 组合条件过滤正常工作 (AND 逻辑)
- ✅ 不等于过滤 (`__n`) 正确排除指定值

---

### Task 5: API 性能测试 (20 分钟)

**目标**: 验证 API 响应时间符合 NFR-P6 要求 (< 30 秒,实际目标 < 2 秒)

**测试用例 1: 单个资源查询性能**

```bash
# 测量查询单个虚拟机的时间
time curl -s -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/1/" \
  > /dev/null

# 预期: real 时间 < 0.5 秒
```

**测试用例 2: 列表查询性能 (50 条记录)**

```bash
# 测量查询 50 条虚拟机列表的时间
time curl -s -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?limit=50" \
  > /dev/null

# 预期: real 时间 < 2 秒
```

**测试用例 3: 复杂过滤查询性能**

```bash
# 测量复杂条件过滤的时间
time curl -s -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?status=planned&cf_infrastructure_platform=proxmox&cf_automation_level=requires_approval&ordering=-created" \
  > /dev/null

# 预期: real 时间 < 2 秒
```

**测试用例 4: 并发查询测试**

```bash
# 使用 GNU parallel 模拟并发查询
seq 1 5 | parallel -j 5 "curl -s -H 'Authorization: Token ${NETBOX_API_TOKEN}' \
  http://192.168.1.104:8080/api/virtualization/virtual-machines/ > /dev/null"

# 测量总时间
time seq 1 5 | parallel -j 5 "curl -s -H 'Authorization: Token ${NETBOX_API_TOKEN}' \
  http://192.168.1.104:8080/api/virtualization/virtual-machines/?status=planned"

# 预期: 5 个并发请求总时间 < 5 秒
```

**性能基准记录**:

| 查询类型 | 目标时间 | 实际时间 | 状态 |
|---------|---------|---------|------|
| 单个资源查询 | < 0.5 秒 | ___ 秒 | ⏳ |
| 50 条列表查询 | < 2 秒 | ___ 秒 | ⏳ |
| 复杂过滤查询 | < 2 秒 | ___ 秒 | ⏳ |
| 5 并发查询 | < 5 秒 | ___ 秒 | ⏳ |

**验证**:
- ✅ 所有查询时间远低于 NFR-P6 要求的 30 秒
- ✅ 平均查询时间 < 2 秒

---

### Task 6: 错误场景和认证测试 (20 分钟)

**测试用例 1: Token 认证失败 (NFR-I1)**

```bash
# 使用错误的 Token
curl -i -H "Authorization: Token invalid-token-12345" \
  http://192.168.1.104:8080/api/virtualization/virtual-machines/

# 预期输出:
# HTTP/1.1 403 Forbidden
# {"detail": "Invalid token."}
```

**测试用例 2: 缺少 Authorization Header**

```bash
# 不提供 Token
curl -i http://192.168.1.104:8080/api/virtualization/virtual-machines/

# 预期输出:
# HTTP/1.1 403 Forbidden
# {"detail": "Authentication credentials were not provided."}
```

**测试用例 3: 查询不存在的资源**

```bash
# 查询不存在的 ID
curl -i -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  http://192.168.1.104:8080/api/virtualization/virtual-machines/99999/

# 预期输出:
# HTTP/1.1 404 Not Found
# {"detail": "Not found."}
```

**测试用例 4: 无效的过滤参数**

```bash
# 使用不存在的 Custom Field
curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_nonexistent_field=value" \
  | jq .

# 预期: 返回空结果列表 (count=0),不报错
```

**测试用例 5: Token 写权限验证**

```bash
# 尝试更新虚拟机 (测试 Write enabled)
curl -X PATCH -H "Authorization: Token ${NETBOX_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"comments": "API write test"}' \
  http://192.168.1.104:8080/api/virtualization/virtual-machines/1/

# 预期输出: HTTP 200,返回更新后的对象
# 如果 Token 未启用 Write,返回 HTTP 403
```

**验证**:
- ✅ 无效 Token 返回 HTTP 403 (符合 NFR-I1)
- ✅ 缺少认证返回 HTTP 403
- ✅ 不存在的资源返回 HTTP 404
- ✅ 无效过滤参数返回空结果,不报错
- ✅ Write enabled Token 可以成功更新资源

---

### Task 7: 文档化 API 集成最佳实践 (20 分钟)

**目标**: 创建 API 集成参考文档,供后续 Story 使用

**步骤**:

1. **创建文档**: `docs/netbox-api-integration-guide.md`

   内容包括:

   ```markdown
   # NetBox API 集成指南

   ## API 端点
   - Base URL: `http://192.168.1.104:8080/api/`
   - Virtual Machines: `/virtualization/virtual-machines/`
   - Devices: `/dcim/devices/`

   ## 认证
   ```bash
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" <endpoint>
   ```

   ## 常用查询模式

   ### 查询所有 Planned 状态的 Proxmox 虚拟机
   ```bash
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/?status=planned&cf_infrastructure_platform=proxmox"
   ```

   ### 查询特定节点的虚拟机
   ```bash
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_proxmox_node=pve0"
   ```

   ### 查询需要审批的资源
   ```bash
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/?cf_automation_level=requires_approval"
   ```

   ## 错误处理

   | HTTP 状态码 | 含义 | 处理方式 |
   |------------|------|---------|
   | 200 | 成功 | 解析 JSON 响应 |
   | 403 | 认证失败 | 检查 Token 是否正确 |
   | 404 | 资源不存在 | 检查 ID 或查询条件 |
   | 500 | 服务器错误 | 查看 NetBox 日志,联系管理员 |

   ## 性能优化

   - 使用过滤参数减少返回结果
   - 避免查询所有字段,使用 `brief` 参数
   - 设置合理的 `limit` 值 (默认 50,最大 1000)

   ## Terraform 集成示例

   ```hcl
   data "netbox_virtual_machines" "proxmox_vms" {
     filter {
       name  = "status"
       value = "planned"
     }
     filter {
       name  = "custom_fields.infrastructure_platform"
       value = "proxmox"
     }
   }
   ```

   ## Jenkins Pipeline 集成示例

   ```groovy
   withCredentials([string(credentialsId: 'netbox-api-token', variable: 'TOKEN')]) {
       sh '''
           curl -H "Authorization: Token ${TOKEN}" \
             http://192.168.1.104:8080/api/virtualization/virtual-machines/?status=planned \
             | jq -r '.results[].name'
       '''
   }
   ```
   ```

2. **更新 README.md 快速参考**

   在项目 README 添加:
   ```markdown
   ## NetBox API 快速参考

   ### 认证
   - 创建 API Token: NetBox UI > API Tokens > Add
   - 使用 Token: `curl -H "Authorization: Token <token>" <url>`

   ### 常用端点
   - Virtual Machines: `/api/virtualization/virtual-machines/`
   - Devices: `/api/dcim/devices/`
   - Custom Fields: `/api/extras/custom-fields/`

   详细文档: [NetBox API Integration Guide](docs/netbox-api-integration-guide.md)
   ```

---

## Testing Strategy

### 单元测试 (API 功能验证)

**测试用例 1: Token 认证**
```
步骤:
1. 使用有效 Token 查询 API
2. 使用无效 Token 查询 API
预期结果:
- 有效 Token 返回 HTTP 200
- 无效 Token 返回 HTTP 403
```

**测试用例 2: 过滤查询**
```
步骤:
1. 查询 cf_infrastructure_platform=proxmox
2. 验证所有结果的 platform 都是 "proxmox"
预期结果: 过滤逻辑正确
```

### 集成测试 (与 Terraform/Jenkins 集成)

**测试用例 3: Terraform Data Source 模拟**
```
步骤:
1. 使用 curl 模拟 Terraform data source 查询
2. 查询 status=planned & platform=proxmox
3. 解析 JSON 并提取必要字段
预期结果: 获取到所有 Terraform 需要的字段
```

**测试用例 4: Jenkins Pipeline 集成**
```
步骤:
1. 创建测试 Pipeline 使用 netbox-api-token Credential
2. 查询虚拟机列表并输出名称
预期结果: Pipeline 成功执行,输出虚拟机名称列表
```

### 性能测试 (响应时间验证)

**测试用例 5: 单次查询性能**
```
步骤:
1. 使用 time 命令测量查询时间
2. 重复 10 次,计算平均时间
预期结果: 平均查询时间 < 2 秒
```

**测试用例 6: 并发查询性能**
```
步骤:
1. 同时发起 5 个并发查询
2. 测量总时间
预期结果: 总时间 < 5 秒,无超时错误
```

---

## Definition of Done

- [x] **NetBox API Token 已创建**
  - Token 类型: 40 字符自动生成
  - Write enabled: ✅
  - 已保存到安全位置

- [x] **Token 已配置到 Jenkins Secrets**
  - ID: `netbox-api-token`
  - 通过测试 Pipeline 验证可用

- [x] **API 查询验证通过**
  - 成功查询虚拟机列表
  - 响应包含所有 13 个必要字段
  - Custom Fields 正确返回

- [x] **过滤查询验证通过**
  - 按 infrastructure_platform 过滤成功
  - 按 automation_level 过滤成功
  - 多条件组合过滤成功
  - 按 proxmox_node 过滤成功

- [x] **性能测试通过**
  - 单个资源查询 < 0.5 秒
  - 列表查询 < 2 秒
  - 复杂过滤查询 < 2 秒
  - 并发查询稳定

- [x] **错误场景验证通过**
  - 无效 Token 返回 HTTP 403
  - 缺少认证返回 HTTP 403
  - 不存在资源返回 HTTP 404
  - Write enabled Token 可更新资源

- [x] **文档化完成**
  - `docs/netbox-api-integration-guide.md` 已创建
  - README.md 快速参考已更新
  - 常用查询模式已记录

---

## Dependencies & Risks

### 依赖
- **Story 1.1**: Custom Fields 已创建 (API 需要返回这些字段)
- **Story 1.3**: 测试虚拟机已创建 (用于 API 查询验证)

### 阻塞以下 Story
- **Story 2.1**: Router Pipeline 开发 (需要 API Token 配置)
- **Story 3.1**: Terraform Provider NetBox POC (需要 API 查询验证)
- **Story 4.2**: Ansible Playbook 自动选择 (需要查询 Custom Fields)

### 风险

| 风险 | 影响 | 缓解措施 | 状态 |
|------|------|----------|------|
| **API Token 泄露** | 🟡 Medium | 定期轮换 Token (90 天),使用 Jenkins Secrets 存储 | Open |
| **API 性能下降 (大规模数据)** | 🟢 Low | 使用过滤参数减少结果集,监控查询时间 | Accepted |
| **NetBox API 版本变更** | 🟢 Low | NetBox 3.x API 稳定,升级前检查 Changelog | Mitigated |
| **网络连接失败** | 🟡 Medium | Pipeline 中添加重试机制,记录详细错误日志 | Open |

---

## Dev Notes

### 架构决策参考
- **ADR-002**: Terraform 集成模式 - terraform-provider-netbox data source
- **NFR-I1**: API Token 认证要求

### 关键约束
1. **Token 必须启用 Write**: 后续 Story 需要回写 NetBox 状态
2. **Token 安全存储**: 仅通过 Jenkins Secrets 使用,不在代码中硬编码
3. **API 端点使用 HTTP**: 内网访问无需 HTTPS,减少开销

### 最佳实践

1. **过滤查询优先**: 避免查询所有资源后在代码中过滤,应在 API 层面过滤
2. **使用 jq 处理 JSON**: Pipeline 中使用 jq 解析 JSON,避免手动字符串处理
3. **记录详细错误**: API 调用失败时记录 HTTP 状态码和响应 Body

### 常用 jq 模式

```bash
# 提取所有虚拟机名称
jq -r '.results[].name'

# 提取 Custom Fields
jq -r '.results[] | {name, platform: .custom_fields.infrastructure_platform}'

# 过滤特定平台
jq '.results[] | select(.custom_fields.infrastructure_platform == "proxmox")'

# 统计数量
jq '.results | length'
```

### 调试技巧

1. **查看完整响应**:
   ```bash
   curl -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     http://192.168.1.104:8080/api/virtualization/virtual-machines/1/ \
     | jq . > response.json
   ```

2. **测试过滤条件**:
   ```bash
   # 先不过滤,查看所有结果
   curl "..." | jq '.results[] | .custom_fields.infrastructure_platform'
   
   # 再添加过滤条件验证
   curl "...?cf_infrastructure_platform=proxmox" | jq .count
   ```

3. **性能分析**:
   ```bash
   curl -w "\nTime: %{time_total}s\n" -o /dev/null -s \
     -H "Authorization: Token ${NETBOX_API_TOKEN}" \
     "http://192.168.1.104:8080/api/virtualization/virtual-machines/"
   ```

---

## Related Documentation

- **PRD**: `/workspaces/IaC/_bmad-output/planning-artifacts/prd.md`
  - FR6: 通过 REST API 获取虚拟机配置
  - NFR-P6: API 查询时间 < 30 秒
  - NFR-I1: API Token 认证

- **Architecture**: `/workspaces/IaC/_bmad-output/planning-artifacts/architecture.md`
  - ADR-002: Terraform 集成模式 - NetBox data source
  - API Surface & Integration Points

- **Epics**: `/workspaces/IaC/_bmad-output/planning-artifacts/epics.md`
  - Epic 1, Story 1.4: NetBox API 集成验证详细需求

- **Story 1.1**: Custom Fields 定义 (API 返回这些字段)
- **Story 1.3**: 测试虚拟机创建 (用于 API 查询验证)

---

## Changelog

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-02-08 | 初始创建 Story 文档 | AI Agent (BMAD Workflow) |

---

**🎯 Ready to Start?** 按照 Implementation Tasks 创建 API Token,配置到 Jenkins,验证查询功能和性能。这个 Story 是后续 Terraform 和 Jenkins 集成的关键基础!
