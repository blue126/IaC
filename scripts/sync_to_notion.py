#!/usr/bin/env python3
"""
Sync Terraform State to Notion Database with Parent/Child relations and Credentials.
"""

import os
import json
import sys
import re
import subprocess
import yaml
from notion_client import Client

# --- Configuration ---
# Load .env file from project root (contains NOTION_TOKEN, NOTION_DATABASE_ID)
def _load_dotenv():
    """Load key=value pairs from .env file into os.environ."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
# Project root (resolved from this script's location)
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
SECRETS_FILE = os.path.join(PROJECT_ROOT, "terraform/proxmox/secrets.auto.tfvars")
DRY_RUN = True  # Set to False to actually write to Notion

# Column Mapping
COLUMN_MAPPING = {
    "hostname": "Resource",         # Title
    "ip": "IP Address",             # URL
    "domain": "domain name",        # URL
    "type": "Resource Type",        # Multi-select
    "parent": "Parent item",        # Relation
    "username": "Username",         # Rich Text  (system-level: SSH/RDP)
    "pw": "PW",                     # Rich Text  (system-level)
    "app_username": "App Username", # Rich Text  (app-level: Web UI/DB)
    "app_pw": "App PW",            # Rich Text  (app-level)
    "notes": "Notes"                # Rich Text
}

# Domain names for services
# Tuple: (domain, is_web_ui) — Web UI domains get https:// prefix, others stored as-is
DOMAIN_MAP = {
    "anki":     ("anki.willfan.me", True),
    "caddy":    ("willfan.me", True),
    "homepage": ("homepage.willfan.me", True),
    "immich":   ("immich.willfan.me", True),
    "jenkins":  ("jenkins.willfan.me", True),      # Via Cloudflare Tunnel
    "n8n":      ("n8n.willfan.me", True),
    "netbox":   ("netbox.willfan.me", True),
    "rustdesk": ("rustdesk.willfan.me", False),    # Client relay address, not a Web UI
    # pbs and windows-server have no domain
}

# Service ports: (primary_port, extra_ports_description)
# Sourced from role defaults, playbook verify plays, and docker-compose templates
PORT_MAP = {
    "anki":           (8080, ""),
    "caddy":          (443,  "HTTP redirect: 80 | WebDAV: 8080"),
    "homepage":       (3000, ""),
    "immich":         (2283, ""),
    "jenkins":        (8080, ""),
    "n8n":            (5678, ""),
    "netbox":         (8080, ""),
    "rustdesk":       (21116, "relay: 21117 | web console: 21118"),
    "pbs":            (8007, ""),
    "windows-server": (3389, ""),
}

# Parent Node Mapping (node name -> Notion Page ID)
PARENT_NODES = {
    "pve0": "29d0f3fa-8dfa-8068-915c-de6f9661de30",    # Proxmox(PVE0)
    "pve1": "2b20f3fa-8dfa-804a-b771-c57c29ae814f",    # Proxmox(PVE1)
    "pve2": "29d0f3fa-8dfa-80f8-b5b3-cbda21fead44",    # Proxmox(PVE2)
    "esxi-01": "29d0f3fa-8dfa-80ac-9e3a-dd4542b9d219", # ESXI
}

# Notion client initialized after secrets are loaded (see sync())

def load_secrets():
    """Load secrets from Ansible Vault (single source of truth).

    Uses ansible-vault to decrypt, then parses YAML properly to handle
    all value types (strings, lists, multiline).
    Falls back to secrets.auto.tfvars if vault is unavailable.
    """
    secrets = {}

    # Primary: Ansible Vault (contains ALL secrets)
    vault_file = os.path.join(PROJECT_ROOT, "ansible/inventory/group_vars/all/vault.yml")
    vault_pass = os.path.join(PROJECT_ROOT, "ansible/.vault_pass")
    if os.path.exists(vault_file) and os.path.exists(vault_pass):
        try:
            result = subprocess.run(
                ["ansible-vault", "view", vault_file, "--vault-password-file", vault_pass],
                capture_output=True, text=True, check=True
            )
            data = yaml.safe_load(result.stdout)
            if isinstance(data, dict):
                secrets = {k: v for k, v in data.items() if k.startswith("vault_")}
            print(f"  Loaded {len(secrets)} secrets from Ansible Vault.")
        except Exception as e:
            print(f"  Warning: Failed to read Ansible Vault: {e}")

    # Fallback: secrets.auto.tfvars (Terraform-only subset)
    if not secrets and os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE, 'r') as f:
            content = f.read()
        matches = re.findall(r'(\w+)\s*=\s*"(.*?)"', content)
        for key, val in matches:
            secrets[key] = val
        print(f"  Loaded {len(secrets)} secrets from {SECRETS_FILE} (fallback).")

    return secrets

def get_resource_types(hostname, infra_type):
    """Build multi_select tag list for Resource Type column.

    Args:
        hostname: The ansible_host name (e.g. 'anki', 'pbs', 'windows-server')
        infra_type: 'VM' or 'Container' (infrastructure-level type)
    Returns:
        List of tag names for Notion multi_select
    """
    tags = [infra_type]  # Always include VM or Container

    # OS tag
    if "win" in hostname.lower():
        tags.append("Windows")
    else:
        tags.append("Linux")

    # Role-based tags: App (user-facing service) vs Server (infrastructure service)
    server_roles = {"pbs", "windows-server"}  # Infrastructure/backend servers
    if hostname in server_roles:
        tags.append("Server")
    else:
        tags.append("App")

    return tags


def get_system_creds(hostname, ansible_user, secrets):
    """Determine system-level credentials (SSH/RDP login).

    Args:
        hostname: The ansible_host name
        ansible_user: User from ansible_host TF resource (e.g. 'root', 'ubuntu')
        secrets: Dict of vault secrets
    """
    user = ansible_user

    # Password: host-specific vault key first, then default
    pw_map = {
        "pbs": "vault_pbs_root_password",
        "windows-server": "vault_windows_admin_password",
    }
    vault_key = pw_map.get(hostname, "vault_vm_default_password")
    pw = secrets.get(vault_key, "")

    return user, pw


def get_app_creds(hostname, secrets):
    """Determine application-level credentials (Web UI / DB login).

    All credentials sourced from Ansible Vault.
    Returns (app_user, app_pw, extra_notes) where extra_notes contains
    additional credentials that don't fit in the App columns.
    """
    app_user = ""
    app_pw = ""
    extra_notes = ""

    if hostname == "anki":
        # vault_anki_sync_users: list of "user:pass" strings, e.g. ["anki:anki"]
        users = secrets.get("vault_anki_sync_users", [])
        if isinstance(users, list) and users:
            parts = users[0].split(":")
            if len(parts) == 2:
                app_user, app_pw = parts[0].strip(), parts[1].strip()
    elif hostname == "caddy":
        app_user = "webdav"
        app_pw = secrets.get("vault_caddy_webdav_password", "")
    elif hostname == "netbox":
        app_user = "admin"
        app_pw = secrets.get("vault_netbox_superuser_password", "")
        token = secrets.get("vault_netbox_superuser_api_token", "")
        if token:
            extra_notes = f"API Token: {token}"
    elif hostname == "pbs":
        # PBS Web UI uses PAM auth with root password
        app_user = "root@pam"
        app_pw = secrets.get("vault_pbs_root_password", "")
        token = secrets.get("vault_pbs_api_token_value", "")
        backup_pw = secrets.get("vault_pbs_backup_user_password", "")
        extras = []
        if token:
            extras.append(f"API Token: {token}")
        if backup_pw:
            extras.append(f"backup@pbs: {backup_pw}")
        extra_notes = " | ".join(extras)
    elif hostname == "immich":
        db_pw = secrets.get("vault_immich_db_password", "")
        if db_pw:
            extra_notes = f"DB: postgres/{db_pw}"

    return app_user, app_pw, extra_notes

def _parse_state_file(state_path, default_parent_node=None):
    """Parse a single TF state file and return (ansible_hosts, vm_resources) dicts.

    Args:
        state_path: Path to terraform.tfstate
        default_parent_node: Fallback parent node name for VMs without node_name
                             (e.g. 'esxi-01' for vSphere VMs)
    """
    if not os.path.exists(state_path):
        print(f"  State file not found: {state_path}, skipping.")
        return {}, {}

    with open(state_path, 'r') as f:
        state = json.load(f)

    if 'resources' not in state:
        return {}, {}

    # Supported VM/LXC resource types
    vm_types = [
        'proxmox_vm_qemu', 'proxmox_virtual_environment_vm',
        'proxmox_lxc', 'proxmox_virtual_environment_container',
        'vsphere_virtual_machine',
    ]

    # Pass 1: Collect ansible_host entries (hostname -> {ip, ansible_user})
    ansible_hosts = {}
    for res in state['resources']:
        if res['type'] != 'ansible_host':
            continue
        for inst in res.get('instances', []):
            attr = inst.get('attributes', {})
            name = attr.get('name', '')
            if not name:
                continue
            variables = attr.get('variables', '{}')
            if isinstance(variables, str):
                variables = json.loads(variables)
            ansible_hosts[name] = {
                "ip": variables.get('ansible_host', ''),
                "ansible_user": variables.get('ansible_user', ''),
            }

    # Pass 2: Collect VM/LXC/vSphere resources (module name -> metadata)
    vm_resources = {}
    for res in state['resources']:
        if res['type'] not in vm_types:
            continue

        # Extract module name: "module.anki" -> "anki"
        module_path = res.get('module', '')
        if not module_path.startswith('module.'):
            continue
        module_name = module_path.split('.')[-1]

        # Determine resource type label
        if res['type'] == 'vsphere_virtual_machine':
            res_type = "VM"
        elif "vm" in res['type']:
            res_type = "VM"
        else:
            res_type = "Container"

        for inst in res.get('instances', []):
            attr = inst.get('attributes', {})

            # Node: Proxmox has node_name/target_node; vSphere uses default
            node = attr.get('target_node') or attr.get('node_name') or default_parent_node

            # VMID: Proxmox has vmid/vm_id; vSphere doesn't have a meaningful one
            vmid = attr.get('vmid') or attr.get('vm_id') or 'N/A'

            status = attr.get('status') or attr.get('started', 'unknown')
            if res['type'] == 'vsphere_virtual_machine':
                power = attr.get('power_state', '')
                status = power if power else 'unknown'

            # Get hostname from initialization block (LXC) or name attr (VM)
            hostname = None
            init = attr.get('initialization', [])
            if init and isinstance(init, list) and len(init) > 0:
                hostname = init[0].get('hostname')
            if not hostname:
                hostname = attr.get('name')

            vm_resources[module_name] = {
                "node": node,
                "vmid": vmid,
                "type": res_type,
                "status": status,
                "tf_hostname": hostname,
            }

    return ansible_hosts, vm_resources


def load_resources():
    """Load and merge resources from all TF state files.

    Strategy:
    - ansible_host resources provide: hostname, accurate IP
    - VM/LXC/vSphere resources provide: node_name, vmid, resource type
    - Join key: ansible_host.name == module name (e.g. 'anki' from 'module.anki')
    - Skip hypervisor entries (pve0/1/2, esxi-01) — they already exist in Notion
    """
    all_ansible_hosts = {}
    all_vm_resources = {}

    # State file -> default parent node mapping
    state_configs = [
        (os.path.join(PROJECT_ROOT, "terraform/proxmox/terraform.tfstate"), None),
        (os.path.join(PROJECT_ROOT, "terraform/esxi/terraform.tfstate"), "esxi-01"),
    ]

    for state_path, default_parent in state_configs:
        print(f"  Parsing: {state_path}")
        hosts, vms = _parse_state_file(state_path, default_parent)
        all_ansible_hosts.update(hosts)
        all_vm_resources.update(vms)

    # Merge — use ansible_host as primary, enrich with VM/LXC data
    resources = []
    skip_hosts = set(PARENT_NODES.keys())

    for name, host_info in all_ansible_hosts.items():
        if name in skip_hosts:
            continue

        # Match by ansible_host name; fall back to normalized name (dash -> underscore)
        # because TF module names use underscores while ansible_host names may use dashes
        vm_info = all_vm_resources.get(name) or all_vm_resources.get(name.replace('-', '_'))
        if not vm_info:
            print(f"  Warning: No VM/LXC resource found for ansible_host '{name}', skipping.")
            continue

        # System user: from ansible_user variable, default 'root' for containers
        ansible_user = host_info.get("ansible_user", "")
        if not ansible_user:
            ansible_user = "root"  # Default for LXC containers without explicit ansible_user

        resources.append({
            "hostname": name,
            "ip": host_info["ip"] if host_info["ip"] else "N/A",
            "node": vm_info.get("node"),
            "type": vm_info.get("type", "VM"),
            "vmid": vm_info.get("vmid"),
            "status": vm_info.get("status", "unknown"),
            "ansible_user": ansible_user,
        })

    return resources

def get_existing_pages():
    """Map Hostname -> Page ID"""
    pages = {}
    has_more = True
    start_cursor = None
    
    while has_more:
        resp = client.databases.query(
            database_id=NOTION_DATABASE_ID,
            start_cursor=start_cursor
        )
        for page in resp['results']:
            try:
                # Title property
                title_list = page['properties'][COLUMN_MAPPING['hostname']]['title']
                if title_list:
                    name = title_list[0]['plain_text']
                    pages[name] = page['id']
            except KeyError:
                continue
        has_more = resp['has_more']
        start_cursor = resp['next_cursor']
    return pages

def ensure_columns_exist():
    """Create App Username / App PW columns in Notion DB if they don't exist."""
    db = client.databases.retrieve(NOTION_DATABASE_ID)
    existing_props = set(db['properties'].keys())

    new_props = {}
    for col_key in ["app_username", "app_pw"]:
        col_name = COLUMN_MAPPING[col_key]
        if col_name not in existing_props:
            new_props[col_name] = {"rich_text": {}}
            print(f"  Creating column: {col_name}")

    if new_props:
        if DRY_RUN:
            print(f"  [DRY RUN] Would create columns: {list(new_props.keys())}")
        else:
            client.databases.update(database_id=NOTION_DATABASE_ID, properties=new_props)
            print("  Columns created.")
    else:
        print("  All columns already exist.")


