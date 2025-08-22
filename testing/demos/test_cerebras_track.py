#!/usr/bin/env python3
"""Send a test message and track Cerebras processing"""

import asyncio
import aiohttp
import json
from datetime import datetime
import time

async def send_and_track():
    url = "http://localhost:8003/api/queue/messages"  # Queue endpoint
    
    # Test message with clear entities
    message = {
        "group_id": "cerebras-test",
        "messages": [{
            "role": "user",
            "role_type": "user",
            "content": "Alice and Bob work at TechCorp. Alice is a software engineer who specializes in Python. Bob is a data scientist who uses machine learning. They are building a recommendation system together.",
            "source": "cerebras_test",
            "source_id": f"test-{datetime.now().timestamp()}",
            "created_at": datetime.now().isoformat()
        }]
    }
    
    print("Sending test message...")
    print(json.dumps(message, indent=2))
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=message) as response:
            status = response.status
            result = await response.text()
            
            print(f"\nStatus: {status}")
            if status == 200:
                print("✅ Message queued successfully!")
                print("\nNow watch the worker logs to see Cerebras processing:")
                print("  docker logs graphiti-worker-1 -f | grep -E 'Cerebras|Extracted|entities|Alice|Bob'")
            else:
                print(f"Response: {result}")

if __name__ == "__main__":
    asyncio.run(send_and_track())