"""
WebSocket connection manager for broadcasting real-time events.
"""

import json
import logging
from typing import List, Set
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
import asyncio

from graph_service.webhooks import NodeAccessEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific WebSocket."""
        try:
            await asyncio.wait_for(websocket.send_text(message), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("Timeout sending message to client - slow consumer")
            await self.disconnect(websocket)
        except Exception as e:
            logger.error(f"Error sending message to client: {e}")
            await self.disconnect(websocket)
    
    async def broadcast(self, message: str):
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
    
    async def broadcast_node_access(self, event: NodeAccessEvent):
        """Broadcast a node access event to all connected clients."""
        message = {
            "type": "node_access",
            "node_ids": event.node_ids,
            "timestamp": event.timestamp.isoformat(),
            "access_type": event.access_type,
            "query": event.query
        }
        await self.broadcast(json.dumps(message))
    
    async def handle_client_message(self, websocket: WebSocket, data: str):
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