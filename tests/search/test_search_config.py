"""
Tests for search configuration models and enums.

Copyright 2024, Zep Software, Inc.
Licensed under the Apache License, Version 2.0.
"""

import pytest
from pydantic import ValidationError

from graphiti_core.search.search_config import (
    DEFAULT_SEARCH_LIMIT,
    CommunityReranker,
    CommunitySearchConfig,
    CommunitySearchMethod,
    EdgeReranker,
    EdgeSearchConfig,
    EdgeSearchMethod,
    EpisodeReranker,
    EpisodeSearchConfig,
    EpisodeSearchMethod,
    NodeReranker,
    NodeSearchConfig,
    NodeSearchMethod,
    SearchConfig,
    SearchResults,
)
from graphiti_core.search.search_utils import (
    DEFAULT_MIN_SCORE,
    DEFAULT_MMR_LAMBDA,
    MAX_SEARCH_DEPTH,
)


class TestEdgeSearchMethod:
    """Tests for EdgeSearchMethod enum."""

    def test_cosine_similarity_value(self):
        assert EdgeSearchMethod.cosine_similarity.value == 'cosine_similarity'

    def test_bm25_value(self):
        assert EdgeSearchMethod.bm25.value == 'bm25'

    def test_bfs_value(self):
        assert EdgeSearchMethod.bfs.value == 'breadth_first_search'

    def test_all_methods_defined(self):
        methods = list(EdgeSearchMethod)
        assert len(methods) == 4
        assert EdgeSearchMethod.cosine_similarity in methods
        assert EdgeSearchMethod.bm25 in methods
        assert EdgeSearchMethod.bfs in methods
        assert EdgeSearchMethod.hipporag in methods


class TestNodeSearchMethod:
    """Tests for NodeSearchMethod enum."""

    def test_cosine_similarity_value(self):
        assert NodeSearchMethod.cosine_similarity.value == 'cosine_similarity'

    def test_bm25_value(self):
        assert NodeSearchMethod.bm25.value == 'bm25'

    def test_bfs_value(self):
        assert NodeSearchMethod.bfs.value == 'breadth_first_search'


class TestEpisodeSearchMethod:
    """Tests for EpisodeSearchMethod enum."""

    def test_bm25_value(self):
        assert EpisodeSearchMethod.bm25.value == 'bm25'

    def test_only_bm25_available(self):
        methods = list(EpisodeSearchMethod)
        assert len(methods) == 1


class TestCommunitySearchMethod:
    """Tests for CommunitySearchMethod enum."""

    def test_cosine_similarity_value(self):
        assert CommunitySearchMethod.cosine_similarity.value == 'cosine_similarity'

    def test_bm25_value(self):
        assert CommunitySearchMethod.bm25.value == 'bm25'


class TestEdgeReranker:
    """Tests for EdgeReranker enum."""

    def test_rrf_value(self):
        assert EdgeReranker.rrf.value == 'reciprocal_rank_fusion'

    def test_node_distance_value(self):
        assert EdgeReranker.node_distance.value == 'node_distance'

    def test_episode_mentions_value(self):
        assert EdgeReranker.episode_mentions.value == 'episode_mentions'

    def test_mmr_value(self):
        assert EdgeReranker.mmr.value == 'mmr'

    def test_cross_encoder_value(self):
        assert EdgeReranker.cross_encoder.value == 'cross_encoder'

    def test_all_rerankers_defined(self):
        rerankers = list(EdgeReranker)
        assert len(rerankers) == 6


class TestNodeReranker:
    """Tests for NodeReranker enum."""

    def test_rrf_value(self):
        assert NodeReranker.rrf.value == 'reciprocal_rank_fusion'

    def test_all_rerankers_match_edge_rerankers(self):
        # Node and Edge rerankers should have the same options
        node_values = {r.value for r in NodeReranker}
        edge_values = {r.value for r in EdgeReranker}
        assert node_values == edge_values


