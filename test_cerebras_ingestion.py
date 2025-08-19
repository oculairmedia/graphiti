#!/usr/bin/env python3
"""Test Cerebras ingestion through the API"""

import asyncio
import aiohttp
import json
from datetime import datetime

async def test_ingestion():
    url = "http://localhost:8003/api/queue/messages"
    
    # Simple test message
    data = {
        "group_id": "test-group",
        "messages": [
            {
                "role_type": "user",
                "role": "user",
                "content": f"Test message at {datetime.now().isoformat()}. The weather is nice today.",
                "source": "test",
                "source_id": f"test-{datetime.now().timestamp()}",
                "created_at": datetime.now().isoformat()
            }
        ]
    }
    
    print("Sending test message to API...")
    print(f"Data: {json.dumps(data, indent=2)}")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            status = response.status
            result = await response.text()
            
            print(f"\nStatus: {status}")
            try:
                result_json = json.loads(result)
                print(f"Response: {json.dumps(result_json, indent=2)}")
            except:
                print(f"Response: {result}")
            
            if status == 200:
                print("\n✅ Ingestion request accepted!")
                print("Check worker logs to see if Cerebras is processing it:")
                print("  docker logs graphiti-worker-1 --tail 50")
            else:
                print(f"\n❌ Error: Status {status}")

if __name__ == "__main__":
    asyncio.run(test_ingestion())