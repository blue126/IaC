# VM500 与双测试 VM 的 HAPI 应用阶段计划

状态：本页保留双QA应用试点的初始计划。2026-10-31已单独完成独立BWS、固定namespace、VM500单Hub与既有会话数据库迁移，以及三worker私有通道验证；详见[迁移记录](2026-10-30-hapi-single-hub-migration.md)。两QA的employee／Firefox／Claude完整应用基线和新的CF身份发布仍未执行，完整开户及首次个人授权未就绪。

用户已确认并已部署VM500单Hub，见[单Hub评估](2026-10-30-hapi-shared-hub-assessment.md)和[迁移记录](2026-10-30-hapi-single-hub-migration.md)。本页原每VM Hub布局仅为历史，不再作为后续执行输入。两台QA VM于2026-10-31已回收，待发布测试身份提案已归档；后续新员工验收应从干净模板重新provision，见[回收记录](2026-10-31-hapi-qa-retirement.md)。

side chat先把统一入口迁到VM500，主流程随后按授权迁移Hub及数据；origin仍为hapi.willfan.me，未重复切Tunnel。两台测试节点9101／9102及独立state保留，未自动转为正式员工。

## 只读能力核对

通过已验证PVE管理通道，仅对500、9101和9102执行工具／账号存在性查询，没有读取个人认证或启动登录。

| 节点 | 已存在 | 应用阶段缺口 |
|---|---|---|
| VM500 | nginx、Python cryptography、tmux；入口迁移后noVNC和控制面服务也已就绪 | 单Hub、集中会话数据及租户鉴权尚未部署 |
| VM9101／9102 | Python、tmux、基础网络及管理身份 | employee账号、nginx、原生Firefox、Claude、Xvfb／x11vnc／websockify／Openbox等运行基线与HAPI服务 |

已有网络测试只验证VM500来源到9443的真实TCP路径，不代表新`hapi-proxy`服务UID、mTLS、Hub或浏览器授权已验收。正式测试必须使用实际服务账号和证书重复验证；若旧VM500规则阻断，先列精确规则与归属，不临时放开管理网络。

## 已准备的代码

- 新`hapi-workspace-baseline`及独立playbook：只作用于独立新工作VM，建立employee及sudo，配置签名验证的Mozilla原生Firefox源，按精确URL／SHA安装Claude；不读旧WireGuard登记／私钥、不安装Browsh、不开始个人授权。
- `hapi-workspace`和`claude-login-agent`继续负责Hub／Runner、9443受限代理、固定登录执行API、真实tmux／PTY与个人浏览器；入口页面和noVNC资源在VM500。
- 本任务私有`remotecc/hapi-admin/hapi-admin.py`已有基础设施阶段候选入口：申请／预留／精确计划／执行／读回恢复。只标记`infrastructure_ready`；不宣称应用或员工交付完成，主checkout正式绑定及完整服务／发布后端尚未完成。

Firefox源及签名指纹依据[Mozilla官方安装说明](https://support.mozilla.org/en-US/kb/install-firefox-linux)。Claude候选沿用仓库已固定的官方2.1.304原生AMD64产物与摘要；执行前须纳入当前artifact清单，不通过可变installer管道安装，也不复制现有VM个人配置。

## 下一阶段动作与明确边界

| 步骤 | 范围与就绪条件 |
|---|---|
| 应用依赖 | VM500 noVNC已由入口迁移准备；两台测试VM仍缺employee和应用基线。按单Hub布局重新核定Hub／worker包及必要转发，旧包安装提问未得到批准，本任务不安装新增组件 |
| 服务秘密 | 建立独立HAPI BWS项目／最小授权机器身份，批准专用CA、CRL、VM500客户端证书和各VM独立服务token／叶证书。当前连接与项目绑定未就绪，不能借用EmployeeWorkspace机器身份或VM502服务token |
| 私有服务 | 在500安装隔离用户、目录、Unix守卫和loopback代理，在9101／9102部署对应Hub／Runner／执行服务。没有PVE或BWS管理员身份进入公开控制面进程，员工VM不持有Tunnel token |
| 身份 | 用户提供的两个测试邮箱仅存私有待发布映射，分别关联两台测试VM；不写公开仓库、不发送邮件、不自动转为生产员工登记 |
| Cloudflare | 先核对新主机名的DNS／Access／Tunnel占用、账户及权限；批准精确对象后再创建或修改。不得复用旧试点AUD／Tunnel token，也不以配置测试新域名为由修改side chat入口 |
| Subject绑定 | issuer、AUD及每个邮箱的subject必须来自受验证的Access身份；当前subject尚未取得。首次绑定／恢复流程须实现并验收，不能用邮箱、API user ID猜测或伪造subject填配置 |
| 联调 | 两身份各进本人VM、自动HAPI会话、API／SSE／Socket.IO／RFB隔离、撤销／恢复及新VM首次Claude授权。个人授权只由本人发起，不能替员工操作或登出原VM502 |

包与artifact范围：VM500的角色需要`nginx-core, python3, python3-cryptography, novnc`，其中前三项当前已存在；两台VM需基线`ca-certificates, gnupg, sudo, firefox, fonts-dejavu-core, fonts-noto-cjk`，以及服务角色的`nginx-core, tmux, xvfb, xauth, x11vnc, websockify, openbox, dbus-daemon, x11-utils`和固定Claude／HAPI产物。安装遵守`policy_rc_d: 101`，不因包安装启动默认nginx或浏览器。

私有身份文件是`pending_test_identity_proposal`，不是可直接部署的路由快照；当前路由为disabled、subject为空、`public_entry_ready=false`。已有两台网络测试VM不会被基础设施执行器按真实邮箱重新创建或静默认领。

## 先完成的材料与放行

先确认独立BWS项目／机器授权和CF账户／域名对象，封存当前源码与网页构建包摘要，再提供精确服务／秘密／DNS变更和回退。应用依赖、BWS写入、共享控制面部署及CF发布分别沿已明确的授权执行；本计划本身不是生产推广授权。

验收成功后才把应用状态从待配置推进到可测试工作区，并另行准备既有VM逐台迁移。网络35／11通过、基础设施执行器测试通过或收到两个邮箱，都不能替代上述实际应用验收。
