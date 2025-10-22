import datetime

import pytest

from graphiti_core.driver.driver import GraphDriver, GraphDriverSession
from graphiti_core.edges import EntityEdge
from graphiti_core.search.search import SearchFilters
from graphiti_core.search.search_utils import (
    DEFAULT_MIN_SCORE,
    RELEVANT_SCHEMA_LIMIT,
    get_edge_invalidation_candidates_single,
)


class _FakeDriverSession(GraphDriverSession):
    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def run(self, query: str, **kwargs):
        raise NotImplementedError

    async def close(self):
        return None

    async def execute_write(self, func, *args, **kwargs):
        raise NotImplementedError


class FakeDriver(GraphDriver):
    provider: str = "falkordb"

    def __init__(self, records):
        self._records = records
        self.captured_queries: list[tuple[str, dict]] = []

    async def execute_query(self, cypher_query_, **kwargs):  # type: ignore[override]
        params = kwargs.get("params", {})
        self.captured_queries.append((cypher_query_, params))
        return self._records, [], None

    def session(self, database: str | None = None) -> GraphDriverSession:  # type: ignore[override]
        return _FakeDriverSession()

    async def close(self):  # type: ignore[override]
        return None

    async def delete_all_indexes(self, database_: str | None = None):  # type: ignore[override]
        raise NotImplementedError


@pytest.mark.asyncio
async def test_get_edge_invalidation_candidates_single_returns_entities():
    record_created_at = "2025-01-01T00:00:00Z"
    fake_records = [
        {
            "uuid": "22222222-2222-2222-2222-222222222222",
            "group_id": "test_group",
            "source_node_uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "target_node_uuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "created_at": record_created_at,
            "name": "relates_to",
            "fact": "Edge fact",
            "fact_embedding": [0.3, 0.4],
            "episodes": ["11111111-1111-1111-1111-111111111111"],
            "expired_at": None,
            "valid_at": None,
            "invalid_at": None,
            "attributes": {"weight": 1.0},
        }
    ]

    driver = FakeDriver(fake_records)

    edge = EntityEdge(
        uuid="11111111-1111-1111-1111-111111111111",
        source_node_uuid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        target_node_uuid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        group_id="test_group",
        name="relates_to",
        fact="Edge fact",
        fact_embedding=[0.1, 0.2],
        episodes=[],
        created_at=datetime.datetime.utcnow(),
        valid_at=None,
        invalid_at=None,
        expired_at=None,
    )

    results = await get_edge_invalidation_candidates_single(
        driver=driver,
        edge=edge,
        search_filter=SearchFilters(),
        min_score=DEFAULT_MIN_SCORE,
        limit=RELEVANT_SCHEMA_LIMIT,
    )

    assert len(results) == 1
    candidate = results[0]
    assert candidate.uuid == "22222222-2222-2222-2222-222222222222"
    assert candidate.group_id == "test_group"
    # verify helper stripped duplicated metadata keys from attributes dict
    assert "weight" in candidate.attributes

    captured_query, captured_params = driver.captured_queries[-1]
    assert "$embedding" in captured_query
    assert captured_params["embedding"] == [0.1, 0.2]
