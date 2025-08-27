#!/usr/bin/env python3
"""
Clear all messages from the Graphiti ingestion queue.
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.append('/opt/stacks/graphiti')

async def clear_queue():
    """Clear all messages from the ingestion queue."""
    
    # Import the queue client
    from graphiti_core.ingestion.queue_client import QueuedClient
    
    print("🧹 Clearing Graphiti Ingestion Queue")
    print("=" * 50)
    
    try:
        client = QueuedClient('http://192.168.50.90:8093')
        
        cleared_count = 0
        batch_size = 100
        
        print(f"🔄 Starting queue clear in batches of {batch_size}...")
        
        while True:
            # Poll a batch of messages
            messages = await client.poll('ingestion', count=batch_size)
            
            if not messages:
                print("✅ No more messages in queue")
                break
            
            print(f"📦 Processing batch of {len(messages)} messages...")
            
            # Delete each message in the batch
            batch_cleared = 0
            for msg_id, task, poll_tag in messages:
                try:
                    # Delete message (acknowledge)
                    await client.delete(msg_id, poll_tag)
                    batch_cleared += 1
                    cleared_count += 1
                    
                    if cleared_count % 1000 == 0:
                        print(f"   🗑️  Cleared {cleared_count:,} messages so far...")
                        
                except Exception as e:
                    print(f"⚠️  Failed to delete message {msg_id}: {e}")
            
            print(f"   ✅ Batch complete: {batch_cleared}/{len(messages)} messages cleared")
            
            # If we got fewer messages than batch size, we're done
            if len(messages) < batch_size:
                break
        
        print(f"\n🎉 Queue clear complete!")
        print(f"📊 Total messages cleared: {cleared_count:,}")
        
        # Verify queue is empty
        try:
            remaining = await client.poll('ingestion', count=1)
            if remaining:
                print(f"⚠️  WARNING: {len(remaining)} messages still in queue")
            else:
                print("✅ Queue is now empty")
        except Exception as e:
            print(f"⚠️  Could not verify empty queue: {e}")
        
        return cleared_count
        
    except Exception as e:
        print(f"❌ Queue clear failed: {e}")
        return -1

if __name__ == "__main__":
    cleared = asyncio.run(clear_queue())
    sys.exit(0 if cleared >= 0 else 1)