"""
Worker implementation for processing ingestion queue tasks.
Handles rate limiting, retries, and error recovery.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from dataclasses import dataclass
import traceback

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.ingestion.queue_client import (
    QueuedClient, IngestionTask, TaskType, TaskPriority, QueueMetrics
)

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when rate limit is exceeded"""
    def __init__(self, group_id: str, retry_after: int = 60):
        self.group_id = group_id
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for group {group_id}")


class TransientError(Exception):
    """Transient error that should be retried"""
    pass


class PermanentError(Exception):
    """Permanent error that should not be retried"""
    pass


@dataclass
class RateLimitWindow:
    """Sliding window for rate limiting"""
    requests: list[float]
    limit: int
    window_seconds: int
    
    def is_allowed(self) -> bool:
        """Check if request is allowed"""
        now = time.time()
        cutoff = now - self.window_seconds
        
        # Remove old requests
        self.requests = [t for t in self.requests if t > cutoff]
        
        # Check if under limit
        return len(self.requests) < self.limit
    
    def record_request(self):
        """Record a new request"""
        self.requests.append(time.time())


class RateLimiter:
    """
    Rate limiter with per-group and global limits.
    Implements sliding window algorithm for accurate rate limiting.
    """
    
    def __init__(self,
                 global_rps: int = 100,
                 group_rpm: int = 60,
                 burst_multiplier: float = 1.5):
        self.global_window = RateLimitWindow([], global_rps, 1)
        self.group_windows: Dict[str, RateLimitWindow] = {}
        self.group_rpm = group_rpm
        self.burst_multiplier = burst_multiplier
        self.suspended_groups: Dict[str, datetime] = {}
        
    def is_group_suspended(self, group_id: str) -> bool:
        """Check if group is suspended"""
        if group_id not in self.suspended_groups:
            return False
        
        if datetime.utcnow() > self.suspended_groups[group_id]:
            del self.suspended_groups[group_id]
            return False
        
        return True
    
    def suspend_group(self, group_id: str, duration_seconds: int):
        """Suspend a group for rate limiting"""
        self.suspended_groups[group_id] = datetime.utcnow() + timedelta(seconds=duration_seconds)
        logger.warning(f"Suspended group {group_id} for {duration_seconds} seconds")
    
    async def acquire(self, group_id: Optional[str] = None) -> bool:
        """
        Acquire permission to process a request.
        
        Args:
            group_id: Optional group ID for per-group rate limiting
            
        Returns:
            True if request is allowed
            
        Raises:
            RateLimitError if rate limit exceeded
        """
        # Check global rate limit
        if not self.global_window.is_allowed():
            raise RateLimitError("global", retry_after=1)
        
        # Check group rate limit
        if group_id:
            if self.is_group_suspended(group_id):
                remaining = (self.suspended_groups[group_id] - datetime.utcnow()).seconds
                raise RateLimitError(group_id, retry_after=remaining)
            
            if group_id not in self.group_windows:
                self.group_windows[group_id] = RateLimitWindow([], self.group_rpm, 60)
            
            if not self.group_windows[group_id].is_allowed():
                # Suspend group for exponential backoff
                self.suspend_group(group_id, 60)
                raise RateLimitError(group_id, retry_after=60)
            
            self.group_windows[group_id].record_request()
        
        self.global_window.record_request()
        return True


