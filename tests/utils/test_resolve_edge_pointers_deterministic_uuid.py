import os
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock

import pytest  # type: ignore

from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.errors import DuplicateEdgeError
from graphiti_core.utils.bulk_utils import resolve_edge_pointers
from graphiti_core.utils.uuid_utils import generate_deterministic_edge_uuid


def test_resolve_edge_pointers_recomputes_entity_edge_uuid_when_deterministic():
    source_uuid = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    target_uuid = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
    updated_source_uuid = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
    group_id = 'test_group'

    with patch.dict(os.environ, {'USE_DETERMINISTIC_UUIDS': 'true'}):
        edge = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target_uuid,
            group_id=group_id,
            name='relates_to',
            fact='Alice relates to Bob',
            fact_embedding=None,
            episodes=[],
            created_at=datetime.now(timezone.utc),
        )

        original_uuid = edge.uuid
        expected_original_uuid = generate_deterministic_edge_uuid(
            source_uuid, target_uuid, edge.name, group_id
        )
        assert original_uuid == expected_original_uuid

        resolve_edge_pointers([edge], {source_uuid: updated_source_uuid})

        assert edge.source_node_uuid == updated_source_uuid
        assert edge.target_node_uuid == target_uuid
        assert edge.uuid != original_uuid
        assert edge.uuid == generate_deterministic_edge_uuid(
            updated_source_uuid, target_uuid, edge.name, group_id
        )


def test_resolve_edge_pointers_recomputes_episodic_edge_uuid_when_deterministic():
    episode_uuid = '11111111-1111-1111-1111-111111111111'
    entity_uuid = '22222222-2222-2222-2222-222222222222'
    updated_entity_uuid = '33333333-3333-3333-3333-333333333333'
    group_id = 'test_group'

    with patch.dict(os.environ, {'USE_DETERMINISTIC_UUIDS': 'true'}):
        edge = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=entity_uuid,
            group_id=group_id,
            created_at=datetime.now(timezone.utc),
        )

        original_uuid = edge.uuid
        expected_original_uuid = generate_deterministic_edge_uuid(
            episode_uuid, entity_uuid, 'MENTIONS', group_id
        )
        assert original_uuid == expected_original_uuid

        resolve_edge_pointers([edge], {entity_uuid: updated_entity_uuid})

        assert edge.source_node_uuid == episode_uuid
        assert edge.target_node_uuid == updated_entity_uuid
        assert edge.uuid != original_uuid
        assert edge.uuid == generate_deterministic_edge_uuid(
            episode_uuid, updated_entity_uuid, 'MENTIONS', group_id
        )


@pytest.mark.asyncio
async def test_entity_edge_save_raises_on_duplicate_uuid_different_endpoints():
    """EntityEdge.save() should raise DuplicateEdgeError if UUID exists on different endpoints."""
    edge_uuid = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
    new_source = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    new_target = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
    existing_source = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
    existing_target = 'dddddddd-dddd-dddd-dddd-dddddddddddd'

    # Mock driver that returns an existing edge with different endpoints
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(
        return_value=(
            [{'source_uuid': existing_source, 'target_uuid': existing_target}],
            None,
            None,
        )
    )

    with patch.dict(os.environ, {'USE_DETERMINISTIC_UUIDS': 'false'}):
        edge = EntityEdge(
            uuid=edge_uuid,
            source_node_uuid=new_source,
            target_node_uuid=new_target,
            group_id='test_group',
            name='relates_to',
            fact='Test fact',
            fact_embedding=None,
            episodes=[],
            created_at=datetime.now(timezone.utc),
        )

    with pytest.raises(DuplicateEdgeError) as exc_info:
        await edge.save(mock_driver)

    assert edge_uuid in str(exc_info.value)
    assert new_source in str(exc_info.value)
    assert existing_source in str(exc_info.value)


@pytest.mark.asyncio
async def test_entity_edge_save_succeeds_when_same_endpoints():
    """EntityEdge.save() should NOT raise if UUID exists on the SAME endpoints (update case)."""
    edge_uuid = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
    source = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    target = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

    # Mock driver returns existing edge with SAME endpoints
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(
        side_effect=[
            # First call: guard check - returns existing edge with same endpoints
            ([{'source_uuid': source, 'target_uuid': target}], None, None),
            # Second call: actual save
            ([{'uuid': edge_uuid}], None, None),
        ]
    )

    with patch.dict(os.environ, {'USE_DETERMINISTIC_UUIDS': 'false'}):
        edge = EntityEdge(
            uuid=edge_uuid,
            source_node_uuid=source,
            target_node_uuid=target,
            group_id='test_group',
            name='relates_to',
            fact='Test fact',
            fact_embedding=None,
            episodes=[],
            created_at=datetime.now(timezone.utc),
        )

    # Should not raise
    result = await edge.save(mock_driver)
    assert result is not None


@pytest.mark.asyncio
async def test_entity_edge_save_succeeds_when_no_existing_edge():
    """EntityEdge.save() should succeed when no existing edge with that UUID."""
    edge_uuid = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
    source = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    target = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

    # Mock driver returns empty result for guard check
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(
        side_effect=[
            # First call: guard check - no existing edge
            ([], None, None),
            # Second call: actual save
            ([{'uuid': edge_uuid}], None, None),
        ]
    )

    with patch.dict(os.environ, {'USE_DETERMINISTIC_UUIDS': 'false'}):
        edge = EntityEdge(
            uuid=edge_uuid,
            source_node_uuid=source,
            target_node_uuid=target,
            group_id='test_group',
            name='relates_to',
            fact='Test fact',
            fact_embedding=None,
            episodes=[],
            created_at=datetime.now(timezone.utc),
        )

    # Should not raise
    result = await edge.save(mock_driver)
    assert result is not None
