# Helper Scripts

Utility scripts for automation and maintenance tasks.

## Purpose

This directory contains shell scripts, Python scripts, or other utilities that support the IaC workflow but are not part of Ansible or Terraform configurations.

## Directory Structure

```
scripts/
├── jenkins/               # Jenkins webhook and pipeline testing scripts
│   ├── test-webhook-payload.sh       # Simulate NetBox webhook POST to Jenkins
│   └── test-netbox-webhook.sh        # Python webhook listener for debugging
├── netbox/                # NetBox API integration scripts
│   ├── create-netbox-custom-fields.py # Create Custom Fields via API (Story 1.1)
│   └── fetch-planned-vms.py           # Fetch planned VMs from NetBox
├── pbs/                   # Proxmox Backup Server utilities
│   └── discover-pci-devices.sh        # PCI device discovery for GPU passthrough
├── get-secrets.sh         # Extract Ansible Vault secrets to Terraform *.auto.tfvars
├── refresh-terraform-state.sh # Pull remote Terraform state for Ansible inventory
├── setup-env.sh           # Initialize Python venv and Ansible Galaxy collections
└── sync-to-notion.py      # Sync documentation to Notion (optional)
```

## Core Scripts

### Environment Setup
- **`setup-env.sh`**: Creates Python venv, installs pip dependencies, and Ansible Galaxy collections. Runs automatically in devcontainer post-create hook.

### Secrets Management
- **`get-secrets.sh`**: Extracts `vault_*` variables from Ansible Vault and writes them to Terraform `*.auto.tfvars` files. Ansible Vault is the single source of truth for all secrets.

### Terraform State
- **`refresh-terraform-state.sh`**: Pulls remote Terraform state from HCP Terraform Cloud for use in Ansible dynamic inventory.

### Cross-Service Integration
- **`sync-to-notion.py`**: Syncs Terraform state to Notion database for resource documentation. This script bridges multiple services (reads Terraform state, called by Jenkins Pipeline, writes to Notion API) and therefore lives at root level rather than in a single subdirectory.

## Subdirectories

### jenkins/
Scripts for testing and debugging Jenkins webhook integration (Epic 1: NetBox 数据建模与 Webhook 基础设施).

### netbox/
NetBox API client scripts for Custom Fields management, VM configuration fetching, and automation testing.

### pbs/
Proxmox Backup Server utilities for hardware discovery and configuration.
