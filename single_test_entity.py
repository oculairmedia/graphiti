#!/usr/bin/env python3
"""
Single test to verify entity extraction with proper timing
"""

import asyncio
import requests
import json
from datetime import datetime
import time

# Configuration
GRAPHITI_URL = "http://localhost:8003"
TEST_GROUP = "single_test_" + str(int(time.time()))

async def main():
    # 1. Send test message
    endpoint = f"{GRAPHITI_URL}/messages"
    test_content = "Testing GraphCanvas component with React and Cosmograph visualization library for graph rendering."
    
    payload = {
        "messages": [{
            "content": test_content,
            "role_type": "user",
            "role": "test_user", 
            "name": f"SingleTest_{datetime.now().isoformat()}",
            "source_description": "Single Entity Test",
            "timestamp": datetime.now().isoformat()
        }],
        "group_id": TEST_GROUP
    }
    
    print("1. Sending test message...")
    print(f"   Content: {test_content}")
    print(f"   Group: {TEST_GROUP}")
    
    response = requests.post(endpoint, json=payload)
    print(f"   Response: {response.status_code} - {response.text}")
    
    if response.status_code != 202:
        print("Failed to send message!")
        return
        
    # 2. Wait for processing
    print("\n2. Waiting 50 seconds for entity extraction...")
    await asyncio.sleep(50)
    
    # 3. Check results
    print("\n3. Checking results...")
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    
    driver = FalkorDriver(
        host="localhost",
        port=6389,
        database="graphiti_migration"
    )
    
    # Find episode
    ep_query = """
    MATCH (ep:Episodic)
    WHERE ep.group_id = $group_id
    RETURN ep.uuid as uuid, ep.content as content, ep.created_at as created_at
    ORDER BY ep.created_at DESC
    LIMIT 1
    """
    
    ep_records, _, _ = await driver.execute_query(ep_query, group_id=TEST_GROUP)
    
    if not ep_records:
        print("   ❌ No episode found!")
        return
        
    episode = ep_records[0]
    print(f"   ✓ Found episode: {episode['uuid']}")
    print(f"   Created: {episode['created_at']}")
    
    # Check entities
    entity_query = """
    MATCH (ep:Episodic {uuid: $uuid})-[:MENTIONS]->(e:Entity)
    RETURN e.name as name, e.summary as summary
    """
    
    entities, _, _ = await driver.execute_query(entity_query, uuid=episode['uuid'])
    
    if entities:
        print(f"\n   ✅ SUCCESS! Found {len(entities)} entities:")
        for e in entities:
            print(f"      - {e['name']}")
            if e.get('summary'):
                print(f"        Summary: {e['summary'][:100]}...")
    else:
        print("\n   ❌ FAILURE! No entities found")
        
        # Check server logs for errors
        print("\n4. Checking server logs for errors...")
        import subprocess
        result = subprocess.run(
            ["docker-compose", "logs", "--tail=30", "graph"],
            capture_output=True,
            text=True
        )
        
        if "error" in result.stdout.lower() or "error" in result.stderr.lower():
            print("   Found errors in logs:")
            for line in result.stdout.split('\n'):
                if 'error' in line.lower() or 'ERROR' in line:
                    print(f"   {line}")

if __name__ == "__main__":
    asyncio.run(main())