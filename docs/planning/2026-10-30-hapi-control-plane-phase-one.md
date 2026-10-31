# HAPI VM500控制面第一阶段实施计划

日期：2026-10-30。本文保留最初阶段的范围与历史盘点。后续按用户单独授权，已在VM500部署统一入口及单Hub并迁移既有会话数据库，原VM502 Runner保持运行；实际最新状态和授权边界以[迁移记录](2026-10-30-hapi-single-hub-migration.md)为准。两台PVE测试VM的35项通信与11项生命周期检查见[验收记录](2026-10-30-hapi-two-vm-pve2.md)；完整新员工开户未据此自动放行。

本计划对应[独立HAPI开户设计](../architecture/hapi-workspace-provisioning.md)。初始范围是代码、清单及验收／回退准备；后续用户单独授权的两台新VM及测试边界在[两VM记录](2026-10-30-hapi-two-vm-pve2.md)追踪，不据此扩大为既有设备迁移、Cloudflare、凭据轮换或通知权限。

## 1. 已确定的边界

- VM500承载专用cloudflared连接器、身份网关和集中Claude登录引导；统一目标域名为`hapi.willfan.me`。
- 每名员工独立VM运行Hub／Runner／Claude、登录执行服务和Firefox；个人凭据留在本人VM。
- BWS管理服务令牌；本阶段沿用设计中的服务端Hub令牌交换方式，不把“员工VM本机交换”建议作为必须新增的认证系统。网关运行时使用的是具备本人Hub执行权限的服务令牌，必须按秘密处理。
- VM500仅连接员工与本人工作VM；工作VM沿已批准的默认路由出网，不因HAPI新增VM500 NAT或更改默认路由。
- VM500的WireGuard目前仍运行、待退役。OCI迁移与旧网关退役是独立变更，不在本计划中顺带删除旧服务。
- HAPI开户与WireGuard的执行器、申请、台账和凭据授权独立；VM500本体不由两个Terraform state共同管理。

## 2. 证据与现场盘点

证据分为源码、2026-10-30只读现场观察和未核实项。源码声明不能替代生产state，当前观测不代表实施时仍无变化。

| 对象 | 已核实内容 | 对实施的影响 |
|---|---|---|
| VM500资源源码 | `terraform/proxmox/employee-access.tf`：PVE2、2核／2048MiB／20GiB，员工网卡来自`employee_workspaces`；cloud block为`iac-proxmox-lab` | VM500新增网卡必须由当前资源所有者管理，HAPI新state只管理新工作VM；正式变更前回读state资源地址 |
| VM500管理连接 | 登记部署inventory为`ubuntu@192.168.1.140`，使用既有`gateway-host-key.pub`严格校验成功 | 未使用accept-new、未改全局known_hosts、未读取密钥值；HAPI后续单独绑定同一管理传输 |
| VM500现场接口 | `employee-uplink`、`emp0`至`emp7`、`wg-employee`、`wg-oci-home`存在；默认路由经现有上游 | 不能把OCI迁移方向当作VM500旧接口已退役 |
| VM500现场服务 | `wg-quick@wg-employee`和`employee-firewall`为active；已启用员工查看／SSH相关unit；`employee-hapi-tunnel`与`cloudflared`这两个unit未安装 | 本轮未部署新控制面；未穷举所有进程，不能据两个unit缺失断言机器从未运行其他Tunnel |
| VM500监听 | SSH绑定现有管理／VPN地址；8443绑定两条既有VPN地址；未观察到8080或9443监听 | 新控制面可拟用loopback8080，部署前须复查占用；不接管现有8443 |
| VM500现场防火墙 | `employee_access`的input／forward默认drop，存在`employee_nat`及7条masquerade；端口匹配集合包含22／6081／8443／51820 | 9443不在当前匹配集合；结合现有output模板，直接叠加新表不能保证放行，须指定旧表相关路径的变更所有者并做真实连通验证 |
| VM500空闲资源 | 2核、约1962MiB内存，其中约1548MiB可用；根盘约16GiB可用，无swap | 仅瞬时基线；控制面不运行Firefox，仍需上线前测并发及长连接资源，无证据不扩容 |
| VM502网络源码 | `10.231.2.2/30`，默认网关声明为`10.231.2.1`；现场VM500到该地址经`emp1` | 旧网关退役前须保证VM502替代出网路径；本轮未登录VM502确认实时默认路由 |
| HAPI试点源码 | Hub／Runner／专用Tunnel均部署到`employee-control`；VM502仅试点 | 不将单人角色去掉断言后用于员工开户 |
| 登录组件源码 | 侧聊角色和助手已读取并生成逐文件SHA256清单 | 已按`bf4e5bd`提取为当前共享角色并记录源／派生摘要；未合并侧聊分支，部署仍须绑定获批代码版本 |

