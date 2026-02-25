from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from graphiti_core.search.search_config import (
    EdgeReranker,
    EdgeSearchConfig,
    EdgeSearchMethod,
    NodeReranker,
    NodeSearchConfig,
    NodeSearchMethod,
)
from graphiti_core.search.search_config_recipes import (
    EDGE_HYBRID_SEARCH_CENTRALITY,
    NODE_HYBRID_SEARCH_CENTRALITY,
)
from graphiti_core.search.search_utils import centrality_reranker


class TestCentralityReranker(IsolatedAsyncioTestCase):
    async def test_centrality_reranker_boosts_high_centrality_nodes(self):
        driver = AsyncMock()
        driver.execute_query = AsyncMock(
            return_value=(
                [
                    {'uuid': 'node-a', 'importance': 0.1, 'pagerank': 0.1, 'degree': 1},
                    {'uuid': 'node-b', 'importance': 0.9, 'pagerank': 0.9, 'degree': 12},
                ],
                [],
                None,
            )
        )

        ranked = await centrality_reranker(
            driver,
            [['node-a', 'node-b'], ['node-a', 'node-b']],
            boost_factor=0.5,
        )

        self.assertEqual(ranked[:2], ['node-b', 'node-a'])

    async def test_centrality_reranker_all_zero_preserves_rrf_ordering(self):
        driver = AsyncMock()
        driver.execute_query = AsyncMock(
            return_value=(
                [
                    {'uuid': 'node-a', 'importance': 0.0, 'pagerank': 0.0, 'degree': 0},
                    {'uuid': 'node-b', 'importance': 0.0, 'pagerank': 0.0, 'degree': 0},
                    {'uuid': 'node-c', 'importance': 0.0, 'pagerank': 0.0, 'degree': 0},
                ],
                [],
                None,
            )
        )

        ranked = await centrality_reranker(
            driver,
            [['node-a', 'node-b', 'node-c'], ['node-a', 'node-b', 'node-c']],
            boost_factor=0.7,
        )

        self.assertEqual(ranked, ['node-a', 'node-b', 'node-c'])

    async def test_centrality_reranker_handles_missing_centrality_records(self):
        driver = AsyncMock()
        driver.execute_query = AsyncMock(
            return_value=(
                [
                    {'uuid': 'node-a', 'importance': 0.2, 'pagerank': 0.2, 'degree': 2},
                ],
                [],
                None,
            )
        )

        ranked = await centrality_reranker(
            driver,
            [['node-a', 'node-b']],
            boost_factor=1.0,
        )

        self.assertEqual(ranked, ['node-a', 'node-b'])

    async def test_centrality_boost_factor_extremes(self):
        driver = AsyncMock()
        driver.execute_query = AsyncMock(
            return_value=(
                [
                    {'uuid': 'node-a', 'importance': 0.0, 'pagerank': 0.0, 'degree': 0},
                    {'uuid': 'node-b', 'importance': 1.0, 'pagerank': 1.0, 'degree': 10},
                ],
                [],
                None,
            )
        )

        pure_rrf = await centrality_reranker(
            driver,
            [['node-a', 'node-b']],
            boost_factor=0.0,
        )
        pure_centrality = await centrality_reranker(
            driver,
            [['node-a', 'node-b']],
            boost_factor=1.0,
        )

        self.assertEqual(pure_rrf, ['node-a', 'node-b'])
        self.assertEqual(pure_centrality, ['node-b', 'node-a'])


def test_new_centrality_reranker_enums_exist():
    assert EdgeReranker.centrality.value == 'centrality'
    assert NodeReranker.centrality.value == 'centrality'


def test_new_centrality_recipes_instantiate_correctly():
    assert EDGE_HYBRID_SEARCH_CENTRALITY.edge_config is not None
    assert EDGE_HYBRID_SEARCH_CENTRALITY.edge_config.reranker == EdgeReranker.centrality
    assert NODE_HYBRID_SEARCH_CENTRALITY.node_config is not None
    assert NODE_HYBRID_SEARCH_CENTRALITY.node_config.reranker == NodeReranker.centrality


def test_edge_and_node_search_config_accept_centrality_boost_factor():
    edge_config = EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.bm25],
        reranker=EdgeReranker.centrality,
        centrality_boost_factor=0.55,
    )
    node_config = NodeSearchConfig(
        search_methods=[NodeSearchMethod.bm25],
        reranker=NodeReranker.centrality,
        centrality_boost_factor=0.8,
    )

    assert edge_config.centrality_boost_factor == 0.55
    assert node_config.centrality_boost_factor == 0.8
