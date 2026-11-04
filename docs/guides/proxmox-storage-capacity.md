# Proxmox storage capacity management

Terraform records guest disk capacity and protects existing guests from unintended replacement. Ansible manages host storage properties that the active Terraform provider does not expose, such as a ZFS volume reservation.

No role manages a guest disk property at present: the only target was VM 250's former disk, and that role was removed on 2026-11-04 after VM 250 became a template outside Terraform. If one is added, it should check the guest, disk and dataset identities before changing a property, skip work when the target already meets policy, and support a check-mode preview and a verify tag.

For Terraform-managed guest disks, review the provider behavior before changing capacity. If a provider version forces replacement for a size change, expand the existing disk using the platform procedure first, update the declared capacity, and inspect the plan. Do not apply a plan that replaces or destroys the guest.

## Importing an existing guest

Use the configured Terraform root and workspace. Save a targeted import plan with private file permissions, inspect it, and confirm that it contains only the intended import with no create, update, replace, or delete actions. Apply only the reviewed saved plan when authorized.

After import, verify the state identity and disk capacity, then review a read-only full workspace plan for unrelated drift. Keep unrelated changes out of the storage operation until they have been reviewed separately.

## Capacity terms

`refquota` limits data stored in a filesystem. `refreservation` reserves pool space for a volume. Removing a reservation makes that space available to other guests, while actual writes still depend on available pool capacity. Check pool health and available space before planning further growth.

## Offline checks

```bash
python3 terraform/proxmox/tests/ct120-storage-check.py --provider /path/to/existing/terraform-provider-proxmox_v0.70.0
```

The checks use fake commands, synthetic state, and a local GET-only API fixture. They do not read production state or connect to infrastructure.