只读摘要和公钥校验临时文件位于管理员本机`/private/tmp/hapi-control-plane-readonly-20261030/`，包含`vm500-readonly-summary.json`、`known-hosts`和`login-source-manifest.json`。不包含BWS令牌或个人认证。临时目录不是长期部署来源。

本次角色加助手的源码清单指纹为`9807fe1bcc419fbacd51313d64ece61e4539c19ba4ad378c3c322abbda941e44`；这是读取时的源文件指纹，不是已保存部署artifact的摘要，不涵盖全部依赖。

仍待在精确部署计划绑定：VM500生产state归属、现有防火墙完整规则与回退依赖、测试VMID／地址／网络所有者、目标域名和Cloudflare对象实时占用、BWS新授权绑定、实际源码artifact、上游HAPI认证载体。未调用Terraform云端state、BWS或Cloudflare API，也未采集WireGuard peer身份或个人凭据。

## 3. 第一阶段代码改动清单

下表为第一阶段目标，不代表各项均已完成；已实现范围见第8节和[原型配置契约](../guides/hapi-control-plane-prototype.md)。实现保持一台测试VM的范围；独立自动开户在原型与两用户隔离验证后交付。

| 改动 | 拟定位置／归属 | 本阶段完成标准 |
|---|---|---|
| VM500控制面部署与验证 | `ansible/roles/hapi-control-plane/`、`ansible/playbooks/deploy-hapi-control-plane.yml` | 独立账号、目录、loopback监听、版本、受控路由；Deploy与Verify两play；不改旧服务 |
| 身份与Hub会话衔接 | 控制面角色中的网关程序／配置；HAPI前端的最小适配补丁 | Access签名／issuer／AUD／时间检查，预登记身份绑定，CSRF保护的session接口，固定本人后端；补丁与Hub锁定版本一起交付 |
| 工作VM服务配置 | `ansible/roles/hapi-workspace/`、独立部署playbook | Hub／Runner参数化、服务代理9443、逐VM唯一服务令牌、保留默认路由；不调用旧开户入口 |
| 登录组件拆分 | `hapi-control-plane`集中页面、`claude-login-agent`员工VM角色 | 集中页面与noVNC静态资源；固定start／code／cancel／status及RFB接口，真实PTY与已有超时逻辑复用 |
| VM502旧包装兼容 | `employee-browser-entry`及`employee-hapi`已有作用范围 | 保持硬限制和现有入口；提取公共代码只能通过明确源码集成变更，不能直接编辑侧聊工作树 |
| 网络接入 | VM500当前Terraform所有者与实际防火墙所有者 | 先列精确接口／规则差异；测试VM不加入旧员工业务台账，旧规则兼容变更不等于复用旧开户流程 |
| 私有登记契约 | 未来`remotecc/hapi-admin/`与`hapi-data/`接口说明 | 第一阶段仅受控测试登记快照及版本／校验和；不创建假执行器；后续自动化复用同一schema |
| 验证 | 拟定`tests/hapi-workspace/`及服务Verify任务 | 覆盖真实请求归属、跨身份攻击、撤销与恢复；不只检查静态资源200或镜像实现断言 |

共享登录资源由控制面提供，HAPI应用资源在MVP中进入本人VM的服务代理，由锁定网页包提供页面、本人Hub提供API；不额外建设共享前端发布平台。先确认v0.33.2实际认证初始化、SSE及Socket.IO载体，再固定补丁和协议验收；当前文档中的JWT时长不能代替上游代码核验。

## 4. 网络与Cloudflare清单

| 路径 | 拟定实现 | 部署约束 |
|---|---|---|
| Cloudflare → VM500 | VM500专用Named Tunnel连接器 → `127.0.0.1:8080`网关 | 8080为拟定本机端口，重查占用；不开放VM500公网监听 |
| 员工统一入口 | `hapi.willfan.me`，完整主机名Access保护，应用会话168h | 查询精确DNS／应用占用后绑定对象ID、AUD及策略，DNS最后发布；不借用VM502试点AUD |
| VM500 → 工作VM | 受限私网TLS服务入口9443，仅允许指定VM500来源与客户端证书 | 验证目标工作区TLS身份；mTLS失败不能回退明文；不通则修IaC，不开任意SSH代理 |
| 工作VM内部 | Hub3006、登录执行6082、查看6081／RFB5901只在loopback | 无员工VM公网Tunnel，无控制面CA私钥，不发布通用shell接口 |
| 工作VM → 外部服务 | 已批准默认路由及DNS | 不增设经VM500的HAPI NAT；新测试网段须有独立核实的路由和VM外隔离 |
| 公共路径分流 | `/_workspace/session`、`/_workspace/login/*`走控制面；其余受保护HAPI路径到本人Hub | `/api/push/*`先拒绝；完整保留查询／流式／升级语义，同时脱敏日志 |

