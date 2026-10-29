# 首个 Jenkins peer agent 本地交付与范围取舍

2026-10-30 集成状态：原 2026-10-23 基线的 99 项通过记录保留为历史。基于最新主线整理后，七套回归为 98 项通过、1 项错误（当前 Terraform 文件闭包与投影策略不匹配）；真实 provider 假上游 CPU 预测仍通过、写次数 0。当前分支不可合并或启用，必须完成新增资源/模板与 state 的安全适配，保留完整 B 及拒绝未知输入的边界。

整理日期：2026-10-23。结论：本地代码实现与评审完成，生产部署与 CI-only 移交未完成。本记录整理已有证据，不表示重新执行了生产验收或新一轮外部评审。

## 版本与资料保留

- 公共基线：`9e38f6138d17dfed06c488382a073e5267a0f247`。
- 本地实现提交：`245e217f4f2e5fe96ff59143e0c9f446017ce0fc`；对应 tree：`6181ea6b5229567bda130e1c8240838cb0b378aa`。
- 本次整理前，已逐项核对原交付摘要中 73 个代码、配置、测试和指南文件的 SHA256，全部与上述提交交付记录一致。本次调整忽略规则、跟踪状态和文档；另将现有文档测试读取的准确性契约移入 `docs/reference/doc-accuracy-contract/`，仅更新读取路径，保留全部断言和原契约字节。Jenkins 运行逻辑未改。
- [批准的规格](../planning/jenkins-peer-agent-recovery.md)、本记录、[部署指南](../guides/jenkins-agent-bootstrap.md)及[私有应用接入契约](../guides/jenkins-private-app-ci-contract.md)随代码保留。
- `_bmad-output/` 整体停止跟踪并保留本地文件；其中重复源码清单、各轮补丁、原始模型响应、失败尝试和长篇过程日志不再作为新增交付内容。既有提交历史未改写，因此历史中仍可找到原记录。其他任务在该目录的本地文件同样保留。

## 实现范围核对

按规格 S1–S8 对照部署引用、入口调用和验收要求，在原交付核对时，没有发现可在保持完整 B 验收的同时直接删除的独立功能组。这是范围与依赖核对，不宣称所有实现都已被证明是最简设计。

| 保留内容 | 对应要求与必要性 |
| --- | --- |
| CT110 Terraform、host vars、agent Deploy/Verify | S1：复用现有 LXC 模块，恢复唯一目标和 inventory；不扩展其他节点 |
| 三 UID、systemd unit、离线工具链及锁 | S2/S4：隔开 plan、deploy、私有应用身份；限制每次作业的能力和依赖来源 |
| producer/projection/broker、schema 与 Read 策略 | S3：真实 provider 预测能力，同时避免把 HCP/PVE mutation 凭据和 raw state 交给 plan |
| admission、runner/client、事务审批、网络/probe 与材料校验 | S4：固定来源和 scope、两次审批、串行执行、残留隔离；由角色安装并由服务或入口调用 |
| watchdog、controller maintenance、bootstrap/config gate、证据收集 | S5/S7：独立于 Jenkins 的恢复和自更新，以及 controller=0 前的真实证据门槛 |
| 三个 staged Jenkins 入口、job 映射、应用接入契约 | S6：保持旧入口，准备五 job 的调度和清理验收；私有代码留在所属仓库 |
| 工具链准备/投影策略更新 CLI、回归与集成夹具 | S2/S3/S8：生成和核对离线材料、审核配置闭包，以及验证实际失败分支；不增加新框架 |
| `_bmad/custom/bmad-build-auto.toml` 两处文档路径修正 | 本任务已批准的 Auto 执行适配；不改变部署行为或评审规则 |

20 个 `scripts/jenkins/*.py` 均有角色安装、运行调用或指南操作入口；其中准备工具链和更新投影策略是运维 CLI，不是常驻服务。三个大 JSON 由实际角色/代码消费：toolchain lock 用于离线安装，provider schema 与 plan policy 用于成对投影和 broker 约束。未仅因行数多就删除或重新格式化这些材料。