class IngestionWorker:
    """
    Worker that processes tasks from the ingestion queue.
    
    Features:
    - Batch processing for efficiency
    - Rate limiting to prevent overload
    - Exponential backoff for retries
    - Dead letter queue for failed tasks
    - Comprehensive metrics and monitoring
    """
    
    def __init__(self,
                 worker_id: str,
                 queue_client: QueuedClient,
                 graphiti: Graphiti,
                 batch_size: int = 10,
                 poll_interval: float = 1.0):
        self.worker_id = worker_id
        self.queue = queue_client
        self.graphiti = graphiti
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.rate_limiter = RateLimiter()
        self.metrics = QueueMetrics()
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the worker processing loop"""
        if self.running:
            logger.warning(f"Worker {self.worker_id} already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info(f"Worker {self.worker_id} started")
    
    async def stop(self):
        """Stop the worker gracefully"""
        if not self.running:
            return
        
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"Worker {self.worker_id} stopped")
    
    async def _process_loop(self):
        """Main processing loop"""
        logger.info(f"Worker {self.worker_id} entering process loop")
        
        while self.running:
            try:
                # Poll for tasks
                tasks = await self.queue.poll(
                    queue_name="ingestion",
                    count=self.batch_size,
                    visibility_timeout=300  # 5 minutes
                )
                
                if tasks:
                    self.metrics.record_poll(len(tasks))
                    logger.debug(f"Worker {self.worker_id} polled {len(tasks)} tasks")
                    
                    # Process tasks
                    for message_id, task, poll_tag in tasks:
                        try:
                            await self._process_task(task)
                            
                            # Delete from queue on success
                            await self.queue.delete(message_id, poll_tag)
                            self.metrics.record_completion()
                            
                        except RateLimitError as e:
                            # Return to queue with backoff
                            retry_after = min(300, e.retry_after * (2 ** task.retry_count))
                            await self.queue.update(message_id, poll_tag, retry_after)
                            self.metrics.record_retry()
                            logger.warning(f"Rate limited task {task.id}, retry in {retry_after}s")
                            
                        except Exception as e:
                            await self._handle_failure(message_id, poll_tag, task, e)
                else:
                    # No tasks available, wait before polling again
                    await asyncio.sleep(self.poll_interval)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {self.worker_id} loop error: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(5)  # Back off on errors
    
    async def _process_task(self, task: IngestionTask):
        """
        Process a single task.
        
        Args:
            task: The task to process
            
        Raises:
            Various exceptions based on task processing
        """
        logger.debug(f"Processing task {task.id} of type {task.type}")
        
        # Apply rate limiting
        await self.rate_limiter.acquire(task.group_id)
        
        # Route to appropriate handler
        if task.type == TaskType.EPISODE:
            await self._process_episode(task)
        elif task.type == TaskType.ENTITY:
            await self._process_entity(task)
        elif task.type == TaskType.BATCH:
            await self._process_batch(task)
        elif task.type == TaskType.RELATIONSHIP:
            await self._process_relationship(task)
        elif task.type == TaskType.DEDUPLICATION:
            await self._process_deduplication(task)
        else:
            raise PermanentError(f"Unknown task type: {task.type}")
    
    async def _process_episode(self, task: IngestionTask):
        """Process an episode ingestion task"""
        payload = task.payload
        
        try:
            result = await self.graphiti.add_episode(
                uuid=payload.get('uuid'),
                group_id=task.group_id,
                name=payload.get('name'),
                episode_body=payload.get('content'),
                reference_time=payload.get('timestamp'),
                source=EpisodeType.message,
                source_description=payload.get('source_description')
            )
            
            logger.info(f"Processed episode {payload.get('uuid')}: "
                       f"{len(result.nodes) if result and result.nodes else 0} entities created")
            
        except Exception as e:
            # Classify error type
            if "rate limit" in str(e).lower():
                raise RateLimitError(task.group_id)
            elif "connection" in str(e).lower() or "timeout" in str(e).lower():
                raise TransientError(f"Connection error: {e}")
            else:
                raise
    
    async def _process_entity(self, task: IngestionTask):
        """Process an entity creation task"""
        payload = task.payload
        
        try:
            node = await self.graphiti.save_entity_node(
                uuid=payload.get('uuid'),
                group_id=task.group_id,
                name=payload.get('name'),
                summary=payload.get('summary')
            )
            
            logger.info(f"Created entity node {node.uuid if node else 'None'}")
            
        except Exception as e:
            if "duplicate" in str(e).lower():
                # Duplicate entity is not an error
                logger.debug(f"Entity already exists: {payload.get('uuid')}")
            else:
                raise
    
    async def _process_batch(self, task: IngestionTask):
        """Process a batch of operations"""
        payload = task.payload
        operations = payload.get('operations', [])
        
        successful = 0
        failed = 0
        
        for op in operations:
            try:
                op_task = IngestionTask(
                    id=f"{task.id}_{op.get('id')}",
                    type=TaskType(op.get('type')),
                    payload=op.get('payload'),
                    group_id=task.group_id,
                    priority=task.priority,
                    metadata=task.metadata
                )
                
                await self._process_task(op_task)
                successful += 1
                
            except Exception as e:
                logger.error(f"Batch operation failed: {e}")
                failed += 1
        
        logger.info(f"Batch {task.id} completed: {successful} successful, {failed} failed")
        
        if failed > 0 and failed == len(operations):
            raise Exception(f"All batch operations failed")
    
    async def _process_relationship(self, task: IngestionTask):
        """Process a relationship creation task"""
        # TODO: Implement relationship processing
        logger.warning(f"Relationship processing not yet implemented for task {task.id}")
    
    async def _process_deduplication(self, task: IngestionTask):
        """Process a deduplication task"""
        # TODO: Implement deduplication processing
        logger.warning(f"Deduplication processing not yet implemented for task {task.id}")
    
    async def _handle_failure(self, 
                              message_id: str,
                              poll_tag: str,
                              task: IngestionTask,
                              error: Exception):
        """
        Handle task failure with retry logic.
        
        Args:
            message_id: Queue message ID
            poll_tag: Queue poll tag
            task: The failed task
            error: The exception that occurred
        """
        self.metrics.record_failure()
        task.retry_count += 1
        
        logger.error(f"Task {task.id} failed (attempt {task.retry_count}): {error}")
        logger.error(traceback.format_exc())
        
        # Classify error and determine action
        if isinstance(error, PermanentError):
            # Move to dead letter queue
            await self._move_to_dlq(task, error)
            await self.queue.delete(message_id, poll_tag)
            
        elif isinstance(error, TransientError) or task.retry_count < task.max_retries:
            # Retry with exponential backoff
            delay = min(300, 10 * (2 ** task.retry_count))
            await self.queue.update(message_id, poll_tag, delay)
            self.metrics.record_retry()
            logger.info(f"Task {task.id} will retry in {delay} seconds")
            
        else:
            # Max retries exceeded
            await self._move_to_dlq(task, error)
            await self.queue.delete(message_id, poll_tag)
            logger.error(f"Task {task.id} moved to DLQ after {task.retry_count} attempts")
    
    async def _move_to_dlq(self, task: IngestionTask, error: Exception):
        """
        Move failed task to dead letter queue.
        
        Args:
            task: The failed task
            error: The error that caused the failure
        """
        task.metadata['error'] = str(error)
        task.metadata['error_type'] = type(error).__name__
        task.metadata['failed_at'] = datetime.utcnow().isoformat()
        task.metadata['worker_id'] = self.worker_id
        
        # Push to DLQ with no expiry
        await self.queue.push(
            [task],
            queue_name="dead_letter"
        )
        
        logger.error(f"Task {task.id} moved to dead letter queue: {error}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get worker metrics"""
        stats = self.metrics.get_stats()
        stats['worker_id'] = self.worker_id
        stats['running'] = self.running
        return stats


class WorkerPool:
    """
    Manages a pool of workers for parallel processing.
    """
    
    def __init__(self,
                 queue_client: QueuedClient,
                 graphiti: Graphiti,
                 worker_count: int = 4,
                 batch_size: int = 10):
        self.queue = queue_client
        self.graphiti = graphiti
        self.worker_count = worker_count
        self.batch_size = batch_size
        self.workers: list[IngestionWorker] = []
        
    async def start(self):
        """Start all workers in the pool"""
        for i in range(self.worker_count):
            worker = IngestionWorker(
                worker_id=f"worker_{i}",
                queue_client=self.queue,
                graphiti=self.graphiti,
                batch_size=self.batch_size
            )
            await worker.start()
            self.workers.append(worker)
        
        logger.info(f"Started worker pool with {self.worker_count} workers")
    
    async def stop(self):
        """Stop all workers gracefully"""
        logger.info("Stopping worker pool...")
        
        # Stop all workers concurrently
        await asyncio.gather(
            *[worker.stop() for worker in self.workers],
            return_exceptions=True
        )
        
        self.workers.clear()
        logger.info("Worker pool stopped")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics from all workers"""
        return {
            "pool_size": self.worker_count,
            "workers": [worker.get_metrics() for worker in self.workers]
        }