第一台测试VM可在同一受保护目标入口、仅一个获批测试身份下验收；第二个身份和VM加入后验证隔离。此时VM502原有两个域名继续使用旧Tunnel，不迁移它们来代替测试资源。无获批测试身份和资源绑定时只能完成代码与合成验证。

Access allow名单来自HAPI独立登记。发布顺序是禁用路由 → 精确策略增量与读回 → 启用本人路由 → 协议验收 → 交付。停用先禁路由和关闭本人长连接，再移除Access allow项；其他员工继续可用，旧cookie不能绕过禁用。

## 5. 凭据和服务身份清单

| 凭据 | 管理来源 | 允许的运行位置与权限 |
|---|---|---|
| HAPI逐VM基础令牌 | 独立BWS授权边界，VM502旧绑定不自动迁移 | 本人Hub及VM500受控认证进程；不进浏览器、URL、日志或普通登记快照；它不是仅只读的管理令牌 |
| 短期HAPI JWT | 本人Hub已有`/api/auth` | 认证浏览器与当前会话的受控使用；换账号清理；不能决定后端路由 |
| VM500 Tunnel token | BWS，获批后创建或绑定专用记录 | 仅VM500专用连接器；不向工作VM分发，不与不等价的VM502 localhost后端共用Tunnel |
| 网关客户端证书／私钥 | HAPI服务身份签发流程及BWS记录 | VM500；用途固定，工作VM验证；不能把服务器叶证书当客户端证书 |
| 工作VM服务器证书／私钥 | 同一签发流程的独立叶身份 | 本人VM服务代理；按预期工作区服务名验证，泄漏不赋予其他VM身份 |
| CA签发私钥 | 管理员专用BWS授权 | 仅管理员签发环境；不进入VM500／工作VM；90天叶证书、提前30天续签为拟定参数，吊销机制实现后才能验收 |
| BWS机器令牌／Cloudflare管理凭据 | 管理员环境批准的秘密来源 | 仅部署／计划操作；不交给公开入口进程，不把现有广权限机器账号复制到VM500 |
| 个人Claude OAuth／Firefox profile | 员工本人授权 | 仅本人VM；不进入模板、BWS服务令牌记录或交付邮件 |

Hub本机换票据作为后续可选改进；BWS保存与轮换仍保留。当前方案接受VM500认证进程会使用各VM服务令牌的权限范围，实施须明确文件权限、可访问进程、轮换及泄漏处置。即使改为VM本机换票据，控制面仍可申请本人会话，不能声称消除了集中权限。

## 6. 验收与实施顺序

| 阶段 | 实际动作与验收 | 后续依赖 |
|---|---|---|
| A：代码与合成验证 | 网关／角色／认证补丁及登录拆分，严格协议／身份回归，语法和lint | 使用批准Sandbox作语法／lint及合成验证，生产部署另按精确计划批准 |
| B：精确测试计划 | 固定一台测试VM资源、VM500接口／规则、BWS及Cloudflare对象、代码／artifact摘要、测试身份、回退步骤 | 回读占用和当前归属后才能形成可部署计划；本文件本身不是Terraform plan |
| C：单VM部署与真人授权 | 部署获批资源，验证REST／SSE／Socket.IO／RFB及新VM首次Claude授权 | 不自动登出VM502，不发起模型请求冒充登录；模型验收须在当前范围批准 |
| D：两身份两VM | 错误AUD／过期JWT／伪造身份／跨VM对象访问、换账号、撤销、后端故障、恢复、默认路由及横向隔离 | 退出或停用A不影响B；本人VM故障不回退别人；默认路由出网不依赖新网关进程 |
| E：独立开户自动化 | 执行器、资源／BWS管理、状态机、恢复与网页通知交付 | 以真实运行路径更新skill；此前不能声称已可生产开户 |
| F：VM502迁移 | 单独核实两个域名、Access差异、原Tunnel配置及登录服务版本后切换 | 完成原型与隔离验收后另列精确变更，不与WireGuard退役捆绑 |

必须覆盖网关重启后查询在途状态、不重复start；执行服务自身重启导致流程结束时明确提示重新开始；个人浏览器profile保留。接口用mTLS和固定服务契约认证，不由控制面抓取旧HTML获取每进程页面随机码。noVNC静态版本与执行端协议基线同时固定。

