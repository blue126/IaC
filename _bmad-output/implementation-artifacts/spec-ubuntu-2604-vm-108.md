---
title: 'Ubuntu 26.04 VM108：直接镜像部署与旧实例退役'
type: 'feature'
created: '2026-09-11'
status: 'done'
review_loop_iteration: 0
baseline_commit: '3237b58bcabf747e229c08b718213b4c62394dc9'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** VM108 is a Veeam worker and VM110 is manually created PNET4.2.4; the user explicitly confirmed retiring both. Existing template/snippet provisioning adds unnecessary dependencies.

**Approach:** Retire the verified old instances, then create `ubuntu-2604` on pve0 as VM108: 4 cores, 32768 MiB RAM, 100 GiB root disk on vmdata, vmbr1, 192.168.1.108/24, gateway/DNS 192.168.1.1. Terraform imports a pinned Ubuntu 26.04 amd64 cloud image directly. Native Cloud-Init provides initial access; Ansible installs QGA and authorized keys. Per the user's latest instruction, bootstrap with a Vault password, verify key-only access, then disable SSH password authentication.

## Boundaries & Constraints

**Always:** Work in the existing dedicated worktree. Keep bpg/proxmox 0.70.0 and current HCP state ownership. Use the approved task Sandbox and subnet rule. Keep credentials out of logs, argv and tracked files; mark password inputs sensitive and Ansible secret tasks no_log. Verify identities, disks, locks, HA/replication and IP availability before deletion. Existing backups remain untouched. Separate old108 destruction from new108 creation. Report actual, not intended, deployment status.

**Ask First:** Exact destructive execution checkpoint after displaying audited volumes; failed graceful shutdown; unexpected identities/disks/state changes; changes outside this spec; live backup job modification. No additional token ACL changes are authorized.

**Never:** Full apply, VM109 replacement, Homepage changes, pve1 repairs, forced shutdown, purge/unreferenced-disk deletion, second-state adoption, state-rm shortcuts, deletion of backups, plaintext secrets, commits/push without separate approval.

## I/O & Edge-Case Matrix

| Scenario | State | Expected behavior | Error handling |
|---|---|---|---|
| Retirement | Verified stopped old108; provider deletion timeout | User-approved precise qm deletion, then HCP refresh-only saved plan removes only the absent old record | Reject extra actions |
| Manual110 | PNET4.2.4, approved disks | Graceful shutdown then precise qm destroy | Stop on mismatch/timeout |
| First boot | QGA absent, static IP | Terraform finishes; Ansible bootstraps over SSH | Do not require QGA address discovery |
| Hardening | Password login available | Install keys, prove key login, then disable password/keyboard-interactive SSH | Do not lock out access |
| Unrelated drift | pve1 unreachable / VM109 replacement | Leave unrelated objects unchanged; disclose full-plan limitation | Never apply the full plan |

</frozen-after-approval>

## Code Map

The following investigation map describes the pre-implementation snapshot. **Current ownership: old108/110 and old108's HCP record are gone; new108 belongs only to module.ubuntu_2604. All old retirement plans are stale and must never be reused.**

- `terraform/modules/proxmox-cloud-image-vm/{main,variables,outputs}.tf`: unfinished direct-image module; native initialization, file_id import, no snippets.
- `terraform/proxmox/{ubuntu-2604,variables,provider}.tf`: VM108, sensitive bootstrap input and dedicated SSH-password provider alias; preserve other providers.
- `terraform/proxmox/veeam-worker.tf`: deleted adoption stub; HCP still owns old108. Targeted destroy preview: exactly one deletion.
- `terraform/proxmox/jenkins-agent.tf`: removed unused CT110 declaration; user confirms never deployed. Do not remove shared Jenkins roles/pipelines.
- `ansible/roles/common/tasks/main.yml`: revert this task's broad QGA change; reuse common baseline unchanged.
- `ansible/inventory/group_vars/pve_vms.yml`: Vault-backed initial SSH/become passwords already exist.
- `ansible/playbooks/deploy-ubuntu-2604.yml`, `ansible/roles/ubuntu-vm/`: new host-scoped Deploy/Verify implementation, including guarded key verification before hardening.
- `docs/designs/homelab-iac-architecture.md`, `docs/specs/backup-architecture-consolidation-spec.md`: correct premature completion claims; preserve historical baselines.
- Existing retirement spec `spec-retire-claude-agent-and-desktop.md`: reuse single-state saved-plan retirement and manual non-Terraform VM deletion pattern, not its backup-deletion scope.

## Tasks & Acceptance

**Execution:**
- [x] Direct-image module: explicit scsi0 boot, compatible SCSI/I/O settings, bounded QGA discovery timeout; sensitive native bootstrap password, no user-data snippet. Preserve 4 CPU/32 GiB.
- [x] Provider/bootstrap: dedicated PVE SSH password alias for image import; feed guest bootstrap password from Vault via runtime input, not the all-environment secrets script.
- [x] Ansible: await SSH/cloud-init, run common, install QGA, deploy keys, validate key authentication from the existing trusted PVE key path, disable SSH password and keyboard-interactive auth, verify effective settings/QGA. Scope only ubuntu-2604.
- [x] Repository docs: distinguish code, planned deployment and proven state; document network-policy root cause. Backup addition remains pending live authorization/reachability.
- [x] Validation: changed-path fmt, validate, syntax checks, self-review and scoped saved-plan audits. Saved plans are protected and untracked. Independent workflow review follows implementation.
- [x] Operations: audited both guests/disks; old108 stopped normally, manual110 stopped by the user after shutdown timeout. Following explicit amended authorization, both were deleted with qm; HCP refresh-only removed the absent old108 record before new108 creation. Native Terraform creation and Ansible bootstrap/key-only verification passed. Old retirement plans must never be reapplied after VMID reuse.