2026-10-23 后续精简仅移除未调用的旧 JSON 投影三函数与未消费的 `ci/agent-access.yml`，将 HTTP 重定向拒绝原语归入已有 `control.py`，并取消 peer 对 broker 服务脚本的复制依赖。原生投影及真实 root policy 来源见现行规格与部署指南；以上历史提交和评审证据仍对应原交付时点。 本次精简保留原 98 项并新增 1 项，99 项回归、真实固定 provider 假上游预测（写次数 0）及相关 Ansible/文档验证通过。Gemini 完成 intent/edge 两层；用户于 2026-10-23 明确授权主代理复核替代另两层，复核未发现需追加修复或延期的问题。完整 B 的生产验收仍待部署阶段授权。

当前 `jenkins_agent_activate`、gateway/watchdog 激活和五 job enabled 均默认关闭，`cutover_authorized=false`，controller 保持 bootstrap。保留现有 `Jenkinsfile` 和 `Jenkinsfile-webhook-router` 的基线行为，新入口通过 staged 验证后再获批切换。

## 最终评审与取舍

最终四层通过 PAL 的 agy CLI 执行：intent-alignment、blind-hunter、edge-case-hunter、verification-gap。请求模型为 `gemini-3.8-flash-high`，推理档位 High（该模型最高可用档）；CLI 返回未报告实际模型字段，不能额外确认实际服务模型。四层均有完整报告、return_code=0、SUCCESS；其中两层初次超时后沿原会话各补完一次，未重复成功层。此前 Claude 两轮报告和额度失败记录仍在本地原始材料中。

最终 19 项：3 项修复、15 项拒绝（含不成立、范围外或生产待验收项）、1 项沿用前轮历史延期；无新增延期条目。下表保留每项取舍依据，生产未完成项仍列在后文，不因拒绝追加代码修复而视为已验收。

