"""
Tests for cross-group edge UUID collision prevention.

These tests ensure that edges connecting entities from different group_ids
generate unique UUIDs and don't collide with edges in other graph partitions.

This addresses the issue where:
1. Entity "opencode" exists in group "claude_conversations" with UUID 07cd3977...
2. Entity "opencode" exists in group "agent-597b5756..." with UUID ed4d955a...
3. An edge between these entities would previously generate a UUID that could
   collide with an existing edge in a different context.
"""

import os
import pytest
from datetime import datetime
from uuid import UUID

# Set deterministic UUID generation before imports
os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'

from graphiti_core.utils.uuid_utils import (
    generate_deterministic_uuid,
    generate_deterministic_edge_uuid,
)
from graphiti_core.edges import EpisodicEdge, EntityEdge
from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType


class TestCrossGroupEdgeUUID:
    """Test cases for cross-group edge UUID generation."""

    def test_same_entities_different_groups_generate_different_edge_uuids(self):
        """
        When the same edge name connects entities with same names but different groups,
        the edge UUIDs should be different.

        This prevents the UUID collision that was occurring when:
        - Edge from opencode(group_A) -> target(group_B)
        - Edge from opencode(group_C) -> target(group_D)
        Would generate the same UUID despite being in different contexts.
        """
        # Entity "opencode" in group A
        entity_a_uuid = generate_deterministic_uuid('opencode', 'group_A')
        entity_a_group = 'group_A'

        # Entity "opencode" in group B (same name, different group = different UUID)
        entity_b_uuid = generate_deterministic_uuid('opencode', 'group_B')
        entity_b_group = 'group_B'

        # Shared target entity
        target_uuid = generate_deterministic_uuid('target', 'shared_group')
        target_group = 'shared_group'

        # Edge from entity_a to target (with group_ids)
        edge_uuid_1 = generate_deterministic_edge_uuid(
            source_uuid=entity_a_uuid,
            target_uuid=target_uuid,
            name='RELATES_TO',
            group_id='group_A',
            source_group_id=entity_a_group,
            target_group_id=target_group,
        )

        # Edge from entity_b to target (with group_ids)
        edge_uuid_2 = generate_deterministic_edge_uuid(
            source_uuid=entity_b_uuid,
            target_uuid=target_uuid,
            name='RELATES_TO',
            group_id='group_B',
            source_group_id=entity_b_group,
            target_group_id=target_group,
        )

        # These should be different UUIDs
        assert edge_uuid_1 != edge_uuid_2, (
            f'Cross-group edges should have different UUIDs.\n'
            f'Edge 1 (group_A -> shared_group): {edge_uuid_1}\n'
            f'Edge 2 (group_B -> shared_group): {edge_uuid_2}'
        )

    def test_same_edge_generates_same_uuid(self):
        """
        The same edge (same source, target, name, and groups) should always
        generate the same UUID for idempotency.
        """
        source_uuid = '07cd3977-f459-57d0-844c-b3e6634c4a44'
        target_uuid = '58d330ed-c783-5bb2-9116-4c928ccec50f'
        edge_name = 'RELATES_TO'
        group_id = 'test_group'
        source_group = 'source_group'
        target_group = 'target_group'

        uuid_1 = generate_deterministic_edge_uuid(
            source_uuid,
            target_uuid,
            edge_name,
            group_id,
            source_group_id=source_group,
            target_group_id=target_group,
        )

        uuid_2 = generate_deterministic_edge_uuid(
            source_uuid,
            target_uuid,
            edge_name,
            group_id,
            source_group_id=source_group,
            target_group_id=target_group,
        )

        assert uuid_1 == uuid_2, 'Same edge should generate same UUID'

    def test_backward_compatibility_without_group_ids(self):
        """
        When source_group_id and target_group_id are not provided,
        the function should still work (backward compatibility).
        """
        source_uuid = '07cd3977-f459-57d0-844c-b3e6634c4a44'
        target_uuid = '58d330ed-c783-5bb2-9116-4c928ccec50f'

        # Without group_ids (legacy behavior)
        uuid_legacy = generate_deterministic_edge_uuid(
            source_uuid, target_uuid, 'RELATES_TO', 'test_group'
        )

        # Should still be valid UUID
        assert UUID(uuid_legacy), 'Should generate valid UUID without group_ids'

    def test_episodic_edge_includes_group_ids(self):
        """
        EpisodicEdge should include source_node_group_id and target_node_group_id
        when created, to prevent cross-group UUID collisions.
        """
        # Use valid UUIDs
        episode_uuid = generate_deterministic_uuid('test_episode', 'episode_group')
        episode_group = 'episode_group'
        entity_uuid = generate_deterministic_uuid('test_entity', 'entity_group')
        entity_group = 'entity_group'

        # Create edge with group_ids
        edge = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=entity_uuid,
            created_at=datetime.now(),
            group_id=entity_group,
            source_node_group_id=episode_group,
            target_node_group_id=entity_group,
        )

        # Should have valid UUID
        assert edge.uuid, 'Edge should have UUID'
        assert UUID(edge.uuid), 'Edge UUID should be valid'

        # Group IDs should be stored
        assert edge.source_node_group_id == episode_group
        assert edge.target_node_group_id == entity_group

    def test_entity_edge_includes_group_ids(self):
        """
        EntityEdge should include source_node_group_id and target_node_group_id
        when created, to prevent cross-group UUID collisions.
        """
        source_uuid = generate_deterministic_uuid('source_entity', 'group_A')
        target_uuid = generate_deterministic_uuid('target_entity', 'group_B')
        episode_uuid = generate_deterministic_uuid('episode', 'group_A')

        edge = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target_uuid,
            name='RELATES_TO',
            group_id='group_A',
            source_node_group_id='group_A',
            target_node_group_id='group_B',
            fact='Source relates to target',
            episodes=[episode_uuid],
            created_at=datetime.now(),
            valid_at=datetime.now(),
        )

        assert edge.uuid, 'Edge should have UUID'
        assert UUID(edge.uuid), 'Edge UUID should be valid'
        assert edge.source_node_group_id == 'group_A'
        assert edge.target_node_group_id == 'group_B'

    def test_cross_group_mentions_edges_are_unique(self):
        """
        Simulate the real-world scenario where an episode in one group
        mentions entities that exist in another group (cross-graph deduplication).

        This was the actual bug:
        - Episode in agent-597b5756... group mentions "opencode"
        - "opencode" resolves to entity in claude_conversations group
        - MENTIONS edge UUID would collide with existing edge
        """
        # Episode from agent A (use valid UUIDs)
        episode_a_uuid = generate_deterministic_uuid('episode_a', 'agent-A-group')
        episode_a_group = 'agent-A-group'

        # Episode from agent B
        episode_b_uuid = generate_deterministic_uuid('episode_b', 'agent-B-group')
        episode_b_group = 'agent-B-group'

        # Shared entity "opencode" (resolved via cross-graph dedup)
        opencode_uuid = generate_deterministic_uuid('opencode', 'shared_group')
        opencode_group = 'shared_group'

        # MENTIONS edge from episode A to opencode
        edge_a = EpisodicEdge(
            source_node_uuid=episode_a_uuid,
            target_node_uuid=opencode_uuid,
            created_at=datetime.now(),
            group_id=opencode_group,  # Edge inherits target's group
            source_node_group_id=episode_a_group,
            target_node_group_id=opencode_group,
        )

        # MENTIONS edge from episode B to opencode
        edge_b = EpisodicEdge(
            source_node_uuid=episode_b_uuid,
            target_node_uuid=opencode_uuid,
            created_at=datetime.now(),
            group_id=opencode_group,  # Same target group
            source_node_group_id=episode_b_group,
            target_node_group_id=opencode_group,
        )

        # These should have different UUIDs despite same target and group
        assert edge_a.uuid != edge_b.uuid, (
            f'MENTIONS edges from different episodes should have different UUIDs.\n'
            f'Edge A (from {episode_a_group}): {edge_a.uuid}\n'
            f'Edge B (from {episode_b_group}): {edge_b.uuid}'
        )

    def test_original_collision_scenario(self):
        """
        Reproduce the exact collision scenario from the bug:

        Existing edge: opencode(07cd3977, claude_conversations) ->
                       agent_reasoningsystem(58d330ed, agent-fe8a9291...)
                       with UUID 27ff95a1-60b6-5307-973b-ff21f3faafd2

        New edge attempted: opencode(ed4d955a, agent-597b5756...) ->
                           opencode(07cd3977, claude_conversations)

        Before fix: Both would generate same UUID -> DuplicateEdgeError
        After fix: Different UUIDs -> No collision
        """
        # Existing edge endpoints
        existing_source = '07cd3977-f459-57d0-844c-b3e6634c4a44'
        existing_source_group = 'claude_conversations'
        existing_target = '58d330ed-c783-5bb2-9116-4c928ccec50f'
        existing_target_group = 'agent-fe8a9291-b49a-4fc1-94c3-1a23b86b6108'

        # New edge endpoints (cross-group)
        new_source = 'ed4d955a-d9d5-55f3-9574-8bf9e9ee2aa4'
        new_source_group = 'agent-597b5756-2915-4560-ba6b-91005f085166'
        new_target = existing_source  # Points to the old opencode
        new_target_group = existing_source_group

        # Generate UUIDs with group_ids included
        existing_edge_uuid = generate_deterministic_edge_uuid(
            existing_source,
            existing_target,
            'SENT_IMAGES_TO',
            existing_source_group,
            source_group_id=existing_source_group,
            target_group_id=existing_target_group,
        )

        new_edge_uuid = generate_deterministic_edge_uuid(
            new_source,
            new_target,
            'RELATES_TO',
            new_source_group,
            source_group_id=new_source_group,
            target_group_id=new_target_group,
        )

        assert existing_edge_uuid != new_edge_uuid, (
            f'Cross-group edges should NOT collide.\n'
            f'Existing edge UUID: {existing_edge_uuid}\n'
            f'New edge UUID: {new_edge_uuid}'
        )


