# 实施基线与待采集输入

## 绑定的架构版本

本规格 adopted companion 为 `../../planning-artifacts/architecture/architecture-vm502-xfce-kasmvnc-2026-10-23/ARCHITECTURE-SPINE.md`，状态 `final`，SHA256 `12339a151d208764c4dacf1b58df619cf3e3e6a94e9a3fbe2ba58fc221724d0a`。AD-1～AD-10 保持原编号与内容；本规格未修改该文件。

原员工工作区 CAP-1～CAP-7 分别对应个人开发、订阅身份、隔离、澳洲运行、体验/扩展、访问管理和日常浏览器。新规格保留这些含义并收窄到试点，完整桌面控制属于 CAP-7 的本次追加，安全验证/切换/维护/回滚以新 CAP-8 表达。

## 真实代码输入

本任务工作树为 `/Users/weierfu/.codex/worktrees/vm502-xfce-kasmvnc-spine/IaC`，来自 `origin/main` 的 `d748e7d`。它包含本次文档，不包含现行员工工作区的全部部署变更。

现行实现位于 `/Users/weierfu/.codex/worktrees/employee-claude-architecture/IaC`，HEAD 为 `c9fb840`，同时含已跟踪修改与未跟踪部署文件。实施须显式取得这份现行输入或管理员认可的等价固定快照；不能仅 checkout 该 HEAD、本任务 HEAD 或其他旧模板当作部署基线。原工作树及其个人凭据、Vault、tfvars、状态文件保持原所有权，不为规格复制或整理它们。

下表只记录非秘密源码文件的 2026-10-23 指纹。`路径` 均相对现行实现工作树；发生变化时先对账相关差异，不自动覆盖新版本。

| 路径 | SHA256 |
| --- | --- |
| `_bmad-output/specs/spec-employee-claude-workspace/SPEC.md` | `d24ddb8122026d59be611cf3c6b6405328ab81887c069a505ee4ccda3ea89c64` |
| `docs/planning/employee-workspace-browser-auth-change.md` | `1d69175d3a0f3449568580b4d60c47b6b9dbc7736b49fc660a7a2a1cf9044b8e` |
| `ansible/roles/employee-workspace/files/workspace-browser.py` | `239b97580f3d0ac34faf851317174d56ad701209e73d975b2455a0eb01f06a1b` |
| `ansible/roles/employee-workspace/files/workspace-login.py` | `7b1e57cd2243ff185c62c78189597fd2a214a3df2edd05a2f5459ba0025f2e91` |
| `ansible/roles/employee-workspace/files/auth-browser.py` | `6db771a9c9c6aab116d3a1358903ebcd78bb9d1278bbe6cc72710971666a679d` |
| `ansible/roles/employee-workspace/tasks/login.yml` | `bbe3d8661999804c0698c425f77ec4842dcf5078a67517b5b56438576bce2c04` |
| `ansible/roles/employee-access/templates/auth-viewer-nginx.conf.j2` | `8025c2023507a6a8155f9beec70275e10c0d615bd3c7fd40bbf8f9b3fb8da4ea` |
| `ansible/roles/employee-access/tasks/auth-viewer-policy.yml` | `da95d1f48f5011006a61a644ded0cae231ce7215c195d41db5732126298afdcc` |
| `ansible/roles/employee-access/tasks/revoke.yml` | `8dad32b5cdc9edeae69510846c239882fadc2f2ac48de64bbd470ea726f57396` |
| `ansible/roles/employee-access/tasks/disable.yml` | `6077586b20e2bd76bf8413eace0b0343994e2c75735e91d030d3e738f079ca62` |
| `terraform/proxmox/employee-template.tf` | `e499ad5d995d440b10257a383931a321117b0d21773bfefbb496ebb9f94958fa` |
| `tests/employee-workspace/test-login.py` | `ccbd61f535bf61f4874708edf296bc847369e31c95c070eef55d06c0d21e337c` |

## 已核对的增量

| 现行行为 | 本次目标 |
| --- | --- |
| Xvfb/Openbox/x11vnc/noVNC/websockify，显示号和浏览器环境由旧监督程序提供 | 仅 VM502 改为 XFCE/KasmVNC；desktop 服务唯一发布环境，browser 服务持有 Firefox |
| workspace-browser 管理包含显示/代理的 browser 服务，stop 结束旧图形后端 | VM502 分开 desktop/browser；其他 VM 保留此 legacy 分支 |
| open 在调用方执行 Firefox 并使用固定 `DISPLAY=:99` | VM502 open 经内部 socket，由 browser 服务执行；环境来自 desktop 记录 |
| 网关 HTTP 8443、固定 HTTP 6081、根路径转 `/vnc.html` | WG HTTP 8080 跳 canonical HTTPS 8443 根；根按后端类型分派；VM502 上游 HTTPS，其余显式 legacy HTTP |
| 映射变更会重启独立网关 viewer 代理清除连接 | 保留外部主动断开能力；新模式不得通过杀 VM 内 Xvnc/桌面来撤销设备 |
| login 检查依赖旧图形组件，复用持久浏览器 | 模式分支检查适配新组件；个人授权的交互/互斥/30 分钟/来源检查与保留浏览器语义继续有效 |

这些是源码观察与目标差异，不是对运行中 VM、个人账号或中国侧体验的通过证明。

## 实施前输入

| 输入 | 取得方式与停止条件 |
| --- | --- |
| 实际 OS/架构/规格/磁盘/服务/端口 | 授权范围内只读盘点 VM502；模板名只作线索。缺项、漂移或 8080/8443/6081 占用冲突先报告，不擅改其他端口/资源 |
| 验证环境与安装清单（Q-1） | 管理员指定可复用且已授权的同 OS/架构无凭据环境；锁定 KasmVNC 包来源、SHA256、依赖及 XFCE 软件源版本。26.04 兼容性尚未证实，不能因存在 Noble 包而宣称可用 |
| 当前设备/浏览器与 UAT（Q-2） | 从现有受管清单确认在用设备及 VM502 所属设备，登记实际浏览器、中国侧测试人/网络与可做 UAT 的本人，不猜邮箱或重新分配 VM |
| 当前映射与后端描述 | 读取管理员最新批准归属与目标状态，明确 type、代次及路由；沿用现有秘密渠道，不把秘密值写进本规格或证据 |
| CA 信任与续期 | 确认证书身份、到期日、管理员续期计划、可信公开根交付与每台在用设备的安装确认；缺信任不切共享入口 |
| 维护与个人副本许可（Q-3） | 确认精确目标、窗口、工作保存、安装/重启/变更权限及既有 profile 副本访问/留存/恢复许可；不把规格或历史授权泛化为本次许可 |
| 新旧体验对照 | 在允许的顺序切换中采集 noVNC 基线，固定设备/网络/分辨率/任务；不并行打开两个 profile 写入者 |

Q-1～Q-3 是实施前待确认事实和授权，不重新开放已定的桌面技术、端口、CA 信任模型或生命周期选择。可在实施前盘点记录中补齐；若答案改变 AD，则先由架构所有者更新 spine，再由 bmad-spec 重派生本契约。
