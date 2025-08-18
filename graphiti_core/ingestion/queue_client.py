"""
Queue client wrapper for the queued service.
Based on Wilson Lin's high-performance queue implementation.
"""

import json
import asyncio
from typing import Any, Dict, List, Optional, TypedDict
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
import httpx
import msgpack
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of ingestion tasks"""
    EPISODE = "episode"
    ENTITY = "entity"
    BATCH = "batch"
    RELATIONSHIP = "relationship"
    DEDUPLICATION = "deduplication"


class TaskPriority(int, Enum):
    """Task priority levels"""
    LOW = 0      # Batch operations, analytics
    NORMAL = 1   # Regular message ingestion
    HIGH = 2     # User-initiated operations
    CRITICAL = 3 # System operations


@dataclass
class IngestionTask:
    """Represents a task in the ingestion queue"""
    id: str
    type: TaskType
    payload: Dict[str, Any]
    group_id: Optional[str] = None
    priority: TaskPriority = TaskPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = None
    visibility_timeout: int = 300  # 5 minutes
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}
    
    def to_json(self) -> str:
        """Serialize task to JSON for queue storage"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['type'] = self.type.value
        data['priority'] = self.priority.value
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, data: str) -> 'IngestionTask':
        """Deserialize task from JSON"""
        obj = json.loads(data)
        obj['created_at'] = datetime.fromisoformat(obj['created_at'])
        obj['type'] = TaskType(obj['type'])
        obj['priority'] = TaskPriority(obj['priority'])
        return cls(**obj)


class QueuedMessage(TypedDict):
    """Message structure from queued service"""
    id: int
    contents: str
    poll_tag: int
    created: str
    poll_count: int


