# VM508 中国侧桌面更新部署范围

本次仅更新已有员工／设备 `suixiaoyou` 的 VM508（`oci-hub-suixiaoyou`，收件邮箱为既有登记 `suxiaoyo@gmail.com`）。源码准备与检查已完成，尚未提交、发布或执行部署。员工的 Mac／Linux 具体系统及是否已用新包接入仍待本人确认。

## 2026-11-02 只读事实

执行器台账确认员工／设备归属 VM508。QGA核查为 Ubuntu26.04.1、x86_64、2核／8GiB配置，系统盘约42GB可用；XFCE、KasmVNC、Claude Desktop和gnome-keyring尚未安装。当前 employee-browser和nginx运行，employee-desktop未运行。APT现有元数据提供XFCE4.20.1及gnome-keyring50.0-1；实际安装须重新模拟，不能据此声称安装已通过。

本人桌面地址为 `https://10.234.0.8:8443/`。现有前端为 IP SAN10.234.0.8、CA:FALSE的自签名叶证书，SHA256为：

```text
91aaeb2ffb705230b3b75d1f587b328e9f01e97d2218da419418d4845b3ccd1e
```

更新保留该证书与私钥；浏览器继续按已批准方式接受本站例外。设备包pin、SSH/WireGuard身份及严格后端TLS验证继续生效。

## 本次具体变更

| 项目 | 范围 |
|---|---|
| 软件 | 安装KasmVNC1.5.0-1、XFCE4.20.1、官方Claude Desktop4.4212.0、gnome-keyring及必要依赖；禁用推荐依赖 |
| 仓库 | 添加Anthropic官方APT仓库；唯一签名主密钥指纹须为31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE |
| 包事务 | 先模拟，发现既有包升级、降级、删除或Claude事务引入QEMU／OVMF／virtiofsd即停止；版本不可得时停止 |
| 后端材料 | 仅在VM508生成独立`g-vm508-trial-v1`代次、loopback localhost:8444证书与认证；材料持久保存于本VM，重复执行复用原代次 |
| 系统文件 | 部署role受管的presentation暂存文件、桌面／浏览器service、控制脚本及配置，使用既有严格OCI nginx模板切换上游 |
| 服务中断 | 员工保存工作后，在包安装和暂存验证成功之后停止本VM已安装的employee-browser／employee-desktop，再共享锁内激活 |
| 启动与验收 | 保持桌面按需启动，员工自行在本人VM内打开Claude并登录；随后验证本人HTTPS/WSS连接、延迟、滚动、中文输入及重连 |

保留员工文件、既有Firefox profile及个人登录状态。此次范围不包含VM502操作、重新开户、网络／Portal变更、设备包重发、邮件、SSH/WireGuard身份轮换或Cowork配置。不能把历史acceptance_waived、服务健康或VM502澳洲体验记作本次中国侧真人通过。

## 现有wsctl入口

私有任务源码位于 `/private/tmp/vm508-wsctl-admin`（branch `codex/vm508-desktop-update`），公开IaC任务位于本worktree（branch `codex/vm508-kasmvnc`）。主私有管理员目录的无关未提交修改保持原样。发布仍使用既有执行器部署方式，实际操作前需批准源码提交、推送／发布及VM508更新这些边界。

源码获准发布至执行器后，在其权威employee-data请求目录保存以下请求，以现有 `wsctl desktop-update REQUEST.json --plan-only` 获取实时计划和摘要；审阅同一范围后以 `--approve SHA` 执行。请求文件内容：

```json
{
  "employee_id": "suixiaoyou",
  "device_id": "suixiaoyou",
  "vmid": 508,
  "generation": "g-vm508-trial-v1",
  "frontend_sha256": "91aaeb2ffb705230b3b75d1f587b328e9f01e97d2218da419418d4845b3ccd1e",
  "stop_browser": true
}
```

计划绑定台账、roster、只读实机身份／指纹／已装版本、源码及配置摘要。变化使旧批准失效。`wsctl`沿用现有锁与临时凭据，Ansible仅限定`oci-hub-suixiaoyou`，SSH公钥由受信PVE的QGA回读固定；不重新provision。部分执行失败保留原代次与既有维护标记，按同一请求重新计划，不用新代次绕过恢复。

## 验证证据

新旧presentation入口语法检查通过，相关role和playbook lint通过。桌面生命周期29项、浏览器12项、presentation／TLS60项、新材料3项合成测试通过；私有desktop更新8项和wsctl44项测试通过。测试覆盖错配员工／设备／VM、证书pin变化、旧批准拒绝、单目标执行、前端自签名叶证书精确pin、独立后端生成／重复使用和符号链接拒绝。未执行真实安装、停止服务或中国侧真人验收。

官方安装来源：[Anthropic安装说明](https://support.claude.com/en/articles/10065433-install-claude-desktop)。角色用法见[KasmVNC role](../../ansible/roles/kasmvnc/README.md)。
