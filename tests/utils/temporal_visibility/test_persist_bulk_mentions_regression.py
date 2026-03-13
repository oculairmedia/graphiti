from datetime import datetime, timezone
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest  # type: ignore

from graphiti_core.driver.driver import GraphDriverSession
from graphiti_core.edges import EpisodicEdge
from graphiti_core.models.edges.edge_db_queries import EPISODIC_EDGE_SAVE_BULK
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
from graphiti_core.utils.bulk_utils import add_nodes_and_edges_bulk_tx


class FakeTx:
    def __init__(self, fail_uuid: str | None = None):
        self.fail_uuid = fail_uuid
        self.attempted_entity_node_uuids: list[str] = []
        self.saved_entity_node_uuids: set[str] = set()
        self.fallback_entity_node_uuids: list[str] = []

    async def run(self, query: str, **params):
        if 'UNWIND $nodes AS node' in query and 'MERGE (n:Entity {uuid: node.uuid})' in query:
            node = params['nodes'][0]
            node_uuid = node['uuid']
            self.attempted_entity_node_uuids.append(node_uuid)
            if self.fail_uuid == node_uuid:
                raise Exception(
                    'mandatory constraint violation: node with label Entity missing property name'
                )
            self.saved_entity_node_uuids.add(node_uuid)
            return [{'uuid': node_uuid}]

        if 'CREATE (n:Entity {uuid: $uuid, name: $name, group_id: $group_id})' in query:
            node_uuid = params['uuid']
            self.fallback_entity_node_uuids.append(node_uuid)
            self.saved_entity_node_uuids.add(node_uuid)
            return [{'uuid': node_uuid}]

        if 'MATCH (n:Entity {uuid: $uuid})' in query and 'SET n.name = COALESCE' in query:
            node_uuid = params['uuid']
            self.fallback_entity_node_uuids.append(node_uuid)
            self.saved_entity_node_uuids.add(node_uuid)
            return [{'uuid': node_uuid}]

        if query == EPISODIC_EDGE_SAVE_BULK:
            saved = []
            for edge in params['episodic_edges']:
                if edge['target_node_uuid'] in self.saved_entity_node_uuids:
                    saved.append({'uuid': edge['uuid']})
            return saved

        if 'UNWIND $entity_edges AS edge' in query:
            return [{'uuid': edge['uuid']} for edge in params.get('entity_edges', [])]

        if 'MATCH (src)-[e:MENTIONS]->(tgt)' in query:
            return []

        if 'MATCH (src:Entity)-[e:RELATES_TO]->(tgt:Entity)' in query:
            return []

        return []


def _build_episode(now: datetime, group_id: str) -> EpisodicNode:
    return EpisodicNode(
        uuid=str(uuid4()),
        name='episode',
        group_id=group_id,
        labels=['Episodic'],
        source=EpisodeType.message,
        source_description='source',
        content='content',
        valid_at=now,
        created_at=now,
    )


def _build_entity(now: datetime, group_id: str, name: str, attrs: dict | None = None) -> EntityNode:
    return EntityNode(
        uuid=str(uuid4()),
        name=name,
        group_id=group_id,
        labels=['Entity'],
        created_at=now,
        summary='',
        name_embedding=[0.1, 0.2],
        attributes=attrs or {},
    )


def _build_mentions(
    now: datetime, group_id: str, episode_uuid: str, target_uuid: str
) -> EpisodicEdge:
    return EpisodicEdge(
        uuid=str(uuid4()),
        group_id=group_id,
        source_node_uuid=episode_uuid,
        target_node_uuid=target_uuid,
        created_at=now,
    )


@pytest.mark.asyncio
async def test_entity_node_save_failure_does_not_abort_remaining_nodes(caplog):
    now = datetime.now(timezone.utc)
    group_id = 'test_group'
    episode = _build_episode(now, group_id)
    bad_node = _build_entity(now, group_id, 'bad-name')
    good_node = _build_entity(now, group_id, 'good-name')
    mentions = [
        _build_mentions(now, group_id, episode.uuid, bad_node.uuid),
        _build_mentions(now, group_id, episode.uuid, good_node.uuid),
    ]

    tx = FakeTx(fail_uuid=bad_node.uuid)

    await add_nodes_and_edges_bulk_tx(
        tx=cast(GraphDriverSession, tx),
        episodic_nodes=[episode],
        episodic_edges=mentions,
        entity_nodes=[bad_node, good_node],
        entity_edges=[],
        embedder=MagicMock(),
        driver=MagicMock(),
    )

    assert bad_node.uuid in tx.attempted_entity_node_uuids
    assert good_node.uuid in tx.attempted_entity_node_uuids
    assert bad_node.uuid in tx.fallback_entity_node_uuids
    assert bad_node.uuid in tx.saved_entity_node_uuids
    assert good_node.uuid in tx.saved_entity_node_uuids
    assert 'Retried entity node save via explicit CREATE' in caplog.text
    assert 'MENTIONS persist mismatch' not in caplog.text


@pytest.mark.asyncio
async def test_invalid_name_from_attributes_is_filtered_before_entity_save(caplog):
    now = datetime.now(timezone.utc)
    group_id = 'test_group'
    episode = _build_episode(now, group_id)
    invalid_from_attributes = _build_entity(now, group_id, 'kept-name', attrs={'name': None})
    valid_node = _build_entity(now, group_id, 'valid-name')
    mentions = [
        _build_mentions(now, group_id, episode.uuid, invalid_from_attributes.uuid),
        _build_mentions(now, group_id, episode.uuid, valid_node.uuid),
    ]

    tx = FakeTx()

    await add_nodes_and_edges_bulk_tx(
        tx=cast(GraphDriverSession, tx),
        episodic_nodes=[episode],
        episodic_edges=mentions,
        entity_nodes=[invalid_from_attributes, valid_node],
        entity_edges=[],
        embedder=MagicMock(),
        driver=MagicMock(),
    )

    assert invalid_from_attributes.uuid not in tx.attempted_entity_node_uuids
    assert valid_node.uuid in tx.attempted_entity_node_uuids
    assert 'Skipping 1 entity nodes with invalid/empty name' in caplog.text
