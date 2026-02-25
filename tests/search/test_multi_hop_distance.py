"""Tests for multi-hop node distance reranking.

Verifies that node_distance_reranker() uses shortest path to compute
actual multi-hop distances instead of only checking direct neighbors.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from graphiti_core.search.search_config import (
    EdgeSearchConfig,
    EdgeSearchMethod,
    NodeSearchConfig,
    NodeSearchMethod,
)
from graphiti_core.search.search_utils import MAX_SEARCH_DEPTH, node_distance_reranker


def _make_driver(query_results: list[dict]) -> MagicMock:
    """Create a mock GraphDriver that returns specified query results."""
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=(query_results, None, None))
    return driver


class TestMultiHopDistanceRanking:
    """Tests for multi-hop shortest path distance ranking."""

    @pytest.mark.asyncio
    async def test_nodes_ranked_by_distance(self):
        """Nodes at distance 1, 2, 3 should be ranked in ascending order."""
        results = [
            {'uuid': 'node-1', 'distance': 1},
            {'uuid': 'node-2', 'distance': 2},
            {'uuid': 'node-3', 'distance': 3},
        ]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['node-1', 'node-2', 'node-3'],
            'center',
        )

        assert ranked == ['node-1', 'node-2', 'node-3']

    @pytest.mark.asyncio
    async def test_closer_nodes_rank_higher(self):
        """2-hop node ranks above 3-hop node, regardless of input order."""
        results = [
            {'uuid': 'far', 'distance': 3},
            {'uuid': 'close', 'distance': 1},
            {'uuid': 'mid', 'distance': 2},
        ]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['far', 'mid', 'close'],
            'center',
        )

        assert ranked == ['close', 'mid', 'far']

    @pytest.mark.asyncio
    async def test_unreachable_nodes_rank_last(self):
        """Disconnected nodes (distance=-1) rank below reachable ones."""
        results = [
            {'uuid': 'reachable', 'distance': 2},
            {'uuid': 'unreachable', 'distance': -1},
        ]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['unreachable', 'reachable'],
            'center',
        )

        assert ranked == ['reachable', 'unreachable']

    @pytest.mark.asyncio
    async def test_center_node_ranks_first(self):
        """Center node always gets distance 0 and ranks first."""
        results = [
            {'uuid': 'other', 'distance': 1},
        ]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['other', 'center'],
            'center',
        )

        assert ranked[0] == 'center'
        assert 'other' in ranked

    @pytest.mark.asyncio
    async def test_center_node_not_in_candidates(self):
        """Center node not in input list means it's not in output."""
        results = [
            {'uuid': 'node-a', 'distance': 1},
        ]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['node-a'],
            'center',
        )

        assert ranked == ['node-a']
        assert 'center' not in ranked


class TestDistanceScoring:
    """Tests for distance scoring formula: score = 1/(distance+1)."""

    @pytest.mark.asyncio
    async def test_min_score_filters_distant_nodes(self):
        """min_score=0.34 should exclude nodes at distance 3+ (score 0.25)."""
        results = [
            {'uuid': 'close', 'distance': 1},  # score = 0.5
            {'uuid': 'far', 'distance': 3},  # score = 0.25
        ]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['close', 'far'],
            'center',
            min_score=0.34,
        )

        assert 'close' in ranked
        assert 'far' not in ranked

    @pytest.mark.asyncio
    async def test_min_score_zero_includes_all(self):
        """min_score=0 should include all nodes including unreachable."""
        results = [
            {'uuid': 'close', 'distance': 1},
            {'uuid': 'unreachable', 'distance': -1},
        ]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['close', 'unreachable'],
            'center',
            min_score=0,
        )

        assert len(ranked) == 2


class TestMaxHopsParameter:
    """Tests for max_hops parameter."""

    @pytest.mark.asyncio
    async def test_max_hops_default(self):
        """Default max_hops should be MAX_SEARCH_DEPTH (3)."""
        driver = _make_driver([])

        await node_distance_reranker(driver, ['node-a'], 'center')

        # Verify the query contains the default max hops
        call_args = driver.execute_query.call_args
        query = call_args[0][0]
        assert f'*..{MAX_SEARCH_DEPTH}]' in query

    @pytest.mark.asyncio
    async def test_max_hops_custom(self):
        """Custom max_hops should be used in the query."""
        driver = _make_driver([])

        await node_distance_reranker(driver, ['node-a'], 'center', max_hops=5)

        call_args = driver.execute_query.call_args
        query = call_args[0][0]
        assert '*..5]' in query

    @pytest.mark.asyncio
    async def test_max_hops_1_equivalent_to_direct(self):
        """max_hops=1 should only find direct neighbors."""
        results = [
            {'uuid': 'neighbor', 'distance': 1},
        ]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['neighbor'],
            'center',
            max_hops=1,
        )

        call_args = driver.execute_query.call_args
        query = call_args[0][0]
        assert '*..1]' in query
        assert ranked == ['neighbor']


class TestDistanceMaxHopsConfig:
    """Tests for distance_max_hops field in search configs."""

    def test_edge_config_has_distance_max_hops(self):
        """EdgeSearchConfig should have distance_max_hops field."""
        config = EdgeSearchConfig(search_methods=[EdgeSearchMethod.bm25])
        assert hasattr(config, 'distance_max_hops')
        assert config.distance_max_hops == MAX_SEARCH_DEPTH

    def test_node_config_has_distance_max_hops(self):
        """NodeSearchConfig should have distance_max_hops field."""
        config = NodeSearchConfig(search_methods=[NodeSearchMethod.bm25])
        assert hasattr(config, 'distance_max_hops')
        assert config.distance_max_hops == MAX_SEARCH_DEPTH

    def test_custom_distance_max_hops(self):
        """Can set custom distance_max_hops."""
        config = NodeSearchConfig(
            search_methods=[NodeSearchMethod.bm25],
            distance_max_hops=5,
        )
        assert config.distance_max_hops == 5

    def test_distance_max_hops_serialization(self):
        """distance_max_hops should serialize correctly."""
        config = EdgeSearchConfig(
            search_methods=[EdgeSearchMethod.cosine_similarity],
            distance_max_hops=7,
        )
        data = config.model_dump()
        assert data['distance_max_hops'] == 7


class TestEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_empty_candidates(self):
        """Empty node list returns empty results."""
        driver = _make_driver([])

        ranked = await node_distance_reranker(driver, [], 'center')

        assert ranked == []

    @pytest.mark.asyncio
    async def test_single_candidate(self):
        """Single node candidate should be returned."""
        results = [{'uuid': 'only-node', 'distance': 1}]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(driver, ['only-node'], 'center')

        assert ranked == ['only-node']

    @pytest.mark.asyncio
    async def test_all_unreachable(self):
        """All unreachable nodes still returned (in original order)."""
        results = [
            {'uuid': 'a', 'distance': -1},
            {'uuid': 'b', 'distance': -1},
        ]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['a', 'b'],
            'center',
        )

        assert set(ranked) == {'a', 'b'}

    @pytest.mark.asyncio
    async def test_duplicate_uuids_handled(self):
        """Duplicate UUIDs in input don't cause issues."""
        results = [{'uuid': 'node-a', 'distance': 1}]
        driver = _make_driver(results)

        ranked = await node_distance_reranker(
            driver,
            ['node-a', 'node-a'],
            'center',
        )

        # Both instances appear since we don't deduplicate input
        assert 'node-a' in ranked
