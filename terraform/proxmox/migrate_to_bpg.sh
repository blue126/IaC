#!/bin/bash
set -e

# Migration Script: telmate/proxmox -> bpg/proxmox

echo "Starting migration..."

# Function to migrate VM
migrate_vm() {
    module=$1
    vmid=$2
    node="pve0"
    
    echo "Migrating VM: $module (ID: $vmid)..."
    terraform state rm "module.$module.proxmox_vm_qemu.vm" || true
    terraform import "module.$module.proxmox_virtual_environment_vm.vm" "$node/qemu/$vmid"
}

# Function to migrate LXC
migrate_lxc() {
    module=$1
    vmid=$2
    node="pve0"
    
    echo "Migrating LXC: $module (ID: $vmid)..."
    terraform state rm "module.$module.proxmox_lxc.lxc" || true
    terraform import "module.$module.proxmox_virtual_environment_container.lxc" "$node/lxc/$vmid"
}

# Migrate VMs
migrate_vm "immich" 101
migrate_vm "rustdesk" 102
migrate_vm "netbox" 104 # Note: module is 'netbox' or 'netbox_vm'? Checking state again...

# Migrate LXCs
migrate_lxc "anki" 100
migrate_lxc "homepage" 103
migrate_lxc "caddy" 105
migrate_lxc "n8n" 106
migrate_lxc "jenkins" 107

# NOTE: module.netbox_vm (provisioning.tf, for_each) is currently empty
# (netbox_provisioned_vms = []).  If populated in the future, each instance
# must be migrated manually:
#   terraform state rm 'module.netbox_vm["<name>"].proxmox_vm_qemu.vm'
#   terraform import 'module.netbox_vm["<name>"].proxmox_virtual_environment_vm.vm' pve0/qemu/<vmid>

echo "Migration commands executed. Please run 'terraform plan' to verify."
