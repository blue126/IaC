# 员工工作环境部署与用户验收记录

## 当前范围

用户2026-10-21明确要求完整部署并完成用户验收；选定独立pve2，中国网络测试，管理员预配每设备接入包；提供Windows/macOS/Linux指引。沿用员工sudo、固定目标双会话SSH/SFTP、1A/2A、停用保盘。个人Claude由本人登录。

已提交基础代码：c9fb840。部署所需新增改动未自动提交、推送、合并。

## 执行环境

- 独立direct Sandbox：iac-employee-claude-deploy-direct-v130。
- 工作树：/Users/weierfu/.codex/worktrees/employee-claude-architecture/IaC。
- 只读HCP凭据挂载，TF_CLI_CONFIG_FILE显式指向已批准的挂载文件；既有iac-proxmox-lab已初始化。
- 自动审批拒绝整段LAN放行后，改为仅pve2的8006/22，policy check allowed。原验证Sandbox未变更。

## 已核实的现场事实

- pve2 API与Vault管理SSH可用，PVE 9.2.2；无/etc/network/interfaces.new待应用配置。
- 节点总内存约378GiB，可用约333GiB；mainpool可用约482GiB。
- 管理/uplink为vmbr0，192.168.1.52/24，经192.168.1.1。
- 既有VM100/101/102/103、CT120、VM250；未看到模板或节点备份作业。
- local内容为iso/import/vztmpl/backup，无snippets；专用hook存储与干净模板须先准备。
- 已有Ubuntu26.04 cloud image，SHA256与仓库固定的8196be9d7958059cb56c6c75c80fdf6cee8a8885bc149ea791d7db1c7ef93035一致。
- bpg0.70.0不提供storage_directory资源，具备VM template与vendor-data支持；PVE宿主已有nft。

## 尚未完成

网关及两台员工VM已部署，基础服务与服务端接入/网络检查已通过。用户已确认客户端成功连接，并通过基础终端与断线重连文件保留检查；仍待文件传输、真实任务、本人OAuth及其余现场CAP，整体验收未完成。


## 部署进展及现场修复

- 用户已单独批准路由器仅新增WAN UDP51820到192.168.1.140:51820，及10.231.1.0/30、10.231.2.0/30经192.168.1.140。实际nft/路由验证通过；前后WAN、DNS、dnsmasq与qnetd仍正常。
- pve2专用employee-snippets已创建并验证；定向14项新建已成功，无现有资源更新/删除。VM9000干净模板从未启动，网关VM500运行，员工VM501/502最初保持停止。
- 网关和PVE实际策略校验已通过，网关MAC固定接口与受控公网出口已配置。cloud-init只有PVE生成user字段的DEPRECATED提示，无业务错误；bootstrap明确只允许这一非业务类别，其他错误继续失败。
- 公司每设备SSH/WG和第二段系统密钥已分别生成，新增4项加密Vault变量；没有生成或读取个人Claude凭据。Windows/macOS/Linux指引改为管理员预配包。
- 官方Claude稳定版2.1.304，linux-x64 SHA256 ea0f135784631619a7a409d07322ecec964f9cc4fd377508ed1ba3f141f27912；manifest签名及官方密钥指纹校验通过。
- 启动计划最初额外包含模板继承vga serial0到空配置的归一化，原范围核对漏检该字段，触发bpg0.70.0非必要qmreboot。VM502已运行、cloud-init完成、QGA及管理员SSH可用，但其初启时QGA未安装导致重启worker等待。已仅对本任务Terraform进程发SIGINT，并取消精确核实的VM502/root@pam/qmreboot UPID；VM502仍运行，磁盘未改。补显式vga serial0并强化后续计划全部字段核对，不把原启动计划说成纯标志变化。
- 协调线程转来用户对call_24d59614f66b4ec68fe28accfc47071f的答复：按现有默认保留/不保留行为，不新增留存或删除设置。当前IaC为持久home/磁盘，未配置注销或凭据清理；个人账号由本人操作，不等同于所有员工已同意。中国网络实际UAT尚未通过，不标完成。

- 随后收到用户直接答复：本次由用户本人测试，已同意既述个人登录态及磁盘管理员可读/默认保留安排。仅适用于该测试者，不代表其他员工同意，不新增留存设置，不代本人登录或读取/传送令牌。

## 服务端检查与客户端交付进展

