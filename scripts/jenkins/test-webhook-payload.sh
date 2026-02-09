#!/bin/bash
# Test NetBox Webhook Payload to Jenkins
# Simulates a NetBox 4.x webhook trigger for testing the router pipeline.
# Usage: ./test-webhook-payload.sh

set -euo pipefail

JENKINS_URL="${JENKINS_URL:-http://192.168.1.107:8080}"
WEBHOOK_TOKEN="${WEBHOOK_TOKEN:-netbox-webhook}"
WEBHOOK_ENDPOINT="${JENKINS_URL}/generic-webhook-trigger/invoke?token=${WEBHOOK_TOKEN}"

# Verify dependencies
for cmd in curl jq; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: Required command '$cmd' not found" >&2
        exit 1
    fi
done

# Test Payload - simulates NetBox 4.x webhook payload
# NetBox maps event types internally: object_created->"created", object_updated->"updated"
# Object data is in $.data (full serialized object), snapshots in $.snapshots
TEST_PAYLOAD='{
  "event": "created",
  "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")'",
  "model": "virtualmachine",
  "username": "admin",
  "request_id": "test-webhook-'$(date +%s)'",
  "data": {
    "id": 999,
    "url": "http://192.168.1.104:8080/api/virtualization/virtual-machines/999/",
    "display_url": "http://192.168.1.104:8080/virtualization/virtual-machines/999/",
    "display": "test-webhook-vm",
    "name": "test-webhook-vm",
    "status": {
      "value": "planned",
      "label": "Planned"
    },
    "memory": 2048,
    "vcpus": 2,
    "disk": 20,
    "cluster": {
      "id": 1,
      "url": "http://192.168.1.104:8080/api/virtualization/clusters/1/",
      "display": "HomeLab Cluster",
      "name": "HomeLab Cluster"
    },
    "primary_ip4": {
      "id": 100,
      "url": "http://192.168.1.104:8080/api/ipam/ip-addresses/100/",
      "display": "192.168.1.201/24",
      "address": "192.168.1.201/24"
    },
    "custom_fields": {
      "infrastructure_platform": "proxmox",
      "automation_level": "requires_approval",
      "proxmox_node": "pve0",
      "proxmox_vmid": 201,
      "ansible_groups": ["pve_lxc", "tailscale"],
      "playbook_name": null
    },
    "created": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")'",
    "last_updated": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")'"
  },
  "snapshots": {
    "prechange": null,
    "postchange": {
      "created": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")'",
      "custom_fields": {
        "infrastructure_platform": "proxmox",
        "automation_level": "requires_approval",
        "proxmox_node": "pve0",
        "proxmox_vmid": 201,
        "ansible_groups": ["pve_lxc", "tailscale"],
        "playbook_name": null
      }
    }
  }
}'

echo "======================================"
echo "Testing NetBox Webhook to Jenkins"
echo "======================================"
echo "Endpoint: ${WEBHOOK_ENDPOINT}"
echo ""
echo "Sending payload:"
echo "${TEST_PAYLOAD}" | jq '.'
echo ""
echo "======================================"

# Send webhook request
echo "Sending webhook..."
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${WEBHOOK_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d "${TEST_PAYLOAD}")

HTTP_CODE=$(echo "${RESPONSE}" | tail -1)
BODY=$(echo "${RESPONSE}" | sed '$d')

echo "HTTP Status Code: ${HTTP_CODE}"
echo ""
echo "Response Body:"
echo "${BODY}"
echo ""

# Check response
case ${HTTP_CODE} in
  200)
    echo "✅ SUCCESS: Webhook triggered successfully"
    echo "   Jenkins should have started a Pipeline build"
    echo "   Check: ${JENKINS_URL}/job/Webhook-Router-Test/"
    exit 0
    ;;
  404)
    echo "⚠️  WARNING: HTTP 404 - No Pipeline configured with token '${WEBHOOK_TOKEN}'"
    echo "   Create a Jenkins Pipeline job with Generic Webhook Trigger configuration"
    exit 1
    ;;
  403)
    echo "⚠️  WARNING: HTTP 403 - CSRF protection or authentication issue"
    echo "   This is expected if no Pipeline is configured yet"
    echo "   Generic Webhook Trigger plugin is installed but needs Pipeline job"
    exit 1
    ;;
  *)
    echo "❌ ERROR: Unexpected HTTP status code ${HTTP_CODE}"
    exit 1
    ;;
esac
