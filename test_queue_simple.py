#!/usr/bin/env python3
"""
Simple test to verify queue is working
"""

import httpx
import msgpack
import json

def test_queue():
    """Test basic queue operations"""
    base_url = "http://localhost:8093"
    
    # List queues
    response = httpx.get(f"{base_url}/queues")
    data = msgpack.unpackb(response.content, raw=False)
    print(f"Available queues: {data}")
    
    # Submit a test message
    task = {
        "type": "episode",
        "data": {
            "content": "Test message from simple test",
            "timestamp": "2024-01-01T00:00:00Z"
        }
    }
    
    message = msgpack.packb(task)
    response = httpx.post(
        f"{base_url}/queues/test/messages",
        content=message,
        headers={"Content-Type": "application/msgpack"}
    )
    
    if response.status_code == 200:
        result = msgpack.unpackb(response.content, raw=False)
        print(f"Message submitted: {result}")
        return True
    else:
        print(f"Failed to submit: {response.status_code}")
        return False

if __name__ == "__main__":
    if test_queue():
        print("✅ Queue test passed!")
    else:
        print("❌ Queue test failed!")