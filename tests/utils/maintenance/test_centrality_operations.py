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

from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.utils.maintenance.centrality_operations import (
    calculate_all_centralities,
    calculate_betweenness_centrality,
    calculate_degree_centrality,
    calculate_pagerank,
    store_centrality_scores,
)


class TestCentralityOperations:
    """Test suite for centrality operations."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = MagicMock(spec=Neo4jDriver)
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
        # Mock the driver response
        mock_driver.execute_query.return_value = sample_nodes

        # Execute PageRank calculation
        result = await calculate_pagerank(mock_driver)

        # Verify the query was called
        mock_driver.execute_query.assert_called_once()
        query_args = mock_driver.execute_query.call_args[0]

        # Check that the query contains PageRank algorithm
        assert 'gds.pageRank' in query_args[0]
        assert 'damping_factor: $damping_factor' in query_args[0]
        assert 'max_iterations: $max_iterations' in query_args[0]

        # Check parameters
        params = mock_driver.execute_query.call_args[1]['parameters']
        assert params['damping_factor'] == 0.85
        assert params['max_iterations'] == 20

        # Verify result
        assert result == sample_nodes
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_calculate_pagerank_custom_params(self, mock_driver, sample_nodes):
        """Test PageRank calculation with custom parameters."""
        mock_driver.execute_query.return_value = sample_nodes

        # Execute with custom parameters
        result = await calculate_pagerank(
            mock_driver, damping_factor=0.75, max_iterations=50, node_ids=['node1', 'node2']
        )

        # Check parameters
        params = mock_driver.execute_query.call_args[1]['parameters']
        assert params['damping_factor'] == 0.75
        assert params['max_iterations'] == 50
        assert params['node_ids'] == ['node1', 'node2']

    @pytest.mark.asyncio
    async def test_calculate_degree_centrality(self, mock_driver, sample_nodes):
        """Test degree centrality calculation."""
        mock_driver.execute_query.return_value = sample_nodes

        result = await calculate_degree_centrality(mock_driver)

        # Verify query contains degree centrality calculation
        query = mock_driver.execute_query.call_args[0][0]
        assert 'size([(n)-[]-() |' in query
        assert 'toFloat(node_count - 1)' in query
        assert 'degree_centrality' in query

        assert result == sample_nodes

    @pytest.mark.asyncio
    async def test_calculate_degree_centrality_with_filters(self, mock_driver, sample_nodes):
        """Test degree centrality with node filters."""
        mock_driver.execute_query.return_value = sample_nodes

        node_ids = [str(uuid4()), str(uuid4())]
        result = await calculate_degree_centrality(mock_driver, node_ids=node_ids, direction='in')

        # Check that node IDs were passed
        params = mock_driver.execute_query.call_args[1]['parameters']
        assert params['node_ids'] == node_ids

        # Check query for incoming edges only
        query = mock_driver.execute_query.call_args[0][0]
        assert '<-' in query  # Should look for incoming edges

    @pytest.mark.asyncio
    async def test_calculate_betweenness_centrality(self, mock_driver, sample_nodes):
        """Test betweenness centrality calculation."""
        mock_driver.execute_query.return_value = sample_nodes

        result = await calculate_betweenness_centrality(mock_driver)

        # Verify query contains betweenness centrality algorithm
        query = mock_driver.execute_query.call_args[0][0]
        assert 'gds.betweenness' in query
        assert 'sample_size: $sample_size' in query

        assert result == sample_nodes

    @pytest.mark.asyncio
    async def test_calculate_betweenness_centrality_sampling(self, mock_driver, sample_nodes):
        """Test betweenness centrality with sampling."""
        mock_driver.execute_query.return_value = sample_nodes

        result = await calculate_betweenness_centrality(mock_driver, sample_size=100)

        # Check sample size parameter
        params = mock_driver.execute_query.call_args[1]['parameters']
        assert params['sample_size'] == 100

    @pytest.mark.asyncio
    async def test_store_centrality_scores(self, mock_driver):
        """Test storing centrality scores to nodes."""
        scores = [
            {
                'uuid': 'node1',
                'pagerank': 0.15,
                'degree_centrality': 0.4,
                'betweenness_centrality': 0.1,
            },
            {
                'uuid': 'node2',
                'pagerank': 0.25,
                'degree_centrality': 0.6,
                'betweenness_centrality': 0.3,
            },
        ]

        await store_centrality_scores(mock_driver, scores)

        # Verify the update query was called
        mock_driver.execute_query.assert_called_once()
        query = mock_driver.execute_query.call_args[0][0]

        # Check that all centrality properties are being set
        assert 'n.pagerank = score.pagerank' in query
        assert 'n.degree_centrality = score.degree_centrality' in query
        assert 'n.betweenness_centrality = score.betweenness_centrality' in query
        assert 'n.centrality_updated_at = $timestamp' in query

        # Check parameters
        params = mock_driver.execute_query.call_args[1]['parameters']
        assert params['scores'] == scores
        assert isinstance(params['timestamp'], str)

    @pytest.mark.asyncio
    async def test_calculate_all_centralities(self, mock_driver, sample_nodes):
        """Test calculating all centrality metrics together."""
        # Mock responses for each calculation
        mock_driver.execute_query.side_effect = [
            sample_nodes,  # PageRank
            sample_nodes,  # Degree centrality
            sample_nodes,  # Betweenness centrality
            None,  # Store operation
        ]

        result = await calculate_all_centralities(mock_driver)

        # Should have called execute_query 4 times
        assert mock_driver.execute_query.call_count == 4

        # Verify result structure
        assert 'pagerank' in result
        assert 'degree' in result
        assert 'betweenness' in result
        assert 'calculated_nodes' in result
        assert 'execution_time_ms' in result

        assert result['calculated_nodes'] == len(sample_nodes)
        assert result['execution_time_ms'] > 0

    @pytest.mark.asyncio
    async def test_calculate_all_centralities_with_node_ids(self, mock_driver, sample_nodes):
        """Test calculating centralities for specific nodes."""
        node_ids = ['node1', 'node2']

        mock_driver.execute_query.side_effect = [
            sample_nodes[:2],  # PageRank
            sample_nodes[:2],  # Degree centrality
            sample_nodes[:2],  # Betweenness centrality
            None,  # Store operation
        ]

        result = await calculate_all_centralities(mock_driver, node_ids=node_ids, recalculate=True)

        # Verify node IDs were passed to each calculation
        for i in range(3):  # First 3 calls are calculations
            call_params = mock_driver.execute_query.call_args_list[i][1]['parameters']
            assert call_params.get('node_ids') == node_ids

        assert result['calculated_nodes'] == 2

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
        mock_driver.execute_query.return_value = []

        result = await calculate_pagerank(mock_driver)

        assert result == []
        assert len(result) == 0


class TestCentralityIntegration:
    """Integration tests that require a real Neo4j connection."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pagerank_with_real_graph(self, neo4j_driver):
        """Test PageRank on a real graph structure."""
        # This test would require a real Neo4j instance
        # Skip if not in integration test mode
        pytest.skip('Requires Neo4j instance')

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_centrality_persistence(self, neo4j_driver):
        """Test that centrality scores are properly persisted."""
        pytest.skip('Requires Neo4j instance')
