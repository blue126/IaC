---
title: 'OCI Hub 已知残留清理'
type: 'chore'
ticket: 'story-oci-hub-residual-cleanup'
created: '2026-11-07'
status: 'built'
baseline_revision: 'c5cc34f149b613941e4183f0224f2f319562826f'
route: 'full'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** 2026-11-07 核对确认三项残留已不再使用：`ansible/playbooks/configure-oci-hub-mosh-boundary.yml` 及其专用测试、`deliver-temp.py` 里 temp.sh 和 `existing` 流程分支、OCI Hub 上的两份旧备份。它们仍留在代码和主机上，让代码哈希、测试和运维判断多出无效路径。

**Approach:** 删除公开仓库的一次性 playbook 与专用测试，去掉 `hub-onboard.py` 代码哈希里的这一项；把私有 `wsctl` 的交付模块收敛到唯一的 apply-site/oci-hub 路径并同步测试；在 Hub 上先只读确认两份备份没有被引用，再删除准确路径。

## Boundaries & Constraints

**Always:** 只删除已确认不再被引用的目标；线上删除前先只读核对存在性和引用；测试必须真实通过；代码哈希会变化，部署前需确认没有未执行的开户计划。

**Never:** 不推送、不开 PR、不合并、不把私有代码部署到执行器；不删未确认的路径；不改动 `employee-data`；不修改历史规划记录。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HUB_DELIVER | 一份合法 oci-hub 设备包 | 上传到站点并核对 SHA-256 | 校验或身份不一致时 `DeliveryError` |
| LEGACY_PROFILE | 调用方再传 `profile='existing'` | 参数已不存在，TypeError | 明确失败，不再有静默回退 |
| HUB_BACKUP_CHECK | 两份旧备份存在且无引用 | 删除后路径不存在 | 无访问权限时报告缺口，不找其他凭据 |

</intent-contract>

## Code Map

- `ansible/playbooks/configure-oci-hub-mosh-boundary.yml` -- 一次性 Mosh 边界审批 playbook；无调用方，仅被下面的测试读取
- `tests/oci-hub/test-mosh-boundary-play.py` -- 专测该 playbook 的 netns 测试，删除后无剩余覆盖对象
- `tests/oci-hub/README.md` -- 测试清单和段落里引用该 playbook 测试
- `remotecc/wsctl/hub-onboard.py` -- `source_hash()` 第 137 行把该 playbook 计入代码哈希
- `remotecc/wsctl/deliver-temp.py` -- 交付模块；`profile` 分支、temp.sh 上传/下载、`require_existing_payload`、OneDrive 回执保护只服务旧流程
- `remotecc/wsctl/oci-hub-admin.py` -- 唯一的 `load_bound`/`publish`/`notify` 调用方，全部传 `profile='oci-hub'`
- `remotecc/wsctl/test-temp-delivery.py` -- 交付测试；`DeliveryTests` 整类走 temp.sh 路径
- `remotecc/wsctl/test-oci-hub.py` -- `LegacyProfileBoundary` 只验证旧 profile 的拒绝行为
- `remotecc/wsctl/hub-remind.py` -- 加载 `deliver-temp` 的注释还提到已不存在的 `--profile` 分派
- OCI Hub `ubuntu@159.13.46.201`（`settings.json` 的 `oci_hub.ssh_target`）-- `/opt/oci-hub/backup-readdress-20261103`、`/etc/oci-hub/portal.yaml.2335891.2026-10-30@06:32:23~`

## Tasks & Acceptance

**Execution:**
- [ ] `ansible/playbooks/configure-oci-hub-mosh-boundary.yml`、`tests/oci-hub/test-mosh-boundary-play.py` -- 删除 -- 无调用方且测试只覆盖自身
- [ ] `tests/oci-hub/README.md` -- 移出该测试的命令和说明 -- 不留失效引用
- [ ] `remotecc/wsctl/hub-onboard.py` -- 代码哈希列表去掉该 playbook -- 文件已不存在
- [ ] `remotecc/wsctl/deliver-temp.py` -- 只保留 apply-site 交付：删 `http()`、`require_existing_payload()`、temp.sh 上传/下载、过期与 OneDrive 分支，`load_bound`/`publish`/`notify`/`guard_payload` 去掉 `profile` 参数 -- 旧流程已无可达调用
- [ ] `remotecc/wsctl/oci-hub-admin.py`、`test-oci-hub.py` -- 调用点与测试去掉 `profile='oci-hub'`，删除 `LegacyProfileBoundary` -- 签名对齐
- [ ] `remotecc/wsctl/test-temp-delivery.py` -- 保留邮件渲染与站点交付覆盖，删除 temp.sh 用例 -- 测试跟随实现
- [ ] `remotecc/wsctl/hub-remind.py` -- 修正加载注释 -- 不再声称有 `--profile` 分派
- [ ] OCI Hub -- 只读核对后删除 `/opt/oci-hub/backup-readdress-20261103` 与 `/etc/oci-hub/portal.yaml.2335891.2026-10-30@06:32:23~` -- 用户已批准清理

