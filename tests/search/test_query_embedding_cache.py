from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graphiti_core.graphiti_types import GraphitiClients
from graphiti_core.search import search as search_module
from graphiti_core.search.search_config import SearchConfig
from graphiti_core.search.search_filters import SearchFilters


@pytest.fixture(autouse=True)
def clear_embedding_cache() -> Iterator[None]:
    search_module._embedding_cache.clear()
    yield
    search_module._embedding_cache.clear()


def _build_clients(embedder: MagicMock) -> GraphitiClients:
    return GraphitiClients.model_construct(
        driver=MagicMock(),
        llm_client=MagicMock(),
        embedder=embedder,
        cross_encoder=MagicMock(),
    )


@pytest.mark.asyncio
async def test_search_uses_cached_query_embedding() -> None:
    embedder = MagicMock()
    embedder.create = AsyncMock(return_value=[0.1, 0.2, 0.3])
    clients = _build_clients(embedder)

    with (
        patch('graphiti_core.search.search.edge_search', new=AsyncMock(return_value=[])),
        patch('graphiti_core.search.search.node_search', new=AsyncMock(return_value=[])),
        patch('graphiti_core.search.search.episode_search', new=AsyncMock(return_value=[])),
        patch('graphiti_core.search.search.community_search', new=AsyncMock(return_value=[])),
    ):
        await search_module.search(clients, 'same query', None, SearchConfig(), SearchFilters())
        await search_module.search(clients, 'same query', None, SearchConfig(), SearchFilters())

    assert embedder.create.await_count == 1


def test_cache_eviction_respects_lru_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_module, '_EMBEDDING_CACHE_MAX', 2)
    monkeypatch.setattr(search_module, '_embedding_cache', OrderedDict())

    search_module._cache_embedding('q1', [1.0])
    search_module._cache_embedding('q2', [2.0])
    assert search_module._get_cached_embedding('q1') == [1.0]

    # q2 is now the least recently used entry.
    search_module._cache_embedding('q3', [3.0])

    assert search_module._get_cached_embedding('q2') is None
    assert search_module._get_cached_embedding('q1') == [1.0]
    assert search_module._get_cached_embedding('q3') == [3.0]


@pytest.mark.asyncio
async def test_manual_cache_invalidation_forces_reembed() -> None:
    embedder = MagicMock()
    embedder.create = AsyncMock(return_value=[0.1, 0.2, 0.3])
    clients = _build_clients(embedder)

    with (
        patch('graphiti_core.search.search.edge_search', new=AsyncMock(return_value=[])),
        patch('graphiti_core.search.search.node_search', new=AsyncMock(return_value=[])),
        patch('graphiti_core.search.search.episode_search', new=AsyncMock(return_value=[])),
        patch('graphiti_core.search.search.community_search', new=AsyncMock(return_value=[])),
    ):
        await search_module.search(clients, 'invalidate me', None, SearchConfig(), SearchFilters())
        search_module._embedding_cache.clear()
        await search_module.search(clients, 'invalidate me', None, SearchConfig(), SearchFilters())

    assert embedder.create.await_count == 2
