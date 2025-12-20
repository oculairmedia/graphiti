"""
Tests for verifying the correct output shape of extracted edges.

These tests ensure that edges created during extraction include all required
fields, particularly source_node_group_id and target_node_group_id which are
critical for preventing cross-group UUID collisions.
"""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

# Set deterministic UUID generation before imports
os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'

from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
from graphiti_core.utils.uuid_utils import generate_deterministic_uuid


class TestEntityEdgeOutputShape:
    """Tests for EntityEdge field completeness and correctness."""

    def test_entity_edge_has_all_required_fields(self):
        """EntityEdge should have all required fields when created properly."""
        source_uuid = generate_deterministic_uuid('source_entity', 'group_A')
        target_uuid = generate_deterministic_uuid('target_entity', 'group_B')
        episode_uuid = generate_deterministic_uuid('test_episode', 'group_A')

        edge = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target_uuid,
            name='RELATES_TO',
            group_id='group_A',
            source_node_group_id='group_A',
            target_node_group_id='group_B',
            fact='Source relates to target',
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        # Verify all required fields exist and are correct
        assert edge.uuid is not None, 'Edge must have UUID'
        assert UUID(edge.uuid), 'Edge UUID must be valid'
        assert edge.source_node_uuid == source_uuid
        assert edge.target_node_uuid == target_uuid
        assert edge.name == 'RELATES_TO'
        assert edge.group_id == 'group_A'
        assert edge.source_node_group_id == 'group_A'
        assert edge.target_node_group_id == 'group_B'
        assert edge.fact == 'Source relates to target'
        assert episode_uuid in edge.episodes
        assert edge.created_at is not None
        assert edge.valid_at is not None

    def test_entity_edge_uuid_includes_group_ids_in_calculation(self):
        """
        Edge UUID should include source/target group_ids in calculation.

        Same edge endpoints with different group_ids should produce different UUIDs.
        """
        source_uuid = generate_deterministic_uuid('entity', 'group_A')
        target_uuid = generate_deterministic_uuid('target', 'group_B')
        episode_uuid = generate_deterministic_uuid('episode', 'group_A')

        # Edge with source in group_A
        edge_a = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target_uuid,
            name='RELATES_TO',
            group_id='group_A',
            source_node_group_id='group_A',
            target_node_group_id='group_B',
            fact='Test fact',
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        # Same edge but source claims to be in group_C
        edge_b = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target_uuid,
            name='RELATES_TO',
            group_id='group_A',
            source_node_group_id='group_C',  # Different source group
            target_node_group_id='group_B',
            fact='Test fact',
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        assert edge_a.uuid != edge_b.uuid, (
            'Edges with different source_node_group_id should have different UUIDs'
        )

    def test_entity_edge_without_group_ids_still_works(self):
        """
        EntityEdge should still work without source/target group_ids for
        backward compatibility, but this is not recommended.
        """
        source_uuid = generate_deterministic_uuid('source', 'group')
        target_uuid = generate_deterministic_uuid('target', 'group')
        episode_uuid = generate_deterministic_uuid('episode', 'group')

        # Create edge without source/target group_ids (legacy behavior)
        edge = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target_uuid,
            name='RELATES_TO',
            group_id='group',
            fact='Test fact',
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        assert edge.uuid is not None
        assert UUID(edge.uuid)
        assert edge.source_node_group_id is None
        assert edge.target_node_group_id is None


class TestEpisodicEdgeOutputShape:
    """Tests for EpisodicEdge field completeness and correctness."""

    def test_episodic_edge_has_all_required_fields(self):
        """EpisodicEdge should have all required fields when created properly."""
        episode_uuid = generate_deterministic_uuid('episode', 'episode_group')
        entity_uuid = generate_deterministic_uuid('entity', 'entity_group')

        edge = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=entity_uuid,
            group_id='entity_group',
            source_node_group_id='episode_group',
            target_node_group_id='entity_group',
            created_at=datetime.now(timezone.utc),
        )

        assert edge.uuid is not None
        assert UUID(edge.uuid)
        assert edge.source_node_uuid == episode_uuid
        assert edge.target_node_uuid == entity_uuid
        assert edge.group_id == 'entity_group'
        assert edge.source_node_group_id == 'episode_group'
        assert edge.target_node_group_id == 'entity_group'


