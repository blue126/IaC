# 实施要求

本文展开已定稿 spine 的实施交付要求，不重新定义 AD。实现应在取得 brownfield.md 所列真实基线后进行；所有生产变更仍遵守独立授权边界。

## 组件与交付范围

| 要求 | 单元 | 必须交付的行为 | 依据 |
| --- | --- | --- | --- |
| R-1 | 兼容盘点与安装 | 记录真实 OS/架构、当前规格/磁盘、服务和端口；固定实际安装资产、SHA256 与依赖；在同 OS/架构、无员工数据的已授权环境验证安装及 systemd/X11 启动。失败不改变 VM502 旧服务 | AD-1；CAP-8 |
| R-2 | employee-workspace role | 仅 VM502 的描述选择 kasmvnc；增加 XFCE、KasmVNC 与两个独立系统级 employee 服务，适配控制命令、桌面默认浏览器、快捷方式与登录检查。legacy 目标按描述保留旧分支 | AD-6、AD-7、AD-10；CAP-1、CAP-7 |
| R-3 | employee-access role | 统一维护设备映射、canonical 根入口、按目标类型的静态资源/WSS 路由、TLS、认证注入和连接撤销；全局配置变更统一锁内现读现写 | AD-2～AD-5、AD-8、AD-10；CAP-3、CAP-6 |
| R-4 | 管理员私密 provisioning | 唯一生成、保存和轮换后端凭据/证书代次；维护 CA、签发记录和到期计划；提供受控切换、事务恢复与反向回滚。两个 role 只消费批准代次 | AD-4、AD-5、AD-9、AD-10；CAP-8 |
| R-5 | 私有设备 bootstrap/连接配置 | 交付公开 CA 根证书、可信渠道核验信息及 canonical HTTPS URL；指导实际设备/浏览器安装信任并确认。只调整接入契约，不扩大到邮件重发、公开发布或管理员秘密交付 | AD-3～AD-5；CAP-5 |
| R-6 | 现有隔离与验证材料 | 保留 PVE/网关外部隔离和 SSH/SFTP 路径；补改与本变化相关的现有验证及员工说明，记录新旧模式与维护状态。测试复用既有脚本/fixture，不引入通用测试平台 | AD-2、AD-8、AD-9；CAP-1、CAP-3、CAP-6、CAP-8 |

Terraform 不因本试点调整 VM502 的系统、磁盘或规格。若需精确外部防火墙调整，单独列出变更范围；验证环境创建、安装和部署均不能由本规格推导为已获授权。

## 入口、后端与信任

| 接口/类型 | 目标行为 |
| --- | --- |
| WireGuard 私网 HTTP 8080 | 校验设备与 Host 后仅跳转至 `https://网关私网地址:8443/`；不透传任意目标/Host/查询参数，不代理桌面、认证或 WebSocket 升级 |
| WireGuard 私网 HTTPS 8443 根入口 | 先设备归属→VM ID，再按该 VM 的后端描述分派客户端；命令与 bootstrap 只输出此 canonical 根 URL |
| VM502 kasmvnc | 专属内部地址 6081，HTTPS/WSS；显式端口、唯一 TLS 校验身份与信任链、固定凭据代次。网关注入读写认证，不把后端密码或 Basic challenge 交给浏览器 |
| 其他 VM legacy-novnc | 沿用内部 HTTP 6081 和原 `/vnc.html` 客户端。该类型是显式兼容例外，不是 KasmVNC 证书或认证失败时的降级路径 |

保留同一设备映射对资源、缓存、开发 API 与 WSS 的约束；覆盖客户端认证/身份/目标头，严格校验 Host 和 HTTPS Origin。VM 外只允许网关访问专属后端，保留既有受保护网络矩阵与 IPv4/IPv6 边界；不开放 UDP/WebRTC/STUN/TURN 或新公网入口。

CA 及代次材料的归属、最小权限、签发范围、续期计划与两段校验按 AD-4/AD-5 实现。签发范围是管理员策略，不额外声称根证书具有密码学名称限制。所有在用设备确认 CA 信任和新 URL 后，才能迁移共享入口。

## 控制命令与运行态

| 操作/事件 | kasmvnc 模式的结果 |
| --- | --- |
| `workspace-desktop start` | 通过唯一模式、锁、事务标记、端口与 profile 检查后幂等启动完整桌面并发布就绪记录 |
| `workspace-desktop status` | 区分停止、就绪和失败；状态查询不自动恢复、清标记或创建新实例 |
| `workspace-desktop stop` | 先正常停止受管 Firefox，再结束受管图形进程；保留 SSH 独立任务、文件和已保存登录态 |
| `workspace-browser start/open` | 共用 desktop 的检查路径，必要时按需启动桌面，再启动/复用 Firefox；通过 browser 服务内部控制路径打开合法 http/https URL |
| `workspace-browser status/stop` | status 区分未运行/就绪失败；stop 仅关受管 Firefox，桌面和图形终端继续存在 |
| `workspace-login` | 沿用交互式 employee 调用、互斥、30 分钟授权超时和认证来源检查；复用日常 Firefox；成功/取消/超时只结束本次授权流程 |
| 网页、SSH、VPN 断开 | 保留图形进程；同员工有效设备可重连同一实例 |
| 多设备连接与缩放 | 可同时操作，新连接不踢旧连接、不要求确认、不自动改变共享几何；显式尺寸调整以最后有效操作为准，各设备同步 |
| desktop/Xvnc 故障 | 停止 browser、清除陈旧运行记录，明确报失败；两个服务均 `Restart=no`，由显式 start 恢复 |
| VM 重启 | 两服务不自动启动；之后手动 start 复用 profile，不承诺恢复未保存窗口/进程 |

