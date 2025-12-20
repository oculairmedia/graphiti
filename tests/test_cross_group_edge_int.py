"""
Integration tests for cross-group edge UUID collision prevention.

These tests verify that edges connecting entities from different group_id partitions
generate unique UUIDs that don't collide with edges in other graph partitions.

The fix addresses DuplicateEdgeError when:
- An episode in group A mentions an entity that resolves to group B
- Cross-graph deduplication links entities across groups
- MENTIONS edges connect episodes to entities in different groups

Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging
import os
import sys
import unittest
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
from graphiti_core.helpers import semaphore_gather
from graphiti_core.utils.maintenance.edge_operations import (
    build_episodic_edges,
    build_duplicate_of_edges,
)

# Enable deterministic UUIDs for testing
os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'

try:
    from graphiti_core.driver.falkordb_driver import FalkorDriver

    HAS_FALKORDB = True
except ImportError:
    FalkorDriver = None
    HAS_FALKORDB = False

pytestmark = pytest.mark.integration

pytest_plugins = ('pytest_asyncio',)

load_dotenv()

FALKORDB_HOST = os.getenv('FALKORDB_HOST', 'localhost')
FALKORDB_PORT = int(os.getenv('FALKORDB_PORT', '6379'))
FALKORDB_USER = os.getenv('FALKORDB_USER', None)
FALKORDB_PASSWORD = os.getenv('FALKORDB_PASSWORD', None)

# Test group IDs
GROUP_A = 'test_group_a'
GROUP_B = 'test_group_b'
GROUP_C = 'test_group_c'


def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger


logger = setup_logging()


class TestCrossGroupEpisodicEdgesIntegration:
    """Integration tests for cross-group episodic (MENTIONS) edges."""

    @pytest.mark.asyncio
    @unittest.skipIf(not HAS_FALKORDB, 'FalkorDB is not installed')
    async def test_cross_group_episodic_edges_no_collision(self):
        """
        Test that episodic edges from an episode in group A to entities in groups A, B, C
        all get unique UUIDs and can be saved without collision.
        """
        if FalkorDriver is None:
            pytest.skip('FalkorDB driver not available')

        driver = FalkorDriver(
            host=FALKORDB_HOST,
            port=FALKORDB_PORT,
            username=FALKORDB_USER,
            password=FALKORDB_PASSWORD,
            database='test_cross_group_edges',
        )

        now = datetime.now(timezone.utc)

        # Create test nodes
        episode_group_a = EpisodicNode(
            uuid=str(uuid4()),
            name='Episode in Group A',
            group_id=GROUP_A,
            source=EpisodeType.text,
            source_description='Test episode',
            content='Alice works with Bob on OpenCode project',
            valid_at=now,
        )

        entity_alice_group_a = EntityNode(
            uuid=str(uuid4()),
            name='Alice',
            group_id=GROUP_A,
            labels=['Person'],
            name_embedding=[0.1] * 1024,
            summary='Alice is a developer',
            created_at=now,
        )

        entity_bob_group_b = EntityNode(
            uuid=str(uuid4()),
            name='Bob',
            group_id=GROUP_B,
            labels=['Person'],
            name_embedding=[0.2] * 1024,
            summary='Bob is a developer',
            created_at=now,
        )

        entity_opencode_group_c = EntityNode(
            uuid=str(uuid4()),
            name='OpenCode',
            group_id=GROUP_C,
            labels=['Project'],
            name_embedding=[0.3] * 1024,
            summary='OpenCode is an AI coding assistant',
            created_at=now,
        )

        nodes = [episode_group_a, entity_alice_group_a, entity_bob_group_b, entity_opencode_group_c]
        episodic_edges: list[EpisodicEdge] = []

        try:
            # Save nodes first
            await semaphore_gather(*[node.save(driver) for node in nodes])

            # Build episodic edges using the function under test
            entities = [entity_alice_group_a, entity_bob_group_b, entity_opencode_group_c]
            episodic_edges = build_episodic_edges(
                entity_nodes=entities,
                episode_uuid=episode_group_a.uuid,
                created_at=now,
                episode_group_id=episode_group_a.group_id,
            )

            # Verify all edges have unique UUIDs
            uuids = [edge.uuid for edge in episodic_edges]
            assert len(uuids) == len(set(uuids)), f'Duplicate UUIDs found: {uuids}'

            logger.info(f'Generated {len(episodic_edges)} episodic edges with unique UUIDs')
            for edge in episodic_edges:
                logger.debug(
                    f'Edge UUID: {edge.uuid}, '
                    f'source_group: {edge.source_node_group_id}, '
                    f'target_group: {edge.target_node_group_id}'
                )

            # Save all edges - should not raise DuplicateEdgeError
            await semaphore_gather(*[edge.save(driver) for edge in episodic_edges])

            # Verify edges can be retrieved
            for edge in episodic_edges:
                retrieved = await EpisodicEdge.get_by_uuid(driver, edge.uuid)
                assert retrieved is not None, f'Failed to retrieve edge {edge.uuid}'
                assert retrieved.uuid == edge.uuid

            logger.info('All cross-group episodic edges saved and retrieved successfully')

        finally:
            # Cleanup
            for edge in episodic_edges:
                try:
                    await edge.delete(driver)
                except Exception:
                    pass
            for node in nodes:
                try:
                    await node.delete(driver)
                except Exception:
                    pass
            await driver.close()

    @pytest.mark.asyncio
    @unittest.skipIf(not HAS_FALKORDB, 'FalkorDB is not installed')
    async def test_same_entity_different_episodes_different_groups(self):
        """
        Test that the same entity can be mentioned by episodes from different groups
        without UUID collision.

        This is the core bug scenario:
        - Episode in group A mentions "OpenCode" (resolves to entity in group C)
        - Episode in group B also mentions "OpenCode" (same entity in group C)
        - Both MENTIONS edges should have unique UUIDs
        """
        if FalkorDriver is None:
            pytest.skip('FalkorDB driver not available')

        driver = FalkorDriver(
            host=FALKORDB_HOST,
            port=FALKORDB_PORT,
            username=FALKORDB_USER,
            password=FALKORDB_PASSWORD,
            database='test_cross_group_edges',
        )

        now = datetime.now(timezone.utc)

        episode_group_a = EpisodicNode(
            uuid=str(uuid4()),
            name='Episode in Group A',
            group_id=GROUP_A,
            source=EpisodeType.text,
            source_description='Test episode',
            content='Working on OpenCode project',
            valid_at=now,
        )

        episode_group_b = EpisodicNode(
            uuid=str(uuid4()),
            name='Episode in Group B',
            group_id=GROUP_B,
            source=EpisodeType.text,
            source_description='Test episode',
            content='Working on OpenCode project',
            valid_at=now,
        )

        entity_opencode_group_c = EntityNode(
            uuid=str(uuid4()),
            name='OpenCode',
            group_id=GROUP_C,
            labels=['Project'],
            name_embedding=[0.3] * 1024,
            summary='OpenCode is an AI coding assistant',
            created_at=now,
        )

        nodes = [episode_group_a, episode_group_b, entity_opencode_group_c]
        edges_from_a: list[EpisodicEdge] = []
        edges_from_b: list[EpisodicEdge] = []

        try:
            # Save nodes
            await semaphore_gather(*[node.save(driver) for node in nodes])

            # Build edges from episode A to OpenCode
            edges_from_a = build_episodic_edges(
                entity_nodes=[entity_opencode_group_c],
                episode_uuid=episode_group_a.uuid,
                created_at=now,
                episode_group_id=episode_group_a.group_id,
            )

            # Build edges from episode B to OpenCode
            edges_from_b = build_episodic_edges(
                entity_nodes=[entity_opencode_group_c],
                episode_uuid=episode_group_b.uuid,
                created_at=now,
                episode_group_id=episode_group_b.group_id,
            )

            # The edges should have different UUIDs
            assert edges_from_a[0].uuid != edges_from_b[0].uuid, (
                f'UUID collision! Edge from A: {edges_from_a[0].uuid}, '
                f'Edge from B: {edges_from_b[0].uuid}'
            )

            logger.info(f'Edge from group A: {edges_from_a[0].uuid}')
            logger.info(f'Edge from group B: {edges_from_b[0].uuid}')

            # Save both edges - should not collide
            all_edges = edges_from_a + edges_from_b
            await semaphore_gather(*[edge.save(driver) for edge in all_edges])

            # Verify both can be retrieved independently
            for edge in all_edges:
                retrieved = await EpisodicEdge.get_by_uuid(driver, edge.uuid)
                assert retrieved is not None

            logger.info('Both edges saved successfully without collision')

        finally:
            # Cleanup
            for edge in edges_from_a + edges_from_b:
                try:
                    await edge.delete(driver)
                except Exception:
                    pass
            for node in nodes:
                try:
                    await node.delete(driver)
                except Exception:
                    pass
            await driver.close()


class TestCrossGroupDuplicateEdgesIntegration:
    """Integration tests for cross-group IS_DUPLICATE_OF edges."""

    @pytest.mark.asyncio
    @unittest.skipIf(not HAS_FALKORDB, 'FalkorDB is not installed')
    async def test_duplicate_of_edges_across_groups(self):
        """
        Test that IS_DUPLICATE_OF edges between entities in different groups
        generate unique UUIDs.
        """
        if FalkorDriver is None:
            pytest.skip('FalkorDB driver not available')

        driver = FalkorDriver(
            host=FALKORDB_HOST,
            port=FALKORDB_PORT,
            username=FALKORDB_USER,
            password=FALKORDB_PASSWORD,
            database='test_cross_group_edges',
        )

        now = datetime.now(timezone.utc)

        # Create duplicate entities in different groups
        alice_group_a = EntityNode(
            uuid=str(uuid4()),
            name='Alice',
            group_id=GROUP_A,
            labels=['Person'],
            name_embedding=[0.1] * 1024,
            summary='Alice is a developer',
            created_at=now,
        )

        alice_group_b = EntityNode(
            uuid=str(uuid4()),
            name='Alice',
            group_id=GROUP_B,
            labels=['Person'],
            name_embedding=[0.1] * 1024,
            summary='Alice the developer',
            created_at=now,
        )

        # Episode that discovered the duplicate
        episode = EpisodicNode(
            uuid=str(uuid4()),
            name='Duplicate discovery episode',
            group_id=GROUP_A,
            source=EpisodeType.text,
            source_description='Test',
            content='Discovered Alice duplicate',
            valid_at=now,
        )

        nodes = [alice_group_a, alice_group_b, episode]
        edges: list[EntityEdge] = []

        try:
            await semaphore_gather(*[node.save(driver) for node in nodes])

            # Build IS_DUPLICATE_OF edge
            duplicate_pairs = [(alice_group_a, alice_group_b)]
            edges, merge_ops, _ = build_duplicate_of_edges(
                episode=episode,
                created_at=now,
                duplicate_nodes=duplicate_pairs,
            )

            assert len(edges) == 1
            edge = edges[0]

            logger.info(
                f'IS_DUPLICATE_OF edge UUID: {edge.uuid}, '
                f'source_group: {edge.source_node_group_id}, '
                f'target_group: {edge.target_node_group_id}'
            )

            # Verify the edge includes source/target group IDs
            assert edge.source_node_group_id == GROUP_A
            assert edge.target_node_group_id == GROUP_B

            # Generate embedding for the entity edge
            edge.fact_embedding = [0.5] * 1024

            # Save the edge
            await edge.save(driver)

            # Verify it can be retrieved
            retrieved = await EntityEdge.get_by_uuid(driver, edge.uuid)
            assert retrieved is not None
            assert retrieved.name == 'IS_DUPLICATE_OF'

            logger.info('IS_DUPLICATE_OF edge saved successfully')

        finally:
            # Cleanup
            for edge in edges:
                try:
                    await edge.delete(driver)
                except Exception:
                    pass
            for node in nodes:
                try:
                    await node.delete(driver)
                except Exception:
                    pass
            await driver.close()


class TestEdgeUUIDDeterminism:
    """Tests for deterministic UUID generation with cross-group parameters."""

    @pytest.mark.asyncio
    async def test_episodic_edge_uuid_is_deterministic(self):
        """
        Verify that episodic edges with the same parameters generate the same UUID.
        """
        now = datetime.now(timezone.utc)
        episode_uuid = str(uuid4())
        entity_uuid = str(uuid4())

        edge1 = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=entity_uuid,
            created_at=now,
            group_id=GROUP_A,
            source_node_group_id=GROUP_A,
            target_node_group_id=GROUP_B,
        )

        edge2 = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=entity_uuid,
            created_at=now,
            group_id=GROUP_A,
            source_node_group_id=GROUP_A,
            target_node_group_id=GROUP_B,
        )

        assert edge1.uuid == edge2.uuid, 'Same parameters should generate same UUID'

    @pytest.mark.asyncio
    async def test_episodic_edge_uuid_changes_with_source_group(self):
        """
        Verify that changing source_node_group_id changes the UUID.
        """
        now = datetime.now(timezone.utc)
        episode_uuid = str(uuid4())
        entity_uuid = str(uuid4())

        edge1 = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=entity_uuid,
            created_at=now,
            group_id=GROUP_A,
            source_node_group_id=GROUP_A,
            target_node_group_id=GROUP_B,
        )

        edge2 = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=entity_uuid,
            created_at=now,
            group_id=GROUP_A,
            source_node_group_id=GROUP_C,  # Different source group
            target_node_group_id=GROUP_B,
        )

        assert edge1.uuid != edge2.uuid, 'Different source_group_id should generate different UUID'

    @pytest.mark.asyncio
    async def test_episodic_edge_uuid_changes_with_target_group(self):
        """
        Verify that changing target_node_group_id changes the UUID.
        """
        now = datetime.now(timezone.utc)
        episode_uuid = str(uuid4())
        entity_uuid = str(uuid4())

        edge1 = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=entity_uuid,
            created_at=now,
            group_id=GROUP_A,
            source_node_group_id=GROUP_A,
            target_node_group_id=GROUP_B,
        )

        edge2 = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=entity_uuid,
            created_at=now,
            group_id=GROUP_A,
            source_node_group_id=GROUP_A,
            target_node_group_id=GROUP_C,  # Different target group
        )

        assert edge1.uuid != edge2.uuid, 'Different target_group_id should generate different UUID'


class TestBuildEpisodicEdgesFunction:
    """Tests for build_episodic_edges function with cross-group scenarios."""

    @pytest.mark.asyncio
    async def test_build_episodic_edges_includes_group_ids(self):
        """
        Verify that build_episodic_edges correctly sets source/target group IDs.
        """
        now = datetime.now(timezone.utc)

        episode_group_a = EpisodicNode(
            uuid=str(uuid4()),
            name='Episode in Group A',
            group_id=GROUP_A,
            source=EpisodeType.text,
            source_description='Test episode',
            content='Test content',
            valid_at=now,
        )

        entity_bob_group_b = EntityNode(
            uuid=str(uuid4()),
            name='Bob',
            group_id=GROUP_B,
            labels=['Person'],
            name_embedding=[0.2] * 1024,
            summary='Bob is a developer',
            created_at=now,
        )

        edges = build_episodic_edges(
            entity_nodes=[entity_bob_group_b],
            episode_uuid=episode_group_a.uuid,
            created_at=now,
            episode_group_id=episode_group_a.group_id,
        )

        assert len(edges) == 1
        edge = edges[0]

        assert edge.source_node_group_id == GROUP_A, "Source group should be episode's group"
        assert edge.target_node_group_id == GROUP_B, "Target group should be entity's group"
        assert edge.group_id == GROUP_B, "Edge group_id should be target's group_id"

    @pytest.mark.asyncio
    async def test_build_episodic_edges_without_episode_group_id(self):
        """
        Verify backward compatibility: build_episodic_edges works without episode_group_id.
        """
        now = datetime.now(timezone.utc)
        episode_uuid = str(uuid4())

        entity_bob_group_b = EntityNode(
            uuid=str(uuid4()),
            name='Bob',
            group_id=GROUP_B,
            labels=['Person'],
            name_embedding=[0.2] * 1024,
            summary='Bob is a developer',
            created_at=now,
        )

        edges = build_episodic_edges(
            entity_nodes=[entity_bob_group_b],
            episode_uuid=episode_uuid,
            created_at=now,
            # No episode_group_id provided
        )

        assert len(edges) == 1
        edge = edges[0]

        assert edge.source_node_group_id is None, 'Source group should be None when not provided'
        assert edge.target_node_group_id == GROUP_B, 'Target group should still be set'


class TestDatabaseEdgePersistence:
    """Tests for edge persistence with cross-group parameters."""

    @pytest.mark.asyncio
    @unittest.skipIf(not HAS_FALKORDB, 'FalkorDB is not installed')
    async def test_edge_roundtrip_preserves_group_ids(self):
        """
        Test that saving and retrieving an edge preserves cross-group information.
        """
        if FalkorDriver is None:
            pytest.skip('FalkorDB driver not available')

        driver = FalkorDriver(
            host=FALKORDB_HOST,
            port=FALKORDB_PORT,
            username=FALKORDB_USER,
            password=FALKORDB_PASSWORD,
            database='test_cross_group_edges',
        )

        now = datetime.now(timezone.utc)

        episode_group_a = EpisodicNode(
            uuid=str(uuid4()),
            name='Episode in Group A',
            group_id=GROUP_A,
            source=EpisodeType.text,
            source_description='Test episode',
            content='Test content',
            valid_at=now,
        )

        entity_bob_group_b = EntityNode(
            uuid=str(uuid4()),
            name='Bob',
            group_id=GROUP_B,
            labels=['Person'],
            name_embedding=[0.2] * 1024,
            summary='Bob is a developer',
            created_at=now,
        )

        edge: EpisodicEdge | None = None

        try:
            # Save nodes
            await episode_group_a.save(driver)
            await entity_bob_group_b.save(driver)

            # Create edge with cross-group info
            edge = EpisodicEdge(
                source_node_uuid=episode_group_a.uuid,
                target_node_uuid=entity_bob_group_b.uuid,
                created_at=now,
                group_id=entity_bob_group_b.group_id,
                source_node_group_id=episode_group_a.group_id,
                target_node_group_id=entity_bob_group_b.group_id,
            )

            original_uuid = edge.uuid
            logger.info(f'Original edge UUID: {original_uuid}')

            # Save and retrieve
            await edge.save(driver)
            retrieved = await EpisodicEdge.get_by_uuid(driver, original_uuid)

            assert retrieved is not None
            assert retrieved.uuid == original_uuid
            assert retrieved.source_node_uuid == episode_group_a.uuid
            assert retrieved.target_node_uuid == entity_bob_group_b.uuid

            logger.info('Edge roundtrip successful')

        finally:
            if edge:
                try:
                    await edge.delete(driver)
                except Exception:
                    pass
            try:
                await episode_group_a.delete(driver)
            except Exception:
                pass
            try:
                await entity_bob_group_b.delete(driver)
            except Exception:
                pass
            await driver.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--log-cli-level=DEBUG'])
