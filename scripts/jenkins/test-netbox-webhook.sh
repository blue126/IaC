#!/bin/bash
# Test NetBox Webhook Payload Listener
# Story 1.2: Configure NetBox Webhook to Jenkins
# Creates a local Python webhook listener for debugging payload format.

set -euo pipefail

echo "=========================================="
echo "NetBox Webhook Test Script"
echo "=========================================="
echo ""

# Configuration — read from environment, fail if token not set
NETBOX_URL="${NETBOX_URL:-http://192.168.1.104:8080}"
NETBOX_TOKEN="${NETBOX_API_TOKEN:?ERROR: NETBOX_API_TOKEN environment variable is not set}"
WEBHOOK_LISTENER_PORT="${WEBHOOK_PORT:-9000}"

# Create a temporary Python webhook listener
echo "1. Creating webhook listener (port $WEBHOOK_LISTENER_PORT)"
echo "   Using Python http.server..."

cat > /tmp/webhook_listener.py <<'EOF'
#!/usr/bin/env python3
"""Temporary webhook listener for debugging NetBox payload format."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        print("\n" + "=" * 60)
        print("Webhook received!")
        print("=" * 60)
        print(f"\nPath: {self.path}")
        print("Headers:")
        for header, value in self.headers.items():
            print(f"   {header}: {value}")

        print("\nPayload:")
        try:
            payload = json.loads(post_data)
            print(json.dumps(payload, indent=2, ensure_ascii=False))

            # Extract key fields (NetBox 4.x format: data in $.data)
            if 'data' in payload:
                data = payload['data']
                print(f"\nParsed fields:")
                print(f"   Event: {payload.get('event', 'N/A')}")
                print(f"   Model: {payload.get('model', 'N/A')}")
                print(f"   Object ID: {data.get('id', 'N/A')}")
                print(f"   Object Name: {data.get('name', 'N/A')}")

                if 'custom_fields' in data:
                    print("   Custom Fields:")
                    for key, value in data['custom_fields'].items():
                        print(f"      - {key}: {value}")
        except json.JSONDecodeError:
            print(post_data.decode('utf-8'))

        print("\n" + "=" * 60 + "\n")

        # Return success response
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Webhook received')

    def log_message(self, format, *args):
        # Suppress default access log
        pass

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    print(f"Webhook listener started on port {port}")
    print(f"Waiting for NetBox webhook requests...\n")
    print(f"Tip: Create or modify a VM in NetBox to trigger a webhook")
    print(f"     Or use Ctrl+C to stop the listener\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nListener stopped")
        sys.exit(0)
EOF

chmod +x /tmp/webhook_listener.py

echo ""
echo "2. Usage:"
echo "   python3 /tmp/webhook_listener.py $WEBHOOK_LISTENER_PORT"
echo ""
echo "3. Test webhook:"
echo "   - Option A: Create a test VM in NetBox UI"
echo "   - Option B: Simulate with curl:"
echo ""
echo '   curl -X POST http://localhost:'"$WEBHOOK_LISTENER_PORT"'/webhook \'
echo '     -H "Content-Type: application/json" \'
echo '     -d '"'"'{'
echo '       "event": "created",'
echo '       "timestamp": "2026-02-09T03:40:00Z",'
echo '       "model": "virtualmachine",'
echo '       "username": "admin",'
echo '       "data": {'
echo '         "id": 999,'
echo '         "name": "test-webhook",'
echo '         "status": {"value": "planned", "label": "Planned"},'
echo '         "custom_fields": {'
echo '           "infrastructure_platform": "proxmox",'
echo '           "automation_level": "requires_approval"'
echo '         }'
echo '       }'
echo '     }'"'"
echo ""
echo "=========================================="
echo "Current NetBox Webhook configuration:"
echo "=========================================="

# Query current webhook config
curl -s "$NETBOX_URL/api/extras/webhooks/" \
  -H "Authorization: Token $NETBOX_TOKEN" \
  | jq -r '.results[] |
    "\nWebhook: \(.name)\n" +
    "   ID: \(.id)\n" +
    "   URL: \(.payload_url)\n" +
    "   Method: \(.http_method)\n" +
    "   Content-Type: \(.http_content_type)\n" +
    "   SSL Verification: \(.ssl_verification)\n"'

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. In another terminal: python3 /tmp/webhook_listener.py $WEBHOOK_LISTENER_PORT"
echo "2. Create a test VM in NetBox to trigger the webhook"
echo "3. Check listener output to verify payload format"
