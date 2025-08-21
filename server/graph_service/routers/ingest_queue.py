"""
Queue-based ingestion router for Graphiti.
Uses Wilson Lin's queued service for high-performance, reliable ingestion.
"""

import uuid
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from graph_service.dto import AddMessagesRequest, AddEntityNodeRequest, Message, Result
from graphiti_core.ingestion.queue_client import (
    QueuedClient, IngestionTask, TaskType, TaskPriority
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Global queue client instance
_queue_client: Optional[QueuedClient] = None


def get_queue_client() -> QueuedClient:
    """Get or create queue client singleton"""
    global _queue_client
    if _queue_client is None:
        _queue_client = QueuedClient(base_url="http://graphiti-queued:8080")  # Use container name in Docker
    return _queue_client


class QueueStatus(BaseModel):
    """Response model for queue status"""
    task_id: str
    status: str = "queued"
    queue_position: Optional[int] = None
    message: str


@router.post('/queue/messages', response_model=List[QueueStatus])
async def queue_messages(messages_request: AddMessagesRequest):
    """
    Queue messages for async ingestion.
    Returns immediately with task IDs for tracking.
    """
    client = get_queue_client()
    
    try:
        # Create tasks for each message
        tasks = []
        for msg in messages_request.messages:
            task = IngestionTask(
                id=str(uuid.uuid4()),
                type=TaskType.EPISODE,
                payload={
                    "uuid": msg.uuid or str(uuid.uuid4()),
                    "group_id": messages_request.group_id,
                    "name": msg.name,
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat() if msg.created_at else datetime.utcnow().isoformat(),
                    "source_description": msg.source,
                },
                group_id=messages_request.group_id,
                priority=TaskPriority.NORMAL,
                visibility_timeout=0,  # Immediately available for processing
                metadata={
                    "user_id": msg.user_id,
                    "source": "api",
                }
            )
            tasks.append(task)
        
        # Push all tasks to queue
        message_ids = await client.push(tasks, queue_name="ingestion")
        
        # Return status for each task
        statuses = []
        for i, task in enumerate(tasks):
            statuses.append(QueueStatus(
                task_id=task.id,
                status="queued",
                queue_position=i + 1,
                message=f"Message queued for processing (Queue ID: {message_ids[i] if i < len(message_ids) else 'unknown'})"
            ))
        
        logger.info(f"Queued {len(tasks)} messages for group {messages_request.group_id}")
        return statuses
        
    except Exception as e:
        logger.error(f"Failed to queue messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue messages: {str(e)}"
        )


@router.post('/queue/entity', response_model=QueueStatus)
async def queue_entity(entity_request: AddEntityNodeRequest):
    """
    Queue entity creation for async processing.
    """
    client = get_queue_client()
    
    try:
        task = IngestionTask(
            id=str(uuid.uuid4()),
            type=TaskType.ENTITY,
            payload={
                "uuid": entity_request.uuid or str(uuid.uuid4()),
                "group_id": entity_request.group_id,
                "name": entity_request.name,
                "summary": entity_request.summary,
            },
            group_id=entity_request.group_id,
            priority=TaskPriority.NORMAL,
            visibility_timeout=0,
            metadata={"source": "api"}
        )
        
        message_ids = await client.push([task], queue_name="ingestion")
        
        return QueueStatus(
            task_id=task.id,
            status="queued",
            message=f"Entity queued for processing (Queue ID: {message_ids[0] if message_ids else 'unknown'})"
        )
        
    except Exception as e:
        logger.error(f"Failed to queue entity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue entity: {str(e)}"
        )


@router.post('/queue/batch', response_model=QueueStatus)
async def queue_batch(operations: List[dict]):
    """
    Queue a batch of operations for processing.
    """
    client = get_queue_client()
    
    try:
        task = IngestionTask(
            id=str(uuid.uuid4()),
            type=TaskType.BATCH,
            payload={"operations": operations},
            priority=TaskPriority.LOW,  # Batch operations are lower priority
            visibility_timeout=0,
            metadata={"source": "api", "batch_size": len(operations)}
        )
        
        message_ids = await client.push([task], queue_name="ingestion")
        
        return QueueStatus(
            task_id=task.id,
            status="queued",
            message=f"Batch of {len(operations)} operations queued (Queue ID: {message_ids[0] if message_ids else 'unknown'})"
        )
        
    except Exception as e:
        logger.error(f"Failed to queue batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue batch: {str(e)}"
        )


@router.get('/queue/status/{task_id}', response_model=QueueStatus)
async def get_task_status(task_id: str):
    """
    Get the status of a queued task.
    Note: This is a placeholder - actual implementation would require task tracking.
    """
    # TODO: Implement actual status tracking
    return QueueStatus(
        task_id=task_id,
        status="processing",
        message="Task is being processed"
    )


@router.get('/queue/stats')
async def get_queue_stats():
    """
    Get queue statistics and metrics.
    """
    client = get_queue_client()
    
    try:
        stats = await client.get_stats()
        queues = await client.list_queues()
        
        return {
            "queues": queues,
            "metrics": stats,
            "status": "healthy"
        }
        
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        return {
            "queues": [],
            "metrics": {},
            "status": "error",
            "error": str(e)
        }


@router.post('/queue/clear')
async def clear_queue(queue_name: str = "ingestion"):
    """
    Clear all messages from the specified queue.
    WARNING: This will delete all pending messages permanently.
    """
    client = get_queue_client()
    
    try:
        # Poll all messages and delete them
        cleared_count = 0
        batch_size = 100
        
        while True:
            # Poll messages with immediate visibility timeout
            messages = await client.poll(
                queue_name=queue_name,
                count=batch_size,
                visibility_timeout=1
            )
            
            if not messages:
                break
                
            # Delete all polled messages
            for message_id, task, poll_tag in messages:
                success = await client.delete(message_id, poll_tag)
                if success:
                    cleared_count += 1
                else:
                    logger.warning(f"Failed to delete message {message_id}")
        
        logger.info(f"Cleared {cleared_count} messages from queue {queue_name}")
        return {
            "queue_name": queue_name,
            "cleared_count": cleared_count,
            "status": "success",
            "message": f"Successfully cleared {cleared_count} messages from queue"
        }
        
    except Exception as e:
        logger.error(f"Failed to clear queue {queue_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear queue: {str(e)}"
        )