#!/usr/bin/env python3
"""Debug script to understand queue issues"""

import asyncio
import httpx
import msgpack
import json

async def check_queue():
    """Check the queue directly"""
    base_url = "http://localhost:8059"
    
    # Check queue status
    async with httpx.AsyncClient() as client:
        # Get queue info
        response = await client.get(f"{base_url}/queue/ingestion")
        print(f"Queue status code: {response.status_code}")
        if response.status_code == 200:
            data = msgpack.unpackb(response.content, raw=False)
            print(f"Queue info: {data}")
        
        # Try to poll messages
        print("\nTrying to poll messages...")
        response = await client.post(
            f"{base_url}/queue/ingestion/messages/poll",
            content=msgpack.packb({
                "count": 10,
                "visibility_timeout_secs": 30
            }),
            headers={"Content-Type": "application/msgpack"}
        )
        print(f"Poll status code: {response.status_code}")
        if response.status_code == 200:
            data = msgpack.unpackb(response.content, raw=False)
            print(f"Polled messages: {data}")
        elif response.status_code == 204:
            print("No messages in queue")

if __name__ == "__main__":
    asyncio.run(check_queue())