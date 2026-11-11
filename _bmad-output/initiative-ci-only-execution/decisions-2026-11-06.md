# CI-only 架构评审决定（2026-11-06）

逐项评审的结论，用户已逐项确认。
对象：`docs/architecture/ci-only-execution-architecture.md`。本文件优先于 SPEC 和 `decisions-2026-11-05.md`。

## 总体方向

Jenkins 改为标准 agent 流程：Jenkinsfile 在 agent 上直接跑各阶段。root runner、admission、watchdog、只读 plan job 都去掉。
后面各项里写着 runner 或 admission 的，以“结构决定”一节为准。

## 结构决定

### 第 20 项 runner：A，标准 agent 流程

- Jenkinsfile 在 agent 上直接跑 plan → `input` → apply → 刷新 inventory → `input` → ansible → verify。
- 保留 `iac-deploy`、`iac-apps` 两个身份；`iac-plan` 去掉。
- 全局锁用 Lockable Resources：`lock('iac-global')`，跨两个 agent。
- 删除 `job-runner`、`controller-admission`、`job-network`、`isolation-probe`、`runner-client`、`job-entry` 及相关测试（约 1400 行，不含 watchdog 和 plan 部分）。admission 里 Webhook-Router 用到的校验要先确认去向。
- 已接受风险：检查跑在 pipeline 里，Jenkins 管理员可绕过。Replay 关掉或只留给管理员。
- ticket R1（三个隔离身份）和 recovery S4 要改，走 Sofia。

### Watchdog：去掉

- 改为备份加手动恢复：停 Jenkins，归档 `JENKINS_HOME` 和服务配置，定期演练恢复。
- agent 更新：从 Mac 运行，确认无 job，重启 agent。
- 要改：ticket R2（Sofia）、`config-write.yml`/`config.yml` 门禁、测试、AD-11（“没有经过验证的备份就禁止变更”）。
- 线上若已部署，要补卸载。

### Gitea：从 CT107 剥离

- 新建 LXC，由 Terraform 管，`gitea` 组，迁移 `/var/lib/gitea`、`/etc/gitea`，更新 Jenkins job、webhook、homepage。
- `deploy-gitea` 成为普通 Jenkins owner。迁移后 CT107 才能做整 CT 的 PBS 恢复。
- 先决定新主机是否加 tailnet。cloudflared 留在 CT107。

### RemoteCC IaC 拆分：A

- 迁入私有 `remotecc` 仓库，子目录名 `IaC`。不卡 CI-only，单独做。

## 逐项决定

