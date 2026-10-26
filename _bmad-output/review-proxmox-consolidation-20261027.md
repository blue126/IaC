# Proxmox迁移 Quick审核

方法：原生Quick，经PAL default；请求/实际模型：claude-opus-5-5。return_code=0，permission_denials=[]，is_error=false；原文完整。单次审核，约188.8秒，标价估算1.2143 USD（不代表实际额外扣款）。

## 原始8条意见

- **`terraform/proxmox/container-lab.tf:96-100`（diff 2833-2839）`lifecycle.ignore_changes = [initialization]`**：这里忽略的是整个 `initialization` 块，不符合 runbook 附录 E 的规则。附录 E（diff 第 85 行）规定："仅在证实provider读不回某个创建字段时，才能只把该字段的最小路径加入该直接资源的lifecycle ignore_changes"。按现在的写法，`initialization` 下 DNS、ip_config、user_account、datastore、interface 等所有可读回的字段，以后漂移都会被静默忽略。同一次变更里，`pdm.tf:907-911` 和 `openbao-testbed.tf:2988-2991` 都只忽略了 `user_account[0].keys/password` 两个最小路径，只有 VM108 放宽到了整块。代码注释说的是"bpg 0.70 reads legacy creation metadata"，但没有指明具体是哪个读不回的字段。

- **`terraform/proxmox/container-lab.tf:94-96` 的 `output "container_lab_ip"`，以及 `terraform/proxmox/fileserver.tf:765-767` 的 `output "fileserver_ip"`**：两个 output 都写成了字面量字符串，分别是 `"192.168.1.108/24"` 和 `"ip=192.168.1.111/24,gw=192.168.1.1 (LXC)"`，没有引用新的直接资源。runbook 附录 E（diff 第 82-83 行）要求"服务outputs转为新直接资源引用"。实际配置的地址如果变了或被改了，output 照样输出旧值。fileserver 甚至把旧 module 输出的格式后缀 `(LXC)` 也写死了。plan 中"等值输出"只是说值相同，并没有给出不必引用资源的豁免。

- **`terraform/proxmox/fileserver.tf:690-693, 754-762`**：从 `module.fileserver` 改成直接资源后，原 module 里对 `description` 的 ignore 被丢掉了。证据是 `terraform/modules/proxmox-lxc/main.tf:82-84` 的 `ignore_changes` 包含 `description`，注释为 "Preserve operator-maintained notes on existing containers"。新资源写死了 `description = "Managed by Terraform"`，lifecycle 只忽略 `template_file_id` 和 `user_account`。这也违反了 AGENTS.md 的规则："Lifecycle blocks: Use ignore_changes for clone, full_clone, efidisk, ostemplate, description"。今后只要有人在 PVE 里修改 CT111 的备注，plan 就会出现更新，一次 apply 就会把备注覆盖掉，行为比 adoption 之前倒退了。

- **`terraform/proxmox/container-lab.tf:35-40` 和 `terraform/proxmox/openbao-testbed.tf:71-76`**：两个文件都声明了 `efi_disk`，但 lifecycle 里没有对 efidisk 做任何 ignore。这违反了 AGENTS.md 中 "Use ignore_changes for … efidisk" 的约定。仓库中可对照的写法是 `terraform/modules/proxmox-vm/main.tf:141` 忽略了 `efi_disk[0].pre_enrolled_keys`。三台 OVMF 来宾（108/112/113）都是 `prevent_destroy`，一旦 efi 属性读回不一致，就会出现 plan 无法通过、却又不能 replace 的状态。

- **`ansible/roles/ubuntu-vm/defaults/main.yml:3` 和 `ansible/playbooks/deploy-container-lab.yml:53`**：known_hosts 路径改成了 `/root/.ssh/known_hosts-container-lab`，但 pve0 上实际固定主机密钥的仍是旧文件 `known_hosts-ubuntu-2604`。plan 第 996 行写明"未迁移或清理远端known_hosts文件"。新文件只有在 Deploy play 的 role 任务（`roles/ubuntu-vm/tasks/main.yml:19-24`）里才会写入。因此按 AGENTS.md 规定的健康检查方式单独运行 `ansible-playbook playbooks/deploy-container-lab.yml --tags verify` 时，第一个 SSH 任务带 `StrictHostKeyChecking=yes`，必然因为找不到主机密钥而失败。而 VM108 按设计保持 stopped/onboot0，Deploy play 也不适合拿来补写这个文件。