class TestEpisodeReranker:
    """Tests for EpisodeReranker enum."""

    def test_rrf_value(self):
        assert EpisodeReranker.rrf.value == 'reciprocal_rank_fusion'

    def test_cross_encoder_value(self):
        assert EpisodeReranker.cross_encoder.value == 'cross_encoder'

    def test_limited_options(self):
        rerankers = list(EpisodeReranker)
        assert len(rerankers) == 2


class TestCommunityReranker:
    """Tests for CommunityReranker enum."""

    def test_rrf_value(self):
        assert CommunityReranker.rrf.value == 'reciprocal_rank_fusion'

    def test_mmr_value(self):
        assert CommunityReranker.mmr.value == 'mmr'

    def test_cross_encoder_value(self):
        assert CommunityReranker.cross_encoder.value == 'cross_encoder'


class TestEdgeSearchConfig:
    """Tests for EdgeSearchConfig model."""

    def test_default_reranker(self):
        config = EdgeSearchConfig(search_methods=[EdgeSearchMethod.cosine_similarity])
        assert config.reranker == EdgeReranker.rrf

    def test_default_sim_min_score(self):
        config = EdgeSearchConfig(search_methods=[EdgeSearchMethod.bm25])
        assert config.sim_min_score == DEFAULT_MIN_SCORE

    def test_default_mmr_lambda(self):
        config = EdgeSearchConfig(search_methods=[EdgeSearchMethod.bm25])
        assert config.mmr_lambda == DEFAULT_MMR_LAMBDA

    def test_default_bfs_max_depth(self):
        config = EdgeSearchConfig(search_methods=[EdgeSearchMethod.bfs])
        assert config.bfs_max_depth == MAX_SEARCH_DEPTH

    def test_custom_values(self):
        config = EdgeSearchConfig(
            search_methods=[EdgeSearchMethod.cosine_similarity, EdgeSearchMethod.bm25],
            reranker=EdgeReranker.mmr,
            sim_min_score=0.5,
            mmr_lambda=0.7,
            bfs_max_depth=5,
        )
        assert config.reranker == EdgeReranker.mmr
        assert config.sim_min_score == 0.5
        assert config.mmr_lambda == 0.7
        assert config.bfs_max_depth == 5

    def test_multiple_search_methods(self):
        config = EdgeSearchConfig(
            search_methods=[
                EdgeSearchMethod.cosine_similarity,
                EdgeSearchMethod.bm25,
                EdgeSearchMethod.bfs,
            ]
        )
        assert len(config.search_methods) == 3


class TestNodeSearchConfig:
    """Tests for NodeSearchConfig model."""

    def test_default_values(self):
        config = NodeSearchConfig(search_methods=[NodeSearchMethod.cosine_similarity])
        assert config.reranker == NodeReranker.rrf
        assert config.sim_min_score == DEFAULT_MIN_SCORE
        assert config.mmr_lambda == DEFAULT_MMR_LAMBDA
        assert config.bfs_max_depth == MAX_SEARCH_DEPTH

    def test_custom_reranker(self):
        config = NodeSearchConfig(
            search_methods=[NodeSearchMethod.bm25],
            reranker=NodeReranker.cross_encoder,
        )
        assert config.reranker == NodeReranker.cross_encoder


class TestEpisodeSearchConfig:
    """Tests for EpisodeSearchConfig model."""

    def test_default_values(self):
        config = EpisodeSearchConfig(search_methods=[EpisodeSearchMethod.bm25])
        assert config.reranker == EpisodeReranker.rrf

    def test_cross_encoder_reranker(self):
        config = EpisodeSearchConfig(
            search_methods=[EpisodeSearchMethod.bm25],
            reranker=EpisodeReranker.cross_encoder,
        )
        assert config.reranker == EpisodeReranker.cross_encoder


class TestCommunitySearchConfig:
    """Tests for CommunitySearchConfig model."""

    def test_default_values(self):
        config = CommunitySearchConfig(search_methods=[CommunitySearchMethod.cosine_similarity])
        assert config.reranker == CommunityReranker.rrf

    def test_mmr_reranker(self):
        config = CommunitySearchConfig(
            search_methods=[CommunitySearchMethod.bm25],
            reranker=CommunityReranker.mmr,
        )
        assert config.reranker == CommunityReranker.mmr


