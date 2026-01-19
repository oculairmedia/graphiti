#!/usr/bin/env python3
"""
Simple queue monitoring script for Graphiti ingestion queue.
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.append('/opt/stacks/graphiti')

async def monitor_queue():
    """Monitor the current state of the ingestion queue."""
    
    # Import the queue client
    from graphiti_core.ingestion.queue_client import QueuedClient
    
    print("📊 Graphiti Queue Monitor")
    print("=" * 40)
    print(f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        client = QueuedClient('http://192.168.50.90:8093')
        
        # Check ingestion queue
        ingestion_messages = await client.poll('ingestion', count=5)
        print(f"📥 Ingestion queue: {len(ingestion_messages)} messages (sampling up to 5)")
        
        if ingestion_messages:
            print("   📋 Recent messages:")
            for i, (msg_id, task, poll_tag) in enumerate(ingestion_messages[:3], 1):
                try:
                    if hasattr(task, 'payload') and isinstance(task.payload, dict):
                        group_id = task.payload.get('group_id', 'unknown')
                        name = task.payload.get('name', 'unknown')[:50] + '...' if len(task.payload.get('name', '')) > 50 else task.payload.get('name', 'unknown')
                        print(f"      {i}. ID: {msg_id}, Group: {group_id}, Name: {name}")
                    else:
                        print(f"      {i}. ID: {msg_id}, Task: {task.id if hasattr(task, 'id') else 'unknown'}")
                    
                    # Return message to queue
                    await client.delete(msg_id, poll_tag)
                except Exception as e:
                    print(f"      {i}. Error analyzing message {msg_id}: {e}")
                    try:
                        await client.delete(msg_id, poll_tag)
                    except:
                        pass
        else:
            print("   ✅ Queue is empty")
        
        # Check dead letter queue
        try:
            dlq_messages = await client.poll('dead_letter', count=5)
            print(f"💀 Dead letter queue: {len(dlq_messages)} messages")
            
            # Return DLQ messages
            for msg_id, task, poll_tag in dlq_messages:
                try:
                    await client.delete(msg_id, poll_tag)
                except:
                    pass
        except Exception as e:
            print(f"💀 Dead letter queue: Could not check ({e})")
        
        print("=" * 40)
        return len(ingestion_messages)
        
    except Exception as e:
        print(f"❌ Monitor failed: {e}")
        return -1

if __name__ == "__main__":
    count = asyncio.run(monitor_queue())
    sys.exit(0)