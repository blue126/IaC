# Proxmox storage capacity management

Terraform records guest disk capacity and protects existing guests from unintended replacement. Ansible manages host storage properties that the active Terraform provider does not expose, such as a ZFS volume reservation.

The storage role checks the configured guest, disk, and dataset identities before changing a property. It skips work when the target already meets policy and fails when the observed identities do not match inventory.

## Change procedure

1. Confirm the target host, guest, disk, and dataset from approved inventory and the current host configuration.
2. Run the playbook syntax check and a check-mode preview. Confirm the preview contains only the intended storage-property change.
3. Obtain deployment authorization before running the playbook without check mode.
4. Run the verify tag and confirm the target property has the expected value.

For Terraform-managed guest disks, review the provider behavior before changing capacity. If a provider version forces replacement for a size change, expand the existing disk using the platform procedure first, update the declared capacity, and inspect the plan. Do not apply a plan that replaces or destroys the guest.

## Importing an existing guest

Use the configured Terraform root and workspace. Save a targeted import plan with private file permissions, inspect it, and confirm that it contains only the intended import with no create, update, replace, or delete actions. Apply only the reviewed saved plan when authorized.

After import, verify the state identity and disk capacity, then review a read-only full workspace plan for unrelated drift. Keep unrelated changes out of the storage operation until they have been reviewed separately.

## Capacity terms

`refquota` limits data stored in a filesystem. `refreservation` reserves pool space for a volume. Removing a reservation makes that space available to other guests, while actual writes still depend on available pool capacity. Check pool health and available space before planning further growth.

## Offline checks

```bash
python3 ansible/tests/proxmox-storage-check.py
python3 terraform/proxmox/tests/ct120-storage-check.py --provider /path/to/existing/terraform-provider-proxmox_v0.70.0
```

The checks use fake commands, synthetic state, and a local GET-only API fixture. They do not read production state or connect to infrastructure.
