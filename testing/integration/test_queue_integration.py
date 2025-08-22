#!/usr/bin/env python3
"""Test the integrated queue system with Graphiti."""

import asyncio
import uuid
from datetime import datetime

import sys
sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.ingestion.queue_client import (
    QueuedClient, IngestionTask, TaskType, TaskPriority
)


async def test_integration():
    """Test the full integration with queued service."""
    
    client = QueuedClient(base_url="http://localhost:8093")
    
    try:
        # List existing queues
        print("Listing queues...")
        queues = await client.list_queues()
        print(f"  Available queues: {queues}")
        
        # Create test tasks
        print("\nCreating test tasks...")
        tasks = [
            IngestionTask(
                id=str(uuid.uuid4()),
                type=TaskType.EPISODE,
                payload={
                    "name": "Test Episode 1",
                    "content": "This is a test episode with high priority",
                    "timestamp": datetime.utcnow().isoformat()
                },
                priority=TaskPriority.HIGH
            ),
            IngestionTask(
                id=str(uuid.uuid4()),
                type=TaskType.ENTITY,
                payload={
                    "name": "Test Entity",
                    "type": "person",
                    "attributes": {"role": "tester"}
                },
                priority=TaskPriority.NORMAL
            ),
            IngestionTask(
                id=str(uuid.uuid4()),
                type=TaskType.BATCH,
                payload={
                    "batch_id": "batch-001",
                    "documents": ["doc1", "doc2", "doc3"]
                },
                priority=TaskPriority.LOW
            ),
        ]
        
        # Push tasks
        print("\nPushing tasks to queue...")
        message_ids = await client.push(tasks)
        print(f"  Pushed {len(message_ids)} tasks: {message_ids}")
        
        # Poll tasks
        print("\nPolling tasks from queue...")
        polled_tasks = await client.poll(count=5)
        print(f"  Polled {len(polled_tasks)} tasks")
        
        # Process and acknowledge tasks
        for msg_id, task, poll_tag in polled_tasks:
            print(f"\n  Processing task {task.id}:")
            print(f"    Type: {task.type}")
            print(f"    Priority: {task.priority}")
            print(f"    Payload: {task.payload}")
            
            # Simulate processing
            await asyncio.sleep(0.1)
            
            # Acknowledge completion
            success = await client.delete(msg_id, poll_tag)
            if success:
                print(f"    ✓ Task completed and acknowledged")
            else:
                print(f"    ✗ Failed to acknowledge task")
        
        # Check queue stats
        print("\nChecking queue statistics...")
        stats = await client.get_stats()
        if stats:
            print(f"  Stats: {stats}")
        
        print("\n✓ Integration test completed successfully!")
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_integration())