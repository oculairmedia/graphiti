from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from graphiti_core.edges import EntityEdge, create_entity_edge_embeddings


def _edge(
    fact: str,
    fact_embedding: list[float] | None,
    source_uuid: str,
    target_uuid: str,
) -> EntityEdge:
    return EntityEdge(
        source_node_uuid=source_uuid,
        target_node_uuid=target_uuid,
        name='RELATES_TO',
        group_id='test_group',
        fact=fact,
        fact_embedding=fact_embedding,
        episodes=['11111111-1111-1111-1111-111111111111'],
        created_at=datetime.now(timezone.utc),
        valid_at=None,
        invalid_at=None,
    )


@pytest.mark.asyncio
async def test_create_entity_edge_embeddings_empty_input() -> None:
    embedder = MagicMock()
    embedder.create_batch = AsyncMock(return_value=[])

    await create_entity_edge_embeddings(embedder, [], skip_existing=True)

    embedder.create_batch.assert_not_called()


@pytest.mark.asyncio
async def test_create_entity_edge_embeddings_skip_existing_false_embeds_all() -> None:
    edge_a = _edge(
        'fact-a',
        [0.9],
        '11111111-1111-1111-1111-111111111111',
        '22222222-2222-2222-2222-222222222222',
    )
    edge_b = _edge(
        'fact-b',
        None,
        '33333333-3333-3333-3333-333333333333',
        '44444444-4444-4444-4444-444444444444',
    )

    embedder = MagicMock()
    embedder.create_batch = AsyncMock(return_value=[[1.1], [2.2]])

    await create_entity_edge_embeddings(embedder, [edge_a, edge_b], skip_existing=False)

    embedder.create_batch.assert_awaited_once_with(['fact-a', 'fact-b'])
    assert edge_a.fact_embedding == [1.1]
    assert edge_b.fact_embedding == [2.2]


@pytest.mark.asyncio
async def test_create_entity_edge_embeddings_skip_existing_true_only_missing() -> None:
    edge_missing = _edge(
        'fact-missing',
        None,
        '55555555-5555-5555-5555-555555555555',
        '66666666-6666-6666-6666-666666666666',
    )
    edge_empty = _edge(
        'fact-empty',
        None,
        '77777777-7777-7777-7777-777777777777',
        '88888888-8888-8888-8888-888888888888',
    )
    edge_empty.fact_embedding = []
    edge_existing = _edge(
        'fact-existing',
        [9.9],
        '99999999-9999-9999-9999-999999999999',
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    )

    embedder = MagicMock()
    embedder.create_batch = AsyncMock(return_value=[[1.0], [2.0]])

    await create_entity_edge_embeddings(
        embedder,
        [edge_missing, edge_empty, edge_existing],
        skip_existing=True,
    )

    embedder.create_batch.assert_awaited_once_with(['fact-missing', 'fact-empty'])
    assert edge_missing.fact_embedding == [1.0]
    assert edge_empty.fact_embedding == [2.0]
    assert edge_existing.fact_embedding == [9.9]


@pytest.mark.asyncio
async def test_create_entity_edge_embeddings_skip_existing_true_no_missing() -> None:
    edge_a = _edge(
        'fact-a',
        [1.0],
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        'cccccccc-cccc-cccc-cccc-cccccccccccc',
    )
    edge_b = _edge(
        'fact-b',
        [2.0],
        'dddddddd-dddd-dddd-dddd-dddddddddddd',
        'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
    )

    embedder = MagicMock()
    embedder.create_batch = AsyncMock(return_value=[])

    await create_entity_edge_embeddings(embedder, [edge_a, edge_b], skip_existing=True)

    embedder.create_batch.assert_not_called()
