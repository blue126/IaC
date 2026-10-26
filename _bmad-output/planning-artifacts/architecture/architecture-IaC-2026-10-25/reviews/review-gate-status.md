# 独立评审与修订状态

2026-10-25：本轮完成的是bmad-architecture架构门禁及其doc_standards文档编辑，不是重新启动最初的独立Spec评审。本轮只审阅/修订文档，没有迁移、备份/恢复、配额、来宾、state、部署或清理写入。

## 执行结果

| 角色 | 通道/实际模型 | 结果 | 完整报告 |
|---|---|---|---|
| architecture-rubric | PAL / claude-opus-5-5 | 完整返回，提出需修订事项 | review-architecture-rubric.md |
| architecture-consistency | PAL / claude-opus-5-5 | 完整返回，提出需修订事项 | review-architecture-consistency.md |
| structure | PAL / claude-opus-5-5 | 完整返回，25条编辑建议 | review-structure.md |
| prose（after structure） | PAL / claude-opus-5-5 | 完整返回，45条编辑建议 | review-prose.md |
| 技术现实层 | 原生公开文档/代码核验 | 已完成及增量核对，非生产演练 | review-technology-reality.md |

四个PAL角色均return_code=0、is_error=false、permission_denials=[]，实际模型匹配请求，完整原文无截断。architecture两层并行；prose仅接收本次structure的完整结果，没有读取其他层。私有响应保存在对应execution JSON引用的位置。费用costBasis=list仅为标价估算，不是账户扣款证明。

## 修订与剩余事项

明确问题已按review-triage.md处理：唯一权威谱系/VM108源退注册、累计回退空间、protected恢复点与namespace、内存启动门槛、PBS共享故障域、固定state重新收编方式、版本/哈希证据及原Spec对齐门槛。Samba当前由Webmin拥有，未按评审推断改为Ansible常规接管。

结构/措辞建议已选择性采纳：状态与术语前置、阶段和单guest循环、关键服务流程回到正文、回退认领集中、收尾移到最后、单位/指代澄清。保留使用点安全强化，不为减字而删除容量、完整性或回退条件。原始两条编辑推断不采纳：vzdump stop不统一写成“备份后才重启”；回退分界仍是首次启动，不按开放客户端分界。generic未知unused记录也不全部改称无效，只明确CT111已证实无效的记录。

用户已明确答复并写入方案：
1. Samba报告760GiB、ZFS硬限额800GiB，保留40GiB差额。
2. 按实测受控内存超配，Windows提前验证后关机；附录G落实8/4/10GiB及PSI操作阈值、逐台启动和值守规则。
3. 接受PBS与VM108共pve2故障域，明确可达恢复点与数据截止点，不保证双机故障回退。

三项策略问题已关闭，架构与方案文档status为final，表示设计定稿，不表示已经获准或能够立即执行。技术准入另有pve2/PBS现场核验、同ID内部API/网络栅栏演练和Linux真实ACL/xattr检查；文档评审不替代这些验证。驱动Spec应经bmad-spec吸收修订，不手改其派生文件。

## 校验与版本边界

- 宿主lint_spine零发现，15个唯一AD；Bash文档块语法通过，未执行；Python/Perl helper正文与之前已做有限校验的版本相同。
- 先前本机内容分支样本使用空xattr stub，不计为真实Linux ACL验证；PVE先前仅做Perl -c和API存在性读取。
- 原评审输入SHA256在execution-architecture.json、execution-editorial.json；最终文档SHA256在final-draft-manifest.json（沿用原文件名）。没有把修订版冒称又独立重审通过，没有自动重复已成功架构层。
- 原始报告保持不改，故其中提到“尚无外发授权/未执行外部评审”是当时输入状态，由本状态页更新。三项用户策略已于本轮答复后关闭；现场准入尚未通过，不能把文档final当作实施验收。
