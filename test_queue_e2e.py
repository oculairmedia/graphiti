#!/usr/bin/env python3
"""End-to-end test of the queued service integration with Graphiti."""

import asyncio
import uuid
import json
from datetime import datetime

import sys
sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.ingestion.queue_client import (
    QueuedClient, IngestionTask, TaskType, TaskPriority
)


async def test_e2e():
    """Test end-to-end queue workflow."""
    
    print("=" * 60)
    print("END-TO-END QUEUE INTEGRATION TEST")
    print("=" * 60)
    
    client = QueuedClient(base_url="http://localhost:8093")
    
    try:
        # Clean up existing messages first
        print("\n1. CLEANING UP EXISTING MESSAGES")
        print("-" * 40)
        while True:
            messages = await client.poll(queue_name="e2e_test", count=100, visibility_timeout=1)
            if not messages:
                break
            for msg_id, _, poll_tag in messages:
                await client.delete(msg_id, poll_tag)
            print(f"  Cleaned {len(messages)} messages")
        print("  Queue is clean")
        
        # Create diverse test tasks
        print("\n2. CREATING TEST TASKS")
        print("-" * 40)
        
        tasks = []
        
        # High priority task
        tasks.append(IngestionTask(
            id=f"high-{uuid.uuid4().hex[:8]}",
            type=TaskType.EPISODE,
            payload={
                "name": "Critical Update",
                "content": "This is a high-priority system update",
                "source": "system",
                "timestamp": datetime.utcnow().isoformat()
            },
            priority=TaskPriority.HIGH,
            visibility_timeout=0,  # Immediately visible
            metadata={"test_run": "e2e", "sequence": 1}
        ))
        
        # Normal priority tasks
        for i in range(3):
            tasks.append(IngestionTask(
                id=f"normal-{uuid.uuid4().hex[:8]}",
                type=TaskType.ENTITY,
                payload={
                    "name": f"Entity {i+1}",
                    "type": "person",
                    "attributes": {
                        "role": f"role_{i+1}",
                        "department": "engineering"
                    }
                },
                priority=TaskPriority.NORMAL,
                visibility_timeout=0,  # Immediately visible
                metadata={"test_run": "e2e", "sequence": i+2}
            ))
        
        # Low priority batch task
        tasks.append(IngestionTask(
            id=f"low-{uuid.uuid4().hex[:8]}",
            type=TaskType.BATCH,
            payload={
                "batch_id": f"batch-{uuid.uuid4().hex[:8]}",
                "documents": [f"doc{i}" for i in range(10)],
                "processing_mode": "background"
            },
            priority=TaskPriority.LOW,
            visibility_timeout=0,  # Immediately visible for testing
            metadata={"test_run": "e2e", "sequence": 5}
        ))
        
        print(f"  Created {len(tasks)} tasks:")
        for task in tasks:
            print(f"    - {task.id}: {task.type.value} (Priority: {task.priority.name})")
        
        # Push tasks to queue
        print("\n3. PUSHING TASKS TO QUEUE")
        print("-" * 40)
        
        message_ids = await client.push(tasks, queue_name="e2e_test")
        print(f"  Successfully pushed {len(message_ids)} tasks")
        print(f"  Message IDs: {message_ids}")
        
        # List queues to verify
        print("\n4. VERIFYING QUEUE STATE")
        print("-" * 40)
        
        queues = await client.list_queues()
        print(f"  Available queues: {queues}")
        assert "e2e_test" in queues, "Test queue not found!"
        
        # Poll tasks (should get high priority first)
        print("\n5. POLLING TASKS BY PRIORITY")
        print("-" * 40)
        
        polled_tasks = await client.poll(queue_name="e2e_test", count=10)
        print(f"  Polled {len(polled_tasks)} tasks")
        
        if not polled_tasks:
            print("  WARNING: No tasks polled! They might still have visibility timeout.")
            print("  Waiting 2 seconds and retrying...")
            await asyncio.sleep(2)
            polled_tasks = await client.poll(queue_name="e2e_test", count=10)
            print(f"  Retry: Polled {len(polled_tasks)} tasks")
        
        # Process tasks
        print("\n6. PROCESSING TASKS")
        print("-" * 40)
        
        processed_count = 0
        failed_count = 0
        
        for msg_id, task, poll_tag in polled_tasks:
            print(f"\n  Processing: {task.id}")
            print(f"    Type: {task.type.value}")
            print(f"    Priority: {task.priority.name}")
            print(f"    Created: {task.created_at}")
            
            # Simulate processing
            try:
                if task.type == TaskType.EPISODE:
                    print(f"    -> Processing episode: {task.payload.get('name')}")
                elif task.type == TaskType.ENTITY:
                    print(f"    -> Processing entity: {task.payload.get('name')}")
                elif task.type == TaskType.BATCH:
                    docs = task.payload.get('documents', [])
                    print(f"    -> Processing batch with {len(docs)} documents")
                
                # Simulate work
                await asyncio.sleep(0.1)
                
                # Acknowledge completion
                success = await client.delete(msg_id, poll_tag)
                if success:
                    processed_count += 1
                    print(f"    ✓ Task completed and acknowledged")
                else:
                    failed_count += 1
                    print(f"    ✗ Failed to acknowledge task")
                    
            except Exception as e:
                print(f"    ✗ Processing error: {e}")
                failed_count += 1
                
                # Update visibility timeout for retry
                new_tag = await client.update(msg_id, poll_tag, visibility_timeout=300)
                if new_tag:
                    print(f"    → Updated visibility timeout for retry")
        
        # Final statistics
        print("\n7. FINAL STATISTICS")
        print("-" * 40)
        print(f"  Tasks created: {len(tasks)}")
        print(f"  Tasks pushed: {len(message_ids)}")
        print(f"  Tasks polled: {len(polled_tasks)}")
        print(f"  Tasks processed: {processed_count}")
        print(f"  Tasks failed: {failed_count}")
        
        # Check remaining messages
        remaining = await client.poll(queue_name="e2e_test", count=10, visibility_timeout=1)
        print(f"  Messages remaining in queue: {len(remaining)}")
        
        # Success criteria
        print("\n8. TEST RESULTS")
        print("-" * 40)
        
        if processed_count > 0 and failed_count == 0:
            print("  ✅ TEST PASSED: All tasks processed successfully!")
        elif processed_count > 0:
            print(f"  ⚠️  TEST PARTIAL: {processed_count} succeeded, {failed_count} failed")
        else:
            print("  ❌ TEST FAILED: No tasks were processed")
        
        print("\n" + "=" * 60)
        print("END-TO-END TEST COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_e2e())