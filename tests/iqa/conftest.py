"""
IQA Framework Test Configuration

Provides fixtures for end-to-end testing of Temporal Activities with:
- Real FalkorDB connection (isolated test database)
- Real or mocked LLM clients
- Activity simulation helpers
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

import pytest
import pytest_asyncio

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.graphiti import Graphiti
from graphiti_core.client_factory import GraphitiClientFactory
from graphiti_core.nodes import EpisodicNode, EntityNode, EpisodeType
from graphiti_core.utils.datetime_utils import utc_now


def pytest_configure(config):
    config.addinivalue_line('markers', 'iqa: IQA framework end-to-end tests')
    config.addinivalue_line('markers', 'iqa_evolution: tests for entity evolution across episodes')
    config.addinivalue_line('markers', 'iqa_dedup: tests for entity deduplication')
    config.addinivalue_line('markers', 'iqa_invalidation: tests for fact invalidation')


@pytest.fixture(scope='session')
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope='session')
def iqa_database_name():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'graphiti_iqa_{timestamp}'


@pytest_asyncio.fixture(scope='function')
async def falkordb_driver(iqa_database_name):
    """
    Provide a FalkorDB driver connected to an isolated test database.
    Database is cleaned after each test.
    """
    driver = FalkorDriver(
        host=os.getenv('FALKORDB_HOST', 'localhost'),
        port=int(os.getenv('FALKORDB_PORT', 6379)),
        database=iqa_database_name,
    )

    yield driver

    try:
        await driver.execute_query('MATCH (n) DETACH DELETE n')
    except Exception:
        pass
    await driver.close()


@pytest_asyncio.fixture(scope='function')
async def graphiti_client(falkordb_driver):
    """
    Provide a fully configured Graphiti client with DSPy enabled.
    Uses real LLM and embedder clients.
    """
    use_dspy = os.getenv('IQA_USE_DSPY', 'true').lower() == 'true'

    if use_dspy:
        client = Graphiti(graph_driver=falkordb_driver, use_dspy=True)
    else:
        llm_client = GraphitiClientFactory.create_llm_client()
        embedder = GraphitiClientFactory.create_embedder()
        client = Graphiti(
            graph_driver=falkordb_driver,
            llm_client=llm_client,
            embedder=embedder,
            use_dspy=False,
        )

    await client.build_indices_and_constraints()

    yield client


@pytest.fixture
def test_group_id():
    return f'iqa_test_{uuid.uuid4().hex[:8]}'


class ActivitySimulator:
    """
    Simulates Temporal workflow data passing between activities.

    Catches serialization bugs by round-tripping data through JSON
    (mimicking Temporal's serialization boundaries).
    """

    def __init__(self, graphiti: Graphiti):
        self.graphiti = graphiti
        self.state: dict[str, Any] = {}
        self._activities = None

    def _get_activities(self):
        if self._activities is None:
            from graphiti_core.utils.temporal_visibility.activities import IngestionActivities

            async def graphiti_factory():
                return self.graphiti

            self._activities = IngestionActivities(graphiti_factory=graphiti_factory)
        return self._activities

    def _serialize_roundtrip(self, data: Any) -> Any:
        """Simulate Temporal serialization boundary."""
        return json.loads(json.dumps(data, default=str))

    async def extract_nodes(
        self,
        episode_uuid: str,
        group_id: str,
        episode_content: str,
        episode_name: str,
        source: str = 'message',
        reference_time: str | None = None,
    ) -> dict[str, Any]:
        """Simulate extract_nodes activity."""
        activities = self._get_activities()
        ref_time = reference_time or utc_now().isoformat()

        result = await activities.extract_nodes(
            episode_uuid=episode_uuid,
            group_id=group_id,
            episode_content=episode_content,
            episode_name=episode_name,
            source=source,
            source_description='IQA test',
            reference_time=ref_time,
            entity_types=None,
            excluded_entity_types=None,
            previous_episode_uuids=None,
        )

        return self._serialize_roundtrip(result.__dict__)

    async def resolve_nodes(
        self,
        episode_uuid: str,
        group_id: str,
        extracted_node_dicts: list[dict],
        episode_content: str,
        episode_name: str,
        source: str = 'message',
        reference_time: str | None = None,
    ) -> dict[str, Any]:
        """Simulate resolve_nodes activity."""
        activities = self._get_activities()
        ref_time = reference_time or utc_now().isoformat()

        result = await activities.resolve_nodes(
            episode_uuid=episode_uuid,
            group_id=group_id,
            extracted_node_dicts=self._serialize_roundtrip(extracted_node_dicts),
            episode_content=episode_content,
            episode_name=episode_name,
            source=source,
            source_description='IQA test',
            reference_time=ref_time,
            entity_types=None,
            previous_episode_uuids=None,
        )

        return self._serialize_roundtrip(result.__dict__)

    async def extract_edges(
        self,
        episode_uuid: str,
        group_id: str,
        extracted_node_dicts: list[dict],
        episode_content: str,
        episode_name: str,
        source: str = 'message',
        reference_time: str | None = None,
    ) -> dict[str, Any]:
        """Simulate extract_edges activity."""
        activities = self._get_activities()
        ref_time = reference_time or utc_now().isoformat()

        result = await activities.extract_edges(
            episode_uuid=episode_uuid,
            group_id=group_id,
            extracted_node_dicts=self._serialize_roundtrip(extracted_node_dicts),
            episode_content=episode_content,
            episode_name=episode_name,
            source=source,
            source_description='IQA test',
            reference_time=ref_time,
            edge_types=None,
            edge_type_map=None,
            previous_episode_uuids=None,
        )

        return self._serialize_roundtrip(result.__dict__)

    async def persist(
        self,
        episode_uuid: str,
        group_id: str,
        extracted_node_dicts: list[dict],
        extracted_edge_dicts: list[dict],
        uuid_map: dict[str, str],
        duplicate_node_uuids: list[str],
        episode_content: str,
        episode_name: str,
        source: str = 'message',
        reference_time: str | None = None,
    ) -> dict[str, Any]:
        """Simulate resolve_edges_and_persist activity."""
        activities = self._get_activities()
        ref_time = reference_time or utc_now().isoformat()

        result = await activities.resolve_edges_and_persist(
            episode_uuid=episode_uuid,
            group_id=group_id,
            extracted_node_dicts=self._serialize_roundtrip(extracted_node_dicts),
            extracted_edge_dicts=self._serialize_roundtrip(extracted_edge_dicts),
            uuid_map=self._serialize_roundtrip(uuid_map),
            duplicate_node_uuids=self._serialize_roundtrip(duplicate_node_uuids),
            episode_content=episode_content,
            episode_name=episode_name,
            source=source,
            source_description='IQA test',
            reference_time=ref_time,
            edge_types=None,
            edge_type_map=None,
            previous_episode_uuids=None,
            store_raw_content=True,
        )

        return self._serialize_roundtrip(result.__dict__)

    async def ingest_episode(
        self,
        episode_content: str,
        episode_name: str | None = None,
        group_id: str | None = None,
        source: str = 'message',
    ) -> dict[str, Any]:
        """
        Run full ingestion pipeline for an episode.
        Returns aggregated results from all stages.
        """
        ep_uuid = str(uuid.uuid4())
        ep_name = episode_name or f'episode_{ep_uuid[:8]}'
        grp_id = group_id or f'iqa_test_{uuid.uuid4().hex[:8]}'
        ref_time = utc_now().isoformat()

        extract_result = await self.extract_nodes(
            episode_uuid=ep_uuid,
            group_id=grp_id,
            episode_content=episode_content,
            episode_name=ep_name,
            source=source,
            reference_time=ref_time,
        )

        resolve_result = await self.resolve_nodes(
            episode_uuid=ep_uuid,
            group_id=grp_id,
            extracted_node_dicts=extract_result['extracted_node_dicts'],
            episode_content=episode_content,
            episode_name=ep_name,
            source=source,
            reference_time=ref_time,
        )

        edge_result = await self.extract_edges(
            episode_uuid=ep_uuid,
            group_id=grp_id,
            extracted_node_dicts=extract_result['extracted_node_dicts'],
            episode_content=episode_content,
            episode_name=ep_name,
            source=source,
            reference_time=ref_time,
        )

        persist_result = await self.persist(
            episode_uuid=ep_uuid,
            group_id=grp_id,
            extracted_node_dicts=extract_result['extracted_node_dicts'],
            extracted_edge_dicts=edge_result['extracted_edge_dicts'],
            uuid_map=resolve_result['uuid_map'],
            duplicate_node_uuids=resolve_result['duplicate_node_uuids'],
            episode_content=episode_content,
            episode_name=ep_name,
            source=source,
            reference_time=ref_time,
        )

        return {
            'episode_uuid': ep_uuid,
            'group_id': grp_id,
            'extract': extract_result,
            'resolve': resolve_result,
            'edges': edge_result,
            'persist': persist_result,
        }


@pytest_asyncio.fixture
async def activity_simulator(graphiti_client):
    """Provide an ActivitySimulator instance."""
    return ActivitySimulator(graphiti_client)


async def get_entity_by_name(driver: FalkorDriver, name: str, group_id: str) -> dict | None:
    """Helper to fetch an entity by name."""
    records, _, _ = await driver.execute_query(
        """
        MATCH (n:Entity {group_id: $group_id})
        WHERE toLower(n.name) = toLower($name)
        RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
               n.created_at AS created_at, labels(n) AS labels
        LIMIT 1
        """,
        name=name,
        group_id=group_id,
    )
    if records:
        return dict(records[0])
    return None


async def get_entity_count(driver: FalkorDriver, group_id: str) -> int:
    """Helper to count entities in a group."""
    records, _, _ = await driver.execute_query(
        'MATCH (n:Entity {group_id: $group_id}) RETURN count(n) AS count',
        group_id=group_id,
    )
    if records:
        return records[0]['count']
    return 0


async def get_edge_between(
    driver: FalkorDriver,
    source_name: str,
    target_name: str,
    group_id: str,
) -> list[dict]:
    """Helper to fetch edges between two entities by name."""
    records, _, _ = await driver.execute_query(
        """
        MATCH (s:Entity {group_id: $group_id})-[r:RELATES_TO]->(t:Entity {group_id: $group_id})
        WHERE toLower(s.name) = toLower($source_name) 
          AND toLower(t.name) = toLower($target_name)
        RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact,
               r.created_at AS created_at, r.invalid_at AS invalid_at
        """,
        source_name=source_name,
        target_name=target_name,
        group_id=group_id,
    )
    if records:
        return [dict(r) for r in records]
    return []
