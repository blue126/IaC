#!/usr/bin/env python3
import pynetbox
import json
import os
import sys
import subprocess

# Configuration
NETBOX_URL = "http://192.168.1.104:8080"
NETBOX_TOKEN = "0123456789abcdef0123456789abcdef01234567" # In production, use env var

# Determine absolute path to the output file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "../terraform/proxmox/provisioning.auto.tfvars.json")

def get_template_info(node_ip, template_name):
    """
    Connects to Proxmox node via SSH to find template VMID and Cloud-Init slot.
    Returns a dict with 'vmid' and 'cloudinit_slot'.
    """
    try:
        # 1. Find VMID
        cmd_list = f"ssh -o StrictHostKeyChecking=no root@{node_ip} 'qm list'"
        result_list = subprocess.check_output(cmd_list, shell=True).decode('utf-8')
        
        vmid = None
        for line in result_list.splitlines():
            if template_name in line:
                parts = line.split()
                if len(parts) > 0 and parts[0].isdigit():
                    vmid = parts[0]
                    break
        
        if not vmid:
            print(f"Warning: Template '{template_name}' not found on {node_ip}")
            return {"cloudinit_slot": "scsi1"} # Default fallback
            return {"cloudinit_slot": "scsi1", "disk_size": 0} # Default fallback

        # 2. Get Config
        cmd_config = f"ssh -o StrictHostKeyChecking=no root@{node_ip} 'qm config {vmid}'"
        result_config = subprocess.check_output(cmd_config, shell=True).decode('utf-8')
        
        cloudinit_slot = "scsi1" # Default
        template_disk_size = 0
        
        for line in result_config.splitlines():
            if "media=cdrom" in line:
                # Example: ide2: vmdata:vm-9000-cloudinit,media=cdrom
                key = line.split(':')[0].strip()
                cloudinit_slot = key
            if line.strip().startswith("scsi0:"):
                # Example: scsi0: vmdata:base-9000-disk-1,size=20G
                parts = line.split(",")
                for part in parts:
                    if "size=" in part:
                        size_str = part.split("=")[1].strip()
                        if size_str.endswith("G"):
                            template_disk_size = int(float(size_str[:-1]))
                        elif size_str.endswith("M"):
                            template_disk_size = int(float(size_str[:-1])) / 1024
                
        return {"cloudinit_slot": cloudinit_slot, "disk_size": template_disk_size}

    except subprocess.CalledProcessError as e:
        print(f"Error querying Proxmox: {e}")
        return {"cloudinit_slot": "scsi1", "disk_size": 0} # Default fallback

def get_tag_value(tags, prefix):
    """Extract value from tags like 'node:pve0'"""
    for tag in tags:
        if tag.name.startswith(prefix):
            return tag.name.split(':', 1)[1]
    return None

def main():
    nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
    
    # Fetch VMs with status 'staged' (Planning to be provisioned)
    vms = nb.virtualization.virtual_machines.filter(status='staged')
    
    provision_list = []
    
    print(f"Connecting to Netbox at {NETBOX_URL}...")
    
    # Template Mapping: Netbox Platform Slug -> Proxmox Template Name
    # This mapping is now largely superseded by custom fields, but kept for reference
    TEMPLATE_MAP = {
        "ubuntu": "ubuntu-24.04-template",
        "alpine": "alpine-3.18-cloudinit",
        "debian": "debian-12-cloudinit"
    }

    for vm in vms:
        print(f"Processing VM: {vm.name}")
        
        # Get target node (custom field or default)
        # Original: if not vm.device: ... target_node = vm.device.name
        # New: Use custom field 'proxmox_node' or default to 'pve0'
        target_node = vm.custom_fields.get("proxmox_node", "pve0")

        # Get template (custom field or default)
        # Original: if not vm.platform: ... template_name = TEMPLATE_MAP.get(vm.platform.slug, vm.platform.slug)
        # New: Use custom field 'proxmox_template' or default to 'ubuntu-24.04-template'
        template_name = vm.custom_fields.get("proxmox_template", "ubuntu-24.04-template")
        
        # Get IP from primary_ip
        # Original: cidr = str(vm.primary_ip4) if vm.primary_ip4 else None
        # New: Use vm.primary_ip.address
        cidr = None
        if vm.primary_ip:
            cidr = vm.primary_ip.address
            
        # Get disk size from local_context_data or default
        # Original: disk_size_gb = int(vm.custom_fields.get("disk_size_gb", 8))
        # New: More complex logic for disk size
        disk_size_gb = 50 # Default
        if vm.local_context_data and "disk_size" in vm.local_context_data:
             disk_size_gb = int(vm.local_context_data["disk_size"].replace("G", ""))
        elif vm.disk: # If disk is set in Netbox resources (MB)
             disk_size_gb = int(vm.disk / 1024)

        # Fetch dynamic template info
        # We need the node IP to SSH. Assuming pve0 is 192.168.1.50 for now, 
        # or we could lookup from Netbox if we had devices.
        # For simplicity, using the known IP of pve0.
        node_ip = "192.168.1.50" 
        
        template_info = get_template_info(node_ip, template_name)
        cloudinit_slot = template_info["cloudinit_slot"]
        template_disk_size = template_info["disk_size"]
        
        # Ensure disk size is at least template size
        final_disk_size = max(disk_size_gb, template_disk_size)

        # Determine VMID from IP (Last Octet)
        vmid = 0
        if cidr:
            try:
                ip_str = cidr.split('/')[0]
                vmid = int(ip_str.split('.')[-1])
            except (ValueError, IndexError):
                vmid = 0

        vm_data = {
            "name": vm.name,
            "target_node": target_node,
            "template": template_name,
            "cores": int(vm.custom_fields.get("cpu_count", 2)),
            "memory": int(vm.custom_fields.get("memory_gb", 2)) * 1024, # Convert GB to MB
            "disk_size": f"{final_disk_size}G",
            "ip_address": cidr, # Passing CIDR for cloud-init
            "vmid": vmid, # Derived from IP
            "cloudinit_slot": cloudinit_slot # Dynamically set
        }
        
        provision_list.append(vm_data)
        print(f"  Added to provisioning list:\n{json.dumps(vm_data, indent=4)}")

    # Output to Terraform variables file
    output_data = {
        "netbox_provisioned_vms": provision_list
    }
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output_data, f, indent=2)
        
    print(f"\nSuccessfully wrote {len(provision_list)} VMs to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
