# VM502 桌面交付与 Story 成果对应

本记录把 Story1 至 Story13 的历史成果对应到当前有效实现，便于总 PR 审核及后续维护。它记录交付去向和证据边界，不将未执行的真人验收记为通过。Story9 与 Story11 已按 Epic 决策取消或取代，编号保留。

## 当前架构

设备通过 WireGuard 接入 OCI Hub，再沿 Spoke 到自己的 VM。VM502 的 nginx 在本 VM overlay HTTPS 8443 终止前端 TLS，验证并代理到 loopback TLS 8444 的 KasmVNC。KasmVNC 与 XFCE 直接运行于 Ubuntu，应用以 `employee` 运行。当前桌面数据使用 WSS/TCP，外层为 WireGuard UDP；Kasm 的 WebRTC UDP 未启用。VM500 保留 HAPI 控制面，已退出员工 WireGuard/内网网关职责。

桌面与浏览器独立生命周期；默认网页、桌面快捷方式通过 `workspace-browser` 使用同一 Firefox profile。HAPI 的既有 viewer URL 保留，直接桌面 URL 从 desktop 配置取得。个人登录沿用主线 `workspace-login`，本交付不覆盖它。

## 逐项对应

| Story／历史提交 | 当前有效成果 | 验证及处理 |
|---|---|---|
| 1 安装兼容性，`3a9b2d5` | 固定 Ubuntu 26.04／amd64、KasmVNC 1.5.0-1；`presentation.yml` 和 `desktop-service.py` 检查平台、已装版本和图形命令 | 本人在现有 VM502 授权安装和图形启动已完成；版本拒绝由 `test-desktop-lifecycle.py` 覆盖。旧兼容性试验脚本与结果依赖本地输出，保留历史；资产和依赖准备见下文 |
| 2 后端契约和隔离纵向样例，`138a082` | workspace 内的 `desktop-contract.py`、不可变代次引用和真实 TLS 纵向样例；基础 VM 和身份由主线 OCI provisioning 负责 | `test-desktop-oci.py` 和 `tests/oci-hub/test-desktop-network.py` 验证材料、目标、证书和桥接；私有 helper 仅供既有批准的隔离入口使用 |
| 3 桌面生命周期，`c5381b1` | `desktop-service.py`、`workspace-desktop.py`、desktop unit、共享 session/锁及 fixture | `test-desktop-lifecycle.py`；原 `desktop.yml` 和 `test-desktop-config.py` 依赖退役 gateway inventory，当前安装选择与平台守卫由 presentation 入口承接；日常操作见生命周期指南 |
| 4 独立浏览器及个人授权接缝，`a5c6fd8` | browser service/unit、`workspace-browser`、默认浏览器与桌面快捷方式；保留主线登录 helper 和 HAPI URL | `test-browser-lifecycle.py`、`test-desktop-oci.py`、主线 `test-login.py`；个人账号/MFA不进入测试 |
| 5 HTTPS及统一网关 writer，`c55f975` | 当前 TLS/认证/Host/Origin 策略来自主线 `oci-hub-spoke/templates/desktop.conf.j2`；桌面维护在共享锁内执行 | 旧 `employee-access/gateway-policy.py` 及共享 8080/8443 入口已由主线 `50b614d` 退役，不重新恢复。当前 HTTPS/WSS 策略由 OCI 协议矩阵验证 |
| 6 隔离和撤销，`748ab6d` | 设备接入状态由 OCI Portal 管理，外部隔离由 OCI/PVE 边界执行；已有主线 `scripts/oci-hub` 与 `tests/oci-hub` | 旧网关撤销测试保留历史；当前合成隔离通过不等于真实员工撤销已验收，本次未执行真实员工停用或撤销 |
| 7 同 VM 重建和中断恢复，`c7c4270` | `prepare-desktop.py` 的 staging／锁／维护标记／失败关闭／同阶段续跑替代旧 gateway 耦合的 rebuild 入口 | `ActivationTests` 覆盖活动旧浏览器拒绝、切换中断、前进续跑及外来维护标记；不是旧栈回滚。原重建的依赖安装准备与当前切换分别记录 |
| 8 原设备信任说明，`1cd779b` | 三平台指南及信任／体验记录格式由 Story13 更新为当前 OCI 路径 | 保留原成果和本地构建记录；不重新实施旧共享网关迁移 |
| 9 清理 | Epic 已取消空的 refactor sweep | 无具体发现时不制造重构 |
| 10 当前 OCI 隔离集成，`5a954e7` | 直接 overlay HTTPS/WSS、目标隔离、失败关闭及 HAPI 合成桥演练 | 既有隔离入口、临时资源和清理证据；后续测试修复隔离 nginx 临时目录，防止污染生产缓存权限 |
| 11 旧共享网关迁移 | 已由 OCI Hub 迁移取代 | 不恢复 VM500 网关和旧入口；不据此宣称所有员工桌面已切换 |
| 12 本人验收及桌面就绪 | presentation 三阶段、当前受管桌面／浏览器／HAPI桥；本人澳洲基本体验 | 相关离线套件 57 项通过，实际合成协议矩阵 25 项通过且清理／非任务元数据检查通过；本人确认中文、画面、双向剪贴板、刷新保留会话及 Claude App 基本体验。中国侧体验、完整个人授权流程、Code/Cowork任务未单独验收 |
| 13 OCI 信任差量，`b5b625d` | `employee-browser-lifecycle.md`、三平台说明、`test-desktop-trust.py` | 使用目标 overlay URL、IP SAN和独立指纹来源；合成通过不能填写其他真实设备已信任 |