def sync():
    global client

    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        print("Error: NOTION_TOKEN and NOTION_DATABASE_ID environment variables must be set.")
        sys.exit(1)
    client = Client(auth=NOTION_TOKEN)

    print("Loading secrets...")
    secrets = load_secrets()

    print("Ensuring Notion DB columns exist...")
    ensure_columns_exist()

    print("Loading Terraform resources...")
    resources = load_resources()

    print("Fetching existing pages...")
    existing_pages = get_existing_pages()

    for res in resources:
        hostname = res['hostname']
        print(f"Processing {hostname}...")

        # 1. Determine Parent ID
        parent_id = PARENT_NODES.get(res['node'])
        if not parent_id:
            print(f"  Warning: Parent node '{res['node']}' not mapped. Skipping parent association.")

        # 2. Determine Credentials (all from vault + TF state)
        user, pw = get_system_creds(hostname, res['ansible_user'], secrets)
        app_user, app_pw, extra_notes = get_app_creds(hostname, secrets)
        
        # 3. Build Properties
        props = {}

        # Title
        props[COLUMN_MAPPING['hostname']] = {"title": [{"text": {"content": hostname}}]}

        # IP Address (with primary port, no http prefix — matches existing DB format)
        port_info = PORT_MAP.get(hostname, (None, ""))
        primary_port, extra_ports = port_info
        if res['ip'] and res['ip'] != "N/A":
            ip_val = f"{res['ip']}:{primary_port}" if primary_port else res['ip']
            props[COLUMN_MAPPING['ip']] = {"url": ip_val}

        # Domain name — Web UI domains get https://, others stored as bare domain
        domain_info = DOMAIN_MAP.get(hostname)
        if domain_info:
            domain, is_web_ui = domain_info
            domain_url = f"https://{domain}" if is_web_ui else domain
            props[COLUMN_MAPPING['domain']] = {"url": domain_url}

        # Resource Type (multi_select with multiple tags)
        type_tags = get_resource_types(hostname, res['type'])
        props[COLUMN_MAPPING['type']] = {
            "multi_select": [{"name": tag} for tag in type_tags]
        }

        # Parent (Relation)
        if parent_id:
            props[COLUMN_MAPPING['parent']] = {"relation": [{"id": parent_id}]}

        # System Credentials (SSH/RDP)
        props[COLUMN_MAPPING['username']] = {"rich_text": [{"text": {"content": user}}]}
        props[COLUMN_MAPPING['pw']] = {"rich_text": [{"text": {"content": pw}}]}

        # App Credentials (Web UI / DB)
        if app_user:
            props[COLUMN_MAPPING['app_username']] = {"rich_text": [{"text": {"content": app_user}}]}
        if app_pw:
            props[COLUMN_MAPPING['app_pw']] = {"rich_text": [{"text": {"content": app_pw}}]}

        # Notes (VMID + extra ports + extra credentials)
        notes_parts = [f"VMID: {res['vmid']}"]
        if extra_ports:
            notes_parts.append(extra_ports)
        if extra_notes:
            notes_parts.append(extra_notes)
        notes = " | ".join(notes_parts)
        props[COLUMN_MAPPING['notes']] = {"rich_text": [{"text": {"content": notes}}]}

        # 4. Create or Update
        if DRY_RUN:
            ip_val = props.get(COLUMN_MAPPING['ip'], {}).get('url', 'N/A')
            domain_val = props.get(COLUMN_MAPPING.get('domain', ''), {}).get('url', 'N/A')
            action = "UPDATE" if hostname in existing_pages else "CREATE"
            print(f"  [{action}] {hostname}")
            print(f"    IP: {ip_val} | Domain: {domain_val}")
            print(f"    Types: {type_tags} | Parent: {res['node']}")
            print(f"    SSH: {user}/{pw[:3]}*** | App: {app_user or '-'}/{app_pw[:3] + '***' if app_pw else '-'}")
            print(f"    Notes: {notes}")
        elif hostname in existing_pages:
            client.pages.update(page_id=existing_pages[hostname], properties=props)
            print("  Updated.")
        else:
            client.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=props)
            print("  Created.")

if __name__ == "__main__":
    sync()
