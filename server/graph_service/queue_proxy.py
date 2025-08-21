"""
Queue proxy for routing ingestion tasks to the queue service.
"""

import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime

import httpx
import msgpack

from graph_service.config import get_settings
from graph_service.dto import Message

logger = logging.getLogger(__name__)


class QueueProxy:
    """Proxy for sending tasks to the queue service"""
    
    def __init__(self, queue_url: Optional[str] = None):
        """Initialize the queue proxy
        
        Args:
            queue_url: URL of the queue service (defaults to settings)
        """
        settings = get_settings()
        self.queue_url = queue_url or settings.queue_url or "http://localhost:8093"
        self.queue_name = "ingestion"
        self.enabled = settings.use_queue_for_ingestion
        
    async def is_healthy(self) -> bool:
        """Check if the queue service is healthy"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.queue_url}/queues")
                if response.status_code == 200:
                    # Check if our queue exists
                    queues = msgpack.unpackb(response.content)
                    queue_names = [q.get('name') for q in queues.get('queues', [])]
                    return self.queue_name in queue_names
                return False
        except Exception as e:
            logger.error(f"Failed to check queue health: {e}")
            return False
    
    async def send_to_queue(self, task: Dict[str, Any], visibility_timeout: int = 300) -> bool:
        """Send a task to the queue
        
        Args:
            task: Task data to send
            visibility_timeout: Time in seconds before task becomes visible again
            
        Returns:
            True if successfully queued, False otherwise
        """
        if not self.enabled:
            logger.debug("Queue proxy disabled, skipping")
            return False
            
        try:
            # Wrap the task in the format expected by the queue client
            # Map priority string to numeric value (matching TaskPriority enum)
            priority_map = {"LOW": 0, "NORMAL": 1, "HIGH": 2, "CRITICAL": 3}
            priority_str = task.get("priority", "NORMAL")
            priority_val = priority_map.get(priority_str, 1)
            
            wrapper = {
                "task": json.dumps(task),  # The queue client expects this to be a JSON string
                "priority": priority_val  # Numeric priority for sorting
            }
            
            # Prepare the message in the format expected by queued
            message_data = {
                "messages": [{
                    "contents": json.dumps(wrapper),  # JSON encode the wrapper
                    "visibility_timeout_secs": visibility_timeout
                }]
            }
            
            # Pack with MessagePack
            packed_message = msgpack.packb(message_data)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.queue_url}/queue/{self.queue_name}/messages/push",
                    content=packed_message,
                    headers={"Content-Type": "application/msgpack"}
                )
                
                if response.status_code == 200:
                    logger.info(f"Successfully queued task: {task.get('task_id', 'unknown')}")
                    return True
                else:
                    logger.error(f"Failed to queue task, status: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send task to queue: {e}")
            return False
    
    async def send_message_to_queue(self, message: Message, group_id: str) -> bool:
        """Send a message ingestion task to the queue
        
        Args:
            message: Message to ingest
            group_id: Group ID for the message
            
        Returns:
            True if successfully queued, False otherwise
        """
        # Create task in the format expected by the worker (IngestionTask)
        # Only use UUID if explicitly provided (for linking to existing episodes)
        task = {
            "id": f"msg-{message.uuid if message.uuid else 'new'}",
            "type": "episode",  # TaskType.EPISODE (lowercase)
            "payload": {
                "uuid": message.uuid,  # None for new episodes, UUID for linking existing ones
                "name": message.name or "",
                "content": f"{message.role or ''}({message.role_type}): {message.content}",
                "timestamp": message.timestamp.isoformat() if message.timestamp else None,
                "source_description": message.source_description or ""  # Ensure it's not None
            },
            "group_id": group_id,
            "priority": 1,  # TaskPriority.NORMAL (numeric value)
            "retry_count": 0,
            "max_retries": 3,
            "created_at": datetime.utcnow().isoformat(),  # Required field
            "metadata": {
                "source": "api",
                "created_at": datetime.utcnow().isoformat()
            }
        }
        
        return await self.send_to_queue(task)
    
    async def send_entity_to_queue(self, entity_data: Dict[str, Any], group_id: str) -> bool:
        """Send an entity ingestion task to the queue
        
        Args:
            entity_data: Entity data to ingest
            group_id: Group ID for the entity
            
        Returns:
            True if successfully queued, False otherwise
        """
        # Create task in the format expected by the worker (IngestionTask)
        task = {
            "id": f"entity-{entity_data.get('uuid', 'unknown')}-{datetime.utcnow().timestamp()}",
            "type": "entity",  # TaskType.ENTITY (lowercase)
            "payload": entity_data,
            "group_id": group_id,
            "priority": 1,  # TaskPriority.NORMAL (numeric value)
            "retry_count": 0,
            "max_retries": 3,
            "created_at": datetime.utcnow().isoformat(),  # Required field
            "metadata": {
                "source": "api",
                "created_at": datetime.utcnow().isoformat()
            }
        }
        
        return await self.send_to_queue(task)
    
    async def send_relationship_to_queue(self, source_node: Dict[str, Any], edge: Dict[str, Any], 
                                         target_node: Dict[str, Any], group_id: str) -> bool:
        """Send a relationship creation task to the queue
        
        Args:
            source_node: Source node data
            edge: Edge data
            target_node: Target node data
            group_id: Group ID for the relationship
            
        Returns:
            True if successfully queued, False otherwise
        """
        # Create task in the format expected by the worker (IngestionTask)
        task = {
            "id": f"relationship-{edge.get('uuid', 'unknown')}-{datetime.utcnow().timestamp()}",
            "type": "relationship",  # TaskType.RELATIONSHIP (lowercase)
            "payload": {
                "source_node": source_node,
                "edge": edge,
                "target_node": target_node
            },
            "group_id": group_id,
            "priority": 1,  # TaskPriority.NORMAL (numeric value)
            "retry_count": 0,
            "max_retries": 3,
            "created_at": datetime.utcnow().isoformat(),  # Required field
            "metadata": {
                "source": "api",
                "created_at": datetime.utcnow().isoformat()
            }
        }
        
        return await self.send_to_queue(task)
    
    async def send_deduplication_to_queue(self, dedup_type: str, group_ids: list[str], 
                                          similarity_threshold: float = 0.8) -> bool:
        """Send a deduplication task to the queue
        
        Args:
            dedup_type: Type of deduplication ('nodes', 'edges', or 'both')
            group_ids: List of group IDs to deduplicate
            similarity_threshold: Similarity threshold for merging (0-1)
            
        Returns:
            True if successfully queued, False otherwise
        """
        # Create task in the format expected by the worker (IngestionTask)
        task = {
            "id": f"dedup-{dedup_type}-{datetime.utcnow().timestamp()}",
            "type": "deduplication",  # TaskType.DEDUPLICATION (lowercase)
            "payload": {
                "type": dedup_type,
                "group_ids": group_ids,
                "similarity_threshold": similarity_threshold
            },
            "group_id": group_ids[0] if group_ids else None,
            "priority": 0,  # TaskPriority.LOW (dedup is background task)
            "retry_count": 0,
            "max_retries": 1,  # Dedup is less critical, fewer retries
            "created_at": datetime.utcnow().isoformat(),  # Required field
            "metadata": {
                "source": "api",
                "created_at": datetime.utcnow().isoformat()
            }
        }
        
        return await self.send_to_queue(task)


# Global queue proxy instance
queue_proxy = QueueProxy()