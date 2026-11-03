# HAPI控制面原型配置契约

> **历史记录（2026-11-03）**：本文涉及的角色、playbook、脚本与测试已在 story 5.24 中删除，员工 VM 一侧改由 `hapi` role管理（默认随`prepare-employee-desktop.yml`的provision／update阶段部署），见[统一入口](hapi-unified-entry.md)。下文命令不可再执行，仅供追溯。

> **当前维护入口（2026-11-02）。** 现网已完成[内部HTTP切换与PKI退役](hapi-internal-http.md)。本页保留早期原型的mTLS、证书／CRL输入和发布门禁契约，仅供历史追溯，不能作为当前部署指令；当前拓扑见[统一入口](hapi-unified-entry.md)。

> **历史配置契约。** 下文保留早期每VM Hub原型及回归依据。现网已迁至VM500单共享Hub，旧工作区角色不是当前生产拓扑；运维以[统一入口说明](hapi-unified-entry.md)及[内部HTTP说明](hapi-internal-http.md)为准。独立开户候选已撤回，不据本文执行开户。

本实现提供VM500的Access身份检查、固定后端路由、Hub票据交换、集中登录引导、可撤销实时连接和独立工作VM的mTLS代理／登录执行服务。对应[设计](../architecture/hapi-workspace-provisioning.md)和[第一阶段计划](../planning/2026-10-30-hapi-control-plane-phase-one.md)。已补齐锁定版本的前端自动登录衔接，并按明确授权将现有VM502所有者试点迁至VM500单一入口；见[实际迁移与验收](hapi-unified-entry.md)。旧独立HAPI开户候选已撤回，不能把该试点部署记作新员工完整交付已验收。

## 运行边界

- VM500的`hapi-control-auth`通过Unix socket提供身份校验与租约守卫；公共Nginx只监听`127.0.0.1:8080`，经守卫和固定Unix桥接Nginx转到工作VM。身份服务／内部桥不能被员工VM直接访问。
- 独立Nginx使用专用配置和systemd unit，不加载或修改系统Nginx站点，也不重启原员工查看、SSH或WireGuard服务。
- 工作VM的`hapi-workspace-hub`／`runner`运行在`employee`账号；`hapi-workspace-proxy`只在批准的私网地址9443监听，API／Socket.IO转到Hub，页面来自校验后的自动登录构建包。Hub3006保持loopback；现有VM502不更换二进制或页面。
- 没有网络／NAT／默认路由修改，没有旧流程调用，没有Terraform／BWS／Cloudflare创建接口。证书、CRL和服务令牌须由批准的管理员流程提前提供。
- `hapi_control_plane_public_entry`必须为false，设为true会在部署开始前失败。当前不安装或启用Tunnel连接器；这是保留在后续阶段的发布门禁。

## 部署输入

仅在已批准的精确inventory中增加`hapi_control_plane`及`hapi_workspaces`组；原型不向生产inventory自动登记。部署仍须单独获批，在已授权执行位置执行；包安装开关只在获准安装时设为true，默认不安装依赖。

| 作用域 | 必须输入 |
|---|---|
| 控制面 | `hapi_control_plane_vmid: 500`、origin、Access team issuer及该应用64位AUD、私有routes快照 |
| 控制面传输 | `vault_hapi_control_plane_ca`、`crl`、`client_certificate`、`client_key`同前缀变量；客户端证书subject固定为`CN=hapi-control-plane`，具clientAuth用途 |
| 控制面服务令牌 | `vault_hapi_control_plane_tokens`，按workspace ID映射本人Hub基础令牌；仅用于运行时交换，不是管理员BWS机器令牌 |
| 工作VM | 已核实VMID（原型排除500／501／502）、`hapi_workspace_id`、bind_address、origin、已有`employee`账号和批准的干净基线 |
| 工作VM前端 | `hapi_workspace_web_archive`为controller本地构建包绝对路径，`hapi_workspace_web_sha256`为其SHA256；二者必填，先核对原包／远端副本及构建元数据再提供页面 |
| 工作VM登录基线 | `employee`账号具批准的本机浏览器管理权限，已装Firefox与Claude；`claude-login-agent`可在明确批准依赖安装时安装tmux／X11／D-Bus组件，不调用原WireGuard开户引擎 |
| 工作VM秘密 | `vault_hapi_workspace_api_token`、`ca`、`crl`、`server_certificate`、`server_key`同前缀变量；服务器SAN必须匹配`<workspace_id>.hapi.internal`，具serverAuth用途 |

CA和CRL为PEM，叶证书满足现代OpenSSL严格校验；同一CA签名不等于获得客户端权限。私钥不会写到默认值／明文inventory，秘密任务关闭diff和日志。原型不签发或自动续签证书；管理员必须提供有效CRL，过期或校验失败不得绕过。

