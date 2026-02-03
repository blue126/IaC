# Cloudflare Tunnel 实现 GitHub Webhook 推送触发

> 替代 Poll SCM，实现 Git push 秒级触发 Jenkins Pipeline

## 背景

### 当前问题

当前使用 Poll SCM 每 5 分钟轮询一次 GitHub：

```
┌─────────┐    每5分钟     ┌────────┐
│ Jenkins │ ──────────────► │ GitHub │
│         │  "有新代码吗?"  │        │
│         │ ◄────────────── │        │
└─────────┘                 └────────┘
```

**痛点**：
- 最长 5 分钟延迟
- 无变更时也在轮询，浪费资源
- 不是真正的事件驱动

### 目标方案

使用 Cloudflare Tunnel 让 GitHub Webhook 能够触达内网 Jenkins：

```
┌────────┐   push    ┌────────┐  webhook   ┌────────────┐  tunnel  ┌─────────┐
│  User  │ ────────► │ GitHub │ ─────────► │ Cloudflare │ ───────► │ Jenkins │
└────────┘           └────────┘            │   Edge     │          │ (内网)  │
                                           └────────────┘          └─────────┘
                                                 ▲
                                                 │ 出站连接
                                                 │ (无需开放入站端口)
                                           ┌─────┴──────┐
                                           │ cloudflared │
                                           │ (Jenkins上) │
                                           └────────────┘
```

**优势**：
- Push 后秒级触发
- 无需公网 IP
- 无需开放防火墙入站端口
- Cloudflare 提供 DDoS 防护和 WAF
- 可限制只允许 GitHub IP 访问

## 前置条件

- [x] 域名托管在 Cloudflare（已有）
- [x] Jenkins 服务器可访问外网（已有）
- [ ] Cloudflare 账户可创建 Tunnel（免费）

## 实施步骤

### Phase 1: 安装 cloudflared

在 Jenkins LXC (192.168.1.107) 上安装 cloudflared：

```bash
# 方式1: 使用 apt (推荐)
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update
sudo apt install cloudflared

# 方式2: 直接下载二进制
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# 验证安装
cloudflared --version
```

### Phase 2: 登录 Cloudflare

```bash
# 以 root 或有权限的用户执行
cloudflared tunnel login
```

这会打开浏览器让你授权。授权后会在 `~/.cloudflared/` 生成 `cert.pem` 证书文件。

### Phase 3: 创建 Tunnel

```bash
# 创建名为 jenkins-webhook 的 tunnel
cloudflared tunnel create jenkins-webhook

# 查看创建的 tunnel
cloudflared tunnel list
```

会输出 Tunnel ID，类似：`a]f7b2c3d4-e5f6-7890-abcd-ef1234567890`

创建后会生成凭据文件：`~/.cloudflared/<TUNNEL_ID>.json`

### Phase 4: 配置 Tunnel

创建配置文件 `/etc/cloudflared/config.yml`：

```yaml
# Tunnel UUID (替换为实际值)
tunnel: <TUNNEL_ID>

# 凭据文件路径
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

# 入口规则
ingress:
  # 只暴露 Jenkins 的 webhook 端点
  - hostname: jenkins-webhook.yourdomain.com
    path: /github-webhook/
    service: http://localhost:8080
  
  # 可选：暴露整个 Jenkins (不推荐生产环境)
  # - hostname: jenkins.yourdomain.com
  #   service: http://localhost:8080
  
  # 必须有一个 catch-all 规则
  - service: http_status:404
```

### Phase 5: 配置 DNS

```bash
# 自动创建 DNS 记录指向 tunnel
cloudflared tunnel route dns jenkins-webhook jenkins-webhook.yourdomain.com
```

或者手动在 Cloudflare Dashboard 添加 CNAME 记录：
- 名称: `jenkins-webhook`
- 目标: `<TUNNEL_ID>.cfargotunnel.com`
- 代理状态: 已代理 (橙色云朵)

### Phase 6: 运行 Tunnel

**测试运行**：
```bash
cloudflared tunnel run jenkins-webhook
```

**配置为 systemd 服务** (推荐)：
```bash
# 安装为系统服务
cloudflared service install

# 启动服务
systemctl start cloudflared
systemctl enable cloudflared

# 查看状态
systemctl status cloudflared
```

### Phase 7: 配置 GitHub Webhook

1. 进入 GitHub 仓库 → Settings → Webhooks → Add webhook

2. 配置 Webhook：
   - **Payload URL**: `https://jenkins-webhook.yourdomain.com/github-webhook/`
   - **Content type**: `application/json`
   - **Secret**: (可选，增强安全性)
   - **SSL verification**: Enable
   - **Events**: Just the push event (或选择需要的事件)

3. 点击 "Add webhook"

4. GitHub 会发送一个 ping 事件测试连接，检查是否显示绿色勾号

### Phase 8: 配置 Jenkins Job

修改 Jenkins Pipeline 配置，从 Poll SCM 切换到 Webhook 触发：

1. 进入 Job → Configure → Build Triggers

2. **取消勾选** "Poll SCM"

3. **勾选** "GitHub hook trigger for GITScm polling"

4. 保存

### Phase 9: 验证

1. **测试 Webhook**：
   ```bash
   # 在本地做一个小改动并 push
   echo "# test" >> README.md
   git add . && git commit -m "test webhook" && git push
   ```

2. **检查 Jenkins**：
   - 应该立即看到新的构建被触发
   - 构建日志应显示 "Started by GitHub push by xxx"