**Acceptance Criteria:**
- Given successful retirement, when PVE/state are queried, then old108 ownership and VM110 are absent and other guests remain unchanged.
- Given creation, when guest and PVE are inspected, then VM108 runs Ubuntu26.04 with 4 cores/32768 MiB and the specified network/storage.
- Given completed bootstrap, when fresh key-only SSH and QGA probes run, then they succeed and SSH password authentication is disabled.
- Given unrelated full-plan failures, when reporting completion, then scoped results and unresolved unrelated drift/backup reachability are distinguished.

## Spec Change Log

- 2026-09-11: User approved native qm deletion of stopped old108 after bpg deletion timed out, followed by targeted HCP refresh-only synchronization; no state rm or second ownership. Both old guests/disks verified absent before creating new108.
- 2026-09-11: Deployment passed; Ubuntu26.04, 4 cores/32768 MiB/20 GiB, static network, key-only SSH, sudo and QGA verified. Scoped Terraform plan exits 0 with No changes. Backup job remains 100–107, with no live backup changes.
- 2026-09-11: Independent review patches: bounded Cloud-Init waiting, interruption-safe SSH reload scheduling, connection-specific sshd config inspection, live authentication-method probe, hardware/rootfs/network assertions, and QGA-to-IP binding. Enhanced Verify play passed 7 tasks, changed=0, failed=0. Historical docs clarified. Long-term key provisioning is an operator prerequisite: this task intentionally did not copy personal private keys into the Sandbox.

- 2026-09-11: User explicitly amended root disk capacity to 100 GiB. Audited and applied resize-108-100g.tfplan (disk.size 20→100 only, in-place). Verified /dev/sda1 ext4 before online growpart and resize2fs; guest disk is 100 GiB, root partition 98.9 GiB, filesystem approximately 96 GiB with 94 GiB available. No reboot/replacement. Updated Verify passed 7/7, and scoped Terraform plan returned No changes.

## Design Notes

Historical planning/handoff notes below are retained as evidence, not instructions to rerun deployment. Live execution finished on 2026-09-11 under subsequent explicit authorizations.

Verified 403 source: Sandbox default-deny for .50:8006/.50:22, not bad credentials. Task subnet allow rule now works. Old108 volumes: vmdata:vm-108-disk-0 (EFI), vm-108-disk-1 (100 GiB). Manual110: vmdata:vm-110-disk-0 (100 GiB). HA/replication empty. pve0 has ~64 GiB RAM; retirement releases 14 GiB. PBS .249 and pve1 are unreachable; current backup job remains 100–107. Prior failed plans are not apply candidates.

Implementation handoff: code and offline checks only; leave live operations pending for the parent's separately authorized execution phase. No apply/import/destroy, credential printing/materialization, or remote guest changes in the implementation handoff. The existing dedicated Sandbox is `iac-claude-run-iac-20260910135814-12478-direct-v130`; its workspace path matches this worktree. Use `sbx exec -w <absolute-dir>` for scoped validation; no new Sandbox or dependencies. bpg0.70 has no wait_for_ip; source investigation confirmed QGA discovery timeout is nonfatal. Use a short fixed timeout (e.g. 5s) and static IP, virtio-scsi-pci without iothread, explicit boot_order=[scsi0]. Native password comes from vault_vm_default_password as sensitive runtime TF_VAR input. Native user_data and user_account must not be mixed. Bootstrap may use existing pve0 key to prove key-only access to ubuntu-2604 from delegated command; ensure retained keys include that trusted source before hardening. Do not copy private keys. Preserve frozen intent. Report any runtime input requirements without reading secrets. Retain pending live verification rather than falsely marking it complete.

## Verification

Run Terraform/Ansible only in the approved Sandbox. `terraform validate`, scoped `fmt -check`, playbook `--syntax-check`, `git diff --check`. Audit saved plans by action/address without printing secrets. After creation check os-release, CPU/RAM, IP/route/DNS, cloud-init, QGA, sshd effective config and fresh key login; rerun idempotent role checks. Inspect full plan but never apply unrelated actions.

Evidence: enhanced Verify passed 7/7 with changed=0; six tests of the actual Cloud-Init guard expressions passed (clean, known warning, fatal error, unexpected warning, different deprecation, unfinished initialization). Scoped VM108 plan returned No changes. Full baseline re-application from this password-only Sandbox after SSH hardening was not performed; future Deploy runs require an approved operator SSH key/agent. Verify remains usable through the existing PVE verifier.

## Suggested Review Order

**创建入口与镜像**

- 核对108资源、运行时密码输入与专属SSH provider。
  [ubuntu-2604.tf:1](../../terraform/proxmox/ubuntu-2604.tf#L1)
- 核对镜像校验、原生Cloud-Init与首次启动QGA等待。
  [main.tf:9](../../terraform/modules/proxmox-cloud-image-vm/main.tf#L9)

**初始化与安全验收**

- 先看Cloud-Init错误门禁，再看独立Verify流程。
  [deploy-ubuntu-2604.yml:1](../../ansible/playbooks/deploy-ubuntu-2604.yml#L1)
- 密钥验证成功后才禁用密码，并校验、加载SSH配置。
  [tasks/main.yml:1](../../ansible/roles/ubuntu-vm/tasks/main.yml#L1)

**状态与外围配置**

- 区分已验收VM与尚未同步的生产备份。
  [backup-architecture-consolidation-spec.md:1](../../docs/specs/backup-architecture-consolidation-spec.md#L1)
- 阻止包含敏感输入的saved plan进入Git。
  [.gitignore:1](../../.gitignore#L1)
