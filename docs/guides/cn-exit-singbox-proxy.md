# 国内服务访问代理 · 使用说明书

> 目标:身在海外(悉尼),访问国内限定服务(QQ音乐、腾讯视频、网易云、B站、爱奇艺)时,自动走国内 VPS 出口;其余流量直连不受影响。

---

## 一、这是什么

家庭网关(iStoreOS, `192.168.1.1`)上跑了一个 **sing-box 代理**(Docker 容器 `cn-proxy`),手机/电脑把系统代理指向它之后:

- **国内服务** → 经 `cn-exit`(国内云 VPS)出口,拿到国内 IP,绕过地域/版权限制
- **其他流量** → 直连,不走代理,速度不受影响

原理:sing-box 内嵌了一个独立的 Tailscale 节点(和网关自带的 tailscale 互不影响),把命中规则的域名通过 Tailscale 的 `cn-exit` 出口转发出去。

```
设备(手机/电脑) → 系统代理 → 192.168.1.1:7890 (sing-box)
                                ├─ 腾讯/网易/B站/爱奇艺 → cn-exit(<cn-exit-vps-ip>)→ 国内服务
                                └─ 其他 → 直连
```

---

## 二、关键信息速查

| 项 | 值 |
|----|----|
| 代理地址 | `192.168.1.1:7890` |
| 代理类型 | HTTP + SOCKS5(混合) |
| 出口节点 | `cn-exit`(国内 VPS `<cn-exit-vps-ip>`,约 10Mbps) |

> 本仓库是公开的,VPS 的公网地址已脱敏为 `<cn-exit-vps-ip>`。
> 实际地址见网关上 sing-box 的 Tailscale 节点配置或 Tailscale 管理后台。
| 配置文件 | 网关 `/etc/sing-box/config.json` |
| 容器名 | `cn-proxy`(Docker,开机自启) |
| 状态目录 | `/etc/sing-box/ts-state`(Tailscale 节点身份,持久化免重登) |
| 分流范围 | 腾讯、网易、B站、爱奇艺 → cn-exit;其余直连 |

---

## 三、如何使用(每台设备一次性设置)

设置"系统代理",填网关地址和端口即可。**日常可以一直开着**——它只对国内服务走 cn-exit,其他流量本来就直连。

### iPhone / iPad

1. 设置 → Wi-Fi → 点当前网络的 ⓘ
2. 配置代理 → **手动**
3. 服务器:`192.168.1.1`,端口:`7890`
4. 存储

> 注意:换到别的 Wi-Fi 或切蜂窝数据后,代理会失效,需重新设置(蜂窝数据场景下系统代理不生效)。

### Android

1. 设置 → WLAN → 长按当前网络 → 修改网络 → 高级选项
2. 代理 → **手动**
3. 服务器主机名:`192.168.1.1`,端口:`7890`
4. 保存

### Windows

1. 设置 → 网络和 Internet → 代理
2. "手动设置代理" → 使用代理服务器 → 开
3. 地址:`192.168.1.1`,端口:`7890`
4. 保存

### macOS

1. 系统设置 → 网络 → Wi-Fi(当前网络)→ 详细信息…
2. 代理 → 勾选 **SOCKS 代理**(或 HTTP 代理)
3. 服务器:`192.168.1.1`,端口:`7890`
4. 好

---

## 四、如何验证生效

最直接:开代理后访问一个国内限定内容,看是否正常加载:

- B站某部"仅限中国大陆"的番剧
- 爱奇艺/腾讯视频的国内独播内容
- QQ音乐/网易云某首海外变灰的歌

**快速自检**:开代理 → 能看;关代理 → 提示"仅限中国大陆地区" → 说明分流正常。

---

## 五、后续配置变更

### 5.1 基本流程(改 → 校验 → 重启)

配置在网关 `/etc/sing-box/config.json`。SSH 进去操作:

```bash
ssh root@192.168.1.1

# 1. 改之前备份(回滚靠它)
cp /etc/sing-box/config.json /etc/sing-box/config.json.bak

# 2. 编辑
vi /etc/sing-box/config.json

# 3. 校验(关键,先别重启;报错就别重启)
docker exec cn-proxy sing-box check -c /etc/sing-box/config.json
#    无报错 / 显示正常 = 通过

# 4. 校验通过再重启
docker restart cn-proxy

# 5. 出问题就回滚
cp /etc/sing-box/config.json.bak /etc/sing-box/config.json && docker restart cn-proxy
```

### 5.2 加一个国内服务(例如优酷)

