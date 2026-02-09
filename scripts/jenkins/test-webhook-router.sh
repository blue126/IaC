#!/bin/bash
# Test script for Webhook Router Pipeline
# Tests all routing scenarios and error handling

set -e

JENKINS_URL="http://192.168.1.107:8080"
WEBHOOK_ENDPOINT="${JENKINS_URL}/generic-webhook-trigger/invoke?token=netbox-webhook"
JOB_NAME="Webhook-Router"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  Webhook Router Pipeline Test Suite"
echo "=========================================="
echo ""

# Function to send webhook
send_webhook() {
    local test_name=$1
    local payload=$2
    local expected_result=$3
    
    echo -e "${YELLOW}Test: ${test_name}${NC}"
    echo "Payload: ${payload}"
    
    response=$(curl -s -w "\n%{http_code}" -X POST "${WEBHOOK_ENDPOINT}" \
        -H "Content-Type: application/json" \
        -d "${payload}")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
        echo -e "${GREEN}✓ Webhook accepted (HTTP ${http_code})${NC}"
    else
        echo -e "${RED}✗ Webhook rejected (HTTP ${http_code})${NC}"
        echo "Response: $body"
    fi
    echo ""
}

# Test 1: Proxmox VM Creation
send_webhook "Test 1: Proxmox VM Creation" '{
  "event": "created",
  "model": "virtualmachine",
  "data": {
    "id": 101,
    "name": "test-proxmox-vm",
    "status": {"value": "planned"},
    "custom_fields": {
      "infrastructure_platform": "proxmox",
      "automation_level": "fully_automated"
    }
  }
}' "success"

# Test 2: ESXi VM Update
send_webhook "Test 2: ESXi VM Update" '{
  "event": "updated",
  "model": "virtualmachine",
  "data": {
    "id": 102,
    "name": "test-esxi-vm",
    "status": {"value": "active"},
    "custom_fields": {
      "infrastructure_platform": "esxi",
      "automation_level": "requires_approval"
    }
  }
}' "success"

# Test 3: Physical Device Creation
send_webhook "Test 3: Physical Device Creation" '{
  "event": "created",
  "model": "device",
  "data": {
    "id": 201,
    "name": "test-physical-server",
    "status": {"value": "planned"},
    "custom_fields": {
      "infrastructure_platform": "physical",
      "automation_level": "manual_only"
    }
  }
}' "success"

# Test 4: Invalid Platform (should trigger error handling)
send_webhook "Test 4: Invalid Platform (Oracle)" '{
  "event": "created",
  "model": "virtualmachine",
  "data": {
    "id": 999,
    "name": "test-invalid-platform",
    "status": {"value": "planned"},
    "custom_fields": {
      "infrastructure_platform": "oracle",
      "automation_level": "fully_automated"
    }
  }
}' "error"

# Test 5: Missing Platform Field (should trigger error handling)
send_webhook "Test 5: Missing Platform Field" '{
  "event": "created",
  "model": "virtualmachine",
  "data": {
    "id": 998,
    "name": "test-no-platform",
    "status": {"value": "planned"},
    "custom_fields": {}
  }
}' "error"

# Test 6: Filtered Event (deleted - should be rejected by regexpFilter)
send_webhook "Test 6: Filtered Event (Deleted)" '{
  "event": "deleted",
  "model": "virtualmachine",
  "data": {
    "id": 997,
    "name": "test-deleted-vm",
    "status": {"value": "decommissioning"},
    "custom_fields": {
      "infrastructure_platform": "proxmox",
      "automation_level": "fully_automated"
    }
  }
}' "filtered"

echo "=========================================="
echo "  Test Results Summary"
echo "=========================================="
echo ""
echo "Check Jenkins Job: ${JENKINS_URL}/job/${JOB_NAME}/"
echo ""
echo "Expected Outcomes:"
echo "  - Tests 1-3: Should trigger pipeline and route successfully"
echo "  - Tests 4-5: Should trigger pipeline but FAIL with clear error message"
echo "  - Test 6: Should be filtered by regexpFilter (no pipeline trigger)"
echo ""
echo "Verify in Jenkins Console Output:"
echo "  1. Routing decision logs present"
echo "  2. Platform validation messages"
echo "  3. Error messages for invalid/missing platforms"
echo "  4. Performance timing < 10s"
echo ""