- 保留继承serial0后的定向apply成功：0新增、2更新、0销毁，VM501/502运行。完整部署后Verify原argv布尔值修正为字符串'true'，实际sudo与Claude版本检查通过。
- 实际网关回环入口SSH/SFTP共9项通过，覆盖设备目标映射、sudo/版本、文件往返、同员工设备共享、跨员工隔离、任意远程命令拒绝、转发拒绝及未登记密钥拒绝。此结果不代表中国侧WireGuard路径已通过。
- 两台实际员工VM共20项IPv4/DNS/公网出口检查通过，9项正向对照可用；包括真实有效公网DNS响应、开发HTTPS和出口114.76.119.2，以及家庭/PVE/其他员工/网关管理及私网DNS阻断。初版DNS探测编码问题修正后重新运行通过。
- ed-pilot-client接入包已生成并提供本机私密链接；SHA256为54b738f6d69f2c92486e2a1a296e42645710548982328de94cba1d534654d830。用户反馈需要具体操作指引，尚未确认取得文件或连接。
- 用户已明确授权只读核对willfan.me旧员工Access应用及关联Tunnel。使用现有连接的隐式账户、限定willfan.me查询Access应用，连接返回HTTP403/缺少access.read；未取得应用清单，不能将空列表视为不存在。未修改Cloudflare，也未通过枚举其他账户绕过。需要连接具备Access: Apps and Policies Read后继续核对。

## 2026-10-22 用户手工验收反馈

用户本人确认连接成功；按逐项指引完成whoami、hostname、免密sudo、Claude版本及文件写入检查，均通过。退出并重新连接后文件仍在；输入回显流畅，无明显卡顿。以上为用户手工反馈，没有据此推导量化延迟、长期稳定性、全部客户端兼容或整体CAP已通过。下一步带用户验证SFTP下载和上传，再推进本人OAuth与真实代码任务。

## 2026-10-22 试点终端浏览器安装

- 用户明确要求立即安装。仅在employee-pilot安装Browsh 1.8.2和Mozilla Firefox 158.0.1，以及运行依赖/中文字体；没有扩散到其他员工VM、网关或模板。员工自主管理工具的决定未改变。
- Firefox使用Mozilla官方APT源，核对签名主指纹35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3；仅为Firefox相关包设置该源优先级。Browsh使用官方v1.8.2 AMD64静态包及同次发布checksums中的SHA256。v1.8.3发布页只提供XPI/源码，未虚称安装其Linux二进制。
- 临时可重复部署入口为tmp/employee-deploy/install-pilot-browser.yml，限employee-pilot；版本读取通过。现代Firefox对Browsh控制操作要求remote-allow-system-access，为Browsh专用Firefox启动器加入该参数；没有关闭浏览器沙箱或放开网络规则。启动器及真实二进制在/usr/local/lib/browsh/，用户入口/usr/local/bin/browsh。
- 已以UID1001 employee在真实PTY和独立临时HOME/浏览器配置启动Browsh，example.com页面文字实际呈现，退出码0；兼容修复后未再出现System access is required错误，两项断言通过。第一次验证脚本缺控制TTY的问题已修正，没有将该次失败算浏览器可用。
- 安装/验证日志位于部署Sandbox的/tmp/employee-install-pilot-browser-compatible.log与/tmp/employee-pilot-browser-smoke-compatible.log。只使用公开页面，没有访问个人浏览器配置、账号、验证码或OAuth令牌；个人Claude登录和登录页兼容仍待本人实测，整体验收未完成。

## 2026-10-22 全部员工VM授权浏览器基线（当前要求）