- **`_bmad-output/planning-artifacts/architecture/architecture-IaC-2026-10-25/runbook.md` 附录 E（diff 第 71-75 行）**：这次只在前面加了一段命名修订说明，但标题"确定的IaC重新收编流程（仅计划，未执行）"和正文"本轮不编辑Terraform业务代码和远端state"都原样保留。这与同一 diff 的实际情况矛盾：本次已经新增和改写了 `container-lab.tf`、`fileserver.tf`、`pdm.tf`、`openbao-testbed.tf`，plan 第 69 行也记录了"HCP精确state-only接管完成，最新发布serial104"。文件头（diff 第 40 行）已经改成"实际阶段……以执行计划实录为准"，附录 E 却仍声称未执行，现行事实前后不一致。

- **`terraform/proxmox/openbao-testbed.tf:128`，`resource "terraform_data" "openbao_testbed_authorization" {}`**：这是一个没有 input、没有 precondition、也没有注释的空资源。对比同仓库 `pnetlab.tf:7-14` 的 `terraform_data`，后者带有明确的 `precondition` 授权门槛。这里的名字叫 "authorization"，实际上什么也不检查，看起来只是为了在 state 里保住一个对象。如果原来的意图是授权门槛，那么这个门槛已经失效。

- **`terraform/proxmox/openbao-testbed.tf:130-148, 150-163`**：`ansible_host.openbao_testbed` 的 `for_each` 和 `output "openbao_testbed_identifiers"` 又把 name/vmid/IP 各手写了一遍，没有复用同文件的 `local.openbao_testbed_adopted`。同一组身份数据因此有三份副本，改其中一处，另外两处会悄悄失去一致。另外，`ansible_host.openbao_testbed` 没有 `depends_on = [proxmox_virtual_environment_vm.openbao_testbed]`，而同一变更中的 `pdm.tf:917`、`fileserver.tf:771`、`container-lab.tf:100` 都加了对 adoption 资源的依赖，写法不一致。


## 核实、修复与最终验证

原始8条逐项核实：6项采用最小patch，2项有实际证据反驳，不新增架构/授权系统或审核轮次。详细逐项verdict/证据见执行计划 Review pass。

| 意见 | 结论与处理 |
|---|---|
| VM108整个initialization ignore | 不采纳：旧NoCloud seed由固定CD-ROM拥有；原实机预览证明去除该旧创建元数据会ForceNew。保留已批准兼容策略。 |
| 两个IP output常量 | 已修：读取直接资源IPv4属性；CIDR及fileserver旧完整格式不变。 |
| CT111 description ignore遗漏 | 已修：恢复operator备注保留策略。 |
| EFI创建期密钥ignore遗漏 | 已修：仅补efi_disk[0].pre_enrolled_keys，不隐藏EFI硬件。 |
| renamed known_hosts缺失 | 已修：两引用恢复原已固定108密钥的文件；不运行Deploy或启动108。 |
| runbook未执行旧文字 | 已修：附录E标题/旧句转为操作规程，链接实际执行计划。 |
| 空authorization marker意味着gate失效 | 不采纳：既有input=null标记明确要求保留，未证实它承担动态授权gate；不发明新门槛。 |
| OpenBao重复身份映射及依赖 | 已修：复用现有map并补实际VM依赖，保留public keys/值/结构。 |

相关3份Terraform fmt/隔离validate、对应Ansible syntax、静态合同及gitdiffcheck通过。父会话已阅读全文修复diff，并在实际HCP backend检查完整/定向plan：定向exit0；完整计划所有PVE资源和outputs均NoOp，仅4项原有employee inventory variables更新，未apply。VM108保持stopped/onboot0；输出精确保留192.168.1.108/24和ip=192.168.1.111/24,gw=192.168.1.1 (LXC)。远端serial104前后未变，未做state/apply或业务启停。

本轮单次Quick已完成。修复后的变更按原生Step04 patch流程读取并验证，没有追加模型评审。3个medium patch与3个low patch均有对应实际/静态验证，无可指明仍需额外模型审核的未验证风险，followup_review_recommended=false。Git提交未授权，未自动提交；Jenkins继续冻结，待代码交付进入其流水线源后再按授权解除。


## 最新main集成复验

PR分支已集成61d9c5c（含已合并#176），四处必要冲突已核实处理。无凭据源码校验的Terraform、Ansible lint/YAML、36份playbook syntax、CI及评审政策契约、文档offline检查通过；完整固定版本/Hugo交由PR原生CI。已授权维护上下文完整计划所有PVE资源NoOp，迁移目标NoOp；只有原4项employee inventory更新及上游PnetLab output后缀更新、image→image[0] NoOp move，均未apply。state仍104。源代码变化除原已审实现外仅为与main接口合并及3个迁移后拓扑注释更正，父逐项读diff核验，无新增设计/第二轮模型评审。
