
import pytest
from datetime import datetime, timezone
from types import SimpleNamespace

from sync_service.extractors.falkordb_extractor import FalkorDBExtractor


class StubGraph:
    """Minimal async graph stub that records queries and returns preset result sets."""

    def __init__(self, result_sets):
        self._result_sets = list(result_sets)
        self.queries = []

    async def query(self, query: str):
        self.queries.append(query)
        if self._result_sets:
            result_set = self._result_sets.pop(0)
        else:
            result_set = []
        return SimpleNamespace(result_set=result_set)


@pytest.mark.asyncio
async def test_extract_entity_edges_optimized_uses_direct_access_pattern():
    stub = StubGraph([
        [
            ['edge-1', 'source-1', 'target-1', '2024-01-01T00:00:00Z', '2024-01-02T00:00:00Z', 0.7, None, None],
            ['edge-2', 'source-2', 'target-2', '2024-01-03T00:00:00Z', None, None, None, None],
        ],
        [
            ['edge-3', 'source-3', 'target-3', '2024-01-04T00:00:00Z', '2024-01-05T00:00:00Z', 0.9, '2024-01-04T00:00:00Z', '2024-01-06T00:00:00Z'],
        ],
    ])

    extractor = FalkorDBExtractor(
        batch_size=1,
        max_query_limit=10,
        enable_pagination=True,
        optimization_enabled=True,
        edge_batch_size=2,
        node_batch_size=5,
        memory_threshold_mb=64,
        adaptive_sizing=False,
    )
    extractor.graph = stub

    batches = [batch async for batch in extractor.extract_entity_edges_optimized()]

    assert [len(batch) for batch in batches] == [2, 1]
    first_edge = batches[0][0]
    assert first_edge['uuid'] == 'edge-1'
    assert first_edge['source_node_uuid'] == 'source-1'
    assert first_edge['target_node_uuid'] == 'target-1'
    assert first_edge['relationship_type'] == 'RELATES_TO'
    assert first_edge['created_at'] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert first_edge['updated_at'] == datetime(2024, 1, 2, tzinfo=timezone.utc)

    # Ensure queries use the direct edge access pattern with selective properties
    assert any('MATCH ()-[r:RELATES_TO]->()' in q for q in stub.queries)
    assert all('MATCH (source)-[r:RELATES_TO]->(target)' not in q for q in stub.queries)
    assert all('properties(r)' not in q for q in stub.queries)
    assert 'SKIP 0 LIMIT 2' in stub.queries[0]
    assert len(stub.queries) == 2

    # Validity dates should be converted when present
    assert batches[1][0]['valid_at'] == datetime(2024, 1, 4, tzinfo=timezone.utc)
    assert batches[1][0]['invalid_at'] == datetime(2024, 1, 6, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_extract_entity_edges_honors_limit_with_optimization():
    stub = StubGraph([
        [['edge-limited', 'source-l', 'target-l', '2024-01-07T00:00:00Z', None, None, None, None]],
        [],
    ])

    extractor = FalkorDBExtractor(
        batch_size=1,
        max_query_limit=10,
        enable_pagination=True,
        optimization_enabled=True,
        edge_batch_size=4,
        node_batch_size=5,
        memory_threshold_mb=64,
        adaptive_sizing=False,
    )
    extractor.graph = stub

    batches = [batch async for batch in extractor.extract_entity_edges(limit=1)]
    edges = [edge for batch in batches for edge in batch]

    assert len(edges) == 1
    assert edges[0]['uuid'] == 'edge-limited'
    assert len(stub.queries) == 1
    assert 'LIMIT 1' in stub.queries[0]


@pytest.mark.asyncio
async def test_extract_entity_nodes_orders_by_uuid_instead_of_created_at():
    stub = StubGraph([
        [
            ['node-1', {'uuid': 'node-1', 'created_at': None, 'name': 'Alice'}],
            ['node-2', {'uuid': 'node-2', 'created_at': '2024-01-02T00:00:00Z', 'name': 'Bob'}],
        ],
    ])

    extractor = FalkorDBExtractor(
        batch_size=2,
        max_query_limit=10,
        enable_pagination=True,
        optimization_enabled=True,
        edge_batch_size=4,
        node_batch_size=5,
        memory_threshold_mb=64,
        adaptive_sizing=False,
    )
    extractor.graph = stub

    batches = [batch async for batch in extractor.extract_entity_nodes()]
    nodes = [node for batch in batches for node in batch]

    assert len(nodes) == 2
    assert nodes[0]['uuid'] == 'node-1'
    assert nodes[1]['uuid'] == 'node-2'
    assert any('ORDER BY n.uuid' in q for q in stub.queries)
    assert all('ORDER BY n.created_at' not in q for q in stub.queries)
