import importlib
from unittest.mock import AsyncMock, MagicMock, patch

from graphiti_core.nodes import EntityNode
from graphiti_core.search.search import node_search
from graphiti_core.search.search_config import NodeReranker, NodeSearchConfig, NodeSearchMethod
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_COMMUNITY_BOOSTED
from graphiti_core.search.search_filters import SearchFilters
from graphiti_core.search.search_utils import community_boost_search

pytest = importlib.import_module('pytest')


def _entity_node(uuid: str, name: str, group_id: str = 'g1'):
    return {
        'uuid': uuid,
        'name': name,
        'group_id': group_id,
        'labels': ['Person'],
        'created_at': '2025-01-01T00:00:00',
        'summary': f'{name} summary',
    }


class TestCommunityBoostConfig:
    def test_community_boost_enum_exists(self):
        assert hasattr(NodeSearchMethod, 'community_boost')
        assert NodeSearchMethod.community_boost.value == 'community_boost'

    def test_community_boost_limit_default(self):
        config = NodeSearchConfig(search_methods=[NodeSearchMethod.community_boost])
        assert config.community_boost_limit == 5

    def test_community_boost_limit_custom(self):
        config = NodeSearchConfig(
            search_methods=[NodeSearchMethod.community_boost],
            community_boost_limit=9,
        )
        assert config.community_boost_limit == 9


class TestCommunityBoostSearch:
    @pytest.mark.asyncio
    async def test_community_boost_search_returns_members(self):
        driver = MagicMock()
        driver.execute_query = AsyncMock(
            return_value=(
                [
                    {
                        'uuid': '11111111-1111-1111-1111-111111111111',
                        'name': 'Alice',
                        'group_id': 'g1',
                        'labels': ['Person'],
                        'created_at': '2025-01-01T00:00:00',
                        'summary': 'A person',
                    },
                    {
                        'uuid': '22222222-2222-2222-2222-222222222222',
                        'name': 'Bob',
                        'group_id': 'g1',
                        'labels': ['Person'],
                        'created_at': '2025-01-01T00:00:00',
                        'summary': 'Another person',
                    },
                ],
                None,
                None,
            )
        )

        nodes = await community_boost_search(
            driver,
            ['community-1'],
            SearchFilters(),
            group_ids=None,
            limit=10,
        )

        assert len(nodes) == 2
        assert nodes[0].uuid == '11111111-1111-1111-1111-111111111111'
        assert nodes[1].uuid == '22222222-2222-2222-2222-222222222222'

    @pytest.mark.asyncio
    async def test_community_boost_search_empty_communities(self):
        driver = MagicMock()
        driver.execute_query = AsyncMock()

        nodes = await community_boost_search(driver, [], SearchFilters(), group_ids=None, limit=10)

        assert nodes == []
        driver.execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_community_boost_search_with_group_filter(self):
        driver = MagicMock()
        driver.execute_query = AsyncMock(return_value=([], None, None))

        await community_boost_search(
            driver,
            ['community-1'],
            SearchFilters(),
            group_ids=['g1'],
            limit=10,
        )

        args = driver.execute_query.call_args.args
        kwargs = driver.execute_query.call_args.kwargs
        assert 'AND n.group_id IN $group_ids' in args[0]
        assert kwargs['group_ids'] == ['g1']


class TestCommunityBoostNodeSearchIntegration:
    @pytest.mark.asyncio
    async def test_community_boost_deduplication_via_uuid_map(self):
        config = NodeSearchConfig(
            search_methods=[NodeSearchMethod.bm25, NodeSearchMethod.community_boost],
            reranker=NodeReranker.rrf,
        )

        with (
            patch(
                'graphiti_core.search.search.node_fulltext_search', new_callable=AsyncMock
            ) as bm25_mock,
            patch(
                'graphiti_core.search.search.community_fulltext_search', new_callable=AsyncMock
            ) as community_fulltext_mock,
            patch(
                'graphiti_core.search.search.community_boost_search', new_callable=AsyncMock
            ) as community_boost_mock,
        ):
            bm25_mock.return_value = [
                EntityNode(**_entity_node('11111111-1111-1111-1111-111111111111', 'Alice'))
            ]
            community_fulltext_mock.return_value = [MagicMock(uuid='community-1')]
            community_boost_mock.return_value = [
                EntityNode(**_entity_node('11111111-1111-1111-1111-111111111111', 'Alice')),
                EntityNode(**_entity_node('22222222-2222-2222-2222-222222222222', 'Bob')),
            ]

            nodes = await node_search(
                driver=MagicMock(),
                cross_encoder=MagicMock(),
                query='alice',
                query_vector=[0.1, 0.2],
                group_ids=['g1'],
                config=config,
                search_filter=SearchFilters(),
                limit=10,
            )

        uuids = [node.uuid for node in nodes]
        assert len(uuids) == len(set(uuids))
        assert '11111111-1111-1111-1111-111111111111' in uuids
        assert '22222222-2222-2222-2222-222222222222' in uuids


class TestCommunityBoostRecipes:
    def test_community_boost_recipe_exists(self):
        recipe = NODE_HYBRID_SEARCH_COMMUNITY_BOOSTED
        assert recipe.node_config is not None
        assert NodeSearchMethod.community_boost in recipe.node_config.search_methods
        assert recipe.node_config.reranker == NodeReranker.rrf
