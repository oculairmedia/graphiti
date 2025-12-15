"""
Tests to verify that edge_search and node_search respect the search_methods configuration.

This test ensures that when specific search methods are configured (e.g., only bm25),
only those methods are executed, preventing unnecessary computation overhead.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graphiti_core.search.search import edge_search, node_search
from graphiti_core.search.search_config import (
    EdgeReranker,
    EdgeSearchConfig,
    EdgeSearchMethod,
    NodeReranker,
    NodeSearchConfig,
    NodeSearchMethod,
)
from graphiti_core.search.search_filters import SearchFilters


@pytest.mark.asyncio
async def test_edge_search_respects_bm25_only_config():
    """When only bm25 is configured, only fulltext search should be called."""
    mock_driver = AsyncMock()
    mock_cross_encoder = AsyncMock()

    config = EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.bm25],
        reranker=EdgeReranker.rrf,
    )

    with (
        patch('graphiti_core.search.search.edge_fulltext_search') as mock_fulltext,
        patch('graphiti_core.search.search.edge_similarity_search') as mock_similarity,
        patch('graphiti_core.search.search.edge_bfs_search') as mock_bfs,
        patch('graphiti_core.search.search.rrf') as mock_rrf,
    ):
        mock_fulltext.return_value = []
        mock_similarity.return_value = []
        mock_bfs.return_value = []
        mock_rrf.return_value = []

        await edge_search(
            driver=mock_driver,
            cross_encoder=mock_cross_encoder,
            query='test query',
            query_vector=[0.1, 0.2, 0.3],
            group_ids=None,
            config=config,
            search_filter=SearchFilters(),
        )

        # Only fulltext (bm25) should be called
        assert mock_fulltext.call_count == 1, 'bm25/fulltext search should be called once'
        assert mock_similarity.call_count == 0, 'similarity search should NOT be called'
        assert mock_bfs.call_count == 0, 'bfs search should NOT be called'


@pytest.mark.asyncio
async def test_edge_search_respects_cosine_similarity_only_config():
    """When only cosine_similarity is configured, only similarity search should be called."""
    mock_driver = AsyncMock()
    mock_cross_encoder = AsyncMock()

    config = EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.cosine_similarity],
        reranker=EdgeReranker.rrf,
    )

    with (
        patch('graphiti_core.search.search.edge_fulltext_search') as mock_fulltext,
        patch('graphiti_core.search.search.edge_similarity_search') as mock_similarity,
        patch('graphiti_core.search.search.edge_bfs_search') as mock_bfs,
        patch('graphiti_core.search.search.rrf') as mock_rrf,
    ):
        mock_fulltext.return_value = []
        mock_similarity.return_value = []
        mock_bfs.return_value = []
        mock_rrf.return_value = []

        await edge_search(
            driver=mock_driver,
            cross_encoder=mock_cross_encoder,
            query='test query',
            query_vector=[0.1, 0.2, 0.3],
            group_ids=None,
            config=config,
            search_filter=SearchFilters(),
        )

        # Only similarity should be called
        assert mock_fulltext.call_count == 0, 'bm25/fulltext search should NOT be called'
        assert mock_similarity.call_count == 1, 'similarity search should be called once'
        assert mock_bfs.call_count == 0, 'bfs search should NOT be called'


@pytest.mark.asyncio
async def test_edge_search_respects_hybrid_config():
    """When bm25 and cosine_similarity are configured, both should be called but not bfs."""
    mock_driver = AsyncMock()
    mock_cross_encoder = AsyncMock()

    config = EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.bm25, EdgeSearchMethod.cosine_similarity],
        reranker=EdgeReranker.rrf,
    )

    with (
        patch('graphiti_core.search.search.edge_fulltext_search') as mock_fulltext,
        patch('graphiti_core.search.search.edge_similarity_search') as mock_similarity,
        patch('graphiti_core.search.search.edge_bfs_search') as mock_bfs,
        patch('graphiti_core.search.search.rrf') as mock_rrf,
    ):
        mock_fulltext.return_value = []
        mock_similarity.return_value = []
        mock_bfs.return_value = []
        mock_rrf.return_value = []

        await edge_search(
            driver=mock_driver,
            cross_encoder=mock_cross_encoder,
            query='test query',
            query_vector=[0.1, 0.2, 0.3],
            group_ids=None,
            config=config,
            search_filter=SearchFilters(),
        )

        # Both fulltext and similarity should be called, but not bfs
        assert mock_fulltext.call_count == 1, 'bm25/fulltext search should be called once'
        assert mock_similarity.call_count == 1, 'similarity search should be called once'
        assert mock_bfs.call_count == 0, 'bfs search should NOT be called'


@pytest.mark.asyncio
async def test_edge_search_all_methods_when_configured():
    """When all three methods are configured, all should be called."""
    mock_driver = AsyncMock()
    mock_cross_encoder = AsyncMock()

    config = EdgeSearchConfig(
        search_methods=[
            EdgeSearchMethod.bm25,
            EdgeSearchMethod.cosine_similarity,
            EdgeSearchMethod.bfs,
        ],
        reranker=EdgeReranker.rrf,
    )

    with (
        patch('graphiti_core.search.search.edge_fulltext_search') as mock_fulltext,
        patch('graphiti_core.search.search.edge_similarity_search') as mock_similarity,
        patch('graphiti_core.search.search.edge_bfs_search') as mock_bfs,
        patch('graphiti_core.search.search.rrf') as mock_rrf,
    ):
        mock_fulltext.return_value = []
        mock_similarity.return_value = []
        mock_bfs.return_value = []
        mock_rrf.return_value = []

        await edge_search(
            driver=mock_driver,
            cross_encoder=mock_cross_encoder,
            query='test query',
            query_vector=[0.1, 0.2, 0.3],
            group_ids=None,
            config=config,
            search_filter=SearchFilters(),
            bfs_origin_node_uuids=['node-1'],  # Provide origin to avoid second BFS call
        )

        # All three should be called
        assert mock_fulltext.call_count == 1, 'bm25/fulltext search should be called once'
        assert mock_similarity.call_count == 1, 'similarity search should be called once'
        assert mock_bfs.call_count == 1, 'bfs search should be called once'


@pytest.mark.asyncio
async def test_node_search_respects_bm25_only_config():
    """When only bm25 is configured for node search, only fulltext search should be called."""
    mock_driver = AsyncMock()
    mock_cross_encoder = AsyncMock()

    config = NodeSearchConfig(
        search_methods=[NodeSearchMethod.bm25],
        reranker=NodeReranker.rrf,
    )

    with (
        patch('graphiti_core.search.search.node_fulltext_search') as mock_fulltext,
        patch('graphiti_core.search.search.node_similarity_search') as mock_similarity,
        patch('graphiti_core.search.search.node_bfs_search') as mock_bfs,
        patch('graphiti_core.search.search.rrf') as mock_rrf,
    ):
        mock_fulltext.return_value = []
        mock_similarity.return_value = []
        mock_bfs.return_value = []
        mock_rrf.return_value = []

        await node_search(
            driver=mock_driver,
            cross_encoder=mock_cross_encoder,
            query='test query',
            query_vector=[0.1, 0.2, 0.3],
            group_ids=None,
            config=config,
            search_filter=SearchFilters(),
        )

        # Only fulltext (bm25) should be called
        assert mock_fulltext.call_count == 1, 'bm25/fulltext search should be called once'
        assert mock_similarity.call_count == 0, 'similarity search should NOT be called'
        assert mock_bfs.call_count == 0, 'bfs search should NOT be called'


@pytest.mark.asyncio
async def test_node_search_respects_hybrid_config():
    """When bm25 and cosine_similarity are configured for node search, both should be called."""
    mock_driver = AsyncMock()
    mock_cross_encoder = AsyncMock()

    config = NodeSearchConfig(
        search_methods=[NodeSearchMethod.bm25, NodeSearchMethod.cosine_similarity],
        reranker=NodeReranker.rrf,
    )

    with (
        patch('graphiti_core.search.search.node_fulltext_search') as mock_fulltext,
        patch('graphiti_core.search.search.node_similarity_search') as mock_similarity,
        patch('graphiti_core.search.search.node_bfs_search') as mock_bfs,
        patch('graphiti_core.search.search.rrf') as mock_rrf,
    ):
        mock_fulltext.return_value = []
        mock_similarity.return_value = []
        mock_bfs.return_value = []
        mock_rrf.return_value = []

        await node_search(
            driver=mock_driver,
            cross_encoder=mock_cross_encoder,
            query='test query',
            query_vector=[0.1, 0.2, 0.3],
            group_ids=None,
            config=config,
            search_filter=SearchFilters(),
        )

        # Both fulltext and similarity should be called, but not bfs
        assert mock_fulltext.call_count == 1, 'bm25/fulltext search should be called once'
        assert mock_similarity.call_count == 1, 'similarity search should be called once'
        assert mock_bfs.call_count == 0, 'bfs search should NOT be called'