- 用户要求所有员工VM具备同一登录方法，并在指引写明；此要求取代仅pilot安装的范围，限员工工作VM。其他项目工具仍由员工自行管理。
- employee-workspace角色新增tasks/browser.yml并由main.yml自动包含，正式部署playbook增加浏览器Verify和employee_browser标签。现有及后续新建的启用员工VM安装相同浏览器环境，模板不包含个人登录态。
- 正式playbook实际安装：pilot 18项ok/changed=0，control 18项ok/changed=8。初次Verify发现跨play的角色默认变量不可见，已改为方案固定账号employee；保留该次失败。修复后两台VM各4项sudo、Claude、Firefox、Browsh检查全部通过且changed=0。
- 新安装的control以employee UID1001、独立临时配置和真实PTY验证公开页面呈现，Browsh退出0、没有System access is required，两项断言通过。pilot此前的相同修复后检查已通过，没有重复更改个人浏览器配置。
- 21个相关文件Ansible lint 0failure/0warning，syntax及24项离线契约通过，宿主git diff --check通过。Sandbox无法解析宿主linked worktree common Git路径，该项改在宿主检查，没有改Git拓扑。
- 三份平台指南完整说明两个SSH窗口、claude auth login、Browsh地址栏打开该次授权URL、本人验证和同意、回调或授权码、auth status及失败反馈。固定网页登录页不代表CLI授权。本人OAuth、实际代码任务及未反馈的SFTP手工验收仍待继续。
- 新employee-ed-pilot-client-v2.zip仅更新三份指南和README，所有接入身份、凭据、配置和脚本与原包逐一字节比较相同，原包未改。v2 SHA256：22213be51eefc23d28f7f9a4e081b8a69822e7dacdcdd2404149a309ff7b17f0。无需重新导入WireGuard。
- Sandbox日志：/tmp/employee-browser-baseline-all-vms.log（保留最初Verify失败）；/tmp/employee-browser-baseline-verify-fixed.log（最终通过）；/tmp/employee-browser-control-render.log（control真实终端渲染通过）。只读帮助预检因sbx inspect exec deadline未取得结果，调用已结束，不作为登录证据。
- 改动未提交、推送或合并。

## 2026-10-22 CPU型号遗漏修正（待执行生效）

- 用户指出VM使用qemu而非host。PVE当前配置与实际QEMU进程核实：网关500、员工501/502和模板9000均为qemu64，三台运行VM的进程参数也为qemu64。
- 根因：本任务直接声明bpg VM资源，仅设置cpu.cores，遗漏cpu.type；没有继承仓库两个通用VM模块的host默认值。不是已批准的迁移兼容设计。三个资源定义现已显式type=host。
- startup.tftest.hcl增加实际计划值断言，覆盖网关、模板及全部员工VM的cpu.type，避免只检查源码字符串。
- 首次定向计划的严格全字段核对抓到网关继承的disk.discard=on会被遗漏字段归一化为ignore；没有apply。已显式保留on，再生成计划，核实仅四项cpu.type从qemu64到host，其他CPU参数、磁盘、网络、内存、启动标志均不变；零新增、删除和替换。
- 审查后的私密saved plan在本任务部署Sandbox /home/agent/.local/state/employee-deploy/cpu-host-preserve-disk.tfplan，对应JSON/log同前缀保存。未执行apply。
- 已核对固定bpg v0.70.0官方源码：CPU块变化设置rebootRequired=true，更新后调用RebootVM；不是仅写入无中断的待生效值。已向正在验收的用户确认执行时机，说明三台运行VM逐台重启、WG/SSH中断并需先保存工作；模板不启动。执行时须parallelism=1，避免网关重启与员工启动边界hook并发。
- 后续生效必须再次核对PVE当前配置和实际QEMU进程的CPU参数，并复验访问服务；不得把源码修正、mock通过或saved plan当作运行CPU已改。

- 最终独立夹具结果：Terraform validate、fmt通过；17个mock场景通过（含host CPU计划值断言），failed=0、errored=0、skipped=0；宿主git diff --check通过。运行CPU仍未更改。

## 2026-10-22 CPU修正已实际生效

- 用户明确回复现在执行、工作已保存后，重核同一saved plan并以parallelism=1串行apply，结果0新增、4更新、0销毁。实际顺序为模板9000、control502、pilot501、网关500；模板保持未启动。
- PVE --current配置现为四个对象cputype=host；三台运行VM的实际QEMU -cpu参数均为host,+kvm_pv_eoi,+kvm_pv_unhalt，不是仅将修改留在pending或只改源码。核心数仍为2。
- 三台VM的管理SSH连接全部恢复。正式Verify：网关6项、两个员工VM各4项均通过，changed=0，涵盖PVE/网关实际隔离策略及routing、sshd转发限制、WireGuard/受管SSH服务、sudo、Claude、Firefox和Browsh。
- 仅确认用户先前创建的/home/employee/work/acceptance/uat-persistence.txt仍存在，没有读取个人浏览器配置或凭据。此次CPU修正完成，个人OAuth和其余UAT仍继续。
- 新证据位于部署Sandbox：私密cpu-host-apply.log、/tmp/employee-cpu-host-live-inspection.log、/tmp/employee-cpu-host-post-verify.log。未提交、推送或合并。

## 2026-10-22 单命令首次登录助手已部署

