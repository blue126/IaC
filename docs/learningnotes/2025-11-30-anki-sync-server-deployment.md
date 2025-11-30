# Anki Sync Server Deployment - Learning Notes

**Date**: 2025-11-30  
**Objective**: Deploy Anki Sync Server on Proxmox LXC using Terraform + Ansible

---

## Infrastructure Overview

### What We Built
- **Terraform**: Created LXC container (ID: 100, IP: 192.168.1.100)
- **Ansible**: Installed and configured Anki Sync Server service

### Architecture
```
Terraform (Infrastructure)  →  Ansible (Configuration)
     ↓                               ↓
  Create LXC                    Install Software
  Set CPU/Memory                Configure Service
  Assign IP                     Start Service
```

---

## Part 1: Terraform LXC Creation

### Configuration (`terraform/proxmox/anki.tf`)
```hcl
module "anki" {
  source = "../modules/proxmox-lxc"
  
  lxc_name       = "anki-sync-server"
  vmid           = 100
  ip_address     = "192.168.1.100/24"
  cores          = 1
  memory         = 2048
  ostemplate     = "debian-12-standard"
}
```

### Key Learnings
- **LXC vs VM**: LXC is lighter weight, shares kernel with host
- **Module pattern**: Reusable `proxmox-lxc` module for consistent deployments
- **State management**: Terraform tracks infrastructure in `.tfstate` files

---

## Part 2: Ansible Role Design

### Role Structure
```
roles/anki-sync-server/
├── defaults/main.yml      # Default variables
├── tasks/main.yml         # Installation steps
├── templates/             # Jinja2 templates
│   └── anki-sync-server.service.j2
└── handlers/main.yml      # Service restart handler
```

