#!/usr/bin/env python3
"""
Submit a test message to the ingestion queue
"""

import httpx
import msgpack
import json
from datetime import datetime

def submit_message():
    """Submit a test message to the ingestion queue"""
    base_url = "http://localhost:8093"
    
    # Create an ingestion task (what the worker expects)
    task = {
        "type": "episode",
        "data": {
            "content": "Alice met Bob at the coffee shop to discuss the new project roadmap",
            "timestamp": datetime.now().isoformat(),
            "source": "test_submission",
            "name": "Test Episode"
        }
    }
    
    # The message format for queued - batch push format
    message_data = {
        "messages": [{
            "contents": json.dumps(task),  # Serialize the task as JSON string
            "visibility_timeout_secs": 300  # 5 minutes visibility timeout
        }]
    }
    
    # Pack with MessagePack
    message = msgpack.packb(message_data)
    
    # Submit to queued - use the push endpoint
    response = httpx.post(
        f"{base_url}/queue/ingestion/messages/push",
        content=message,
        headers={"Content-Type": "application/msgpack"}
    )
    
    if response.status_code == 200:
        result = msgpack.unpackb(response.content, raw=False)
        print(f"✅ Message submitted successfully!")
        print(f"Response: {result}")
        
        # Check queue depth
        response = httpx.get(f"{base_url}/queues")
        data = msgpack.unpackb(response.content, raw=False)
        print(f"Current queues: {data}")
        
        return True
    else:
        print(f"❌ Failed to submit: {response.status_code}")
        print(f"Response: {response.text}")
        return False

if __name__ == "__main__":
    submit_message()