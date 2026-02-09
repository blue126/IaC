#!/usr/bin/env python3
"""
自动创建 NetBox Custom Fields
Story 1.1: 定义核心 Custom Fields
"""

import requests
import json
import sys

NETBOX_URL = "http://192.168.1.104:8080"
NETBOX_TOKEN = "0123456789abcdef0123456789abcdef01234567"

headers = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json"
}

# 定义 6 个 Custom Fields
custom_fields = [
    {
        "name": "infrastructure_platform",
        "label": "Infrastructure Platform",
        "type": "select",
        "object_types": ["virtualization.virtualmachine", "dcim.device"],
        "required": True,
        "weight": 100,
        "group_name": "Automation",
        "description": "定义资源的目标基础设施平台",
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
        "description": "控制自动化流程的审批行为",
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
        "description": "指定 Proxmox VE 集群中的目标节点",
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
        "description": "Proxmox 资源的唯一标识符 (100-999)",
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
        "description": "定义资源所属的 Ansible 组",
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
        "description": "指定关联的 Ansible Playbook 文件名"
    }
]

def create_custom_field(field_config):
    """创建单个 Custom Field"""
    name = field_config["name"]
    
    # 检查字段是否已存在
    check_url = f"{NETBOX_URL}/api/extras/custom-fields/?name={name}"
    response = requests.get(check_url, headers=headers)
    
    if response.status_code == 200:
        results = response.json().get("results", [])
        if results:
            print(f"⏭️  字段 '{name}' 已存在，跳过")
            return True
    
    # 创建字段
    url = f"{NETBOX_URL}/api/extras/custom-fields/"
    
    # 对于 select/multiselect 类型，需要先创建 choice_set
    if field_config["type"] in ["select", "multiselect"]:
        # 注意：NetBox API 可能需要特殊处理 choices
        # 这里简化处理，实际可能需要调整
        pass
    
    response = requests.post(url, headers=headers, json=field_config)
    
    if response.status_code in [200, 201]:
        print(f"✅ 成功创建字段: {name}")
        return True
    else:
        print(f"❌ 创建字段 '{name}' 失败:")
        print(f"   状态码: {response.status_code}")
        print(f"   响应: {response.text}")
        return False

def main():
    print("=" * 60)
    print("开始创建 NetBox Custom Fields")
    print("=" * 60)
    
    success_count = 0
    failed_count = 0
    
    for field in custom_fields:
        if create_custom_field(field):
            success_count += 1
        else:
            failed_count += 1
        print()
    
    print("=" * 60)
    print(f"总计: {success_count} 成功, {failed_count} 失败")
    print("=" * 60)
    
    if failed_count > 0:
        print("\n⚠️  部分字段创建失败，请检查上述错误信息")
        print("💡 建议：手动在 NetBox UI 中创建失败的字段")
        sys.exit(1)
    else:
        print("\n🎉 所有字段创建成功！")
        sys.exit(0)

if __name__ == "__main__":
    main()