class TestSearchConfig:
    """Tests for main SearchConfig model."""

    def test_all_configs_optional(self):
        config = SearchConfig()
        assert config.edge_config is None
        assert config.node_config is None
        assert config.episode_config is None
        assert config.community_config is None

    def test_default_limit(self):
        config = SearchConfig()
        assert config.limit == DEFAULT_SEARCH_LIMIT

    def test_default_reranker_min_score(self):
        config = SearchConfig()
        assert config.reranker_min_score == 0

    def test_custom_limit(self):
        config = SearchConfig(limit=50)
        assert config.limit == 50

    def test_custom_reranker_min_score(self):
        config = SearchConfig(reranker_min_score=0.5)
        assert config.reranker_min_score == 0.5

    def test_with_edge_config(self):
        edge_config = EdgeSearchConfig(search_methods=[EdgeSearchMethod.cosine_similarity])
        config = SearchConfig(edge_config=edge_config)
        assert config.edge_config is not None
        assert config.edge_config.search_methods == [EdgeSearchMethod.cosine_similarity]

    def test_with_node_config(self):
        node_config = NodeSearchConfig(search_methods=[NodeSearchMethod.bm25])
        config = SearchConfig(node_config=node_config)
        assert config.node_config is not None

    def test_with_all_configs(self):
        config = SearchConfig(
            edge_config=EdgeSearchConfig(search_methods=[EdgeSearchMethod.bm25]),
            node_config=NodeSearchConfig(search_methods=[NodeSearchMethod.cosine_similarity]),
            episode_config=EpisodeSearchConfig(search_methods=[EpisodeSearchMethod.bm25]),
            community_config=CommunitySearchConfig(
                search_methods=[CommunitySearchMethod.cosine_similarity]
            ),
            limit=20,
            reranker_min_score=0.3,
        )
        assert config.edge_config is not None
        assert config.node_config is not None
        assert config.episode_config is not None
        assert config.community_config is not None
        assert config.limit == 20
        assert config.reranker_min_score == 0.3


class TestSearchResults:
    """Tests for SearchResults model."""

    def test_empty_results(self):
        results = SearchResults(edges=[], nodes=[], episodes=[], communities=[])
        assert len(results.edges) == 0
        assert len(results.nodes) == 0
        assert len(results.episodes) == 0
        assert len(results.communities) == 0

    def test_results_are_lists(self):
        results = SearchResults(edges=[], nodes=[], episodes=[], communities=[])
        assert isinstance(results.edges, list)
        assert isinstance(results.nodes, list)
        assert isinstance(results.episodes, list)
        assert isinstance(results.communities, list)


class TestSearchConfigRecipes:
    """Tests for search config recipe helpers."""

    def test_edge_only_search_config(self):
        """Test creating a config for edge-only search."""
        config = SearchConfig(
            edge_config=EdgeSearchConfig(
                search_methods=[EdgeSearchMethod.cosine_similarity, EdgeSearchMethod.bm25],
                reranker=EdgeReranker.rrf,
            ),
            limit=10,
        )
        assert config.edge_config is not None
        assert config.node_config is None
        assert len(config.edge_config.search_methods) == 2

    def test_hybrid_search_config(self):
        """Test creating a config for hybrid search across all types."""
        config = SearchConfig(
            edge_config=EdgeSearchConfig(
                search_methods=[EdgeSearchMethod.cosine_similarity],
            ),
            node_config=NodeSearchConfig(
                search_methods=[NodeSearchMethod.cosine_similarity],
            ),
            community_config=CommunitySearchConfig(
                search_methods=[CommunitySearchMethod.cosine_similarity],
            ),
            limit=5,
        )
        assert config.edge_config is not None
        assert config.node_config is not None
        assert config.community_config is not None