**Acceptance Criteria:**
- Given 公开与私有仓库，when 搜索 `configure-oci-hub-mosh-boundary`、`test-mosh-boundary-play`、`temp.sh`、`LEGACY_PROFILE_MISMATCH`，then 除历史规划记录外没有代码或测试引用
- Given 私有 `wsctl`，when 运行 `test-temp-delivery.py`、`test-oci-hub.py`、`test-hub-remind.py`、`test-wsctl.py`、`test-hub-mosh.py`，then 全部通过
- Given OCI Hub 主机，when 核对两份备份的引用并删除，then 两个准确路径都不再存在，Portal 与配额服务仍为 active
- Given 所有改动，when 检查版本库，then 只有本地提交，没有推送、PR、合并或部署

## Implementation Notes

- 公共仓库基线 `c5cc34f149b613941e4183f0224f2f319562826f`，私有 `remotecc` 基线 `fe3f25e603506ff792deb2176c4f5f211bae5e54`。
- 实现由宿主会话在调查阶段直接完成，没有派发 step-03 子代理：改动集中在两个仓库的少数文件，调查已产出精确编辑。审核针对该版本的真实 diff 运行。
- 删除 `deliver-temp.py` 的 `main()` 与 `test_mail` 参数后，`templates/test-notice.html` 失去唯一调用方，一并删除；`mail_subject()` 不再接收 `test_mail`。
- `tests/oci-hub/inventory.yml` 的 `oci_hub_mosh_gateway` 组只服务已删除的 playbook，移除该组。`docs/deployment/mosh-oci-hub-pilot.md` 里的同名组描述的是私有 `mosh_inventory` 契约，`settings.json` 仍使用它，故保留。
- OCI Hub 只读核对（2026-11-07）：`/opt/oci-hub/backup-readdress-20261103`（executor.py 8296640…、portal.py 38e3486…）与 `/etc/oci-hub/portal.yaml.2335891.2026-10-30@06:32:23~`（f858f5c…）存在；在 `/etc`、`/opt`、`/var`、`/usr`、`/root` 搜索两个路径只命中 `auth.log` 中本次 sudo 记录。删除后两路径均不存在；`oci-hub-portal.service` active/running（启动于 2026-11-06 12:08，未因删除重启），`oci-hub-boundary.service` active/exited，`oci-hub-quota.timer` active/waiting。
- 代码哈希 `source_hash()` 变化，部署前需确认没有未执行的开户计划。

## Plan Change Log

## Review Triage Log

### 2026-11-07 — Review pass
- verdicts: 14 findings — high 0, medium 1, low 10, false 3, maybe-false 0
- lenses: quick (PAL clink, claude / claude-opus-5-5, return_code 0, no permission denials, duration 196.1 s, cost USD 1.4068382)
- findings:
  - `[low]` `[patch]` `deliver-temp.py:260` `mail_subject()` 仍返回 `Temp.sh 自动交付验证` — 真实存在；随后移除 `test_mail` 参数与整条路径，该字符串消失。
  - `[low]` `[patch]` 旧 CLI `main()` 留在文件里 — 真实存在且不可达，`guard_payload` 会让其失败；删除 `main()`、`argparse` 导入和尾部 `__main__` 分支。
  - `[low]` `[patch]` `test_mail` 与 `test-notice.html` 孤立 — 与上两条同根因；删除参数、模板引用和模板文件。
  - `[low]` `[patch]` `publish`/`notify` 的 `if approval:` 恒真 — 真实存在；改为无条件写入 `upload_subject_sha256` / `mail_subject_sha256`。
  - `[medium]` `[patch]` 删除 `test_bundle_hash_mismatch_stops_before_upload` 后 `BUNDLE_CHECKSUM_MISMATCH` 无测试 — 真实存在；在 `SiteDeliveryTests` 补回该用例，断言上传前停止。
  - `[low]` `[patch]` 外层 zip 只含 `FILES` 与回执 `0o600` 的断言随旧类丢失 — 真实存在；新增 `test_payload_is_the_unified_outer_zip_with_a_private_receipt`。
  - `[low]` `[patch]` 计划的 `LEGACY_PROFILE` 矩阵行没有测试 — 真实存在；新增 `test_removed_legacy_profile_is_rejected`，断言 `profile=` 触发 `TypeError`。
  - `[low]` `[patch]` `oci_hub_mosh_gateway` 组在测试 inventory 里孤立 — 真实存在；移除该组。文档同句描述的是仍在使用的私有 `mosh_inventory` 契约，不改。
  - `[low]` `[patch]` `test-hub-remind.py:127` 仍称 `--profile` — 真实存在；改为“加载的模块不应看到调用方参数”。
  - `[low]` `[patch]` 计划的验收命令只查 Portal，未覆盖配额服务 — 真实存在；验收与验证命令补 `oci-hub-quota.timer`，并执行核对。
  - `[low]` `[patch]` 两处非必要改动（`spent` 的默认参数、`UnifiedFormatTests` 的参数改名） — 真实存在；按 `AGENTS.md` 最小改动原则回退。
  - `[false]` `[reject]` 主机删除与 Portal 状态在 diff 里没有证据 — 主机操作不在版本库 diff 中；证据记入 Implementation Notes 与验收记录。
  - `[false]` `[reject]` 审核未验证测试与“仅本地提交” — 原生 Quick 层按规则不运行测试；宿主已运行全部相关测试，提交状态在交付记录中。
  - `[false]` `[reject]` source 视图缺 `_bmad-output` — X3 要求共享 source 不含 spec 与作者声明；票据与计划已放入该层 inputs，并从 diff 审核。

