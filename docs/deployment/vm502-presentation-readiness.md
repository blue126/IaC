# VM502 桌面前置就绪

Story1–13 的成果、固定安装资产及替代关系见 [完整交付对应](../architecture/vm502-desktop-delivery.md)，日常启停与中断处理见 [桌面生命周期](../guides/employee-desktop-lifecycle.md)。

本入口只维护 VM502 的 presentation。`trust`、`prepare`、`activate` 是显式阶段；准备或静态验证成功不代表桌面已运行，更不代表 Story12 真实 OAuth、中国网络体验或员工 UAT 通过。实机操作由父会话审阅差异后执行。

当前 VM502 已按获准流程完成切换及本人澳洲基本体验。复现本次切换时，先执行 `trust` 核实前端信任，再确认本人会话可停止后执行 `prepare`／`activate`。不安装依赖、不运行完整 employee-workspace 或 oci-hub-spoke role，不修改 workspace-login、VPN、Portal、PVE、VM500 或个人 Firefox profile。

## 输入与材料

使用生产 inventory 之外的单目标 inventory 和受保护运行变量；Ansible 只在本任务独立 Docker Sandbox 执行。材料预先由获准渠道放到目标 VM，入口不生成或轮换身份。

```yaml
employee_desktop_target: vm502
employee_workspace_vmid: 502
employee_desktop_phase: trust
oci_hub_spoke_address: 198.18.53.10/32 # 合成示例，实机必须与已分配 overlay 一致
employee_desktop_frontend:
  address: 198.18.53.10
  certificate: /approved/frontend/server.pem
  private_key: /approved/frontend/server.key
  ca: /approved/frontend/ca.pem
```

前端 CA 必须为 `CA:TRUE`，叶证书具有目标 IP SAN，链、有效期和公私钥必须匹配。输入为 root 所有的绝对路径，禁止符号链接及组/其他用户写入；私钥仅允许 root 或受限组读取。浏览器的根信任安装与原生接入包新 pin 由父会话独立处理。

`prepare` 与 `activate` 另需以下输入。`oci_hub_desktop_backend_basic` 必须通过受保护运行时输入提供，与不可变代次 `authentication.json` 的用户名/密码一致；不把它写进 Git。

```yaml
employee_desktop_config:
  vmid: 502
  viewer_url: https://198.18.53.10:8443/
  materials_root: /etc/employee-workspace/materials
  backend:
    type: kasmvnc
    address: 127.0.0.1
    port: 8444
    client_path: /
    route_enabled: true
    generation_id: g-approved
    tls_server_name: localhost
    trust_ref: generations/g-approved/502/ca.pem
  generation:
    vmid: 502
    trust_ref: generations/g-approved/502/ca.pem
    certificate_ref: generations/g-approved/502/server.pem
    private_key_ref: generations/g-approved/502/server.key
    authentication_ref: generations/g-approved/502/authentication.json
```

后端 CA 为 `CA:TRUE`，叶证书 DNS SAN 为 `localhost`，nginx 和 HAPI 桥均验证 TLS。代次四文件为 root 所有；CA/证书至多 0644，私钥和认证 JSON 至多 0640 且可被 employee 读取，目录可被 employee 遍历。认证 JSON 严格仅含 `username`、`password`。禁止 `latest`、跨 VM 引用及改端口。

## 精确部署面

| 阶段 | 写入或动作 |
|---|---|
| trust | `/usr/local/lib/employee-workspace/presentation/{prepare-desktop.py,frontend.json}`；校验后替换 `/etc/oci-hub/{desktop.crt,desktop.key}`；nginx -t，通过且内容变化时 reload |
| prepare | 同一 root-only staging 目录保存 runtime、unit、桌面 JSON、前端模板和 backend CA；创建 `/etc/tmpfiles.d/employee-desktop.conf`、共享锁与维护标记目录；活动 noVNC 定义、CLI、上游保持原值 |
| activate | 共享锁下拒绝活动 browser/desktop、旧6081/5901监听、外部 profile 写入者和非本入口维护标记；先关闭本 VM nginx 桌面 route，再安装下列文件，验证后开放 |

activate 安装：

- `/usr/local/lib/employee-workspace/{desktop-contract.py,desktop-service.py,browser-service.py}`。
- `/usr/local/bin/{workspace-desktop,workspace-browser}`；保留已有 workspace-login。
- `/usr/local/lib/employee-login-guide.py`，保留既有静态页面及 noVNC 客户端。
- `/etc/systemd/system/{employee-desktop.service,employee-browser.service}` 及 `employee-browser.service.d/desktop.conf`；employee 身份、Restart=no、禁用自动启动。
- `/etc/employee-workspace-desktop.json`；合并 `/etc/employee-workspace-browser.json` 的 `mode=kasmvnc`，保留 HAPI viewer 与其他字段。
- `/etc/oci-hub/backend-ca.crt`、严格现成模板渲染的 `/etc/nginx/conf.d/oci-hub-desktop.conf`，使用 overlay:8443 → localhost TLS:8444。
- employee 的受管浏览器 desktop entry、XFCE WebBrowser 选择及 web MIME 默认；不读取/复制/删除 Firefox profile。

activate 只 reload nginx、更新 systemd 元数据并重启已有 employee-login-guide，不启动桌面/Firefox。失败保留 `/var/lib/employee-workspace/transition.json`，桌面 route 保持关闭；修正原因后重跑同一 activate 前进续跑，不恢复旧栈。不会强杀未归属进程。

## 本机输入与画面

macOS／Firefox 首次连接后，在 Kasm 左侧 Settings 开启 `IME Input Mode`，通过 Mac 本机菜单栏选择拼音输入法；缩放选择 `Local Scaling`，与本入口固定的服务端画面配合。Firefox 使用 Kasm 的 Clipboard 面板传递双向文本。本轮已由本人确认中文粘贴、IME 与画面调整可用；本人同时确认刷新后原会话保留；中国侧体验和 Code/Cowork 具体任务仍待单独验收。设置含义见 [KasmVNC 客户端说明](https://docs.kasmvnc.com/docs/latest/clientside/)。

## 验证与待验收项

```bash
python3 tests/employee-workspace/test-desktop-oci.py -v
git diff --check
# 以下仅在独立 Sandbox，指定合成 inventory/vars 和 tests/ci/fixtures/ansible.cfg：
ansible-playbook -i /tmp/synthetic-inventory.yml playbooks/prepare-employee-desktop.yml --syntax-check
# 实机仅父会话批准的受保护 inventory/vars；phase 必须显式选择：
ansible-playbook -i /approved/single-vm502.yml playbooks/prepare-employee-desktop.yml -e employee_desktop_target=vm502 -e @/approved/presentation-vars.yml
```

实机 activate 后，以 employee 运行 `workspace-desktop status` 应显示 stopped，按需 `workspace-browser start` 后再检查 `workspace-desktop status`、`workspace-browser status`、可信 HTTPS/WSS、HAPI 画面/输入/重连，最后 `workspace-desktop stop`。浏览器本机信任、真实 VM、个人 OAuth 及中国体验结果分别记录。

实际 Kasm/nginx/Firefox/发行版 noVNC 协议实验沿用 `tests/oci-hub/test-desktop-network.py` 的显式 `--execute` 入口、固定 Story10 helper、独立 netns 和合成 HOME；新增 HAPI 分支执行生产 Guide 桥和四控制 API 的合成身份检查。没有实际执行结果时保持“未执行”。