两个系统级单元为 `employee-desktop.service` 和 `employee-browser.service`，均 `User=employee` 且不开机 enable。desktop 唯一发布 `/run/employee-desktop/session.json` 的显示号、XAUTHORITY、D-Bus 与运行目录；只有真正就绪才发布，停止/重启清理陈旧记录，browser/login 不独立推断。

保留 `/home/employee/.local/share/employee-workspace/firefox`，所有受管 Firefox 执行（含新标签转交）只在 browser 服务进程组内。命令使用 employee 专属 `/run/employee-browser/control.sock`，仅支持 open 与合法网页 URL，不接受命令/环境参数，不记录个人授权 URL。系统单元控制沿用 `sudo -n systemctl` 与精确的非交互 sudoers 操作范围，同时保留员工原有 sudo。

禁用 XFCE 应用会话自动恢复、Firefox 独立自启动、自动锁屏/密码屏保与空闲挂起。首轮在本机 IME 组字，VM 不同时启用组字引擎；本机浏览器优先 Chrome/Edge，Firefox 客户端用其支持的剪贴板路径对照，Safari 经网关的支持须实测。

## 配置所有权与变更互斥

| 对象 | 唯一归属与一致性要求 |
| --- | --- |
| 员工/设备→VM 归属 | 现有受管映射唯一拥有；后端描述用 VM ID 为键，不复制可独立修改的员工归属 |
| 后端描述 | 显式类型、地址/端口、服务端客户端路径、固定密码/证书代次、持久路由启停；不解析 latest、不探测协议、不失败回退其他目标 |
| 目标事务锁 | 目标 VM `/run/lock/employee-desktop.lock` 的 flock，与启动锁相同；全部 VM 管理步骤由同一持锁进程或继承同一描述符的子进程执行 |
| 目标事务标记 | `/var/lib/employee-workspace/transition.json` 持久保存唯一事务 ID。内部 start 只有无标记或持锁主体携带匹配 ID 时放行；外部 CLI 永不接收/读取 ID 冒充，见标记即拒绝 |
| 网关全局锁 | 网关 `/run/lock/employee-access-policy.lock` 的 flock；所有变更在锁内读取最新映射、描述和路由状态，验证后原子生效，不以旧快照恢复已撤销身份或已关闭路由 |

锁顺序固定为先 VM、再网关；设备撤销只取网关锁。内部 start 不重取已经持有的 flock，不用独立无锁 SSH 步骤或直接绕过检查的 systemctl 实现维护启动。中断即使释放运行期锁，持久标记仍阻止外部 start；只有管理员复核完整模式/代次后显式恢复。网关/PVE/CA 管理凭据留在控制端，不下发员工 VM。

轮换先暂存新代次，正常重跑不推进代次、不触发桌面重启。需要重启加载材料时先由持有人确认保存工作，按计划维护及同一受管内部 stop/start 路径生效；实际生效时关闭目标路由、更新验证后端、推进描述及网关匹配代次再开放。有效未撤销的旧代次在维护未确认时继续使用；失败路由关闭并恢复匹配配置，保留回滚所需前代材料。临时验证启动后恢复维护前运行状态。

## 切换与回滚要求

部署前盘点旧配置与服务，按既有许可在正常停止浏览器后处理 profile 一致副本。许可不明不创建含登录态快照/副本。安装不自动启动 KasmVNC；切换 type 时持锁、确认旧显示/代理和 profile 写入者已退出，非当前模式专属单元停止并 mask，共名单元按选定模式替换。

先确认在用设备 CA/URL，再迁移网关并验证它可代理旧后端，最后切换 VM502。允许的服务组合只有：

| 网关入口 | VM502 后端 | 判定 |
| --- | --- | --- |
| 新 8080/HTTPS 8443 | 新 KasmVNC | 目标状态 |
| 新 8080/HTTPS 8443 | 旧 noVNC | 合法过渡或回滚状态 |
| 旧 HTTP 8443 | 旧 noVNC | 完整旧状态 |
| 旧 HTTP 8443 | 新 KasmVNC | 禁止提供路由 |

失败时先关闭新后端并恢复 VM502 的旧服务与描述，再按需恢复旧网关及匹配客户端 URL。VM502 旧栈无法先恢复时保持其路由关闭。默认保留当前 profile；还原旧副本必须另有明确授权。其他 VM 的模式、后端和生命周期保持原状，只迁移共享入口协议。

## 验证交付物

提供相关部署/验证入口、精确目标选择、幂等与失败行为、模式/代次配置及维护回滚说明；按 acceptance.md 提供与交付版本一致的证据。复用现有 `tests/employee-workspace/`，优先验证跨进程生命周期、实际隔离、并发写入/中断及协议正反对照。离线与 PR 验证使用合成数据，不加载生产 secrets、不运行 deploy/publish/apply 流水线。

实际 OS、验证环境、资产校验和设备清单是实施输入，不从模板或历史报告猜测；具体 XFCE 包版本和显示号由实施盘点锁定，仍受上述唯一所有权约束。
