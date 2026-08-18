# Terraform Infrastructure

This directory contains the Infrastructure as Code (IaC) definitions for the homelab environment.

## Directory Structure

*   **`proxmox/`**:  
    Contains the main configuration for Proxmox resources (VMs, LXC containers).  
    **This is the primary working directory.** All `terraform` commands (init, plan, apply) should be executed here.

*   **`modules/`**:  
    Reusable Terraform modules (e.g., `proxmox-vm`, `proxmox-lxc`). These are consumed by the configurations in `proxmox/`.

*   **`esxi/`**:  
    Legacy or separate configuration for ESXi hosts.

*   **`oci/`**:  
    Configuration for Oracle Cloud Infrastructure.

## Known Gaps

*   **`proxmox-backup-server` on `pve1` is not managed by Terraform.**
    It was migrated off the ESXi host manually, and no `.tf` definition or
    state entry exists for it under `proxmox/`. Import it into the
    `iac-proxmox` workspace next time `pve1` is up, so the backup server does
    not stay outside IaC. The retired ESXi copy is still defined in
    `esxi/pbs.tf`; remove that file and apply once the migration is confirmed.

## How to Run

To apply changes to Proxmox resources:

1.  Navigate to the provider directory:
    ```bash
    cd proxmox
    ```
2.  Initialize Terraform (if not already done):
    ```bash
    terraform init
    ```
3.  Review pending changes:
    ```bash
    terraform plan
    ```
4.  Apply changes:
    ```bash
    terraform apply
    ```
