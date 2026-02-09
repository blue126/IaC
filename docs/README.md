# Directory Index

## Files

- **[README.md](./README.md)** - Documentation index and navigation hub.
- **[netbox-custom-fields-reference.md](./netbox-custom-fields-reference.md)** - NetBox Custom Fields definition reference (Epic 1).

## Subdirectories

### agent-setup/

- **[bmad-opencode-subagent-integration.md](./agent-setup/bmad-opencode-subagent-integration.md)** - BMAD + OpenCode two-layer agent architecture integration guide and optimization records.

### deployment/

- **[immich-deployment.md](./deployment/immich-deployment.md)** - Immich deployment guide covering Terraform, Ansible, and Docker.
- **[netbox-deployment.md](./deployment/netbox-deployment.md)** - Netbox deployment architecture, infrastructure provisioning, and application setup.
- **[pbs-esxi-deployment.md](./deployment/pbs-esxi-deployment.md)** - Proxmox Backup Server on ESXi deployment with ZFS/PCIe passthrough.
- **[pbs-iscsi-veeam-guide.md](./deployment/pbs-iscsi-veeam-guide.md)** - Hybrid backup architecture guide for PBS and Veeam using iSCSI.
- **[proxmox-vm-deployment.md](./deployment/proxmox-vm-deployment.md)** - Guide for managing Proxmox VMs using Terraform.
- **[README.md](./deployment/README.md)** - Index and overview of deployment guides.
- **[veeam-backup-deployment-guide.md](./deployment/veeam-backup-deployment-guide.md)** - Veeam Backup & Replication deployment and configuration guide.

### designs/

- **[ansible-role-architecture.md](./designs/ansible-role-architecture.md)** - Ansible Role architecture design, boundaries, and dependencies.
- **[ansible-vault-architecture.md](./designs/ansible-vault-architecture.md)** - Ansible Vault secret management design and integration principles.
- **[cicd-architecture.md](./designs/cicd-architecture.md)** - Jenkins CI/CD pipeline architecture for Terraform and Ansible.
- **[cicd-pipeline-flowchart.excalidraw](./designs/cicd-pipeline-flowchart.excalidraw)** - Excalidraw flowchart visualizing the CI/CD pipeline steps.
- **[homelab-iac-architecture.md](./designs/homelab-iac-architecture.md)** - Full system architecture document for the homelab IaC project.

### guides/

- **[ansible-patterns-and-best-practices.md](./guides/ansible-patterns-and-best-practices.md)** - Comprehensive guide on Ansible best practices and patterns.
- **[jenkins-webhook-router-setup.md](./guides/jenkins-webhook-router-setup.md)** - Jenkins Webhook-Router job manual configuration guide (Story 2.1).
- **[notion-sync-setup.md](./guides/notion-sync-setup.md)** - Setup guide for syncing Terraform state to Notion.
- **[proxmox-provider-migration-guide.md](./guides/proxmox-provider-migration-guide.md)** - Guide for migrating from telmate to bpg Proxmox Terraform provider.
- **[QUICK-REFERENCE.md](./guides/QUICK-REFERENCE.md)** - Quick reference card for Terraform and Proxmox operations.
- **[README.md](./guides/README.md)** - Index for comprehensive guides.
- **[terraform-proxmox-complete-guide.md](./guides/terraform-proxmox-complete-guide.md)** - Complete guide for Terraform automation with Proxmox.

### improvement/

- **[inventory-and-document-sync-via-cicd.md](./improvement/inventory-and-document-sync-via-cicd.md)** - Proposal for change-driven automated documentation synchronization.
- **[PLANNING.md](./improvement/PLANNING.md)** - High-level project planning, roadmap, and goals.

### improvement/implemented/

- **[cloudflare-tunnel-webhook.md](./improvement/implemented/cloudflare-tunnel-webhook.md)** - Implementation details for Cloudflare Tunnel GitHub Webhook trigger.
- **[proxmox-provider-migration.md](./improvement/implemented/proxmox-provider-migration.md)** - Plan and record of the Proxmox Terraform provider migration.

### learningnotes/

