"""
Tests for centrality operations in Graphiti.

This module tests the graph centrality analysis functionality including:
- PageRank calculation
- Degree centrality calculation
- Betweenness centrality calculation
- Combined centrality operations
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.utils.maintenance.centrality_operations import (
    calculate_all_centralities,
    calculate_betweenness_centrality,
    calculate_degree_centrality,
    calculate_pagerank,
    store_centrality_scores,
)


def _build_execute_query_side_effect(
    node_uuids: list[str],
    *,
    total_degree: int = 2,
    node_count: int | None = None,
):
    if node_count is None:
        node_count = len(node_uuids)

    async def _side_effect(query: str, **kwargs):
        if 'count(DISTINCT e) AS total_degree' in query:
            return ([{'uuid': uuid, 'total_degree': total_degree} for uuid in node_uuids], [], None)

        if 'RETURN count(n) AS count' in query:
            return ([{'count': node_count}], [], None)

        if 'RETURN source.uuid AS source_id' in query:
            return ([], [], None)

        if 'RETURN count(e) AS out_count' in query:
            return ([{'out_count': 1}], [], None)

        if 'nodes(shortestPath' in query:
            return ([], [], None)

        if 'RETURN n.uuid AS uuid' in query:
            return ([{'uuid': uuid} for uuid in node_uuids], [], None)

        return ([], [], None)

    return _side_effect


class TestCentralityOperations:
    """Test suite for centrality operations."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock graph driver."""
        driver = MagicMock(spec=GraphDriver)
        driver.execute_query = AsyncMock()
        return driver

    @pytest.fixture
    def sample_nodes(self):
        """Create sample node data for testing."""
        return [
            {
                'uuid': str(uuid4()),
                'name': 'Node A',
                'pagerank': 0.15,
                'degree_centrality': 0.4,
                'betweenness_centrality': 0.1,
            },
            {
                'uuid': str(uuid4()),
                'name': 'Node B',
                'pagerank': 0.25,
                'degree_centrality': 0.6,
                'betweenness_centrality': 0.3,
            },
            {
                'uuid': str(uuid4()),
                'name': 'Node C',
                'pagerank': 0.10,
                'degree_centrality': 0.2,
                'betweenness_centrality': 0.05,
            },
        ]

    @pytest.mark.asyncio
    async def test_calculate_pagerank_default_params(self, mock_driver, sample_nodes):
        """Test PageRank calculation with default parameters."""
        node_uuids = [node['uuid'] for node in sample_nodes]
        mock_driver.execute_query.side_effect = _build_execute_query_side_effect(node_uuids)

        result = await calculate_pagerank(mock_driver)

        first_query = mock_driver.execute_query.call_args_list[0].args[0]
        assert 'MATCH (n)' in first_query
        assert 'RETURN n.uuid AS uuid' in first_query

        assert isinstance(result, dict)
        assert set(result.keys()) == set(node_uuids)

    @pytest.mark.asyncio
    async def test_calculate_pagerank_custom_params(self, mock_driver, sample_nodes):
        """Test PageRank calculation with custom parameters."""
        node_uuids = [node['uuid'] for node in sample_nodes]
        mock_driver.execute_query.side_effect = _build_execute_query_side_effect(node_uuids)

        result = await calculate_pagerank(mock_driver, damping_factor=0.75, iterations=50)

        assert isinstance(result, dict)
        assert set(result.keys()) == set(node_uuids)

    @pytest.mark.asyncio
    async def test_calculate_degree_centrality(self, mock_driver, sample_nodes):
        """Test degree centrality calculation."""
        mock_driver.execute_query.return_value = (
            [{'uuid': node['uuid'], 'total_degree': 2} for node in sample_nodes],
            [],
            None,
        )

        result = await calculate_degree_centrality(mock_driver)

        query = mock_driver.execute_query.call_args[0][0]
        assert 'MATCH (n)' in query
        assert 'total_degree' in query

        assert isinstance(result, dict)
        assert set(result.keys()) == {node['uuid'] for node in sample_nodes}
        assert all(result[node['uuid']]['total'] == 2 for node in sample_nodes)

    @pytest.mark.asyncio
    async def test_calculate_degree_centrality_with_filters(self, mock_driver, sample_nodes):
        """Test degree centrality with node filters."""
        mock_driver.execute_query.return_value = (
            [{'uuid': node['uuid'], 'in_degree': 3} for node in sample_nodes],
            [],
            None,
        )

        result = await calculate_degree_centrality(mock_driver, direction='in')

        query = mock_driver.execute_query.call_args[0][0]
        assert 'OPTIONAL MATCH ()-[e]->(n)' in query

        assert isinstance(result, dict)
        assert set(result.keys()) == {node['uuid'] for node in sample_nodes}
        assert all(result[node['uuid']]['in'] == 3 for node in sample_nodes)

    @pytest.mark.asyncio
    async def test_calculate_betweenness_centrality(self, mock_driver, sample_nodes):
        """Test betweenness centrality calculation."""
        node_uuids = [node['uuid'] for node in sample_nodes]
        mock_driver.execute_query.side_effect = _build_execute_query_side_effect(node_uuids)

        result = await calculate_betweenness_centrality(mock_driver)

        assert isinstance(result, dict)
        assert set(result.keys()) == set(node_uuids)

    @pytest.mark.asyncio
    async def test_calculate_betweenness_centrality_sampling(self, mock_driver, sample_nodes):
        """Test betweenness centrality with sampling."""
        node_uuids = [node['uuid'] for node in sample_nodes]
        mock_driver.execute_query.side_effect = _build_execute_query_side_effect(node_uuids)

        result = await calculate_betweenness_centrality(mock_driver, sample_size=2)

        assert isinstance(result, dict)
        assert set(result.keys()).issubset(set(node_uuids))

    @pytest.mark.asyncio
    async def test_store_centrality_scores(self, mock_driver):
        """Test storing centrality scores to nodes."""
        scores = {
            'node1': {'pagerank': 0.15, 'degree': 2, 'betweenness': 0.1},
            'node2': {'pagerank': 0.25, 'degree': 3, 'betweenness': 0.3},
        }

        with patch(
            'graphiti_core.utils.maintenance.atomic_centrality_storage.AtomicCentralityStorage'
        ) as mock_storage_class:
            mock_storage = mock_storage_class.return_value
            mock_transaction = MagicMock()
            mock_transaction.processed_nodes = 2
            mock_transaction.total_nodes = 2
            mock_transaction.transaction_id = 'tx-1'
            mock_storage.store_centrality_atomic = AsyncMock(return_value=mock_transaction)

            await store_centrality_scores(mock_driver, scores)

            mock_storage.store_centrality_atomic.assert_awaited_once_with(scores)

    @pytest.mark.asyncio
    async def test_calculate_all_centralities(self, mock_driver, sample_nodes):
        """Test calculating all centrality metrics together."""
        node_uuids = [node['uuid'] for node in sample_nodes]
        mock_driver.execute_query.side_effect = _build_execute_query_side_effect(
            node_uuids,
            total_degree=2,
            node_count=len(node_uuids),
        )

        with patch(
            'graphiti_core.utils.maintenance.centrality_operations.store_centrality_scores',
            new=AsyncMock(),
        ) as mock_store:
            result = await calculate_all_centralities(mock_driver)

            assert isinstance(result, dict)
            assert set(result.keys()) == set(node_uuids)
            mock_store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_calculate_all_centralities_with_node_ids(self, mock_driver, sample_nodes):
        """Test calculating centralities for specific nodes."""
        node_uuids = [node['uuid'] for node in sample_nodes[:2]]
        mock_driver.execute_query.side_effect = _build_execute_query_side_effect(
            node_uuids,
            total_degree=1,
            node_count=len(node_uuids),
        )

        with patch(
            'graphiti_core.utils.maintenance.centrality_operations.store_centrality_scores',
            new=AsyncMock(),
        ) as mock_store:
            result = await calculate_all_centralities(mock_driver, store_results=True)

            assert set(result.keys()) == set(node_uuids)
            mock_store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_calculate_all_centralities_error_handling(self, mock_driver):
        """Test error handling in centrality calculations."""
        # Mock a database error
        mock_driver.execute_query.side_effect = Exception('Database connection error')

        with pytest.raises(Exception) as exc_info:
            await calculate_all_centralities(mock_driver)

        assert 'Database connection error' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_graph_handling(self, mock_driver):
        """Test handling of empty graph (no nodes)."""
        mock_driver.execute_query.return_value = ([], [], None)

        result = await calculate_pagerank(mock_driver)

        assert result == {}
        assert len(result) == 0


class TestCentralityIntegration:
    """Integration tests that require a real graph database connection."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pagerank_with_real_graph(self, graph_driver):
        """Test PageRank on a real graph structure."""
        # This test would require a real graph database instance
        # Skip if not in integration test mode
        pytest.skip('Requires graph database instance')

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_centrality_persistence(self, graph_driver):
        """Test that centrality scores are properly persisted."""
        pytest.skip('Requires graph database instance')
