# Anki Desktop Role 设计文档

**Last Updated**: 2026-03-01
**Status**: ✅ Implemented
**Owner**: Homelab IaC Project

## 背景

`anki` server（LXC 100, `192.168.1.100`, pve0）上除了已纳入 IaC 管理的 `anki-sync-server`（pip + systemd）之外，还手动运行了一个 Docker 容器，提供 Anki Desktop Web UI 和 AnkiConnect API。该容器目前通过 `/root/anki/docker-compose.yml` 手动维护，未纳入 IaC。

本文档描述将其以独立 role（`anki-desktop`）的形式纳入 Ansible 管理的设计方案。

## 设计目标

1. **独立 role** — 与 `anki`（sync server）职责分离，各自可单独部署
2. **幂等性** — 重复执行 playbook 不应重建容器（`pull: missing`）
3. **配置即代码** — docker-compose 以 Jinja2 模板管理，变量可覆盖

## 服务信息

| 属性 | 值 |
|------|----|
| **容器名** | `anki-container` |
| **镜像** | `mlcivilengineer/anki-desktop-docker:main` |
| **端口 3000** | Anki Desktop Web UI（noVNC，无认证） |
| **端口 8765** | AnkiConnect API（无认证） |
| **数据卷** | `/root/anki/anki_data:/config` |
| **认证** | 无（VNC 启动参数 `-disableBasicAuth -SecurityTypes None`） |

## Role 结构

```
roles/anki-desktop/
├── defaults/main.yml           # 默认变量
├── handlers/main.yml           # 容器重启 handler
├── tasks/main.yml              # 主任务
└── templates/
    └── docker-compose.yml.j2   # docker-compose 模板
```

## 变量设计

### `defaults/main.yml`

```yaml
anki_desktop_data_dir: /root/anki
anki_desktop_container_name: anki-container
anki_desktop_image: mlcivilengineer/anki-desktop-docker:main
anki_desktop_web_port: 3000
anki_connect_port: 8765
```

> 无敏感变量，无需 vault 间接引用。

## 任务流程

```
Include role: docker          # 确保 Docker Engine 已安装
  ↓
Create data directory         # /root/anki
  ↓
Template docker-compose.yml   # 生成 /root/anki/docker-compose.yml
  ↓ (若有变更，触发 handler)
docker_compose_v2: present    # 启动容器（pull: missing，不强制拉取）
```

## 模板设计

`templates/docker-compose.yml.j2` 对应现有手动配置：

```yaml
services:
  anki:
    image: {{ anki_desktop_image }}
    container_name: {{ anki_desktop_container_name }}
    ports:
      - "{{ anki_desktop_web_port }}:3000"
      - "{{ anki_connect_port }}:8765"
    volumes:
      - ./anki_data:/config
    environment:
      - PUID=0
      - PGID=0
      - QTWEBENGINE_DISABLE_SANDBOX=1
    privileged: true
    restart: always
```

## 与现有架构的集成

### `playbooks/deploy-anki.yml` 变更

在现有 sync server 部署和验证 play 之后，追加两个新 play：

```yaml
- name: Deploy Anki Desktop
  hosts: anki
  gather_facts: true
  become: true
  roles:
    - anki-desktop

- name: Verify Anki Desktop Deployment
  hosts: anki
  gather_facts: false
  become: true
  tags: [verify]
  tasks:
    - name: Check anki-desktop container status
      community.docker.docker_container_info:
        name: anki-container
      register: desktop_info

    - name: Assert anki-desktop is running
      assert:
        that: desktop_info.container.State.Running
        fail_msg: "❌ anki-desktop container is not running"
        success_msg: "✅ anki-desktop container is running"

    - name: Display Desktop deployment summary
      debug:
        msg:
          - "======================================="
          - "✅ Anki Desktop Deployment Successful"
          - "======================================="
          - "Web UI:      http://{{ ansible_host }}:{{ anki_desktop_web_port }}"
          - "AnkiConnect: http://{{ ansible_host }}:{{ anki_connect_port }}"
          - "======================================="
```

### Docker role 依赖

`anki-desktop` role 通过 `include_role: docker` 确保 Docker Engine 已安装，与 rustdesk 的处理方式一致。该 server 上 Docker 已经安装，`include_role` 对已安装的情况是幂等的。

## 与 ansible-role-architecture.md 的一致性检查

| 原则 | 本设计 |
|------|--------|
| 单一职责 | ✅ anki-desktop role 只管 Docker 容器 |
| 可覆盖的默认值 | ✅ 所有变量在 defaults/main.yml 定义 |
| 透明的依赖关系 | ✅ docker role 依赖在 tasks 层显式 include |
| 安全的密钥管理 | ✅ 无凭据，不适用 |

## 验证方式

```bash
cd /workspaces/IaC/ansible
ansible-playbook playbooks/deploy-anki.yml --tags verify
```

预期结果：
- `anki-container` 状态为 `running`
- 端口 3000 HTTP 可达（状态码 200）
- 端口 8765 HTTP 可达（AnkiConnect 返回 JSON）
