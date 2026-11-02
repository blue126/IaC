# KasmVNC 员工桌面

本 role 负责现有员工 VM 的固定 KasmVNC/XFCE 包安装，以及桌面 presentation 的分阶段部署。网络、VM、员工身份和密钥由现有管理员流程负责。共享的桌面／浏览器运行文件继续使用 `employee-workspace/files/` 的唯一源码；旧 presentation 入口委托到本 role，保留 VM502 的使用方式。

批准目标的唯一清单为 `../employee-workspace/files/desktop-targets.json`：`approved_vmids` 显式列出 VM502 和 VM508，`approved_vmid_range` 覆盖员工工作区 VMID 方案 502–754（2026-11-03 起每个员工 VM 都带 VM 浏览器入口，见 story 5.25）。清单表示源码支持范围，实际部署仍须单独批准；以现有管理员登记确认所属员工和 inventory VMID，再提供该 VM 独立的 generation、后端认证和前端材料。运行时始终只允许 loopback 8444，材料路径必须包含目标 VMID，客户端不能改选其他 VM。

统一入口为 `ansible/playbooks/prepare-employee-desktop.yml`。必须显式传入 `employee_desktop_target`（一个 inventory 主机）及 `employee_desktop_phase`：

| 阶段 | 行为 |
|---|---|
| packages | 校验 Ubuntu 26.04/amd64，下载 SHA256 固定的 KasmVNC 1.5.0-1 资产，核对包身份，模拟 XFCE 4.20.1 安装；遇到既有包升级、降级或删除即拒绝，再安装确切集合 |
| trust | 校验独立前端证书及私钥，仅更新前端信任材料 |
| prepare | 校验配置与 inventory VMID、overlay 地址一致，暂存并验证运行文件和材料 |
| activate | 在共享维护锁下拒绝活动桌面／浏览器、旧监听和其他维护事务，再切换本 VM 的 presentation |
| provision | 新开户或尚无桌面的 VM：安装 nginx（不启用默认站点），写入管理员提供的本 VM 前端证书（已有证书必须与 pin 一致，绝不替换），把 VM 浏览器入口指向本 VM overlay，再执行完整的 update |

包准备依赖现有工作区基线提供 Firefox、nginx、tmux 等命令。安装事务不包含 Claude Desktop，不能把通过包准备当作完整应用体验通过。role 不自动停止员工会话，激活前须由员工保存工作并按批准范围停止旧服务。

VM502 既有中断标记保持兼容；其他目标的中断标记记录本人 VMID，不能接管其他 VM 的事务。日常桌面仍按需启动，Verify play 不启动个人应用或读取个人 profile。

`update` 阶段供现有私有 `wsctl desktop-update` 调用，组合 packages、官方 Claude Desktop 安装、独立后端材料准备、prepare、停止受管图形服务和 activate。官方应用固定为4.4212.0，禁用推荐依赖；签名主密钥必须唯一且指纹为 `31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE`。官方仓库说明见 [Anthropic 安装文档](https://support.claude.com/en/articles/10065433-install-claude-desktop)。普通 packages/trust/prepare/activate 不额外安装该应用。

更新使用 `kasmvnc_update` 中经批准的 VMID、overlay、generation、既有前端 SHA256和停止浏览器范围。既有自签名叶证书只有在与明确批准指纹完全一致、CA文件就是同一证书且IP SAN、有效期、公私钥匹配时才能复用；这不会改变严格后端 CA/hostname验证。新后端 CA私钥留在本人VM的root-only文件，服务私钥和认证文件为root:employee0640，generation不自动轮换。应用安装和材料暂存验证通过后才停止旧会话；安装失败不会先停旧浏览器。

`provision` 阶段供私有 `wsctl provision`（新开户）和 `wsctl desktop-update` 的安装模式调用：变量与 update 相同，另需 vault 中的 `kasmvnc_frontend_certificate`／`kasmvnc_frontend_private_key`（自签名叶证书，IP SAN 为本 VM overlay，指纹即设备包的 `tls_certificate_sha256`）。