失败状态记录阶段、安全原因码、最后成功点及路由禁用标志。失败恢复须重新验证受影响链路；暂停恢复需明确批准。暂停默认只撤接入，不自动停止Runner或工作VM出网；安全事件的停任务／网络隔离在相应计划中明确。

上线验收不能用合成测试或服务active代替。记录瞬时基线和两用户并发／长连接资源；内存耗尽、流式响应缓冲、身份错误或跨VM访问任一出现即停止推广。

## 7. 回退与VM502迁移边界

- 新控制面验证失败：保持新身份路由关闭，将本次新域名入口拒绝或撤回；只停止本次HAPI控制面服务，不停止旧WireGuard、既有查看入口或VM502服务。
- VM500网络兼容变更失败：按保存的接口／规则精确差异恢复，保留管理员通道；不得`flush ruleset`或恢复一份会覆盖别人并发变更的全机快照。回退前比较基线，发生漂移则先核实。
- 测试VM保留文件和失败证据；删除、凭据轮换／撤销各按计划执行，不以失败为由清空个人数据。其他工作区路由继续服务。
- VM502迁移目标是并入`hapi.willfan.me`。原`hapi-test.willfan.me`和`login-vm502.willfan.me`先继续旧链路，分别保存DNS、Tunnel ingress、Access应用／策略及AUD。新统一入口完成本人HAPI及授权引导正向验收后，将旧域名切为只到新入口的过渡跳转或拒绝，不保留直达旧Hub／浏览器的旁路；过渡方式与旧客户端影响进入迁移计划。
- 不能让同一个Tunnel在VM500和VM502同时使用不同localhost上游来试切换。采用新Tunnel时保持两个独立对象；若复用旧Tunnel，必须先证明全部连接器上游等价，或安排明确的停止／启动切换窗口。
- 切换失败恢复两个旧域名的原DNS／ingress／Access配置和VM502旧连接器，不删除或重建Hub／Runner／个人浏览器。新入口先关闭本人路由，避免两条不一致会话路径。成功后再按批准计划停用旧连接器和撤销旧入口秘密。

## 8. 本次交付与限制

已完成现场只读盘点、源码关系核对、设计／skill同步，以及以下原型：

- `hapi-control-plane`：Access验签、本人路由、票据交换、集中引导页面／noVNC资源、可撤销Unix流与分配指纹桥接；当前断言注销摘要在私有SQLite持久化。
- `hapi-workspace`与`claude-login-agent`：官方Hub／Runner、固定mTLS代理、个人授权Flow及浏览器助手；不配置Tunnel、网络或默认路由。
- 锁定的HAPI前端：自动登录、短票据刷新、身份切换清理及同源“Claude 登录”入口。
- 隔离验证：15项身份／文件权限、16项Nginx／撤销／RFB、6项执行服务／真实tmux回归通过；两份playbook语法与三个角色production lint通过（36文件处理）。网页21项相关测试、完整类型检查、生产构建及Chromium模拟回归通过。

验证Sandbox为`iac-codex-hapi-control-plane-direct-v130`，direct模式绑定本工作树；用户单独批准验证工具安装，无生产凭据额外挂载、homelab放行或端口发布。角色和测试说明见[原型配置契约](../guides/hapi-control-plane-prototype.md)。RFB端点、CLI及浏览器身份服务仍为合成环境，不代表真实员工授权或现网验收。

当前仍缺subject首次绑定、独立自动开户及真实资源验收。`public_entry=true`继续被角色拒绝；同源引导已可在隔离环境使用，但没有创建公网Tunnel。未创建VM、修改生产路由／规则、访问BWS秘密、写入Cloudflare、发信或部署；未退役WireGuard或迁移VM502。下一步是精确测试资源计划与独立开户后端，再执行真实Cloudflare／工作VM／个人授权验收。

本轮skill结构／元数据、显式调用策略、Markdown本地引用及差异空白检查通过；仓库文档契约测试共70项通过，11个离线fixture全部匹配，已登记文档声明检查2项、失败0项。未新增测试，不据文档检查通过宣称服务或网络已实现。环境缺少Go／Hugo，完整站点构建未运行，未安装工具。

## 依据

- [HAPI开户架构](../architecture/hapi-workspace-provisioning.md)
- [VM502试点与BWS运行时说明](../guides/employee-hapi-pilot.md)
- [VM500 Terraform声明](../../terraform/proxmox/employee-access.tf)
- [原防火墙模板](../../ansible/roles/employee-access/templates/nftables.conf.j2)
- [现有HAPI部署入口](../../ansible/playbooks/deploy-employee-hapi.yml)
- 管理员README及已登记inventory／主机公钥仅作本机连接依据，不复制私有申请、设备台账或凭据。
