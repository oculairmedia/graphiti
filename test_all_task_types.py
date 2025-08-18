#!/usr/bin/env python3
"""
Test script to demonstrate all queue task types:
- Episode ingestion
- Entity creation
- Relationship creation
- Deduplication
"""

import asyncio
import json
from datetime import datetime
import httpx
import uuid as uuid_lib

# API endpoint
api_url = "http://localhost:8003"

async def test_episode_ingestion():
    """Test episode/message ingestion through queue"""
    print("\n=== Testing Episode Ingestion ===")
    
    test_message = {
        "group_id": "test_all_tasks",
        "messages": [
            {
                "uuid": f"test-episode-{datetime.utcnow().isoformat()}",
                "name": "Test Episode",
                "role": "user",
                "role_type": "user",
                "content": "Alice met Bob at the coffee shop to discuss the new AI project.",
                "timestamp": datetime.utcnow().isoformat(),
                "source_description": "test_all_task_types.py"
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/messages",
            json=test_message,
            timeout=10.0
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 202:
            print("✅ Episode queued successfully")
        else:
            print(f"❌ Failed: {response.text}")

async def test_entity_creation():
    """Test direct entity creation through queue"""
    print("\n=== Testing Entity Creation ===")
    
    entity_data = {
        "uuid": str(uuid_lib.uuid4()),
        "group_id": "test_all_tasks",
        "name": "OpenAI GPT-4",
        "summary": "A large language model developed by OpenAI"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/entity-node",
            json=entity_data,
            timeout=10.0
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 201:
            print("✅ Entity created successfully")
        else:
            print(f"❌ Failed: {response.text}")

async def test_relationship_creation():
    """Test relationship creation (requires custom API endpoint)"""
    print("\n=== Testing Relationship Creation ===")
    print("Note: This would require a custom API endpoint to queue relationship tasks")
    
    # Example payload structure for relationship task
    relationship_task = {
        "source_node": {
            "uuid": str(uuid_lib.uuid4()),
            "name": "Alice",
            "summary": "Software engineer"
        },
        "edge": {
            "uuid": str(uuid_lib.uuid4()),
            "name": "works_with",
            "fact": "Alice works with Bob on the AI project"
        },
        "target_node": {
            "uuid": str(uuid_lib.uuid4()),
            "name": "Bob",
            "summary": "Data scientist"
        }
    }
    
    print(f"Example relationship task structure:")
    print(json.dumps(relationship_task, indent=2))
    print("This would be sent to queue with type='relationship'")

async def test_deduplication():
    """Test deduplication task (requires custom API endpoint)"""
    print("\n=== Testing Deduplication ===")
    print("Note: This would require a custom API endpoint to queue deduplication tasks")
    
    # Example payload structure for deduplication task
    dedup_task = {
        "type": "both",  # 'nodes', 'edges', or 'both'
        "group_ids": ["test_all_tasks"],
        "similarity_threshold": 0.8
    }
    
    print(f"Example deduplication task structure:")
    print(json.dumps(dedup_task, indent=2))
    print("This would be sent to queue with type='deduplication'")

async def test_batch_operations():
    """Test batch operations through queue"""
    print("\n=== Testing Batch Operations ===")
    
    # Send multiple messages in one request
    batch_messages = {
        "group_id": "test_batch",
        "messages": [
            {
                "uuid": f"batch-msg-1-{datetime.utcnow().isoformat()}",
                "name": "First Message",
                "role": "user",
                "role_type": "user",
                "content": "The weather is nice today.",
                "timestamp": datetime.utcnow().isoformat(),
                "source_description": "test_batch"
            },
            {
                "uuid": f"batch-msg-2-{datetime.utcnow().isoformat()}",
                "name": "Second Message",
                "role": "assistant",
                "role_type": "assistant",
                "content": "Yes, it's perfect for a walk in the park.",
                "timestamp": datetime.utcnow().isoformat(),
                "source_description": "test_batch"
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/messages",
            json=batch_messages,
            timeout=10.0
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 202:
            print("✅ Batch messages queued successfully")
        else:
            print(f"❌ Failed: {response.text}")

async def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing All Queue Task Types")
    print("=" * 60)
    
    # Make sure queue is enabled
    print("\nNote: Ensure USE_QUEUE_FOR_INGESTION=true is set in the API")
    
    # Run tests
    await test_episode_ingestion()
    await asyncio.sleep(1)
    
    await test_entity_creation()
    await asyncio.sleep(1)
    
    await test_batch_operations()
    await asyncio.sleep(1)
    
    await test_relationship_creation()
    await test_deduplication()
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("Check worker logs to see processing: docker logs graphiti-worker-1")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())