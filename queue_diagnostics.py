#!/usr/bin/env python3
"""
Queue diagnostics script - examines messages without removing them.
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.append('/opt/stacks/graphiti')

async def diagnose_queue():
    """Diagnose queue issues without modifying messages."""
    
    from graphiti_core.ingestion.queue_client import QueuedClient
    
    print("🔍 Graphiti Queue Diagnostics")
    print("=" * 50)
    print(f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        client = QueuedClient('http://192.168.50.90:8093')
        
        # Check ingestion queue WITHOUT removing messages
        print("\n📥 INGESTION QUEUE:")
        ingestion_messages = await client.poll('ingestion', count=10)
        print(f"   Found {len(ingestion_messages)} messages")
        
        if ingestion_messages:
            for i, (msg_id, task, poll_tag) in enumerate(ingestion_messages[:5], 1):
                print(f"\n   Message {i} (ID: {msg_id}):")
                try:
                    if hasattr(task, 'task_type'):
                        print(f"      Task Type: {task.task_type}")
                    if hasattr(task, 'payload') and isinstance(task.payload, dict):
                        payload = task.payload
                        print(f"      Group ID: {payload.get('group_id', 'N/A')}")
                        print(f"      Name: {payload.get('name', 'N/A')[:100]}")
                        if 'episode_body' in payload:
                            print(f"      Episode Length: {len(payload['episode_body'])} chars")
                        print(f"      Payload Keys: {list(payload.keys())}")
                    else:
                        print(f"      Task: {task}")
                except Exception as e:
                    print(f"      Error analyzing: {e}")
            
            # Put messages back immediately
            for msg_id, task, poll_tag in ingestion_messages:
                try:
                    await client.delete(msg_id, poll_tag)
                except:
                    pass
        
        # Check dead letter queue WITHOUT removing messages
        print("\n💀 DEAD LETTER QUEUE:")
        dlq_messages = await client.poll('dead_letter', count=10)
        print(f"   Found {len(dlq_messages)} messages")
        
        if dlq_messages:
            for i, (msg_id, task, poll_tag) in enumerate(dlq_messages[:5], 1):
                print(f"\n   DLQ Message {i} (ID: {msg_id}):")
                try:
                    print(f"      Task: {task}")
                    if hasattr(task, 'task_type'):
                        print(f"      Task Type: {task.task_type}")
                    if hasattr(task, 'payload'):
                        print(f"      Payload: {task.payload}")
                    if hasattr(task, 'error'):
                        print(f"      Error: {task.error}")
                except Exception as e:
                    print(f"      Error analyzing: {e}")
            
            # Put DLQ messages back
            for msg_id, task, poll_tag in dlq_messages:
                try:
                    await client.delete(msg_id, poll_tag)
                except:
                    pass
        
        print("\n" + "=" * 50)
        return len(ingestion_messages), len(dlq_messages)
        
    except Exception as e:
        print(f"❌ Diagnostics failed: {e}")
        import traceback
        traceback.print_exc()
        return -1, -1

if __name__ == "__main__":
    ing_count, dlq_count = asyncio.run(diagnose_queue())
    print(f"\n📊 Summary: {ing_count} in ingestion, {dlq_count} in dead letter")
    sys.exit(0)