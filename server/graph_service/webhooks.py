"""
Webhook service for emitting events when nodes are accessed.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional
import httpx
from pydantic import BaseModel
import os

logger = logging.getLogger(__name__)


class NodeAccessEvent(BaseModel):
    """Event emitted when nodes are accessed."""
    event_type: str = "node_access"
    node_ids: List[str]
    timestamp: datetime
    access_type: str  # "search", "direct", etc.
    query: Optional[str] = None
    metadata: Optional[dict] = None


class WebhookService:
    """Service for managing and dispatching webhooks."""
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("GRAPHITI_WEBHOOK_URL")
        self.internal_handlers = []
        self._handlers_lock = asyncio.Lock()
        self.client = httpx.AsyncClient(timeout=5.0)
        self._enabled = bool(self.webhook_url or self.internal_handlers)
    
    async def add_internal_handler(self, handler):
        """Add an internal handler for webhook events (e.g., WebSocket broadcast)."""
        async with self._handlers_lock:
            self.internal_handlers.append(handler)
            self._enabled = True
    
    async def emit_node_access(
        self,
        node_ids: List[str],
        access_type: str = "search",
        query: Optional[str] = None,
        metadata: Optional[dict] = None
    ):
        """Emit a node access event."""
        logger.info(f"emit_node_access called: enabled={self._enabled}, node_ids={len(node_ids) if node_ids else 0}, handlers={len(self.internal_handlers)}")
        if not self._enabled or not node_ids:
            logger.warning(f"Skipping emit: enabled={self._enabled}, has_nodes={bool(node_ids)}")
            return
        
        event = NodeAccessEvent(
            node_ids=node_ids,
            timestamp=datetime.now(timezone.utc),
            access_type=access_type,
            query=query,
            metadata=metadata
        )
        
        # Dispatch to all handlers asynchronously
        tasks = []
        
        # External webhook
        if self.webhook_url:
            tasks.append(self._send_webhook(event))
        
        # Internal handlers (e.g., WebSocket)
        async with self._handlers_lock:
            handlers_copy = self.internal_handlers.copy()
        
        for handler in handlers_copy:
            tasks.append(self._call_handler(handler, event))
        
        # Run all tasks concurrently
        if tasks:
            logger.info(f"Running {len(tasks)} webhook tasks")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Task {i} failed: {result}")
                else:
                    logger.info(f"Task {i} completed successfully")
    
    async def _send_webhook(self, event: NodeAccessEvent):
        """Send webhook to external URL."""
        try:
            response = await self.client.post(
                self.webhook_url,
                json=event.model_dump(mode='json'),
                headers={"Content-Type": "application/json"}
            )
            if response.status_code >= 400:
                logger.error(f"Webhook failed with status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
    
    async def _call_handler(self, handler, event: NodeAccessEvent):
        """Call an internal handler."""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as e:
            logger.error(f"Internal handler failed: {e}")
    
    async def close(self):
        """Clean up resources."""
        await self.client.aclose()


# Global webhook service instance
webhook_service = WebhookService()