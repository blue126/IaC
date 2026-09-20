# Hermes Gateway SSH Access

`hermes-gateway-access` 是经仓库所有者明确授权、供 Hermes gateway 使用的 SSH 公钥。

## 授权范围

该 key 定义在 `ansible/inventory/group_vars/all/common.yml`；`common` role 会将其部署给每台受管 Linux 主机的主要用户。此全站范围是有意设计：gateway 需要在整个受管 Linux 环境中保持一致的运维访问能力。

## 运维边界

- 匹配的私钥必须始终由 homelab 所有者控制。
- 在确认 gateway 替换或恢复方案前，不得删除或轮换该公钥。
- 修改该 key 或其全站授权范围需要所有者的明确授权与审阅。
