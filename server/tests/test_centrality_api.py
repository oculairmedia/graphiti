"""
Tests for centrality API endpoints.

This module tests the FastAPI endpoints for centrality analysis including:
- POST /centrality/calculate
- GET /centrality/pagerank
- GET /centrality/degree
- GET /centrality/betweenness
- GET /centrality/report/{node_id}
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from uuid import uuid4
import json

from graph_service.main import app
from graph_service.dto.centrality import (
    CentralityCalculateRequest,
    CentralityResponse,
    NodeCentralityScore,
    CentralityReportResponse,
)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_graphiti():
    """Create a mock Graphiti instance."""
    mock = MagicMock()
    mock.driver = MagicMock()
    return mock


@pytest.fixture
def sample_centrality_data():
    """Create sample centrality data for testing."""
    return [
        {
            'node_id': str(uuid4()),
            'name': 'Machine Learning',
            'pagerank': 0.0834,
            'degree_centrality': 0.342,
            'betweenness_centrality': 0.089,
            'in_degree': 25,
            'out_degree': 30,
            'total_degree': 55
        },
        {
            'node_id': str(uuid4()),
            'name': 'Neural Networks',
            'pagerank': 0.0672,
            'degree_centrality': 0.298,
            'betweenness_centrality': 0.156,
            'in_degree': 20,
            'out_degree': 25,
            'total_degree': 45
        },
        {
            'node_id': str(uuid4()),
            'name': 'Data Science',
            'pagerank': 0.0523,
            'degree_centrality': 0.215,
            'betweenness_centrality': 0.045,
            'in_degree': 15,
            'out_degree': 18,
            'total_degree': 33
        }
    ]


class TestCentralityCalculateEndpoint:
    """Test the POST /centrality/calculate endpoint."""

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_calculate_all_centralities_success(self, mock_get_graphiti, client, mock_graphiti):
        """Test successful calculation of all centralities."""
        mock_get_graphiti.return_value = mock_graphiti
        
        # Mock the centrality calculation
        with patch('graph_service.routers.centrality.calculate_all_centralities') as mock_calc:
            mock_calc.return_value = {
                'pagerank': 3,
                'degree': 3,
                'betweenness': 3,
                'calculated_nodes': 3,
                'execution_time_ms': 1234
            }
            
            response = client.post(
                "/centrality/calculate",
                json={"recalculate": True}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'
            assert data['data']['calculated_nodes'] == 3
            assert data['data']['execution_time_ms'] == 1234
            assert 'pagerank' in data['data']['metrics_calculated']

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_calculate_specific_nodes(self, mock_get_graphiti, client, mock_graphiti):
        """Test calculation for specific nodes."""
        mock_get_graphiti.return_value = mock_graphiti
        node_ids = [str(uuid4()), str(uuid4())]
        
        with patch('graph_service.routers.centrality.calculate_all_centralities') as mock_calc:
            mock_calc.return_value = {
                'pagerank': 2,
                'degree': 2,
                'betweenness': 2,
                'calculated_nodes': 2,
                'execution_time_ms': 567
            }
            
            response = client.post(
                "/centrality/calculate",
                json={"node_ids": node_ids, "recalculate": False}
            )
            
            assert response.status_code == 200
            mock_calc.assert_called_once_with(
                mock_graphiti.driver,
                node_ids=node_ids,
                recalculate=False
            )

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_calculate_error_handling(self, mock_get_graphiti, client, mock_graphiti):
        """Test error handling in calculation endpoint."""
        mock_get_graphiti.return_value = mock_graphiti
        
        with patch('graph_service.routers.centrality.calculate_all_centralities') as mock_calc:
            mock_calc.side_effect = Exception("Database error")
            
            response = client.post("/centrality/calculate", json={})
            
            assert response.status_code == 500
            data = response.json()
            assert data['status'] == 'error'
            assert 'Database error' in data['error']['message']


class TestPageRankEndpoint:
    """Test the GET /centrality/pagerank endpoint."""

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_get_pagerank_all_nodes(self, mock_get_graphiti, client, mock_graphiti, sample_centrality_data):
        """Test getting PageRank for all nodes."""
        mock_get_graphiti.return_value = mock_graphiti
        
        # Mock the query result
        mock_graphiti.driver.execute_query = AsyncMock(return_value=[
            {
                'uuid': d['node_id'],
                'name': d['name'],
                'pagerank': d['pagerank']
            } for d in sample_centrality_data
        ])
        
        response = client.get("/centrality/pagerank")
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert len(data['data']) == 3
        assert data['data'][0]['pagerank'] == 0.0834
        assert 'rank' in data['data'][0]

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_get_pagerank_top_n(self, mock_get_graphiti, client, mock_graphiti, sample_centrality_data):
        """Test getting top N nodes by PageRank."""
        mock_get_graphiti.return_value = mock_graphiti
        
        mock_graphiti.driver.execute_query = AsyncMock(return_value=[
            {
                'uuid': sample_centrality_data[0]['node_id'],
                'name': sample_centrality_data[0]['name'],
                'pagerank': sample_centrality_data[0]['pagerank']
            }
        ])
        
        response = client.get("/centrality/pagerank?top_n=1")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data['data']) == 1
        assert data['metadata']['returned_nodes'] == 1

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_get_pagerank_specific_nodes(self, mock_get_graphiti, client, mock_graphiti):
        """Test getting PageRank for specific nodes."""
        mock_get_graphiti.return_value = mock_graphiti
        node_ids = [str(uuid4()), str(uuid4())]
        
        mock_graphiti.driver.execute_query = AsyncMock(return_value=[])
        
        response = client.get(f"/centrality/pagerank?node_ids={','.join(node_ids)}")
        
        assert response.status_code == 200
        # Verify node IDs were passed to query
        call_args = mock_graphiti.driver.execute_query.call_args
        assert call_args[1]['parameters']['node_ids'] == node_ids


class TestDegreeCentralityEndpoint:
    """Test the GET /centrality/degree endpoint."""

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_get_degree_centrality(self, mock_get_graphiti, client, mock_graphiti, sample_centrality_data):
        """Test getting degree centrality scores."""
        mock_get_graphiti.return_value = mock_graphiti
        
        mock_graphiti.driver.execute_query = AsyncMock(return_value=[
            {
                'uuid': d['node_id'],
                'name': d['name'],
                'degree_centrality': d['degree_centrality'],
                'in_degree': d['in_degree'],
                'out_degree': d['out_degree'],
                'total_degree': d['total_degree']
            } for d in sample_centrality_data
        ])
        
        response = client.get("/centrality/degree")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data['data']) == 3
        assert data['data'][0]['degree_centrality'] == 0.342
        assert data['data'][0]['total_degree'] == 55

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_get_degree_centrality_direction(self, mock_get_graphiti, client, mock_graphiti):
        """Test getting degree centrality with direction filter."""
        mock_get_graphiti.return_value = mock_graphiti
        
        mock_graphiti.driver.execute_query = AsyncMock(return_value=[])
        
        # Test incoming edges
        response = client.get("/centrality/degree?direction=in")
        assert response.status_code == 200
        
        # Test outgoing edges
        response = client.get("/centrality/degree?direction=out")
        assert response.status_code == 200
        
        # Test invalid direction
        response = client.get("/centrality/degree?direction=invalid")
        assert response.status_code == 422  # Validation error


class TestBetweennessCentralityEndpoint:
    """Test the GET /centrality/betweenness endpoint."""

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_get_betweenness_centrality(self, mock_get_graphiti, client, mock_graphiti, sample_centrality_data):
        """Test getting betweenness centrality scores."""
        mock_get_graphiti.return_value = mock_graphiti
        
        mock_graphiti.driver.execute_query = AsyncMock(return_value=[
            {
                'uuid': d['node_id'],
                'name': d['name'],
                'betweenness_centrality': d['betweenness_centrality']
            } for d in sample_centrality_data
        ])
        
        response = client.get("/centrality/betweenness?normalized=true")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data['data']) == 3
        assert data['metadata']['normalized'] is True


class TestCentralityReportEndpoint:
    """Test the GET /centrality/report/{node_id} endpoint."""

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_get_centrality_report(self, mock_get_graphiti, client, mock_graphiti, sample_centrality_data):
        """Test getting comprehensive centrality report for a node."""
        mock_get_graphiti.return_value = mock_graphiti
        node_data = sample_centrality_data[0]
        node_id = node_data['node_id']
        
        # Mock node details query
        mock_graphiti.driver.execute_query = AsyncMock(side_effect=[
            # First call: node details
            [{
                'uuid': node_id,
                'name': node_data['name'],
                'type': 'CONCEPT',
                'pagerank': node_data['pagerank'],
                'degree_centrality': node_data['degree_centrality'],
                'betweenness_centrality': node_data['betweenness_centrality'],
                'in_degree': node_data['in_degree'],
                'out_degree': node_data['out_degree']
            }],
            # Second call: percentile calculations
            [{'percentile': 95.2}],
            [{'percentile': 92.1}],
            [{'percentile': 88.5}]
        ])
        
        response = client.get(f"/centrality/report/{node_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['data']['node']['id'] == node_id
        assert 'centrality_metrics' in data['data']
        assert 'interpretation' in data['data']
        
        # Check metrics
        metrics = data['data']['centrality_metrics']
        assert metrics['pagerank']['score'] == node_data['pagerank']
        assert metrics['degree']['total_degree'] == node_data['total_degree']
        assert metrics['betweenness']['score'] == node_data['betweenness_centrality']

    @patch('graph_service.routers.centrality.get_graphiti')
    async def test_get_centrality_report_node_not_found(self, mock_get_graphiti, client, mock_graphiti):
        """Test report endpoint when node doesn't exist."""
        mock_get_graphiti.return_value = mock_graphiti
        node_id = str(uuid4())
        
        mock_graphiti.driver.execute_query = AsyncMock(return_value=[])
        
        response = client.get(f"/centrality/report/{node_id}")
        
        assert response.status_code == 404
        data = response.json()
        assert data['status'] == 'error'
        assert data['error']['code'] == 'NODE_NOT_FOUND'


class TestCentralityEndpointIntegration:
    """Integration tests for centrality endpoints."""

    @pytest.mark.integration
    async def test_full_centrality_workflow(self, client):
        """Test complete workflow: calculate, then retrieve results."""
        # This would test against a real database
        pytest.skip("Requires Neo4j instance")

    @pytest.mark.integration
    async def test_concurrent_requests(self, client):
        """Test handling of concurrent centrality requests."""
        pytest.skip("Requires Neo4j instance")