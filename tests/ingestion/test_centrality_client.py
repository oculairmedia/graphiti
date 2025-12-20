"""
Tests for the CentralityClient HTTP client.
Covers centrality update operations and error handling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from graphiti_core.ingestion.worker import CentralityClient


class TestCentralityClientInit:
    """Tests for CentralityClient initialization."""

    def test_default_url_from_env(self):
        """Should use RUST_CENTRALITY_URL env var if set."""
        with patch.dict('os.environ', {'RUST_CENTRALITY_URL': 'http://custom:9000'}):
            client = CentralityClient()
            assert client.base_url == 'http://custom:9000'

    def test_explicit_url_override(self):
        """Should use explicit URL over env var."""
        with patch.dict('os.environ', {'RUST_CENTRALITY_URL': 'http://env:9000'}):
            client = CentralityClient(base_url='http://explicit:8000')
            assert client.base_url == 'http://explicit:8000'

    def test_default_url_fallback(self):
        """Should use default URL when no env var set."""
        with patch.dict('os.environ', {}, clear=True):
            # Remove the env var if it exists
            import os

            os.environ.pop('RUST_CENTRALITY_URL', None)
            client = CentralityClient()
            assert client.base_url == 'http://graphiti-centrality-rs:3003'


class TestUpdateNodeCentrality:
    """Tests for single node centrality updates."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        return CentralityClient(base_url='http://test:3003')

    @pytest.mark.asyncio
    async def test_successful_update(self, client):
        """Should return True on successful update."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'metrics': {
                'degree': 5,
                'pagerank': 0.15,
                'betweenness': 0.02,
                'eigenvector': 0.08,
            }
        }

        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.update_node_centrality('node-123')

        assert result is True
        client.client.post.assert_called_once_with(
            'http://test:3003/centrality/node/node-123',
            json={
                'metrics': ['degree', 'pagerank', 'betweenness', 'eigenvector'],
                'store_results': True,
            },
        )

    @pytest.mark.asyncio
    async def test_failed_update_returns_false(self, client):
        """Should return False on non-200 status."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.update_node_centrality('node-123')

        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self, client):
        """Should return False on exception."""
        client.client.post = AsyncMock(side_effect=Exception('Connection error'))

        result = await client.update_node_centrality('node-123')

        assert result is False

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self, client):
        """Should return False on timeout."""
        import httpx

        client.client.post = AsyncMock(side_effect=httpx.TimeoutException('Timeout'))

        result = await client.update_node_centrality('node-123')

        assert result is False

    @pytest.mark.asyncio
    async def test_server_error_returns_false(self, client):
        """Should return False on 500 error."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.update_node_centrality('node-123')

        assert result is False


class TestUpdateNodesCentrality:
    """Tests for batch node centrality updates."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        return CentralityClient(base_url='http://test:3003')

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero(self, client):
        """Should return 0 for empty node list."""
        result = await client.update_nodes_centrality([])
        assert result == 0

    @pytest.mark.asyncio
    async def test_all_successful_returns_count(self, client):
        """Should return count of successful updates."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'metrics': {}}

        client.client.post = AsyncMock(return_value=mock_response)

        result = await client.update_nodes_centrality(['node-1', 'node-2', 'node-3'])

        assert result == 3
        assert client.client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_partial_success_returns_partial_count(self, client):
        """Should return count of successful updates even with failures."""
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {'metrics': {}}

        fail_response = MagicMock()
        fail_response.status_code = 404

        # First and third succeed, second fails
        client.client.post = AsyncMock(
            side_effect=[success_response, fail_response, success_response]
        )

        result = await client.update_nodes_centrality(['node-1', 'node-2', 'node-3'])

        assert result == 2

    @pytest.mark.asyncio
    async def test_all_failures_returns_zero(self, client):
        """Should return 0 when all updates fail."""
        fail_response = MagicMock()
        fail_response.status_code = 500

        client.client.post = AsyncMock(return_value=fail_response)

        result = await client.update_nodes_centrality(['node-1', 'node-2'])

        assert result == 0

    @pytest.mark.asyncio
    async def test_mixed_errors_handles_gracefully(self, client):
        """Should handle mixed success, failure, and exceptions."""
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {'metrics': {}}

        fail_response = MagicMock()
        fail_response.status_code = 404

        # Success, 404, exception, success
        client.client.post = AsyncMock(
            side_effect=[
                success_response,
                fail_response,
                Exception('Network error'),
                success_response,
            ]
        )

        result = await client.update_nodes_centrality(['node-1', 'node-2', 'node-3', 'node-4'])

        assert result == 2


class TestCentralityClientClose:
    """Tests for client cleanup."""

    @pytest.mark.asyncio
    async def test_close_closes_http_client(self):
        """Should close the underlying HTTP client."""
        client = CentralityClient(base_url='http://test:3003')
        client.client.aclose = AsyncMock()

        await client.close()

        client.client.aclose.assert_called_once()


class TestCentralityClientIntegration:
    """Integration-style tests for CentralityClient."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        return CentralityClient(base_url='http://test:3003')

    @pytest.mark.asyncio
    async def test_request_includes_all_metrics(self, client):
        """Should request all centrality metrics."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'metrics': {}}

        client.client.post = AsyncMock(return_value=mock_response)

        await client.update_node_centrality('node-123')

        call_args = client.client.post.call_args
        json_body = call_args[1]['json']

        assert 'degree' in json_body['metrics']
        assert 'pagerank' in json_body['metrics']
        assert 'betweenness' in json_body['metrics']
        assert 'eigenvector' in json_body['metrics']

    @pytest.mark.asyncio
    async def test_store_results_flag_set(self, client):
        """Should set store_results flag to True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'metrics': {}}

        client.client.post = AsyncMock(return_value=mock_response)

        await client.update_node_centrality('node-123')

        call_args = client.client.post.call_args
        json_body = call_args[1]['json']

        assert json_body['store_results'] is True

    @pytest.mark.asyncio
    async def test_node_uuid_in_url(self, client):
        """Should include node UUID in URL path."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'metrics': {}}

        client.client.post = AsyncMock(return_value=mock_response)

        await client.update_node_centrality('special-node-uuid-123')

        call_args = client.client.post.call_args
        url = call_args[0][0]

        assert 'special-node-uuid-123' in url