- 用户批准workspace-login方案，继续使用普通claude auth login与本人VM内授权，不改setup-token，不从其他电脑导入个人令牌。
- 增加角色files/workspace-login.py、open-auth-browser.sh及tasks/login.yml，main.yml自动包含，正式Verify支持workspace_login标签。两台员工VM各ok=7/changed=3，安装及--check均通过；后续新建VM沿用相同角色。
- 助手检查已有订阅登录；有效则显示认证状态。未登录时启动独立私有tmux服务器，调用官方CLI并通过BROWSER打开机制自动把授权URL交给Browsh，在同一SSH窗口显示；回调成功后核对claude.ai认证来源并返回。授权码可退出浏览器后在同一窗口输入；取消只结束自己创建的会话和进程，不清除已有凭据，也不覆盖API key/外部令牌来源。
- 已用Claude 2.1.304、空白临时HOME/配置实测BROWSER调用，当前原生授权主机/路径是claude.com/cai/oauth/authorize。助手只接受已核实的当前/兼容官方授权目标，不接收任意URL；不记录完整授权URL、授权码或令牌。临时tmux历史限制为0，状态文件只存流程结果。
- 9项真实PTY/tmux合成测试通过：成功、已登录、同窗授权码、取消保留另一tmux服务器、SIGTERM及子进程清理、非法URL、CLI失败、其他认证来源保留、状态异常不泄漏stderr。测试用假CLI/浏览器，不联网、不使用个人账号。重放入口tests/employee-workspace/test-login.py；当前实测由tmp/employee-deploy/login-helper-tests.yml在control已有tmux环境执行。
- Python/Bash语法、正式playbook syntax及相关23个Ansible文件lint通过，0failure/0warning。没有为测试安装Sandbox依赖。
- 已安装助手与真实CLI/Browsh/Firefox的空白配置实测通过：两个内部窗口自动建立；真实Browsh和firefox-bin运行；页面包含登录表单文字，未观察到人机验证提示；取消后exit=1（表示未登录）、0个自有活跃子进程、0个残留临时会话。不输入账号、不完成授权、不读取本人配置。首次检查因只识别firefox而未识别Mozilla实际firefox-bin而失败，已正确识别实际进程名并重新通过，没有降低进程/清理断言。
- 真实连通最终日志：部署Sandbox /tmp/employee-workspace-login-native-check-final.log；部署日志/tmp/employee-workspace-login-deploy.log。原失败日志/tmp/employee-workspace-login-native-check.log保留。
- 三个平台指南现为workspace-login单命令，包含本人页面操作、正常回调、授权码、退出/取消及故障反馈；管理员说明和测试README同步。v3接入包只更新指南及README，凭据和连接文件逐一字节比较与原包相同。SHA256 f3463f578d711ef4f8a5d122ba6e127467f6c3421a0dbbb4932fb5768f92b3ca，原包/v2保留，无需重新导入WireGuard。
- 助手实现与匿名连通验证完成；本人OAuth、真实代码任务、未反馈的SFTP及其他未完成CAP仍不标通过。改动未提交、推送或合并。

## 2026-10-22 本人报告Browsh无法输入，授权交互验收失败

- 用户截图显示登录正文空白、敲字无反应。此前原生连通检查只匹配标题/文本中的sign in/continue/email，不能证明表单可见或可输入；先前“显示登录表单”的表述撤回，实际本人OAuth从未通过。
- control VM使用新建匿名配置在80x24复现：地址栏收到测试文字，正文错位且混入隐藏导航；PageDown出现空白，Tab/单色/小步滚动/实验文本可见性均未产生可靠邮箱输入。临时布局CSS虽移动部分按钮，仍未验证不提交测试标记能进入邮箱框；未部署这些实验配置。
- 独立原生Firefox对照显示可见email输入框；使用原生点击和ElementSendKeys输入不提交标记后，实际DOM值匹配true。匿名截图在部署Sandbox /tmp/employee-anonymous-firefox.png；没有登录、发送邮件或提交表单，没有读取/修改pilot在用会话。该结果不等于图形查看通道已交付。
- 官方v1.8.2 ui.go的overlayCallToSupport确认Unsupported version是捐助提示，不是浏览器/扩展版本检测，未据此盲目升级。源码与临时检查路径保留在本任务tmp/employee-deploy/。
- 已修正临时原生连通检查输出字段为page_title_or_text_mentions_login，并显式login_form_interaction_verified=false，保留其自动URL交付/会话清理原有有效范围。三平台指南加入当前已知交互问题，接入Agent仓库草案同步，不能报告Claude就绪。
- 已准备docs/planning/employee-workspace-browser-auth-change.md，建议仅本人授权时提供澳洲VM内原生Firefox图形窗口，私网入口仅既有WireGuard登记设备、固定到本人VM，不开放公网VNC/RDP或SSH转发。现有SPEC明确一次性图形也未批准，已就新组件和私网入口向用户请求明确范围选择，尚未部署。
- GitHub接入项目仍为设计草案，未创建/推送仓库。当前修复工作等待入口方案选择，原个人账号/项目/SFTP等UAT未标通过。

