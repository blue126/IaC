#!/bin/bash
# 测试 NetBox Webhook Payload
# Story 1.2: 配置 NetBox Webhook 到 Jenkins

set -e

echo "=========================================="
echo "NetBox Webhook 测试脚本"
echo "=========================================="
echo ""

# 配置
NETBOX_URL="http://192.168.1.104:8080"
NETBOX_TOKEN="${NETBOX_API_TOKEN:-0123456789abcdef0123456789abcdef01234567}"
WEBHOOK_LISTENER_PORT="${WEBHOOK_PORT:-9000}"

# 启动临时 webhook 监听器
echo "1. 启动临时 Webhook 监听器 (端口 $WEBHOOK_LISTENER_PORT)"
echo "   使用 Python http.server..."

# 创建临时 Python 脚本来接收 Webhook
cat > /tmp/webhook_listener.py <<'EOF'
#!/usr/bin/env python3
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        print("\n" + "="*60)
        print("📥 Webhook 接收成功！")
        print("="*60)
        print(f"\n🔹 Path: {self.path}")
        print(f"🔹 Headers:")
        for header, value in self.headers.items():
            print(f"   {header}: {value}")
        
        print(f"\n🔹 Payload:")
        try:
            payload = json.loads(post_data)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            
            # 提取关键字段
            if 'data' in payload:
                data = payload['data']
                print(f"\n🔹 解析结果:")
                print(f"   Event: {payload.get('event', 'N/A')}")
                print(f"   Model: {payload.get('model', 'N/A')}")
                print(f"   Object ID: {data.get('id', 'N/A')}")
                print(f"   Object Name: {data.get('name', 'N/A')}")
                
                if 'custom_fields' in data:
                    print(f"   Custom Fields:")
                    for key, value in data['custom_fields'].items():
                        print(f"      - {key}: {value}")
        except json.JSONDecodeError:
            print(post_data.decode('utf-8'))
        
        print("\n" + "="*60 + "\n")
        
        # 返回成功响应
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Webhook received')
    
    def log_message(self, format, *args):
        # 静默访问日志
        pass

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    print(f"🎧 Webhook 监听器启动在端口 {port}")
    print(f"📡 等待 NetBox Webhook 请求...\n")
    print(f"💡 提示：在 NetBox 中创建或修改虚拟机来触发 Webhook")
    print(f"💡 或使用 Ctrl+C 停止监听器\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 监听器已停止")
        sys.exit(0)
EOF

chmod +x /tmp/webhook_listener.py

echo ""
echo "2. 启动方式:"
echo "   python3 /tmp/webhook_listener.py $WEBHOOK_LISTENER_PORT"
echo ""
echo "3. 测试 Webhook:"
echo "   - 方式 A: 在 NetBox UI 创建测试虚拟机"
echo "   - 方式 B: 使用 curl 模拟 Webhook 请求:"
echo ""
echo '   curl -X POST http://localhost:'"$WEBHOOK_LISTENER_PORT"'/webhook \\'
echo '     -H "Content-Type: application/json" \\'
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
echo "📋 当前 NetBox Webhook 配置:"
echo "=========================================="

# 查询当前 Webhook 配置
curl -s "$NETBOX_URL/api/extras/webhooks/" \
  -H "Authorization: Token $NETBOX_TOKEN" \
  | jq -r '.results[] | 
    "\n🔹 Webhook: \(.name)\n" +
    "   ID: \(.id)\n" +
    "   URL: \(.payload_url)\n" +
    "   Method: \(.http_method)\n" +
    "   Content-Type: \(.http_content_type)\n" +
    "   SSL Verification: \(.ssl_verification)\n"'

echo ""
echo "=========================================="
echo "✅ 脚本准备完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 在另一个终端运行: python3 /tmp/webhook_listener.py $WEBHOOK_LISTENER_PORT"
echo "2. 在 NetBox 创建测试虚拟机触发 Webhook"
echo "3. 检查监听器输出验证 Payload 格式"
