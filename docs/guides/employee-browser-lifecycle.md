# OCI Hub 桌面入口与设备信任

本页适用于已登记为 OCI Hub 接入、且管理员已分配目标 VM 的设备。访问路径为：本机设备 WireGuard → OCI Hub → 所分配 VM。桌面 HTTPS 的 TLS 在目标 VM 终止；服务端叶证书的 IP SAN（Subject Alternative Name，使用 IP Address 类型的身份）必须包含该 VM 的 overlay IPv4。

## 取得自己的桌面入口

开启 WireGuard，在自己的 VM 远端终端运行 `workspace-browser start`；已启动时可运行 `workspace-browser status`。浏览器就绪后，命令才输出配置的 `https://<目标 VM overlay IPv4>:8443/` 根 URL。先将该 IP 与管理员分配的目标核对，再按下方步骤确认本机信任，最后在本机浏览器打开命令输出的完整 URL。

未就绪时先按终端提示处理；不知道分配地址或输出与分配不一致时联系管理员，保持“未确认”。不要猜地址、追加旧 `/vnc.html` 路径、改用 HTTP、访问 loopback 后端端口，或回退到旧 `10.230.0.1:8443` 共享入口。证书警告也不能作为降级理由。

VM500 继续承担 HAPI 控制面；退役的是它的员工 WireGuard/内网网关角色。HAPI 接入不要求执行本页的 WireGuard 桌面信任步骤。

## 首次连接前：独立核验公开 CA

管理员需单独提供公开 CA 根证书、预期 CA 指纹及独立可信核验渠道。公开证书不含 CA 私钥、设备身份私钥、服务凭据或个人 profile；不需要为本页交付这些秘密，也不改变现有设备包字段。独立参考不能只是与证书同一下载包里的摘要，应经另一个已确认可信的渠道取得并记录来源。

本页的 CA 指纹统一为 **X.509 CA 证书 DER 字节的 SHA256 十六进制摘要**。它与用于标识单个服务端叶证书的 pin、用于校验下载文件完整性的设备包 ZIP SHA256 是三种不同对象；不能互相代替，也不能直接对 PEM 文本求摘要来代替 DER 指纹。

1. 取得公开 CA、独立来源的预期指纹，并核对它们适用于所分配目标。缺少 CA、独立参考或实际分配资料时停止导入和信任确认，记录“未确认”。
2. 在本机按所属平台计算 DER SHA256，与独立来源的预期指纹逐字核对。比较时仅忽略空格、冒号和十六进制大小写。任何不匹配都停止，不导入、不忽略证书警告、不关闭 TLS 校验。
3. 匹配后才按获准的系统/浏览器方式导入公开根。导入之后仍需在实际浏览器核对目标 URL 和叶证书 IP SAN；证书链或目标身份错误时停止，不点击继续、不添加临时例外。

### Windows

在 PowerShell 中将管理员提供的单张 PEM CA 证书转换为 DER，再计算摘要：

```powershell
$pem = (Get-Content .\public-ca.pem -Raw) -replace '-----[^-]+-----|\s', ''
$derPath = Join-Path (Get-Location).Path 'public-ca.cer'
[IO.File]::WriteAllBytes($derPath, [Convert]::FromBase64String($pem))
certutil -hashfile $derPath SHA256
```

匹配独立参考后，在同一个 PowerShell 会话中，当前用户可用 `certutil -user -addstore Root $derPath` 导入 Trusted Root store。确认实际浏览器使用该信任库；Firefox 可使用 Windows 系统根，仍须检查本机配置和实际访问结果。

### macOS

```bash
openssl x509 -in public-ca.pem -outform DER | shasum -a 256
```

确认转换和摘要命令均成功且匹配独立参考后，在 Keychain Access 导入公开根并检查 SSL trust policy。Firefox 可使用系统根，仍须确认本机浏览器实际信任该根。

### Linux

```bash
openssl x509 -in public-ca.pem -outform DER | sha256sum
```

确认两条命令均成功且指纹匹配后，Ubuntu/Debian 可把公开根以 `.crt` 文件安装到 `/usr/local/share/ca-certificates/`，再按本机许可运行 `sudo update-ca-certificates`。其他发行版按管理员批准的方式操作。Linux Firefox 还需按 Mozilla CA 配置确认其实际信任库包含该根，不能只凭系统导入成功就填“已确认”。设备没有获准导入方式时保持“未确认”并联系管理员。

平台参考：[Microsoft certutil](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/certutil)、[Apple Keychain trust settings](https://support.apple.com/en-au/guide/mac-help/mchlp2824/mac)、[Ubuntu root CA trust store](https://ubuntu.com/server/docs/how-to/security/install-a-root-ca-certificate-in-the-trust-store/)、[Firefox CA configuration](https://support.mozilla.org/en-US/kb/setting-certificate-authorities-firefox)。

## 逐设备信任确认表

每台当前在用登记设备一行；未知字段明确填写“未确认”。实际 CA 指纹独立渠道、真实设备/浏览器清单及持有人确认尚未提供，因此下表保留未确认；空表、本文或合成检查都不证明真实设备已信任。仅记录公开指纹和必要状态，不记录私钥、口令、个人会话或完整设备配置。

| Device ID | 系统/浏览器/版本 | 目标 overlay IPv4 / HTTPS 根 URL | CA DER SHA256 指纹 | 独立核验来源 | 持有人 | 确认时间 | 状态 |
|---|---|---|---|---|---|---|---|
| 未确认 | 未确认 | 未确认 | 未确认 | 未确认 | 未确认 | 未确认 | 未确认 |

## 中国侧体验对照记录表

沿用 Story8 的体验记录格式，补充当前 OCI Hub 目标和信任来源。实际网络体验由后续本人 UAT 填写；未执行的动作保持“未确认”。如需演示填写，设备及每项结果须明确标“合成”，不得混入真实确认。

| 设备/系统/浏览器 | 网络条件 | 目标 overlay IPv4 / HTTPS 根 URL | CA 指纹 / 独立来源 | 信任状态 | 任务/动作 | 结果与备注 | 持有人/日期 |
|---|---|---|---|---|---|---|---|
| 未确认 | 未确认 | 未确认 | 未确认 | 未确认 | 未确认 | 未确认 | 未确认 |

## 离线合成核验的边界

运行 `python3 tests/oci-hub/test-desktop-trust.py -v` 可用临时 CA、叶证书和合成设备/目标演练指纹、证书链、IP SAN 及 URL 正反例。测试不访问实际服务、设备包、profile、Vault 或 BWS，不导入系统信任；合成私钥只存在于测试临时目录，不作为交付材料。

通过仅表示这组说明核验规则通过，不代表真实 WireGuard 连通、浏览器信任、设备撤销或本人 UAT 通过。缺少真实资料只阻塞真实信任确认与后续本人 UAT，文档和离线合成核验可独立完成。