- **[2025-11-28-terraform-modules-netbox-debugging.md](./learningnotes/2025-11-28-terraform-modules-netbox-debugging.md)** - Notes on Terraform modules and Netbox debugging.
- **[2025-11-28-terraform-proxmox.md](./learningnotes/2025-11-28-terraform-proxmox.md)** - Initial learning notes on Terraform Proxmox deployment.
- **[2025-11-29-ansible-netbox-docker.md](./learningnotes/2025-11-29-ansible-netbox-docker.md)** - Notes on Ansible deployment for Netbox and Docker.
- **[2025-11-29-netbox-deployment-version-troubleshooting.md](./learningnotes/2025-11-29-netbox-deployment-version-troubleshooting.md)** - Troubleshooting Netbox deployment version compatibility.
- **[2025-11-30-anki-sync-server-deployment.md](./learningnotes/2025-11-30-anki-sync-server-deployment.md)** - Notes on deploying Anki Sync Server.
- **[2025-11-30-ansible-deployment-verification.md](./learningnotes/2025-11-30-ansible-deployment-verification.md)** - Patterns for verifying Ansible deployments.
- **[2025-11-30-lxc-vm-network-bridge.md](./learningnotes/2025-11-30-lxc-vm-network-bridge.md)** - Notes on LXC and VM network bridging topology.
- **[2025-11-30-terraform-proxmox-provider-crash.md](./learningnotes/2025-11-30-terraform-proxmox-provider-crash.md)** - Analysis of Terraform Proxmox provider crashes.
- **[2025-11-30-terraform-refactoring-best-practices.md](./learningnotes/2025-11-30-terraform-refactoring-best-practices.md)** - Best practices for refactoring Terraform code.
- **[2025-12-01-homepage-lxc-deployment.md](./learningnotes/2025-12-01-homepage-lxc-deployment.md)** - Notes on deploying Homepage on LXC.
- **[2025-12-01-homepage-proxmox-integration.md](./learningnotes/2025-12-01-homepage-proxmox-integration.md)** - Guide for integrating Homepage with Proxmox.
- **[2025-12-02-ansible-inventory-refactoring.md](./learningnotes/2025-12-02-ansible-inventory-refactoring.md)** - Notes on refactoring Ansible inventory structure.
- **[2025-12-02-ansible-vault-secret-management.md](./learningnotes/2025-12-02-ansible-vault-secret-management.md)** - Guide to managing secrets with Ansible Vault.
- **[2025-12-02-proxmox-terraform-ansible-immich.md](./learningnotes/2025-12-02-proxmox-terraform-ansible-immich.md)** - Integration notes for Proxmox, Terraform, Ansible, and Immich.
- **[2025-12-02-tailscale-integration-refactoring.md](./learningnotes/2025-12-02-tailscale-integration-refactoring.md)** - Deep integration of Tailscale in LXC and hybrid cloud.
- **[2025-12-03-ansible-abstraction-levels.md](./learningnotes/2025-12-03-ansible-abstraction-levels.md)** - Discussion on Ansible abstraction levels (Role vs Task).
- **[2025-12-03-caddy-webdav-tailscale-troubleshooting.md](./learningnotes/2025-12-03-caddy-webdav-tailscale-troubleshooting.md)** - Troubleshooting Caddy WebDAV and Tailscale ACLs.
- **[2025-12-04-ansible-tags-and-variables.md](./learningnotes/2025-12-04-ansible-tags-and-variables.md)** - Notes on Ansible tags and variable scoping.
- **[2025-12-04-hybrid-iac-netbox-workflow.md](./learningnotes/2025-12-04-hybrid-iac-netbox-workflow.md)** - Workflow for hybrid IaC management with Netbox.
- **[2025-12-04-netbox-population-terraform-vs-ansible.md](./learningnotes/2025-12-04-netbox-population-terraform-vs-ansible.md)** - Comparison of Netbox population methods.
- **[2025-12-04-tailscale-magicdns-and-split-dns.md](./learningnotes/2025-12-04-tailscale-magicdns-and-split-dns.md)** - Explanation of Tailscale MagicDNS and Split DNS.
- **[2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md](./learningnotes/2025-12-04-terraform-proxmox-disk-and-cloudinit-troubleshooting.md)** - Troubleshooting Terraform Proxmox disk and Cloud-Init issues.
- **[2025-12-04-zfs-pool-migration-and-expansion.md](./learningnotes/2025-12-04-zfs-pool-migration-and-expansion.md)** - Notes on ZFS pool migration and expansion.
- **[2025-12-11-elk-vs-lpg-comparison.md](./learningnotes/2025-12-11-elk-vs-lpg-comparison.md)** - Comparison between ELK and LPG logging stacks.
- **[2025-12-15-deploying-n8n-on-lxc.md](./learningnotes/2025-12-15-deploying-n8n-on-lxc.md)** - Guide for deploying n8n on LXC.
- **[2025-12-21-esxi-integration-and-venv.md](./learningnotes/2025-12-21-esxi-integration-and-venv.md)** - Notes on ESXi integration and Ansible venv.
- **[2026-01-28-rustdesk-terraform.md](./learningnotes/2026-01-28-rustdesk-terraform.md)** - Terraform management for Rustdesk deployment.
- **[2026-01-28-ssh-key-management-strategy.md](./learningnotes/2026-01-28-ssh-key-management-strategy.md)** - Mixed SSH key management strategy with Terraform and Ansible.
- **[2026-01-29-ansible-troubleshooting.md](./learningnotes/2026-01-29-ansible-troubleshooting.md)** - Log of Ansible troubleshooting experiences.
- **[2026-01-29-inventory-migration-trap.md](./learningnotes/2026-01-29-inventory-migration-trap.md)** - Analysis of data loss risks during inventory migration.
- **[2026-01-29-rustdesk-deployment-lessons.md](./learningnotes/2026-01-29-rustdesk-deployment-lessons.md)** - Lessons learned from Rustdesk deployment.
- **[2026-01-31-ansible-role-refactoring.md](./learningnotes/2026-01-31-ansible-role-refactoring.md)** - Notes on Ansible role architecture refactoring.
- **[2026-01-31-ansible-vault-architecture-refactoring.md](./learningnotes/2026-01-31-ansible-vault-architecture-refactoring.md)** - Notes on Ansible Vault architecture standardization.
- **[2026-01-31-pbs-proxmox-backup-integration.md](./learningnotes/2026-01-31-pbs-proxmox-backup-integration.md)** - Integration notes for Proxmox Backup Server.
- **[2026-02-03-esxi-vm-infrastructure-improvements.md](./learningnotes/2026-02-03-esxi-vm-infrastructure-improvements.md)** - Improvements to ESXi VM infrastructure.
- **[2026-02-03-jenkins-cicd-phase1-infrastructure.md](./learningnotes/2026-02-03-jenkins-cicd-phase1-infrastructure.md)** - Phase 1 of Jenkins CI/CD infrastructure setup.
- **[2026-02-03-jenkins-cicd-phase2-configuration.md](./learningnotes/2026-02-03-jenkins-cicd-phase2-configuration.md)** - Phase 2 of Jenkins CI/CD configuration.
- **[2026-02-03-jenkins-cicd-phase3-pipeline.md](./learningnotes/2026-02-03-jenkins-cicd-phase3-pipeline.md)** - Phase 3 of Jenkins CI/CD pipeline implementation.
- **[2026-02-04-ansible-cloudflared-review.md](./learningnotes/2026-02-04-ansible-cloudflared-review.md)** - Code review and learning notes for Cloudflared Ansible role.
- **[INDEX.md](./learningnotes/INDEX.md)** - Index file for learning notes.

