"""
Webhook service for emitting events when nodes are accessed or data is ingested.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
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


class DataIngestionEvent(BaseModel):
    """Event emitted when data is ingested into the graph."""
    event_type: str = "data_ingestion"
    operation: str  # "add_episode", "add_entity", "update_entity", "bulk_ingest"
    timestamp: datetime
    group_id: Optional[str] = None
    episode: Optional[Dict[str, Any]] = None  # Serialized EpisodicNode
    nodes: List[Dict[str, Any]] = []  # Serialized EntityNodes
    edges: List[Dict[str, Any]] = []  # Serialized EntityEdges
    metadata: Optional[dict] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


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
    
    async def emit_data_ingestion(
        self,
        operation: str,
        nodes: List[Any],
        edges: List[Any],
        episode: Optional[Any] = None,
        group_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ):
        """Emit a data ingestion event when new data is added to the graph."""
        # Get data webhook URLs from environment
        data_webhook_urls = os.getenv("GRAPHITI_DATA_WEBHOOK_URLS", "")
        
        if not data_webhook_urls:
            logger.debug("No data webhook URLs configured, skipping data ingestion webhook")
            return
        
        # Serialize entities to dictionaries
        serialized_nodes = []
        for node in nodes:
            if hasattr(node, 'model_dump'):
                serialized_nodes.append(node.model_dump(mode='json'))
            elif hasattr(node, 'dict'):
                serialized_nodes.append(node.dict())
            else:
                serialized_nodes.append(dict(node))
        
        serialized_edges = []
        for edge in edges:
            if hasattr(edge, 'model_dump'):
                serialized_edges.append(edge.model_dump(mode='json'))
            elif hasattr(edge, 'dict'):
                serialized_edges.append(edge.dict())
            else:
                serialized_edges.append(dict(edge))
        
        serialized_episode = None
        if episode:
            if hasattr(episode, 'model_dump'):
                serialized_episode = episode.model_dump(mode='json')
            elif hasattr(episode, 'dict'):
                serialized_episode = episode.dict()
            else:
                serialized_episode = dict(episode)
        
        event = DataIngestionEvent(
            operation=operation,
            timestamp=datetime.now(timezone.utc),
            group_id=group_id,
            episode=serialized_episode,
            nodes=serialized_nodes,
            edges=serialized_edges,
            metadata=metadata
        )
        
        # Send to each configured webhook URL
        webhook_urls = [url.strip() for url in data_webhook_urls.split(',') if url.strip()]
        tasks = []
        
        for url in webhook_urls:
            tasks.append(self._send_data_webhook(url, event))
        
        if tasks:
            logger.info(f"Sending data ingestion webhooks to {len(tasks)} endpoints")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Data webhook to {webhook_urls[i]} failed: {result}")
                else:
                    logger.info(f"Data webhook to {webhook_urls[i]} succeeded")
    
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
    
    async def _send_data_webhook(self, url: str, event: DataIngestionEvent):
        """Send data ingestion webhook to a specific URL."""
        try:
            response = await self.client.post(
                url,
                json=event.model_dump(mode='json'),
                headers={"Content-Type": "application/json"}
            )
            if response.status_code >= 400:
                logger.error(f"Data webhook to {url} failed with status {response.status_code}: {response.text}")
                raise Exception(f"HTTP {response.status_code}")
            logger.debug(f"Data webhook sent successfully to {url}")
        except httpx.TimeoutException:
            logger.error(f"Data webhook to {url} timed out")
            raise
        except Exception as e:
            logger.error(f"Failed to send data webhook to {url}: {e}")
            raise
    
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