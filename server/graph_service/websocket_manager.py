"""
WebSocket connection manager for broadcasting real-time events.
Handles client connections and broadcasts node access events.
"""

import json
import logging
from typing import Set, List, Optional, Dict, Any
from fastapi import WebSocket
from datetime import datetime, timezone
import asyncio
from enum import Enum

from graph_service.webhooks import NodeAccessEvent, DataIngestionEvent

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Types of notifications sent via WebSocket."""
    NODE_ACCESS = "node_access"
    GRAPH_NOTIFICATION = "graph:notification"
    DATA_ADDED = "data:added"
    DATA_UPDATED = "data:updated"
    DATA_REMOVED = "data:removed"


class GraphOperation(str, Enum):
    """Types of graph operations."""
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    BULK_INSERT = "bulk_insert"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"


class EntityType(str, Enum):
    """Types of graph entities."""
    NODE = "node"
    EDGE = "edge"
    EPISODE = "episode"


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""
    
    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._sequence_counter = 0
        self._sequence_lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        """Send a message to a specific WebSocket."""
        try:
            await asyncio.wait_for(websocket.send_text(message), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("Timeout sending message to client - slow consumer")
            await self.disconnect(websocket)
        except Exception as e:
            logger.error(f"Error sending message to client: {e}")
            await self.disconnect(websocket)
    
    async def broadcast(self, message: str) -> None:
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return
        
        # Create a copy of connections to avoid modification during iteration
        async with self._lock:
            connections = list(self.active_connections)
        
        # Send to all connections concurrently with timeout
        disconnected = []
        tasks = []
        for connection in connections:
            try:
                # Wrap each send in a timeout
                task = asyncio.create_task(
                    asyncio.wait_for(connection.send_text(message), timeout=5.0)
                )
                tasks.append((connection, task))
            except Exception as e:
                logger.error(f"Error preparing broadcast: {e}")
                disconnected.append(connection)
        
        # Execute all sends concurrently
        if tasks:
            for connection, task in tasks:
                try:
                    await task
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout broadcasting to client - slow consumer")
                    disconnected.append(connection)
                except Exception as e:
                    logger.error(f"Error broadcasting to client: {e}")
                    disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            await self.disconnect(connection)
        
        if disconnected:
            logger.info(f"Removed {len(disconnected)} disconnected clients")
    
    async def _get_next_sequence(self) -> int:
        """Get the next sequence number for ordering notifications."""
        async with self._sequence_lock:
            self._sequence_counter += 1
            return self._sequence_counter
    
    async def broadcast_node_access(self, event: NodeAccessEvent) -> None:
        """Broadcast a node access event to all connected clients.
        
        NOTE: This now sends ONLY notification, not the actual data.
        Clients should query the backend for the actual node data.
        """
        sequence = await self._get_next_sequence()
        message = {
            "type": NotificationType.NODE_ACCESS,
            "node_ids": event.node_ids,
            "timestamp": event.timestamp.isoformat(),
            "access_type": event.access_type,
            "query": event.query,
            "sequence": sequence
        }
        logger.info(f"Broadcasting node access notification: {len(event.node_ids)} nodes, type: {event.access_type}, seq: {sequence}")
        await self.broadcast(json.dumps(message))
    
    async def broadcast_graph_notification(
        self,
        operation: GraphOperation,
        entity_type: EntityType,
        entity_ids: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Broadcast a graph change notification to all connected clients.
        
        This sends ONLY a notification about what changed, not the actual data.
        Clients should query the backend API to fetch the actual changes.
        
        Args:
            operation: Type of operation (insert, update, delete)
            entity_type: Type of entity (node, edge, episode)
            entity_ids: List of affected entity IDs
            metadata: Optional metadata about the change
        """
        sequence = await self._get_next_sequence()
        message = {
            "type": NotificationType.GRAPH_NOTIFICATION,
            "operation": operation.value,
            "entity_type": entity_type.value,
            "entity_ids": entity_ids,
            "sequence": sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {}
        }
        
        logger.info(
            f"Broadcasting graph notification: {operation.value} {len(entity_ids)} {entity_type.value}(s), seq: {sequence}"
        )
        await self.broadcast(json.dumps(message))
    
    async def broadcast_data_ingestion_notification(self, event: DataIngestionEvent) -> None:
        """Broadcast a notification when data is ingested into the graph.
        
        This sends ONLY a notification about what was ingested, not the actual data.
        Clients should query the backend API to fetch the actual data.
        
        Args:
            event: Data ingestion event with operation details
        """
        # Determine operation type
        operation = GraphOperation.INSERT
        if "update" in event.operation.lower():
            operation = GraphOperation.UPDATE
        elif "bulk" in event.operation.lower():
            operation = GraphOperation.BULK_INSERT
        
        # Extract entity IDs
        node_ids = [node.get("uuid", node.get("id", "")) for node in event.nodes if node]
        edge_ids = [f"{edge.get('source_node_id')}-{edge.get('target_node_id')}" 
                   for edge in event.edges if edge]
        
        # Send separate notifications for nodes and edges
        if node_ids:
            await self.broadcast_graph_notification(
                operation=operation,
                entity_type=EntityType.NODE,
                entity_ids=node_ids,
                metadata={
                    "group_id": event.group_id,
                    "operation": event.operation
                }
            )
        
        if edge_ids:
            await self.broadcast_graph_notification(
                operation=operation,
                entity_type=EntityType.EDGE,
                entity_ids=edge_ids,
                metadata={
                    "group_id": event.group_id,
                    "operation": event.operation
                }
            )
        
        if event.episode:
            episode_id = event.episode.get("uuid", event.episode.get("id", ""))
            if episode_id:
                await self.broadcast_graph_notification(
                    operation=operation,
                    entity_type=EntityType.EPISODE,
                    entity_ids=[episode_id],
                    metadata={
                        "group_id": event.group_id,
                        "operation": event.operation
                    }
                )
    
    async def handle_client_message(self, websocket: WebSocket, data: str) -> None:
        """Handle incoming messages from a client."""
        try:
            message = json.loads(data)
            message_type = message.get("type")
            
            if message_type == "ping":
                # Respond to ping with pong
                await self.send_personal_message(
                    json.dumps({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}),
                    websocket
                )
            elif message_type == "subscribe":
                # Client subscription acknowledged
                client_id = message.get("client_id", "unknown")
                logger.info(f"Client {client_id} subscribed")
                await self.send_personal_message(
                    json.dumps({
                        "type": "subscription_confirmed",
                        "client_id": client_id,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }),
                    websocket
                )
            else:
                logger.warning(f"Unknown message type: {message_type}")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {data}")
        except Exception as e:
            logger.error(f"Error handling client message: {e}")


# Global connection manager instance
manager = ConnectionManager()