### learningnotes/refactoring/

- **[2026-02-09-epic1-netbox-webhook-jenkins-learning.md](./learningnotes/refactoring/2026-02-09-epic1-netbox-webhook-jenkins-learning.md)** - Epic 1 learning review: NetBox, Jenkins, webhooks, and API concepts.

### specs/

- **[pbs-iscsi-veeam-spec.md](./specs/pbs-iscsi-veeam-spec.md)** - Implementation specifications for PBS iSCSI Target for Veeam.

### troubleshooting/

- **[ansible-issues.md](./troubleshooting/ansible-issues.md)** - Troubleshooting guide for common Ansible issues.
- **[deployment-issues.md](./troubleshooting/deployment-issues.md)** - Troubleshooting guide for general deployment issues (Docker, etc.).
- **[network-connectivity.md](./troubleshooting/network-connectivity.md)** - Troubleshooting guide for network connectivity, VPN, and proxy issues.
- **[README.md](./troubleshooting/README.md)** - Index and overview of troubleshooting guides.
- **[slow-smb-over-wifi.md](./troubleshooting/slow-smb-over-wifi.md)** - Specific troubleshooting log for slow SMB transfer speeds.
- **[STRUCTURE.md](./troubleshooting/STRUCTURE.md)** - Structure definition for the troubleshooting documentation.
- **[terraform-issues.md](./troubleshooting/terraform-issues.md)** - Troubleshooting guide for Terraform and Proxmox issues.
