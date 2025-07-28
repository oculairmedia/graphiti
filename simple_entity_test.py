#!/usr/bin/env python3
"""
Simple test to check if entity extraction is working with new model
"""

import asyncio
import requests
import json
from datetime import datetime
import time

# Send a simple test message
def send_test():
    endpoint = "http://localhost:8003/messages"
    
    payload = {
        "messages": [{
            "content": "Testing entity extraction with GraphCanvas React component and Cosmograph library.",
            "role_type": "user", 
            "role": "test_bot",
            "name": f"SimpleTest_{datetime.now().isoformat()}",
            "source_description": "Simple Entity Test",
            "timestamp": datetime.now().isoformat()
        }],
        "group_id": "simple_test_group"
    }
    
    print(f"Sending test message...")
    response = requests.post(endpoint, json=payload)
    print(f"Response: {response.status_code} - {response.text}")
    return response.status_code == 202

async def check_results():
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    
    driver = FalkorDriver(
        host="localhost",
        port=6389,
        database="graphiti_migration"
    )
    
    # Check for recent episodes
    query = """
    MATCH (ep:Episodic)
    WHERE ep.group_id = 'simple_test_group'
    RETURN ep.uuid as uuid, ep.content as content
    ORDER BY ep.created_at DESC
    LIMIT 1
    """
    
    records, _, _ = await driver.execute_query(query)
    
    if not records:
        print("No episode found!")
        return
        
    episode_uuid = records[0]['uuid']
    print(f"Found episode: {episode_uuid}")
    
    # Check for entities
    entity_query = """
    MATCH (ep:Episodic {uuid: $uuid})-[:MENTIONS]->(e:Entity)
    RETURN e.name as name
    """
    
    entities, _, _ = await driver.execute_query(entity_query, uuid=episode_uuid)
    
    if entities:
        print(f"✅ SUCCESS! Found {len(entities)} entities:")
        for e in entities:
            print(f"  - {e['name']}")
    else:
        print("❌ No entities found")
        
        # Check server logs
        print("\nChecking what model is being used...")
        import subprocess
        logs = subprocess.run(
            ["docker-compose", "logs", "--tail=10", "graph"],
            capture_output=True,
            text=True
        )
        if "qwen3:30b" in logs.stdout or "qwen3:30b" in logs.stderr:
            print("✓ Model qwen3:30b is mentioned in logs")
        else:
            print("⚠ Model qwen3:30b not found in recent logs")

async def main():
    # Send test message
    if send_test():
        print("Message sent successfully, waiting 50 seconds for processing...")
        await asyncio.sleep(50)
        
        # Check results
        await check_results()
    else:
        print("Failed to send message")

if __name__ == "__main__":
    asyncio.run(main())