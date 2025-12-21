"""
GRAPH-105: Change Event Publisher for Real-time Sync

This module provides event publishing capabilities for Graphiti mutations,
enabling real-time change propagation via Redis Streams.

The ChangeEventPublisher publishes events when nodes/edges are created,
updated, or deleted. Consumers (like the Rust visualizer) can subscribe
to these events for real-time updates without polling.

Usage:
    publisher = ChangeEventPublisher(redis_client)
    await publisher.publish_node_change("create", node)
    await publisher.publish_edge_change("update", edge)
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ChangeAction(str, Enum):
    """Type of change action."""

    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'


class EntityType(str, Enum):
    """Type of entity being changed."""

    NODE = 'node'
    EDGE = 'edge'
    EPISODE = 'episode'


class ChangeEvent(BaseModel):
    """A change event to be published to Redis Streams."""

    action: ChangeAction
    entity_type: EntityType
    uuid: str
    group_id: str
    timestamp: str
    data: dict[str, Any] | None = None

    def to_stream_dict(self) -> dict[str, str]:
        """Convert to dict suitable for Redis XADD."""
        result = {
            'action': self.action.value,
            'entity_type': self.entity_type.value,
            'uuid': self.uuid,
            'group_id': self.group_id,
            'timestamp': self.timestamp,
        }
        if self.data:
            result['data'] = json.dumps(self.data, default=str)
        return result


class RedisClientProtocol(Protocol):
    """Protocol for Redis client compatibility."""

    async def xadd(
        self, name: str, fields: dict[str, str], maxlen: int | None = None, approximate: bool = True
    ) -> str: ...

    async def ping(self) -> bool: ...


class ChangeEventPublisher:
    """
    Publishes change events to Redis Streams for real-time sync.

    Events are published to the stream 'graphiti:changes' with the following fields:
    - action: create, update, delete
    - entity_type: node, edge, episode
    - uuid: entity UUID
    - group_id: graph partition
    - timestamp: ISO format timestamp
    - data: JSON-encoded entity data (optional, for create/update)

    The stream is capped at 100,000 entries (rolling window) to prevent
    unbounded memory growth.
    """

    STREAM_KEY = 'graphiti:changes'
    MAX_STREAM_LEN = 100000  # Rolling window size

    def __init__(self, redis_client: Any = None, enabled: bool = True):
        """
        Initialize the publisher.

        Args:
            redis_client: Async Redis client instance. If None, publishing is disabled.
            enabled: Whether to actually publish events. Useful for testing.
        """
        self._redis = redis_client
        self._enabled = enabled and redis_client is not None

        if self._enabled:
            logger.info(f'ChangeEventPublisher initialized with stream: {self.STREAM_KEY}')
        else:
            logger.info('ChangeEventPublisher disabled (no Redis client or explicitly disabled)')

    @property
    def is_enabled(self) -> bool:
        """Check if publishing is enabled."""
        return self._enabled

    async def _publish(self, event: ChangeEvent) -> str | None:
        """
        Publish an event to the Redis stream.

        Returns:
            The stream entry ID if successful, None otherwise.
        """
        if not self._enabled:
            return None

        try:
            entry_id = await self._redis.xadd(
                self.STREAM_KEY,
                event.to_stream_dict(),
                maxlen=self.MAX_STREAM_LEN,
                approximate=True,  # Use ~ for performance
            )
            logger.debug(
                f'Published {event.action.value} event for {event.entity_type.value} '
                f'{event.uuid} -> {entry_id}'
            )
            return entry_id
        except Exception as e:
            logger.warning(f'Failed to publish change event: {e}')
            return None

    async def publish_node_change(
        self, action: ChangeAction | str, node: Any, include_data: bool = True
    ) -> str | None:
        """
        Publish a node change event.

        Args:
            action: The change action (create, update, delete)
            node: The node object (must have uuid, group_id, and optionally dict()/model_dump())
            include_data: Whether to include node data in the event

        Returns:
            The stream entry ID if successful, None otherwise.
        """
        if isinstance(action, str):
            action = ChangeAction(action)

        # Extract data from node
        data = None
        if include_data and action != ChangeAction.DELETE:
            if hasattr(node, 'model_dump'):
                data = node.model_dump(exclude={'name_embedding'})
            elif hasattr(node, 'dict'):
                data = node.dict(exclude={'name_embedding'})
            elif isinstance(node, dict):
                data = {k: v for k, v in node.items() if k != 'name_embedding'}

        # Extract uuid and group_id from node (handles both objects and dicts)
        if isinstance(node, dict):
            node_uuid = node.get('uuid', '')
            node_group_id = node.get('group_id', '')
        else:
            node_uuid = getattr(node, 'uuid', '')
            node_group_id = getattr(node, 'group_id', '')

        event = ChangeEvent(
            action=action,
            entity_type=EntityType.NODE,
            uuid=node_uuid,
            group_id=node_group_id,
            timestamp=datetime.utcnow().isoformat(),
            data=data,
        )

        return await self._publish(event)

    async def publish_edge_change(
        self, action: ChangeAction | str, edge: Any, include_data: bool = True
    ) -> str | None:
        """
        Publish an edge change event.

        Args:
            action: The change action (create, update, delete)
            edge: The edge object (must have uuid, group_id)
            include_data: Whether to include edge data in the event

        Returns:
            The stream entry ID if successful, None otherwise.
        """
        if isinstance(action, str):
            action = ChangeAction(action)

        # Extract data from edge
        data = None
        if include_data and action != ChangeAction.DELETE:
            if hasattr(edge, 'model_dump'):
                data = edge.model_dump(exclude={'fact_embedding'})
            elif hasattr(edge, 'dict'):
                data = edge.dict(exclude={'fact_embedding'})
            elif isinstance(edge, dict):
                data = {k: v for k, v in edge.items() if k != 'fact_embedding'}

        # Extract uuid and group_id from edge (handles both objects and dicts)
        if isinstance(edge, dict):
            edge_uuid = edge.get('uuid', '')
            edge_group_id = edge.get('group_id', '')
        else:
            edge_uuid = getattr(edge, 'uuid', '')
            edge_group_id = getattr(edge, 'group_id', '')

        event = ChangeEvent(
            action=action,
            entity_type=EntityType.EDGE,
            uuid=edge_uuid,
            group_id=edge_group_id,
            timestamp=datetime.utcnow().isoformat(),
            data=data,
        )

        return await self._publish(event)

    async def publish_episode_change(
        self,
        action: ChangeAction | str,
        episode: Any,
        include_data: bool = False,  # Episodes can be large, default to not including
    ) -> str | None:
        """
        Publish an episode change event.

        Args:
            action: The change action (create, update, delete)
            episode: The episode object (must have uuid, group_id)
            include_data: Whether to include episode data (default False due to size)

        Returns:
            The stream entry ID if successful, None otherwise.
        """
        if isinstance(action, str):
            action = ChangeAction(action)

        # Extract minimal data from episode
        data = None
        if include_data and action != ChangeAction.DELETE:
            if hasattr(episode, 'model_dump'):
                data = episode.model_dump(exclude={'content'})  # Exclude large content
            elif hasattr(episode, 'dict'):
                data = episode.dict(exclude={'content'})
            elif isinstance(episode, dict):
                data = {k: v for k, v in episode.items() if k != 'content'}

        # Extract uuid and group_id from episode (handles both objects and dicts)
        if isinstance(episode, dict):
            episode_uuid = episode.get('uuid', '')
            episode_group_id = episode.get('group_id', '')
        else:
            episode_uuid = getattr(episode, 'uuid', '')
            episode_group_id = getattr(episode, 'group_id', '')

        event = ChangeEvent(
            action=action,
            entity_type=EntityType.EPISODE,
            uuid=episode_uuid,
            group_id=episode_group_id,
            timestamp=datetime.utcnow().isoformat(),
            data=data,
        )

        return await self._publish(event)

    async def publish_bulk_changes(
        self,
        action: ChangeAction | str,
        nodes: list[Any] | None = None,
        edges: list[Any] | None = None,
        include_data: bool = False,  # Default False for bulk operations
    ) -> int:
        """
        Publish multiple change events efficiently.

        Args:
            action: The change action for all entities
            nodes: List of node objects
            edges: List of edge objects
            include_data: Whether to include entity data

        Returns:
            Number of events successfully published.
        """
        if not self._enabled:
            return 0

        count = 0

        if nodes:
            for node in nodes:
                if await self.publish_node_change(action, node, include_data):
                    count += 1

        if edges:
            for edge in edges:
                if await self.publish_edge_change(action, edge, include_data):
                    count += 1

        logger.info(f'Published {count} bulk change events (action={action})')
        return count


# Singleton instance for convenience (initialized lazily)
_default_publisher: ChangeEventPublisher | None = None


def get_event_publisher() -> ChangeEventPublisher | None:
    """Get the default event publisher singleton."""
    return _default_publisher


def set_event_publisher(publisher: ChangeEventPublisher) -> None:
    """Set the default event publisher singleton."""
    global _default_publisher
    _default_publisher = publisher
