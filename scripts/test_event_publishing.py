#!/usr/bin/env python3
"""
Test script for GRAPH-106: Event publishing integration.

This script tests that the ChangeEventPublisher can publish events
to Redis Streams when nodes/edges are created.
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis
from graphiti_core.events import ChangeEventPublisher, ChangeAction


async def test_event_publishing():
    """Test that events can be published to Redis Streams."""

    # Connect to FalkorDB Redis
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    print(f'Connecting to Redis at {redis_url}...')

    try:
        redis_client = aioredis.from_url(redis_url)
        await redis_client.ping()
        print('✓ Redis connection successful')
    except Exception as e:
        print(f'✗ Failed to connect to Redis: {e}')
        return False

    # Create publisher
    publisher = ChangeEventPublisher(redis_client)
    print(f'✓ Publisher initialized (enabled={publisher.is_enabled})')

    if not publisher.is_enabled:
        print('✗ Publisher is not enabled')
        return False

    # Create a mock node for testing
    class MockNode:
        uuid = 'test-node-uuid-12345'
        group_id = 'test-group'
        name = 'Test Entity'
        summary = 'A test entity for event publishing'

        def model_dump(self, exclude=None):
            data = {
                'uuid': self.uuid,
                'group_id': self.group_id,
                'name': self.name,
                'summary': self.summary,
            }
            if exclude:
                for key in exclude:
                    data.pop(key, None)
            return data

    # Create a mock edge for testing
    class MockEdge:
        uuid = 'test-edge-uuid-67890'
        group_id = 'test-group'
        source_node_uuid = 'source-123'
        target_node_uuid = 'target-456'
        fact = 'Test relationship fact'

        def model_dump(self, exclude=None):
            data = {
                'uuid': self.uuid,
                'group_id': self.group_id,
                'source_node_uuid': self.source_node_uuid,
                'target_node_uuid': self.target_node_uuid,
                'fact': self.fact,
            }
            if exclude:
                for key in exclude:
                    data.pop(key, None)
            return data

    # Test publishing a node change
    print('\nTesting node change publishing...')
    node = MockNode()
    entry_id = await publisher.publish_node_change(ChangeAction.CREATE, node)
    if entry_id:
        print(f'✓ Node change published: {entry_id}')
    else:
        print('✗ Failed to publish node change')
        return False

    # Test publishing an edge change
    print('\nTesting edge change publishing...')
    edge = MockEdge()
    entry_id = await publisher.publish_edge_change(ChangeAction.CREATE, edge)
    if entry_id:
        print(f'✓ Edge change published: {entry_id}')
    else:
        print('✗ Failed to publish edge change')
        return False

    # Test bulk publishing
    print('\nTesting bulk change publishing...')
    count = await publisher.publish_bulk_changes(
        ChangeAction.CREATE, nodes=[MockNode(), MockNode()], edges=[MockEdge()], include_data=False
    )
    print(f'✓ Bulk changes published: {count} events')

    # Verify events are in the stream
    print('\nVerifying events in stream...')
    stream_info = await redis_client.xinfo_stream(ChangeEventPublisher.STREAM_KEY)
    print(f'✓ Stream length: {stream_info["length"]}')
    print(f'✓ First entry: {stream_info.get("first-entry", "N/A")}')
    print(f'✓ Last entry: {stream_info.get("last-entry", "N/A")}')

    # Read some events
    print('\nReading last 5 events...')
    events = await redis_client.xrevrange(ChangeEventPublisher.STREAM_KEY, count=5)
    for event_id, data in events:
        print(
            f'  {event_id}: {data.get(b"action", b"?").decode()} {data.get(b"entity_type", b"?").decode()} {data.get(b"uuid", b"?").decode()}'
        )

    await redis_client.aclose()
    print('\n✓ All tests passed!')
    return True


if __name__ == '__main__':
    success = asyncio.run(test_event_publishing())
    sys.exit(0 if success else 1)
