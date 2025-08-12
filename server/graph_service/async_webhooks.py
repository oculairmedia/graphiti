"""
Asynchronous webhook dispatcher for improved performance.

This module provides a non-blocking webhook system that moves webhook
dispatch out of the critical request path, improving response times.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Callable, Union, Awaitable
from asyncio import Queue, Task
import httpx
from pydantic import BaseModel
import os
import json

from graph_service.webhooks import NodeAccessEvent, DataIngestionEvent

logger = logging.getLogger(__name__)


class WebhookMetrics:
    """Track webhook dispatch metrics."""
    
    def __init__(self):
        self.total_dispatched = 0
        self.total_failed = 0
        self.total_retried = 0
        self.queue_max_size = 0
        self.last_error_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_dispatched": self.total_dispatched,
            "total_failed": self.total_failed,
            "total_retried": self.total_retried,
            "queue_max_size": self.queue_max_size,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
        }


class AsyncWebhookDispatcher:
    """
    High-performance asynchronous webhook dispatcher.
    
    Features:
    - Non-blocking webhook dispatch
    - Automatic retry with exponential backoff
    - Queue overflow protection
    - Circuit breaker pattern
    - Metrics tracking
    """
    
    def __init__(
        self,
        webhook_url: Optional[str] = None,
        max_queue_size: int = 10000,
        num_workers: int = 3,
        max_retries: int = 3,
        timeout_seconds: float = 5.0,
        circuit_breaker_threshold: int = 10,
        circuit_breaker_reset_seconds: int = 60,
    ):
        """
        Initialize the async webhook dispatcher.
        
        Args:
            webhook_url: External webhook URL
            max_queue_size: Maximum events to queue
            num_workers: Number of concurrent workers
            max_retries: Maximum retry attempts per event
            timeout_seconds: HTTP request timeout
            circuit_breaker_threshold: Failures before opening circuit
            circuit_breaker_reset_seconds: Time before circuit reset
        """
        self.webhook_url = webhook_url or os.getenv("GRAPHITI_WEBHOOK_URL")
        self.data_webhook_urls = self._parse_webhook_urls(
            os.getenv("GRAPHITI_DATA_WEBHOOK_URLS", "")
        )
        
        self.queue: Queue = Queue(maxsize=max_queue_size)
        self.num_workers = num_workers
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        
        # Circuit breaker
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_reset_seconds = circuit_breaker_reset_seconds
        self.consecutive_failures = 0
        self.circuit_open_until: Optional[datetime] = None
        
        # Workers
        self.workers: List[Task] = []
        self.shutdown_event = asyncio.Event()
        
        # Internal handlers (e.g., WebSocket)
        self.internal_handlers: List[Callable[[Any], Awaitable[None]]] = []
        self._handlers_lock = asyncio.Lock()
        
        # HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=timeout_seconds,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        
        # Metrics
        self.metrics = WebhookMetrics()
        
        # Start workers
        self._started = False
    
    def _parse_webhook_urls(self, urls_string: str) -> List[str]:
        """Parse comma-separated webhook URLs."""
        if not urls_string:
            return []
        return [url.strip() for url in urls_string.split(',') if url.strip()]
    
    async def start(self):
        """Start the dispatcher workers."""
        if self._started:
            return
        
        self._started = True
        logger.info(f"Starting {self.num_workers} webhook dispatch workers")
        
        for i in range(self.num_workers):
            worker = asyncio.create_task(self._worker(i))
            self.workers.append(worker)
    
    async def stop(self):
        """Gracefully stop the dispatcher."""
        if not self._started:
            return
        
        logger.info("Stopping webhook dispatcher...")
        self.shutdown_event.set()
        
        # Wait for queue to empty (with timeout)
        try:
            await asyncio.wait_for(self._wait_for_empty_queue(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(f"Queue not empty after 10s, {self.queue.qsize()} events remaining")
        
        # Cancel workers
        for worker in self.workers:
            worker.cancel()
        
        await asyncio.gather(*self.workers, return_exceptions=True)
        
        # Close HTTP client
        await self.client.aclose()
        
        self._started = False
        logger.info("Webhook dispatcher stopped")
    
    async def _wait_for_empty_queue(self):
        """Wait for the queue to be empty."""
        while not self.queue.empty():
            await asyncio.sleep(0.1)
    
    async def add_internal_handler(self, handler: Callable[[Any], Awaitable[None]]):
        """Add an internal handler (e.g., WebSocket broadcast)."""
        async with self._handlers_lock:
            self.internal_handlers.append(handler)
    
    async def add_data_handler(self, handler: Callable[[DataIngestionEvent], Awaitable[None]]):
        """Add a data ingestion handler (e.g., WebSocket notification).
        
        This is a convenience method that wraps the handler to work with
        the internal handler system.
        """
        async with self._handlers_lock:
            self.internal_handlers.append(handler)
    
    async def remove_internal_handler(self, handler: Callable[[Any], Awaitable[None]]):
        """Remove an internal handler."""
        async with self._handlers_lock:
            if handler in self.internal_handlers:
                self.internal_handlers.remove(handler)
    
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.circuit_open_until is None:
            return False
        
        if datetime.now(timezone.utc) > self.circuit_open_until:
            # Reset circuit
            self.circuit_open_until = None
            self.consecutive_failures = 0
            logger.info("Circuit breaker reset")
            return False
        
        return True
    
    def record_failure(self):
        """Record a failure for circuit breaker."""
        self.consecutive_failures += 1
        self.metrics.total_failed += 1
        self.metrics.last_error_time = datetime.now(timezone.utc)
        
        if self.consecutive_failures >= self.circuit_breaker_threshold:
            self.circuit_open_until = datetime.now(timezone.utc).replace(
                second=datetime.now(timezone.utc).second + self.circuit_breaker_reset_seconds
            )
            logger.warning(
                f"Circuit breaker opened after {self.consecutive_failures} failures. "
                f"Will reset at {self.circuit_open_until.isoformat()}"
            )
    
    def record_success(self):
        """Record a success for circuit breaker."""
        self.consecutive_failures = 0
        self.metrics.total_dispatched += 1
        self.metrics.last_success_time = datetime.now(timezone.utc)
    
    async def emit_node_access(
        self,
        node_ids: List[str],
        access_type: str = "search",
        query: Optional[str] = None,
        metadata: Optional[dict] = None
    ):
        """
        Emit a node access event asynchronously.
        
        This is non-blocking and returns immediately.
        """
        if not node_ids:
            return
        
        event = NodeAccessEvent(
            node_ids=node_ids,
            timestamp=datetime.now(timezone.utc),
            access_type=access_type,
            query=query,
            metadata=metadata
        )
        
        try:
            # Non-blocking add to queue
            self.queue.put_nowait(("node_access", event))
            
            # Update metrics
            current_size = self.queue.qsize()
            if current_size > self.metrics.queue_max_size:
                self.metrics.queue_max_size = current_size
            
            if current_size > self.queue.maxsize * 0.8:
                logger.warning(f"Webhook queue at {current_size}/{self.queue.maxsize} capacity")
        
        except asyncio.QueueFull:
            logger.error("Webhook queue full, dropping event")
    
    async def emit_data_ingestion(
        self,
        operation: str,
        group_id: Optional[str] = None,
        episode: Optional[Dict[str, Any]] = None,
        nodes: Optional[List[Dict[str, Any]]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[dict] = None
    ):
        """
        Emit a data ingestion event asynchronously.
        
        This is non-blocking and returns immediately.
        """
        event = DataIngestionEvent(
            operation=operation,
            timestamp=datetime.now(timezone.utc),
            group_id=group_id,
            episode=episode,
            nodes=nodes or [],
            edges=edges or [],
            metadata=metadata
        )
        
        try:
            self.queue.put_nowait(("data_ingestion", event))
        except asyncio.QueueFull:
            logger.error("Webhook queue full, dropping data ingestion event")
    
    async def _worker(self, worker_id: int):
        """Background worker to process webhook queue."""
        logger.info(f"Webhook worker {worker_id} started")
        
        while not self.shutdown_event.is_set():
            try:
                # Get event from queue with timeout
                try:
                    event_type, event = await asyncio.wait_for(
                        self.queue.get(), 
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process the event
                await self._dispatch_event(event_type, event)
                
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        logger.info(f"Webhook worker {worker_id} stopped")
    
    async def _dispatch_event(self, event_type: str, event: Union[NodeAccessEvent, DataIngestionEvent]):
        """Dispatch an event to all configured endpoints."""
        tasks = []
        
        # Check circuit breaker for external webhooks
        if not self.is_circuit_open():
            # External webhook
            if event_type == "node_access" and self.webhook_url:
                tasks.append(self._send_to_webhook(self.webhook_url, event, retry=True))
            
            # Data ingestion webhooks
            if event_type == "data_ingestion" and self.data_webhook_urls:
                for url in self.data_webhook_urls:
                    tasks.append(self._send_to_webhook(url, event, retry=True))
        
        # Internal handlers (always run, no circuit breaker)
        async with self._handlers_lock:
            handlers_copy = self.internal_handlers.copy()
        
        for handler in handlers_copy:
            tasks.append(self._call_internal_handler(handler, event))
        
        # Execute all tasks concurrently
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for failures
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Dispatch error: {result}")
    
    async def _send_to_webhook(self, url: str, event: BaseModel, retry: bool = True):
        """Send event to external webhook with retry logic."""
        attempt = 0
        last_error = None
        
        while attempt <= self.max_retries:
            try:
                response = await self.client.post(
                    url,
                    json=event.model_dump(),
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code < 400:
                    self.record_success()
                    return
                
                # Server error - retry
                if response.status_code >= 500 and retry and attempt < self.max_retries:
                    last_error = f"HTTP {response.status_code}"
                    attempt += 1
                    self.metrics.total_retried += 1
                    
                    # Exponential backoff
                    await asyncio.sleep(2 ** attempt)
                    continue
                
                # Client error - don't retry
                logger.error(f"Webhook failed with status {response.status_code}: {response.text}")
                self.record_failure()
                return
                
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = str(e)
                
                if retry and attempt < self.max_retries:
                    attempt += 1
                    self.metrics.total_retried += 1
                    await asyncio.sleep(2 ** attempt)
                    continue
                
                logger.error(f"Webhook connection error: {e}")
                self.record_failure()
                return
            
            except Exception as e:
                logger.error(f"Unexpected webhook error: {e}")
                self.record_failure()
                return
        
        # Max retries exceeded
        logger.error(f"Webhook failed after {self.max_retries} retries: {last_error}")
        self.record_failure()
    
    async def _call_internal_handler(self, handler: Callable, event: BaseModel):
        """Call an internal handler (e.g., WebSocket)."""
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Internal handler error: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return {
            **self.metrics.to_dict(),
            "queue_size": self.queue.qsize(),
            "circuit_open": self.is_circuit_open(),
            "consecutive_failures": self.consecutive_failures,
        }


# Global dispatcher instance
dispatcher = AsyncWebhookDispatcher()


async def startup_webhook_dispatcher():
    """Start the webhook dispatcher on app startup."""
    await dispatcher.start()


async def shutdown_webhook_dispatcher():
    """Stop the webhook dispatcher on app shutdown."""
    await dispatcher.stop()