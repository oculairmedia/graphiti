#!/usr/bin/env python3
"""
Test script to verify the group_id constraint violation fix.
"""

import uuid
import json
import asyncio
import httpx
from datetime import datetime
from graphiti_core.ingestion.queue_client import QueuedClient, IngestionTask, TaskType, TaskPriority


async def test_group_id_fix():
    """Test that episodic nodes can be created without constraint violations."""
    print("Testing group_id fix for constraint violations...")
    
    # Test 1: Task with explicit group_id
    print("\n1. Testing task with explicit group_id...")
    client = QueuedClient(base_url="http://localhost:8059")
    
    task_with_group = IngestionTask(
        id=str(uuid.uuid4()),
        type=TaskType.EPISODE,
        payload={
            "uuid": str(uuid.uuid4()),
            "name": "Test Episode with Group ID",
            "content": "This episode has an explicit group_id and should work.",
            "timestamp": datetime.utcnow().isoformat(),
            "source_description": "test script"
        },
        group_id="test-group-explicit",
        priority=TaskPriority.HIGH
    )
    
    try:
        message_ids = await client.push([task_with_group], queue_name="ingestion")
        print(f"✓ Successfully queued task with explicit group_id: {message_ids}")
    except Exception as e:
        print(f"✗ Failed to queue task with explicit group_id: {e}")
    
    # Test 2: Task with None group_id (should use fallback)
    print("\n2. Testing task with None group_id (fallback to default)...")
    
    task_no_group = IngestionTask(
        id=str(uuid.uuid4()),
        type=TaskType.EPISODE,
        payload={
            "uuid": str(uuid.uuid4()),
            "group_id": "test-payload-fallback",  # Should use this as fallback
            "name": "Test Episode with Payload Group ID",
            "content": "This episode has None task.group_id but payload.group_id should be used.",
            "timestamp": datetime.utcnow().isoformat(),
            "source_description": "test script"
        },
        group_id=None,  # This is None, should use payload fallback
        priority=TaskPriority.HIGH
    )
    
    try:
        message_ids = await client.push([task_no_group], queue_name="ingestion")
        print(f"✓ Successfully queued task with None group_id: {message_ids}")
    except Exception as e:
        print(f"✗ Failed to queue task with None group_id: {e}")
    
    # Test 3: Task with both None (should use default)
    print("\n3. Testing task with both None (should use FalkorDB default '_')...")
    
    task_all_none = IngestionTask(
        id=str(uuid.uuid4()),
        type=TaskType.EPISODE,
        payload={
            "uuid": str(uuid.uuid4()),
            "name": "Test Episode with Default Group ID",
            "content": "This episode has both task.group_id and payload.group_id as None, should use FalkorDB default.",
            "timestamp": datetime.utcnow().isoformat(),
            "source_description": "test script"
        },
        group_id=None,  # This is None
        priority=TaskPriority.HIGH
        # payload has no group_id either
    )
    
    try:
        message_ids = await client.push([task_all_none], queue_name="ingestion")
        print(f"✓ Successfully queued task with all None group_ids: {message_ids}")
    except Exception as e:
        print(f"✗ Failed to queue task with all None group_ids: {e}")
    
    # Test 4: Test via HTTP API
    print("\n4. Testing via HTTP API...")
    
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                "http://localhost:8003/queue/messages",
                json={
                    "messages": [
                        {
                            "name": "HTTP API Test",
                            "content": "Testing message submission via HTTP API with group_id fix.",
                            "source": "test-script"
                        }
                    ],
                    "group_id": "test-http-api"
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                print(f"✓ HTTP API test successful: {response.json()}")
            else:
                print(f"✗ HTTP API test failed: {response.status_code} - {response.text}")
                
    except Exception as e:
        print(f"✗ HTTP API test failed with exception: {e}")
    
    await client.close()
    print("\n✓ All tests completed!")


if __name__ == "__main__":
    asyncio.run(test_group_id_fix())