## 2026-10-22：图形授权例外已批准并部署

用户在 Browsh 空白／无法输入复现后，以“你赶紧改吧”明确批准仅本人授权期间的图形 Firefox 提案。现已部署至 gateway VM500、pilot VM501、control VM502；三平台员工指南和独立更新入口 deploy-employee-auth.yml 已同步。个人 OAuth 仍未代用户完成。

- 员工 VM：Ubuntu 仓库提供 Xvfb、xauth、Openbox、x11vnc、noVNC、websockify，使用既有 Mozilla 原生 Firefox。workspace-login 继续以 employee 运行官方 CLI，BROWSER 自动将当次 URL 交给 VM 内 Firefox，SSH 终端显示固定私网查看地址。专用 profile 保存在个人 VM，不放模板；30 分钟上限，完成／取消／终端断开后关闭本次进程。
- 网关：独立 employee-auth-viewer systemd/nginx，仅绑定 10.230.0.1:8443；默认 nginx 服务已 stopped/disabled，不新增 80/443、LAN／公网 VNC/RDP 或路由器映射。客户端 HTTP/WebSocket 位于已加密 WireGuard 内。按登记 WG 地址固定映射 VM；拒绝未知设备、错误 Host、异源 WebSocket，自选目标参数无效。
- VM 后端：VNC 只在 loopback 5901，X11 不监听 TCP，临时 websockify 仅绑定所属内部地址 6081。网关 nft 只增加启用设备到本机 8443、网关到所属内部 VM 6081 及已建立回包；WG 直达 VM、员工跨网段及管理面隔离未放宽。
- 停用路径：已部署 viewer 时，实际 disable 任务先更新身份映射并重启 viewer，终止已有 WebSocket；然后执行既有 WG／SSH 撤销，员工停用继续 VM 外断网／停机保盘。映射更新会使当时所有授权画面短暂断开。

实测证据（均为空白个人配置、未提交账号）：

| 检查 | 结果与范围 |
| --- | --- |
| 真实 WG → 网关 → WebSocket/RFB → Firefox | control 登记设备实际点击邮箱框，输入 INPUT_PROBE_NOT_SUBMITTED；从独立匿名 Firefox DOM 核对值一致，截图确认显示正常 |
| 静态客户端 | vnc.html、app/ui.js、core/rfb.js 经固定映射均正常，追加目标查询仍进入 control |
| 异源及会话撤销 | 异源 WebSocket 返回 403；临时撤销 control 测试设备 viewer 映射后，已有连接关闭，新请求 403；随后已恢复正式映射 |
| 跨员工真实正反对照 | control 短时匿名后端可达且所属设备返回 200；另一员工备用 WG 设备即使指定 control 目标，也只进入其自身无活动会话的后端，返回 502，无法得到 control 标记；fixture 已自行关闭 |
| 真实 native Claude | 空 HOME 的 workspace-login 调起真实 Claude/Firefox、显示私网 URL；取消后自有图形进程为 0、临时会话为 0 |
| 合成流程回归 | 真实 PTY/tmux 的 9 项通过；含完成／取消／SIGTERM、本人订阅复用、手工码同窗输入、非法 URL、其他凭据来源保护 |
| 原有网络隔离复核 | 两台 VM 的 20 项检查、9 个可达正对照通过，公网开发／DNS／澳洲出口正常，家庭／PVE／其他员工和网关管理面仍拒绝 |
| 安装与静态验证 | 新 playbook 在全部三个对象 Deploy/Verify 通过；两台 VM 最终重跑 changed=0；Ansible lint 23 文件 0 failure，Python 语法与 git diff --check 通过 |
| 最终网关监听 | 仅新 10.230.0.1:8443；既有两类 SSH 和 loopback DNS；默认 nginx disabled，专用 viewer active |

