#!/usr/bin/env python3
"""
Test script to verify queue proxy is working
"""

import httpx
import json
from datetime import datetime

# API endpoint
api_url = "http://localhost:8003"

# Test message
test_message = {
    "group_id": "test_queue_proxy",
    "messages": [
        {
            "uuid": f"test-{datetime.utcnow().isoformat()}",
            "name": "Test Queue Message",
            "role": "user",
            "role_type": "user",
            "content": "This is a test message sent through the queue proxy",
            "timestamp": datetime.utcnow().isoformat(),
            "source_description": "test_queue_proxy.py"
        }
    ]
}

print("Sending test message to API with queue proxy enabled...")
print(f"Message: {json.dumps(test_message, indent=2)}")

# Send the request
response = httpx.post(
    f"{api_url}/messages",
    json=test_message,
    timeout=10.0
)

print(f"\nResponse status: {response.status_code}")
print(f"Response body: {response.json()}")

if response.status_code == 202:
    result = response.json()
    if "Queued" in result.get("message", ""):
        print("\n✅ SUCCESS: Message was queued for processing!")
        print(f"Response: {result['message']}")
    else:
        print("\n⚠️ Message was processed directly (not queued)")
        print(f"Response: {result}")
else:
    print(f"\n❌ Error: {response.text}")