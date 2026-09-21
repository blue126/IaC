# Non-sensitive Terraform variables
# This file is committed to Git

pm_api_url   = "https://192.168.1.50:8006/api2/json"
target_node  = "pve0"
storage_pool = "vmdata"

# Standalone node, addressed directly rather than through the cluster endpoint.
pm_api_url_pve2 = "https://192.168.1.52:8006/api2/json"

# Confirmed by the operator after router and NetBox allocation checks.
pnetlab_ip_allocation_confirmed = true