日志保留在部署 Sandbox：/tmp/employee-graphical-{control-deploy,pilot-deploy,gateway-deploy,final-deploy,native-check,probe-v3,revoke-probe-final,network-check,lint-final}.log，以及 /tmp/employee-viewer-isolation.log、/tmp/employee-graphical-login-tests.log。匿名 screenshot 为 /tmp/employee-graphical-anonymous.png（本机副本位于 /private/tmp/employee-graphical-anonymous.png），不包含真实账号。

私密接入包 v4 只更新 README 和三平台指南；所有密钥、WireGuard、SSH 和连接脚本与 v3 逐字节一致，无需重新导入隧道。文件 /private/tmp/employee-client-delivery-Azoee0/employee-ed-pilot-client-v4.zip，模式 0600，SHA256：5aa35cca138b809788f7b33e4b50249357021fa8261b35939bcb8b94724f1aad。旧版本保留。

仍待本人实际 UAT：本机浏览器中的 noVNC 操作体验、个人邮件／SSO／二次验证与 OAuth 回调、正确账号／订阅，以及真实小项目请求。匿名通道测试不等于本人 OAuth 通过；旧 Cloudflare Access 只读审计仍受连接器 access.read 权限阻挡。独立 GitHub onboarding 项目仍是设计草案，未创建或发布。此次修改未提交、推送或合并。

## 2026-10-22：用户批准独立日常浏览器，已部署

用户明确同意将图形授权入口扩展为日常 VM 浏览器。新增 /usr/local/bin/workspace-browser，支持 start/status/open/stop；employee-browser.service 以 employee 身份在独立 D-Bus 会话内运行 Firefox 与显示后端。SSH／本机查看页断线不结束浏览器，同一私网地址可重连；Claude 登录自动启动／复用浏览器并在新标签打开授权。只有 Claude 授权仍有 30 分钟等待上限，结束／取消不再关闭日常浏览器。

浏览器服务默认不随 VM 开机启动，部署也不主动启动或重启个人会话。显式 stop 关闭 6081/5901 后端，保留同一个个人 profile。VM 重启后需 start，标签恢复由 Firefox 设置决定。仍用原 WireGuard 设备映射及已验证网关策略，此次没有修改网关、路由器或 SSH 转发。

Control 端到端测试使用 /run 下独立空 HOME、临时 systemd 环境 override、无账号的公开登录页；测试结束已停止浏览器并撤回 override，恢复 production HOME。最终 12 个布尔条件全部通过：

1. 重复 start 保持同一服务 PID。
2. 浏览器由 systemd 独立管理，启动命令返回后仍在运行。
3. open 在原 Firefox 新标签打开目标网页。
4. 实际登记 WireGuard → 网关 → WebSocket/RFB 的点击和键盘输入在 Firefox DOM 核对一致。
5. 查看连接关闭／重连后仍是同一服务 PID。
6. 真实 native Claude 开页复用此浏览器。
7. 真实 Claude 授权取消后，浏览器仍运行且 PID 不变。
8. 授权 tmux/runtime 清理完成。
9. stop 后个人 profile 留存。
10. 停止后的 status 返回“未运行”。
11. 再 start 为新服务进程并复用同一 profile 路径。
12. 最后 stop 后 6081 与 5901 均关闭。

实现中纠正了 SSH 与 systemd Firefox 不共享 D-Bus 会话导致新标签复用超时的问题；运行环境仅在 employee 私有 runtime 记录 D-Bus 地址，新标签命令复用该会话。第一次点击测试发生在新标签异步字体／布局尚未稳定时，坐标失效；匿名测试在布局稳定后重跑，实际输入通过，没有通过修改生产页面隐藏错误。

合成登录回归 9 项通过，新增断言确认完成／取消／SIGTERM 只结束授权，不停止员工浏览器；非法 OAuth URL、其他凭据来源保护和其他 tmux 会话保留继续通过。最终 Ansible lint 23 文件 0 failure；Python 语法与 git diff --check 通过。最终部署及 Verify 在两台 VM 均通过；发现 pilot 原个人授权会话正在运行，部署未停止或重启它，新日常模式供后续启动使用。

日志：部署 Sandbox /tmp/employee-daily-browser-{login-tests,control-deploy-v2,uat-v3,final-deploy,lint-final}.log。实测中新标签、停止／重连等均为匿名配置，没有读取 pilot 个人浏览器或代用户授权。

