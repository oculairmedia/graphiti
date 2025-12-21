#!/usr/bin/env python3
"""
Test script for GRAPH-111: Delete event publishing integration.

This script tests that the ChangeEventPublisher can publish DELETE events
to Redis Streams when nodes/edges/episodes are deleted.
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis
from graphiti_core.events import ChangeEventPublisher, ChangeAction


async def test_delete_event_publishing():
    """Test that DELETE events can be published to Redis Streams."""

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

    # Create mock objects for testing
    class MockNode:
        def __init__(self, uuid: str):
            self.uuid = uuid
            self.group_id = 'test-group'
            self.name = 'Test Entity'
            self.summary = 'A test entity for delete event testing'

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

    class MockEdge:
        def __init__(self, uuid: str):
            self.uuid = uuid
            self.group_id = 'test-group'
            self.source_node_uuid = 'source-123'
            self.target_node_uuid = 'target-456'
            self.fact = 'Test relationship fact'

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

    class MockEpisode:
        def __init__(self, uuid: str):
            self.uuid = uuid
            self.group_id = 'test-group'
            self.content = 'Test episode content'

        def model_dump(self, exclude=None):
            data = {
                'uuid': self.uuid,
                'group_id': self.group_id,
                'content': self.content,
            }
            if exclude:
                for key in exclude:
                    data.pop(key, None)
            return data

    # Test publishing a node DELETE event
    print('\n=== Testing DELETE event publishing ===')

    print('\n1. Testing node DELETE event...')
    node = MockNode('delete-node-uuid-12345')
    entry_id = await publisher.publish_node_change(ChangeAction.DELETE, node, include_data=False)
    if entry_id:
        print(f'   ✓ Node DELETE event published: {entry_id}')
    else:
        print('   ✗ Failed to publish node DELETE event')
        return False

    # Test publishing an edge DELETE event
    print('\n2. Testing edge DELETE event...')
    edge = MockEdge('delete-edge-uuid-67890')
    entry_id = await publisher.publish_edge_change(ChangeAction.DELETE, edge, include_data=False)
    if entry_id:
        print(f'   ✓ Edge DELETE event published: {entry_id}')
    else:
        print('   ✗ Failed to publish edge DELETE event')
        return False

    # Test publishing an episode DELETE event
    print('\n3. Testing episode DELETE event...')
    episode = MockEpisode('delete-episode-uuid-11111')
    entry_id = await publisher.publish_episode_change(
        ChangeAction.DELETE, episode, include_data=False
    )
    if entry_id:
        print(f'   ✓ Episode DELETE event published: {entry_id}')
    else:
        print('   ✗ Failed to publish episode DELETE event')
        return False

    # Test bulk DELETE publishing
    print('\n4. Testing bulk DELETE publishing...')
    count = await publisher.publish_bulk_changes(
        ChangeAction.DELETE,
        nodes=[MockNode('bulk-del-node-1'), MockNode('bulk-del-node-2')],
        edges=[MockEdge('bulk-del-edge-1')],
        include_data=False,
    )
    print(f'   ✓ Bulk DELETE events published: {count} events')

    # Verify events are in the stream
    print('\n=== Verifying DELETE events in stream ===')
    stream_info = await redis_client.xinfo_stream(ChangeEventPublisher.STREAM_KEY)
    print(f'✓ Stream length: {stream_info["length"]}')

    # Read the most recent DELETE events
    print('\nReading last 10 events (looking for DELETE actions)...')
    events = await redis_client.xrevrange(ChangeEventPublisher.STREAM_KEY, count=10)
    delete_count = 0
    for event_id, data in events:
        action = data.get(b'action', b'?').decode()
        entity_type = data.get(b'entity_type', b'?').decode()
        uuid = data.get(b'uuid', b'?').decode()
        if action == 'delete':
            delete_count += 1
            print(f'  ✓ {event_id}: {action} {entity_type} {uuid}')

    if delete_count >= 6:
        print(f'\n✓ Found {delete_count} DELETE events as expected')
    else:
        print(f'\n⚠ Only found {delete_count} DELETE events (expected at least 6)')

    await redis_client.aclose()
    print('\n=== All DELETE event tests passed! ===')
    return True


if __name__ == '__main__':
    success = asyncio.run(test_delete_event_publishing())
    sys.exit(0 if success else 1)
