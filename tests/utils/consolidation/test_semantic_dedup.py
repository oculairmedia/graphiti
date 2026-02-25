from unittest.mock import AsyncMock, patch

import pytest

from graphiti_core.utils.consolidation.semantic_dedup import (
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_SIMILARITY_THRESHOLD,
    SemanticDedupActivities,
    SemanticDedupResult,
)


class TestSemanticDedupResult:
    def test_dataclass_creation(self):
        result = SemanticDedupResult(
            merged_count=5,
            edges_transferred=20,
            nodes_deleted=5,
            failed_merges=0,
            candidates_found=10,
            details={'similarity_threshold': 0.92},
            duration_ms=5000,
        )
        assert result.merged_count == 5
        assert result.candidates_found == 10

    def test_defaults(self):
        assert DEFAULT_SIMILARITY_THRESHOLD == 0.92
        assert DEFAULT_MAX_CANDIDATES == 10


class TestSemanticEntityDedup:
    @pytest.fixture
    def activities(self):
        mock_graphiti = AsyncMock()
        mock_graphiti.driver = AsyncMock()
        mock_graphiti.embedder = AsyncMock()

        async def factory():
            return mock_graphiti

        acts = SemanticDedupActivities(factory)
        return acts, mock_graphiti

    @pytest.mark.asyncio
    async def test_no_entities_returns_empty(self, activities):
        acts, mock_graphiti = activities
        mock_graphiti.driver.execute_query.return_value = ([], None, None)

        result = await acts.semantic_entity_dedup.__wrapped__(acts)
        assert result.merged_count == 0
        assert result.candidates_found == 0

    @pytest.mark.asyncio
    async def test_no_similar_candidates(self, activities):
        acts, mock_graphiti = activities
        entity_records = [{'uuid': 'entity-1', 'name': 'Python', 'embedding': [0.1, 0.2, 0.3]}]
        mock_graphiti.driver.execute_query.side_effect = [
            (entity_records, None, None),
            ([], None, None),
            ([], None, None),
        ]

        result = await acts.semantic_entity_dedup.__wrapped__(acts)
        assert result.merged_count == 0
        assert result.candidates_found == 0

    @pytest.mark.asyncio
    async def test_merges_similar_entities(self, activities):
        acts, mock_graphiti = activities

        entity_records = [
            {'uuid': 'entity-1', 'name': 'Python Language', 'embedding': [0.1, 0.2, 0.3]}
        ]
        similar_records = [
            {
                'uuid': 'entity-2',
                'name': 'Python Programming',
                'score': 0.95,
                'edge_count': 3,
                'summary_len': 50,
                'created_at': '2025-01-02',
            }
        ]
        current_stats = [{'edge_count': 5, 'summary_len': 100, 'created_at': '2025-01-01'}]
        merge_stats = {'edges_transferred': 3, 'conflicts_resolved': 0, 'nodes_deleted': 1}

        mock_graphiti.driver.execute_query.side_effect = [
            (entity_records, None, None),
            (similar_records, None, None),
            (current_stats, None, None),
            ([], None, None),
        ]

        with patch(
            'graphiti_core.utils.maintenance.node_operations.merge_node_into',
            new_callable=AsyncMock,
            return_value=merge_stats,
        ):
            result = await acts.semantic_entity_dedup.__wrapped__(acts)

        assert result.merged_count == 1
        assert result.edges_transferred == 3
        assert result.nodes_deleted == 1
        assert result.candidates_found == 1

    @pytest.mark.asyncio
    async def test_skips_already_processed(self, activities):
        acts, mock_graphiti = activities

        batch1 = [
            {'uuid': 'entity-1', 'name': 'Python', 'embedding': [0.1, 0.2, 0.3]},
            {'uuid': 'entity-2', 'name': 'Python Lang', 'embedding': [0.1, 0.2, 0.31]},
        ]
        similar_for_1 = [
            {
                'uuid': 'entity-2',
                'name': 'Python Lang',
                'score': 0.95,
                'edge_count': 3,
                'summary_len': 50,
                'created_at': '2025-01-02',
            }
        ]
        current_stats_1 = [{'edge_count': 5, 'summary_len': 100, 'created_at': '2025-01-01'}]
        merge_stats = {'edges_transferred': 3, 'nodes_deleted': 1}

        mock_graphiti.driver.execute_query.side_effect = [
            (batch1, None, None),
            (similar_for_1, None, None),
            (current_stats_1, None, None),
            ([], None, None),
        ]

        with patch(
            'graphiti_core.utils.maintenance.node_operations.merge_node_into',
            new_callable=AsyncMock,
            return_value=merge_stats,
        ):
            result = await acts.semantic_entity_dedup.__wrapped__(acts)

        assert result.merged_count == 1

    @pytest.mark.asyncio
    async def test_merge_failure_counted(self, activities):
        acts, mock_graphiti = activities

        entity_records = [{'uuid': 'entity-1', 'name': 'Test', 'embedding': [0.1, 0.2]}]
        similar_records = [
            {
                'uuid': 'entity-2',
                'name': 'Test2',
                'score': 0.95,
                'edge_count': 2,
                'summary_len': 30,
                'created_at': '2025-01-02',
            }
        ]
        current_stats = [{'edge_count': 5, 'summary_len': 100, 'created_at': '2025-01-01'}]

        mock_graphiti.driver.execute_query.side_effect = [
            (entity_records, None, None),
            (similar_records, None, None),
            (current_stats, None, None),
            ([], None, None),
        ]

        with patch(
            'graphiti_core.utils.maintenance.node_operations.merge_node_into',
            new_callable=AsyncMock,
            side_effect=Exception('Node not found'),
        ):
            result = await acts.semantic_entity_dedup.__wrapped__(acts)

        assert result.merged_count == 0
        assert result.failed_merges == 1

    @pytest.mark.asyncio
    async def test_canonical_selection_most_edges_wins(self, activities):
        acts, mock_graphiti = activities

        entity_records = [{'uuid': 'entity-1', 'name': 'Small Node', 'embedding': [0.1, 0.2]}]
        similar_records = [
            {
                'uuid': 'entity-2',
                'name': 'Big Node',
                'score': 0.95,
                'edge_count': 20,
                'summary_len': 200,
                'created_at': '2025-01-01',
            }
        ]
        current_stats = [{'edge_count': 2, 'summary_len': 10, 'created_at': '2025-01-02'}]
        merge_stats = {'edges_transferred': 2, 'nodes_deleted': 1}

        mock_graphiti.driver.execute_query.side_effect = [
            (entity_records, None, None),
            (similar_records, None, None),
            (current_stats, None, None),
            ([], None, None),
        ]

        with patch(
            'graphiti_core.utils.maintenance.node_operations.merge_node_into',
            new_callable=AsyncMock,
            return_value=merge_stats,
        ) as mock_merge:
            await acts.semantic_entity_dedup.__wrapped__(acts)

        mock_merge.assert_called_once()
        assert mock_merge.call_args.kwargs.get('canonical_uuid') == 'entity-2'
        assert mock_merge.call_args.kwargs.get('duplicate_uuid') == 'entity-1'

    def test_result_details_include_config(self):
        result = SemanticDedupResult(
            merged_count=0,
            edges_transferred=0,
            nodes_deleted=0,
            failed_merges=0,
            candidates_found=0,
            details={
                'similarity_threshold': 0.92,
                'max_candidates': 10,
                'batch_size': 100,
                'entities_scanned': 500,
            },
            duration_ms=100,
        )
        assert result.details['similarity_threshold'] == 0.92
        assert result.details['max_candidates'] == 10
