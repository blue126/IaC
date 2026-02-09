# Scripts Directory Reorganization

**Date**: 2026-02-09  
**Reason**: Improve maintainability and organization for growing script collection

## Changes

### New Directory Structure

```
scripts/
├── jenkins/               # Jenkins webhook and pipeline testing (NEW)
│   ├── test-webhook-payload.sh
│   └── test-netbox-webhook.sh
├── netbox/                # NetBox API integration scripts (NEW)
│   ├── create-netbox-custom-fields.py
│   └── fetch-planned-vms.py
├── pbs/                   # Proxmox Backup Server utilities (EXISTING)
│   └── discover-pci-devices.sh
├── get-secrets.sh         # Secrets management (Ansible Vault → Terraform)
├── refresh-terraform-state.sh # Terraform state sync
├── setup-env.sh           # Environment initialization
└── sync-to-notion.py      # Cross-service integration (Terraform → Jenkins → Notion)
```

### Root-Level Scripts Rationale

Scripts remain at root level when they:
- Bridge multiple services (e.g., `sync-to-notion.py` integrates Terraform, Jenkins, and Notion)
- Serve core infrastructure functions (e.g., `get-secrets.sh` for secrets management)
- Are invoked from multiple contexts (e.g., `setup-env.sh` from devcontainer and manual setup)

### Moved Files

| Old Path | New Path | Purpose |
|----------|----------|---------|
| `scripts/test-webhook-payload.sh` | `scripts/jenkins/test-webhook-payload.sh` | Simulate NetBox webhook POST |
| `scripts/test-netbox-webhook.sh` | `scripts/jenkins/test-netbox-webhook.sh` | Python webhook listener |
| `scripts/create-netbox-custom-fields.py` | `scripts/netbox/create-netbox-custom-fields.py` | Create Custom Fields via API |
| `scripts/fetch-planned-vms.py` | `scripts/netbox/fetch-planned-vms.py` | Fetch planned VMs from NetBox |

### Updated Documentation

- ✅ `scripts/README.md` - Added directory structure and descriptions
- ✅ `docs/jenkins-webhook-router-setup.md` - Updated script paths
- ✅ `_bmad-output/implementation-artifacts/1-2-*.md` - Updated references

## Usage Examples

### Jenkins Scripts

```bash
# Test webhook trigger
bash scripts/jenkins/test-webhook-payload.sh

# Start webhook listener (debugging)
python3 scripts/jenkins/test-netbox-webhook.sh
```

### NetBox Scripts

```bash
# Create Custom Fields
python3 scripts/netbox/create-netbox-custom-fields.py

# Fetch planned VMs
python3 scripts/netbox/fetch-planned-vms.py
```

## Migration Notes

No backward compatibility symlinks created - all references in documentation have been updated to new paths.

## Future Organization

Consider additional subdirectories as script collection grows:
- `terraform/` - Terraform state and resource management utilities
- `ansible/` - Ansible inventory generation and testing scripts  
- `monitoring/` - Health check and alerting scripts
