from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graphiti_core.utils.consolidation.activities import (
    ConsolidationActivities,
    ConsolidationResult,
    EnrichResult,
)


def _build_activities(mock_graphiti: MagicMock) -> ConsolidationActivities:
    activities = ConsolidationActivities(graphiti_factory=AsyncMock())
    activities._get_graphiti = AsyncMock(return_value=mock_graphiti)
    return activities


def test_enrich_result_dataclass() -> None:
    result = EnrichResult(
        processed_count=5,
        updated_count=3,
        category='entity_summaries',
        details={'batch_size': 50},
        duration_ms=123,
    )

    data = asdict(result)
    assert data['processed_count'] == 5
    assert data['updated_count'] == 3
    assert data['category'] == 'entity_summaries'
    assert data['details'] == {'batch_size': 50}
    assert data['duration_ms'] == 123


def test_consolidation_result_has_enrich_results() -> None:
    assert 'enrich_results' in ConsolidationResult.__dataclass_fields__

    result = ConsolidationResult(
        run_id='run-1',
        started_at='2026-02-25T00:00:00+00:00',
        completed_at='2026-02-25T00:01:00+00:00',
        pre_metrics={'entity_nodes': 1},
        post_metrics={'entity_nodes': 1},
        prune_results=[],
        merge_results=[],
        enrich_results=[{'category': 'centrality', 'updated_count': 1}],
        total_duration_ms=1000,
    )
    assert result.enrich_results[0]['category'] == 'centrality'


@pytest.mark.asyncio
async def test_regenerate_summaries_no_entities() -> None:
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([], [], None))
    mock_graphiti = MagicMock()
    mock_graphiti.driver = mock_driver
    mock_graphiti.llm_client = MagicMock()

    activities = _build_activities(mock_graphiti)
    result = await activities.regenerate_entity_summaries(batch_size=25)

    assert isinstance(result, EnrichResult)
    assert result.category == 'entity_summaries'
    assert result.processed_count == 0
    assert result.updated_count == 0


@pytest.mark.asyncio
async def test_regenerate_summaries_with_entities() -> None:
    records = [
        {
            'uuid': 'u1',
            'name': 'Entity One',
            'labels': ['Person'],
            'facts': ['Fact one', 'Fact two'],
        },
        {
            'uuid': 'u2',
            'name': 'Entity Two',
            'labels': ['Company'],
            'facts': ['Fact three'],
        },
    ]

    async def query_side_effect(query: str, **kwargs):
        if 'RETURN n.uuid AS uuid, n.name AS name, n.labels AS labels, facts' in query:
            if query_side_effect.called:
                return ([], [], None)
            query_side_effect.called = True
            return (records, [], None)
        if 'SET n.summary = $summary' in query:
            return ([], [], None)
        return ([], [], None)

    query_side_effect.called = False

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(side_effect=query_side_effect)
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(return_value='Generated entity summary')
    mock_graphiti = MagicMock()
    mock_graphiti.driver = mock_driver
    mock_graphiti.llm_client = mock_llm

    activities = _build_activities(mock_graphiti)
    result = await activities.regenerate_entity_summaries(batch_size=10)

    assert result.processed_count == 2
    assert result.updated_count == 2
    assert result.category == 'entity_summaries'

    set_calls = [
        call
        for call in mock_driver.execute_query.call_args_list
        if 'SET n.summary = $summary' in call.args[0]
    ]
    assert len(set_calls) == 2


@pytest.mark.asyncio
async def test_backfill_embeddings_no_missing() -> None:
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([], [], None))
    mock_embedder = MagicMock()
    mock_embedder.create_batch = AsyncMock(return_value=[])
    mock_graphiti = MagicMock()
    mock_graphiti.driver = mock_driver
    mock_graphiti.embedder = mock_embedder

    activities = _build_activities(mock_graphiti)
    result = await activities.backfill_entity_embeddings(batch_size=30)

    assert isinstance(result, EnrichResult)
    assert result.category == 'entity_embeddings'
    assert result.processed_count == 0
    assert result.updated_count == 0


@pytest.mark.asyncio
async def test_backfill_embeddings_with_missing() -> None:
    records = [
        {'uuid': 'u1', 'name': 'Alpha'},
        {'uuid': 'u2', 'name': 'Beta'},
    ]

    async def query_side_effect(query: str, **kwargs):
        if 'WHERE n.name_embedding IS NULL' in query:
            if query_side_effect.called:
                return ([], [], None)
            query_side_effect.called = True
            return (records, [], None)
        if 'SET n.name_embedding = vecf32([' in query:
            return ([], [], None)
        return ([], [], None)

    query_side_effect.called = False

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(side_effect=query_side_effect)
    mock_embedder = MagicMock()
    mock_embedder.create_batch = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
    mock_graphiti = MagicMock()
    mock_graphiti.driver = mock_driver
    mock_graphiti.embedder = mock_embedder

    activities = _build_activities(mock_graphiti)
    result = await activities.backfill_entity_embeddings(batch_size=100)

    assert result.category == 'entity_embeddings'
    assert result.processed_count == 2
    assert result.updated_count == 2

    vec_calls = [
        call
        for call in mock_driver.execute_query.call_args_list
        if 'SET n.name_embedding = vecf32([' in call.args[0]
    ]
    assert len(vec_calls) == 2


@pytest.mark.asyncio
async def test_recalculate_centrality_calls_function() -> None:
    mock_graphiti = MagicMock()
    mock_graphiti.driver = MagicMock()
    activities = _build_activities(mock_graphiti)

    mocked_scores = {
        'u1': {'pagerank': 0.1, 'degree': 1, 'betweenness': 0.0, 'importance': 0.2},
        'u2': {'pagerank': 0.2, 'degree': 2, 'betweenness': 0.1, 'importance': 0.4},
    }

    with patch(
        'graphiti_core.utils.maintenance.centrality_operations.calculate_all_centralities',
        new=AsyncMock(return_value=mocked_scores),
    ) as mock_calc:
        result = await activities.recalculate_centrality()

    mock_calc.assert_awaited_once_with(
        driver=mock_graphiti.driver,
        group_id=None,
        store_results=True,
    )
    assert result.category == 'centrality'
    assert result.processed_count == 2
    assert result.updated_count == 2


@pytest.mark.asyncio
async def test_enrich_result_categories() -> None:
    summary_driver = MagicMock()
    summary_driver.execute_query = AsyncMock(return_value=([], [], None))
    summary_graphiti = MagicMock()
    summary_graphiti.driver = summary_driver
    summary_graphiti.llm_client = MagicMock()
    summary_result = await _build_activities(summary_graphiti).regenerate_entity_summaries()

    embedding_driver = MagicMock()
    embedding_driver.execute_query = AsyncMock(return_value=([], [], None))
    embedding_graphiti = MagicMock()
    embedding_graphiti.driver = embedding_driver
    embedding_graphiti.embedder = MagicMock()
    embedding_graphiti.embedder.create_batch = AsyncMock(return_value=[])
    embedding_result = await _build_activities(embedding_graphiti).backfill_entity_embeddings()

    centrality_graphiti = MagicMock()
    centrality_graphiti.driver = MagicMock()
    with patch(
        'graphiti_core.utils.maintenance.centrality_operations.calculate_all_centralities',
        new=AsyncMock(return_value={}),
    ):
        centrality_result = await _build_activities(centrality_graphiti).recalculate_centrality()

    assert summary_result.category == 'entity_summaries'
    assert embedding_result.category == 'entity_embeddings'
    assert centrality_result.category == 'centrality'