class TestEdgeUUIDDeterminism:
    """Tests to ensure edge UUIDs remain deterministic."""

    def test_uuid_is_deterministic_with_all_parameters(self):
        """UUID generation should be fully deterministic given same inputs."""
        params = {
            'source_uuid': 'source-123',
            'target_uuid': 'target-456',
            'name': 'RELATES_TO',
            'group_id': 'my_group',
            'source_group_id': 'source_group',
            'target_group_id': 'target_group',
        }

        # Generate multiple times
        uuids = [generate_deterministic_edge_uuid(**params) for _ in range(10)]

        # All should be identical
        assert len(set(uuids)) == 1, 'All UUIDs should be identical for same inputs'

    def test_different_edge_names_produce_different_uuids(self):
        """Different edge names should produce different UUIDs."""
        base_params = {
            'source_uuid': 'source-123',
            'target_uuid': 'target-456',
            'group_id': 'my_group',
            'source_group_id': 'source_group',
            'target_group_id': 'target_group',
        }

        uuid_relates_to = generate_deterministic_edge_uuid(**base_params, name='RELATES_TO')
        uuid_mentions = generate_deterministic_edge_uuid(**base_params, name='MENTIONS')
        uuid_is_duplicate = generate_deterministic_edge_uuid(**base_params, name='IS_DUPLICATE_OF')

        assert uuid_relates_to != uuid_mentions
        assert uuid_relates_to != uuid_is_duplicate
        assert uuid_mentions != uuid_is_duplicate