用户曾反馈本机 noVNC 一直加载，已只读确认 10.230.0.2 固定映射 pilot、实际 WG 握手和后端监听正常；用户随后确认刷新即恢复。尚未确证那次加载的根因，不归因为 IP、sudo 或未经证实的协议故障。用户实际账号授权／真实项目 UAT 仍待明确反馈。

三平台指南、管理员指南、SPEC CAP-7、阶段路线图与 Agent onboarding 草案已同步。未创建 GitHub onboarding 项目，未提交、推送或合并本次修改。

## 2026-10-22：本人重新执行登录流程成功

用户明确反馈“重新走了一遍流程跑通了”，并要求先不处理此前登录后黑屏／终端等待现象。本次记录为本人报告的登录流程通过；不将此前一次状态检查 loggedIn=false 外推到重试成功后的当前状态，也不宣称黑屏根因已经查明或修复。按用户要求停止该现象排查，不再请求授权码、截图或重复登录。实际 Claude 任务响应、账号／订阅核对及其余 UAT 项仍按各自证据记录，不因登录流程通过而自动标为完成。

用户明确要求保留 workspace-login 快捷入口。现有 Ansible 安装声明、脚本与三平台指南均已保留该命令；它继续检查已保存订阅状态，并自动启动／复用 VM 浏览器完成 Claude 授权。workspace-browser 提供独立日常浏览器管理，两者同时保留。

## 2026-10-22：员工 Bootstrap 专属私有项目首版交付

