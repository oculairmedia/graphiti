#!/usr/bin/env python3
"""
Clear all messages from the ingestion queue.
Direct implementation using the queued service API.
"""

import asyncio
import httpx
import msgpack
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clear_queue():
    """Clear all messages from the ingestion queue"""
    base_url = "http://localhost:8059"
    queue_name = "ingestion"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        cleared_count = 0
        batch_size = 100
        
        while True:
            # Poll messages
            try:
                response = await client.post(
                    f"{base_url}/queue/{queue_name}/messages/poll",
                    content=msgpack.packb({
                        "count": batch_size,
                        "visibility_timeout_secs": 1
                    }),
                    headers={"Content-Type": "application/msgpack"}
                )
                
                if response.status_code == 204:
                    # No messages available
                    break
                    
                if response.status_code != 200:
                    logger.error(f"Poll failed: {response.status_code} - {response.text}")
                    break
                    
                result = msgpack.unpackb(response.content, raw=False)
                messages = result.get("messages", [])
                
                if not messages:
                    break
                
                logger.info(f"Found {len(messages)} messages to delete")
                
                # Delete all polled messages
                delete_batch = []
                for msg in messages:
                    delete_batch.append({
                        "id": msg["id"],
                        "poll_tag": msg["poll_tag"]
                    })
                
                delete_response = await client.post(
                    f"{base_url}/queue/{queue_name}/messages/delete",
                    content=msgpack.packb({"messages": delete_batch}),
                    headers={"Content-Type": "application/msgpack"}
                )
                
                if delete_response.status_code == 200:
                    cleared_count += len(delete_batch)
                    logger.info(f"Deleted {len(delete_batch)} messages (total: {cleared_count})")
                else:
                    logger.error(f"Delete failed: {delete_response.status_code} - {delete_response.text}")
                    break
                    
            except Exception as e:
                logger.error(f"Error during queue clearing: {e}")
                break
        
        logger.info(f"Queue clearing complete. Deleted {cleared_count} messages total.")
        return cleared_count

if __name__ == "__main__":
    result = asyncio.run(clear_queue())
    print(f"Cleared {result} messages from queue")