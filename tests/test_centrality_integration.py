"""
Integration tests for centrality features in Graphiti.

These tests verify that centrality analysis works correctly
with the full Graphiti stack including Neo4j.
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode
from graphiti_core.utils.maintenance.centrality_operations import (
    calculate_all_centralities,
    calculate_betweenness_centrality,
    calculate_degree_centrality,
    calculate_pagerank,
)


@pytest.mark.integration
class TestCentralityIntegration:
    """Integration tests for centrality analysis with real Neo4j."""

    @pytest.fixture
    async def graphiti_instance(self, neo4j_config):
        """Create a real Graphiti instance for testing."""
        graphiti = Graphiti(
            neo4j_uri=neo4j_config['uri'],
            neo4j_user=neo4j_config['user'],
            neo4j_password=neo4j_config['password'],
        )

        # Initialize the graph
        await graphiti.initialize()

        # Clean up any existing data
        await graphiti.driver.execute_query('MATCH (n) DETACH DELETE n')

        yield graphiti

        # Cleanup after tests
        await graphiti.close()

    @pytest.fixture
    async def populated_graph(self, graphiti_instance):
        """Create a populated graph for testing centrality."""
        graphiti = graphiti_instance

        # Create a knowledge graph about AI/ML concepts
        nodes_data = [
            ('AI', 'Artificial Intelligence', 'FIELD'),
            ('ML', 'Machine Learning', 'FIELD'),
            ('DL', 'Deep Learning', 'CONCEPT'),
            ('NN', 'Neural Networks', 'CONCEPT'),
            ('CV', 'Computer Vision', 'APPLICATION'),
            ('NLP', 'Natural Language Processing', 'APPLICATION'),
            ('RL', 'Reinforcement Learning', 'CONCEPT'),
            ('DS', 'Data Science', 'FIELD'),
            ('Stats', 'Statistics', 'CONCEPT'),
            ('Python', 'Python Programming', 'TOOL'),
        ]

        # Create nodes
        nodes = {}
        for node_id, name, node_type in nodes_data:
            node = EntityNode(
                uuid=node_id,
                name=name,
                type=node_type,
                created_at=datetime.now(timezone.utc),
                summary=f'{name} is a key concept in the field',
            )
            await graphiti.driver.create_node(node)
            nodes[node_id] = node

        # Create edges representing relationships
        edges_data = [
            ('AI', 'ML', 'INCLUDES', 'includes'),
            ('ML', 'DL', 'INCLUDES', 'includes'),
            ('DL', 'NN', 'BASED_ON', 'is based on'),
            ('ML', 'NN', 'USES', 'uses'),
            ('DL', 'CV', 'APPLIED_TO', 'is applied to'),
            ('DL', 'NLP', 'APPLIED_TO', 'is applied to'),
            ('ML', 'RL', 'INCLUDES', 'includes'),
            ('ML', 'DS', 'PART_OF', 'is part of'),
            ('DS', 'Stats', 'REQUIRES', 'requires'),
            ('ML', 'Python', 'IMPLEMENTED_WITH', 'is implemented with'),
            ('DL', 'Python', 'IMPLEMENTED_WITH', 'is implemented with'),
            ('DS', 'Python', 'USES', 'uses'),
        ]

        for source, target, edge_type, name in edges_data:
            edge = EntityEdge(
                uuid=str(uuid4()),
                source=source,
                target=target,
                type=edge_type,
                name=name,
                created_at=datetime.now(timezone.utc),
                summary=f'{source} {name} {target}',
            )
            await graphiti.driver.create_edge(edge)

        return graphiti, nodes

    @pytest.mark.asyncio
    async def test_calculate_pagerank_integration(self, populated_graph):
        """Test PageRank calculation on a real graph."""
        graphiti, nodes = populated_graph

        # Calculate PageRank
        results = await calculate_pagerank(graphiti.driver)

        # Verify results
        assert len(results) == len(nodes)

        # Check that nodes have PageRank scores
        node_scores = {r['uuid']: r['pagerank'] for r in results}

        # ML should have high PageRank (many outgoing edges)
        assert node_scores['ML'] > 0.1

        # Python should have high PageRank (many incoming edges)
        assert node_scores['Python'] > node_scores['Stats']

        # All scores should be positive and sum to approximately 1
        total_score = sum(node_scores.values())
        assert 0.9 < total_score < 1.1

    @pytest.mark.asyncio
    async def test_calculate_degree_centrality_integration(self, populated_graph):
        """Test degree centrality calculation on a real graph."""
        graphiti, nodes = populated_graph

        # Calculate degree centrality
        results = await calculate_degree_centrality(graphiti.driver)

        # Verify results
        assert len(results) == len(nodes)

        # Check degree counts
        node_degrees = {r['uuid']: r for r in results}

        # ML should have high degree (connected to many nodes)
        ml_node = node_degrees['ML']
        assert ml_node['total_degree'] >= 6  # Connected to DL, NN, RL, DS, Python, AI
        assert ml_node['degree_centrality'] > 0.5

        # Stats should have low degree (only connected to DS)
        stats_node = node_degrees['Stats']
        assert stats_node['total_degree'] == 1
        assert stats_node['degree_centrality'] < 0.2

    @pytest.mark.asyncio
    async def test_calculate_betweenness_centrality_integration(self, populated_graph):
        """Test betweenness centrality calculation on a real graph."""
        graphiti, nodes = populated_graph

        # Calculate betweenness centrality
        results = await calculate_betweenness_centrality(graphiti.driver)

        # Verify results
        assert len(results) == len(nodes)

        # Check betweenness scores
        node_scores = {r['uuid']: r['betweenness_centrality'] for r in results}

        # ML should have high betweenness (bridge between AI and specific concepts)
        assert node_scores['ML'] > 0.1

        # Leaf nodes should have zero betweenness
        assert node_scores['CV'] == 0.0
        assert node_scores['NLP'] == 0.0

    @pytest.mark.asyncio
    async def test_calculate_all_centralities_integration(self, populated_graph):
        """Test calculating all centrality metrics together."""
        graphiti, nodes = populated_graph

        # Calculate all centralities
        result = await calculate_all_centralities(graphiti.driver)

        # Verify result structure
        assert 'pagerank' in result
        assert 'degree' in result
        assert 'betweenness' in result
        assert 'calculated_nodes' in result
        assert 'execution_time_ms' in result

        assert result['calculated_nodes'] == len(nodes)
        assert result['execution_time_ms'] > 0

        # Verify scores were stored on nodes
        stored_nodes = await graphiti.driver.execute_query(
            'MATCH (n) RETURN n.uuid as uuid, n.pagerank as pagerank, '
            'n.degree_centrality as degree_centrality, '
            'n.betweenness_centrality as betweenness_centrality, '
            'n.centrality_updated_at as updated_at'
        )

        for node in stored_nodes:
            assert node['pagerank'] is not None
            assert node['degree_centrality'] is not None
            assert node['betweenness_centrality'] is not None
            assert node['updated_at'] is not None

    @pytest.mark.asyncio
    async def test_centrality_with_filtered_nodes(self, populated_graph):
        """Test centrality calculation for specific nodes only."""
        graphiti, nodes = populated_graph

        # Calculate centralities for ML-related nodes only
        target_nodes = ['ML', 'DL', 'NN']
        result = await calculate_all_centralities(graphiti.driver, node_ids=target_nodes)

        assert result['calculated_nodes'] == 3

        # Verify only target nodes have updated centrality
        all_nodes = await graphiti.driver.execute_query(
            'MATCH (n) RETURN n.uuid as uuid, n.centrality_updated_at as updated_at'
        )

        updated_nodes = [n['uuid'] for n in all_nodes if n['updated_at'] is not None]
        assert set(updated_nodes) == set(target_nodes)

    @pytest.mark.asyncio
    async def test_centrality_persistence(self, populated_graph):
        """Test that centrality scores persist across queries."""
        graphiti, nodes = populated_graph

        # Calculate centralities
        await calculate_all_centralities(graphiti.driver)

        # Retrieve scores
        first_query = await graphiti.driver.execute_query(
            "MATCH (n) WHERE n.uuid = 'ML' RETURN n.pagerank as pr, n.degree_centrality as dc"
        )

        # Wait a bit and query again
        await asyncio.sleep(0.1)

        second_query = await graphiti.driver.execute_query(
            "MATCH (n) WHERE n.uuid = 'ML' RETURN n.pagerank as pr, n.degree_centrality as dc"
        )

        # Scores should be identical
        assert first_query[0]['pr'] == second_query[0]['pr']
        assert first_query[0]['dc'] == second_query[0]['dc']

    @pytest.mark.asyncio
    async def test_centrality_with_search_integration(self, populated_graph):
        """Test using centrality scores in search queries."""
        graphiti, nodes = populated_graph

        # Calculate centralities
        await calculate_all_centralities(graphiti.driver)

        # Search for high PageRank nodes
        high_pagerank_nodes = await graphiti.driver.execute_query(
            'MATCH (n) WHERE n.pagerank > 0.1 '
            'RETURN n.uuid as uuid, n.name as name, n.pagerank as pagerank '
            'ORDER BY n.pagerank DESC'
        )

        assert len(high_pagerank_nodes) > 0
        assert all(n['pagerank'] > 0.1 for n in high_pagerank_nodes)

        # The results should be ordered by PageRank
        scores = [n['pagerank'] for n in high_pagerank_nodes]
        assert scores == sorted(scores, reverse=True)
