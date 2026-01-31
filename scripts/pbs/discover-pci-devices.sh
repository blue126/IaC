#!/bin/bash
# PBS PCIe Device Discovery Script
# Purpose: Discover LSI HBA and NVMe PCI IDs on ESXi host

echo "=== PBS Hardware Discovery ==="
echo ""

echo "=== 1. Searching for SAS/SCSI Controllers (Broad Search) ==="
esxcli hardware pci list | grep -i -C 20 "SAS\|SCSI\|Fusion\|MPT"

echo ""
echo "=== 2. Searching by Device Class (Mass Storage Controllers) ==="
# Mass Storage Controller class often contains "Storage"
esxcli hardware pci list | grep -i -C 20 "Class Name:.*Storage"

echo ""
echo "=== 3. Searching for Avago/Broadcom (LSI parent companies) ==="
esxcli hardware pci list | grep -i -C 20 "Avago\|Broadcom"

echo ""
echo "=== 4. NVMe Devices (Broad Search) ==="
esxcli hardware pci list | grep -i -C 20 "NVMe\|Non-Volatile"

echo ""
echo "=== 5. List ALL PCI Devices (Summary) ==="
# Compact listing to manually spot the device if above fails
esxcli hardware pci list | grep -E "Address:|Device Name:|Class Name:" | awk '
/Address:/ { printf "\nID: " $2 "\t" }
/Device Name:/ { printf "Dev: " substr($0, index($0,$3)) "\t" }
/Class Name:/ { printf "Class: " substr($0, index($0,$3)) }
'


echo ""
echo "=== Instructions ==="
echo "Copy the PCI IDs (format: 0000:XX:XX.X) to terraform/esxi/terraform.tfvars"