上述历史提交不全是当前主线祖先，部分实现经后续独立提交进入主线或被替代；不能通过整批 cherry-pick 旧分支恢复，亦不能只按祖先关系判断功能遗漏。总 PR 以当前有效源码及可执行验证为准。

## 固定资产与安装准备

Story1 在获准的 VM502 Ubuntu 26.04 amd64 使用以下资产，当前 presentation 入口要求事先安装，不承担包安装、VM 创建或凭据生成：

- KasmVNC：`kasmvncserver_noble_1.5.0_amd64.deb`，包版本 `1.5.0-1`。
- 固定下载 URL：<https://github.com/kasmtech/KasmVNC/releases/download/v1.5.0/kasmvncserver_noble_1.5.0_amd64.deb>。
- 下载文件 SHA256：`f599fe02e2175b9817b6165f74a5d2bebdc73118dde9181ba3410963bed7ae1e`，来自 Story1 固定资产记录。
- 当时的精确安装事务：`apt-get --no-install-recommends --no-remove install xfce4=4.20.1 <已校验的本地 deb>`。其他依赖由当时 apt 解析；当前所需图形命令由 `presentation.yml` 的实际命令清单检查，不能将该历史事务当作任何全新 VM 的完整安装器。Firefox、tmux、nginx及OpenSSL由既有工作区基线提供。

在批准的任务 Sandbox 中，以单目标 Ansible play 执行包准备：先检查发行版和架构，以 `get_url` 的 `checksum: sha256:<上述摘要>` 获取固定资产，再用 `dpkg-deb -f` 核对 Package／Version／Architecture 为 kasmvncserver／1.5.0-1／amd64；对确切安装集合先做 apt simulation。若有删除或升级既有包、版本无法取得或摘要不匹配，停止并审阅差异；不要用其他发行版包、浮动版本或全机 upgrade 绕过。已匹配的包应跳过安装。安装授权与实际部署分别明确，不能把语法检查当作安装验证。

随后按 [桌面就绪说明](../deployment/vm502-presentation-readiness.md) 准备独立前后端材料，执行 trust／prepare／activate。只恢复上述当前入口所需检查，不复活包含个人机器路径、旧脚本指纹及旧 gateway 绑定的兼容性实验工具。当前 runtime 的真实启动、TLS与浏览器由现有协议夹具覆盖。

## Claude App 与信任试点

官方 Claude Desktop 4.4212.0 已按本次用户授权在 VM502 安装并启动，本人反馈基本体验正常。该应用不是 presentation playbook 的安装依赖。官方 Linux 支持及更新使用 [Anthropic 安装说明](https://support.claude.com/en/articles/10065433-install-claude-desktop)；当前试用没有配置 Cowork 的 QEMU 环境，不能把基本 App 体验写成 Cowork 验收通过。

VM502 本人已确认 Firefox 导入 CA 后无证书警告。其他设备仍需独立核验。VM508 后续试用经用户接受站点证书例外，属于单独任务；不将该决定改写为全员关闭 TLS 检查，也不放宽后端 TLS 与设备包身份约束。

## 保存边界

公开仓库只包含源码、合成测试和操作说明。私有管理员实现仍在主 checkout 的独立 `remotecc/employee-admin` 仓库；身份、材料、设备包、运行结果和 profile 留在私有数据中。`_bmad-output` 保留本地历史，不重新加入 Git。总 PR 不包含 VM508 新任务，不触发部署，不将仍待员工执行的验收标为完成。