| ID | 处理 | 发现与依据 |
| --- | --- | --- |
| I1 | 不追加修复 | 真实CT110/IPAM及目标内核验收尚未执行。carried pass2 I1/I4：同一线上表面尚未部署，用户仍仅授权本地实施/提交；明确保留生产验收未完成，不据描述性差异提前部署或归零。 |
| I2 | 不追加修复 | 线上job切换与controller归零尚未执行。carried pass2 I2/I3：同一线上表面尚未部署，用户仍仅授权本地实施/提交；明确保留生产验收未完成，不据描述性差异提前部署或归零。 |
| I3 | 不追加修复 | 真实Vault/恢复证据/AD-9待生产授权。carried pass2 I7：同一线上表面尚未部署，用户仍仅授权本地实施/提交；明确保留生产验收未完成，不据描述性差异提前部署或归零。 |
| I4 | 不追加修复 | 门控代码不等于真实生产移交。carried pass2 I6/I8：同一线上表面尚未部署，用户仍仅授权本地实施/提交；明确保留生产验收未完成，不据描述性差异提前部署或归零。 |
| B1 | 不追加修复 | GC删除nonce锁文件导致新旧inode并发。carried pass2 B21：registry_lock内先证明record存在再open锁；GC同锁删除record/lock，之后新调用无法通过record检查，没有重新open另一inode的可达路径。 |
| B2 | 不追加修复 | bundle慢读者长时间占worker。读取截止仅约束读取阶段是有意设计；bundle仅root mTLS可取且有256MiB上限、socket单次写超时。闭环可信peer上的极慢传输为低频假设，额外传输监督器/期限不纳入首peer最小实现；不声称无限期占用已获证明。 |
| B3 | 不追加修复 | 本地只读Git子进程缺少逐调用timeout。唯一远端fetch已经timeout60。其他调用读root受管bare对象，未展示正常受支持输入上的锁等待；底层存储故障是全控制器问题。为每个本地读取添加防御性期限不是当前必要修复，按用户取舍要求拒绝扩张。 |
| B4 | 不追加修复 | peer断开使SO_PEERCRED崩溃selector。AF_UNIX凭据在连接建立时保存，peer close不使accepted fd失效；任务Sandbox实际16组socketpair在peer close后getSO_PEERCRED均成功。异常需要本地fd被关闭，而该fd此时仅selector持有，所述远端触发不成立。 |
| B5 | 不追加修复 | global.lock执行期持有阻塞maintenance。该锁正是mutation/清理与独立维护互斥的意图要求；watchdog用LOCK_NB等待，必须等run清理后维护。释放它会破坏已批准的串行边界。 |
| B6 | 已修复 | Terraform-only apply后提前返回未刷新inventory state。scripts/jenkins/transaction.py将已有refresh置于现有Terraform/playbooks判断后、空playbook早退前；test_terraform_only_apply_refreshes_state_before_returning_without_ansible验证apply→refresh且不启动Ansible。 |
| B7 | 不追加修复 | FQDN host_vars路径不能自动推导playbook。项目service/playbook使用kebab-case固定映射，带点hostname不属于自动推导契约；未映射输入按现有explicit_scope路径安全拒绝，并非已支持名称静默错误部署。不新增命名扩展。 |
| B8 | 不追加修复 | 材料统一错误消息丢失diagnostics。carried pass2 V5：消费者全部no_log且必须静默fail-closed；未证明接受坏材料或外部错误变更。测试假通过已在前轮单独修复，不能由此要求输出秘密上下文。 |
| B9 | 不追加修复 | legacy echo/未引用Vault路径的既有兼容问题。Jenkinsfile与公开9e基线逐字相同，问题未由peer入口引入。依据用户本轮明确要求有所取舍，保留旧入口字节及该历史旁注，不扩大本任务到legacy维护或工单操作；不宣称已修复。 |
| B10 | 沿用历史延期 | legacy缺HEAD~1时跳过构建。carried pass2 E17：相同旧入口/相同claim，已判为前置问题；本轮不重复验证、修复或新增延期条目。 |
| B11 | 不追加修复 | skip inspection后when引用results失败。Queue task第一条when与inspection使用同一activate/runner gate，Ansible顺序短路；第一条false时不求值results。此前真实role首装/未激活夹具已执行通过，所述skip场景没有missing attribute。 |
| B12 | 不追加修复 | 解包后chown跟随任意symlink越界。Runner解包前toolchain.check_archive、restore/drill前inspect_tar均只允许普通文件/目录，拒绝软/硬链接；私有root暂存区在启动消费者前chown，没有所述从archive进入symlink的路径。三个调用链均核对，避免重复nofollow保护。 |
| E1 | 不追加修复 | legacy Terraform异常退出码137等被视作无变更。这是原样保留的9e入口既有行为，peer transaction.run已经拒绝非允许退出码。按用户本轮取舍，仅保留历史旁注，不为了恢复旧入口而顺带扩展legacy功能改造；不声称该问题不存在或已修复。 |
| V1 | 已修复 | prepare_plan_ca生产hook缺少正常CI中的直接覆盖。复用RunnerTests.execute_fixture的plan profile，新增test_plan_ca_staging_and_execute_hook_use_public_readable_certificate，覆盖实际execute hook、有效CA/0444、非法CA拒绝和非plan不读取。 |
| V2 | 已修复 | apps-validation的真实Git object/tree检查未进CI回归。SourcePreflightTests.test_apps_validation_checks_real_repair_object_sha_and_tree_digest使用合成local bare Git，验证真实对象/tree摘要以及缺对象、错SHA、错摘要和畸形摘要的拒绝。 |

## 本地验证证据与复现

以下为实现提交收尾时的实际记录，本次文档整理未重新执行这 98 项：

