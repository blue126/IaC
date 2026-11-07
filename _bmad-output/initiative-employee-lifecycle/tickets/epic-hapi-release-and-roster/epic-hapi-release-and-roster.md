---
id: 7
type: epic
title: "HAPI 应用独立发布，员工名单由执行器推送"
parent: initiative-employee-lifecycle
covers: [R19]
sources: [docs/planning/2026-11-05-hapi-architecture-redesign.md]
companions: [docs/architecture/hapi-control-plane.md]
after: [epic-hapi-access]
refined: false
risk: high
---

# HAPI 应用独立发布，员工名单由执行器推送

## Description

HAPI 应用代码移到私有 `remotecc/hapi-control/`，经 `wsctl hapi-release` 发布到 VM500；`wsctl enforce` 和 `wsctl hapi-sync` 经 SSH 把员工名单交给 VM500 的 `hapi-ctl apply`。日常路径不再经过 Ansible。到期员工被拒绝登录 HAPI，VM502 转为普通员工 VM。

## Outcome

管理员改登录页或员工变化时不用走 Ansible，到期员工不能再登录 HAPI。

## Done when

- 改一行登录页只需 `wsctl hapi-release`，失败自动切回，可手动回滚。
- `hapi-sync` 和 `enforce` 的运行过程中没有 `ansible-playbook` 写 VM500。
- 到期员工在下一次成功的 `enforce` 后被拒绝登录，续费后恢复，已验收。
- 运行 `deploy-hapi-control-plane.yml` 和 `deploy-hapi-shared-hub.yml` 不改路由、令牌和名单文件。
- VM502 走普通员工路径，代码里没有 `static_routes`、`static_ids`。

## Boundaries

- 不改 Hub 二进制、Cloudflare 的 Terraform 归属，不做 VM500 从零重建。
- 不改网站，不新增网站接口。
- 每一步线上操作都单独授权。
- 取代 `epic-hapi-access` 中“不改 VM500 上 HAPI 服务本身的部署方式”和“不改 VM502 现有 route 与会话历史”这两条边界。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R19)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-2, AD-10, AD-13, AD-14, AD-16, AD-20, AD-22, AD-23, AD-24
- plan — `docs/planning/2026-11-05-hapi-architecture-redesign.md`
- guide — `docs/architecture/hapi-control-plane.md`

## Notes

- Decision: 2026-11-05 用户决定取消单独的 HAPI 开关，紧急时直接关 VM；到期只停 route；名单推送；`hapi-ctl` 留在 VM500；VM502 不保留旧会话；VM500 损坏靠备份恢复。
- Decision: 2026-11-05 initiative R18 已按取消单独 HAPI 开关修订。
- Decision: 2026-11-05 tracer bullet 是故事 2：VM500 上用新代码比对线上文件，不改线上。
- Decision: 2026-11-05 故事 1 现场核实结果：VM500 为 Python 3.14.4、nginx 1.28.3、cryptography 46.0.5，SSH sudo 免密可用，`trust.json` 存在。Hub 自 10-31 起未重启，`credentials.json` 在 11-03 改过，新员工令牌生效，推断为热加载，二进制本身未验证。线上 8 条路由；`access_enabled` 为 true，`static_routes` 为 control→vm502。当前没有已到期员工，P4 不会立即拒绝任何人。执行器 runs 下有 1 个未走完的 create-workspace 检查点（75539dbf），时间和用途未确认，P2 前要处理。
- Decision: 2026-11-05 故事 2 线上比对通过：`hapi-ctl apply --check` 用真实名单比对 VM500 的 7 个文件，除代码路径外差异为零。私有分支 `hapi-control` 提交 9f42040。`test-proxy.py` 留在 IaC 到故事 10。
- Decision: 2026-11-05 P2 切换：第一次发布（0a6bd4a385c56efe）健康检查未等待鉴权套接字，自动切回又删除了 `current`，HAPI 中断约 27 秒（UTC 12:26:36–12:27:03），手工恢复。修复 e91de24 后发布 4a7355cc9d0870ed，未重启鉴权，Nginx 已指向 `current`。
- Decision: 2026-11-05 P3 完成：`vm500_writer` 改为 hapi-ctl，首次 `hapi-sync` 报告 changed=false、reaped=[]、PVE 和 Access unchanged，日常路径不再调用 Ansible，开户和退役解冻。Semaphore 每日 `hapi-sync` 模板还没加，属故事 8 剩余项。
- Decision: 2026-11-05 P4 开启：`enforce_push` 为 true，首轮 `enforce` 推送成功，无变化，没有关机或开机。到期拒绝的真实路径还没用测试员工验证。
- Decision: 2026-11-06 P6 提前到 P5 之前完成：VM502 转为员工 `control`，删除 `static_routes`。`hapi-install` 不会重启 Runner；Hub 拒绝属于旧空间的 machine ID（403），删除 VM502 `~/.hapi/settings.json` 的 `machineId` 后恢复。
- Decision: 2026-11-06 到期实测通过：`control` 改为已到期后，定时 `enforce` 停用路由并关闭 VM502，浏览器被拒绝；恢复后路由启用、VM502 开机，身份绑定保留。
- Decision: 2026-11-06 P5 提前完成：删除 `hapi-registry`、`vm500_writer`、`enforce_push`、`static_ids`，线上版本 7a65901fbfb2cabe。`test-proxy.py` 移到 `hapi-control/tests/`。`_bmad-output/` 改为随仓库提交。
- Decision: 2026-11-06 noVNC 清理完成：线上版本 da6df049cc5f12d2 去掉旧路由，VM500 卸载 `novnc` 和 `websockify`。
- Decision: 2026-11-07 WILL-112 核对私有代码后的已知缺口：7.5 的“回滚到不支持的 schema 被拒绝”只有前向测试，修复后没有线上回滚记录；7.10 的测试员工只记录了到期和恢复，开户、退役没有记录，“观察一周”被提前。由 `story-lifecycle-e2e-acceptance` 补。
