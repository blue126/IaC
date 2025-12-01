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

# inventory/pve_lxc/anki.yml (environment-specific)
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

## Part 5: Automated Deployment Verification

### Why Add Verification Steps?

**Benefits of automated verification**:
- ✅ Catch deployment failures immediately
- ✅ Validate service is actually working (not just "deployed")
- ✅ Provide clear success/failure feedback
- ✅ Enable CI/CD integration (automated testing)
- ✅ Document expected service behavior

### Implementation Pattern

We added a second play in `deploy-anki.yml` dedicated to verification:

```yaml
- name: Deploy Anki Sync Server
  hosts: anki
  roles:
    - anki-sync-server

- name: Verify Anki Sync Server Deployment
  hosts: anki
  tags: [verify]
  tasks:
    # Wait for service to start
    - name: Wait for service to be ready
      wait_for:
        port: 8080
        timeout: 30
    
    # Check systemd status
    - name: Check service status
      systemd:
        name: anki-sync-server
      register: service_status
    
    # Assert expected state
    - name: Assert service is running
      assert:
        that:
          - service_status.status.ActiveState == "active"
          - service_status.status.SubState == "running"
    
    # Test HTTP connectivity
    - name: Test HTTP endpoint
      uri:
        url: "http://localhost:8080/"
        status_code: [200, 404, 405]
```

### Key Ansible Modules for Verification

| Module | Purpose | Example |
|--------|---------|---------|
| `wait_for` | Wait for port/file to be ready | Wait for port 8080 to listen |
| `systemd` | Query service status | Check if service is active |
| `assert` | Enforce conditions | Fail if service not running |
| `uri` | Test HTTP endpoints | Verify web service responds |
| `stat` | Check file/directory | Verify config file exists |

### Running Verification

```bash
# Full deployment + verification
ansible-playbook playbooks/deploy-anki.yml

# Only run verification (skip deployment)
ansible-playbook playbooks/deploy-anki.yml --tags verify
```

**Use case for `--tags verify`**:
- After manual fixes on the server
- Periodic health checks
- Troubleshooting without redeploying

### Verification Output Example

```
TASK [Assert service is running] ***********************
ok: [anki-node] => {
    "changed": false,
    "msg": "✅ Anki Sync Server is active and running"
}

TASK [Display deployment summary] **********************
ok: [anki-node] => {
    "msg": [
        "=========================================",
        "✅ Anki Sync Server Deployment Successful",
        "=========================================",
        "Service Status: active",
        "Listening Port: 8080",
        "Server URL: http://192.168.1.100:8080",
        "HTTP Response: 404",
        "========================================="
    ]
}
```

---

## Part 6: Security & User Management (Homelab Simplified)

### Initial Design vs Final Implementation

**Originally planned** (production best practice):
- Create dedicated `anki` system user
- Run service as `anki` (not root)
- Use `become_user` to switch users

**Problem encountered**:
```bash
FAILED! => {"msg": "MODULE FAILURE: /bin/sh: 1: sudo: not found"}
```

**Root cause**: Debian LXC minimal install doesn't include `sudo` by default.

**Solutions considered**:
1. Install sudo: `apt install sudo`
2. Simplify for homelab: Use root directly

**Final decision**: Use root for homelab simplicity
- ✅ LXC already provides isolation
- ✅ No external network exposure
- ✅ Reduces complexity for learning environment
- ⚠️ Production would use dedicated user + sudo

### Final User Configuration

| Type | Purpose | Example | Notes |
|------|---------|---------|-------|
| **SSH User** | Ansible connection | `root` | Direct access to LXC |
| **Service User** | Run process | `root` | Simplified for homelab |
| **Sync User** | App authentication | `anki:anki` | Application-level credential |

---

## Part 7: Deployment Flow

### Step-by-Step Execution
```bash
cd /home/will/IaC/ansible
ansible-playbook playbooks/deploy-anki.yml
```

### What Happens Internally
1. **Install dependencies**: python3, venv, pip
2. **Create directory**: `/opt/anki-syncserver/` (owned by root for homelab)
3. **Create venv**: `python3 -m venv /opt/anki-syncserver/venv`
4. **Install anki**: `pip install anki` in venv
5. **Deploy service**: Render template → `/etc/systemd/system/anki-sync-server.service`
6. **Enable & start**: `systemctl enable --now anki-sync-server`
7. **Handler (if config changed)**: Restart service
8. **Verify deployment**: Wait for port, check status, test HTTP, display summary

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

## Part 8: Client Configuration

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

## Part 9: Lessons Learned

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

### 4. **Idempotency & Verification**
- Handlers ensure services only restart when needed
- `creates` parameter in commands prevents re-execution
- Ansible's declarative nature enables safe re-runs
- **Automated verification catches deployment issues immediately**

### 5. **Port Discovery**
- Initially configured port 27701 (based on assumption)
- Discovered Anki Sync Server defaults to 8080 (from logs)
- Lesson: Always verify actual service behavior, not just configuration
- Updated all references (inventory, templates, docs) to 8080

### 6. **Homelab vs Production Trade-offs**
- Skipped dedicated system user (would need sudo in LXC)
- Run as root for simplicity in isolated homelab environment
- Documented the trade-off in learning notes
- Production deployment would use proper user isolation

---

## Part 10: Troubleshooting Reference

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

# Should be: drwxr-xr-x root root (in homelab setup)
```

### sudo not found error
```
MODULE FAILURE: /bin/sh: 1: sudo: not found
```

**Solution options**:
1. Install sudo: `ansible anki -m raw -a "apt install -y sudo" -u root`
2. Use root directly (homelab): Remove `become_user` directives
3. Use `su` command: `shell: su - user -c "command"`

We chose option 2 for simplicity.

### Can't connect from client
```bash
# Verify service is listening on all interfaces
ss -tlnp | grep 8080
# Should show: 0.0.0.0:8080

# Check firewall (if any)
iptables -L -n
```

---

## Part 11: Next Steps

1. **SSL/TLS**: Add reverse proxy (nginx) with Let's Encrypt
2. **Backup**: Automate backup of `/opt/anki-syncserver/` data
3. **Monitoring**: Add health checks and alerting
4. **Multiple users**: Test with additional `SYNC_USER2`, `SYNC_USER3`
5. **Apply verification pattern to other services**: Add similar verification to Samba, Immich, Netbox playbooks

---

## Part 12: References

- [Anki Sync Server Official Docs](https://docs.ankiweb.net/sync-server.html)
- [Ansible Best Practices](https://docs.ansible.com/ansible/latest/user_guide/playbooks_best_practices.html)
- [systemd Service Documentation](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