1. **A：** OCI 规则留在 `terraform/oci`，由 Jenkins 持有。AD-14 收窄为主机侧 hub 服务。`oci-hub-ingress.auto.tfvars.json` 是 AD-6 的 `shared`。D2、D3 已定。
2. **A：** 真实凭据上线前脱离公告范围。High 公告 14 天内处理。AD-11 加安全升级路径。当前回滚是手动备份恢复，Gitea 迁走前不用整 CT 回滚；按 AD-9 格式记录。
3. **A：** 关闭 lightweight，保留 `skipDefaultCheckout(true)`。状态写入 `ci/agent-jobs.yml`，验证改由 CI 和 Jenkinsfile 完成（原为 admission）。AD-10 注明例外。验收要两次真实 push。
4. **C：** 留在 ansible-core 2.19，升到 2.19.15，`requirements.txt` 和 BOM 钉版本，记录风险。
5. 备份后有写入时拒绝恢复这一规则，改为手动恢复的检查项。重新捕获并演练。AD-9 下的灾难恢复归 D2。
6. **A：** 改 ticket/SPEC：PR 验证是质量检查。改动 workflow、`scripts/ci/`、`tests/ci/` 的 PR 在合并时审查。
7. **A：** execution map 声明 delegate 目标，经 inventory 解析，进入审批摘要和凭据范围，解析不了就拒绝。CI 扫描 `delegate_to`。普通 lane 拒绝 CT107/CT110。
8. 关闭，用户推迟。
9. **A：** 水位按 root/playbook 存，verify 后沿 main 祖先推进，缺失就拒绝，普通 lane 只跑 main head，回退走前向 revert。存储改由 `iac-deploy` 写在 CT110（原为 root 独占）。
10. **A：** 单一全局锁，从开始到终态。清理无法证明时进入隔离，改用 agent 上的标记文件，下一个 job 看到就拒绝，`verify-and-release` 清除。`force-unlock` 只用于 HCP state 锁。排队靠重试。重写 AD-4。
11. **A：** 一个文件或字段一个 owner，运行时归 IaC，应用内容归 app lane。审计 `n8n-rental`，保持 `n8n_checkout_app: false`。
12. **A：** 自动部署的 playbook 禁止可变引用，CI 扫描。`rustdesk`、`anki-api`、`anki-desktop`、`immich`、tailscale install.sh 在各 playbook 移交时修。
13. **A：** AD-1 增加 owner `control-plane`：`deploy-jenkins`、`upgrade-jenkins`、`deploy-jenkins-agent`、`deploy-cloudflared` 由操作者在 Mac 运行，按 AD-9 格式记录。Jenkins 拒绝它们。触及 CT107/CT110 的 Terraform plan 失败关闭。CT110 不在 state，要 import。
14. **A：** 第一步把隧道路径改成 `^/github-webhook/$`。探针是完整的 `X-GitHub-Event: ping` 加非空 JSON，测无签名、错签名、正确签名。手动恢复和 JCasC 应用后重跑。`X-Jenkins-Validation` 记为已接受风险，上线前确认不触发 build，否则用 WAF。
15. **A：** Jenkins 显式 `-i` 指定 `groups.yml`、`terraform.yml`、`oci/hosts.yml`。execution map 声明每个 playbook 允许的组。`site.yml` 和 `hosts: all` 不进普通 lane。验证 `-i` 下 group_vars/host_vars 仍能加载。`terraform-remotecc.yml` 随 RemoteCC 拆分移走。
16. **A：** 每个 root 一个事务，各有 manifest、审批、水位。每个 playbook 只依赖一个 root，否则拒绝。预览就是部署 lane 审批前的 plan，Mac 只读 plan 可用。OCI key 只注入 OCI 事务。一次 main 构建是一个批次，拿一次锁，按序跑各 root 再跑 Ansible。出站改为只管内网（见第 21 项）。
17. **D：** 部署密钥全部放 Jenkins Credentials，审批后用 `withCredentials` 注入。
    - 部署凭据放在只含部署 job 的 folder。
    - 去掉 CT107 明文 root 文件和 admission `secrets` 操作。去掉“密钥变更使审批失效”。
    - Jenkins Credentials 是 CI 运行时唯一存储，Vault 仍是来源，轮换两边都改。
    - JCasC 不写 `credentials:` 段，上线前实测现有凭据不受影响。`CASC_STRICT_SECRET_RESOLUTION=true`。
    - 已接受风险：CT107 被攻破就全部泄露；密钥短暂经过 agent；`JENKINS_HOME` 备份含全部密钥，恢复要带 `master.key`。
    - OCI key 仍是 UI 上传的 secret-file，11-05 决定不变。
18. **A：** AD-1 把“只读”改成“不改生产配置，但会连主机、探测、写临时文件”。`check_mode: false` 只用于读取或临时候选文件。CI 扫描 `file`/`copy`/`template` 等写入模块。7 个模板逐一核实，确含密钥的加 `diff: false`：`anki-writer.env`、`ldoce5-api.env`、`Caddyfile`、gitea `app.ini`、immich `env`、`jenkins-agent.service`、`jenkins-plan-gateway.service`。审计依据：当前 79 处，静态审查，未改生产配置。
19. **A：** HCP 组织已核实为 `free_standard`，`teams: false`。
    - 令牌放 Jenkins Credentials，只注入部署事务。AD-5 写明按事务限制，HCP 不限制 workspace。
    - Jenkins 能碰全部 workspace 记为已接受风险，preflight 只放行 execution map 里的 workspace。
    - 去掉 `IaC-ReadOnly-Plan`、`Jenkinsfile-plan`、`plan-snapshot.py`、`iac-plan`、gateway 的 plan 部分。
    - 后续在 RemoteCC 迁移时把 `iac-remotecc` 搬到单独 HCP 组织。Free 能否开第二个组织、owners 团队令牌能否这样用，尚未核实。

21. **A：** CT110 出站只管内网：各身份只能到声明的内网主机，其他私有网段拒绝；公网 HTTPS、DNS 和到声明 OCI 主机的 SSH 放行。公网外传记为已接受风险。这改写了第 16 项的允许清单。

## 中等问题

- **RW-06：** AD-9 写明首次引导 diff 只含 CT110 和 inventory，超出就停。
- **R-05、R-06：** 已被第 14、17 项覆盖。
- **R-07、R-08：** 已被第 19 项覆盖。
- **R-09：** BOM 列全 Pipeline 用到的插件（含 Lockable Resources、Mailer），CI 检查缺项，随第 2 项升级补齐。
- **R-10：** bpg 0.70 记为已知风险，升级单独做，先跑真实 plan。
- **R-11：** 保留 `-lock-timeout`，在 Jenkinsfile 调 Terraform 时加上。
- **R-12：** 通知走 Resend SMTP，Jenkins 单独 API key 放 Jenkins Credentials，上线前测一封。
- **R-13：** 写 spine 时补来源和核查日期，含 HCP 套餐。

## 授权边界

以上决定不授权部署。CT110 部署、真实密钥使用、controller 归零、提交、推送都要单独授权。
