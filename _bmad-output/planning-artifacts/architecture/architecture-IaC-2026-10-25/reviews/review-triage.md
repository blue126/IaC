# 架构独立评审分诊

日期：2026-10-25。两项架构视角均由已批准的Claude Opus 5.5经PAL独立完成，CLI return_code=0、is_error=false、permission_denials为空，返回模型与请求一致。完整原文分别保留，不按重叠去掉任何发现。报告中的“Validate”是只读reviewer自述；宿主仍按本次architecture Finalize执行分诊/文档修正，没有变更父任务意图。

## 共同问题及处理

| 原报告位置 | 处理 | 目前状态 |
|---|---|---|
| rubric HIGH-1 / consistency H5 | 新AD-14、启动前MemAvailable/ARC门槛、Windows提前验后关、禁止高负载验收并发 | 用户已选实测受控超配；附录G明确8/4/10GiB与PSI停止/恢复线，生产停止范围仍须实施批准 |
| rubric HIGH-2 / consistency H4、M3 | 硬quota与Samba报告值必须留余量；CT111备份固定stop；容量所有权分清 | 用户已选报告760GiB/硬限额800GiB/差额40GiB；实际配置核验通过才开写 |
| rubric HIGH-3 | 图示PBS VM100位于pve2，预算合计PBS/VM108/ARC/宿主，PBS运行参数零动作 | 用户接受共享pve2故障域；可达恢复点及数据截止点必须记录，不保证双机故障回退 |
| rubric HIGH-4 / consistency M2 | 固定服务文件直接adoption + 精确state rm/import；无创建镜像重放、共享模块lifecycle不改 | 文档已修，真实state操作未执行 |
| consistency H1、M6 | VM108源也退注册/留置ID；首次目标启动后默认T1，例外R0必须有书面无业务写入证据和明确接受副作用丢弃 | 已修；内部API及隔离演练仍为准入项 |
| consistency H2 | AD-13按node/pool累计认领A/B/C，包含metadata、VM108及试恢复，整体回退不重复使用同一free | 已修；具体账本实施前填入 |
| consistency H3 | T0/T1从创建时保护并复核，完整PBS身份及owner、pve2 VM108专用namespace，取消保护另行授权 | 已修；保护不是离机冗余 |
| consistency M1 | T0后、源尚注册时宿主离线清单，再卸载/退注册；两侧同视图与映射 | 已修 |
| rubric MEDIUM-1 / consistency M4 | 补两端guest-common/cluster/qemu/container版本及AbstractConfig哈希，要求演练/执行匹配 | 已修，升级后失效需重新演练 |
| rubric MEDIUM-2 / consistency M7 | 明确驱动Spec需由bmad-spec吸收新方法/窗口/容量/回退依据，未对齐不进入实施 | 已列为交接条件；未越权手改SPEC派生文件 |
| rubric MEDIUM-3 | rpool SMART/历史错误说明和ZFS健康为准入；源清理需迁后数据备份verify | 已修，未宣称单盘变成冗余 |
| rubric MEDIUM-4 | link_down配置之外加入真实guest/tap/veth/生产网段断链验证 | 已修，真实演练未执行 |
| consistency M5 | 同ID孤立旧盘保留期间禁止rescan/ID复用，VM108 R1空间入账 | 已修 |
| rubric LOW-1 | VM源长度范围块摘要列作可选强证据，区分Cloud-Init等有意重建盘并计入时间 | 已补说明，未虚称块比对已运行 |
| rubric LOW-2 | R1的QEMU恢复后显式onboot=0再验收 | 已修 |
| rubric LOW-3 / consistency L1 | 统一quota/refquota/reservation800G，设置失败停止；容量停止线不由CT111 reservation保证 | 已统一为报告760GiB、quota/refquota/reservation800GiB，40GiB差额 |
| rubric LOW-4 | CAP-2映射加入AD-11及累计回退/内存/故障域 | 已修 |
| rubric LOW-5 | 固定bpg0.70.0并禁止PBS任何重启相关变更，不以reboot=false放行 | 已修 |
| consistency L4 | 临时ID试恢复也记入累计容量，不借用无记录余量 | 已修 |

## 有证据修正/不采纳的建议

- consistency H4建议Samba由Ansible拥有，不符合该文件头：configure-fileserver-timemachine.yml明确one-time bootstrap，之后Webmin owns。采纳“容量有多个写者及报告值无余量”的问题，拒绝把当前ownership改为Ansible常规接管。保留Webmin/操作者，冻结1T bootstrap；不是把整个H4拒绝。
- consistency L2要求全部AD统一状态标签不是已安装方法要求；[ADOPTED]用于已有决定、[ASSUMPTION]用于未确认调用，其他为本次新增规则，保留真实语义，不用标签制造已批准。
- consistency L3所述AGENTS概述仍写旧provider属于范围外文档漂移；本方案按现有代码bpg0.70.0，不改AGENTS或升级provider。
- 两角色未执行lint是其只读限制，不是整体gate缺失：宿主在分发前及修订后已独立运行lint_spine，零发现。其余现场演练仍未执行，没有被文档评审替代。

## 原文与版本

完整报告：review-architecture-rubric.md、review-architecture-consistency.md。execution-architecture.json记录固定输入SHA256、实际CLI/模型/用量及私有原始响应路径。费用字段costBasis=list，仅为模型标价估算，不作为账户实际扣款证据。宿主使用标准MCP stdio客户端调用既有隔离PAL配置；本次不冒称完成Codex原生工具注册/自动路由接入验收。

明确修正已经应用到草案；这不等于修订版又跑过一轮架构评审，原报告版本与修订版本分别记录。配置要求的structure/prose检查已完成并修订，三项用户选择已落实，方案文档定稿。保留现场执行停止线；本次没有自动重复已成功评审层，也未把修订版冒称独立重审通过。