class TestBuildEpisodicEdgesIntegration:
    """Integration tests for build_episodic_edges with cross-group support."""

    def test_build_episodic_edges_passes_group_ids(self):
        """
        build_episodic_edges should pass episode_group_id to prevent
        cross-group UUID collisions.
        """
        from graphiti_core.utils.maintenance.edge_operations import build_episodic_edges

        # Create entity nodes
        entity1 = EntityNode(
            uuid=generate_deterministic_uuid('entity1', 'entity_group'),
            name='entity1',
            group_id='entity_group',
            created_at=datetime.now(),
        )
        entity2 = EntityNode(
            uuid=generate_deterministic_uuid('entity2', 'entity_group'),
            name='entity2',
            group_id='entity_group',
            created_at=datetime.now(),
        )

        # Build edges with episode_group_id (use valid UUID)
        episode_uuid = generate_deterministic_uuid('episode_123', 'episode_group')
        episode_group = 'episode_group'

        edges = build_episodic_edges(
            entity_nodes=[entity1, entity2],
            episode_uuid=episode_uuid,
            created_at=datetime.now(),
            episode_group_id=episode_group,
        )

        assert len(edges) == 2

        for edge in edges:
            assert edge.source_node_group_id == episode_group
            assert edge.target_node_group_id == 'entity_group'

    def test_build_episodic_edges_without_episode_group_backward_compatible(self):
        """
        build_episodic_edges should work without episode_group_id for
        backward compatibility.
        """
        from graphiti_core.utils.maintenance.edge_operations import build_episodic_edges

        entity = EntityNode(
            uuid=generate_deterministic_uuid('entity', 'my_group'),
            name='entity',
            group_id='my_group',
            created_at=datetime.now(),
        )

        # Build without episode_group_id (use valid UUID)
        episode_uuid = generate_deterministic_uuid('episode', 'my_group')
        edges = build_episodic_edges(
            entity_nodes=[entity],
            episode_uuid=episode_uuid,
            created_at=datetime.now(),
        )

        assert len(edges) == 1
        assert edges[0].source_node_group_id is None
        assert edges[0].target_node_group_id == 'my_group'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