用户要求完成 GitHub bootstrap 项目，明确选择私有，并要求设备包／实际接入配置单一起内置，以一个项目完成员工设置。已创建并发布 [blue126/workspace-onboarding](https://github.com/blue126/workspace-onboarding)，本机目录 /Users/weierfu/Projects/workspace-onboarding，版本 1.0.0，最终提交 ca2ce71a1e618e1c4f3167b4cae831ed69dce01d。新仓库默认 main；该仓库提交／推送为用户授权的首版发布，未提交或推送 IaC 现有变更。

当前是 pilot 用户专属私有项目，只含其 ed-pilot-client 原 SSH／WireGuard 身份、manifest、已核验主机 pin 和实际配置单；未重生成密钥，不含 control、其他员工或管理员身份。用户明确授权该公司设备包进入专属私有 GitHub，作为早先通用代码／包分离与不进 Git 约定的有限例外；个人 OAuth、浏览器会话、Vault／PVE 管理凭据仍不进入。GitHub 读取权限相当于设备身份使用权限；其他员工用新建专属私有仓库，不 fork 或复制当前密钥历史，未擅自邀请未指定用户或修改其他仓库权限。

交付包括 README/AGENTS 一段本机 Agent 入口、Windows PS5.1/7 与 macOS/Linux 原生脚本、check/setup/verify/connect/sftp/disconnect、严格数据包和报告 schema、无敏感示例、三平台人工步骤和故障恢复。默认从项目 deployment 读取包和摘要，不需要另给设备包路径或生成公钥。导入到仓库外本机私有目录，固定主机身份校验；拒绝包路径穿越／执行文件／未知字段、现有配置冲突、非本人隧道与入口路由冲突。Linux 只安装缺失的客户端；Mac 官方 VPN 权限交本人；Windows 通过官方签名安装器和 tunnel service。受管验证不附任意远程命令，使用交互 SSH PTY 和专用 employee-sftp，随机文件往返比对后只清理本次内容。

workspace-login 快捷命令与 workspace-browser 日常浏览器均保留。个人授权交还本人，verify 只导出 loggedIn/authMethod 判定结果，不输出账号／令牌，真实任务始终 pending。

最终 [CI](https://github.com/blue126/workspace-onboarding/actions/runs/39737559348) 在 Ubuntu、macOS、Windows 三个 OS job 全部 success，Windows PS7 和 PS5.1 均通过。测试只用合成身份，sparse checkout 排除真实 deployment，未注入或连接公司 VPN。Linux 17 项，Mac 13 项适用／4 项 OS 跳过，Windows 每版本 8 项适用／9 项 Unix 跳过；Bash/ShellCheck 与 PS 语法通过。实际包在管理员 Mac 只读 check 通过，没有激活或修改管理员 Mac VPN。

首版兼容性修复包括 Windows 命名参数显式转交、.NET 原生 SHA256、不含敏感值的异常类型／行号，以及 PS5.1 子进程从 PS7 Agent 启动时恢复本进程原生模块路径。没有改变系统／用户永久模块配置，也未让员工安装 PS7。

尚需在实际员工设备确认系统许可、客户端握手与实际工作体验；CI 不替代这一验证。当前用户已报告本人重新完成 VM 登录流程，仍保留其真实项目 UAT 后续。

## 2026-10-22：MCP 来源与临时卡顿只读核查

用户发现 VM Claude 出现 MCP，询问是否复制了本机配置；同时报告中国设备数十秒延迟，随后确认自行恢复，并确认多台电脑同时复用同一份设备包。独立员工 VM、独立设备身份与地址早已确定，不能再次当作待选架构。当前内置 ed-pilot-client 的项目仅映射 employee-pilot；多人使用该包会进入同一 VM/employee 账户并共享其个人登录数据，不是员工逐人隔离交付。须按既定要求给员工独立 VM、给每台设备独立 SSH/WG 身份和地址，不发布共用身份给其他员工。未在无名单／目标分配数据时擅自创建 VM 或撤销当前本人身份。

MCP 核查只解析来源元数据，没有输出 URL、command/args/env/headers、邮箱、令牌或个人页面。employee-workspace 部署没有复制本机 .claude 配置的任务；pilot 的 .claude.json 与 .claude/settings.json 均无 mcpServers，已检查的项目作用域也为空，control 无对应配置。官方 Claude Code 文档说明订阅账号的 Claude.ai connectors 会自动出现在 /mcp；这与当前现象相符，但未看到用户 /mcp 的来源标记，具体条目仍以其 claude.ai 标签为准。未启动、禁用或更改 MCP 服务。

恢复后的资源快照：pilot load 0.13，约 2.8GiB 内存可用，连续采样 CPU 近 100% idle，iowait/steal 为 0；网关负载与内存也充足。此为恢复后的状态，不代表已排除故障时的短时峰值。对 10.230.0.2/32 仅做 42 秒只读 endpoint 采样，观察到一个 endpoint、0 次变化，未导出外部 IP。用户确认的共享密钥会造成 peer endpoint/session 竞争，但这次采样没有直接捕获竞争，不能把之前延迟已定因为此或已定为普通网络波动。

诊断未改变路由、WG peer、VM 配置或个人会话，未提交／推送。共享身份须消除；不同员工 VM 的既定决定保持不变。

另一次 command-not-found 来自本机 Mac 的 zanesmbp 提示符；workspace-login 安装在 VM，旧手工包需先本机 bash ./connect.sh，进入 employee@employee-pilot 后再运行该命令。新的 bootstrap 项目则先 connect 动作。

## 2026-10-22：logout 状态只读复核

用户确认此前在 VM 内执行 Claude /logout 或 claude auth logout。随后只读检查发现，预装 /usr/local/bin/claude 2.1.304 与用户自装 npm 路径的 Claude 2.1.308 均返回 rc=1、loggedIn=false、authMethod=none，配置目录同为 /home/employee/.claude；未见 CLI 环境凭据替代或自定义认证目录。存在运行中的用户 npm CLI，但未停止该进程，也未读取内存令牌、个人页面或执行 logout／删除操作。

当前检查证实已经退出，未复现先前的“退出后仍已保存登录”状态。不能据旧输出确定当时是退出失败、其他共享会话重新登录、后续再次登录或其他原因；两版本共用同一配置目录，版本不同本身不是已证实根因。workspace-login 每次读取原生 auth status，不缓存账号；若退出后再运行此命令，会按用途启动新授权，因此只读核验应使用 claude auth status --text。不同 CLI／网页会话的退出作用域需分开处理；用户这次已确认是 VM CLI 退出，不再用“仅网页退出”解释。

## 2026-10-22：按用户要求移除 npm 版 Claude

仅在 employee-pilot 以 employee 身份，从 /home/employee/.npm-global 卸载 @anthropic-ai/claude-code@2.1.308；使用 npm --prefix 指定准确用户前缀并禁用生命周期脚本。验证该包目录与 npm launcher 均已移除，保留的 /usr/local/bin/claude 为 2.1.304，workspace-login --check 正常，workspace-browser 仍存在。没有卸载 Node/npm、删除项目／个人认证配置或终止运行中的用户会话。既有终端若缓存旧命令路径，需要 hash -r；已运行的旧 Claude 由本人退出后再重新启动。此为用户指定的重复包清理，员工工具自主管理约定保持有效。