需要在配置里**三处**都加上对应类别。以加 `geosite-alibaba`(优酷/淘宝/支付宝)为例:

1. `route.rule_set` 里加一条定义:
```json
{ "tag": "geosite-alibaba", "type": "remote", "format": "binary",
  "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-alibaba.srs" }
```

2. `route.rules` 里把该类别加进 `outbound: ts` 的列表:
```json
{ "rule_set": ["geosite-tencent", "geosite-netease", "geosite-bilibili", "geosite-iqiyi", "geosite-alibaba"], "outbound": "ts" }
```

3. `dns.rules` 里把该类别加进 `server: dns-exit` 的列表(让它的域名走国内 DNS 解析,拿到正确 CDN):
```json
{ "rule_set": ["geosite-tencent", "geosite-netease", "geosite-bilibili", "geosite-iqiyi", "geosite-alibaba"], "server": "dns-exit" }
```

改完走 5.1 的校验 + 重启流程。

### 5.3 收窄到只有几个域名

把 `route.rules` 里的 `rule_set` 换成精确 `domain_suffix`(同时可删掉 `rule_set` 定义块):

```json
{ "domain_suffix": ["y.qq.com", "v.qq.com", "music.163.com", "bilibili.com", "iqiyi.com"], "outbound": "ts" }
```

> 区别:geosite 自动更新、覆盖广;domain_suffix 精准、但要手动维护。

### 5.4 改端口

需同时改两处:`config.json` 里的 `listen_port`,以及 Docker 的端口映射:

```bash
docker rm -f cn-proxy
docker run -d --name cn-proxy --restart unless-stopped \
  -p 新端口:新端口 \
  -v /etc/sing-box:/etc/sing-box \
  ghcr.io/sagernet/sing-box:latest run -c /etc/sing-box/config.json
```

### 5.5 常用 geosite 类别参考

| 类别 | 覆盖 |
|------|------|
| `geosite-tencent` | 腾讯全家桶(QQ、微信、腾讯视频、QQ音乐、腾讯云…) |
| `geosite-netease` | 网易全家桶(网易云、邮箱、新闻、游戏…) |
| `geosite-bilibili` | B站 |
| `geosite-iqiyi` | 爱奇艺 |
| `geosite-alibaba` | 阿里系(淘宝/天猫/优酷/支付宝) |
| `geosite-bytedance` | 字节系(抖音/头条/西瓜) |
| `geosite-baidu` | 百度系 |
| `geosite-meituan` | 美团 |
| `geosite-cn` | 全部中国域名(聚合,慎用) |

---

## 六、故障排查

| 现象 | 排查 |
|------|------|
| 代理完全不通 | `docker ps` 看 `cn-proxy` 是否在跑;`docker logs cn-proxy` 看报错 |
| 国内服务打不开、其他正常 | 可能出口节点挂了,先 `docker logs cn-proxy` 看 tailscale 连接状态 |
| 容器反复重启 | 配置改坏了 → 走 5.1 回滚;`docker logs cn-proxy` 看具体报错 |
| 改了配置没生效 | 忘了 `docker restart cn-proxy`;或改了没校验通过就重启 |
| 某设备不走代理 | 检查该设备的系统代理设置(IP/端口);换 Wi-Fi 后代理会丢 |

**查看日志**:`docker logs cn-proxy`(加 `-f` 实时跟踪)

---

## 七、运维命令速查

```bash
ssh root@192.168.1.1            # 登录网关

docker ps                        # 看容器状态
docker logs cn-proxy             # 看日志(-f 跟踪)
docker restart cn-proxy          # 重启
docker exec cn-proxy sing-box check -c /etc/sing-box/config.json   # 校验配置

vi /etc/sing-box/config.json     # 编辑配置
cp /etc/sing-box/config.json /etc/sing-box/config.json.bak          # 备份
cp /etc/sing-box/config.json.bak /etc/sing-box/config.json          # 回滚
```

---

## 八、附注

- 代理只在局域网内生效(`192.168.1.1` 的 WAN 口默认拒绝外部访问),不会暴露到公网。
- 容器开机自启、Tailscale 身份持久化,路由器重启后无需任何手动操作。
- 出口 `cn-exit` 是一台国内云 VPS,约 10Mbps 带宽,刷网页/听歌/标清视频够用,高清视频会紧。
- **安全提醒**:VPS 的 root 密码曾在截图里明文出现过,建议尽快登录改掉(通过 `ssh` 登录后 `passwd`)。