私有routes示例（全为合成值）：

```yaml
hapi_control_plane_routes:
  - workspace_id: alice
    email: alice@example.com
    subject: preverified-access-subject-alice
    enabled: true
    generation: 1
    backend_address: 10.77.0.2
    backend_name: alice.hapi.internal
```

后端只接受RFC1918 IPv4及固定9443；工作区ID、邮箱、subject、后端地址和TLS名不能冲突。用户请求不能选择VM。原型要求subject已核实绑定，尚未实现“只填邮箱后首次自动绑定”；不能填占位subject后声称可交付。

## 已实现接口

| 接口 | 契约 |
|---|---|
| 私有`GET /authorize` | 验证Access RS256 JWT和当前登记，返回固定upstream／TLS名及绑定票据／分配／有效期的签名租约；Nginx内部子请求使用，公网不可直接调用 |
| 同源`GET /_workspace/identity` | 返回工作区、路由代次、不含邮箱的身份摘要及与当前票据／工作区绑定的CSRF值；不缓存 |
| 同源`POST /_workspace/session` | 正文只能为`{}`，要求精确Origin、JSON及CSRF；由本人Hub经mTLS返回短期JWT，交换后再次检查路由仍有效 |
| 同源`POST /_workspace/logout` | 正文`{}`、Origin及CSRF要求同session；撤销当前Access断言的本地接入，哈希和到期时间写入私有SQLite，进程重启不恢复该断言；不注销个人Claude |
| 同源`/_workspace/login/` | 集中页面、CSS／JS及noVNC客户端；固定操作经本人路由到VM的6082，远程画面经`websockify`固定到本人VM的6081 |
| 私有`GET /health` | 仅证明配置／进程可用，明确`public_ready=false`，不证明后端、SSO或生产验收 |

JWT密钥仅从配置的Access team HTTPS certs入口读取，不跟随重定向或用户提供的jku；缓存5分钟，未知kid刷新限流，过期缓存或取钥失败拒绝。轮换新kid的短暂限流可能导致拒绝，不能以放宽验签解决。

HAPI长期基础令牌由BWS提供并仅供本人Hub及控制面认证进程使用；浏览器得到短期票据。网关进程持有多VM认证权限的范围仍存在，不能将BWS存储或mTLS描述成消除了这个影响。

## 一次入口验证后的自动登录

员工只完成一次Cloudflare Access身份验证。页面先调用`/_workspace/identity`，通过后自动从`/_workspace/session`取得本人Hub短期票据；初次进入、票据刷新或网络恢复均不显示HAPI token输入框。Access失效时显示“重新验证入口”，不降级成第二套HAPI登录。

定制构建忽略URL中的token／Hub／Telegram参数和旧长期token存储；后台地址固定为当前origin。短期票据仅在页面内存中使用，不写URL或localStorage。身份轮询保留同一身份的引用，普通检查不重建ApiClient；刷新后ApiClient继续读取当前票据。

首次使用或身份／路由代次变化时，先移除旧应用并清理本origin的localStorage、sessionStorage、CacheStorage和IndexedDB，注销旧service worker；保留Cloudflare cookie，因此清理应用状态不要求再次邮件验证。账号切换用完整文档导航丢弃模块级消息缓存；离开／回到页面时先隐藏旧工作区并核验身份。个人Claude凭据仍在本人VM，不受浏览器清理影响。

当前网页不注册离线service worker。浏览器清理负责本页状态，服务端另按下节租约机制撤销现有流；两者分别验证，公网发布门禁继续保留。

构建入口及锁定源码见[构建说明](../../scripts/hapi-workspace-web/README.md)。本轮21项相关前端测试、完整类型检查及生产构建通过；Chromium针对真实构建页面的loopback模拟网关回归验证自动进入、账号切换、会话失效／恢复，原`/api/auth`请求数为0。没有使用真实Access或Claude账号。

本轮最终网页包在当时批准Sandbox（已退役）的`/tmp/hapi-workspace-web-artifact-r3-20261030/`，SHA256为`785d2192cef097b4dcb4df7cfb2ac06c2f500ce029fdb291b6741754c60721b9`；provenance已核对与当前补丁／overlay一致。Chromium模拟回归截图在`/tmp/hapi-workspace-web-browser-r3-20261030/`，不含真实员工数据。构建有上游Browserslist、字体路径及包体积提示，未为消除提示升级依赖。

## 集中登录与服务端撤销

