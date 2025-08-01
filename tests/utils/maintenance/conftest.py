"""
Shared test fixtures for maintenance utilities tests.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode


@pytest.fixture
def neo4j_driver():
    """Create a mock Neo4j driver for testing."""
    driver = MagicMock(spec=Neo4jDriver)
    driver.execute_query = AsyncMock()
    driver.fetch_nodes = AsyncMock()
    driver.fetch_edges = AsyncMock()
    return driver


@pytest.fixture
def sample_graph_data():
    """
    Create a sample graph structure for testing centrality calculations.

    Returns a dict with nodes and edges representing a simple knowledge graph:

        A (ML) -----> B (Neural Networks)
        |   ^         |
        |   |         v
        v   |         C (Deep Learning)
        D (Data)      |
                      v
                      E (Computer Vision)
    """
    nodes = [
        {
            'uuid': 'node-a',
            'name': 'Machine Learning',
            'type': 'CONCEPT',
            'created_at': datetime.now(timezone.utc).isoformat(),
        },
        {
            'uuid': 'node-b',
            'name': 'Neural Networks',
            'type': 'CONCEPT',
            'created_at': datetime.now(timezone.utc).isoformat(),
        },
        {
            'uuid': 'node-c',
            'name': 'Deep Learning',
            'type': 'CONCEPT',
            'created_at': datetime.now(timezone.utc).isoformat(),
        },
        {
            'uuid': 'node-d',
            'name': 'Data Science',
            'type': 'FIELD',
            'created_at': datetime.now(timezone.utc).isoformat(),
        },
        {
            'uuid': 'node-e',
            'name': 'Computer Vision',
            'type': 'APPLICATION',
            'created_at': datetime.now(timezone.utc).isoformat(),
        },
    ]

    edges = [
        {
            'uuid': 'edge-1',
            'source': 'node-a',
            'target': 'node-b',
            'type': 'RELATES_TO',
            'name': 'includes',
        },
        {
            'uuid': 'edge-2',
            'source': 'node-a',
            'target': 'node-d',
            'type': 'REQUIRES',
            'name': 'requires',
        },
        {
            'uuid': 'edge-3',
            'source': 'node-b',
            'target': 'node-c',
            'type': 'ENABLES',
            'name': 'enables',
        },
        {
            'uuid': 'edge-4',
            'source': 'node-d',
            'target': 'node-a',
            'type': 'SUPPORTS',
            'name': 'supports',
        },
        {
            'uuid': 'edge-5',
            'source': 'node-c',
            'target': 'node-e',
            'type': 'APPLIED_TO',
            'name': 'applied to',
        },
    ]

    return {'nodes': nodes, 'edges': edges}


@pytest.fixture
def expected_centrality_scores():
    """
    Expected centrality scores for the sample graph.

    These are approximate values for testing purposes.
    """
    return {
        'node-a': {
            'pagerank': 0.25,  # High - has incoming and outgoing edges
            'degree_centrality': 0.75,  # 3 connections out of 4 possible
            'betweenness_centrality': 0.5,  # On path between D and B/C
        },
        'node-b': {
            'pagerank': 0.20,
            'degree_centrality': 0.5,  # 2 connections
            'betweenness_centrality': 0.25,  # Bridge to C
        },
        'node-c': {
            'pagerank': 0.18,
            'degree_centrality': 0.5,
            'betweenness_centrality': 0.0,  # Not between any nodes
        },
        'node-d': {'pagerank': 0.15, 'degree_centrality': 0.5, 'betweenness_centrality': 0.0},
        'node-e': {
            'pagerank': 0.12,
            'degree_centrality': 0.25,  # Only 1 connection
            'betweenness_centrality': 0.0,
        },
    }


@pytest.fixture
def centrality_query_results(sample_graph_data, expected_centrality_scores):
    """Mock results from centrality queries."""
    nodes = sample_graph_data['nodes']
    scores = expected_centrality_scores

    return [
        {
            'uuid': node['uuid'],
            'name': node['name'],
            'pagerank': scores[node['uuid']]['pagerank'],
            'degree_centrality': scores[node['uuid']]['degree_centrality'],
            'betweenness_centrality': scores[node['uuid']]['betweenness_centrality'],
            'in_degree': len(
                [e for e in sample_graph_data['edges'] if e['target'] == node['uuid']]
            ),
            'out_degree': len(
                [e for e in sample_graph_data['edges'] if e['source'] == node['uuid']]
            ),
            'total_degree': len(
                [
                    e
                    for e in sample_graph_data['edges']
                    if e['source'] == node['uuid'] or e['target'] == node['uuid']
                ]
            ),
        }
        for node in nodes
    ]


@pytest.fixture
def mock_graphiti_instance(neo4j_driver):
    """Create a mock Graphiti instance with driver."""
    from unittest.mock import MagicMock

    graphiti = MagicMock()
    graphiti.driver = neo4j_driver
    graphiti.llm_client = MagicMock()
    graphiti.embedder = MagicMock()

    return graphiti