class TestExtractEdgesOutputShape:
    """Tests for extract_edges function output shape."""

    @pytest.mark.asyncio
    async def test_extract_edges_includes_source_target_group_ids(self):
        """
        Edges created by extract_edges should include source_node_group_id
        and target_node_group_id from the source/target nodes.
        """
        from graphiti_core.utils.maintenance.edge_operations import extract_edges

        # Create mock episode
        episode = EpisodicNode(
            uuid=generate_deterministic_uuid('test_episode', 'agent_group'),
            name='test_episode',
            group_id='agent_group',
            source=EpisodeType.message,
            source_description='Test conversation',
            content='Alice works with Bob at Acme Corp',
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        # Create entity nodes with different group_ids
        alice = EntityNode(
            uuid=generate_deterministic_uuid('alice', 'users_group'),
            name='alice',
            group_id='users_group',
            created_at=datetime.now(timezone.utc),
        )
        bob = EntityNode(
            uuid=generate_deterministic_uuid('bob', 'users_group'),
            name='bob',
            group_id='users_group',
            created_at=datetime.now(timezone.utc),
        )
        acme = EntityNode(
            uuid=generate_deterministic_uuid('acme_corp', 'companies_group'),
            name='acme_corp',
            group_id='companies_group',
            created_at=datetime.now(timezone.utc),
        )

        nodes = [alice, bob, acme]

        # Mock LLM response
        mock_llm_response = {
            'edges': [
                {
                    'source_entity_id': 0,  # alice
                    'target_entity_id': 1,  # bob
                    'relation_type': 'WORKS_WITH',
                    'fact': 'Alice works with Bob',
                },
                {
                    'source_entity_id': 0,  # alice
                    'target_entity_id': 2,  # acme
                    'relation_type': 'EMPLOYED_BY',
                    'fact': 'Alice is employed by Acme Corp',
                },
            ]
        }

        # Mock clients
        mock_llm_client = AsyncMock()
        mock_llm_client.generate_response = AsyncMock(return_value=mock_llm_response)

        mock_clients = MagicMock()
        mock_clients.llm_client = mock_llm_client

        # Call extract_edges
        edges = await extract_edges(
            clients=mock_clients,
            episode=episode,
            nodes=nodes,
            previous_episodes=[],
            edge_type_map={},
            group_id='agent_group',
        )

        assert len(edges) == 2, f'Expected 2 edges, got {len(edges)}'

        # Verify first edge (alice -> bob)
        edge1 = edges[0]
        assert edge1.source_node_uuid == alice.uuid
        assert edge1.target_node_uuid == bob.uuid
        assert edge1.name == 'WORKS_WITH'
        assert edge1.source_node_group_id == 'users_group', (
            f"source_node_group_id should be 'users_group', got '{edge1.source_node_group_id}'"
        )
        assert edge1.target_node_group_id == 'users_group', (
            f"target_node_group_id should be 'users_group', got '{edge1.target_node_group_id}'"
        )

        # Verify second edge (alice -> acme)
        edge2 = edges[1]
        assert edge2.source_node_uuid == alice.uuid
        assert edge2.target_node_uuid == acme.uuid
        assert edge2.name == 'EMPLOYED_BY'
        assert edge2.source_node_group_id == 'users_group', (
            f"source_node_group_id should be 'users_group', got '{edge2.source_node_group_id}'"
        )
        assert edge2.target_node_group_id == 'companies_group', (
            f"target_node_group_id should be 'companies_group', got '{edge2.target_node_group_id}'"
        )

    @pytest.mark.asyncio
    async def test_extract_edges_cross_group_no_uuid_collision(self):
        """
        Edges connecting entities from different groups should not have
        UUID collisions even with same edge name and fact.
        """
        from graphiti_core.utils.maintenance.edge_operations import extract_edges

        # Create two episodes from different groups
        episode1 = EpisodicNode(
            uuid=generate_deterministic_uuid('episode1', 'agent_A'),
            name='episode1',
            group_id='agent_A',
            source=EpisodeType.message,
            source_description='Test conversation',
            content='Alice likes Python',
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        # Create nodes - same names but could have different UUIDs
        alice_a = EntityNode(
            uuid=generate_deterministic_uuid('alice', 'group_A'),
            name='alice',
            group_id='group_A',
            created_at=datetime.now(timezone.utc),
        )
        python_a = EntityNode(
            uuid=generate_deterministic_uuid('python', 'shared_group'),
            name='python',
            group_id='shared_group',
            created_at=datetime.now(timezone.utc),
        )

        alice_b = EntityNode(
            uuid=generate_deterministic_uuid('alice', 'group_B'),
            name='alice',
            group_id='group_B',
            created_at=datetime.now(timezone.utc),
        )

        # Same LLM response for both
        mock_response = {
            'edges': [
                {
                    'source_entity_id': 0,
                    'target_entity_id': 1,
                    'relation_type': 'LIKES',
                    'fact': 'Alice likes Python',
                },
            ]
        }

        mock_llm_client = AsyncMock()
        mock_llm_client.generate_response = AsyncMock(return_value=mock_response)

        mock_clients = MagicMock()
        mock_clients.llm_client = mock_llm_client

        # Extract edges for first group
        edges1 = await extract_edges(
            clients=mock_clients,
            episode=episode1,
            nodes=[alice_a, python_a],
            previous_episodes=[],
            edge_type_map={},
            group_id='agent_A',
        )

        # Extract edges for second group (different alice)
        edges2 = await extract_edges(
            clients=mock_clients,
            episode=episode1,
            nodes=[alice_b, python_a],
            previous_episodes=[],
            edge_type_map={},
            group_id='agent_B',
        )

        assert len(edges1) == 1
        assert len(edges2) == 1

        # UUIDs should be different because source nodes are in different groups
        assert edges1[0].uuid != edges2[0].uuid, (
            f'Cross-group edges should have different UUIDs.\n'
            f'Edge 1 UUID: {edges1[0].uuid}\n'
            f'Edge 2 UUID: {edges2[0].uuid}'
        )

        # Verify group_ids are set correctly
        assert edges1[0].source_node_group_id == 'group_A'
        assert edges2[0].source_node_group_id == 'group_B'


class TestEdgeSchemaValidation:
    """Tests for edge schema validation."""

    def test_entity_edge_schema_fields(self):
        """Verify EntityEdge has all expected schema fields."""
        expected_fields = {
            'uuid',
            'source_node_uuid',
            'target_node_uuid',
            'name',
            'group_id',
            'source_node_group_id',
            'target_node_group_id',
            'fact',
            'fact_embedding',
            'episodes',
            'created_at',
            'valid_at',
            'invalid_at',
            'expired_at',
        }

        actual_fields = set(EntityEdge.__fields__.keys())
        missing_fields = expected_fields - actual_fields

        assert not missing_fields, f'EntityEdge is missing expected fields: {missing_fields}'

    def test_episodic_edge_schema_fields(self):
        """Verify EpisodicEdge has all expected schema fields."""
        expected_fields = {
            'uuid',
            'source_node_uuid',
            'target_node_uuid',
            'group_id',
            'source_node_group_id',
            'target_node_group_id',
            'created_at',
        }

        actual_fields = set(EpisodicEdge.__fields__.keys())
        missing_fields = expected_fields - actual_fields

        assert not missing_fields, f'EpisodicEdge is missing expected fields: {missing_fields}'


class TestEdgeUUIDUniqueness:
    """Tests for edge UUID uniqueness across different scenarios."""

    def test_same_source_different_targets_unique_uuids(self):
        """Same source to different targets should have unique UUIDs."""
        source_uuid = generate_deterministic_uuid('source', 'group')
        target1_uuid = generate_deterministic_uuid('target1', 'group')
        target2_uuid = generate_deterministic_uuid('target2', 'group')
        episode_uuid = generate_deterministic_uuid('episode', 'group')

        edge1 = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target1_uuid,
            name='RELATES_TO',
            group_id='group',
            source_node_group_id='group',
            target_node_group_id='group',
            fact='Source relates to target1',
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        edge2 = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target2_uuid,
            name='RELATES_TO',
            group_id='group',
            source_node_group_id='group',
            target_node_group_id='group',
            fact='Source relates to target2',
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        assert edge1.uuid != edge2.uuid

    def test_different_sources_same_target_unique_uuids(self):
        """Different sources to same target should have unique UUIDs."""
        source1_uuid = generate_deterministic_uuid('source1', 'group')
        source2_uuid = generate_deterministic_uuid('source2', 'group')
        target_uuid = generate_deterministic_uuid('target', 'group')
        episode_uuid = generate_deterministic_uuid('episode', 'group')

        edge1 = EntityEdge(
            source_node_uuid=source1_uuid,
            target_node_uuid=target_uuid,
            name='RELATES_TO',
            group_id='group',
            source_node_group_id='group',
            target_node_group_id='group',
            fact='Source1 relates to target',
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        edge2 = EntityEdge(
            source_node_uuid=source2_uuid,
            target_node_uuid=target_uuid,
            name='RELATES_TO',
            group_id='group',
            source_node_group_id='group',
            target_node_group_id='group',
            fact='Source2 relates to target',
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        assert edge1.uuid != edge2.uuid, (
            f'Different source nodes should produce different UUIDs.\n'
            f'Source1 UUID: {source1_uuid}\n'
            f'Source2 UUID: {source2_uuid}\n'
            f'Edge1 UUID: {edge1.uuid}\n'
            f'Edge2 UUID: {edge2.uuid}'
        )

    def test_same_fact_different_sources_unique_uuids(self):
        """
        Same fact content but different source nodes should have unique UUIDs.

        This is the exact scenario that caused the bug:
        - agent_reasoning -> target with fact "User likes option 2..."
        - houdini -> target with same fact
        Should NOT collide!
        """
        source1_uuid = generate_deterministic_uuid('agent_reasoning', 'agent_group')
        source2_uuid = generate_deterministic_uuid('houdini', 'agent_group')
        target_uuid = generate_deterministic_uuid('user_preference', 'agent_group')
        episode_uuid = generate_deterministic_uuid('episode', 'agent_group')

        same_fact = 'User likes option 2 real time export from Houdini'

        edge1 = EntityEdge(
            source_node_uuid=source1_uuid,
            target_node_uuid=target_uuid,
            name='RELATES_TO',
            group_id='agent_group',
            source_node_group_id='agent_group',
            target_node_group_id='agent_group',
            fact=same_fact,
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        edge2 = EntityEdge(
            source_node_uuid=source2_uuid,
            target_node_uuid=target_uuid,
            name='RELATES_TO',
            group_id='agent_group',
            source_node_group_id='agent_group',
            target_node_group_id='agent_group',
            fact=same_fact,  # Same fact!
            episodes=[episode_uuid],
            created_at=datetime.now(timezone.utc),
            valid_at=datetime.now(timezone.utc),
        )

        assert edge1.uuid != edge2.uuid, (
            f'Edges with same fact but different sources MUST have different UUIDs.\n'
            f'This was the bug that caused UUID collisions!\n'
            f'Source1 (agent_reasoning): {source1_uuid}\n'
            f'Source2 (houdini): {source2_uuid}\n'
            f'Edge1 UUID: {edge1.uuid}\n'
            f'Edge2 UUID: {edge2.uuid}'
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
