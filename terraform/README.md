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