| 套件（`tests/ci/`） | 通过数 |
| --- | ---: |
| `jenkins-peer-test.py` | 22 |
| `jenkins-controller-state-test.py` | 12 |
| `jenkins-runner-boundary-test.py` | 5 |
| `jenkins-source-preflight-test.py` | 4 |
| `jenkins-toolchain-unpack-test.py` | 4 |
| `jenkins-peer-repair-test.py` | 42 |
| `jenkins-role-fixture-test.py` | 9 |
| **合计** | **98** |

- 真实 Terraform 1.14.4 / bpg 0.70 经 broker 对假 HTTPS PVE 上游预测 VM/LXC CPU 2→3，假上游写次数 0；真实 Terraform dynamic inventory 与合成加密 Vault 的审批前后集成通过。
- repository fixtures、相关 41 文件离线 Ansible lint/control syntax、tracked 34 HCL fmt 和 native 31 文件 init/validate 通过；Ansible/HCL 此后未变化。native validate 仅有既存 CT120 timeout_start 弃用警告。
- 真实 Sandbox proc-root 反例验证了 user namespace 的隔离机制；这些结果不替代目标 LXC 的实际 systemd/cgroup 能力验证。
- 指定验证 Sandbox：`iac-codex-jenkins-peer-recovery-direct-v130`，linux_arm64；Kit 的 Terraform 1.14.9 / Ansible-core 2.20.10 与目标运行版本不同。另校验 Terraform 1.14.4；目标 amd64、Java 25、Ansible 2.19.12 尚需现场验收。

在该 Sandbox 的仓库根目录，单个普通套件使用 `python3 tests/ci/<suite>.py`；Ansible role fixture 需 login shell 激活已有工具环境。真实 provider 集成需提供对应 Terraform 二进制和已锁 provider mirror：

```bash
python3 tests/ci/jenkins-peer-provider-test.py --terraform <terraform-1.14.4> --mirror <locked-provider-mirror>
python3 tests/ci/jenkins-inventory-scope-test.py --terraform <terraform-1.14.4> --mirror <locked-provider-mirror>
python3 tests/ci/jenkins-peer-test.py --project-native
```

原始验证日志仍在任务 Sandbox 的 `/tmp/jenkins-peer-final-*.log` 等任务路径中，属于临时证据，可能随 Sandbox 清理消失；本记录保留版本、结果、覆盖与复现入口，不复制完整日志或巨量源码清单。临时二进制/mirror 不存在时，在已有安装授权范围内重新准备材料；不得用真实凭据或生产写入代替夹具。

## 本次资料整理验证

在任务 Sandbox 的临时 Git 快照中执行 `bash scripts/ci/validate-documentation.sh false` 全部通过；快照不含 `_bmad-output/`，因此同时验证了新克隆场景不再依赖被忽略的契约文件。批准意图契约逐字一致，四份文档准确性契约逐字一致；新整理文档的本地 Markdown 链接均有效。Jenkins 实现未变化，因此未重复执行先前通过的 98 项回归。

## 尚未完成的生产验收

这些属于已批准 B 范围，仍需各自部署/演练授权，未降为可选项：

1. IPAM/state/VMID/模板/存储复核，创建 CT110，目标 amd64 整套离线安装、真实秘密登记与节点重连。
2. 目标 LXC 的双向 namespace/proc/socket、IPv4/IPv6、cgroup、abort/双 fork/残留、并发及 OOM/磁盘预算验证。
3. 真实只读身份最小权限、当前 root/provider 覆盖和盲区验证；五 job 的调度、分阶段凭据、审批、清理证据及应用所有者补丁。
4. 获批约 10 分钟停服窗口内完成实际备份/演练、故意失败恢复、Gitea 不变及独立自更新验证。
5. 两次 Ansible 幂等验证及全部移交证据齐全后，单独批准 controller=0，再由正常 Jenkins plan 对账。

旧入口缺 HEAD~1 时跳过构建，以及历史退出码/路径引用问题，本轮未修复；它们未由新 peer 入口引入。投影覆盖仍为 partial，零变化不能作为整个 root 无变化证明。推送、合并和生产部署均未执行。