## Verification

**Commands:**
- `cd remotecc/wsctl && python3 test-temp-delivery.py` -- expected: 31 tests OK
- `cd remotecc/wsctl && python3 test-oci-hub.py` -- expected: 73 tests OK
- `cd remotecc/wsctl && python3 test-hub-remind.py && python3 test-wsctl.py && python3 test-hub-mosh.py` -- expected: 28 + 50 + 20 tests OK
- `ssh ubuntu@159.13.46.201 "sudo -n sh -c 'test ! -e /opt/oci-hub/backup-readdress-20261103 && test ! -e /etc/oci-hub/portal.yaml.2335891.2026-10-30@06:32:23~ && systemctl is-active oci-hub-portal && systemctl is-active oci-hub-quota.timer'"` -- expected: active / active
- `git grep -n -i "configure-oci-hub-mosh-boundary\|test-mosh-boundary-play\|temp\.sh\|LEGACY_PROFILE_MISMATCH"` -- expected: 仅历史规划记录

## Auto Run Result

**Summary:** 删除一次性 Mosh 边界 playbook 与其专用测试，去掉 `source_hash()` 里对应的哈希项；把私有 `wsctl` 的交付模块收敛为唯一的 apply-site/oci-hub 路径，删除 temp.sh、`existing` profile、旧 CLI 入口和 canary 邮件模板；在确认无引用后删除 Hub 上的两份旧备份。

**Files changed:**
- `ansible/playbooks/configure-oci-hub-mosh-boundary.yml` -- 删除
- `tests/oci-hub/test-mosh-boundary-play.py` -- 删除
- `tests/oci-hub/README.md` -- 移除该测试的命令与说明
- `tests/oci-hub/inventory.yml` -- 移除只服务该 playbook 的 `oci_hub_mosh_gateway` 组
- `_bmad-output/backlog/story-oci-hub-residual-cleanup.md`、`...-plan.md` -- 票据与计划
- `wsctl/deliver-temp.py` -- 只保留站点交付；删 `http()`、`require_existing_payload()`、profile 分支、旧 CLI 与 `test_mail`
- `wsctl/oci-hub-admin.py` -- 调用点去掉 `profile`
- `wsctl/hub-onboard.py` -- 代码哈希去掉已删除的 playbook
- `wsctl/hub-remind.py`、`wsctl/test-hub-remind.py` -- 修正加载注释
- `wsctl/test-temp-delivery.py` -- 邮件与站点交付覆盖，删除 temp.sh 用例，补回校验和、外层 zip、回执权限和旧 profile 拒绝用例
- `wsctl/test-oci-hub.py` -- 调用点去掉 `profile`，删除 `LegacyProfileBoundary`
- `wsctl/templates/test-notice.html` -- 删除

**Review:** quick 层（PAL clink，claude-opus-5-5，return_code 0，无权限拒绝，196.1 s，USD 1.4068382）。14 条 finding：0 high、1 medium、10 low、3 false；11 条 patch，0 条 defer，3 条 reject。`followup_review_recommended: false`（首轮仅 1 条 medium）。

**Verification:** `test-temp-delivery.py` 31、`test-oci-hub.py` 73、`test-hub-remind.py` 28、`test-wsctl.py` 50、`test-hub-mosh.py` 20，全部 OK；Hub 上两个目标路径已不存在，`oci-hub-portal.service` active、`oci-hub-quota.timer` active。

**Residual risks:** 代码哈希改变会让未执行的开户计划失效，部署前须确认没有进行中的运行；审核针对打补丁前的 diff，补丁为审核发现的最小修复并已重跑相关测试。