### Installation Method: Official pip Approach
Following [official documentation](https://docs.ankiweb.net/sync-server.html):

```bash
# Official recommended method
python3 -m venv ~/syncserver
~/syncserver/bin/pip install anki
SYNC_USER1=user:pass ~/syncserver/bin/python -m anki.syncserver
```

**Why pip instead of source build?**
- ✅ Simpler and officially recommended
- ✅ Automatic dependency management
- ✅ Easy updates via `pip install --upgrade anki`

---

## Part 3: Key Ansible Concepts Learned

### 1. **Roles** - Reusable Configuration Units
- **Purpose**: Package related tasks, templates, variables together
- **Benefit**: Can be shared across projects, tested independently
- **Example**: `roles/anki-sync-server` can be used in multiple playbooks

### 2. **Templates (Jinja2)** - Dynamic Configuration Files
```jinja2
User={{ anki_user }}
{% for sync_user in anki_sync_users %}
Environment="SYNC_USER{{ loop.index }}={{ sync_user }}"
{% endfor %}
```

**Key features**:
- `{{ variable }}` - Variable substitution
- `{% for ... %}` - Loops
- `loop.index` - Loop counter (starts at 1)

**Why use templates?**
- Same role works in different environments (dev/prod)
- Variables defined in inventory, not hardcoded

### 3. **Handlers** - Conditional Execution
```yaml
tasks:
  - name: Deploy systemd service
    template: ...
    notify: Restart anki-sync-server  # Only if file changes

handlers:
  - name: Restart anki-sync-server
    systemd: ...
```

**Behavior**:
- Handler only runs if task reports "changed"
- Executes at end of playbook
- Multiple notifications → single execution
- **Benefit**: Avoids unnecessary service restarts

### 4. **Inventory Variable Override**
```yaml
# defaults/main.yml (role default)
anki_sync_users:
  - "user:pass"

# inventory/pve-lxc/anki.yml (environment-specific)
anki_sync_users:
  - "ankiuser:MyPassword123"
```

**Hierarchy**: Inventory variables > Role defaults  
**Best practice**: Keep secrets in inventory, defaults as examples

---

## Part 4: systemd Service Configuration

### Service File Components

#### [Unit] Section
```ini
Description=Anki Sync Server
After=network.target  # Start after network is available
```

#### [Service] Section
```ini
Type=simple                # Foreground process
User=anki                  # Run as dedicated user (security)
WorkingDirectory=/opt/...  # Data storage location
Environment="SYNC_USER1=..." # Pass credentials
ExecStart=/path/to/python -m anki.syncserver
Restart=on-failure         # Auto-restart if crashes
```

#### [Install] Section
```ini
WantedBy=multi-user.target  # Auto-start on boot
```

**systemd targets**:
- `multi-user.target` = Server mode (no GUI)
- `graphical.target` = Desktop mode (with GUI)

---

## Part 5: Security & User Management

### Three Types of "Users" in This System

| Type | Purpose | Example | Can Login? |
|------|---------|---------|------------|
| **System User** | Run service process | `anki` | ❌ No (`nologin` shell) |
| **SSH User** | Ansible connection | `root` | ✅ Yes |
| **Sync User** | Anki app authentication | `ankiuser` | N/A (app-level) |

**Why create dedicated system user?**
```
root runs service  → Compromised service = full system control
anki runs service  → Compromised service = limited to /opt/anki-syncserver/
```

This is the **principle of least privilege**.

---

## Part 6: Deployment Flow

### Step-by-Step Execution
```bash
cd /home/will/IaC/ansible
ansible-playbook playbooks/deploy-anki.yml
```

### What Happens Internally
1. **Install dependencies**: python3, venv, pip
2. **Create system user**: `anki` (no login)
3. **Create directory**: `/opt/anki-syncserver/` (owned by `anki`)
4. **Create venv**: `python3 -m venv /opt/anki-syncserver/venv`
5. **Install anki**: `pip install anki` in venv
6. **Deploy service**: Render template → `/etc/systemd/system/`
7. **Enable & start**: `systemctl enable --now anki-sync-server`
8. **Handler (if config changed)**: Restart service

### Verification Commands
```bash
# Check service status
ansible anki -m shell -a "systemctl status anki-sync-server"

# Check port listening
ansible anki -m shell -a "ss -tlnp | grep 8080"

# View logs
ansible anki -m shell -a "journalctl -u anki-sync-server -n 50"
```

---

## Part 7: Client Configuration

### Anki Desktop Settings
1. Tools → Preferences → Syncing
2. Self-hosted sync server: `http://192.168.1.100:8080`
3. Username: `anki`
4. Password: `anki`

### AnkiDroid (Android)
1. Settings → Advanced → Custom sync server
2. Sync URL: `http://192.168.1.100:8080`
3. Media sync URL: `http://192.168.1.100:8080`

---

## Lessons Learned

### 1. **Follow Official Documentation**
- Initially considered building from source
- Official pip method is simpler and officially supported
- Lesson: Check official docs first before complex solutions

### 2. **Directory Structure Matters**
- Considered splitting install vs data directories
- Decided to keep simple: everything in `/opt/anki-syncserver/`
- Lesson: Don't over-engineer, follow upstream conventions

### 3. **Variable Scope in Ansible**
- Defaults provide examples
- Inventory overrides for actual values
- Secrets management (considered ansible-vault for future)

### 4. **Idempotency**
- Handlers ensure services only restart when needed
- `creates` parameter in commands prevents re-execution
- Ansible's declarative nature enables safe re-runs

---

## Troubleshooting Reference

### Service won't start
```bash
# Check service status
systemctl status anki-sync-server

# View detailed logs
journalctl -u anki-sync-server -xe

# Check if port is already in use
ss -tlnp | grep 8080
```

### Permission issues
```bash
# Verify directory ownership
ls -ld /opt/anki-syncserver/

# Should be: drwxr-xr-x anki anki
```

### Can't connect from client
```bash
# Verify service is listening on all interfaces
ss -tlnp | grep 8080
# Should show: 0.0.0.0:8080

# Check firewall (if any)
iptables -L -n
```

---

## Next Steps

1. **SSL/TLS**: Add reverse proxy (nginx) with Let's Encrypt
2. **Backup**: Automate backup of `/opt/anki-syncserver/` data
3. **Monitoring**: Add health checks and alerting
4. **Multiple users**: Test with additional `SYNC_USER2`, `SYNC_USER3`

---

## References

- [Anki Sync Server Official Docs](https://docs.ankiweb.net/sync-server.html)
- [Ansible Best Practices](https://docs.ansible.com/ansible/latest/user_guide/playbooks_best_practices.html)
- [systemd Service Documentation](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
