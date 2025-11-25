# Proxmox VM Management with Ansible

This project uses Ansible to automate virtual machine management on a three-node Proxmox cluster.

## Project Goals
- Create Ubuntu VM template
- Deploy VMs using the template
- Run Docker applications on VMs

## Project Structure
```
├── ansible.cfg           # Ansible configuration file
├── inventory/           # Host inventory
│   └── hosts.yml       # Proxmox cluster nodes configuration
├── group_vars/         # Group variables
├── host_vars/          # Host variables
├── playbooks/          # Ansible playbooks
├── roles/              # Custom roles
└── templates/          # Configuration templates
```

## Prerequisites
- Proxmox VE cluster is configured
- Ansible is installed
- Appropriate SSH access permissions