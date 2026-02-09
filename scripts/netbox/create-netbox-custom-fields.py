#!/usr/bin/env python3
"""
Automatically create NetBox Custom Fields via API.
Story 1.1: Define core Custom Fields for IaC automation.

Requires NETBOX_API_TOKEN environment variable.
Optional: NETBOX_URL environment variable (defaults to http://192.168.1.104:8080).
"""

import os
import requests
import sys

NETBOX_URL = os.environ.get("NETBOX_URL", "http://192.168.1.104:8080")
NETBOX_TOKEN = os.environ.get("NETBOX_API_TOKEN")

if not NETBOX_TOKEN:
    print("ERROR: NETBOX_API_TOKEN environment variable is not set.")
    print("Export it first: export NETBOX_API_TOKEN='your-token-here'")
    sys.exit(1)

headers = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json"
}

# 6 core Custom Fields defined in Story 1.1
custom_fields = [
    {
        "name": "infrastructure_platform",
        "label": "Infrastructure Platform",
        "type": "select",
        "object_types": ["virtualization.virtualmachine", "dcim.device"],
        "required": True,
        "weight": 100,
        "group_name": "Automation",
        "description": "Target infrastructure platform for routing decisions",
        "choices": ["proxmox", "esxi", "physical"],
        "default": "proxmox"
    },
    {
        "name": "automation_level",
        "label": "Automation Level",
        "type": "select",
        "object_types": ["virtualization.virtualmachine", "dcim.device"],
        "required": True,
        "weight": 110,
        "group_name": "Automation",
        "description": "Controls automation approval behavior",
        "choices": ["fully_automated", "requires_approval", "manual_only"],
        "default": "requires_approval"
    },
    {
        "name": "proxmox_node",
        "label": "Proxmox Node",
        "type": "select",
        "object_types": ["virtualization.virtualmachine"],
        "required": False,
        "weight": 200,
        "group_name": "Proxmox Configuration",
        "description": "Target node in Proxmox VE cluster",
        "choices": ["pve0", "pve1", "pve2"]
    },
    {
        "name": "proxmox_vmid",
        "label": "Proxmox VMID",
        "type": "integer",
        "object_types": ["virtualization.virtualmachine"],
        "required": False,
        "weight": 210,
        "group_name": "Proxmox Configuration",
        "description": "Proxmox resource unique identifier (100-999)",
        "validation_minimum": 100,
        "validation_maximum": 999
    },
    {
        "name": "ansible_groups",
        "label": "Ansible Groups",
        "type": "multiselect",
        "object_types": ["virtualization.virtualmachine", "dcim.device"],
        "required": False,
        "weight": 300,
        "group_name": "Ansible Configuration",
        "description": "Ansible inventory groups for this resource",
        "choices": ["pve_vms", "pve_lxc", "docker", "tailscale", "backup_client", "monitoring_target"]
    },
    {
        "name": "playbook_name",
        "label": "Ansible Playbook Name",
        "type": "text",
        "object_types": ["virtualization.virtualmachine", "dcim.device"],
        "required": False,
        "weight": 310,
        "group_name": "Ansible Configuration",
        "description": "Associated Ansible playbook filename (without .yml suffix)"
    }
]

def create_choice_set(name, choices):
    """Create a CustomFieldChoiceSet for select/multiselect fields (NetBox 4.x)."""
    url = f"{NETBOX_URL}/api/extras/custom-field-choice-sets/"

    # Check if choice set already exists
    try:
        response = requests.get(f"{url}?name={name}", headers=headers, timeout=10)
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                return results[0]["id"]
    except requests.RequestException as exc:
        print(f"  WARNING: Failed to check existing choice set: {exc}")

    # Create new choice set — NetBox 4.x expects list of [value, label] pairs
    extra_choices = [[c, c] for c in choices]
    payload = {
        "name": name,
        "extra_choices": extra_choices,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            choice_set_id = response.json()["id"]
            print(f"  Created choice set '{name}' (ID: {choice_set_id})")
            return choice_set_id
        else:
            print(f"  WARNING: Failed to create choice set '{name}': "
                  f"{response.status_code} {response.text}")
            return None
    except requests.RequestException as exc:
        print(f"  WARNING: Network error creating choice set: {exc}")
        return None


def create_custom_field(field_config):
    """Create a single Custom Field in NetBox via API."""
    name = field_config["name"]

    # Check if field already exists
    check_url = f"{NETBOX_URL}/api/extras/custom-fields/?name={name}"
    try:
        response = requests.get(check_url, headers=headers, timeout=10)
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                print(f"  Field '{name}' already exists, skipping")
                return True
    except requests.RequestException as exc:
        print(f"  WARNING: Failed to check existing field: {exc}")

    # For select/multiselect types, create a choice set first (NetBox 4.x requirement)
    payload = dict(field_config)
    if payload["type"] in ["select", "multiselect"] and "choices" in payload:
        choices = payload.pop("choices")
        choice_set_name = f"{name}_choices"
        choice_set_id = create_choice_set(choice_set_name, choices)
        if choice_set_id:
            payload["choice_set"] = choice_set_id
        else:
            print(f"  WARNING: Could not create choice set for '{name}', "
                  "field creation may fail")

    # Create the custom field
    url = f"{NETBOX_URL}/api/extras/custom-fields/"
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"  OK: Created field '{name}'")
            return True
        else:
            print(f"  FAIL: Creating field '{name}':")
            print(f"    Status: {response.status_code}")
            print(f"    Response: {response.text}")
            return False
    except requests.RequestException as exc:
        print(f"  FAIL: Network error creating field '{name}': {exc}")
        return False

def main():
    print("=" * 60)
    print("Creating NetBox Custom Fields (Story 1.1)")
    print(f"Target: {NETBOX_URL}")
    print("=" * 60)

    success_count = 0
    failed_count = 0

    for field in custom_fields:
        print(f"\n[{field['name']}]")
        if create_custom_field(field):
            success_count += 1
        else:
            failed_count += 1

    print("\n" + "=" * 60)
    print(f"Result: {success_count} succeeded, {failed_count} failed")
    print("=" * 60)

    if failed_count > 0:
        print("\nSome fields failed to create. Check errors above.")
        print("Tip: You can create them manually in NetBox Admin UI.")
        sys.exit(1)
    else:
        print("\nAll fields created successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
