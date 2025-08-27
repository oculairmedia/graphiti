#!/usr/bin/env python3
"""Quick queue status checker"""
import asyncio
from graphiti_core.ingestion.queue_client import QueuedClient

async def main():
    client = QueuedClient()
    try:
        # Quick check for messages
        messages = await client.poll(queue_name='ingestion', count=50, visibility_timeout=1)
        print(f"Queue status: {len(messages)} messages waiting")
        if messages:
            # Count by type
            types = {}
            for _, task, _ in messages:
                task_type = task.type.value
                types[task_type] = types.get(task_type, 0) + 1
            
            print("Breakdown:")
            for task_type, count in types.items():
                print(f"  {task_type}: {count}")
        
        queues = await client.list_queues()
        print(f"Available queues: {', '.join(queues)}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())