3. **检查 GitHub**：
   - 仓库 → Settings → Webhooks → 点击 webhook
   - 查看 "Recent Deliveries"，应该显示成功的请求

## 安全加固（可选）

### 1. 限制只允许 GitHub IP

在 Cloudflare Dashboard → 网站 → 安全性 → WAF → 创建规则：

```
规则名称: Allow only GitHub webhooks
表达式: (http.host eq "jenkins-webhook.yourdomain.com") and not (ip.src in {192.30.252.0/22 185.199.108.0/22 140.82.112.0/20 143.55.64.0/20})
操作: 阻止
```

GitHub Webhook IP 范围可从 https://api.github.com/meta 获取。

### 2. 配置 Webhook Secret

1. 在 GitHub Webhook 设置中添加 Secret

2. 在 Jenkins 中配置验证：
   - 安装 "GitHub Plugin"
   - Manage Jenkins → Configure System → GitHub → 添加 Shared Secret

### 3. 只暴露 webhook 路径

配置文件已经只暴露 `/github-webhook/` 路径，其他路径返回 404。

## Ansible Role 实现

创建 Ansible role 自动化部署：

### 目录结构

```
ansible/roles/cloudflared/
├── defaults/main.yml
├── tasks/main.yml
├── templates/
│   └── config.yml.j2
└── handlers/main.yml
```

### defaults/main.yml

```yaml
---
cloudflared_tunnel_name: jenkins-webhook
cloudflared_hostname: jenkins-webhook.yourdomain.com
cloudflared_service_port: 8080
cloudflared_service_path: /github-webhook/
```

### tasks/main.yml

```yaml
---
- name: Add Cloudflare GPG key
  get_url:
    url: https://pkg.cloudflare.com/cloudflare-main.gpg
    dest: /usr/share/keyrings/cloudflare-main.gpg
    mode: '0644'

- name: Add Cloudflare apt repository
  copy:
    dest: /etc/apt/sources.list.d/cloudflared.list
    content: "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main\n"
    mode: '0644'

- name: Install cloudflared
  apt:
    name: cloudflared
    state: present
    update_cache: yes

- name: Create cloudflared config directory
  file:
    path: /etc/cloudflared
    state: directory
    mode: '0755'

- name: Deploy cloudflared config
  template:
    src: config.yml.j2
    dest: /etc/cloudflared/config.yml
    mode: '0600'
  notify: Restart cloudflared

# 注意: tunnel 创建和登录需要手动执行一次
# cloudflared tunnel login
# cloudflared tunnel create {{ cloudflared_tunnel_name }}

- name: Enable and start cloudflared service
  systemd:
    name: cloudflared
    enabled: yes
    state: started
    daemon_reload: yes
```

### templates/config.yml.j2

```yaml
tunnel: {{ cloudflared_tunnel_id }}
credentials-file: /root/.cloudflared/{{ cloudflared_tunnel_id }}.json

ingress:
  - hostname: {{ cloudflared_hostname }}
    path: {{ cloudflared_service_path }}
    service: http://localhost:{{ cloudflared_service_port }}
  - service: http_status:404
```

### handlers/main.yml

```yaml
---
- name: Restart cloudflared
  systemd:
    name: cloudflared
    state: restarted
```

## 更新 Jenkinsfile

移除 Poll SCM 相关配置（如果有的话），确保使用 webhook 触发：

```groovy
pipeline {
    agent any
    
    // 不再需要 triggers { pollSCM(...) }
    
    // ... 其余配置保持不变
}
```

## 更新 CI/CD 架构文档

部署完成后，更新 `docs/designs/cicd-architecture.md`：

1. 架构图中添加 Cloudflare Tunnel 组件
2. 触发机制从 "Poll SCM" 改为 "GitHub Webhook via Cloudflare Tunnel"
3. 更新延迟说明：从 "最长 5 分钟" 改为 "秒级"

## 回滚方案

如果 Cloudflare Tunnel 出现问题，可以快速回滚到 Poll SCM：

1. 在 Jenkins Job 中重新启用 "Poll SCM"
2. 停止 cloudflared 服务：`systemctl stop cloudflared`
3. 在 GitHub 中禁用或删除 Webhook

## 监控

### 检查 Tunnel 状态

```bash
# 查看 tunnel 状态
cloudflared tunnel info jenkins-webhook

# 查看服务日志
journalctl -u cloudflared -f
```

### Cloudflare Dashboard

- Cloudflare Dashboard → Zero Trust → Access → Tunnels
- 可以看到连接状态、流量统计

## 费用

- Cloudflare Tunnel: **免费**
- 需要域名托管在 Cloudflare（免费计划即可）

## 时间估算

| 步骤 | 时间 |
|------|------|
| 安装 cloudflared | 5 分钟 |
| 创建和配置 Tunnel | 15 分钟 |
| 配置 DNS | 5 分钟 |
| 配置 GitHub Webhook | 5 分钟 |
| 修改 Jenkins Job | 5 分钟 |
| 测试验证 | 10 分钟 |
| **总计** | **约 45 分钟** |

## 参考资料

- [Cloudflare Tunnel 官方文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [GitHub Webhook 文档](https://docs.github.com/en/developers/webhooks-and-events/webhooks)
- [Jenkins GitHub Plugin](https://plugins.jenkins.io/github/)
- [GitHub Meta API (IP 范围)](https://api.github.com/meta)
