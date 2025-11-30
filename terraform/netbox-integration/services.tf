# Service definitions for all VMs and LXC containers

# =============================================================================
# Netbox Services
# =============================================================================
resource "netbox_service" "netbox_web" {
  name               = "Netbox Web"
  protocol           = "tcp"
  ports              = [8080]
  virtual_machine_id = netbox_virtual_machine.netbox.id
  description        = "Netbox IPAM/DCIM web interface"
}

resource "netbox_service" "netbox_postgres" {
  name               = "PostgreSQL (Netbox)"
  protocol           = "tcp"
  ports              = [5432]
  virtual_machine_id = netbox_virtual_machine.netbox.id
  description        = "Netbox PostgreSQL database"
}

resource "netbox_service" "netbox_redis" {
  name               = "Redis (Netbox)"
  protocol           = "tcp"
  ports              = [6379]
  virtual_machine_id = netbox_virtual_machine.netbox.id
  description        = "Netbox Redis cache"
}

# =============================================================================
# Immich Services
# =============================================================================
resource "netbox_service" "immich_web" {
  name               = "Immich Web"
  protocol           = "tcp"
  ports              = [2283]
  virtual_machine_id = netbox_virtual_machine.immich.id
  description        = "Immich photo management web interface"
}

resource "netbox_service" "immich_postgres" {
  name               = "PostgreSQL (Immich)"
  protocol           = "tcp"
  ports              = [5432]
  virtual_machine_id = netbox_virtual_machine.immich.id
  description        = "Immich PostgreSQL database"
}

resource "netbox_service" "immich_redis" {
  name               = "Redis (Immich)"
  protocol           = "tcp"
  ports              = [6379]
  virtual_machine_id = netbox_virtual_machine.immich.id
  description        = "Immich Redis cache"
}

# =============================================================================
# Samba Services
# =============================================================================
resource "netbox_service" "samba_smb" {
  name               = "SMB/CIFS"
  protocol           = "tcp"
  ports              = [445]
  virtual_machine_id = netbox_virtual_machine.samba.id
  description        = "Samba file sharing service"
}

resource "netbox_service" "samba_netbios" {
  name               = "NetBIOS"
  protocol           = "tcp"
  ports              = [139]
  virtual_machine_id = netbox_virtual_machine.samba.id
  description        = "NetBIOS session service"
}

# =============================================================================
# Anki Sync Server Services
# =============================================================================
resource "netbox_service" "anki_sync" {
  name               = "Anki Sync Server"
  protocol           = "tcp"
  ports              = [8080]
  virtual_machine_id = netbox_virtual_machine.anki.id
  description        = "Anki flashcard synchronization server"
}