class QueuedClient:
    """
    Client for interacting with the queued service.
    
    Provides high-performance, durable message queuing with:
    - 300K ops/sec capability
    - Persistent storage with fsync
    - Visibility timeout for at-least-once processing
    - Batch operations for efficiency
    """
    
    def __init__(self, base_url: str = "http://localhost:8093", timeout: float = 30.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized_queues = set()
        
    @asynccontextmanager
    async def _get_client(self):
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        try:
            yield self._client
        finally:
            pass  # Keep client alive for reuse
    
    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _ensure_queue_exists(self, queue_name: str):
        """Ensure a queue exists, creating it if necessary"""
        if queue_name in self._initialized_queues:
            return
            
        async with self._get_client() as client:
            # Try to create the queue
            response = await client.put(
                f"{self.base_url}/queue/{queue_name}",
                content=msgpack.packb({}),
                headers={"Content-Type": "application/msgpack"}
            )
            
            if response.status_code in (200, 409):  # 409 means queue already exists
                self._initialized_queues.add(queue_name)
                logger.debug(f"Queue {queue_name} ready")
            else:
                logger.warning(f"Failed to ensure queue {queue_name}: {response.status_code}")
    
    async def push(self, tasks: List[IngestionTask], queue_name: str = "ingestion") -> List[int]:
        """
        Push tasks to the queue.
        
        Args:
            tasks: List of tasks to enqueue
            queue_name: Name of the queue (for logical separation)
            
        Returns:
            List of message IDs
        """
        await self._ensure_queue_exists(queue_name)
        
        async with self._get_client() as client:
            # Prepare messages for batch push
            messages = []
            for task in tasks:
                # Store task with priority prefix in contents
                contents = json.dumps({
                    "priority": task.priority.value,
                    "task": task.to_json()
                })
                messages.append({
                    "contents": contents,
                    "visibility_timeout_secs": task.visibility_timeout
                })
            
            # Batch push for efficiency
            response = await client.post(
                f"{self.base_url}/queue/{queue_name}/messages/push",
                content=msgpack.packb({"messages": messages}),
                headers={"Content-Type": "application/msgpack"}
            )
            response.raise_for_status()
            
            result = msgpack.unpackb(response.content, raw=False)
            ids = result.get("ids", [])
            logger.info(f"Pushed {len(tasks)} tasks to queue {queue_name}, IDs: {ids}")
            return ids
    
    async def poll(self, 
                   queue_name: str = "ingestion",
                   count: int = 10,
                   visibility_timeout: int = 300) -> List[tuple[int, IngestionTask, int]]:
        """
        Poll tasks from the queue.
        
        Args:
            queue_name: Name of the queue
            count: Maximum number of messages to retrieve
            visibility_timeout: Seconds before message becomes visible again
            
        Returns:
            List of (message_id, task, poll_tag) tuples
        """
        await self._ensure_queue_exists(queue_name)
        
        async with self._get_client() as client:
            response = await client.post(
                f"{self.base_url}/queue/{queue_name}/messages/poll",
                content=msgpack.packb({
                    "count": count,
                    "visibility_timeout_secs": visibility_timeout
                }),
                headers={"Content-Type": "application/msgpack"}
            )
            
            if response.status_code == 204:
                # No messages available
                return []
            
            response.raise_for_status()
            result = msgpack.unpackb(response.content, raw=False)
            
            # Sort messages by priority (stored in contents)
            messages = result.get("messages", [])
            prioritized_messages = []
            
            for msg in messages:
                try:
                    # Contents may be bytes or string
                    contents_raw = msg["contents"]
                    if isinstance(contents_raw, bytes):
                        contents_str = contents_raw.decode('utf-8')
                    else:
                        contents_str = contents_raw
                    
                    contents = json.loads(contents_str)
                    task = IngestionTask.from_json(contents["task"])
                    prioritized_messages.append((
                        contents.get("priority", TaskPriority.NORMAL.value),
                        msg["id"],
                        task,
                        msg["poll_tag"]
                    ))
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Failed to parse message {msg.get('id')}: {e}")
                    continue
            
            # Sort by priority (higher priority first)
            prioritized_messages.sort(key=lambda x: x[0], reverse=True)
            
            # Return without priority value
            result_messages = [(msg_id, task, poll_tag) 
                              for _, msg_id, task, poll_tag in prioritized_messages]
            
            if result_messages:
                logger.debug(f"Polled {len(result_messages)} tasks from queue {queue_name}")
            
            return result_messages
    
    async def delete(self, message_id: int, poll_tag: int) -> bool:
        """
        Delete a message from the queue (acknowledge processing).
        
        Args:
            message_id: ID of the message to delete
            poll_tag: Poll tag received when polling the message
            
        Returns:
            True if deleted successfully
        """
        # Find the queue name (we'll use a default for now)
        queue_name = "ingestion"
        
        async with self._get_client() as client:
            response = await client.post(
                f"{self.base_url}/queue/{queue_name}/messages/delete",
                content=msgpack.packb({
                    "messages": [{
                        "id": message_id,
                        "poll_tag": poll_tag
                    }]
                }),
                headers={"Content-Type": "application/msgpack"}
            )
            
            success = response.status_code == 200
            if success:
                logger.debug(f"Deleted message {message_id}")
            else:
                logger.warning(f"Failed to delete message {message_id}: {response.status_code}")
            
            return success
    
    async def update(self, 
                     message_id: int, 
                     poll_tag: int,
                     visibility_timeout: int) -> Optional[int]:
        """
        Update message visibility timeout (for retry with backoff).
        
        Args:
            message_id: ID of the message to update
            poll_tag: Poll tag received when polling
            visibility_timeout: New visibility timeout in seconds
            
        Returns:
            New poll tag if updated successfully, None otherwise
        """
        queue_name = "ingestion"
        
        async with self._get_client() as client:
            response = await client.post(
                f"{self.base_url}/queue/{queue_name}/messages/update",
                content=msgpack.packb({
                    "id": message_id,
                    "poll_tag": poll_tag,
                    "visibility_timeout_secs": visibility_timeout
                }),
                headers={"Content-Type": "application/msgpack"}
            )
            
            if response.status_code == 200:
                result = msgpack.unpackb(response.content, raw=False)
                new_poll_tag = result.get("new_poll_tag")
                logger.debug(f"Updated visibility timeout for message {message_id}, new tag: {new_poll_tag}")
                return new_poll_tag
            else:
                logger.warning(f"Failed to update message {message_id}: {response.status_code}")
                return None
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.
        
        Returns:
            Dictionary with queue metrics
        """
        async with self._get_client() as client:
            response = await client.get(f"{self.base_url}/metrics")
            
            if response.status_code == 200:
                # Metrics might be in MessagePack format
                try:
                    return msgpack.unpackb(response.content, raw=False)
                except:
                    return response.json()
            else:
                return {}
    
    async def list_queues(self) -> List[str]:
        """
        List all available queues.
        
        Returns:
            List of queue names
        """
        async with self._get_client() as client:
            response = await client.get(f"{self.base_url}/queues")
            
            if response.status_code == 200:
                result = msgpack.unpackb(response.content, raw=False)
                queues = result.get("queues", [])
                return [q["name"] for q in queues]
            else:
                return []


class QueueMetrics:
    """Metrics collector for queue operations"""
    
    def __init__(self):
        self.tasks_pushed = 0
        self.tasks_polled = 0
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.tasks_retried = 0
        
    def record_push(self, count: int = 1):
        self.tasks_pushed += count
        
    def record_poll(self, count: int = 1):
        self.tasks_polled += count
        
    def record_completion(self, count: int = 1):
        self.tasks_completed += count
        
    def record_failure(self, count: int = 1):
        self.tasks_failed += count
        
    def record_retry(self, count: int = 1):
        self.tasks_retried += count
    
    def get_stats(self) -> Dict[str, int]:
        return {
            "pushed": self.tasks_pushed,
            "polled": self.tasks_polled,
            "completed": self.tasks_completed,
            "failed": self.tasks_failed,
            "retried": self.tasks_retried,
            "success_rate": (self.tasks_completed / max(1, self.tasks_polled)) * 100
        }