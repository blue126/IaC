#!/bin/bash
# Test script for Webhook Router Pipeline
# Tests all routing scenarios and error handling
#
# Usage: WEBHOOK_TOKEN=<your-token> ./test-webhook-router.sh
# Optional: JENKINS_URL=http://host:port (default: http://192.168.1.107:8080)

command -v jq >/dev/null 2>&1 || { echo "Error: jq is required but not installed"; exit 1; }

JENKINS_URL="${JENKINS_URL:-http://192.168.1.107:8080}"
WEBHOOK_TOKEN="${WEBHOOK_TOKEN:?Error: WEBHOOK_TOKEN environment variable is required}"
WEBHOOK_ENDPOINT="${JENKINS_URL}/generic-webhook-trigger/invoke"
JOB_NAME="Webhook-Router"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

echo "=========================================="
echo "  Webhook Router Pipeline Test Suite"
echo "=========================================="
echo ""

# Function to send webhook and assert trigger result
send_webhook() {
    local test_name=$1
    local payload=$2
    local expected=$3  # "triggered" or "not_triggered"
    
    echo -e "${YELLOW}Test: ${test_name}${NC}"
    
    # Token sent via header to avoid URL logging and encoding issues
    response=$(curl -s -w "\n%{http_code}" -X POST "${WEBHOOK_ENDPOINT}" \
        -H "Content-Type: application/json" \
        -H "token: ${WEBHOOK_TOKEN}" \
        -d "${payload}" 2>&1)
    local curl_exit=$?
    
    if [ "$curl_exit" -ne 0 ]; then
        echo -e "${RED}  ✗ FAIL - curl error (exit code: ${curl_exit})${NC}"
        echo "  Response: $response"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo ""
        return
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    # Validate http_code is numeric
    if ! [[ "$http_code" =~ ^[0-9]{3}$ ]]; then
        echo -e "${RED}  ✗ FAIL - invalid HTTP response code: ${http_code}${NC}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo ""
        return
    fi
    
    if [ "$http_code" -ne 200 ] && [ "$http_code" -ne 201 ]; then
        echo -e "${RED}  ✗ FAIL - HTTP ${http_code} (expected 200)${NC}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo ""
        return
    fi
    
    # Check if pipeline was triggered from response body
    triggered=$(echo "$body" | jq -r '.jobs | to_entries[0].value.triggered // false' 2>/dev/null)
    if [ $? -ne 0 ] || [ -z "$triggered" ]; then
        echo -e "${RED}  ✗ FAIL - failed to parse response JSON${NC}"
        echo "  Response: $body"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo ""
        return
    fi
    
    if [ "$expected" = "triggered" ] && [ "$triggered" = "true" ]; then
        echo -e "${GREEN}  ✓ PASS - Pipeline triggered as expected${NC}"
        PASS_COUNT=$((PASS_COUNT + 1))
    elif [ "$expected" = "not_triggered" ] && [ "$triggered" != "true" ]; then
        echo -e "${GREEN}  ✓ PASS - Pipeline not triggered (filtered) as expected${NC}"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo -e "${RED}  ✗ FAIL - expected: ${expected}, triggered: ${triggered}${NC}"
        echo "  Response: $body"
        FAIL_COUNT=$((FAIL_COUNT + 1))
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
}' "triggered"

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
}' "triggered"

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
}' "triggered"

# Test 4: Invalid Platform (should trigger pipeline, fails at validation)
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
}' "triggered"

# Test 5: Missing Platform Field (should trigger pipeline, fails at validation)
send_webhook "Test 5: Missing Platform Field" '{
  "event": "created",
  "model": "virtualmachine",
  "data": {
    "id": 998,
    "name": "test-no-platform",
    "status": {"value": "planned"},
    "custom_fields": {}
  }
}' "triggered"

# Test 6: Deleted VM (should trigger pipeline, router passes event to downstream)
send_webhook "Test 6: Deleted VM Event" '{
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
}' "triggered"

# Test 7: IP Address event (should be filtered by regexpFilter - not a VM/Device)
send_webhook "Test 7: Non-VM Object (IP Address)" '{
  "event": "created",
  "model": "ipaddress",
  "data": {
    "id": 500,
    "name": "192.168.1.100/24",
    "custom_fields": {}
  }
}' "not_triggered"

echo "=========================================="
echo "  Test Results Summary"
echo "=========================================="
echo ""
echo "  Passed: ${PASS_COUNT}"
echo "  Failed: ${FAIL_COUNT}"
echo "  Total:  $((PASS_COUNT + FAIL_COUNT))"
echo ""
echo "Check Jenkins Job: ${JENKINS_URL}/job/${JOB_NAME}/"
echo ""
echo "Expected Outcomes:"
echo "  - Tests 1-3: Triggered, route to platform pipeline"
echo "  - Tests 4-5: Triggered, fail at platform validation"
echo "  - Test 6:    Triggered, deleted event routed to downstream"
echo "  - Test 7:    Not triggered, filtered by regexpFilter (not VM/Device)"
echo ""
if [ "$FAIL_COUNT" -gt 0 ]; then
    echo -e "${RED}RESULT: SOME TESTS FAILED${NC}"
    exit 1
else
    echo -e "${GREEN}RESULT: ALL TESTS PASSED${NC}"
fi