HAPI页面新增同源“Claude 登录”入口；不另开Access应用或域名。VM500只提供页面和noVNC资源，不运行个人Firefox。员工VM的`claude-login-agent`以employee运行固定status／start／code／cancel接口，复用已实现的Flow、真实tmux／PTY及浏览器助手。新共享角色中的来源与派生文件摘要曾记录在`claude-login-agent/source-provenance.json`（该角色已于2026-11-03删除），没有修改或合并侧聊工作树，也没有修改原VM502包装。

页面每次读取状态或操作前核验当前身份和分配；失去前台时断开查看，身份变化时清空旧画面／未提交内容，停止向旧VM发送操作。写操作仍要求精确Origin及本次身份／代次的CSRF，授权码只经有界JSON正文和私有stdin／tmux缓冲，不放URL、日志或磁盘队列。8KiB以内请求使用16KiB内存缓冲规范化HTTP framing，不落客户端正文临时文件。WebSocket固定转发，不接受目标参数。

服务端链路为公共Nginx → 签名租约Unix守卫 → 固定Unix桥接Nginx → 本人VM mTLS服务。守卫不解析响应或TLS，不替代Nginx的HTTP实现；它仅移除内部租约头、验证当前分配并转发有界字节。租约绑定当前Access断言哈希、完整分配指纹及其`exp`。守卫每250ms检查登记与撤销状态，停用、改归属／后端／代次、票据到期或本地注销都会关闭已建立的对应连接；损坏／缺失登记关闭现有连接并拒绝新请求。

桥接Nginx还核对期望分配指纹，登记先更新、Nginx尚未reload的窗口返回409，不会把新身份送到旧后端。常规登记变更不重启认证进程；代理配置只reload，其他员工现有流不被主动关闭。修改issuer／AUD／origin等信任根或认证程序才重启服务。认证进程重启时内核关闭旧流，注销哈希保留在`/var/lib/hapi-control-plane/revoked.sqlite3`，不得当缓存删除。

注销接口的范围是当前Access断言，不是一个跨断言更新的完整浏览器会话平台；浏览器换账号也会关闭本页旧连接。外部IdP或Cloudflare控制台单独撤销不会自动修改本地登记，正式停用仍须先禁本地路由、断连接，再同步Access策略。证书撤销也须先禁对应路由，再更新CRL／代理配置。当前没有自动跳转Cloudflare退出端点，因为官方说明该退出会影响跨应用会话，参见[Cloudflare会话管理](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/)。

隔离测试验证已打开SSE／WebSocket被切断，Bob仍可在原连接中收发；测试断开上限为3秒，不代表真实Cloudflare链路的时延承诺。完成授权后再自然过期或切换认证来源时，状态会重新变为可重试／未知／阻断，不会一直误显示成功。取消／超时及接入撤销不自动停止日常Firefox、Runner或VM出网；永久退役仍使用单独计划。

## 上线前剩余条件

- 自动登录已在锁定网页构建中实现；真实Cloudflare应用、工作VM和浏览器的端到端验收仍待执行，现有VM502继续使用旧入口直至迁移。
- 本地票据／登记驱动的撤销已实现，真实Cloudflare、多设备会话、PKI轮换及现网故障恢复仍待验收；不把代理空闲超时当作撤销。
- 集中页面与VM执行服务拆分已实现；真实新VM的Firefox／RFB、首次或自然过期Claude授权仍待本人验收；测试RFB端点与CLI均为合成环境。
- 首次subject绑定、Access策略同步、证书签发续签、独立开户执行器、邮件交付、真实VM网络隔离及两用户端到端验收。
- Tunnel部署与VM502两个旧域名迁移。原型没有任何新公网入口。

这批代码只交付身份／代理基础切片，第一阶段整体仍在实施。应继续完成精确测试资源计划、独立开户后端和真实网络／个人授权验收，再考虑批准发布。

## 依据与验证

- [测试说明](../../tests/hapi-workspace/README.md)
- [HAPI v0.33.2认证接口](https://github.com/tiann/hapi/blob/v0.33.2/hub/src/web/routes/auth.ts)：基础令牌换取4小时Hub JWT。
- [Nginx auth_request](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html)：身份子请求放行／拒绝机制。
- [Nginx代理模块](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)：TLS验证、CRL、流式及代理配置。


## 提交前审核修正

路由快照先经`hapi-auth.py --check`校验候选文件，成功后由Ansible原子替换，避免新增员工的错误配置污染正在服务的登记。完整Nginx夹具使用真实Ansible渲染，覆盖实际filter与Python指纹的一致性。重复的session CSRF请求头已删除；仅远程画面的三跳代理使用1800秒空闲读超时，其他应用路径保持60秒，撤销仍受租约约束。

`reset()`失败时显示重新验证入口、以及本地注销API尚无前端按钮，仍为明确的原型限制；不把Cloudflare跨应用退出作为自动恢复措施。角色不发布Tunnel，真实网络和个人授权验收仍未完成。
